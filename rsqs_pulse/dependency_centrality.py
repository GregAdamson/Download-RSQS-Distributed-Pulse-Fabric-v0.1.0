from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

from .dependency_graph import DependencyGraph
from .substitution import SubstitutionGraph


@dataclass(frozen=True)
class DependencyFinding:
    node: str
    dependent_capabilities: tuple[str, ...]
    dependency_count: int
    substitution_score: float
    criticality_score: float
    node_kind: str = "capability"
    direct_dependents: tuple[str, ...] = ()


class DependencyCentralityAnalyzer:
    def analyze(
        self,
        graph: DependencyGraph,
        substitutions: SubstitutionGraph | None = None,
    ) -> tuple[DependencyFinding, ...]:
        substitutions = substitutions or SubstitutionGraph()
        capabilities = set(graph.capabilities())
        resources = {
            req.resource
            for requirements in graph.resource_requirements.values()
            for req in requirements
            if req.critical
        }

        direct_capability_dependents: Dict[str, set[str]] = {
            node: set() for node in capabilities
        }
        for capability, requirements in graph.capability_requirements.items():
            for requirement in requirements:
                if requirement.critical:
                    direct_capability_dependents.setdefault(
                        requirement.capability, set()
                    ).add(capability)

        def downstream_capabilities(seed: Iterable[str]) -> set[str]:
            discovered = set(seed)
            frontier = list(seed)
            while frontier:
                current = frontier.pop()
                for dependent in direct_capability_dependents.get(current, set()):
                    if dependent not in discovered:
                        discovered.add(dependent)
                        frontier.append(dependent)
            return discovered

        findings = []

        for resource in sorted(resources):
            direct = {
                capability
                for capability, requirements in graph.resource_requirements.items()
                if any(req.critical and req.resource == resource for req in requirements)
            }
            downstream = downstream_capabilities(direct)
            alternatives = substitutions.alternatives(resource)
            substitution_score = 1.0 / (1.0 + len(alternatives))
            dependency_count = len(downstream)
            criticality = float(dependency_count) + substitution_score
            findings.append(
                DependencyFinding(
                    node=resource,
                    dependent_capabilities=tuple(sorted(downstream)),
                    dependency_count=dependency_count,
                    substitution_score=substitution_score,
                    criticality_score=criticality,
                    node_kind="resource",
                    direct_dependents=tuple(sorted(direct)),
                )
            )

        for capability in sorted(capabilities):
            direct = direct_capability_dependents.get(capability, set())
            downstream = downstream_capabilities(direct)
            dependency_count = len(downstream)
            substitution_score = 1.0
            criticality = float(dependency_count) + substitution_score
            findings.append(
                DependencyFinding(
                    node=capability,
                    dependent_capabilities=tuple(sorted(downstream)),
                    dependency_count=dependency_count,
                    substitution_score=substitution_score,
                    criticality_score=criticality,
                    node_kind="capability",
                    direct_dependents=tuple(sorted(direct)),
                )
            )

        return tuple(
            sorted(
                findings,
                key=lambda item: (
                    -item.criticality_score,
                    item.node_kind,
                    item.node,
                ),
            )
        )
