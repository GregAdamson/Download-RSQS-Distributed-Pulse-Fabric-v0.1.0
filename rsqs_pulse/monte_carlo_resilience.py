from __future__ import annotations

from dataclasses import dataclass
import random
from statistics import mean
from typing import Callable, Iterable


@dataclass(frozen=True)
class ShockScenario:
    resource: str
    reduction: float
    duration: int


@dataclass(frozen=True)
class ScenarioOutcome:
    survived: bool
    failure_period: int | None
    score: float


class MonteCarloResilienceEngine:
    def __init__(self, seed: int = 0) -> None:
        self.seed = int(seed)
        self.random = random.Random(self.seed)

    def reset(self) -> None:
        self.random = random.Random(self.seed)

    def generate(
        self,
        resources: Iterable[str],
        count: int,
    ) -> tuple[ShockScenario, ...]:
        resources = tuple(sorted(set(resources)))
        if count < 0:
            raise ValueError("count must be non-negative")
        if count and not resources:
            raise ValueError("at least one resource is required")
        return tuple(
            ShockScenario(
                self.random.choice(resources),
                self.random.choice((0.1, 0.25, 0.5, 0.75, 1.0)),
                self.random.randint(1, 12),
            )
            for _ in range(count)
        )

    def evaluate(
        self,
        scenarios: Iterable[ShockScenario],
        simulator: Callable[[ShockScenario], ScenarioOutcome],
    ) -> tuple[ScenarioOutcome, ...]:
        return tuple(simulator(scenario) for scenario in scenarios)

    def summary(self, outcomes: Iterable[ScenarioOutcome]) -> dict[str, float | None]:
        values = tuple(outcomes)
        if not values:
            return {
                "survival_rate": 0.0,
                "average_score": 0.0,
                "mean_failure_period": None,
            }
        failure_periods = [
            value.failure_period
            for value in values
            if value.failure_period is not None
        ]
        return {
            "survival_rate": sum(1 for value in values if value.survived) / len(values),
            "average_score": sum(value.score for value in values) / len(values),
            "mean_failure_period": (
                None if not failure_periods else float(mean(failure_periods))
            ),
        }

    def run(
        self,
        resources: Iterable[str],
        count: int,
        simulator: Callable[[ShockScenario], ScenarioOutcome],
        *,
        reset: bool = True,
    ) -> tuple[tuple[ShockScenario, ...], tuple[ScenarioOutcome, ...], dict[str, float | None]]:
        if reset:
            self.reset()
        scenarios = self.generate(resources, count)
        outcomes = self.evaluate(scenarios, simulator)
        return scenarios, outcomes, self.summary(outcomes)
