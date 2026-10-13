"""Independent, hash-only receipt of an already owned native event stream.

The journal is started by the existing claimed notification before turn/start,
not by an importer, polling or a recovery request. It records positive item
observations; a subscription is NOT complete inventory or process cleanup.
"""
import hashlib
import math
import os
from pathlib import Path
import stat
import time

from .admission import exact
from .core import canonical, digest, require
from .native_read_client import decode, file_identity

SOURCE = "owned_native_item_capture_v1"
FIELD = "nativeEffectCapture"
MAX_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 512
CONTROL_KINDS = {"standard_play", "standard_pause", "standard_resume", "standard_pause_recovery",
                 "standard_pause_receipt_recovery"}
ITEM_TYPES = {"commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall",
              "collabAgentToolCall", "contextCompaction"}
STATUSES = {"completed", "failed", "declined", "inProgress"}


def source_hash():
    with Path(__file__).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value <= time.time() + 1


def identifier(value):
    require(isinstance(value, str) and 0 < len(value) <= 200 and "\x00" not in value,
            "Capture identity is missing or malformed")
    return value


def request_hash(command):
    # Standard Play uses its owner receipt/payload rather than the generic
    # command fingerprint. Pin the immutable intent fields in either contract.
    return digest({key: command.get(key) for key in ('id', 'kind', 'actor', 'createdAt', 'payload', 'fingerprint')})


def path_for(ledger, command_id):
    root = Path(ledger.root)
    require(root.is_absolute() and root.resolve(strict=True) == root, "Canonical private ledger required")
    info = root.stat()
    require(info.st_uid == os.getuid() and not info.st_mode & 0o077, "Private capture directory required")
    return root / ("native-effect-capture-" + digest(identifier(command_id)) + ".jsonl")


def read(path):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
            and not before.st_mode & 0o077 and before.st_nlink == 1 and before.st_size <= MAX_BYTES,
            "One private bounded regular capture file required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        require(file_identity(before) == file_identity(os.fstat(stream.fileno())), "Capture was replaced")
        raw = stream.read(MAX_BYTES + 1)
        require(file_identity(before) == file_identity(os.fstat(stream.fileno())) == file_identity(path.lstat()),
                "Capture changed while reading")
    require(len(raw) <= MAX_BYTES and raw.endswith(b"\n"), "Capture is oversized or interrupted")
    lines = raw.splitlines()
    require(1 <= len(lines) <= MAX_EVENTS + 2 and all(0 < len(line) <= 16384 for line in lines),
            "Capture framing or event bound exceeded")
    rows = [decode(line) for line in lines]
    require(all(isinstance(row, dict) for row in rows), "Malformed capture record")
    header = rows[0]
    exact(header, {"version", "source", "sourceHash", "commandId", "brainId", "runId", "bindingHash",
                   "originalRequestHash", "startedAt"})
    require(type(header["version"]) is int and header["version"] == 1 and header["source"] == SOURCE
            and header["sourceHash"] == source_hash() and finite(header["startedAt"]),
            "Capture source or original epoch is unsupported")
    head, prior_at = digest(header), header["startedAt"]
    for sequence, row in enumerate(rows[1:], 1):
        exact(row, {"sequence", "previousHash", "event"})
        require(type(row["sequence"]) is int and row["sequence"] == sequence and row["previousHash"] == head
                and isinstance(row["event"], dict) and finite(row["event"].get("observedAt"))
                and row["event"]["observedAt"] >= prior_at,
                "Capture chain, order or observation epoch changed")
        head, prior_at = digest(row), row["event"]["observedAt"]
    return header, rows[1:], head, hashlib.sha256(raw).hexdigest(), before


def _append(path, event, *, closing=False):
    header, rows, head, _, before = read(path)
    require(not rows or rows[-1]["event"].get("kind") != "closed", "Capture is permanently sealed")
    require(closing or len(rows) < MAX_EVENTS, "Capture event coverage limit reached")
    row = {"sequence": len(rows) + 1, "previousHash": head, "event": event}
    raw = (canonical(row) + "\n").encode()
    require(before.st_size + len(raw) <= MAX_BYTES, "Capture byte coverage limit reached")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    with os.fdopen(fd, "wb") as stream:
        require(file_identity(before) == file_identity(os.fstat(stream.fileno())) == file_identity(path.lstat()),
                "Capture changed before append")
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return digest(row)


