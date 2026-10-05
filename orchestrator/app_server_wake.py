"""Opt-in, one-shot wake of a bound standard-project brain on an owned app-server.

This is an event-driven notification transport, not a scheduler or a Codex tool
client. A committed ledger claim precedes every call into this module. The socket
and exact brain checkout are private operator configuration, never browser input.
"""
import copy
import os
from pathlib import Path
import re
import secrets
import selectors
import stat
import threading
import time

from .core import Refusal, canonical, digest, require
from .native_read_client import ReadProxy, decode, file_identity, secure_path, socket_identity, validate_endpoint
from .projects import text as catalog_text

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
MAX_BINDING = 16_384
MAX_APPROVAL = 16_000
APPROVAL_SECONDS = 600
APPROVAL_METHODS = {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}
# The owned observer must see native approval requests on its retained socket.
# A resume can otherwise inherit danger-full-access/never and let an escalated
# command finish without an app-server prompt. The exact restricted policy is
# owner-pinned in the private binding and reapplied before every owned turn.
NATIVE_APPROVAL_POLICY = {"sandbox": "workspace-write", "approvalPolicy": "on-request",
                          "codeMode": False}
COMMAND_FIELDS = {"threadId", "turnId", "itemId", "reason", "command", "cwd",
                  "commandActions", "proposedExecpolicyAmendment", "networkApprovalContext",
                  "availableDecisions", "additionalPermissions", "kind", "startedAtMs",
                  "environmentId", "approvalId", "proposedNetworkPolicyAmendments"}
FILE_FIELDS = {"threadId", "turnId", "itemId", "reason", "grantRoot", "startedAtMs"}
THREAD_EVENT_LIMIT = 128
THREAD_STREAM_GAP = "owned_stream_not_exhaustive"


class WakeProxy(ReadProxy):
    """Fixed-purpose write client with bounded event streaming for a full turn."""
    request_limit = 16_384
    total_limit = 128_000_000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._frame_lock = threading.Lock()
        self._write_deadline = threading.local()

    def _ready(self, stream, event):
        if event != selectors.EVENT_WRITE or not hasattr(self._write_deadline, "value"):
            return super()._ready(stream, event)
        remaining = self._write_deadline.value - time.monotonic()
        require(remaining > 0, "Native approval write deadline exceeded")
        with selectors.DefaultSelector() as selector:
            selector.register(stream, event)
            require(selector.select(remaining), "Native approval write deadline exceeded")

    def _send_frame(self, opcode, payload):
        # A WebSocket ping may race the owner's decision. Never interleave two
        # masked frames on the same nonblocking stdin pipe.
        with self._frame_lock:
            self._write_deadline.value = time.monotonic() + 2
            try:
                return super()._send_frame(opcode, payload)
            finally:
                del self._write_deadline.value

    def _rpc(self, method, params):
        self._awaiting_start = method == "turn/start"
        try:
            return super()._rpc(method, params)
        finally:
            self._awaiting_start = False

    def _line(self):
        row = super()._line()
        if isinstance(row, dict) and row.get("method") == "thread/started":
            callback = getattr(self, "_on_thread_started", None)
            if callback is not None:
                try:
                    callback(row)
                except Exception:
                    # The native turn must not be retried because an observer
                    # could not persist an event. Keep an explicit coverage gap.
                    self._thread_event_error = True
        # A short turn can finish before turn/start returns its response. Keep
        # only the lifecycle fact while the parent RPC drops notifications.
        if getattr(self, "_awaiting_start", False) and isinstance(row, dict) and row.get("method") == "turn/completed":
            params = row.get("params")
            turn = params.get("turn") if isinstance(params, dict) else None
            if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                self._early_completion = (params.get("threadId"), turn["id"], turn.get("status"))
        if getattr(self, "_awaiting_start", False) and isinstance(row, dict) and "id" in row and isinstance(row.get("method"), str):
            # A prompt can race the turn/start reply. The read-only base RPC
            # rejects server requests; retain this one for the turn observer.
            early = getattr(self, "_early_requests", None)
            if early is None:
                early = self._early_requests = []
            require(len(early) < 16 and len(canonical(row).encode("utf-8")) <= MAX_APPROVAL,
                    "Early native request exceeds its bound")
            early.append(row)
            return {"method": "wake/earlyServerRequest", "params": {}}
        return row


