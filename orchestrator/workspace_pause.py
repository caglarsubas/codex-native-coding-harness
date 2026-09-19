"""Cooperative workspace pause evidence. No native effects or ownership release."""
import json
import time

from .admission import exact, identifier, sha, timestamp
from .core import canonical, digest, require
from .decisions import authorize_brain

PROTOCOL = "workspace_pause_v1"
AGE = 120


def active(meta):
    control = meta.get("brainControl") or {}
    return control.get("protocol") == PROTOCOL and control.get("desired") == "stopped"


def worker_binding(worker):
    binding = {k: worker.get(k) for k in ("id", "repository", "status", "hostId", "threadId", "clientThreadId")}
    if "dispatchAdmission" in worker:
        binding.update({k: worker.get(k) for k in ("nativeLifecycleHash", "nativeContinuationIntentHash")})
    return binding


def fence_new_work(meta):
    require(not active(meta), "Workspace is pausing or paused; resume the brain from its checkpoint before new work")


def native_pair(row):
    return row["hostId"], row["threadId"]


def validate(document):
    exact(document, {"workspaceId", "commandId", "observedAt", "evidenceHash", "complete", "includesDescendants", "brain", "tasks"})
    identifier(document["workspaceId"]); identifier(document["commandId"])
    timestamp(document["observedAt"]); sha(document["evidenceHash"])
    require(type(document["complete"]) is bool and type(document["includesDescendants"]) is bool, "Explicit inventory coverage required")
    exact(document["brain"], {"hostId", "threadId"})
    identifier(document["brain"]["hostId"]); identifier(document["brain"]["threadId"])
    require(isinstance(document["tasks"], list) and len(document["tasks"]) <= 500, "Pause inventory must contain at most 500 tasks")
    require(len(canonical(document).encode()) <= 512_000, "Pause evidence exceeds its bound")
    seen, workers = set(), set()
    for task in document["tasks"]:
        exact(task, {"hostId", "threadId", "workerId", "parent", "status", "observedAt", "checkpointArtifactId"})
        identifier(task["hostId"]); identifier(task["threadId"]); timestamp(task["observedAt"])
        require(task["status"] in ("idle", "running", "unknown"), "Invalid native activity state")
        if task["workerId"] is not None:
            identifier(task["workerId"])
            require(task["workerId"] not in workers, "Duplicate worker observation")
            workers.add(task["workerId"])
        if task["parent"] is not None:
            exact(task["parent"], {"hostId", "threadId"})
            identifier(task["parent"]["hostId"]); identifier(task["parent"]["threadId"])
        if task["checkpointArtifactId"] is not None: sha(task["checkpointArtifactId"])
        key = native_pair(task)
        require(key not in seen and key != native_pair(document["brain"]), "Duplicate task or brain included as a worker")
        seen.add(key)


def source(ledger, db, control):
    workers = {w["id"]: worker_binding(w) for w in ledger.all(db, "workers")}
    required = {w["id"]: w for w in control.get("retainedWorkers", [])}
    required.update({wid: w for wid, w in workers.items() if w["status"] != "complete"})
    # A completed or missing row after Pause cannot erase the captured owner.
    for wid in set(required) & set(workers): required[wid] = workers[wid]
    meta = ledger.get(db, "meta", 1)
    pending = [{"id": c["id"], "kind": c["kind"], "status": c["status"]} for c in ledger.all(db, "commands")
               if c["status"] == "processing" and c["kind"] in ("checkpoint", "archive")]
    return {"workers": sorted(required.values(), key=lambda w: w["id"]),
            "missingWorkers": sorted(set(required) - set(workers)), "runner": meta["runner"],
            "pendingControls": sorted(pending, key=lambda c: c["id"])}


