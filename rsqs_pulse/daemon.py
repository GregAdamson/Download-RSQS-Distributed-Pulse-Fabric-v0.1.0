from __future__ import annotations
import argparse
import json
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .policy import LocalPolicy
from .runtime import FabricRuntime


class RuntimeHTTPDaemon:
    def __init__(self, runtime: FabricRuntime, host: str, port: int) -> None:
        self.runtime = runtime
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def _send(self, code: int, body: dict) -> None:
                raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                if self.path == "/health":
                    self._send(200, outer.runtime.health())
                    return
                if self.path == "/state":
                    self._send(200, outer.runtime.current_state().values)
                    return
                if self.path == "/capabilities":
                    self._send(200, {"capabilities": sorted(outer.runtime.handlers)})
                    return
                self._send(404, {"error": "not_found"})

        self.httpd = ThreadingHTTPServer((host, port), Handler)

    @property
    def address(self):
        return self.httpd.server_address

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="RSQS distributed cognition runtime daemon")
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--allow-capability", action="append", default=[])
    args = parser.parse_args()

    runtime = FabricRuntime(
        args.node_id,
        args.state,
        LocalPolicy(allowed_capabilities=set(args.allow_capability)),
    )
    daemon = RuntimeHTTPDaemon(runtime, args.host, args.port)

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
