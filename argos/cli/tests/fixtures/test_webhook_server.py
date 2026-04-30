"""Tiny in-process HTTP server fixture used by ARG1-041 webhook tests.

Run a one-shot loopback server (port chosen by the OS) on a daemon thread,
record every request it sees, and let tests inspect them.

The filename includes ``test_`` to make the package layout predictable, but
this module contains no ``unittest`` cases — running it as a test target is
a no-op.
"""

from __future__ import annotations

import http.server
import json
import socket
import threading
from typing import Any
from urllib.parse import urlparse


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    """Records every POST it sees on ``self.server.requests``.

    Responds with ``self.server.response_status`` (default 200). Silent on
    stderr so test output stays clean.
    """

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return  # silence "127.0.0.1 - - [...] POST /hook HTTP/1.0" lines

    def do_POST(self) -> None:  # noqa: N802 — http.server convention
        length_header = self.headers.get("Content-Length") or "0"
        try:
            length = int(length_header)
        except ValueError:
            length = 0
        raw_body = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None

        path = urlparse(self.path).path
        record = {
            "path": path,
            "raw_path": self.path,
            "method": "POST",
            "headers": {k: v for k, v in self.headers.items()},
            "body": raw_body,
            "payload": payload,
        }
        self.server.requests.append(record)  # type: ignore[attr-defined]

        status = getattr(self.server, "response_status", 200)
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        body_out = b"OK" if 200 <= status < 300 else b"ERROR"
        try:
            self.wfile.write(body_out)
        except OSError:
            pass


class WebhookTestServer:
    """Wrapper around an :class:`http.server.HTTPServer` running on a daemon thread."""

    def __init__(self, response_status: int = 200) -> None:
        self._server = http.server.HTTPServer(("127.0.0.1", 0), _RecordingHandler)
        self._server.requests = []  # type: ignore[attr-defined]
        self._server.response_status = response_status  # type: ignore[attr-defined]
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()

    @property
    def host(self) -> str:
        return self._server.server_address[0]

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/hook"

    @property
    def requests(self) -> list[dict[str, Any]]:
        return list(self._server.requests)  # type: ignore[attr-defined]

    def set_response_status(self, status: int) -> None:
        self._server.response_status = status  # type: ignore[attr-defined]

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)


def find_unused_port() -> int:
    """Return a TCP port that was free at call time (best-effort).

    Used by tests that need an unreachable address: bind to port 0, capture
    the chosen port, then release it. There is a brief race between
    closing the socket and the test using the port — acceptable for the
    "connection refused on a closed loopback port" scenario these tests
    target.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()
