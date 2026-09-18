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
from .inference import ENV_FILE, public_status

WEB = Path(__file__).resolve().parent.parent / "web"
COOKIE = "orchestrator_session"


class Dashboard(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, ledger, port=8768, inference_env=ENV_FILE):
        super().__init__(("127.0.0.1", port), Handler)
        self.ledger = ledger
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.bootstrap = secrets.token_urlsafe(32)
        self.sessions = {}
        self.session_lock = threading.Lock()
        self.observation_lock = threading.Lock()
        self.observation_job = {"status": "idle"}
        self.inference_env = inference_env
        self.inference_lock = threading.Lock()
        self.inference_job = {"status": "idle"}
        self.readiness_lock = threading.Lock()
        self.readiness_job = {"status": "idle"}


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
        static["/observations.js"] = ("observations.js", "text/javascript; charset=utf-8")
        static["/inference.js"] = ("inference.js", "text/javascript; charset=utf-8")
        static["/readiness.js"] = ("readiness.js", "text/javascript; charset=utf-8")
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
                state["observationJob"] = self.server.observation_job.copy()
                state["inference"] = public_status(self.server.ledger, state, self.server.inference_env)
                state["inference"]["job"] = self.server.inference_job.copy()
                from .readiness import diagnose
                state["readiness"] = diagnose(self.server.ledger, state)
                state["readiness"]["job"] = self.server.readiness_job.copy()
                return self.respond(200, state)
            if path == "/api/export":
                return self.respond(200, report(self.server.ledger.snapshot()), "text/markdown; charset=utf-8", {"Content-Disposition": 'attachment; filename="portfolio-snapshot.md"'})
            if path.startswith("/api/documents/"):
                return self.respond(200, self.server.ledger.document(path.rsplit("/", 1)[1]))
            if path.startswith("/api/artifacts/"):
                from .observations import artifact
                identity = path.split("/")[3]
                metadata, raw = artifact(self.server.ledger, identity)
                if path == "/api/artifacts/" + identity + "/download":
                    # Active HTML/SVG/documents never execute in the dashboard origin.
                    return self.respond(200, raw, "application/octet-stream", {"Content-Disposition": 'attachment; filename="artifact-' + identity[:12] + Path(metadata["name"]).suffix + '"'})
                if path != "/api/artifacts/" + identity:
                    return self.respond(404, {"error": "Not found"})
                try:
                    preview = raw.decode("utf-8") if b"\0" not in raw else None
                except UnicodeError:
                    preview = None
                return self.respond(200, {"metadata": metadata, "text": preview[:500000] if preview else None, "truncated": bool(preview and len(preview) > 500000)})
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
            if self.path == "/api/readiness":
                if not isinstance(body, dict) or set(body) != {"operation"} or body["operation"] not in ("inspect", "rehearse"):
                    return self.respond(400, {"error": "Only inspect or rehearse is accepted; no dispatch or native actions"})
                if not self.server.readiness_lock.acquire(blocking=False):
                    return self.respond(409, {"error": "Readiness check already running"})
                self.server.readiness_job = {"status": "running", "operation": body["operation"], "startedAt": time.time()}
                def check_readiness():
                    try:
                        from .readiness import collect
                        from .rehearsal import run
                        (collect if body["operation"] == "inspect" else run)(self.server.ledger)
                        self.server.readiness_job = {"status": "complete", "operation": body["operation"], "finishedAt": time.time()}
                    except Exception:
                        self.server.readiness_job = {"status": "failed", "operation": body["operation"], "error": "Readiness check failed; no controller state was changed.", "finishedAt": time.time()}
                    finally:
                        self.server.readiness_lock.release()
                threading.Thread(target=check_readiness, daemon=True).start()
                return self.respond(202, self.server.readiness_job.copy())
            if self.path == "/api/executive-summary":
                if not isinstance(body, dict) or set(body) != {"force"} or type(body["force"]) is not bool:
                    return self.respond(400, {"error": "Expected only a boolean force flag; prompts and endpoint settings are server-owned"})
                if not self.server.inference_lock.acquire(blocking=False):
                    return self.respond(409, {"error": "Executive brief generation already running"})
                self.server.inference_job = {"status": "running", "startedAt": time.time()}
                def summarize():
                    try:
                        from .inference import generate
                        result = generate(self.server.ledger, self.server.inference_env, body["force"])
                        self.server.inference_job = {"status": result["status"], "finishedAt": time.time()}
                    except Refusal as error:
                        self.server.inference_job = {"status": "failed", "finishedAt": time.time(), "error": str(error)}
                    except Exception:
                        self.server.inference_job = {"status": "failed", "finishedAt": time.time(), "error": "Executive brief failed; previous brief retained. No automatic retry was sent."}
                    finally:
                        self.server.inference_lock.release()
                threading.Thread(target=summarize, daemon=True).start()
                return self.respond(202, self.server.inference_job.copy())
            if self.path == "/api/observe":
                if not isinstance(body, dict) or set(body) != {"remote"} or type(body["remote"]) is not bool:
                    return self.respond(400, {"error": "Expected only a boolean remote flag"})
                if not self.server.observation_lock.acquire(blocking=False):
                    return self.respond(409, {"error": "Observation refresh already running"})
                self.server.observation_job = {"status": "running", "startedAt": time.time(), "remote": body["remote"]}
                def collect():
                    try:
                        from .observations import refresh_observations
                        result = refresh_observations(self.server.ledger, body["remote"])
                        self.server.observation_job = {"status": "complete", "finishedAt": time.time(), "result": result}
                    except Exception as error:
                        self.server.observation_job = {"status": "failed", "finishedAt": time.time(), "error": str(error)[:300]}
                    finally:
                        self.server.observation_lock.release()
                threading.Thread(target=collect, daemon=True).start()
                return self.respond(202, self.server.observation_job.copy())
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
