from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ResilienceWeights:
    capability_retention: float = 5.0
    reserve_margin: float = 3.0
    recovery_speed: float = 2.0
    substitution_depth: float = 1.0
    supply_diversity: float = 1.0
    resource_consumption: float = -2.0
    dependency_risk: float = -5.0
    irreversible_actions: float = -3.0


@dataclass(frozen=True)
class ResilienceMetrics:
    capability_retention: float = 0.0
    reserve_margin: float = 0.0
    recovery_speed: float = 0.0
    substitution_depth: float = 0.0
    supply_diversity: float = 0.0
    resource_consumption: float = 0.0
    dependency_risk: float = 0.0
    irreversible_actions: float = 0.0


@dataclass
class ResilienceObjective:
    weights: ResilienceWeights = field(default_factory=ResilienceWeights)

    def score(self, metrics: ResilienceMetrics | Mapping[str, float]) -> float:
        if isinstance(metrics, Mapping):
            metrics = ResilienceMetrics(**metrics)
        return (
            self.weights.capability_retention * metrics.capability_retention
            + self.weights.reserve_margin * metrics.reserve_margin
            + self.weights.recovery_speed * metrics.recovery_speed
            + self.weights.substitution_depth * metrics.substitution_depth
            + self.weights.supply_diversity * metrics.supply_diversity
            + self.weights.resource_consumption * metrics.resource_consumption
            + self.weights.dependency_risk * metrics.dependency_risk
            + self.weights.irreversible_actions * metrics.irreversible_actions
        )
