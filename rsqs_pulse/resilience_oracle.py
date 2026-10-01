from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .dependency_centrality import DependencyCentralityAnalyzer, DependencyFinding
from .dependency_graph import DependencyGraph
from .monte_carlo_resilience import MonteCarloResilienceEngine, ScenarioOutcome
from .substitution import SubstitutionGraph
from .temporal_allocation import TemporalAllocationPlan


@dataclass(frozen=True)
class ResilienceOracleReport:
    viable: bool
    survival_rate: float
    average_score: float
    mean_failure_period: float | None
    first_failure_period: int | None
    critical_nodes: tuple[DependencyFinding, ...]
    evidence: dict[str, object]


class ResilienceOracle:
    def __init__(
        self,
        centrality: DependencyCentralityAnalyzer | None = None,
        monte_carlo: MonteCarloResilienceEngine | None = None,
    ) -> None:
        self.centrality = centrality or DependencyCentralityAnalyzer()
        self.monte_carlo = monte_carlo or MonteCarloResilienceEngine()

    def assess(
        self,
        graph: DependencyGraph,
        temporal_plan: TemporalAllocationPlan,
        outcomes: Iterable[ScenarioOutcome],
        *,
        substitutions: SubstitutionGraph | None = None,
        top_n: int = 5,
    ) -> ResilienceOracleReport:
        if top_n < 0:
            raise ValueError("top_n must be non-negative")
        outcome_tuple = tuple(outcomes)
        summary = self.monte_carlo.summary(outcome_tuple)
        findings = self.centrality.analyze(graph, substitutions)
        critical = findings[:top_n]
        return ResilienceOracleReport(
            viable=temporal_plan.viable,
            survival_rate=float(summary["survival_rate"]),
            average_score=float(summary["average_score"]),
            mean_failure_period=summary["mean_failure_period"],
            first_failure_period=temporal_plan.first_failure_period,
            critical_nodes=critical,
            evidence={
                "scenario_count": len(outcome_tuple),
                "failed_demands": temporal_plan.failed_demands,
                "period_count": len(temporal_plan.periods),
                "critical_node_count": len(findings),
            },
        )
