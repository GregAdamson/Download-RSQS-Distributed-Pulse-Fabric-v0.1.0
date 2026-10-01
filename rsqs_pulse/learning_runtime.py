from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict

from .causal import CausalMemory, CausalAssessment
from .experiments import DeterministicExperimentLoop, Experiment, ExperimentResult
from .persistent import SQLiteState
from .provenance import ProvenanceLedger
from .state_reasoning import State
from .world_models import CompetingWorldModels, WorldModel


@dataclass(frozen=True)
class LearningResult:
    experiment: ExperimentResult
    causal: CausalAssessment
    best_model: str | None


class LearningRuntime:
    def __init__(self, state_path: str) -> None:
        self.state = SQLiteState(state_path)
        self.causal = CausalMemory(self.state.conn)
        self.ledger = ProvenanceLedger(self.state.conn)
        self.models = CompetingWorldModels()
        self.loop = DeterministicExperimentLoop(self.models)

    def register_model(self, model: WorldModel) -> None:
        self.models.register(model)

    def experiment(
        self,
        experiment_id: str,
        cause: str,
        action: str,
        args: Dict[str, Any],
        before: State,
        execute: Callable[[str, Dict[str, Any]], State],
        source: str,
    ) -> LearningResult:
        result = self.loop.run(Experiment(experiment_id, action, args), before, execute)
        best = self.models.best()
        observed_change = result.after.values != before.values
        self.causal.observe(
            cause, action, before.values, result.after.values, source,
            context={"experiment_id": experiment_id, "args": args},
            supports=observed_change,
            confidence=1.0,
        )
        assessment = self.causal.assess(cause, action)
        self.ledger.append(
            "experiment",
            experiment_id,
            {
                "cause": cause,
                "action": action,
                "before": before.values,
                "after": result.after.values,
                "models": [
                    {"model_id": item.model_id, "error": item.error, "score": item.score}
                    for item in result.evaluations
                ],
                "best_model": best.model_id if best else None,
            },
        )
        return LearningResult(result, assessment, best.model_id if best else None)

    def close(self) -> None:
        self.state.conn.close()
