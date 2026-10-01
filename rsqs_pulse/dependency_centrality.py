from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .dependency_graph import DependencyGraph


@dataclass(frozen=True)
class DependencyFinding:
    node: str
    dependent_capabilities: tuple[str, ...]
    dependency_count: int
    substitution_score: float
    criticality_score: float


class DependencyCentralityAnalyzer:
    def analyze(self, graph: DependencyGraph) -> tuple[DependencyFinding, ...]:
        findings = []
        capabilities = set(graph.resource_requirements.keys()) | set(graph.capability_requirements.keys())
        for node in sorted(capabilities):
            dependents = []
            for capability, requirements in graph.capability_requirements.items():
                if any(req.capability == node for req in requirements):
                    dependents.append(capability)
            resource_dependents = []
            for capability, requirements in graph.resource_requirements.items():
                if any(req.resource == node for req in requirements):
                    resource_dependents.append(capability)
            all_dependents = tuple(sorted(set(dependents + resource_dependents)))
            count = len(all_dependents)
            substitution_score = 1.0 if count == 0 else 1.0 / count
            criticality = float(count) + substitution_score
            findings.append(DependencyFinding(node, all_dependents, count, substitution_score, criticality))
        return tuple(sorted(findings, key=lambda item: (-item.criticality_score, item.node)))