def inspect(ledger, db, meta, retained, now):
    control = meta["brainControl"]
    start = control["requestedAt"]
    current = source(ledger, db, control)
    issues, expiries = [], []
    def issue(code, detail, **scope):
        issues.append({"code": code, "detail": detail, **scope})
    def fresh(at):
        return type(at) in (int, float) and start <= at <= now and now - at <= AGE
    if current["runner"]: issue("runner_owned", "Observe runner exit and cleanup before releasing it.", view="workers")
    if current["pendingControls"]: issue("worker_control_inflight", "Reconcile in-flight worker controls before parking.", view="workers")
    for wid in current["missingWorkers"]: issue("retained_worker_missing", "A retained worker record is missing; recover it explicitly.", workerId=wid, view="workers")
    for worker in current["workers"]:
        if worker["status"] in ("starting", "accepting"):
            issue("worker_effect_inflight", "Reconcile creation or acceptance; do not retry or release ownership.", workerId=worker["id"], view="workers")
    hb = meta["heartbeat"]
    if not ((hb["id"] is None and hb["status"] == "not_configured") or
            (hb["id"] and hb["status"] == "PAUSED" and fresh(hb.get("observedAt")))):
        issue("heartbeat_unconfirmed", "Record a fresh native heartbeat pause after this request.", view="overview")
    if hb.get("id") and type(hb.get("observedAt")) in (int, float): expiries.append(hb["observedAt"] + AGE)
    if not retained:
        issue("inventory_missing", "The brain must observe workers and descendants, then retain pause evidence.", view="workers")
        return current, issues, None
    document = retained["document"]
    if retained["sourceHash"] != digest(current): issue("ownership_changed", "Worker or runner state changed; observe and record evidence again.", view="workers")
    if not document["complete"] or not document["includesDescendants"]:
        issue("inventory_incomplete", "Native coverage is incomplete, including nested and review tasks.", view="workers")
    if not fresh(document["observedAt"]): issue("inventory_stale", "Pause inventory is stale, future-dated or older than the request.", view="workers")
    expiries.append(document["observedAt"] + AGE)
    by_worker = {t["workerId"]: t for t in document["tasks"] if t["workerId"]}
    required = {w["id"]: w for w in current["workers"]}
    for wid, worker in required.items():
        if worker["status"] == "reserved" and not worker["threadId"] and not worker["clientThreadId"]:
            continue  # No creation attempt; retain the reservation.
        task = by_worker.get(wid)
        if not task or not worker["threadId"] or native_pair(task) != (worker["hostId"], worker["threadId"]):
            issue("worker_observation_missing", "A retained worker needs its exact host/task observation.", workerId=wid, view="workers")
    for wid in set(by_worker) - set(required): issue("foreign_worker", "Observation references an unowned worker.", workerId=wid, view="workers")
    tasks = {native_pair(t): t for t in document["tasks"]}
    repositories = {r["id"] for r in ledger.all(db, "repos")}
    brain = native_pair(document["brain"])
    retained_bindings = {(w.get("hostId"), w.get("threadId")) for w in control.get("retainedWorkers", []) if w.get("threadId")}
    for key in retained_bindings - set(tasks):
        issue("retained_native_missing", "A native binding captured at Pause is absent from the inventory.", threadId=key[1], view="workers")
    for key, task in tasks.items():
        scope = {"threadId": key[1], "hostId": key[0], "view": "workers"}
        if task["status"] != "idle": issue("task_not_idle", "Task is running or its activity is unknown.", **scope)
        if not fresh(task["observedAt"]) or task["observedAt"] > document["observedAt"]:
            issue("task_observation_stale", "A fresh native observation after the checkpoint is required.", **scope)
        expiries.append(task["observedAt"] + AGE)
        cursor, seen, root_worker = key, set(), None
        while cursor in tasks and cursor not in seen:
            seen.add(cursor); row = tasks[cursor]
            if row["workerId"]:
                root_worker = required.get(row["workerId"])
            parent = native_pair(row["parent"]) if row["parent"] else None
            if parent is None and row["workerId"] in required: break
            if parent == brain: break
            cursor = parent
        else:
            issue("task_ancestry_unresolved", "Task ancestry is missing, foreign or cyclic.", **scope)
        artifact = None
        if task["checkpointArtifactId"]:
            row = db.execute("SELECT data FROM artifact_versions WHERE id=?", (task["checkpointArtifactId"],)).fetchone()
            artifact = json.loads(row[0]) if row else None
        if not artifact or artifact.get("repository") not in repositories or not (start <= artifact.get("observedAt", 0) <= task["observedAt"]) or not any(
                r.get("session") == task["threadId"] for r in artifact.get("references", [])) or (
                root_worker and artifact["repository"] != root_worker["repository"]):
            issue("task_checkpoint_missing", "Retain this task's post-request checkpoint artifact before observing idle.", **scope)
    return current, issues, min(expiries) if expiries else None


