#!/usr/bin/env python3
from rsqs_pulse.digital_twin import TwinAsset
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.intelligence_export import IntelligenceEnvelope
from rsqs_pulse.intelligence_federation import FederatedIntelligenceStore
from rsqs_pulse.intelligence_router import IntelligenceRouter
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.reality_observation import PhysicalObservation
from rsqs_pulse.reality_runtime import RealityEngine
from rsqs_pulse.runtime import FabricRuntime

producer_identity = NodeIdentity("producer")
producer = FabricRuntime(
    "producer",
    ":memory:",
    LocalPolicy(allowed_capabilities=set()),
    identity=producer_identity,
)
producer_reality = RealityEngine(producer)
producer_reality.twin.upsert_asset(
    TwinAsset("reservoir-1", "storage", "Reservoir 1", None, {})
)
producer_reality.ingest([
    PhysicalObservation(
        "level",
        "reservoir-1",
        "2026-10-01T00:00:00+00:00",
        73.2,
        "percent",
        0.94,
        "sensor-local",
        {"raw_ref": "local-only"},
    )
])

producer_router = IntelligenceRouter(
    producer,
    reality_engine=producer_reality,
)
asset_identity = producer_router.ensure_asset_identity("reservoir-1")
exported = producer_router.call(
    asset_identity.uri,
    "export",
    {"ttl_seconds": 300},
).result["envelope"]

consumer = FabricRuntime(
    "consumer",
    ":memory:",
    LocalPolicy(allowed_capabilities=set()),
    identity=NodeIdentity("consumer"),
)
federation = FederatedIntelligenceStore(consumer.state.conn)
federation.trust_issuer(producer_identity.public)

exported["relations"] = tuple(exported["relations"])
exported["provenance_refs"] = tuple(exported["provenance_refs"])
federation.import_envelope(
    IntelligenceEnvelope(**exported),
    now=exported["issued_at"],
)

consumer_router = IntelligenceRouter(
    consumer,
    federated_store=federation,
)
remote = consumer_router.call(asset_identity.uri, "state")
assert remote.result["level"]["value"] == 73.2
assert asset_identity.uri in consumer_router.identity_uris()

print("INTELLIGENCE_FEDERATION_PROOF=PASS")
producer.close()
consumer.close()
