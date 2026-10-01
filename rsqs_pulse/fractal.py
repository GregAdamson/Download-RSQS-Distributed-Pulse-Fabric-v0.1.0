from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class FabricDescriptor:
    fabric_id: str
    level: str
    capabilities: Tuple[str, ...]
    authority_scope: Tuple[str, ...]
    children: Tuple[str, ...] = ()


class FabricRegistry:
    def __init__(self) -> None:
        self._fabrics: Dict[str, FabricDescriptor] = {}

    def register(self, descriptor: FabricDescriptor) -> None:
        if descriptor.fabric_id in descriptor.children:
            raise ValueError("fabric cannot contain itself")
        self._fabrics[descriptor.fabric_id] = descriptor

    def get(self, fabric_id: str) -> FabricDescriptor:
        return self._fabrics[fabric_id]

    def providers(self, capability: str) -> list[FabricDescriptor]:
        return sorted(
            [f for f in self._fabrics.values() if capability in f.capabilities],
            key=lambda f: (f.level, f.fabric_id),
        )
