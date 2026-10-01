#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rsqs_pulse.broker import InMemoryBroker
from rsqs_pulse.capabilities import CapabilityAdvertisement, CapabilityRegistry
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.offline import OfflineJournal
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.quorum import QuorumRule
from rsqs_pulse.secure import SecureCoordinator, SecureNode
from rsqs_pulse.simulation import Simulator
from rsqs_pulse.swarm import SwarmPlanner
from rsqs_pulse.taskgraph import GraphTask, TaskGraph


broker = InMemoryBroker()
authority_identity = NodeIdentity("authority")
coordinator_state = SQLiteState(":memory:")
coordinator = SecureCoordinator("rsqs-global", authority_identity, broker, coordinator_state)

node_state_a = SQLiteState(":memory:")
node_state_b = SQLiteState(":memory:")
policy = LocalPolicy(allowed_capabilities={"math.scale", "text.upper"})

node_a = SecureNode("node-a", "rsqs-global", authority_identity.public, policy, node_state_a)
node_b = SecureNode("node-b", "rsqs-global", authority_identity.public, policy, node_state_b)

node_a.register("math.scale", lambda args: {"result": args["value"] * 2})
node_b.register("text.upper", lambda args: {"result": args["text"].upper()})
broker.subscribe(node_a.receive)
broker.subscribe(node_b.receive)

registry_state = SQLiteState(":memory:")
registry = CapabilityRegistry(registry_state)
registry.advertise(CapabilityAdvertisement("node-a", "math.scale", metadata={"region": "local"}))
registry.advertise(CapabilityAdvertisement("node-b", "text.upper", metadata={"region": "local"}))

swarm = SwarmPlanner(registry).assemble("demo-swarm", {"math.scale": 1, "text.upper": 1})
print("swarm", [(m.node_id, m.capability) for m in swarm.members])

graph = TaskGraph([
    GraphTask("scale", "math.scale", {"value": 9}),
    GraphTask("render", "text.upper", {"text": "distributed"}, ("scale",)),
])

sim = Simulator(lambda task: (len(registry.providers(task.capability)) > 0, "provider available"))
print("simulation", [(s.task_id, s.admitted) for s in sim.dry_run(graph)])

coordinator.emit("WAKE", {"reason": "v0.2 demo"})
coordinator.emit("TASK", {
    "task_id": "scale-1",
    "capability": "math.scale",
    "operation": "run",
    "args": {"value": 9},
})
coordinator.emit("TASK", {
    "task_id": "upper-1",
    "capability": "text.upper",
    "operation": "run",
    "args": {"text": "distributed"},
})

print("node-a epoch", node_a.last_epoch)
print("node-b epoch", node_b.last_epoch)
print("ledger-valid", coordinator.ledger.verify())
print("quorum", QuorumRule(2, 3).decide({"a": True, "b": True, "c": False}))

journal = OfflineJournal("node-a", node_state_a)
journal.append({"kind": "observation", "value": 42})
sent = []
print("reconciled", journal.reconcile(lambda event: sent.append(event) is None or True))
print("offline-events", sent)
