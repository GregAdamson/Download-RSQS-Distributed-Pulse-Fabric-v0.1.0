from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List

from .state_reasoning import State
from .world_models import CompetingWorldModels, ModelEvaluation


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    action: str
    args: Dict[str, Any]


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    before: State
    after: State
    evaluations: tuple[ModelEvaluation, ...]


class DeterministicExperimentLoop:
    def __init__(self, models: CompetingWorldModels) -> None:
        self.models = models

    def run(
        self,
        experiment: Experiment,
        before: State,
        execute: Callable[[str, Dict[str, Any]], State],
    ) -> ExperimentResult:
        after = execute(experiment.action, dict(experiment.args))
        evaluations = tuple(self.models.evaluate(before, experiment.action, experiment.args, after))
        return ExperimentResult(experiment.experiment_id, before, after, evaluations)
