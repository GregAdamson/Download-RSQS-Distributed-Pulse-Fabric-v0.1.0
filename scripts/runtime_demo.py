#!/usr/bin/env python3
import os
import sys
import tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rsqs_pulse.cognitive_loop import Observation
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.runtime import FabricRuntime, RuntimeTransition
from rsqs_pulse.state_reasoning import Constraint, State, Transition


with tempfile.TemporaryDirectory() as directory:
    db = os.path.join(directory, "runtime.db")
    runtime = FabricRuntime("demo-node", db, LocalPolicy(allowed_capabilities={"counter.increment"}))
    runtime.register_capability("counter.increment", lambda args: {"delta": args.get("delta", 1)})

    increment = Transition(
        "increment",
        "counter.increment",
        lambda state: State({**state.values, "counter": state.values.get("counter", 0) + 1}),
        cost=1,
    )
    result = runtime.run_cycle(
        [Observation("demo-sensor", {"counter": 0})],
        lambda state: state.values.get("counter") == 3,
        [RuntimeTransition(increment, {"delta": 1})],
        [Constraint("upper-bound", lambda state: state.values.get("counter", 0) <= 3)],
        max_depth=4,
    )
    print("cycle", result.status, result.executed, result.final_state)
    print("health", runtime.health())
    runtime.close()

    restored = FabricRuntime("demo-node", db, LocalPolicy(allowed_capabilities={"counter.increment"}))
    print("restored-state", restored.current_state().values)
    print("restored-health", restored.health())
    restored.close()
