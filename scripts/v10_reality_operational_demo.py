#!/usr/bin/env python3
from rsqs_pulse.digital_twin import TwinAsset
from rsqs_pulse.evidence_fusion import EvidenceFusionEngine, SourcePolicy
from rsqs_pulse.information_requirements import InformationRequirementSpec
from rsqs_pulse.observation_acquisition import (
    AcquisitionPlanner,
    ObservationSource,
)
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.reality_observation import PhysicalObservation
from rsqs_pulse.reality_runtime import RealityEngine
from rsqs_pulse.runtime import FabricRuntime


class StaticAdapter:
    def __init__(self, observations):
        self.observations = tuple(observations)

    def fetch(self):
        return self.observations


runtime = FabricRuntime(
    "reality-demo",
    ":memory:",
    LocalPolicy(allowed_capabilities=set()),
)
engine = RealityEngine(
    runtime,
    fusion=EvidenceFusionEngine(
        {
            "sensor-a": SourcePolicy(
                reliability=0.95,
                independence_group="source-a",
            ),
            "sensor-b": SourcePolicy(
                reliability=0.90,
                independence_group="source-b",
            ),
        }
    ),
)
engine.twin.upsert_asset(
    TwinAsset("asset-1", "storage", "Asset 1", None, {})
)

requirements = {
    "asset-1": [
        InformationRequirementSpec(
            "level",
            minimum_confidence=0.2,
            priority=10,
        )
    ]
}
needs = engine.information.evaluate(
    "asset-1",
    requirements["asset-1"],
    engine.twin,
    engine.store,
)
assert needs and needs[0].reason == "missing"

sources = [
    ObservationSource(
        "level-source-a",
        ("level",),
        StaticAdapter([
            PhysicalObservation.create(
                "level",
                "asset-1",
                50.0,
                "ML",
                0.9,
                "sensor-a",
                {"sensor": "a"},
            )
        ]),
        reliability=0.95,
        independence_group="source-a",
    ),
    ObservationSource(
        "level-source-b",
        ("level",),
        StaticAdapter([
            PhysicalObservation.create(
                "level",
                "asset-1",
                50.5,
                "ML",
                0.85,
                "sensor-b",
                {"sensor": "b"},
            )
        ]),
        reliability=0.90,
        independence_group="source-b",
    ),
]
processed, acquisition = engine.acquire_and_ingest(
    sources,
    planner=AcquisitionPlanner(max_sources_per_need=2),
    requirements=requirements,
)
assert len(acquisition) == 2
assert processed.raw_count == 2
assert not engine.information.open_needs()
assert "physical.asset-1.level" in runtime.current_state().values
assert engine.twin.latest_state("asset-1")["level"].unit == "ML"

variance = engine.reconcile_expected(
    {"physical.asset-1.level": 52.0},
    processed.fused[0],
)
assert variance.variance > 0
assert engine.store.counts()["raw_observations"] == 2
assert engine.store.counts()["fused_observations"] == 1
assert engine.store.counts()["variances"] == 1
assert runtime.ledger.verify()

print("REALITY_OPERATIONAL_PROOF=PASS")
runtime.close()