def load_binding(path):
    """Read only a private, exact operator binding; never discover a socket."""
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path, "Canonical private brain binding required")
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
            info.st_nlink == 1 and not info.st_mode & 0o077 and info.st_size <= MAX_BINDING,
            "Private brain binding permissions or size are unsafe")
    with path.open("rb") as stream:
        require(file_identity(os.fstat(stream.fileno())) == file_identity(info), "Brain binding changed")
        value = decode(stream.read(MAX_BINDING + 1))
        require(file_identity(os.fstat(stream.fileno())) == file_identity(info) ==
                file_identity(path.lstat()),
                "Brain binding changed")
    require(isinstance(value, dict) and set(value) == {"endpoint", "brains"}, "Invalid brain binding")
    require(isinstance(value["brains"], dict) and 0 < len(value["brains"]) <= 32,
            "Invalid brain inventory")
    # This performs the same executable, socket and server-identity pin checks
    # used by the read-only native observer. It does not connect or start Codex.
    validate_endpoint(value["endpoint"])
    for brain, record in value["brains"].items():
        require(isinstance(brain, str) and UUID.fullmatch(brain) and
                isinstance(record, dict) and
                set(record) in ({"cwd", "projectId", "workspaceId", "nativePolicy"},
                                {"cwd", "projectId", "catalogProjectId", "workspaceId", "nativePolicy"}) and
                isinstance(record["projectId"], str) and UUID.fullmatch(record["projectId"]),
                "Invalid brain binding entry")
        policy = record["nativePolicy"]
        require(isinstance(policy, dict) and set(policy) == set(NATIVE_APPROVAL_POLICY) and
                policy["sandbox"] == "workspace-write" and
                policy["approvalPolicy"] == "on-request" and
                type(policy["codeMode"]) is bool and not policy["codeMode"],
                "Owned brain requires an exact reviewed native approval policy")
        # The Codex app's list_projects ID can differ from the app-server's
        # project ID. Both must be explicit; neither substitutes for the other.
        if "catalogProjectId" in record:
            catalog_text(record["catalogProjectId"])
        require(isinstance(record["workspaceId"], str) and
                re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", record["workspaceId"]),
                "Invalid bound workspace")
        cwd = record["cwd"]
        require(isinstance(cwd, str) and len(cwd) <= 4096 and Path(cwd).is_absolute(),
                "Bound brain checkout is unavailable or changed")
        try:
            valid_cwd = str(Path(cwd).resolve(strict=True)) == cwd and Path(cwd).is_dir()
        except OSError:
            valid_cwd = False
        require(valid_cwd, "Bound brain checkout is unavailable or changed")
    return value


