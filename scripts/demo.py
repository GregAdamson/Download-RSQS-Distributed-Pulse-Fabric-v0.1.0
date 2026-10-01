#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rsqs_pulse import Capability, Coordinator, InMemoryBroker, LocalPolicy, Node

SECRET = b"demo-only-secret"

broker = InMemoryBroker()
coordinator = Coordinator("rsqs-global", SECRET, broker)


def make_node(node_id: str, multiplier: int) -> Node:
    policy = LocalPolicy(allowed_capabilities={"math.scale"})
    node = Node(node_id, "rsqs-global", SECRET, policy)
    node.register(Capability("math.scale"), lambda args: {
        "input": args["value"],
        "multiplier": multiplier,
        "result": args["value"] * multiplier,
    })
    broker.subscribe(node.receive)
    return node


nodes = [make_node("node-a", 2), make_node("node-b", 3), make_node("node-c", 5)]

coordinator.emit("WAKE", {"reason": "demo"})
task = coordinator.dispatch_task("math.scale", "run", {"value": 7})

print("task", task.task_id)
for node in nodes:
    for result in node.results:
        print(result.node_id, result.status, result.output)
