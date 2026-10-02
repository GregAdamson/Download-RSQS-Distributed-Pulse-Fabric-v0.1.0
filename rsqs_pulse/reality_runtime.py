from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .cognitive_loop import Observation
from .digital_twin import DigitalTwinStore
from .evidence_fusion import EvidenceFusionEngine, FusedObservation
from .information_requirements import (
    InformationNeed,
    InformationRequirementEngine,
    InformationRequirementSpec,
)
from .reality_observation import PhysicalObservation, RealityVariance
from .reality_store import RealityStore
from .observation_acquisition import AcquisitionExecutor, AcquisitionPlanner, ObservationSource


@dataclass(frozen=True)
class RealityProcessingResult:
    raw_count: int
    fused: tuple[FusedObservation, ...]
    pulses: tuple[dict[str, Any], ...]
    information_needs: tuple[InformationNeed, ...]


class RealityEngine:
    def __init__(
        self,
        runtime,
        *,
        fusion: EvidenceFusionEngine | None = None,
    ) -> None:
        self.runtime = runtime
        self.store = RealityStore(runtime.state.conn)
        self.twin = DigitalTwinStore(runtime.state.conn)
        self.information = InformationRequirementEngine(runtime.state.conn)
        self.fusion = fusion or EvidenceFusionEngine()

    @staticmethod
    def state_key(asset_id: str, observation_type: str) -> str:
        return f"physical.{asset_id}.{observation_type}"

    def ingest_adapter(
        self,
        adapter,
        *,
        requirements: Mapping[str, Iterable[InformationRequirementSpec]] | None = None,
    ) -> RealityProcessingResult:
        return self.ingest(
            adapter.fetch(),
            requirements=requirements,
        )

    def ingest(
        self,
        observations: Iterable[PhysicalObservation],
        *,
        requirements: Mapping[str, Iterable[InformationRequirementSpec]] | None = None,
    ) -> RealityProcessingResult:
        items = tuple(observations)
        grouped: dict[tuple[str, str, str], list[PhysicalObservation]] = {}
        for item in items:
            self.store.record_observation(item)
            grouped.setdefault(
                (item.asset_id, item.observation_type, item.unit),
                [],
            ).append(item)

        fused_items = []
        pulses = []
        for (asset_id, observation_type, unit), evidence in sorted(grouped.items()):
            fused = self.fusion.fuse(evidence)
            fused_id = self.store.record_fused(fused)
            self.twin.apply_fused(fused, source_ref=f"fused:{fused_id}")
            state_key = self.state_key(asset_id, observation_type)
            self.runtime.observe([
                Observation(
                    "reality:fused",
                    {
                        state_key: fused.value,
                        f"{state_key}:confidence": fused.confidence,
                        f"{state_key}:unit": unit,
                        f"{state_key}:contradictory": fused.contradictory,
                    },
                )
            ])
            pulse = {
                "type": "physical_observation",
                "asset_id": asset_id,
                "observation_type": observation_type,
                "timestamp": fused.timestamp,
                "confidence": fused.confidence,
                "contradictory": fused.contradictory,
                "fused_id": fused_id,
                "payload": {
                    "value": fused.value,
                    "unit": fused.unit,
                    "contributors": list(fused.contributors),
                    "independent_source_count": fused.independent_source_count,
                    "disagreement": fused.disagreement,
                },
            }
            self.runtime.ledger.append(
                "reality_fused",
                fused_id,
                pulse,
            )
            fused_items.append(fused)
            pulses.append(pulse)

        needs = []
        for asset_id, specs in sorted((requirements or {}).items()):
            needs.extend(
                self.information.evaluate(
                    asset_id,
                    specs,
                    self.twin,
                    self.store,
                )
            )
        for need in needs:
            self.runtime.ledger.append(
                "information_need",
                need.need_id,
                {
                    "asset_id": need.asset_id,
                    "observation_type": need.observation_type,
                    "reason": need.reason,
                    "priority": need.priority,
                },
            )

        return RealityProcessingResult(
            raw_count=len(items),
            fused=tuple(fused_items),
            pulses=tuple(pulses),
            information_needs=tuple(needs),
        )

    def reconcile_expected(
        self,
        expected: Mapping[str, Any],
        fused: FusedObservation,
    ) -> RealityVariance:
        key = self.state_key(fused.asset_id, fused.observation_type)
        target = expected.get(key)
        if target is None:
            variance = RealityVariance(
                fused.asset_id,
                None,
                fused.value,
                0.0,
                fused.confidence,
                f"no expected state available for {key}",
            )
        else:
            try:
                delta = abs(float(fused.value) - float(target))
            except (TypeError, ValueError):
                delta = 0.0 if fused.value == target else 1.0
            variance = RealityVariance(
                fused.asset_id,
                target,
                fused.value,
                float(delta),
                fused.confidence,
                f"expected vs fused observed state for {key}",
            )
        variance_id = self.store.record_variance(variance)
        self.runtime.ledger.append(
            "reality_variance",
            variance_id,
            {
                "asset_id": fused.asset_id,
                "observation_type": fused.observation_type,
                "expected": target,
                "observed": fused.value,
                "variance": variance.variance,
                "confidence": variance.confidence,
            },
        )
        return variance

    def acquire_and_ingest(
        self,
        sources: Iterable[ObservationSource],
        *,
        planner: AcquisitionPlanner | None = None,
        requirements: Mapping[str, Iterable[InformationRequirementSpec]] | None = None,
    ) -> tuple[RealityProcessingResult, tuple[Any, ...]]:
        needs = self.information.open_needs()
        planner = planner or AcquisitionPlanner()
        tasks = planner.plan(needs, sources)
        results = AcquisitionExecutor().execute(tasks, sources)
        observations = tuple(
            observation
            for result in results
            if result.status == "ok"
            for observation in result.observations
        )
        processed = self.ingest(
            observations,
            requirements=requirements,
        )
        for result in results:
            self.runtime.ledger.append(
                "acquisition_result",
                result.task.need_id,
                {
                    "source_id": result.task.source_id,
                    "asset_id": result.task.asset_id,
                    "observation_type": result.task.observation_type,
                    "status": result.status,
                    "observation_count": len(result.observations),
                    "error": result.error,
                },
            )
        return processed, results

    def status(self) -> dict[str, Any]:
        return {
            "store": self.store.counts(),
            "open_information_needs": len(self.information.open_needs()),
            "open_needs": [
                {
                    "need_id": item.need_id,
                    "asset_id": item.asset_id,
                    "observation_type": item.observation_type,
                    "reason": item.reason,
                    "priority": item.priority,
                }
                for item in self.information.open_needs()
            ],
        }
