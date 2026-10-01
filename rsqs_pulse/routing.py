from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, List
from .capabilities import CapabilityAdvertisement
from .resources import ResourceProfile


@dataclass(frozen=True)
class RouteDecision:
    node_id: str
    capability: str
    score: float


class ResourceAwareRouter:
    def choose(
        self,
        providers: Iterable[CapabilityAdvertisement],
        resources: Dict[str, ResourceProfile],
        limit: int = 1,
    ) -> List[RouteDecision]:
        choices: List[RouteDecision] = []
        for provider in providers:
            profile = resources.get(provider.node_id)
            if profile is None or not profile.healthy:
                continue
            choices.append(RouteDecision(provider.node_id, provider.name, profile.score()))
        choices.sort(key=lambda x: (-x.score, x.node_id))
        return choices[:limit]
