from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List

from .state_reasoning import State


@dataclass
class WorldModel:
    model_id: str
    predict: Callable[[State, str, Dict[str, Any]], State]
    evidence: float = 1.0
    error_total: float = 0.0
    observations: int = 0

    @property
    def mean_error(self) -> float:
        return self.error_total / self.observations if self.observations else float("inf")

    @property
    def score(self) -> float:
        if not self.observations:
            return self.evidence
        return self.evidence / (1.0 + self.mean_error)


@dataclass(frozen=True)
class ModelEvaluation:
    model_id: str
    error: float
    score: float


class CompetingWorldModels:
    def __init__(self) -> None:
        self.models: Dict[str, WorldModel] = {}

    def register(self, model: WorldModel) -> None:
        self.models[model.model_id] = model

    @staticmethod
    def state_error(predicted: State, observed: State) -> float:
        keys = sorted(set(predicted.values) | set(observed.values))
        if not keys:
            return 0.0
        errors = []
        for key in keys:
            p = predicted.values.get(key)
            o = observed.values.get(key)
            if isinstance(p, (int, float)) and isinstance(o, (int, float)):
                errors.append(abs(float(p) - float(o)))
            else:
                errors.append(0.0 if p == o else 1.0)
        return sum(errors) / len(errors)

    def evaluate(self, before: State, action: str, args: Dict[str, Any], observed: State) -> List[ModelEvaluation]:
        results = []
        for model in self.models.values():
            predicted = model.predict(before, action, args)
            error = self.state_error(predicted, observed)
            model.observations += 1
            model.error_total += error
            model.evidence = max(0.000001, model.evidence * (1.0 / (1.0 + error)))
            results.append(ModelEvaluation(model.model_id, error, model.score))
        return sorted(results, key=lambda item: (-item.score, item.error, item.model_id))

    def best(self) -> WorldModel | None:
        if not self.models:
            return None
        return sorted(self.models.values(), key=lambda m: (-m.score, m.model_id))[0]