def begin(ledger, binding, command, meta):
    """Only the existing sending standard control can create the original anchor."""
    if command.get("kind") not in CONTROL_KINDS:
        return None
    run, note = meta.get("standardRun") or {}, command.get("notification") or {}
    require(run.get("protocol") == "standard_cooperative_v1" and note.get("status") == "sending"
            and note.get("hostInspectionTransport") == "owned_observer_v1"
            and run.get("id") == note.get("hostRunId") and run.get("brainId") == note.get("brainId")
            and meta.get("brainId") == note.get("brainId") and note.get("hostBindingHash") == digest(binding)
            and FIELD not in note, "Capture requires its exact one-shot owned standard claim")
    identifier(command["id"]); identifier(run["id"]); identifier(meta["brainId"])
    header = {"version": 1, "source": SOURCE, "sourceHash": source_hash(), "commandId": command["id"],
              "brainId": meta["brainId"], "runId": run["id"], "bindingHash": digest(binding),
              "originalRequestHash": request_hash(command), "startedAt": time.time()}
    path = path_for(ledger, command["id"])
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write((canonical(header) + "\n").encode())
        stream.flush(); os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)
    info = path.stat()
    return {"version": 1, "source": SOURCE, "headerHash": digest(header), "sourceHash": header["sourceHash"],
            "fileInode": info.st_ino, "startedAt": header["startedAt"], "status": "open"}


def project(row, brain):
    """Closed metadata projection; no transcript, arguments, command or output."""
    method, params = row.get("method"), row.get("params")
    if not isinstance(params, dict) or params.get("threadId") != brain:
        return None
    if method == "turn/completed":
        turn = params.get("turn")
        require(isinstance(turn, dict), "Unknown captured turn completion")
        status = turn.get("status")
        require(status in {"completed", "failed", "interrupted"}, "Unknown captured turn status")
        completion = turn.get("completedAt")
        return {"kind": "turn_completed", "turnId": identifier(turn.get("id")), "status": status,
                "nativeCompletedAt": completion if finite(completion) else None, "rowHash": digest(row),
                "observedAt": time.time()}
    if method not in {"item/started", "item/completed"}:
        return None
    item = params.get("item")
    require(isinstance(item, dict), "Unknown captured native item")
    if item.get("type") in {"userMessage", "agentMessage", "plan", "reasoning", "webSearch"}:
        return None
    command, cwd = item.get("command"), item.get("cwd")
    handle, pid = item.get("processId"), item.get("osPid")
    return {"kind": "item_started" if method == "item/started" else "item_completed",
            "turnId": identifier(params.get("turnId")), "itemId": identifier(item.get("id")),
            "itemType": item.get("type") if item.get("type") in ITEM_TYPES else "unsupported",
            "status": item.get("status") if item.get("status") in STATUSES else "unknown",
            "commandHash": digest(command), "cwdHash": digest(cwd), "itemHash": digest(item),
            "exitCode": item.get("exitCode") if type(item.get("exitCode")) is int else None,
            "nativeHandleHash": digest(handle) if isinstance(handle, str) and handle else None,
            "osPidHash": digest(pid) if type(pid) is int and pid > 0 else None,
            "rowHash": digest(row), "observedAt": time.time()}


def append(ledger, command_id, brain_id, row):
    event = project(row, brain_id)
    if event is None:
        return
    path = path_for(ledger, command_id)
    header, _, _, _, _ = read(path)
    require(header["commandId"] == command_id and header["brainId"] == brain_id,
            "Capture event belongs to another original claim")
    _append(path, event)


