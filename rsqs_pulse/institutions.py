from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, Tuple
from .capabilities import CapabilityRegistry


@dataclass(frozen=True)
class RoleRequirement:
    role: str
    capability: str
    count: int = 1


@dataclass(frozen=True)
class InstitutionMember:
    role: str
    node_id: str
    capability: str


@dataclass(frozen=True)
class TemporaryInstitution:
    institution_id: str
    objective: str
    members: Tuple[InstitutionMember, ...]
    authority: Dict[str, str]
    persistent: bool = False


class InstitutionAssembler:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def assemble(
        self,
        institution_id: str,
        objective: str,
        requirements: Iterable[RoleRequirement],
        authority: Dict[str, str],
    ) -> TemporaryInstitution:
        members = []
        used = set()
        for requirement in requirements:
            providers = [p for p in self.registry.choose(requirement.capability) if p.node_id not in used]
            if len(providers) < requirement.count:
                raise RuntimeError(f"insufficient providers for role {requirement.role}")
            for provider in providers[:requirement.count]:
                used.add(provider.node_id)
                members.append(InstitutionMember(requirement.role, provider.node_id, requirement.capability))
        return TemporaryInstitution(institution_id, objective, tuple(members), dict(authority))
