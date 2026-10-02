from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .reality_observation import PhysicalObservation


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class SourcePolicy:
    reliability: float = 1.0
    independence_group: str | None = None
    half_life_seconds: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.reliability <= 1.0:
            raise ValueError("reliability must be in [0,1]")
        if self.half_life_seconds is not None and self.half_life_seconds <= 0:
            raise ValueError("half_life_seconds must be positive")


@dataclass(frozen=True)
class FusedObservation:
    observation_type: str
    asset_id: str
    timestamp: str
    value: Any
    unit: str
    confidence: float
    contributors: tuple[str, ...]
    contributor_count: int
    independent_source_count: int
    disagreement: float
    contradictory: bool
    provenance: tuple[dict[str, Any], ...]


class EvidenceFusionEngine:
    def __init__(
        self,
        source_policies: Mapping[str, SourcePolicy] | None = None,
        *,
        contradiction_threshold: float = 0.25,
    ) -> None:
        if contradiction_threshold < 0:
            raise ValueError("contradiction_threshold must be non-negative")
        self.source_policies = dict(source_policies or {})
        self.contradiction_threshold = float(contradiction_threshold)

    def _policy(self, source: str) -> SourcePolicy:
        return self.source_policies.get(source, SourcePolicy())

    def _weight(
        self,
        observation: PhysicalObservation,
        now: datetime,
    ) -> float:
        policy = self._policy(observation.source)
        weight = observation.confidence * policy.reliability
        if policy.half_life_seconds is not None:
            age = max(
                0.0,
                (now - _parse_time(observation.timestamp)).total_seconds(),
            )
            weight *= math.pow(0.5, age / policy.half_life_seconds)
        return max(0.0, weight)

    def fuse(
        self,
        observations: Iterable[PhysicalObservation],
        *,
        now: datetime | None = None,
    ) -> FusedObservation:
        items = tuple(observations)
        if not items:
            raise ValueError("at least one observation is required")
        first = items[0]
        for item in items[1:]:
            if (
                item.asset_id != first.asset_id
                or item.observation_type != first.observation_type
                or item.unit != first.unit
            ):
                raise ValueError(
                    "all fused observations must share asset, type and unit"
                )
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # Correlated sources share one group's evidence budget. This prevents
        # five derived feeds from the same upstream sensor counting as five
        # independent confirmations.
        grouped: dict[str, list[tuple[PhysicalObservation, float]]] = {}
        for item in items:
            policy = self._policy(item.source)
            group = policy.independence_group or f"source:{item.source}"
            grouped.setdefault(group, []).append((item, self._weight(item, now)))

        effective: list[tuple[PhysicalObservation, float]] = []
        for group_items in grouped.values():
            total = sum(weight for _, weight in group_items)
            if total <= 0:
                continue
            group_budget = max(weight for _, weight in group_items)
            for item, weight in group_items:
                effective.append((item, group_budget * weight / total))

        total_weight = sum(weight for _, weight in effective)
        if total_weight <= 0:
            raise ValueError("all evidence weights decayed to zero")

        numeric = all(
            isinstance(item.value, (int, float)) and not isinstance(item.value, bool)
            for item, _ in effective
        )
        if numeric:
            value = sum(float(item.value) * weight for item, weight in effective) / total_weight
            variance = sum(
                weight * (float(item.value) - value) ** 2
                for item, weight in effective
            ) / total_weight
            scale = max(abs(value), 1.0)
            disagreement = math.sqrt(variance) / scale
        else:
            votes: dict[str, float] = {}
            original: dict[str, Any] = {}
            for item, weight in effective:
                key = repr(item.value)
                votes[key] = votes.get(key, 0.0) + weight
                original[key] = item.value
            winner = sorted(votes, key=lambda key: (-votes[key], key))[0]
            value = original[winner]
            winner_weight = votes[winner]
            disagreement = 1.0 - winner_weight / total_weight

        independent_sources = len(grouped)
        diversity_factor = 1.0 - math.exp(-independent_sources)
        mean_quality = min(1.0, total_weight / max(1, independent_sources))
        confidence = max(
            0.0,
            min(
                1.0,
                mean_quality
                * (0.5 + 0.5 * diversity_factor)
                * max(0.0, 1.0 - disagreement),
            ),
        )
        latest = max(_parse_time(item.timestamp) for item in items)
        return FusedObservation(
            observation_type=first.observation_type,
            asset_id=first.asset_id,
            timestamp=latest.isoformat(),
            value=value,
            unit=first.unit,
            confidence=confidence,
            contributors=tuple(sorted({item.source for item in items})),
            contributor_count=len(items),
            independent_source_count=independent_sources,
            disagreement=float(disagreement),
            contradictory=disagreement > self.contradiction_threshold,
            provenance=tuple(item.provenance for item in items),
        )
