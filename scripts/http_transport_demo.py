#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rsqs_pulse.http_transport import HTTPTransportClient, PulseHTTPServer
from rsqs_pulse.identity import NodeIdentity
from rsqs_pulse.model import Pulse
from rsqs_pulse.secure import pulse_bytes


server = PulseHTTPServer("127.0.0.1", 0, "demo-publish-token")
server.start()
host, port = server.address
base = f"http://{host}:{port}"

try:
    authority = NodeIdentity("authority")
    unsigned = Pulse.new("rsqs-global", 1, "WAKE", {"reason": "http-demo"})
    pulse = Pulse(
        unsigned.pulse_id,
        unsigned.network,
        unsigned.epoch,
        unsigned.kind,
        unsigned.issued_at,
        unsigned.expires_at,
        unsigned.payload,
        authority.sign(pulse_bytes(unsigned)),
    )
    publisher = HTTPTransportClient(base, "demo-publish-token")
    reader = HTTPTransportClient(base)
    publisher.publish(pulse)
    cursor, events = reader.poll()
    print("cursor", cursor)
    print("events", [(e.epoch, e.kind, e.network) for e in events])
finally:
    server.close()
