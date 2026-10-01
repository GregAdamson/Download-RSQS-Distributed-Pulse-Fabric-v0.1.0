from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List
from .persistent import SQLiteState


@dataclass(frozen=True)
class CapabilityAdvertisement:
    node_id: str
    name: str
    version: str = "1"
    metadata: Dict[str, Any] = field(default_factory=dict)


class CapabilityRegistry:
    def __init__(self, state: SQLiteState) -> None:
        self.state = state

    def advertise(self, ad: CapabilityAdvertisement) -> None:
        self.state.upsert_capability(ad.node_id, ad.name, ad.version, ad.metadata, int(time.time()))

    def providers(self, capability: str) -> List[CapabilityAdvertisement]:
        rows = self.state.list_capabilities(capability)
        return [
            CapabilityAdvertisement(r["node_id"], r["name"], r["version"], r["metadata"])
            for r in rows
        ]

    def choose(self, capability: str, required: Dict[str, Any] | None = None) -> List[CapabilityAdvertisement]:
        required = required or {}
        result = []
        for ad in self.providers(capability):
            if all(ad.metadata.get(k) == v for k, v in required.items()):
                result.append(ad)
        return sorted(result, key=lambda x: x.node_id)
