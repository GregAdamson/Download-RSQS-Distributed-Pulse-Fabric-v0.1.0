#!/usr/bin/env python3
from rsqs_pulse.reconciliation import OperationState, OperationStatus, Reconciler

class Device:
    def __init__(self):
        self.applied = {}
        self.calls = 0
    def execute(self, operation_id, args):
        self.calls += 1
        self.applied[operation_id] = args["value"]
        return {"value": args["value"]}
    def status(self, operation_id):
        if operation_id in self.applied:
            return OperationStatus(operation_id, OperationState.COMPLETE, {"value": self.applied[operation_id]}, {"device_receipt": operation_id})
        return OperationStatus(operation_id, OperationState.NOT_APPLIED, {}, {"device_receipt": "absent"})

device = Device()
reconciler = Reconciler()
op = "physical-proof-1"
before = reconciler.inspect(device, op)
assert before.action == "retry_eligible"
device.execute(op, {"value": 7})
after = reconciler.inspect(device, op)
assert after.action == "commit"
assert after.status.output["value"] == 7
unknown = OperationStatus("uncertain", OperationState.UNKNOWN, {}, {"device": "unreachable"})
device.status = lambda operation_id: unknown
assert reconciler.inspect(device, "uncertain").action == "escalate"
print("PHYSICAL_RECONCILIATION_PROOF=PASS")
