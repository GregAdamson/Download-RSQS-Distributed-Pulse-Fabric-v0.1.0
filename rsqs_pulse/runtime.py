from __future__ import annotations
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List

from .capabilities import CapabilityAdvertisement, CapabilityRegistry
from .cognitive_loop import CognitiveLoop, Observation
from .dal import DALGraph, DALNode
from .identity import NodeIdentity
from .persistent import SQLiteState
from .policy import LocalPolicy
from .provenance import ProvenanceLedger
from .state_reasoning import Constraint, State, Transition
from .world_state import WorldState


@dataclass(frozen=True)
class RuntimeTransition:
    transition: Transition
    args: Dict[str, Any]
    reduce: Callable[[State, Dict[str, Any]], State] | None = None


@dataclass(frozen=True)
class RuntimeCycleResult:
    cycle_id: str
    status: str
    start_state: Dict[str, Any]
    final_state: Dict[str, Any]
    executed: tuple[str, ...]
    reason: str


class FabricRuntime:
    def __init__(self, node_id: str, state_path: str, policy: LocalPolicy, identity: NodeIdentity | None = None) -> None:
        self.node_id = node_id
        self.state = SQLiteState(state_path)
        self.policy = policy
        self.identity = identity or NodeIdentity(node_id)
        self.world = WorldState(self.state.conn)
        self.registry = CapabilityRegistry(self.state)
        self.ledger = ProvenanceLedger(self.state.conn)
        self.cognitive = CognitiveLoop()
        self.dal = DALGraph()
        self.handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._init_runtime_schema()

    def _init_runtime_schema(self) -> None:
        self.state.conn.executescript("""
        CREATE TABLE IF NOT EXISTS runtime_cycles(
          cycle_id TEXT PRIMARY KEY, created_at INTEGER NOT NULL, status TEXT NOT NULL,
          input_json TEXT NOT NULL, output_json TEXT NOT NULL, reason TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runtime_actions(
          cycle_id TEXT NOT NULL, seq INTEGER NOT NULL, capability TEXT NOT NULL,
          args_json TEXT NOT NULL, output_json TEXT NOT NULL, status TEXT NOT NULL,
          PRIMARY KEY(cycle_id, seq)
        );
        """)
        self.state.conn.commit()

    def register_capability(self, name: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]], version: str = "1", metadata: Dict[str, Any] | None = None) -> None:
        self.handlers[name] = handler
        self.registry.advertise(CapabilityAdvertisement(self.node_id, name, version, metadata or {}))

    def current_state(self) -> State:
        rows = self.state.conn.execute("""
          SELECT w.key,w.value_json FROM world_state w
          JOIN (SELECT key,MAX(version) AS version FROM world_state GROUP BY key) x
          ON x.key=w.key AND x.version=w.version ORDER BY w.key
        """).fetchall()
        return State({key: json.loads(value) for key, value in rows})

    def observe(self, observations: Iterable[Observation]) -> State:
        observations = tuple(observations)
        current = self.current_state()
        perceived = self.cognitive.perceive(current, observations)
        for observation in observations:
            for key, value in sorted(observation.values.items()):
                self.world.assert_fact(key, value, observation.source)
                node_id = f"obs:{uuid.uuid4()}"
                self.dal.add_node(DALNode("OBSERVATION", node_id, {"source": observation.source, "key": key, "value": value}))
                self.ledger.append("observation", node_id, {"source": observation.source, "key": key, "value": value})
        return perceived

    def run_cycle(self, observations: Iterable[Observation], desired: Callable[[State], bool], transitions: Iterable[RuntimeTransition], constraints: Iterable[Constraint] = (), max_depth: int = 4) -> RuntimeCycleResult:
        cycle_id = str(uuid.uuid4())
        start = self.observe(observations)
        transition_map = {item.transition.name: item for item in transitions}

        def authorise(trajectory):
            for transition in trajectory.transitions:
                if transition.capability not in self.handlers:
                    return False, f"capability unavailable: {transition.capability}"
                if not self.policy.permits_capability(transition.capability):
                    return False, f"local policy denied: {transition.capability}"
            return True, "local policy permits trajectory"

        decision = self.cognitive.decide(start, desired, [x.transition for x in transition_map.values()], constraints, authorise, max_depth)
        if not decision.authorised or decision.trajectory is None:
            result = RuntimeCycleResult(cycle_id, "denied", start.values, start.values, (), decision.reason)
            self._record_cycle(result)
            self.ledger.append("cycle_denied", cycle_id, {"reason": decision.reason})
            return result

        working = start
        executed: List[str] = []
        for seq, transition in enumerate(decision.trajectory.transitions, start=1):
            spec = transition_map[transition.name]
            handler = self.handlers[transition.capability]
            self._record_action(cycle_id, seq, transition.capability, spec.args, {}, "pending")
            try:
                output = handler(dict(spec.args))
                if not isinstance(output, dict):
                    raise TypeError("capability output must be a dictionary")
                next_state = spec.reduce(working, output) if spec.reduce is not None else transition.apply(working)
                for constraint in constraints:
                    if not constraint.predicate(next_state):
                        raise ValueError(f"execution result violates constraint: {constraint.name}")
            except Exception as exc:
                self._record_action(cycle_id, seq, transition.capability, spec.args, {"error": str(exc)}, "failed")
                self.ledger.append("action_failed", f"{cycle_id}:{seq}", {"capability": transition.capability, "error": str(exc)})
                result = RuntimeCycleResult(cycle_id, "failed", start.values, working.values, tuple(executed), str(exc))
                self._record_cycle(result)
                return result

            working = next_state
            for key, value in sorted(working.values.items()):
                previous = self.world.latest(key)
                if previous is None or previous.value != value:
                    self.world.assert_fact(key, value, f"action:{transition.capability}")
            self._record_action(cycle_id, seq, transition.capability, spec.args, output, "ok")
            executed.append(transition.name)
            self.ledger.append("action", f"{cycle_id}:{seq}", {"capability": transition.capability, "args": spec.args, "output": output})

        status = "achieved" if desired(working) else "incomplete"
        result = RuntimeCycleResult(cycle_id, status, start.values, working.values, tuple(executed), decision.reason)
        self._record_cycle(result)
        self.ledger.append("cycle_complete", cycle_id, {"status": status, "executed": executed})
        return result

    def _record_action(self, cycle_id: str, seq: int, capability: str, args: Dict[str, Any], output: Dict[str, Any], status: str) -> None:
        self.state.conn.execute(
            """INSERT INTO runtime_actions(cycle_id,seq,capability,args_json,output_json,status)
               VALUES(?,?,?,?,?,?) ON CONFLICT(cycle_id,seq) DO UPDATE SET
               output_json=excluded.output_json,status=excluded.status""",
            (cycle_id, seq, capability, json.dumps(args, sort_keys=True), json.dumps(output, sort_keys=True), status),
        )
        self.state.conn.commit()

    def _record_cycle(self, result: RuntimeCycleResult) -> None:
        self.state.conn.execute(
            """INSERT OR REPLACE INTO runtime_cycles(cycle_id,created_at,status,input_json,output_json,reason)
               VALUES(?,?,?,?,?,?)""",
            (result.cycle_id, int(time.time()), result.status, json.dumps(result.start_state, sort_keys=True), json.dumps(result.final_state, sort_keys=True), result.reason),
        )
        self.state.conn.commit()

    def health(self) -> Dict[str, Any]:
        cycles = int(self.state.conn.execute("SELECT COUNT(*) FROM runtime_cycles").fetchone()[0])
        actions = int(self.state.conn.execute("SELECT COUNT(*) FROM runtime_actions").fetchone()[0])
        failed = int(self.state.conn.execute("SELECT COUNT(*) FROM runtime_actions WHERE status='failed'").fetchone()[0])
        return {"node_id": self.node_id, "status": "ok" if failed == 0 else "degraded", "cycles": cycles, "actions": actions, "failed_actions": failed, "provenance_valid": self.ledger.verify(), "capabilities": sorted(self.handlers)}

    def close(self) -> None:
        self.state.conn.close()
