from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class ResourceOffer:
    provider: str
    resource: str
    quantity: float
    unit: str
    constraints: Dict[str, str]


@dataclass(frozen=True)
class ResourceNeed:
    consumer: str
    resource: str
    quantity: float
    unit: str
    constraints: Dict[str, str]


@dataclass(frozen=True)
class ResourceMatch:
    provider: str
    consumer: str
    resource: str
    quantity: float
    unit: str


class ResourceExchange:
    def match(self, offers: Iterable[ResourceOffer], needs: Iterable[ResourceNeed]) -> List[ResourceMatch]:
        remaining = {i: max(0.0, n.quantity) for i, n in enumerate(needs)}
        needs = list(needs)
        matches: List[ResourceMatch] = []
        for offer in sorted(offers, key=lambda x: (x.resource, x.provider)):
            available = max(0.0, offer.quantity)
            for i, need in enumerate(needs):
                if available <= 0:
                    break
                if need.resource != offer.resource or need.unit != offer.unit or remaining[i] <= 0:
                    continue
                if any(offer.constraints.get(k) != v for k, v in need.constraints.items()):
                    continue
                quantity = min(available, remaining[i])
                matches.append(ResourceMatch(offer.provider, need.consumer, offer.resource, quantity, offer.unit))
                available -= quantity
                remaining[i] -= quantity
        return matches