class AppServerWake:
    def __init__(self, binding, ledger):
        self.binding = binding
        self.ledger = ledger
        self._lock = threading.Lock()
        self._subscriptions = set()
        self._pending_approvals = {}
        self._closed = False
        self._connection_lock = threading.Lock()
        self._connection = {}

    def connection_status(self, brain_id):
        """Cached handshake fact only. State polling never opens a connection."""
        with self._lock:
            observed = copy.deepcopy(self._connection.get(brain_id))
        if observed is None:
            return {"status": "unchecked", "checkedAt": None,
                    "detail": "Host connection has not been checked. A socket file is not a running host."}
        if time.time() - observed["checkedAt"] > 30:
            observed["status"] = "stale"
            observed["detail"] = "Last connection check is out of date. Check again; no request will be replayed."
        return observed

    def check_connection(self, brain_id):
        """Explicit, bounded initialize-only diagnostic. No task RPC or ledger write."""
        require(self._connection_lock.acquire(blocking=False), "Host connection check is already in progress")
        try:
            status, detail = "unavailable", "Reviewed host binding is unavailable or changed. No replacement was selected."
            if not self._closed and self.configured(brain_id):
                try:
                    with ReadProxy(self.binding["endpoint"], timeout=5):
                        pass  # Only upgrade, initialize and initialized; never resume/read a task.
                    validate_endpoint(self.binding["endpoint"])
                    require(self.configured(brain_id), "Reviewed endpoint changed")
                    with self._lock:
                        require(not self._closed, "Owned connection was closed during its check")
                    status, detail = "connected", "Reviewed host answered its identity handshake. This does not prove brain activity, tools or phase readiness."
                except (Refusal, OSError, ValueError):
                    status, detail = "disconnected", "Cannot connect to the reviewed host. The dashboard is still available; repair the host, then check again. No request was replayed."
            observed = {"status": status, "checkedAt": time.time(), "detail": detail}
            with self._lock:
                self._connection[brain_id] = observed
            return copy.deepcopy(observed)
        finally:
            self._connection_lock.release()

    def close(self):
        """Dashboard shutdown drops owned subscriptions, never retries turns."""
        with self._lock:
            self._closed = True
            subscriptions = tuple(self._subscriptions)
            self._subscriptions.clear()
            pending = tuple(self._pending_approvals.values())
            self._pending_approvals.clear()
            for request in pending:
                request["cancelled"] = True
                request["event"].set()
        for proxy in subscriptions:
            proxy.__exit__(None, None, None)

    def pending_approval(self, brain_id):
        """Exact, transient owner-only prompt. Never persist or send to inference."""
        with self._lock:
            pending = self._pending_approvals.get(brain_id)
            if pending is None or pending["cancelled"] or pending["decision"] is not None or time.time() >= pending["projection"]["expiresAt"]:
                return None
            projection = copy.deepcopy(pending["projection"])
        # UI state is advisory. Never advertise acceptance for an incomplete
        # prompt or after a phase stop, even if Codex offers the raw choice.
        if not projection["canAccept"] or not self._phase_allows_accept(brain_id):
            projection["canAccept"] = False
            projection["allowedDecisions"] = [choice for choice in projection["allowedDecisions"] if choice != "accept"]
        return projection

    def _phase_allows_accept(self, brain_id):
        if self.ledger is None:
            return False
        try:
            from . import standard
            from .brain_control import stopped
            with self.ledger.tx() as db:
                meta = self.ledger.get(db, "meta", 1)
                run = meta.get("standardRun")
                return (meta.get("brainId") == brain_id and not stopped(meta) and
                        isinstance(run, dict) and run.get("protocol") == standard.PROTOCOL and
                        run.get("status") == "running" and
                        not standard.current_blockers(self.ledger, db, run))
        except Exception:
            return False

    def confirm_approval(self, brain_id, command_id, request_hash, decision):
        """Queue one exact owner decision for the existing observer connection.

        This is not a native delivery receipt. The caller must separately bind an
        authenticated, signed preview to the projection before calling it.
        """
        require(decision in ("accept", "decline", "cancel"), "Unsupported native approval decision")
        with self._lock:
            pending = self._pending_approvals.get(brain_id)
            require(not self._closed and pending is not None and not pending["cancelled"] and
                    pending["decision"] is None, "Native approval is no longer pending")
            projection = pending["projection"]
            require(projection["commandId"] == command_id and projection["requestHash"] == request_hash and
                    time.time() < projection["expiresAt"], "Native approval preview is stale")
            require(decision in projection["allowedDecisions"],
                    "Native request does not offer that decision")
            require(decision != "accept" or projection["canAccept"],
                    "Native request lacks complete approval evidence; only decline or cancel is available")
            pending["decision"] = decision
            pending["event"].set()
        return {"status": "queued", "detail": "Owner decision queued on the exact native request; delivery is not yet confirmed."}

    @staticmethod
    def _complete_approval(row, brain_id, turn_id, item):
        """Keep unrecognized or incomplete prompt shapes decline-only."""
        params = row.get("params")
        method = row.get("method")
        if not isinstance(params, dict) or params.get("threadId") != brain_id or params.get("turnId") != turn_id:
            return False
        item_id = params.get("itemId")
        if not isinstance(item_id, str) or not 0 < len(item_id) <= 128:
            return False
        if method == "item/commandExecution/requestApproval":
            if (not set(params) <= COMMAND_FIELDS or params.get("kind", "command") != "command" or
                    type(params.get("startedAtMs")) is not int or params["startedAtMs"] < 0 or
                    (params.get("environmentId") is not None and
                     (not isinstance(params["environmentId"], str) or
                      not 0 < len(params["environmentId"]) <= 128)) or
                    any(params.get(key) is not None for key in
                        ("additionalPermissions", "networkApprovalContext",
                         "proposedNetworkPolicyAmendments", "approvalId"))):
                return False
            # A suggested persistent exec-policy rule may accompany a
            # one-command approval. Keep it visible to the owner, but only
            # ever send the plain `accept` decision; never the amendment.
            amendment = params.get("proposedExecpolicyAmendment")
            if amendment is not None and (not isinstance(amendment, list) or len(amendment) > 16 or
                                          any(not isinstance(part, str) or not 0 < len(part) <= 4096
                                              for part in amendment)):
                return False
            command = params.get("command")
            cwd = params.get("cwd")
            if not isinstance(command, str) or not command.strip() or not isinstance(cwd, str) or not Path(cwd).is_absolute():
                if not isinstance(item, dict) or item.get("type") != "commandExecution" or item.get("id") != item_id:
                    return False
                command = item.get("command")
                cwd = item.get("cwd")
            if (not isinstance(command, str) or not command.strip() or
                    not isinstance(cwd, str) or not Path(cwd).is_absolute() or
                    os.path.normpath(cwd) != cwd):
                return False
            if isinstance(item, dict) and item.get("id") == item_id and item.get("type") == "commandExecution" and (
                    item.get("command") != command or item.get("cwd") != cwd):
                return False
            actions = params.get("commandActions")
            if actions is not None and not isinstance(actions, list):
                return False
            available = params.get("availableDecisions")
            return available is None or isinstance(available, list) and "accept" in available
        if method == "item/fileChange/requestApproval":
            if (not set(params) <= FILE_FIELDS or type(params.get("startedAtMs")) is not int or
                    params["startedAtMs"] < 0 or params.get("grantRoot") is not None or
                    not isinstance(item, dict) or item.get("id") != item_id or item.get("type") != "fileChange"):
                return False
            changes = item.get("changes")
            return (isinstance(changes, list) and bool(changes) and len(changes) <= 100 and
                    all(isinstance(change, dict) and set(change) == {"path", "kind", "diff"} and
                        all(isinstance(change[key], str) and change[key] for key in ("path", "kind", "diff"))
                        and Path(change["path"]).is_absolute() and
                        os.path.normpath(change["path"]) == change["path"]
                        for change in changes))
        return False

    def _within_bound_checkout(self, row, brain_id, item):
        """Approval never extends a brain to another checkout or source root."""
        try:
            recorded = Path(self.binding["brains"][brain_id]["cwd"])
            root = recorded.resolve(strict=True)
            if root != recorded or not root.is_dir():
                return False
            params = row["params"]
            if row["method"] == "item/commandExecution/requestApproval":
                cwd = params.get("cwd") or (item or {}).get("cwd")
                if not isinstance(cwd, str) or os.path.normpath(cwd) != cwd:
                    return False
                target = Path(cwd).resolve(strict=True)
                return target.is_dir() and (target == root or root in target.parents)
            if row["method"] == "item/fileChange/requestApproval":
                for change in item["changes"]:
                    path = Path(change["path"])
                    if path.is_symlink():
                        return False
                    parent = path.parent.resolve(strict=True)
                    if not (parent == root or root in parent.parents):
                        return False
                    if path.exists():
                        target = path.resolve(strict=True)
                        if not (target == root or root in target.parents):
                            return False
                return True
        except (OSError, KeyError, TypeError, ValueError):
            return False
        return False

    def _record_approval_status(self, command_id, brain_id, turn_id, request_hash, status):
        """Advance only the matching hash-only owner claim; never store a prompt."""
        prior = {
            "response_written": {"claimed", "queued"},
            "resolved": {"response_written"},
            "resolved_without_response": {"claimed", "queued"},
            "blocked": {"claimed", "queued"},
            "uncertain": {"claimed", "queued", "response_written"},
        }
        if self.ledger is None or status not in prior:
            return
        try:
            with self.ledger.tx() as db:
                command = self.ledger.get(db, "commands", command_id)
                note = command.get("notification") or {}
                if note.get("brainId") != brain_id or note.get("nativeTurnId") != turn_id:
                    return
                entries = note.get("nativeApprovals")
                if not isinstance(entries, list):
                    return
                for entry in entries:
                    if (isinstance(entry, dict) and entry.get("requestHash") == request_hash and
                            entry.get("turnId") == turn_id and entry.get("status") in prior[status]):
                        entry["status"] = status
                        entry["observedAt"] = time.time()
                        note["nativeApprovals"] = entries
                        command["notification"] = note
                        self.ledger.put(db, "commands", command_id, command)
                        self.ledger.event(db, "native_permission_status", {"commandId": command_id,
                                          "requestHash": request_hash, "status": status})
                        return
        except Exception:
            # A missing receipt observation never authorizes a second native
            # response. The original one-shot decision claim remains durable.
            return

    def _offer_approval(self, proxy, row, command_id, brain_id, turn_id, item):
        """Read native resolution while waiting for an exact owner choice."""
        params = row.get("params")
        request_id = row.get("id")
        require(type(request_id) in (int, str) and not (isinstance(request_id, str) and
                not 0 < len(request_id) <= 128) and isinstance(params, dict) and
                params.get("threadId") == brain_id and params.get("turnId") == turn_id,
                "Native approval scope is unknown")
        raw = canonical(row)
        require(len(raw.encode("utf-8")) <= MAX_APPROVAL, "Native approval exceeds its bound")
        observed = time.time()
        available = params.get("availableDecisions") if row["method"] == "item/commandExecution/requestApproval" else None
        require(available is None or isinstance(available, list) and len(available) <= 16,
                "Invalid native decision inventory")
        allowed = [decision for decision in ("accept", "decline", "cancel")
                   if available is None or decision in available]
        require(allowed, "Native request has no supported owner decision")
        projection = {"commandId": command_id, "brainId": brain_id, "turnId": turn_id,
                      "itemId": params.get("itemId"), "requestId": request_id,
                      "method": row["method"], "observedAt": observed,
                      "expiresAt": observed + APPROVAL_SECONDS,
                      "canAccept": ("accept" in allowed and
                                    self._complete_approval(row, brain_id, turn_id, item) and
                                    self._within_bound_checkout(row, brain_id, item)),
                      "allowedDecisions": allowed,
                      "request": copy.deepcopy(params)}
        if item is not None:
            projection["item"] = copy.deepcopy(item)
        require(len(canonical(projection).encode("utf-8")) <= MAX_APPROVAL,
                "Native approval context exceeds its bound")
        projection["requestHash"] = digest({"nonce": secrets.token_hex(16), "projection": projection})
        request_hash = projection["requestHash"]
        pending = {"projection": projection, "decision": None, "cancelled": False,
                   "event": threading.Event(), "rows": [], "readerError": False}
        with self._lock:
            require(not self._closed and brain_id not in self._pending_approvals,
                    "Another native approval is unresolved")
            self._pending_approvals[brain_id] = pending

        def read_while_pending():
            try:
                while True:
                    next_row = proxy._line()
                    with self._lock:
                        if pending["cancelled"]:
                            break
                        if len(pending["rows"]) >= 64:
                            pending["readerError"] = True
                            pending["event"].set()
                            break
                        pending["rows"].append(next_row)
                        pending["event"].set()
                    if (isinstance(next_row, dict) and
                        (next_row.get("method") in ("serverRequest/resolved", "turn/completed") or
                         "id" in next_row and isinstance(next_row.get("method"), str))):
                        break
            except Exception:
                with self._lock:
                    pending["readerError"] = True
                    pending["event"].set()

        reader = threading.Thread(target=read_while_pending, daemon=True,
                                  name="codex-brain-native-approval-reader")
        reader.start()
        try:
            response_sent = False
            decision = None
            while time.time() < projection["expiresAt"]:
                pending["event"].wait(max(0, projection["expiresAt"] - time.time()))
                with self._lock:
                    rows, pending["rows"] = pending["rows"], []
                    error = pending["readerError"] or pending["cancelled"]
                    decision = pending["decision"]
                    pending["event"].clear()
                if error:
                    if decision is not None:
                        self._record_approval_status(command_id, brain_id, turn_id, request_hash, "uncertain")
                    return "native_approval_response_uncertain" if response_sent else "native_attention_required"
                # Native resolution takes precedence over a concurrent owner
                # click; a resolved or finished request can never be approved.
                for next_row in rows:
                    require(isinstance(next_row, dict), "Invalid native approval event")
                    method, event_params = next_row.get("method"), next_row.get("params")
                    if method == "serverRequest/resolved":
                        if isinstance(event_params, dict) and event_params.get("threadId") == brain_id and event_params.get("requestId") == request_id:
                            self._record_approval_status(command_id, brain_id, turn_id, request_hash,
                                                         "resolved" if response_sent else "resolved_without_response")
                            return "resolved" if response_sent else "native_attention_required"
                        if decision is not None:
                            self._record_approval_status(command_id, brain_id, turn_id, request_hash, "uncertain")
                        return "native_attention_required"
                    if method == "turn/completed":
                        if isinstance(event_params, dict) and event_params.get("threadId") == brain_id:
                            turn = event_params.get("turn")
                            if isinstance(turn, dict) and turn.get("id") == turn_id:
                                if decision is not None:
                                    self._record_approval_status(command_id, brain_id, turn_id, request_hash,
                                                                 "uncertain" if response_sent else "resolved_without_response")
                                value = turn.get("status")
                                return value if value in ("completed", "failed", "interrupted") else "unconfirmed"
                        if decision is not None:
                            self._record_approval_status(command_id, brain_id, turn_id, request_hash, "uncertain")
                        return "native_attention_required"
                    if "id" in next_row and isinstance(method, str):
                        if decision is not None:
                            self._record_approval_status(command_id, brain_id, turn_id, request_hash, "uncertain")
                        return "native_attention_required"
                if decision is not None and not response_sent:
                    if time.time() >= projection["expiresAt"]:
                        self._record_approval_status(command_id, brain_id, turn_id, request_hash, "blocked")
                        return "native_attention_required"
                    # The observer alone writes on this same retained socket.
                    # A pipe write is not native approval resolution.
                    response = {"id": request_id, "result": {"decision": decision}}
                    if decision == "accept":
                        sent = self._write_accept_if_current(proxy, response, command_id,
                                                             brain_id, turn_id, projection["requestHash"])
                        if sent is None:
                            self._record_approval_status(command_id, brain_id, turn_id, request_hash, "uncertain")
                            return "native_approval_response_uncertain"
                        if not sent:
                            self._record_approval_status(command_id, brain_id, turn_id, request_hash, "blocked")
                            return "native_attention_required"
                    else:
                        try:
                            proxy._write(response)
                        except (OSError, Refusal, ValueError, RuntimeError):
                            self._record_approval_status(command_id, brain_id, turn_id, request_hash, "uncertain")
                            return "native_approval_response_uncertain"
                    response_sent = True
                    self._record_approval_status(command_id, brain_id, turn_id, request_hash, "response_written")
            if decision is not None:
                self._record_approval_status(command_id, brain_id, turn_id, request_hash,
                                             "uncertain" if response_sent else "blocked")
            return "native_approval_response_uncertain" if response_sent else "native_attention_required"
        finally:
            with self._lock:
                if self._pending_approvals.get(brain_id) is pending:
                    del self._pending_approvals[brain_id]
                pending["cancelled"] = True
                pending["event"].set()
            # On any non-resolution path, the enclosing observer closes the
            # subscription; the reader then exits without a second RPC.
            if reader.is_alive() and not response_sent:
                proxy.__exit__(None, None, None)
            reader.join(timeout=0.5)

    def _accept_authorized_in_db(self, db, command_id, brain_id, turn_id, request_hash):
        """Check one exact durable owner claim under the Pause writer lock."""
        from . import standard
        from .brain_control import stopped
        meta = self.ledger.get(db, "meta", 1)
        command = self.ledger.get(db, "commands", command_id)
        run = meta.get("standardRun")
        notification = command.get("notification") or {}
        approvals = notification.get("nativeApprovals", [])
        return (meta.get("brainId") == brain_id and
                not stopped(meta) and
                isinstance(run, dict) and run.get("protocol") == standard.PROTOCOL and
                run.get("status") == "running" and
                notification.get("status") == "accepted" and
                notification.get("brainId") == brain_id and
                notification.get("nativeTurnId") == turn_id and
                isinstance(approvals, list) and
                any(isinstance(entry, dict) and
                    entry.get("requestHash") == request_hash and
                    entry.get("decision") == "accept" and
                    entry.get("turnId") == turn_id and
                    entry.get("status") in ("claimed", "queued")
                    for entry in approvals) and
                not standard.current_blockers(self.ledger, db, run))

    def _write_accept_if_current(self, proxy, response, command_id, brain_id, turn_id, request_hash):
        """Serialize final gate and bounded native frame against Pause writes.

        The durable claim already exists. A partial/lost frame is uncertain and
        must not be retried; the caller closes the subscription on any failure.
        """
        if self.ledger is None:
            return False
        try:
            with self.ledger.tx() as db:
                if not self._accept_authorized_in_db(db, command_id, brain_id, turn_id, request_hash):
                    return False
                proxy._write(response)
                return True
        except Exception:
            return None

    def configured(self, brain_id):
        if brain_id not in self.binding["brains"]:
            return False
        if self.binding["brains"][brain_id]["workspaceId"] != getattr(self.ledger, "workspace_id", None):
            return False
        try:
            endpoint = self.binding["endpoint"]
            secure_path(endpoint["executable"])
            _, sock = secure_path(endpoint["socket"], socket_file=True)
            if socket_identity(sock) != endpoint["socketIdentity"]:
                return False
            cwd = self.binding["brains"][brain_id]["cwd"]
            return Path(cwd).resolve(strict=True) == Path(cwd) and Path(cwd).is_dir()
        except (OSError, Refusal, ValueError):
            return False

    def _identity(self, thread, brain_id):
        record = self.binding["brains"][brain_id]
        cwd = record["cwd"]
        # A catalogProjectId, when present, is never inferred from or matched
        # against this app-server task identity.
        require(isinstance(thread, dict) and thread.get("id") == brain_id and
                thread.get("cwd") == cwd and thread.get("projectId") == record["projectId"],
                "Native brain, project or checkout identity differs from owner binding")
        return cwd

    def _begin_thread_observation(self, command_id, brain_id):
        """Durably mark partial coverage before the native effect boundary."""
        require(self.ledger is not None, "Owned thread observation requires a ledger")
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", command_id)
            notification = command.get("notification") or {}
            require(notification.get("brainId") == brain_id and notification.get("status") == "sending" and
                    "nativeThreadObservation" not in notification,
                    "Owned thread observation does not match the one-shot claim")
            notification["nativeThreadObservation"] = {
                "version": 1, "rootThreadId": brain_id, "streamStatus": "open",
                "monitoringStartedAt": time.time(), "complete": False,
                "gaps": [THREAD_STREAM_GAP], "events": []}
            command["notification"] = notification
            self.ledger.put(db, "commands", command_id, command)

    def _record_thread_started(self, command_id, brain_id, row):
        """Retain only IDs with a witnessed chain to this brain, never content."""
        params = row.get("params")
        thread = params.get("thread") if isinstance(params, dict) else None
        if not isinstance(thread, dict):
            return
        thread_id = thread.get("id")
        parent_id = thread.get("parentThreadId")
        fork_id = thread.get("forkedFromId")
        if thread_id == brain_id or not isinstance(thread_id, str) or not UUID.fullmatch(thread_id):
            return
        # A foreign notification on the same app-server is never placed in
        # this workspace. A fork is retained only if its exact source is owned.
        relation = parent_id if isinstance(parent_id, str) and UUID.fullmatch(parent_id) else fork_id
        if not isinstance(relation, str) or not UUID.fullmatch(relation):
            return
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", command_id)
            notification = command.get("notification") or {}
            observation = notification.get("nativeThreadObservation")
            require(notification.get("brainId") == brain_id and
                    notification.get("status") in ("sending", "accepted") and
                    isinstance(observation, dict) and observation.get("rootThreadId") == brain_id and
                    observation.get("streamStatus") == "open", "Owned thread observation changed")
            events = observation["events"]
            if relation != brain_id and relation not in {item["threadId"] for item in events}:
                return
            event = {"threadId": thread_id, "parentThreadId": relation,
                     "relation": "parent" if relation == parent_id else "fork",
                     "ephemeral": thread.get("ephemeral") if type(thread.get("ephemeral")) is bool else None,
                     "observedAt": time.time()}
            prior = next((item for item in events if item["threadId"] == thread_id), None)
            if prior is not None:
                if any(prior[key] != event[key] for key in ("parentThreadId", "relation", "ephemeral")):
                    if "conflicting_thread_event" not in observation["gaps"]:
                        observation["gaps"].append("conflicting_thread_event")
                else:
                    return
            elif len(events) >= THREAD_EVENT_LIMIT:
                if "thread_event_limit" not in observation["gaps"]:
                    observation["gaps"].append("thread_event_limit")
            else:
                events.append(event)
            command["notification"] = notification
            self.ledger.put(db, "commands", command_id, command)

    def _finish_thread_observation(self, command_id, brain_id, turn_id, status, *, event_error=False):
        """Close the local stream fact; never promote it to complete inventory."""
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", command_id)
            notification = command.get("notification") or {}
            observation = notification.get("nativeThreadObservation")
            if (notification.get("brainId") != brain_id or not isinstance(observation, dict) or
                    observation.get("rootThreadId") != brain_id or observation.get("streamStatus") != "open"):
                return
            observation["streamStatus"] = "closed" if status in ("completed", "failed", "interrupted") else "unconfirmed"
            observation["nativeTurnId"] = turn_id
            observation["monitoringEndedAt"] = time.time()
            if observation["streamStatus"] == "unconfirmed":
                observation["gaps"].append("stream_ended_without_confirmed_turn")
            if event_error:
                observation["gaps"].append("thread_event_persist_failed")
            command["notification"] = notification
            self.ledger.put(db, "commands", command_id, command)

    def send(self, brain_id, message, command_id):
        """Return a sanitized one-shot result; no retries after an effect boundary."""
        with self._lock:
            if self._closed:
                return {"status": "unavailable", "detail": "Owned Codex host is closing; no message was sent."}
        if not self.configured(brain_id):
            return {"status": "unavailable", "detail": "Reviewed Codex app-server binding is unavailable; the saved control was not sent."}
        proxy = WakeProxy(self.binding["endpoint"], timeout=15)
        effect_started = False
        retained = False
        try:
            proxy.__enter__()
            read = proxy._rpc("thread/read", {"threadId": brain_id, "includeTurns": False})
            thread = read.get("thread") if isinstance(read, dict) else None
            if isinstance(thread, dict) and thread.get("projectId") is None:
                return {"status": "unavailable", "detail":
                        "Native Codex did not report the brain's project identity; no turn was sent."}
            cwd = self._identity(thread, brain_id)
            status = thread.get("status")
            require(isinstance(status, dict) and status.get("type") in
                    ("active", "idle", "notLoaded"), "Native brain activity is not safe to assume")
            if status["type"] == "active":
                # The queue command acknowledges delivery but does not give this
                # client the active turn's prompt stream. Until a same-host
                # subscription for active turns is qualified, refuse the effect.
                return {"status": "unavailable", "detail":
                        "The bound brain already has an active turn; native approval coverage for queued turns is unavailable. No message was sent."}
            with self.ledger.tx() as db:
                recovery = self.ledger.get(db, "commands", command_id).get("kind") == "brain_reply_recovery"
            if recovery:
                from .reply_recovery import send_check
                send_check(self.ledger, self.binding, command_id, proxy)
            policy = self.binding["brains"][brain_id]["nativePolicy"]
            resumed = proxy._rpc("thread/resume", {"threadId": brain_id,
                                                    "config": {"features": {"code_mode": {"enabled": policy["codeMode"]}}},
                                                    "sandbox": policy["sandbox"],
                                                    "approvalPolicy": policy["approvalPolicy"]})
            self._identity(resumed.get("thread") if isinstance(resumed, dict) else None, brain_id)
            if recovery:
                # Resume changes native loading, not dispatch authority. Recheck
                # a racing Stop and exact original immediately before turn/start.
                send_check(self.ledger, self.binding, command_id, proxy)
            # Immediately before this boundary a concurrent native turn may start.
            # A rejection or lost response is uncertain, never permission to retry.
            self._begin_thread_observation(command_id, brain_id)
            proxy._on_thread_started = lambda row: self._record_thread_started(command_id, brain_id, row)
            effect_started = True
            started = proxy._rpc("turn/start", {"threadId": brain_id,
                "input": [{"type": "text", "text": message}], "cwd": cwd})
            turn = started.get("turn") if isinstance(started, dict) else None
            require(isinstance(turn, dict) and isinstance(turn.get("id"), str) and
                    0 < len(turn["id"]) <= 128, "Native turn start was not confirmed")
            thread = threading.Thread(target=self._observe_turn,
                args=(proxy, command_id, brain_id, turn["id"]), daemon=True,
                name="codex-brain-wake-observer")
            with self._lock:
                require(not self._closed, "Owned Codex host closed during turn start")
                self._subscriptions.add(proxy)
            thread.start()
            retained = True
            return {"status": "accepted", "nativeTurnId": turn["id"], "nativeDelivery": "owned_turn_start",
                    "detail": "Turn started on the bound Codex app-server. Waiting for the brain's ledger receipt; native turn completion is separate."}
        except (OSError, Refusal, ValueError, KeyError, RuntimeError):
            with self._lock:
                self._subscriptions.discard(proxy)
            return {"status": "uncertain" if effect_started else "unavailable",
                    "detail": ("Native turn outcome is unknown. No automatic resend."
                               if effect_started else "Bound Codex app-server inspection failed before a turn was sent.")}
        finally:
            if not retained:
                if effect_started:
                    try:
                        self._finish_thread_observation(command_id, brain_id, None, "unconfirmed",
                            event_error=bool(getattr(proxy, "_thread_event_error", False)))
                    except (OSError, Refusal):
                        pass
                proxy.__exit__(None, None, None)

    def _observe_turn(self, proxy, command_id, brain_id, turn_id):
        """Keep the owned subscription alive; store only bounded lifecycle facts."""
        status = "unconfirmed"
        items = {}
        try:
            proxy.deadline = time.monotonic() + 6 * 3600
            early = getattr(proxy, "_early_completion", None)
            if isinstance(early, tuple) and len(early) == 3 and early[:2] == (brain_id, turn_id):
                status = early[2] if early[2] in ("completed", "failed", "interrupted") else "unconfirmed"
            early_requests = list(getattr(proxy, "_early_requests", ()))
            for _ in range(0 if early and early[:2] == (brain_id, turn_id) else 100_000):
                row = early_requests.pop(0) if early_requests else proxy._line()
                if not isinstance(row, dict):
                    break
                method, params = row.get("method"), row.get("params")
                if "id" in row and isinstance(method, str) and (
                        not isinstance(params, dict) or params.get("threadId") != brain_id):
                    status = "native_attention_required"
                    break
                if not isinstance(params, dict) or params.get("threadId") != brain_id:
                    continue
                if method == "item/started" and params.get("turnId") == turn_id:
                    item = params.get("item")
                    if (isinstance(item, dict) and isinstance(item.get("id"), str) and
                            item.get("type") in ("commandExecution", "fileChange") and
                            len(canonical(item).encode("utf-8")) <= MAX_APPROVAL):
                        items[item["id"]] = item
                        if len(items) > 16:
                            items.pop(next(iter(items)))
                    continue
                if method == "turn/completed" and isinstance(params.get("turn"), dict) and params["turn"].get("id") == turn_id:
                    value = params["turn"].get("status")
                    status = value if value in ("completed", "failed", "interrupted") else "unconfirmed"
                    break
                if "id" in row and isinstance(method, str):
                    if method not in APPROVAL_METHODS or params.get("turnId") != turn_id:
                        status = "native_attention_required"
                        break
                    outcome = self._offer_approval(proxy, row, command_id, brain_id, turn_id,
                                                   items.get(params.get("itemId")))
                    if outcome == "resolved":
                        continue
                    status = outcome
                    break
        except (OSError, Refusal, ValueError):
            pass
        finally:
            proxy.__exit__(None, None, None)
            with self._lock:
                self._subscriptions.discard(proxy)
            try:
                with self.ledger.tx() as db:
                    command = self.ledger.get(db, "commands", command_id)
                    notification = command.get("notification") or {}
                    if notification.get("nativeTurnId") in (None, turn_id) and notification.get("brainId") == brain_id:
                        notification["nativeTurnStatus"] = status
                        notification["nativeObservedAt"] = time.time()
                        command["notification"] = notification
                        self.ledger.put(db, "commands", command_id, command)
                self._finish_thread_observation(command_id, brain_id, turn_id, status,
                    event_error=bool(getattr(proxy, "_thread_event_error", False)))
            except (OSError, Refusal):
                # Shutdown or an unavailable ledger cannot turn a native fact
                # into permission to retry the one-shot control.
                pass
