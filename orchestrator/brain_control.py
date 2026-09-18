"""Cooperative brain stop/resume. Intent, checkpoint and native activity differ."""
import time

from .core import SHA, canonical, digest, require
from .decisions import authorize_brain, text


def control(meta):
    return meta.get("brainControl", {"desired": "running", "phase": "ready"})


def stopped(meta):
    return control(meta)["desired"] == "stopped"


def request(ledger, db, command, meta):
    previous = control(meta)
    stopping = command["kind"] == "brain_stop"
    if stopping:
        require(not stopped(meta), "A brain stop is already requested or checkpointed")
    else:
        require(previous["phase"] != "resume_requested", "Brain resume already requested")
    for older in ledger.all(db, "commands"):
        supersede = older["kind"] in ("brain_stop", "brain_resume") or (stopping and older["kind"] == "resume")
        if supersede and older["status"] in ("queued", "processing"):
            older.update(status="rejected", result="Superseded by a newer brain control request")
            ledger.put(db, "commands", older["id"], older)
    meta["brainControl"] = {"desired": "stopped" if stopping else "running",
        "phase": "stop_requested" if stopping else "resume_requested",
        "commandId": command["id"], "requestedAt": command["createdAt"],
        "checkpoint": previous.get("checkpoint")}
    if stopping:
        # Close new worker creation now, but never kill a task/process or release
        # ownership. Resume brain does not silently reopen worker dispatch.
        meta["paused"] = True
    ledger.put(db, "meta", 1, meta)


def receive_stop(ledger, db, token):
    meta = authorize_brain(ledger, db, token)
    current = control(meta)
    if current["phase"] == "parked":
        return []
    command = ledger.get(db, "commands", current["commandId"])
    if command["status"] == "queued":
        command.update(status="processing", receivedAt=time.time(),
            result="Stop received. Preserve a safe checkpoint and reconcile workers/runner before parking the brain.")
        current["phase"] = "checkpointing"
        meta["brainControl"] = current
        ledger.put(db, "meta", 1, meta)
        ledger.put(db, "commands", command["id"], command)
        ledger.event(db, "brain_stop_received", {"commandId": command["id"]})
    # Repeated cycles reconcile this same stop, never replay native side effects.
    return [{"kind": "brain_stop", "commandId": command["id"], "phase": current["phase"]}]


def park(ledger, token, command_id, checkpoint):
    require(isinstance(checkpoint, dict) and set(checkpoint) == {"summary", "artifactIds", "workerObservations"}, "Invalid brain checkpoint fields")
    text(checkpoint["summary"], "checkpoint summary")
    ids = checkpoint["artifactIds"]
    require(isinstance(ids, list) and 1 <= len(ids) <= 8 and all(isinstance(i, str) and SHA.fullmatch(i) for i in ids), "Retain 1–8 checkpoint artifacts first")
    require(len(set(ids)) == len(ids), "Duplicate checkpoint artifact")
    observations = checkpoint["workerObservations"]
    require(isinstance(observations, list), "Worker observations must be a list")
    now = time.time()
    with ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        current = control(meta)
        require(stopped(meta) and current.get("commandId") == command_id, "Stop was superseded; re-read brain control intent")
        command = ledger.get(db, "commands", command_id)
        fingerprint = digest(checkpoint)
        if current["phase"] == "parked":
            require(current["checkpoint"]["fingerprint"] == fingerprint, "Checkpoint retry changed")
            return current["checkpoint"]
        require(command["kind"] == "brain_stop" and command["status"] == "processing", "Receive the exact stop before parking")
        require(meta["runner"] is None, "Acceptance runner still owned; observe exit and release it first")
        hb = meta["heartbeat"]
        require((hb["id"] is None and hb["status"] == "not_configured") or
                (hb["id"] and hb["status"] == "PAUSED" and current["requestedAt"] <= hb.get("observedAt", 0) <= now
                 and now - hb["observedAt"] <= 120), "Fresh native heartbeat PAUSED observation required after this stop")
        artifacts = []
        for identity in ids:
            artifact = ledger.get(db, "artifact_versions", identity)
            ledger.get(db, "repos", artifact["repository"])
            artifacts.append(artifact)
        require(any(current["requestedAt"] <= a.get("observedAt", 0) <= now for a in artifacts), "Retain a new checkpoint artifact after this stop request")
        workers = [w for w in ledger.all(db, "workers") if w["status"] != "complete"]
        require(all(w["status"] not in ("starting", "accepting") for w in workers), "Reconcile in-flight native creation/acceptance before parking")
        required = {w["id"]: w for w in workers if w["status"] != "reserved"}
        seen = set()
        for item in observations:
            require(isinstance(item, dict) and set(item) == {"workerId", "threadId", "status", "observedAt", "reference"}, "Invalid worker checkpoint observation")
            wid = item["workerId"]
            require(isinstance(wid, str) and wid in required and wid not in seen, "Unexpected or duplicate worker observation")
            worker = required[wid]
            require(worker.get("threadId") and item["threadId"] == worker["threadId"] and item["status"] == "idle", "Each active worker needs a matching native idle observation")
            at = item["observedAt"]
            require(type(at) in (int, float) and current["requestedAt"] <= at <= now and now-at <= 120, "Worker observation must be fresh and after the stop")
            text(item["reference"], "native worker checkpoint reference")
            seen.add(wid)
        require(seen == set(required), "Reconcile and checkpoint every active worker first")
        require(not any(c["status"] == "processing" and c["kind"] in ("checkpoint", "archive") for c in ledger.all(db, "commands")), "Reconcile in-flight worker controls before parking")
        document = {"schemaVersion": 1, "kind": "brain_checkpoint", "commandId": command_id,
                    "at": now, "heartbeat": hb, "workers": workers,
                    "queue": ledger.all(db, "queue"),
                    "pendingCommands": [c["id"] for c in ledger.all(db, "commands") if (c["status"] in ("queued", "processing") or c.get("needsBrainReceipt")) and c["id"] != command_id],
                    **checkpoint}
        identity = digest(document)
        db.execute("INSERT INTO snapshots VALUES (?,?,?)", (identity, "brain_checkpoint", canonical(document)))
        saved = {"documentHash": identity, "fingerprint": fingerprint, "at": now, **checkpoint}
        current.update(phase="parked", checkpoint=saved)
        meta["brainControl"] = current
        meta["paused"] = True
        ledger.put(db, "meta", 1, meta)
        command.update(status="completed", result="Safe checkpoint saved; automatic brain work is stopped. Native turn completion is observed separately.")
        ledger.put(db, "commands", command_id, command)
        ledger.event(db, "brain_checkpoint_saved", {"commandId": command_id, "documentHash": identity})
        return saved
