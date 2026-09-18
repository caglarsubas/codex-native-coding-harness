"""Bounded, read-only brain telemetry. No transcript storage or native API calls."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import threading
import time

from .core import Refusal
from .observations import config, contained, stamp

TAIL_BYTES = 256 * 1024
HEADER_BYTES = 64 * 1024
MAX_ENTRIES = 20000
MAX_FILES = 64
FRESH_SECONDS = 120
IDENTITY = re.compile(r"[a-zA-Z0-9_-]{1,100}")
LABELS = {
    "started": "Turn started", "working": "Processing this turn",
    "tool": "Tool activity recorded", "update": "Progress update posted in Codex",
    "reply": "Reply posted in Codex", "finished": "Turn finished",
    "interrupted": "Turn interrupted", "failed": "Turn failed",
}


def open_regular(path):
    """Refuse symlinks at every component and refuse special files before reading."""
    path = Path(path).absolute()
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        child = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        stream = os.fdopen(child, "rb")
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            stream.close()
            raise ValueError("Not a regular file")
        return stream
    finally:
        os.close(fd)


def candidates(home, brain):
    found, count = [], 0
    for folder in (home / "sessions", home / "archived_sessions"):
        if folder.is_symlink():
            raise ValueError("Symlink log root")
        if not folder.exists():
            continue
        def refuse(error):
            raise error
        for directory, dirs, files in os.walk(folder, followlinks=False, onerror=refuse):
            count += len(dirs) + len(files)
            if count > MAX_ENTRIES:
                raise ValueError("Discovery limit")
            dirs[:] = [d for d in dirs if not Path(directory, d).is_symlink()]
            for name in files:
                # Continuation files may add an underscore plus another UUID.
                if name.startswith("rollout-") and name.endswith(".jsonl") and brain in name:
                    found.append(Path(directory, name))
                    if len(found) > MAX_FILES:
                        raise ValueError("Segment limit")
    return found


def classify(record, brain):
    """Project only allowlisted event kinds; never copy arbitrary payload text."""
    if not isinstance(record, dict):
        return None
    p = record.get("payload")
    if not isinstance(p, dict) or p.get("thread_id", brain) != brain:
        return None
    kind, event = record.get("type"), p.get("type")
    phase = None
    if kind == "event_msg":
        phase = {"task_started": "started", "task_complete": "failed" if p.get("error") else "finished",
                 "turn_aborted": "interrupted", "token_count": "working",
                 "agent_message": "update"}.get(event)
        if event == "item_completed":
            item = p.get("item")
            item_kind = item.get("type") if isinstance(item, dict) else None
            phase = {"toolCall": "tool", "function_call": "tool", "mcpToolCall": "tool",
                     "commandExecution": "tool", "agentMessage": "update"}.get(item_kind, "working")
    elif kind == "turn_context":
        phase = "started"
    elif kind == "response_item":
        if event in ("function_call", "function_call_output", "custom_tool_call", "custom_tool_call_output"):
            phase = "tool"
        elif event == "message" and p.get("role") == "assistant":
            phase = "reply" if p.get("phase") in ("final", "final_answer") else "update" if p.get("phase") == "commentary" else None
    at = stamp(record.get("timestamp"))
    return {"at": at, "kind": phase, "label": LABELS[phase]} if phase and at else None


def read_segment(path, brain, roots, now):
    with open_regular(path) as stream:
        first = stream.readline(HEADER_BYTES + 1)
        if len(first) > HEADER_BYTES or not first.endswith(b"\n"):
            raise ValueError("Missing bounded header")
        header = json.loads(first)
        if not isinstance(header, dict) or not isinstance(header.get("payload"), dict):
            raise ValueError("Invalid header")
        p = header["payload"]
        if header.get("type") != "session_meta" or p.get("id") != brain:
            return []  # A filename match alone never authorizes reading the tail.
        cwd = p.get("cwd")
        if not isinstance(cwd, str) or not any(contained(cwd, r) for r in roots):
            return []
        size = os.fstat(stream.fileno()).st_size
        start = max(stream.tell(), size - TAIL_BYTES)
        stream.seek(start)
        if start > len(first):
            stream.readline(TAIL_BYTES + 1)  # Drop the first partial record.
        raw = stream.read(TAIL_BYTES)
    events = []
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            continue  # The writer may still be appending a record.
        try:
            value = classify(json.loads(line), brain)
        except (ValueError, TypeError, AttributeError):
            continue
        if value:
            if value["at"] > now + 5:
                raise ValueError("Future activity timestamp")
            events.append(value)
    return events


class BrainActivity:
    def __init__(self, ledger):
        self.ledger = ledger
        self.lock = threading.Lock()
        self.key = None
        self.cached = None
        self.checked = 0

    def snapshot(self, state, now=None):
        now = time.time() if now is None else now
        brain = state["meta"]["brainId"]
        native = state["observations"].get("native") or {}
        title = native.get("brain", {}).get("title") if native.get("brain", {}).get("id") == brain else None
        result = {"brainId": brain, "title": title or "Designated brain", "status": "unknown",
                  "source": "unavailable", "observedAt": None, "lastEventAt": None,
                  "phase": "No recent activity observed", "events": [], "checkedAt": now,
                  "fresh": False, "reason": "Local task logs are not configured.", "readOnly": True}
        if not isinstance(brain, str) or not IDENTITY.fullmatch(brain):
            return {**result, "reason": "No valid designated brain identity."}
        try:
            settings = config(self.ledger)
            home = settings.get("codexHome")
            roots = tuple(r["path"] for r in state["repositories"] if r["path"])
            key = (brain, home, roots)
            if home:
                home = Path(home)
                if not home.is_absolute() or ".." in home.parts or home.is_symlink():
                    raise ValueError("Invalid log root")
                with self.lock:
                    if key != self.key or not 0 <= now - self.checked < 3:
                        events = []
                        for path in candidates(home, brain):
                            events.extend(read_segment(path, brain, roots, now))
                        # Archives and continuation overlap must not duplicate events.
                        self.cached = sorted({(e["at"], e["kind"]): e for e in events}.values(), key=lambda e: e["at"])[-12:]
                        self.key, self.checked = key, now
                    events = list(self.cached or [])
                result.update(source="local_task_events", events=events, checkedAt=self.checked,
                              reason="Bounded local event metadata; not a live Codex connection. No conversation contents are displayed.")
                if events:
                    last = events[-1]
                    fresh = 0 <= now - last["at"] <= FRESH_SECONDS
                    status = {"finished": "idle", "interrupted": "interrupted", "failed": "failed"}.get(last["kind"], "running") if fresh else "unknown"
                    result.update(status=status, observedAt=last["at"], lastEventAt=last["at"], phase=last["label"], fresh=fresh)
                else:
                    result["reason"] = "No supported recent events in the bounded brain log tail. Open the brain task to verify activity."
        except (OSError, ValueError, TypeError, KeyError, Refusal):
            result.update(reason="Brain activity could not be read safely. Open the Codex task; no state was changed.")
            # Do not silently fall back to older logs after a read failure.
            return result
        # A newer native observation wins, but it also expires. Polling never
        # advances either source timestamp or fabricates a new native observation.
        observed = native.get("observedAt")
        observation = native.get("brain", {})
        if (observation.get("id") == brain and type(observed) in (int, float)
                and 0 <= now - observed <= FRESH_SECONDS
                and observed >= (result["lastEventAt"] or 0)):
            status = observation.get("status", "unknown")
            result.update(status=status if status in ("running", "idle") else "unknown", fresh=True,
                          source="recorded_native_observation", observedAt=observed,
                          phase="Native task status observed: " + status,
                          reason="Status recorded using native Codex tools; the webpage does not call those tools.")
        return result
