#!/usr/bin/env python3
import os
import tempfile

from rsqs_pulse.cognitive_loop import Observation
from rsqs_pulse.durable_transport import DurablePulseEventStore
from rsqs_pulse.model import Pulse
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.runtime import FabricRuntime, RuntimeTransition
from rsqs_pulse.state_reasoning import State, Transition

with tempfile.TemporaryDirectory() as d:
    events = os.path.join(d, "events.db")
    pulse = Pulse.new("proof", 1, "WAKE", {"proof": True})
    store = DurablePulseEventStore(events)
    assert store.append(pulse) == store.append(pulse)
    store.close()
    store = DurablePulseEventStore(events)
    _, restored = store.after(0)
    assert len(restored) == 1
    store.close()

    runtime = FabricRuntime("proof-node", os.path.join(d, "runtime.db"), LocalPolicy(allowed_capabilities={"measure"}))
    runtime.register_capability("measure", lambda args: {"measured": 7})
    speculative = Transition("measure", "measure", lambda state: State({"value": 1000}))
    result = runtime.run_cycle(
        [Observation("sensor", {"value": 0})],
        lambda state: state.values["value"] == 7,
        [RuntimeTransition(speculative, {}, reduce=lambda state, output: State({"value": output["measured"]}))],
    )
    assert result.status == "achieved"
    assert runtime.current_state().values["value"] == 7
    runtime.close()
    print("HARDENING_PROOF=PASS")
