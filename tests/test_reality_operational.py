import csv
import datetime
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from rsqs_pulse.digital_twin import DigitalTwinStore, TwinAsset
from rsqs_pulse.evidence_fusion import EvidenceFusionEngine, SourcePolicy
from rsqs_pulse.information_requirements import (
    InformationRequirementEngine,
    InformationRequirementSpec,
)
from rsqs_pulse.persistent import SQLiteState
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.reality_observation import PhysicalObservation
from rsqs_pulse.reality_runtime import RealityEngine
from rsqs_pulse.reality_store import RealityStore
from rsqs_pulse.runtime import FabricRuntime
from rsqs_pulse.sensor_adapters import (
    CSVObservationAdapter,
    JSONFileObservationAdapter,
    JSONHTTPObservationAdapter,
    ObservationMapping,
    RecordObservationAdapter,
)


def obs(source, value, *, ts="2026-10-01T00:00:00+00:00", confidence=1.0):
    return PhysicalObservation(
        observation_type="temperature",
        asset_id="asset-1",
        timestamp=ts,
        value=value,
        unit="C",
        confidence=confidence,
        source=source,
        provenance={"source": source},
    )


class RealityOperationalTests(unittest.TestCase):
    def test_record_json_file_and_csv_adapters(self):
        mapping = ObservationMapping(
            observation_type_field="kind",
            asset_id_field="asset",
            value_field="value",
            unit_field="unit",
            confidence_field="confidence",
            timestamp_field="timestamp",
        )
        adapter = RecordObservationAdapter(mapping, source="records")
        rows = [{
            "kind": "soil_moisture",
            "asset": "field-1",
            "value": 0.3,
            "unit": "fraction",
            "confidence": 0.8,
            "timestamp": "2026-10-01T00:00:00+00:00",
        }]
        adapted = adapter.adapt(rows)
        self.assertEqual(adapted[0].asset_id, "field-1")
        self.assertEqual(adapted[0].confidence, 0.8)

        with tempfile.TemporaryDirectory() as d:
            json_path = os.path.join(d, "data.json")
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump({"records": rows}, handle)
            fetched = JSONFileObservationAdapter(
                json_path, adapter, records_path=("records",)
            ).fetch()
            self.assertEqual(fetched[0].value, 0.3)

            csv_path = os.path.join(d, "data.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerow(rows[0])
            fetched_csv = CSVObservationAdapter(csv_path, adapter).fetch()
            self.assertEqual(fetched_csv[0].asset_id, "field-1")

    def test_http_adapter_fetches_live_local_json(self):
        payload = {
            "data": [{
                "kind": "flow",
                "asset": "meter-1",
                "value": 12.5,
                "unit": "ML",
                "confidence": 0.9,
                "timestamp": "2026-10-01T00:00:00+00:00",
            }]
        }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            mapping = ObservationMapping(
                observation_type_field="kind",
                asset_id_field="asset",
                value_field="value",
                unit_field="unit",
                confidence_field="confidence",
                timestamp_field="timestamp",
            )
            adapter = JSONHTTPObservationAdapter(
                f"http://127.0.0.1:{server.server_address[1]}",
                RecordObservationAdapter(mapping, source="http-feed"),
                records_path=("data",),
            )
            result = adapter.fetch()
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].value, 12.5)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_fusion_limits_correlated_sources_and_detects_disagreement(self):
        policies = {
            "derived-a": SourcePolicy(independence_group="sensor-x"),
            "derived-b": SourcePolicy(independence_group="sensor-x"),
            "independent": SourcePolicy(independence_group="sensor-y"),
        }
        engine = EvidenceFusionEngine(policies, contradiction_threshold=0.2)
        fused = engine.fuse([
            obs("derived-a", 10),
            obs("derived-b", 10),
            obs("independent", 20),
        ], now=datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc))
        self.assertEqual(fused.independent_source_count, 2)
        self.assertEqual(fused.contributor_count, 3)
        self.assertTrue(fused.contradictory)
        self.assertGreater(fused.value, 10)
        self.assertLess(fused.value, 20)

    def test_stale_evidence_decays_and_fresh_measurement_dominates(self):
        policies = {
            "old": SourcePolicy(half_life_seconds=10),
            "fresh": SourcePolicy(half_life_seconds=10),
        }
        engine = EvidenceFusionEngine(policies)
        now = datetime.datetime(2026, 10, 1, 0, 2, tzinfo=datetime.timezone.utc)
        fused = engine.fuse([
            obs("old", 100, ts="2026-10-01T00:00:00+00:00"),
            obs("fresh", 10, ts="2026-10-01T00:01:59+00:00"),
        ], now=now)
        self.assertLess(fused.value, 20)

    def test_reality_store_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "reality.db")
            state = SQLiteState(path)
            store = RealityStore(state.conn)
            item = obs("sensor", 15)
            store.record_observation(item, observation_id="o1")
            fused = EvidenceFusionEngine().fuse([item])
            store.record_fused(fused, fused_id="f1")
            state.conn.close()

            restored = SQLiteState(path)
            store = RealityStore(restored.conn)
            self.assertEqual(store.observations("asset-1")[0].value, 15)
            self.assertEqual(
                store.latest_fused("asset-1", "temperature").value,
                15,
            )
            restored.conn.close()

    def test_twin_hierarchy_cycle_rolls_back(self):
        state = SQLiteState(":memory:")
        twin = DigitalTwinStore(state.conn)
        twin.upsert_asset(TwinAsset("a", "site", "A", None, {}))
        twin.upsert_asset(TwinAsset("b", "asset", "B", "a", {}))
        with self.assertRaises(ValueError):
            twin.upsert_asset(TwinAsset("a", "site", "A", "b", {}))
        self.assertIsNone(twin.asset("a").parent_id)
        state.conn.close()

    def test_information_needs_missing_contradictory_and_resolution(self):
        state = SQLiteState(":memory:")
        twin = DigitalTwinStore(state.conn)
        reality = RealityStore(state.conn)
        engine = InformationRequirementEngine(state.conn)
        twin.upsert_asset(TwinAsset("asset-1", "asset", "Asset", None, {}))

        spec = InformationRequirementSpec(
            "temperature",
            minimum_confidence=0.0,
            max_age_seconds=3600,
            priority=5,
        )
        needs = engine.evaluate(
            "asset-1",
            [spec],
            twin,
            reality,
            now=datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(needs[0].reason, "missing")

        fused = EvidenceFusionEngine(contradiction_threshold=0.01).fuse([
            obs("s1", 10),
            obs("s2", 20),
        ], now=datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc))
        reality.record_fused(fused, fused_id="contradictory")
        twin.apply_fused(fused, source_ref="fused:contradictory")
        needs = engine.evaluate(
            "asset-1",
            [spec],
            twin,
            reality,
            now=datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(needs[0].reason, "contradictory_evidence")

        good = EvidenceFusionEngine().fuse([
            obs("s1", 15),
            obs("s2", 15),
        ], now=datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc))
        reality.record_fused(good, fused_id="good")
        twin.apply_fused(good, source_ref="fused:good")
        needs = engine.evaluate(
            "asset-1",
            [spec],
            twin,
            reality,
            now=datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc),
        )
        self.assertEqual(needs, ())
        self.assertEqual(engine.open_needs(), ())
        state.conn.close()

    def test_reality_engine_end_to_end(self):
        runtime = FabricRuntime(
            "reality-node",
            ":memory:",
            LocalPolicy(allowed_capabilities=set()),
        )
        engine = RealityEngine(
            runtime,
            fusion=EvidenceFusionEngine(
                {
                    "sensor-a": SourcePolicy(independence_group="a"),
                    "sensor-b": SourcePolicy(independence_group="b"),
                }
            ),
        )
        engine.twin.upsert_asset(
            TwinAsset("tank-1", "storage", "Tank 1", None, {})
        )
        requirements = {
            "tank-1": [
                InformationRequirementSpec(
                    "level",
                    minimum_confidence=0.2,
                    priority=10,
                ),
                InformationRequirementSpec(
                    "temperature",
                    minimum_confidence=0.2,
                    priority=5,
                ),
            ]
        }
        result = engine.ingest(
            [
                PhysicalObservation(
                    "level", "tank-1", "2026-10-01T00:00:00+00:00",
                    10.0, "ML", 0.9, "sensor-a", {"id": "a"},
                ),
                PhysicalObservation(
                    "level", "tank-1", "2026-10-01T00:00:01+00:00",
                    10.2, "ML", 0.8, "sensor-b", {"id": "b"},
                ),
            ],
            requirements=requirements,
        )
        self.assertEqual(result.raw_count, 2)
        self.assertEqual(len(result.fused), 1)
        self.assertEqual(
            runtime.current_state().values["physical.tank-1.level:unit"],
            "ML",
        )
        self.assertEqual(
            engine.twin.latest_state("tank-1")["level"].unit,
            "ML",
        )
        self.assertEqual(
            result.information_needs[0].observation_type,
            "temperature",
        )
        variance = engine.reconcile_expected(
            {"physical.tank-1.level": 11.0},
            result.fused[0],
        )
        self.assertGreater(variance.variance, 0)
        self.assertEqual(engine.status()["store"]["raw_observations"], 2)
        self.assertEqual(engine.status()["store"]["variances"], 1)
        self.assertTrue(runtime.ledger.verify())
        runtime.close()


if __name__ == "__main__":
    unittest.main()
