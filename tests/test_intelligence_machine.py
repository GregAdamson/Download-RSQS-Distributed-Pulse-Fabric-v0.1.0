import json
import os
import queue
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from dataclasses import asdict

from rsqs_pulse.daemon import RuntimeHTTPDaemon
from rsqs_pulse.digital_twin import TwinAsset
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.intelligence_export import IntelligenceExportPolicy
from rsqs_pulse.intelligence_federation import FederatedIntelligenceStore
from rsqs_pulse.intelligence_router import IntelligenceRouter
from rsqs_pulse.policy import LocalPolicy
from rsqs_pulse.reality_observation import PhysicalObservation
from rsqs_pulse.reality_runtime import RealityEngine
from rsqs_pulse.runtime import FabricRuntime


class IntelligenceMachineTests(unittest.TestCase):
    def _runtime_with_asset(self, node_id="node-a"):
        identity = NodeIdentity(node_id)
        runtime = FabricRuntime(
            node_id,
            ":memory:",
            LocalPolicy(allowed_capabilities=set()),
            identity=identity,
        )
        reality = RealityEngine(runtime)
        reality.twin.upsert_asset(
            TwinAsset("asset-1", "storage", "Asset One", None, {})
        )
        reality.ingest([
            PhysicalObservation(
                "level",
                "asset-1",
                "2026-10-01T00:00:00+00:00",
                12.5,
                "ML",
                0.9,
                "sensor-a",
                {"raw": "local-only"},
            )
        ])
        return runtime, reality, identity

    def test_identity_is_stable_callable_and_export_is_derived_only(self):
        runtime, reality, identity = self._runtime_with_asset()
        router = IntelligenceRouter(runtime, reality_engine=reality)
        asset_identity = router.ensure_asset_identity("asset-1")

        again = router.ensure_asset_identity("asset-1")
        self.assertEqual(asset_identity.identity_id, again.identity_id)
        self.assertTrue(asset_identity.uri.startswith("rsqs://asset/"))

        snapshot = router.call(asset_identity.uri, "snapshot")
        self.assertEqual(snapshot.result["state"]["level"]["value"], 12.5)

        exported = router.call(
            asset_identity.uri,
            "export",
            {
                "minimum_confidence": 0.5,
                "include_provenance_refs": True,
                "ttl_seconds": 300,
            },
        ).result["envelope"]
        self.assertEqual(exported["state"]["level"]["value"], 12.5)
        self.assertNotIn("raw", json.dumps(exported))
        self.assertTrue(exported["signature"])
        runtime.close()

    def test_identity_rebuild_derives_same_uri(self):
        runtime_a, reality_a, _ = self._runtime_with_asset("node-stable")
        router_a = IntelligenceRouter(runtime_a, reality_engine=reality_a)
        uri_a = router_a.ensure_asset_identity("asset-1").uri
        runtime_a.close()

        runtime_b, reality_b, _ = self._runtime_with_asset("node-stable")
        router_b = IntelligenceRouter(runtime_b, reality_engine=reality_b)
        uri_b = router_b.ensure_asset_identity("asset-1").uri
        self.assertEqual(uri_a, uri_b)
        runtime_b.close()

    def test_signed_intelligence_can_be_imported_and_called_remotely(self):
        runtime_a, reality_a, identity_a = self._runtime_with_asset("node-a")
        router_a = IntelligenceRouter(runtime_a, reality_engine=reality_a)
        asset_identity = router_a.ensure_asset_identity("asset-1")
        envelope_dict = router_a.call(
            asset_identity.uri,
            "export",
            {"ttl_seconds": 300},
        ).result["envelope"]

        runtime_b = FabricRuntime(
            "node-b",
            ":memory:",
            LocalPolicy(allowed_capabilities=set()),
            identity=NodeIdentity("node-b"),
        )
        federated = FederatedIntelligenceStore(runtime_b.state.conn)
        federated.trust_issuer(identity_a.public)
        from rsqs_pulse.intelligence_export import IntelligenceEnvelope
        envelope_dict["relations"] = tuple(envelope_dict["relations"])
        envelope_dict["provenance_refs"] = tuple(
            envelope_dict["provenance_refs"]
        )
        envelope = IntelligenceEnvelope(**envelope_dict)
        federated.import_envelope(envelope, now=envelope.issued_at)

        router_b = IntelligenceRouter(
            runtime_b,
            federated_store=federated,
        )
        remote = router_b.call(asset_identity.uri, "state")
        self.assertEqual(remote.result["level"]["value"], 12.5)
        self.assertIn(asset_identity.uri, router_b.identity_uris())
        runtime_a.close()
        runtime_b.close()

    def test_untrusted_remote_intelligence_is_rejected(self):
        runtime_a, reality_a, _ = self._runtime_with_asset("node-a")
        router_a = IntelligenceRouter(runtime_a, reality_engine=reality_a)
        asset_identity = router_a.ensure_asset_identity("asset-1")
        envelope_dict = router_a.call(
            asset_identity.uri,
            "export",
            {"ttl_seconds": 300},
        ).result["envelope"]

        runtime_b = FabricRuntime(
            "node-b",
            ":memory:",
            LocalPolicy(allowed_capabilities=set()),
            identity=NodeIdentity("node-b"),
        )
        federated = FederatedIntelligenceStore(runtime_b.state.conn)
        from rsqs_pulse.intelligence_export import IntelligenceEnvelope
        envelope_dict["relations"] = tuple(envelope_dict["relations"])
        envelope_dict["provenance_refs"] = tuple(
            envelope_dict["provenance_refs"]
        )
        envelope = IntelligenceEnvelope(**envelope_dict)
        with self.assertRaises(PermissionError):
            federated.import_envelope(envelope, now=envelope.issued_at)
        runtime_a.close()
        runtime_b.close()

    def test_callable_intelligence_http_api(self):
        ready = queue.Queue()

        def serve():
            runtime, reality, identity = self._runtime_with_asset("api-node")
            federation = FederatedIntelligenceStore(runtime.state.conn)
            router = IntelligenceRouter(
                runtime,
                reality_engine=reality,
                federated_store=federation,
            )
            daemon = RuntimeHTTPDaemon(
                runtime,
                "127.0.0.1",
                0,
                reality_engine=reality,
                intelligence_router=router,
                federated_intelligence=federation,
                write_token="reality-secret",
                intelligence_token="intelligence-secret",
            )
            ready.put((daemon, runtime, router))
            daemon.serve_forever()
            runtime.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        daemon, runtime, router = ready.get(timeout=5)
        host, port = daemon.address
        base = f"http://{host}:{port}"

        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(
                base + "/intelligence/identities",
                timeout=5,
            )
        self.assertEqual(caught.exception.code, 401)

        req = urllib.request.Request(
            base + "/intelligence/identities",
            headers={"Authorization": "Bearer intelligence-secret"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            listing = json.loads(response.read().decode("utf-8"))
        asset_uri = next(
            item["uri"]
            for item in listing["identities"]
            if item["kind"] == "asset"
        )

        body = json.dumps({
            "identity_uri": asset_uri,
            "operation": "state",
            "args": {},
        }).encode("utf-8")
        req = urllib.request.Request(
            base + "/intelligence/call",
            data=body,
            headers={
                "Authorization": "Bearer intelligence-secret",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            called = json.loads(response.read().decode("utf-8"))
        self.assertEqual(called["result"]["level"]["value"], 12.5)

        daemon.close()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
