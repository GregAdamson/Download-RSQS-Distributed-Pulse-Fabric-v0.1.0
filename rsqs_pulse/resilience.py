from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .dependency_graph import DependencyGraph, ResourceRequirement
from .resource_state import ResourceInventory
from .substitution import SubstitutionGraph

@dataclass(frozen=True)
class ScarcityFinding:
    resource: str
    unit: str
    required: float
    available: float
    shortage: float
    shortage_ratio: float
    affected_capabilities: tuple[str, ...]

@dataclass(frozen=True)
class SubstitutionAllocation:
    original_resource: str
    substitute: str
    substitute_quantity: float
    ratio: float
    unit: str

@dataclass(frozen=True)
class ResiliencePlan:
    capability: str
    viable: bool
    allocations: tuple[SubstitutionAllocation, ...]
    unresolved: tuple[ResourceRequirement, ...]

class ScarcityAnalyzer:
    def analyze(self, graph: DependencyGraph, inventory: ResourceInventory) -> list[ScarcityFinding]:
        aggregate: Dict[tuple[str, str], float] = {}
        capability_map: Dict[tuple[str, str], set[str]] = {}
        quality_floor: Dict[tuple[str, str], float] = {}
        for capability, requirements in graph.resource_requirements.items():
            for req in requirements:
                if not req.critical:
                    continue
                key = (req.resource, req.unit)
                aggregate[key] = aggregate.get(key, 0.0) + req.quantity
                capability_map.setdefault(key, set()).add(capability)
                quality_floor[key] = max(quality_floor.get(key, 0.0), req.minimum_quality)
        findings = []
        for (resource, unit), required in sorted(aggregate.items()):
            available = inventory.available(resource, unit, minimum_quality=quality_floor[(resource, unit)])
            shortage = max(0.0, required - available)
            findings.append(
                ScarcityFinding(
                    resource, unit, required, available, shortage,
                    0.0 if required <= 0 else shortage / required,
                    tuple(sorted(capability_map[(resource, unit)])),
                )
            )
        return findings

class ResiliencePlanner:
    def __init__(self, substitutions: SubstitutionGraph) -> None:
        self.substitutions = substitutions

    def plan(self, capability: str, graph: DependencyGraph, inventory: ResourceInventory) -> ResiliencePlan:
        allocations: List[SubstitutionAllocation] = []
        unresolved: List[ResourceRequirement] = []
        for req in graph.resource_requirements.get(capability, []):
            available = inventory.available(
                req.resource, req.unit, location=req.location, minimum_quality=req.minimum_quality
            )
            deficit = max(0.0, req.quantity - available)
            if deficit <= 1e-12 or not req.critical:
                continue
            remaining = deficit
            for alt in self.substitutions.alternatives(req.resource):
                substitute_available = inventory.available(
                    alt.substitute, req.unit, location=req.location, minimum_quality=req.minimum_quality
                )
                if substitute_available <= 0:
                    continue
                substitute_needed = remaining * alt.ratio
                used = min(substitute_available, substitute_needed)
                restored_original = used / alt.ratio
                if used > 0:
                    allocations.append(
                        SubstitutionAllocation(req.resource, alt.substitute, used, alt.ratio, req.unit)
                    )
                    remaining = max(0.0, remaining - restored_original)
                if remaining <= 1e-12:
                    break
            if remaining > 1e-12:
                unresolved.append(
                    ResourceRequirement(
                        req.resource, remaining, req.unit, req.minimum_quality,
                        req.location, req.critical,
                    )
                )
        dependency_failures = [
            dep.capability
            for dep in graph.capability_requirements.get(capability, [])
            if dep.critical and not graph.evaluate(dep.capability, inventory).operational
        ]
        viable = not unresolved and not dependency_failures
        return ResiliencePlan(capability, viable, tuple(allocations), tuple(unresolved))
