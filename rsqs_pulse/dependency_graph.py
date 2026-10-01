from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple

from .resource_state import ResourceInventory

@dataclass(frozen=True)
class ResourceRequirement:
    resource: str
    quantity: float
    unit: str
    minimum_quality: float = 0.0
    location: str | None = None
    critical: bool = True

@dataclass(frozen=True)
class CapabilityRequirement:
    capability: str
    critical: bool = True

@dataclass(frozen=True)
class CapabilityStatus:
    capability: str
    operational: bool
    missing_resources: tuple[ResourceRequirement, ...]
    failed_dependencies: tuple[str, ...]

class DependencyGraph:
    def __init__(self) -> None:
        self.resource_requirements: Dict[str, List[ResourceRequirement]] = {}
        self.capability_requirements: Dict[str, List[CapabilityRequirement]] = {}

    def require_resource(self, capability: str, requirement: ResourceRequirement) -> None:
        if requirement.quantity < 0:
            raise ValueError("required quantity must be non-negative")
        self.resource_requirements.setdefault(capability, []).append(requirement)

    def require_capability(self, capability: str, dependency: CapabilityRequirement) -> None:
        self.capability_requirements.setdefault(capability, []).append(dependency)
        self._assert_acyclic()

    def capabilities(self) -> list[str]:
        return sorted(set(self.resource_requirements) | set(self.capability_requirements) | {
            dep.capability for deps in self.capability_requirements.values() for dep in deps
        })

    def _assert_acyclic(self) -> None:
        visiting: Set[str] = set()
        visited: Set[str] = set()
        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError(f"capability dependency cycle detected at {node}")
            if node in visited:
                return
            visiting.add(node)
            for dep in self.capability_requirements.get(node, []):
                visit(dep.capability)
            visiting.remove(node)
            visited.add(node)
        for node in self.capabilities():
            visit(node)

    def evaluate(self, capability: str, inventory: ResourceInventory) -> CapabilityStatus:
        memo: Dict[str, CapabilityStatus] = {}
        def resolve(name: str) -> CapabilityStatus:
            if name in memo:
                return memo[name]
            missing = []
            for req in self.resource_requirements.get(name, []):
                available = inventory.available(
                    req.resource, req.unit, location=req.location, minimum_quality=req.minimum_quality
                )
                if available + 1e-12 < req.quantity and req.critical:
                    missing.append(req)
            failed = []
            for dep in self.capability_requirements.get(name, []):
                status = resolve(dep.capability)
                if not status.operational and dep.critical:
                    failed.append(dep.capability)
            result = CapabilityStatus(name, not missing and not failed, tuple(missing), tuple(sorted(failed)))
            memo[name] = result
            return result
        return resolve(capability)

    def impact_of_resource_loss(self, resource: str, inventory: ResourceInventory) -> list[str]:
        affected = []
        for capability in self.capabilities():
            direct = any(req.resource == resource for req in self.resource_requirements.get(capability, []))
            if direct and not self.evaluate(capability, inventory).operational:
                affected.append(capability)
        changed = True
        while changed:
            changed = False
            for capability in self.capabilities():
                if capability in affected:
                    continue
                deps = {dep.capability for dep in self.capability_requirements.get(capability, []) if dep.critical}
                if deps.intersection(affected):
                    affected.append(capability)
                    changed = True
        return sorted(affected)
