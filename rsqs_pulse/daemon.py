from __future__ import annotations
import argparse
import json
import os
import signal
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .observability import FabricObserver
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
        write_token: str | None = None,
        ssl_context: ssl.SSLContext | None = None,
        max_body_bytes: int = 1_000_000,
    ) -> None:
        self.runtime = runtime
        self.observer = observer or FabricObserver(runtime)
        self.reality_engine = reality_engine
        self.write_token = write_token
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

            def _authorised_write(self) -> bool:
                if outer.write_token is None:
                    return False
                expected = f"Bearer {outer.write_token}"
                return self.headers.get("Authorization") == expected

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
                self._send(404, {"error": "not_found"})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/reality/observations":
                    self._send(404, {"error": "not_found"})
                    return
                if outer.reality_engine is None:
                    self._send(404, {"error": "reality_engine_disabled"})
                    return
                if not self._authorised_write():
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
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    self._send(400, {"error": str(exc)})

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
        description="RSQS distributed cognition and reality runtime daemon"
    )
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--allow-capability", action="append", default=[])
    parser.add_argument("--reality", action="store_true")
    parser.add_argument(
        "--write-token-env",
        default="RSQS_REALITY_WRITE_TOKEN",
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

    runtime = FabricRuntime(
        args.node_id,
        args.state,
        LocalPolicy(allowed_capabilities=set(args.allow_capability)),
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

    daemon = RuntimeHTTPDaemon(
        runtime,
        args.host,
        args.port,
        reality_engine=reality,
        write_token=write_token,
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
