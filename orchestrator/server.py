"""Loopback-only dashboard. This server cannot call Codex or launch workers."""
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from .core import Refusal
from .repository import aggregate, report

WEB = Path(__file__).resolve().parent.parent / "web"
COOKIE = "orchestrator_session"


class Dashboard(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, ledger, port=8768):
        super().__init__(("127.0.0.1", port), Handler)
        self.ledger = ledger
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.bootstrap = secrets.token_urlsafe(32)
        self.sessions = {}
        self.session_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalOrchestrator"

    def log_message(self, *args):
        pass  # No request bodies, cookies, URL fragments or private references in logs.

    def respond(self, status, value, content_type="application/json; charset=utf-8", headers=None):
        data = json.dumps(value, ensure_ascii=False).encode() if content_type.startswith("application/json") else value.encode() if isinstance(value, str) else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, val in (headers or {}).items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(data)

    def host_ok(self):
        return self.headers.get("Host") == urlsplit(self.server.origin).netloc

    def session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            sid = cookie[COOKIE].value if COOKIE in cookie else ""
        except Exception:
            return None
        with self.server.session_lock:
            session = self.server.sessions.get(sid)
            if session and session["expires"] > time.time():
                return session
        return None

    def do_GET(self):
        if not self.host_ok():
            return self.respond(403, {"error": "Host refused"})
        path = urlsplit(self.path).path
        static = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
        if path in static:
            file, mime = static[path]
            return self.respond(200, (WEB / file).read_bytes(), mime)
        session = self.session()
        if not session:
            return self.respond(401, {"error": "Open the private dashboard link from the local session file."})
        try:
            if path == "/api/session":
                return self.respond(200, {"csrf": session["csrf"]})
            if path == "/api/state":
                state = self.server.ledger.snapshot()
                state["summary"] = aggregate(state)
                return self.respond(200, state)
            if path == "/api/export":
                return self.respond(200, report(self.server.ledger.snapshot()), "text/markdown; charset=utf-8", {"Content-Disposition": 'attachment; filename="portfolio-snapshot.md"'})
            if path.startswith("/api/documents/"):
                return self.respond(200, self.server.ledger.document(path.rsplit("/", 1)[1]))
            return self.respond(404, {"error": "Not found"})
        except (Refusal, ValueError) as error:
            return self.respond(400, {"error": str(error)})

    def do_POST(self):
        if not self.host_ok() or self.headers.get("Origin") != self.server.origin:
            return self.respond(403, {"error": "Same-origin request required"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.respond(415, {"error": "JSON required"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 32768:
                return self.respond(413, {"error": "Invalid request size"})
            body = json.loads(self.rfile.read(length))
            if self.path == "/api/login":
                if not isinstance(body, dict) or not isinstance(body.get("token"), str) or not secrets.compare_digest(body["token"], self.server.bootstrap):
                    return self.respond(403, {"error": "Invalid local session token"})
                sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                with self.server.session_lock:
                    self.server.sessions = {key: value for key, value in self.server.sessions.items() if value["expires"] > time.time()}
                    if len(self.server.sessions) >= 32:
                        return self.respond(429, {"error": "Local session limit reached"})
                    self.server.sessions[sid] = {"csrf": csrf, "expires": time.time() + 8 * 3600}
                return self.respond(200, {"csrf": csrf}, headers={"Set-Cookie": f"{COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"})
            session = self.session()
            if not session or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), session["csrf"]):
                return self.respond(403, {"error": "Session and CSRF token required"})
            if self.path == "/api/commands":
                return self.respond(200, self.server.ledger.submit(body))
            return self.respond(404, {"error": "Not found"})
        except Refusal as error:
            return self.respond(409, {"error": str(error)})
        except (ValueError, TypeError, KeyError) as error:
            return self.respond(400, {"error": "Malformed request: " + str(error)})


def serve(ledger, port):
    # File lock prevents separate app instances presenting competing local sessions.
    import fcntl
    lock = open(ledger.root / "dashboard.lock", "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise Refusal("Dashboard already running for this ledger") from error
    server = Dashboard(ledger, port)
    session_file = ledger.root / "dashboard-session.json"
    fd = os.open(session_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"url": server.origin + "/#token=" + server.bootstrap, "pid": os.getpid(), "startedAt": time.time()}, stream)
    print(json.dumps({"dashboard": server.origin, "privateSessionFile": str(session_file)}), flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        lock.close()
