from __future__ import annotations
import argparse
import json
import os
import signal
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .intelligence_export import IntelligenceEnvelope
from .intelligence_federation import FederatedIntelligenceStore
from .intelligence_router import IntelligenceRouter
from .observability import FabricObserver
from .persistent_identity import load_or_create_identity
from .policy import LocalPolicy
from .reality_observation import PhysicalObservation
from .reality_runtime import RealityEngine
from .runtime import FabricRuntime


class RuntimeHTTPDaemon:
    def __init__(
        self,
        runtime: FabricRuntime,
        host: str,
        port: int,
        *,
        observer: FabricObserver | None = None,
        reality_engine: RealityEngine | None = None,
        intelligence_router: IntelligenceRouter | None = None,
        federated_intelligence: FederatedIntelligenceStore | None = None,
        write_token: str | None = None,
        intelligence_token: str | None = None,
        ssl_context: ssl.SSLContext | None = None,
        max_body_bytes: int = 1_000_000,
    ) -> None:
        self.runtime = runtime
        self.observer = observer or FabricObserver(runtime)
        self.reality_engine = reality_engine
        self.intelligence_router = intelligence_router
        self.federated_intelligence = federated_intelligence
        self.write_token = write_token
        self.intelligence_token = intelligence_token
        self.max_body_bytes = max(1, int(max_body_bytes))
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def _send(self, code: int, body: dict) -> None:
                raw = json.dumps(
                    body,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    default=str,
                ).encode("ascii")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _authorised(self, token: str | None) -> bool:
                if token is None:
                    return False
                return self.headers.get("Authorization") == f"Bearer {token}"

            def _read_json(self):
                raw_length = self.headers.get("Content-Length")
                if raw_length is None:
                    raise ValueError("Content-Length required")
                length = int(raw_length)
                if length < 0 or length > outer.max_body_bytes:
                    raise ValueError("request body too large")
                return json.loads(self.rfile.read(length).decode("utf-8"))

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._send(200, outer.runtime.health())
                    return
                if parsed.path == "/state":
                    self._send(200, outer.runtime.current_state().values)
                    return
                if parsed.path == "/capabilities":
                    self._send(
                        200,
                        {"capabilities": sorted(outer.runtime.handlers)},
                    )
                    return
                if parsed.path == "/observability":
                    self._send(200, outer.observer.as_dict())
                    return
                if parsed.path == "/operations":
                    snapshot = outer.observer.snapshot()
                    self._send(
                        200,
                        {"operations": list(snapshot.unresolved_operations)},
                    )
                    return
                if parsed.path == "/reality/status":
                    if outer.reality_engine is None:
                        self._send(404, {"error": "reality_engine_disabled"})
                        return
                    self._send(200, outer.reality_engine.status())
                    return
                if parsed.path == "/reality/needs":
                    if outer.reality_engine is None:
                        self._send(404, {"error": "reality_engine_disabled"})
                        return
                    self._send(
                        200,
                        {
                            "needs": [
                                {
                                    "need_id": item.need_id,
                                    "asset_id": item.asset_id,
                                    "observation_type": item.observation_type,
                                    "reason": item.reason,
                                    "priority": item.priority,
                                    "minimum_confidence": item.minimum_confidence,
                                    "max_age_seconds": item.max_age_seconds,
                                    "created_at": item.created_at,
                                }
                                for item in outer.reality_engine.information.open_needs()
                            ]
                        },
                    )
                    return
                if parsed.path == "/reality/twin":
                    if outer.reality_engine is None:
                        self._send(404, {"error": "reality_engine_disabled"})
                        return
                    asset_id = parse_qs(parsed.query).get("asset_id", [None])[0]
                    if not asset_id:
                        self._send(400, {"error": "asset_id_required"})
                        return
                    try:
                        body = outer.reality_engine.twin.snapshot(asset_id)
                    except KeyError:
                        self._send(404, {"error": "asset_not_found"})
                        return
                    self._send(200, body)
                    return
                if parsed.path == "/intelligence/status":
                    if outer.intelligence_router is None:
                        self._send(404, {"error": "intelligence_disabled"})
                        return
                    if not self._authorised(outer.intelligence_token):
                        self._send(401, {"error": "unauthorised"})
                        return
                    self._send(
                        200,
                        {
                            "local_identities": len(
                                outer.intelligence_router.identities()
                            ),
                            "callable_identity_uris": list(
                                outer.intelligence_router.identity_uris()
                            ),
                            "federated": (
                                None
                                if outer.federated_intelligence is None
                                else outer.federated_intelligence.status()
                            ),
                        },
                    )
                    return
                if parsed.path == "/intelligence/identities":
                    if outer.intelligence_router is None:
                        self._send(404, {"error": "intelligence_disabled"})
                        return
                    if not self._authorised(outer.intelligence_token):
                        self._send(401, {"error": "unauthorised"})
                        return
                    self._send(
                        200,
                        {
                            "identities": [
                                {
                                    "identity_id": item.identity_id,
                                    "kind": item.kind,
                                    "local_ref": item.local_ref,
                                    "display_name": item.display_name,
                                    "owner_node": item.owner_node,
                                    "metadata": item.metadata,
                                    "uri": item.uri,
                                }
                                for item in outer.intelligence_router.identities()
                            ],
                            "callable_identity_uris": list(
                                outer.intelligence_router.identity_uris()
                            ),
                        },
                    )
                    return
                self._send(404, {"error": "not_found"})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)

                if parsed.path == "/reality/observations":
                    if outer.reality_engine is None:
                        self._send(404, {"error": "reality_engine_disabled"})
                        return
                    if not self._authorised(outer.write_token):
                        self._send(401, {"error": "unauthorised"})
                        return
                    try:
                        body = self._read_json()
                        rows = body.get("observations")
                        if not isinstance(rows, list):
                            raise ValueError("observations must be a list")
                        observations = tuple(
                            PhysicalObservation(
                                observation_type=str(row["observation_type"]),
                                asset_id=str(row["asset_id"]),
                                timestamp=str(row["timestamp"]),
                                value=row["value"],
                                unit=str(row["unit"]),
                                confidence=float(row.get("confidence", 1.0)),
                                source=str(row["source"]),
                                provenance=dict(row.get("provenance", {})),
                            )
                            for row in rows
                        )
                        if any(
                            item.confidence < 0.0 or item.confidence > 1.0
                            for item in observations
                        ):
                            raise ValueError("confidence must be in [0,1]")
                        result = outer.reality_engine.ingest(observations)
                        self._send(
                            202,
                            {
                                "accepted": result.raw_count,
                                "fused": len(result.fused),
                                "information_needs": len(result.information_needs),
                            },
                        )
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as exc:
                        self._send(400, {"error": str(exc)})
                    return

                if parsed.path == "/intelligence/call":
                    if outer.intelligence_router is None:
                        self._send(404, {"error": "intelligence_disabled"})
                        return
                    if not self._authorised(outer.intelligence_token):
                        self._send(401, {"error": "unauthorised"})
                        return
                    try:
                        body = self._read_json()
                        result = outer.intelligence_router.call(
                            str(body["identity_uri"]),
                            str(body.get("operation", "describe")),
                            body.get("args") or {},
                        )
                        self._send(
                            200,
                            {
                                "identity_uri": result.identity_uri,
                                "operation": result.operation,
                                "result": result.result,
                            },
                        )
                    except KeyError as exc:
                        self._send(404, {"error": str(exc)})
                    except (TypeError, ValueError) as exc:
                        self._send(400, {"error": str(exc)})
                    return

                if parsed.path == "/intelligence/import":
                    if outer.federated_intelligence is None:
                        self._send(404, {"error": "federation_disabled"})
                        return
                    if not self._authorised(outer.intelligence_token):
                        self._send(401, {"error": "unauthorised"})
                        return
                    try:
                        body = self._read_json()
                        raw = dict(body["envelope"])
                        raw["relations"] = tuple(raw.get("relations", ()))
                        raw["provenance_refs"] = tuple(
                            raw.get("provenance_refs", ())
                        )
                        envelope = IntelligenceEnvelope(**raw)
                        outer.federated_intelligence.import_envelope(envelope)
                        self._send(
                            202,
                            {
                                "accepted": envelope.envelope_id,
                                "identity_uri": envelope.identity_uri,
                                "issuer_node": envelope.issuer_node,
                            },
                        )
                    except PermissionError as exc:
                        self._send(403, {"error": str(exc)})
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as exc:
                        self._send(400, {"error": str(exc)})
                    return

                self._send(404, {"error": "not_found"})

        self.httpd = HTTPServer((host, port), Handler)
        if ssl_context is not None:
            self.httpd.socket = ssl_context.wrap_socket(
                self.httpd.socket,
                server_side=True,
            )

    @property
    def address(self):
        return self.httpd.server_address

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RSQS distributed cognition, reality and intelligence runtime daemon"
    )
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--allow-capability", action="append", default=[])
    parser.add_argument("--reality", action="store_true")
    parser.add_argument("--intelligence", action="store_true")
    parser.add_argument("--identity-key")
    parser.add_argument(
        "--write-token-env",
        default="RSQS_REALITY_WRITE_TOKEN",
    )
    parser.add_argument(
        "--intelligence-token-env",
        default="RSQS_INTELLIGENCE_TOKEN",
    )
    parser.add_argument("--cert")
    parser.add_argument("--key")
    args = parser.parse_args()

    if (args.cert is None) != (args.key is None):
        raise SystemExit("--cert and --key must be provided together")

    tls = None
    if args.cert is not None:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(args.cert, args.key)

    identity_path = args.identity_key or (args.state + ".identity")
    identity = load_or_create_identity(args.node_id, identity_path)
    runtime = FabricRuntime(
        args.node_id,
        args.state,
        LocalPolicy(allowed_capabilities=set(args.allow_capability)),
        identity=identity,
    )
    reality = RealityEngine(runtime) if args.reality else None

    write_token = None
    if args.reality:
        write_token = os.environ.get(args.write_token_env)
        if not write_token:
            runtime.close()
            raise SystemExit(
                f"missing reality write token environment variable: {args.write_token_env}"
            )

    intelligence_token = None
    federation = None
    router = None
    if args.intelligence:
        intelligence_token = os.environ.get(args.intelligence_token_env)
        if not intelligence_token:
            runtime.close()
            raise SystemExit(
                f"missing intelligence token environment variable: {args.intelligence_token_env}"
            )
        federation = FederatedIntelligenceStore(runtime.state.conn)
        router = IntelligenceRouter(
            runtime,
            reality_engine=reality,
            federated_store=federation,
        )

    daemon = RuntimeHTTPDaemon(
        runtime,
        args.host,
        args.port,
        reality_engine=reality,
        intelligence_router=router,
        federated_intelligence=federation,
        write_token=write_token,
        intelligence_token=intelligence_token,
        ssl_context=tls,
    )

    def stop(*_):
        threading.Thread(target=daemon.close, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        daemon.serve_forever()
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