def retained_in(ledger, db, control):
    key = control.get("pauseEvidenceHash")
    if not key: return None
    retained = ledger.get(db, "snapshots", key)
    require(digest(retained) == key, "Pause evidence hash mismatch")
    return retained


def observe(ledger, token, command_id, document):
    validate(document)
    with ledger.tx() as db:
        meta = authorize_brain(ledger, db, token); control = meta.get("brainControl") or {}
        require(active(meta) and control.get("commandId") == command_id and control["phase"] == "checkpointing", "Receive the current workspace pause before observing")
        require(document["commandId"] == command_id and document["workspaceId"] == control["workspaceId"] and
                document["brain"]["threadId"] == meta["brainId"], "Pause evidence scope mismatch")
        prior = retained_in(ledger, db, control)
        current = source(ledger, db, control)
        if prior and prior["document"] == document and prior["sourceHash"] == digest(current): return {"documentHash": control["pauseEvidenceHash"]}
        now = time.time()
        require(control["requestedAt"] <= document["observedAt"] <= now and now - document["observedAt"] <= AGE, "Fresh pause inventory required")
        if prior:
            require(document["observedAt"] > prior["document"]["observedAt"], "Pause observations must move forwards")
            require({native_pair(t) for t in prior["document"]["tasks"]} <= {native_pair(t) for t in document["tasks"]},
                    "Observed tasks cannot disappear from the pause inventory")
        value = {"kind": "workspace_pause_evidence", "document": document, "sourceHash": digest(current),
                 "previousHash": control.get("pauseEvidenceHash"), "recordedAt": now}
        identity = digest(value)
        db.execute("INSERT INTO snapshots VALUES(?,?,?)", (identity, value["kind"], canonical(value)))
        control["pauseEvidenceHash"] = identity; meta["brainControl"] = control
        ledger.put(db, "meta", 1, meta)
        ledger.event(db, "workspace_pause_observed", {"commandId": command_id, "documentHash": identity})
        return {"documentHash": identity}


def status_in(ledger, db, now=None):
    now = time.time() if now is None else now
    meta = ledger.get(db, "meta", 1); control = meta.get("brainControl") or {}
    if not active(meta): return {"status": "not_requested", "canResumeBrain": control.get("phase") != "resume_requested", "blockers": []}
    retained = retained_in(ledger, db, control)
    current, issues, valid_until = inspect(ledger, db, meta, retained, now)
    if control["phase"] == "stop_requested": issues.insert(0, {"code": "brain_receipt_pending", "detail": "The brain has not received this pause yet.", "view": "overview"})
    return {"status": "checkpoint_saved" if control["phase"] == "parked" else "pausing",
            "commandId": control["commandId"], "requestedAt": control["requestedAt"],
            "evidenceHash": control.get("pauseEvidenceHash"), "validUntil": valid_until,
            "blockers": issues, "readyToPark": not issues and control["phase"] == "checkpointing",
            "canResumeBrain": control["phase"] == "parked", "retainedWorkers": len(current["workers"]),
            "observedTasks": len(retained["document"]["tasks"]) if retained else None,
            "checkpointAt": (control.get("checkpoint") or {}).get("at"),
            "ownershipReleased": False, "executionAuthorized": False}
