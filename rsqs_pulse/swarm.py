from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
from .capabilities import CapabilityRegistry


@dataclass(frozen=True)
class SwarmMember:
    node_id: str
    capability: str


@dataclass(frozen=True)
class Swarm:
    swarm_id: str
    members: tuple[SwarmMember, ...]


class SwarmPlanner:
    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def assemble(self, swarm_id: str, requirements: Dict[str, int]) -> Swarm:
        members: List[SwarmMember] = []
        for capability, count in sorted(requirements.items()):
            providers = self.registry.choose(capability)
            if len(providers) < count:
                raise RuntimeError(f"insufficient providers for {capability}")
            members.extend(SwarmMember(ad.node_id, capability) for ad in providers[:count])
        return Swarm(swarm_id, tuple(members))
