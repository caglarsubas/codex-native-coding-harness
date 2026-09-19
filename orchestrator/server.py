"""Loopback dashboard with an opt-in, fixed-purpose native brain notification."""
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import parse_qs, urlsplit

from .core import Refusal
from .repository import aggregate, report
from .inference import ENV_FILE, public_status
from .provenance import Provenance
from .activity import BrainActivity
from .notification import BrainNotifier, NOTIFY_KINDS

WEB = Path(__file__).resolve().parent.parent / "web"
COOKIE = "orchestrator_session"


class WorkspaceRuntime:
    """All mutable operational state belongs to one ledger, never to UI selection."""

    def __init__(self, ledger, inference_env=ENV_FILE, runtime_root=WEB.parent, notification_cli=None):
        self.ledger = ledger
        self.registry = None
        self.workspace_id = None
        self.observation_lock = threading.Lock()
        self.observation_job = {"status": "idle"}
        self.inference_env = inference_env
        self.inference_lock = threading.Lock()
        self.inference_job = {"status": "idle"}
        self.readiness_lock = threading.Lock()
        self.readiness_job = {"status": "idle"}
        self.provenance = Provenance(runtime_root)
        self.provenance_lock = threading.Lock()
        self.provenance_job = {"status": "idle"}
        self.brain_activity = BrainActivity(ledger)
        self.notifier = BrainNotifier(ledger, notification_cli)
        from .assistant_actions import ActionProposals
        self.assistant_proposals = ActionProposals()
        self.run_readiness_report = None
        self.run_readiness_lock = threading.Lock()

    def snapshot(self):
        """Same evidence for workspace and assistant; no model-triggered scans or refresh."""
        state = self.ledger.snapshot()
        state["summary"] = aggregate(state)
        state["observationJob"] = self.observation_job.copy()
        state["inference"] = public_status(self.ledger, state, self.inference_env)
        state["inference"]["job"] = self.inference_job.copy()
        from .readiness import diagnose
        state["readiness"] = diagnose(self.ledger, state)
        state["readiness"]["job"] = self.readiness_job.copy()
        state["provenance"] = self.provenance.snapshot()
        state["provenance"]["job"] = self.provenance_job.copy()
        state["brainActivity"] = self.brain_activity.snapshot(state)
        state["brainNotification"] = self.notifier.status(state["meta"]["brainId"])
        from .run_readiness import assistant_summary
        state["runReadiness"] = assistant_summary(self.run_readiness_report)
        if self.registry:
            state["workspace"] = {"id": self.workspace_id,
                "name": next(w["name"] for w in self.registry.list() if w["id"] == self.workspace_id),
                "projectProfile": self.registry.profile(self.workspace_id)}
        return state

    def submit_control(self, body, actor="dashboard"):
        command = self.ledger.submit(body, actor=actor)
        return self.notify_control(command)

    def notify_control(self, command):
        if command["kind"] in NOTIFY_KINDS:
            return self.notifier.notify(command["id"])
        return command


class Dashboard(ThreadingHTTPServer, WorkspaceRuntime):
    daemon_threads = True

    def __init__(self, ledger, port=8768, inference_env=ENV_FILE, runtime_root=WEB.parent,
                 notification_cli=None, registry=None):
        ThreadingHTTPServer.__init__(self, ("127.0.0.1", port), Handler)
        WorkspaceRuntime.__init__(self, ledger, inference_env, runtime_root, notification_cli)
        self.registry = registry
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.bootstrap = secrets.token_urlsafe(32)
        self.sessions = {}
        self.session_lock = threading.Lock()
        self.runtime_lock = threading.Lock()
        self.runtimes = {}
        self.runtime_options = (inference_env, runtime_root, notification_cli)
        # One configured inference tenancy: serialize explicit calls across workspaces.
        self.shared_inference_lock = self.inference_lock
        self.served_workspaces = {w["id"] for w in registry.list()} if registry else set()

    def runtime_for(self, workspace_id):
        if not self.registry or workspace_id not in self.served_workspaces:
            raise Refusal("Unknown workspace; restart the dashboard after registration")
        self.registry.root_for(workspace_id)  # Revalidate even cached runtime identities.
        with self.runtime_lock:
            if workspace_id not in self.runtimes:
                runtime = WorkspaceRuntime(self.registry.ledger(workspace_id), *self.runtime_options)
                runtime.registry, runtime.workspace_id = self.registry, workspace_id
                runtime.inference_lock = self.shared_inference_lock
                self.runtimes[workspace_id] = runtime
            return self.runtimes[workspace_id]


