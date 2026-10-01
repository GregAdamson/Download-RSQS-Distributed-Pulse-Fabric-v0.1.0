from __future__ import annotations
import json
import threading
import urllib.parse
import urllib.request
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List, Tuple
from .model import Pulse


def pulse_to_json(pulse: Pulse) -> bytes:
    return json.dumps(asdict(pulse), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def pulse_from_dict(data: dict) -> Pulse:
    return Pulse(
        pulse_id=data["pulse_id"],
        network=data["network"],
        epoch=int(data["epoch"]),
        kind=data["kind"],
        issued_at=int(data["issued_at"]),
        expires_at=int(data["expires_at"]),
        payload=data.get("payload", {}),
        signature=data.get("signature", ""),
    )


class PulseEventStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: List[Pulse] = []

    def append(self, pulse: Pulse) -> int:
        with self._lock:
            self._events.append(pulse)
            return len(self._events)

    def after(self, cursor: int, limit: int = 100) -> Tuple[int, List[Pulse]]:
        with self._lock:
            events = self._events[max(cursor, 0):max(cursor, 0) + max(1, min(limit, 1000))]
            return cursor + len(events), list(events)


class PulseHTTPServer:
    def __init__(self, host: str, port: int, publish_token: str) -> None:
        self.store = PulseEventStore()
        store = self.store
        token = publish_token

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def _json(self, code: int, body: dict) -> None:
                raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self) -> None:
                if self.path != "/v1/pulses":
                    self._json(404, {"error": "not_found"})
                    return
                if self.headers.get("Authorization", "") != "Bearer " + token:
                    self._json(401, {"error": "unauthorized"})
                    return
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    data = json.loads(self.rfile.read(length).decode("ascii"))
                    pulse = pulse_from_dict(data)
                except Exception:
                    self._json(400, {"error": "invalid_pulse"})
                    return
                cursor = store.append(pulse)
                self._json(202, {"cursor": cursor})

            def do_GET(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != "/v1/pulses":
                    self._json(404, {"error": "not_found"})
                    return
                query = urllib.parse.parse_qs(parsed.query)
                try:
                    cursor = int(query.get("after", ["0"])[0])
                    limit = int(query.get("limit", ["100"])[0])
                except ValueError:
                    self._json(400, {"error": "invalid_cursor"})
                    return
                next_cursor, events = store.after(cursor, limit)
                self._json(200, {
                    "cursor": next_cursor,
                    "events": [asdict(event) for event in events],
                })

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.httpd.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None


class HTTPTransportClient:
    def __init__(self, base_url: str, publish_token: str | None = None, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.publish_token = publish_token
        self.timeout = timeout

    def publish(self, pulse: Pulse) -> int:
        if self.publish_token is None:
            raise PermissionError("publish token required")
        request = urllib.request.Request(
            self.base_url + "/v1/pulses",
            data=pulse_to_json(pulse),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.publish_token,
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("ascii"))
        return int(body["cursor"])

    def poll(self, after: int = 0, limit: int = 100) -> tuple[int, list[Pulse]]:
        query = urllib.parse.urlencode({"after": after, "limit": limit})
        with urllib.request.urlopen(self.base_url + "/v1/pulses?" + query, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("ascii"))
        return int(body["cursor"]), [pulse_from_dict(item) for item in body["events"]]
