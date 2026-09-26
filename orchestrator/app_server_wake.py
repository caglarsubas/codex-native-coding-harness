"""Opt-in, one-shot wake of a bound standard-project brain on an owned app-server.

This is an event-driven notification transport, not a scheduler or a Codex tool
client. A committed ledger claim precedes every call into this module. The socket
and exact brain checkout are private operator configuration, never browser input.
"""
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import threading
import time

from .core import Refusal, canonical, require
from .native_read_client import ReadProxy, decode, file_identity, secure_path, socket_identity, validate_endpoint

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
ACK = re.compile(r"Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\Z")
MAX_BINDING = 16_384


class WakeProxy(ReadProxy):
    """Fixed-purpose write client with bounded event streaming for a full turn."""
    def _rpc(self, method, params):
        self._awaiting_start = method == "turn/start"
        try:
            return super()._rpc(method, params)
        finally:
            self._awaiting_start = False

    def _write(self, value):
        raw = (canonical(value) + "\n").encode()
        require(len(raw) <= 16_384, "Native wake pointer exceeds its bound")
        while raw:
            self._ready(self.process.stdin, selectors.EVENT_WRITE)
            try:
                size = os.write(self.process.stdin.fileno(), raw)
            except BlockingIOError:
                continue
            require(size > 0, "Native proxy input closed")
            raw = raw[size:]

    def _line(self):
        while b"\n" not in self.buffer:
            self._ready(self.process.stdout, selectors.EVENT_READ)
            try:
                chunk = os.read(self.process.stdout.fileno(), 65536)
            except BlockingIOError:
                continue
            require(chunk, "Native proxy output closed")
            self.total += len(chunk)
            self.buffer += chunk
            require(self.total <= 128_000_000 and len(self.buffer) <= 1_000_000,
                    "Native wake stream exceeds its bound")
        line, self.buffer = self.buffer.split(b"\n", 1)
        row = decode(line)
        # A short turn can finish before turn/start returns its response. Keep
        # only the lifecycle fact while the parent RPC drops notifications.
        if getattr(self, "_awaiting_start", False) and isinstance(row, dict) and row.get("method") == "turn/completed":
            params = row.get("params")
            turn = params.get("turn") if isinstance(params, dict) else None
            if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                self._early_completion = (params.get("threadId"), turn["id"], turn.get("status"))
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
                isinstance(record, dict) and set(record) == {"cwd", "projectId", "workspaceId"} and
                isinstance(record["projectId"], str) and UUID.fullmatch(record["projectId"]),
                "Invalid brain binding entry")
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

    def close(self):
        """Dashboard shutdown drops owned subscriptions, never retries turns."""
        with self._lock:
            subscriptions = tuple(self._subscriptions)
            self._subscriptions.clear()
        for proxy in subscriptions:
            proxy.__exit__(None, None, None)

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
        require(isinstance(thread, dict) and thread.get("id") == brain_id and
                thread.get("cwd") == cwd and thread.get("projectId") == record["projectId"],
                "Native brain, project or checkout identity differs from owner binding")
        return cwd

    def _queue_active(self, brain_id, message, cwd):
        endpoint = self.binding["endpoint"]
        # A queue is used only when this *same owned host* reports an active turn.
        # It is never the default desktop queue that caused the unloaded-brain gap.
        try:
            completed = subprocess.run(
                [endpoint["executable"], "queue", "--remote", "unix://" + endpoint["socket"],
                 "--thread", brain_id, "--message", message],
                stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=8, check=False, cwd=cwd, shell=False)
        except OSError:
            return {"status": "uncertain", "detail": "Owned Codex queue could not be reached after native status inspection. No automatic resend."}
        except subprocess.TimeoutExpired:
            return {"status": "uncertain", "detail": "Owned Codex queue timed out; delivery is unknown. No automatic resend."}
        ack = ACK.fullmatch(completed.stdout.strip()) if completed.returncode == 0 else None
        if ack and UUID.fullmatch(ack[1]) and ack[2] == brain_id:
            return {"status": "accepted", "nativeMessageId": ack[1], "nativeDelivery": "owned_active_queue",
                    "detail": "Queued on the bound active Codex host. This is delivery, not a brain ledger receipt."}
        return {"status": "uncertain", "detail": "Owned Codex queue did not confirm exact delivery. No automatic resend."}

    def send(self, brain_id, message, command_id):
        """Return a sanitized one-shot result; no retries after an effect boundary."""
        if not self.configured(brain_id):
            return {"status": "unavailable", "detail": "Reviewed Codex app-server binding is unavailable; the saved control was not sent."}
        proxy = WakeProxy(self.binding["endpoint"], timeout=15)
        effect_started = False
        retained = False
        try:
            proxy.__enter__()
            read = proxy._rpc("thread/read", {"threadId": brain_id, "includeTurns": False})
            thread = read.get("thread") if isinstance(read, dict) else None
            cwd = self._identity(thread, brain_id)
            status = thread.get("status")
            require(isinstance(status, dict) and status.get("type") in
                    ("active", "idle", "notLoaded"), "Native brain activity is not safe to assume")
            if status["type"] == "active":
                return self._queue_active(brain_id, message, cwd)
            resumed = proxy._rpc("thread/resume", {"threadId": brain_id})
            self._identity(resumed.get("thread") if isinstance(resumed, dict) else None, brain_id)
            # Immediately before this boundary a concurrent native turn may start.
            # A rejection or lost response is uncertain, never permission to retry.
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
                proxy.__exit__(None, None, None)

    def _observe_turn(self, proxy, command_id, brain_id, turn_id):
        """Keep the owned subscription alive; store only bounded lifecycle facts."""
        status = "unconfirmed"
        try:
            proxy.deadline = time.monotonic() + 6 * 3600
            early = getattr(proxy, "_early_completion", None)
            if isinstance(early, tuple) and len(early) == 3 and early[:2] == (brain_id, turn_id):
                status = early[2] if early[2] in ("completed", "failed", "interrupted") else "unconfirmed"
            for _ in range(0 if early and early[:2] == (brain_id, turn_id) else 100_000):
                row = proxy._line()
                if not isinstance(row, dict):
                    break
                method, params = row.get("method"), row.get("params")
                if not isinstance(params, dict) or params.get("threadId") != brain_id:
                    continue
                if method == "turn/completed" and isinstance(params.get("turn"), dict) and params["turn"].get("id") == turn_id:
                    value = params["turn"].get("status")
                    status = value if value in ("completed", "failed", "interrupted") else "unconfirmed"
                    break
                if "id" in row and isinstance(method, str):
                    # No native permission is silently granted. A future owner
                    # approval adapter must be qualified before live migration.
                    status = "native_attention_required"
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
            except (OSError, Refusal):
                # Shutdown or an unavailable ledger cannot turn a native fact
                # into permission to retry the one-shot control.
                pass
