from __future__ import annotations
from dataclasses import dataclass, field
from typing import Set


@dataclass
class LocalPolicy:
    allowed_pulse_kinds: Set[str] = field(default_factory=lambda: {
        "WAKE", "STATE_CHANGED", "AGENT_AVAILABLE", "CAPABILITY_AVAILABLE",
        "POLICY_CHANGED", "EMERGENCY", "TASK"
    })
    allowed_capabilities: Set[str] = field(default_factory=set)

    def permits_pulse(self, kind: str) -> bool:
        return kind in self.allowed_pulse_kinds

    def permits_capability(self, capability: str) -> bool:
        return capability in self.allowed_capabilities
