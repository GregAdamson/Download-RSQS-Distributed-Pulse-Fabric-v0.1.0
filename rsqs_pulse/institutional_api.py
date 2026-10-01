from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict


@dataclass(frozen=True)
class InstitutionalCapability:
    name: str
    description: str
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    read_only: bool = True


class InstitutionalGateway:
    def __init__(self) -> None:
        self._capabilities: Dict[str, InstitutionalCapability] = {}

    def expose(self, capability: InstitutionalCapability) -> None:
        self._capabilities[capability.name] = capability

    def describe(self) -> list[dict]:
        return [
            {"name": c.name, "description": c.description, "read_only": c.read_only}
            for c in sorted(self._capabilities.values(), key=lambda c: c.name)
        ]

    def invoke(self, name: str, args: Dict[str, Any], allow_write: bool = False) -> Dict[str, Any]:
        capability = self._capabilities[name]
        if not capability.read_only and not allow_write:
            raise PermissionError("write capability requires explicit local authority")
        return capability.handler(args)
