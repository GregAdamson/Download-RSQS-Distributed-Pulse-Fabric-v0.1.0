#!/usr/bin/env python3
import os
import tempfile
from rsqs_pulse.learning_runtime import LearningRuntime
from rsqs_pulse.state_reasoning import State
from rsqs_pulse.world_models import WorldModel

with tempfile.TemporaryDirectory() as directory:
    runtime = LearningRuntime(os.path.join(directory, "learning.db"))
    runtime.register_model(WorldModel("linear-plus-delta", lambda state, action, args: State({"level": state.values["level"] + args["delta"]})))
    runtime.register_model(WorldModel("no-effect", lambda state, action, args: State({"level": state.values["level"]})))
    state = State({"level": 10})
    for index in range(3):
        result = runtime.experiment(
            f"exp-{index}", "control-input", "raise-level", {"delta": 2}, state,
            lambda action, args: State({"level": state.values["level"] + args["delta"]}),
            "controlled-demo",
            lambda before, after: after.values["level"] > before.values["level"],
        )
        state = result.experiment.after
    assert result.best_model == "linear-plus-delta"
    assert result.causal.observations == 3
    assert runtime.ledger.verify()
    print("COGNITIVE_SUBSTRATE_PROOF=PASS")
    runtime.close()
