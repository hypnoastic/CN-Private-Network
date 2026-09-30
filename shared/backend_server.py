#!/usr/bin/env python3
"""The two small HTTP/1.1 backends; only Python's standard library is used."""
import json
import os
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from env_loader import ROOT, load_env

ETAG = '"cn-project-v1"'
# Identical representation on A and B makes this ETag valid across round robin.
CACHE_BODY = b'{"message":"Computer Networks Phase 1 cache demonstration","version":1}\n'


def handler_for(backend):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.respond()

        def do_HEAD(self):
            self.respond(head=True)

        def respond(self, head=False):
            path = urlsplit(self.path).path
            code, headers = 200, {}
            if path == "/":
                body = json.dumps({"backend": backend, "message": f"Backend {backend} is running"}).encode() + b"\n"
            elif path == "/api/status":
                body = json.dumps({"backend": backend, "status": "ok"}).encode() + b"\n"
            elif path == "/cache-demo":
                body = CACHE_BODY
                headers = {"Cache-Control": "public, max-age=60", "ETag": ETAG}
                tags = [tag.strip().removeprefix("W/") for tag in self.headers.get("If-None-Match", "").split(",")]
                if ETAG in tags or "*" in tags:
                    code = 304
            else:
                code = 404
                body = b'{"error":"Not found"}\n'
            self.send_response(code)
            self.send_header("X-Backend", backend)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            # 304 has no body. Omit Content-Length there (HTTP semantics).
            if code != 304:
                self.send_header("Content-Length", str(len(body)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            if not head and code != 304:
                self.wfile.write(body)

    return Handler


def serve(backend):
    try:
        env = load_env()
        port = int(env[f"BACKEND_{backend}_PORT"])
        server = ThreadingHTTPServer(("0.0.0.0", port), handler_for(backend))
    except (ValueError, OSError) as exc:
        print(f"Cannot start Backend {backend}: {exc}", file=sys.stderr)
        return 1
    server.daemon_threads = True
    server.timeout = 1
    def stop_signal(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_signal)
    directory = ROOT / ("mac3_backend_a" if backend == "A" else "mac4_backend_b_client") / "runtime"
    directory.mkdir(exist_ok=True)
    pidfile = directory / "backend.pid"
    pidfile.write_text(str(os.getpid()))
    print(f"Backend {backend} listening on 0.0.0.0:{port}; press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print(f"\nStopping Backend {backend}.", flush=True)
    finally:
        server.server_close()
        if pidfile.exists() and pidfile.read_text().strip() == str(os.getpid()):
            pidfile.unlink()
    return 0
