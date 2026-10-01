from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PhysicalObservation:
    """A provenance-controlled measurement of an external state."""

    observation_type: str
    asset_id: str
    timestamp: str
    value: Any
    unit: str
    confidence: float
    source: str
    provenance: dict[str, Any]

    @classmethod
    def create(
        cls,
        observation_type: str,
        asset_id: str,
        value: Any,
        unit: str,
        confidence: float,
        source: str,
        provenance: dict[str, Any] | None = None,
    ) -> "PhysicalObservation":
        return cls(
            observation_type=observation_type,
            asset_id=asset_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            value=value,
            unit=unit,
            confidence=max(0.0, min(1.0, confidence)),
            source=source,
            provenance=provenance or {},
        )


@dataclass(frozen=True)
class RealityVariance:
    asset_id: str
    expected: Any
    observed: Any
    variance: float
    confidence: float
    explanation: str


class RealityObservationRegistry:
    """Stores physical observations and reconciles expected vs observed state."""

    def __init__(self) -> None:
        self._observations: list[PhysicalObservation] = []

    def ingest(self, observation: PhysicalObservation) -> None:
        self._observations.append(observation)

    def observations(self) -> tuple[PhysicalObservation, ...]:
        return tuple(self._observations)

    def pulse(self, observation: PhysicalObservation) -> dict[str, Any]:
        return {
            "type": "physical_observation",
            "asset_id": observation.asset_id,
            "observation_type": observation.observation_type,
            "timestamp": observation.timestamp,
            "confidence": observation.confidence,
            "source": observation.source,
            "payload": asdict(observation),
        }

    def reconcile(
        self,
        expected: dict[str, Any],
        observed: PhysicalObservation,
    ) -> RealityVariance:
        target = expected.get(observed.asset_id)
        if target is None:
            return RealityVariance(
                observed.asset_id,
                None,
                observed.value,
                0.0,
                observed.confidence,
                "no expected state available",
            )
        variance = abs(float(observed.value) - float(target))
        return RealityVariance(
            observed.asset_id,
            target,
            observed.value,
            variance,
            observed.confidence,
            "measured difference between expected and observed state",
        )
