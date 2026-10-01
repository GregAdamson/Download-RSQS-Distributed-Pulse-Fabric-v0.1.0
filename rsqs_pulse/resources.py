from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceProfile:
    node_id: str
    cpu_free: float
    memory_free_mb: int
    storage_free_mb: int
    latency_ms: float
    healthy: bool = True

    def score(self) -> float:
        if not self.healthy:
            return float("-inf")
        return (
            max(self.cpu_free, 0.0) * 100.0
            + max(self.memory_free_mb, 0) / 1024.0
            + max(self.storage_free_mb, 0) / 10240.0
            - max(self.latency_ms, 0.0) / 100.0
        )
