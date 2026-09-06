from __future__ import annotations
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from importlib.resources import files
import json
import threading
import time
from . import __version__

WEB_ROOT = files("autoft8").joinpath("web")


def dashboard_state(engine) -> dict:
    """Return the operator-console state with the canonical package version.

    The decision engine deliberately owns radio/QSO state, while the package
    version belongs to the application shell. Keeping that value here prevents
    stale hard-coded dashboard versions after a release bump.
    """
    state = engine.snapshot()
    state["version"] = __version__
    return state


class Dashboard:
    def __init__(self, engine, host, port):
        self.engine = engine
        self.host = host
        self.port = port
        self.server = None

    def start(self):
        engine = self.engine

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def _bytes(self, code: int, body: bytes, ctype: str):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, payload: dict):
                self._bytes(code, json.dumps(payload, default=str).encode(), "application/json; charset=utf-8")

            def _read_json(self) -> dict:
                try:
                    n = int(self.headers.get("Content-Length", "0") or "0")
                    if n <= 0:
                        return {}
                    return json.loads(self.rfile.read(n).decode("utf-8"))
                except Exception:
                    return {}

            def _asset(self, name: str, ctype: str):
                try:
                    body = WEB_ROOT.joinpath(name).read_bytes()
                except (FileNotFoundError, IsADirectoryError):
                    return self._json(404, {"error": "not found"})
                self._bytes(200, body, ctype)

            def do_GET(self):
                if self.path == "/":
                    return self._asset("index.html", "text/html; charset=utf-8")
                if self.path == "/assets/dashboard.css":
                    return self._asset("dashboard.css", "text/css; charset=utf-8")
                if self.path == "/assets/dashboard.js":
                    return self._asset("dashboard.js", "text/javascript; charset=utf-8")
                if self.path == "/api/state":
                    return self._json(200, dashboard_state(engine))
                if self.path == "/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "keep-alive")
                    self.send_header("X-Accel-Buffering", "no")
                    self.end_headers()
                    try:
                        while True:
                            payload = json.dumps(dashboard_state(engine), default=str, separators=(",", ":"))
                            self.wfile.write(f"data: {payload}\n\n".encode())
                            self.wfile.flush()
                            time.sleep(0.5)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                return self._json(404, {"error": "not found"})

            def do_POST(self):
                try:
                    if self.path == "/api/arm":
                        engine.set_armed(True)
                    elif self.path == "/api/disarm":
                        engine.set_armed(False)
                    elif self.path == "/api/halt":
                        engine.halt()
                    elif self.path == "/api/strategy":
                        engine.set_strategy(self._read_json().get("strategy", ""))
                    elif self.path == "/api/limits":
                        data = self._read_json()
                        engine.set_limits(data.get("per_hour"), data.get("per_session"))
                    else:
                        return self._json(404, {"error": "not found"})
                    return self._json(200, {"ok": True, "state": dashboard_state(engine)})
                except ValueError as exc:
                    return self._json(400, {"ok": False, "error": str(exc)})
                except Exception as exc:
                    return self._json(500, {"ok": False, "error": str(exc)})

        self.server = ThreadingHTTPServer((self.host, self.port), H)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True, name="dxweaver-dashboard").start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
