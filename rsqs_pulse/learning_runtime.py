from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict

from .causal import CausalMemory, CausalAssessment
from .experiments import DeterministicExperimentLoop, Experiment, ExperimentResult
from .model_store import WorldModelStore
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
        self.model_store = WorldModelStore(self.state.conn)
        self.models = CompetingWorldModels()
        self.loop = DeterministicExperimentLoop(self.models)

    def register_model(self, model: WorldModel) -> None:
        self.models.register(self.model_store.restore(model))

    def experiment(
        self,
        experiment_id: str,
        cause: str,
        action: str,
        args: Dict[str, Any],
        before: State,
        execute: Callable[[str, Dict[str, Any]], State],
        source: str,
        outcome_test: Callable[[State, State], bool],
        confidence: float = 1.0,
    ) -> LearningResult:
        result = self.loop.run(Experiment(experiment_id, action, args), before, execute)
        for model in self.models.models.values():
            self.model_store.save(model)
        best = self.models.best()
        supports = bool(outcome_test(before, result.after))
        self.causal.observe(
            cause, action, before.values, result.after.values, source,
            context={"experiment_id": experiment_id, "args": args},
            supports=supports,
            confidence=confidence,
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
                "supports": supports,
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