def scoped_csrf(session, workspace_id):
    if workspace_id is None:
        return session["csrf"]
    return hmac.new(session["csrf"].encode(), workspace_id.encode(), hashlib.sha256).hexdigest()


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

    def route(self, path):
        if path.startswith("/api/workspaces/"):
            parts = path.split("/", 4)
            if len(parts) != 5 or not parts[4]:
                raise Refusal("Workspace endpoint required")
            from .workspaces import identity
            return self.server.runtime_for(identity(parts[3])), "/api/" + parts[4], parts[3]
        if self.server.registry:
            raise Refusal("Select an explicit workspace for this operation")
        return self.server, path, None

    def do_GET(self):
        if not self.host_ok():
            return self.respond(403, {"error": "Host refused"})
        path = urlsplit(self.path).path
        static = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
        static["/observations.js"] = ("observations.js", "text/javascript; charset=utf-8")
        static["/inference.js"] = ("inference.js", "text/javascript; charset=utf-8")
        static["/readiness.js"] = ("readiness.js", "text/javascript; charset=utf-8")
        static["/provenance.js"] = ("provenance.js", "text/javascript; charset=utf-8")
        static["/activity.js"] = ("activity.js", "text/javascript; charset=utf-8")
        static["/decisions.js"] = ("decisions.js", "text/javascript; charset=utf-8")
        static["/decisions.css"] = ("decisions.css", "text/css; charset=utf-8")
        for file in ("panes.js", "assistant.js", "routing.js", "workspaces.js", "missions.js", "workspace-pause.js", "run-readiness.js", "panes.css"):
            static["/" + file] = (file, "text/javascript; charset=utf-8" if file.endswith(".js") else "text/css; charset=utf-8")
        if path in static:
            file, mime = static[path]
            return self.respond(200, (WEB / file).read_bytes(), mime)
        session = self.session()
        if not session:
            return self.respond(401, {"error": "Open the private dashboard link from the local session file."})
        try:
            if path == "/api/session":
                return self.respond(200, {"csrf": session["csrf"]})
            if path == "/api/workspaces":
                return self.respond(200, {"enabled": self.server.registry is not None,
                    "workspaces": [w for w in self.server.registry.list() if w["id"] in self.server.served_workspaces]
                        if self.server.registry else []})
            if path == "/api/workspaces/summary" and self.server.registry:
                return self.respond(200, self.server.registry.summary(self.server.served_workspaces))
            runtime, path, workspace_id = self.route(path)
            if path == "/api/session":
                return self.respond(200, {"csrf": scoped_csrf(session, workspace_id), "workspaceId": workspace_id})
            if path == "/api/profile" and workspace_id:
                return self.respond(200, self.server.registry.profile(workspace_id))
            if path == "/api/mission" and workspace_id:
                from .missions import read
                return self.respond(200, read(runtime.ledger))
            if path == "/api/run-readiness" and workspace_id:
                from .run_readiness import inspect
                if not runtime.run_readiness_lock.acquire(blocking=False):
                    return self.respond(409, {"error": "Run inspection is already in progress for this workspace."})
                try:
                    runtime.run_readiness_report = inspect(self.server.registry, runtime.ledger)
                    return self.respond(200, runtime.run_readiness_report)
                finally:
                    runtime.run_readiness_lock.release()
            if path == "/api/assistant/context":
                from .assistant import context
                query = parse_qs(urlsplit(self.path).query)
                if set(query) - {"view"} or len(query.get("view", ["overview"])) != 1:
                    return self.respond(400, {"error": "Expected one dashboard view"})
                data, _ = context(runtime.snapshot(), query.get("view", ["overview"])[0])
                return self.respond(200, data)
            if path == "/api/state":
                return self.respond(200, runtime.snapshot())
            if path == "/api/export":
                return self.respond(200, report(runtime.ledger.snapshot()), "text/markdown; charset=utf-8", {"Content-Disposition": 'attachment; filename="portfolio-snapshot.md"'})
            if path.startswith("/api/documents/"):
                return self.respond(200, runtime.ledger.document(path.rsplit("/", 1)[1]))
            if path.startswith("/api/artifacts/"):
                from .observations import artifact
                identity = path.split("/")[3]
                metadata, raw = artifact(runtime.ledger, identity)
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
            if not session:
                return self.respond(403, {"error": "Session and CSRF token required"})
            runtime, path, workspace_id = self.route(urlsplit(self.path).path)
            csrf = scoped_csrf(session, workspace_id)
            if not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), csrf):
                return self.respond(403, {"error": "Workspace session and CSRF token required"})
            if path == "/api/profile" and workspace_id:
                if not isinstance(body, dict) or set(body) != {"profile", "expectedVersion"}:
                    raise Refusal("Expected profile and version")
                return self.respond(200, self.server.registry.save_profile(workspace_id, body["profile"], body["expectedVersion"]))
            if path == "/api/commands":
                return self.respond(200, runtime.submit_control(body))
            if path == "/api/mission" and workspace_id:
                from .missions import change
                return self.respond(200, change(runtime.ledger, body))
            if path == "/api/assistant/confirm":
                command, first = runtime.assistant_proposals.confirm(runtime.ledger, body, csrf)
                if first:
                    command = runtime.notify_control(command)
                return self.respond(200, command)
            if path == "/api/assistant":
                from .assistant import chat
                if not runtime.inference_lock.acquire(blocking=False):
                    return self.respond(409, {"error": "Inference service is busy; no automatic retry was sent"})
                try:
                    return self.respond(200, chat(runtime.ledger, body, runtime.inference_env,
                        runtime.snapshot, runtime.assistant_proposals, csrf))
                except Refusal as error:
                    return self.respond(409, {"error": str(error)})
                except Exception:
                    return self.respond(502, {"error": "Assistant request failed. No automatic retry was sent; no dashboard controls were changed."})
                finally:
                    runtime.inference_lock.release()
            if path == "/api/provenance":
                if not isinstance(body, dict) or set(body) != {"remote"} or type(body["remote"]) is not bool:
                    return self.respond(400, {"error": "Expected only a boolean remote flag; no paths or process controls"})
                if not runtime.provenance_lock.acquire(blocking=False):
                    return self.respond(409, {"error": "Runtime inspection already running"})
                runtime.provenance_job = {"status": "running", "startedAt": time.time()}
                def inspect_runtime():
                    try:
                        runtime.provenance.refresh(body["remote"])
                        runtime.provenance_job = {"status": "complete", "finishedAt": time.time()}
                    except Exception:
                        runtime.provenance_job = {"status": "failed", "error": "Runtime inspection failed; no process or controller action was performed."}
                    finally:
                        runtime.provenance_lock.release()
                threading.Thread(target=inspect_runtime, daemon=True).start()
                return self.respond(202, runtime.provenance_job.copy())
            if path == "/api/readiness":
                if not isinstance(body, dict) or set(body) != {"operation"} or body["operation"] not in ("inspect", "rehearse"):
                    return self.respond(400, {"error": "Only inspect or rehearse is accepted; no dispatch or native actions"})
                if not runtime.readiness_lock.acquire(blocking=False):
                    return self.respond(409, {"error": "Readiness check already running"})
                runtime.readiness_job = {"status": "running", "operation": body["operation"], "startedAt": time.time()}
                def check_readiness():
                    try:
                        from .readiness import collect
                        from .rehearsal import run
                        (collect if body["operation"] == "inspect" else run)(runtime.ledger)
                        runtime.readiness_job = {"status": "complete", "operation": body["operation"], "finishedAt": time.time()}
                    except Exception:
                        runtime.readiness_job = {"status": "failed", "operation": body["operation"], "error": "Readiness check failed; no controller state was changed.", "finishedAt": time.time()}
                    finally:
                        runtime.readiness_lock.release()
                threading.Thread(target=check_readiness, daemon=True).start()
                return self.respond(202, runtime.readiness_job.copy())
            if path == "/api/executive-summary":
                if not isinstance(body, dict) or set(body) != {"force"} or type(body["force"]) is not bool:
                    return self.respond(400, {"error": "Expected only a boolean force flag; prompts and endpoint settings are server-owned"})
                if not runtime.inference_lock.acquire(blocking=False):
                    return self.respond(409, {"error": "Executive brief generation already running"})
                runtime.inference_job = {"status": "running", "startedAt": time.time()}
                def summarize():
                    try:
                        from .inference import generate
                        result = generate(runtime.ledger, runtime.inference_env, body["force"])
                        runtime.inference_job = {"status": result["status"], "finishedAt": time.time()}
                    except Refusal as error:
                        runtime.inference_job = {"status": "failed", "finishedAt": time.time(), "error": str(error)}
                    except Exception:
                        runtime.inference_job = {"status": "failed", "finishedAt": time.time(), "error": "Executive brief failed; previous brief retained. No automatic retry was sent."}
                    finally:
                        runtime.inference_lock.release()
                threading.Thread(target=summarize, daemon=True).start()
                return self.respond(202, runtime.inference_job.copy())
            if path == "/api/observe":
                if not isinstance(body, dict) or set(body) != {"remote"} or type(body["remote"]) is not bool:
                    return self.respond(400, {"error": "Expected only a boolean remote flag"})
                if not runtime.observation_lock.acquire(blocking=False):
                    return self.respond(409, {"error": "Observation refresh already running"})
                runtime.observation_job = {"status": "running", "startedAt": time.time(), "remote": body["remote"]}
                def collect():
                    try:
                        from .observations import refresh_observations
                        result = refresh_observations(runtime.ledger, body["remote"])
                        runtime.observation_job = {"status": "complete", "finishedAt": time.time(), "result": result}
                    except Exception as error:
                        runtime.observation_job = {"status": "failed", "finishedAt": time.time(), "error": str(error)[:300]}
                    finally:
                        runtime.observation_lock.release()
                threading.Thread(target=collect, daemon=True).start()
                return self.respond(202, runtime.observation_job.copy())
            return self.respond(404, {"error": "Not found"})
        except Refusal as error:
            return self.respond(409, {"error": str(error)})
        except (ValueError, TypeError, KeyError) as error:
            return self.respond(400, {"error": "Malformed request: " + str(error)})


def serve(ledger, port, notification_cli=None, registry=None):
    # Every registered ledger has a single dashboard owner. New registrations
    # become served only after a restart and lock acquisition, never on a GET.
    import fcntl
    from contextlib import ExitStack
    registered = registry.list() if registry else []
    roots = [registry.root_for(w["id"]) for w in registered] if registry else [ledger.root]
    if not roots:
        raise Refusal("Register at least one workspace before serving")
    with ExitStack() as stack:
        for root in sorted(roots):
            lock = stack.enter_context(open(root / "dashboard.lock", "a"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise Refusal("Dashboard already running for a registered ledger") from error
        server = Dashboard(ledger, port, notification_cli=notification_cli, registry=registry)
        # Freeze the exact locked set, including a registration that races startup.
        if registry:
            server.served_workspaces = {w["id"] for w in registered}
        session_file = (registry.root if registry else ledger.root) / "dashboard-session.json"
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