def seal(ledger, command, turn_id, status, *, failed=False):
    note = command.get("notification") or {}
    marker = note.get(FIELD)
    if marker is None:
        return
    require(marker.get("status") == "open", "Capture cannot be reopened or resealed")
    path = path_for(ledger, command["id"])
    header, _, _, _, info = read(path)
    require(marker["headerHash"] == digest(header) and marker["fileInode"] == info.st_ino
            and header["originalRequestHash"] == request_hash(command)
            and header["bindingHash"] == note["hostBindingHash"], "Capture original anchor changed")
    ended = status in {"completed", "failed", "interrupted"}
    footer = {"kind": "closed", "turnId": turn_id, "status": status if ended else "unconfirmed",
              "captureError": bool(failed), "observedAt": time.time()}
    _append(path, footer, closing=True)
    _, rows, head, file_hash, _ = read(path)
    marker.update(status="sealed", turnId=turn_id, fileHash=file_hash, chainHead=head,
                  eventCount=len(rows) - 1, sealedAt=footer["observedAt"])


def retained(ledger, command):
    """Import only an original command's immutable anchor, never an arbitrary file."""
    note = command.get("notification") or {}
    marker = note.get(FIELD)
    if marker is None:
        return {"status": "unavailable", "reason": "capture_absent_at_original_effect", "events": []}
    require(isinstance(marker, dict), "Malformed original capture marker")
    base = {"version", "source", "headerHash", "sourceHash", "fileInode", "startedAt", "status"}
    exact(marker, base if marker.get("status") == "open" else
          base | {"turnId", "fileHash", "chainHead", "eventCount", "sealedAt"})
    require(type(marker["version"]) is int and marker["version"] == 1 and marker["source"] == SOURCE
            and type(marker["fileInode"]) is int and marker["fileInode"] > 0,
            "Original capture source or file identity is unsupported")
    header, rows, head, file_hash, info = read(path_for(ledger, command["id"]))
    require(digest(header) == marker["headerHash"] and header["sourceHash"] == marker["sourceHash"]
            and info.st_ino == marker["fileInode"] and header["startedAt"] == marker["startedAt"]
            and header["commandId"] == command["id"] and header["originalRequestHash"] == request_hash(command)
            and header["brainId"] == note["brainId"] and header["runId"] == note["hostRunId"]
            and header["bindingHash"] == note["hostBindingHash"], "Original capture provenance changed")
    if marker["status"] == "open":
        return {"status": "incomplete", "reason": "original_capture_not_sealed", "events": [],
                "headerHash": marker["headerHash"], "fileHash": file_hash,
                "startedAt": header["startedAt"], "eventCount": len(rows)}
    require(marker["status"] == "sealed" and rows and rows[-1]["event"].get("kind") == "closed"
            and marker["fileHash"] == file_hash and marker["chainHead"] == head
            and type(marker["eventCount"]) is int and marker["eventCount"] == len(rows) - 1
            and marker["turnId"] == note.get("nativeTurnId"), "Sealed original capture changed")
    footer = rows[-1]["event"]
    exact(footer, {"kind", "turnId", "status", "captureError", "observedAt"})
    require(footer["turnId"] == marker["turnId"] and footer["observedAt"] == marker["sealedAt"]
            and type(footer["captureError"]) is bool, "Capture seal or epoch changed")
    events = [row["event"] for row in rows[:-1]]
    for event in events:
        common = {"kind", "turnId", "status", "rowHash", "observedAt"}
        fields = common | {"nativeCompletedAt"} if event.get("kind") == "turn_completed" else common | {
            "itemId", "itemType", "commandHash", "cwdHash", "itemHash", "exitCode", "nativeHandleHash", "osPidHash"}
        exact(event, fields)
        require(event["kind"] in {"item_started", "item_completed", "turn_completed"}
                and event["turnId"] == marker["turnId"], "Foreign or unsupported captured effect")
    incomplete = footer["captureError"] or footer["status"] not in {"completed", "failed", "interrupted"}
    return {"status": "incomplete" if incomplete else "observed", "reason": "capture_interrupted" if incomplete else None,
            "headerHash": marker["headerHash"], "fileHash": file_hash, "startedAt": header["startedAt"],
            "sealedAt": marker["sealedAt"], "events": events,
            "completeInventory": False, "historicalCleanup": "unknown"}
