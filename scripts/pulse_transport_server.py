#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import ssl
import threading

from rsqs_pulse.http_transport import PulseHTTPServer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RSQS durable pulse transport server"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--store", required=True)
    parser.add_argument("--token-env", default="RSQS_TRANSPORT_TOKEN")
    parser.add_argument("--cert")
    parser.add_argument("--key")
    args = parser.parse_args()

    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(
            f"missing transport token environment variable: {args.token_env}"
        )
    if (args.cert is None) != (args.key is None):
        raise SystemExit("--cert and --key must be provided together")

    tls = None
    if args.cert is not None:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(args.cert, args.key)

    server = PulseHTTPServer(
        args.host,
        args.port,
        token,
        store_path=args.store,
        ssl_context=tls,
    )

    def stop(*_):
        threading.Thread(target=server.close, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    host, port = server.address
    scheme = "https" if tls is not None else "http"
    print(f"RSQS_TRANSPORT={scheme}://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.close()


if __name__ == "__main__":
    main()
