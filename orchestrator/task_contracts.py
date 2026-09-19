"""Immutable brain-proposed task declarations. No grant, adapter or native effects."""
import contextlib
import json
import math
import re
import sqlite3
import time

from . import missions
from .core import ACTIVE, SHA, Refusal, canonical, digest, require, validate_seed
from .phase_scope import contained_path

MAX_DOCUMENT_BYTES = 32768
SPEC_FIELDS = {"queueId", "seedHash", "packetDigest", "missionHash", "reviewReceiptHash",
               "operations", "requestedSettings", "estimatedTokens", "rationale", "reuseReason"}
DOC_FIELDS = {"schemaVersion", "kind", "workspaceId", "brainId", "version", "createdAt",
              "actor", "previousHash", "missionRevision", "phaseId", "repositoryBinding",
              "spec", "executionAuthorized"}


def document_in(db, sid, kind, bound=MAX_DOCUMENT_BYTES):
    if not isinstance(sid, str) or not SHA.fullmatch(sid): return None
    row = db.execute("SELECT data FROM snapshots WHERE id=? AND kind=? AND length(CAST(data AS BLOB))<=?",
                     (sid, kind, bound)).fetchone()
    if not row: return None
    try:
        value = json.loads(row[0])
        return value if isinstance(value, dict) and digest(value) == sid else None
    except (ValueError, TypeError): return None


def context_in(ledger, db, q):
    mission = missions.state_in(ledger, db)
    return {"workspaceId": missions.workspace(ledger), "meta": ledger.get(db, "meta", 1),
            "mission": mission, "receipt": document_in(db, mission.get("receiptHash"), "mission_receipt"),
            "repos": ledger.all(db, "repos"),
            "seeds": {q["id"]: document_in(db, q["seedHash"], "seed", 512000)}}


def reviewed_phase(source):
    m = source["mission"]; doc = m["document"]; receipt = source["receipt"] or {}
    require(isinstance(doc, dict) and digest(doc) == m["documentHash"], "Current mission integrity is required")
    require(doc["workspaceId"] == source["workspaceId"] and doc["brainId"] == source["meta"]["brainId"], "Mission identity changed")
    spec, bindings = missions.validate(doc["spec"], source["repos"])
    require(spec == doc["spec"] and bindings == doc["repositoryBindings"] and not m["bindingIssues"], "Mission repository bindings changed")
    require(m["effectiveStatus"] == "reviewed" and digest(receipt) == m.get("receiptHash") and
            receipt.get("operation") == "review" and receipt.get("actor") == "dashboard_owner" and
            receipt.get("documentHash") == m["documentHash"] and receipt.get("revision") == m["revision"],
            "Exact current owner-reviewed mission required")
    return spec, bindings


def shape(spec):
    require(isinstance(spec, dict) and set(spec) == SPEC_FIELDS, "Task contract fields must match v1")
    require(len(canonical(spec).encode()) <= 16000, "Task contract spec exceeds 16 KiB")
    for key in ("seedHash", "packetDigest", "missionHash", "reviewReceiptHash"):
        require(isinstance(spec[key], str) and SHA.fullmatch(spec[key]), "Exact task contract hashes required")
    queue_id = missions.text(spec["queueId"], "Queue ID", 200)
    ops = missions.strings(spec["operations"], "Task operations", maximum=len(missions.OPERATIONS))
    require(set(ops) <= set(missions.OPERATIONS), "Unknown operation; arbitrary commands are not allowed")
    settings = spec["requestedSettings"]
    require(isinstance(settings, dict) and set(settings) == {"model", "effort", "speed"}, "Explicit requested setting fields required")
    for value in settings.values():
        require(value is None or isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", value),
                "Requested settings must be bounded identifiers or null for defaults")
    estimate = missions.integer(spec["estimatedTokens"], "Estimated tokens", 1, 1_000_000_000)
    return {**spec, "queueId": queue_id, "operations": sorted(ops), "estimatedTokens": estimate,
            "rationale": missions.text(spec["rationale"], "Selection rationale"),
            "reuseReason": missions.text(spec["reuseReason"], "Why a new task rather than reuse")}


def validate_binding(spec, q, source):
    clean = shape(spec)
    require(clean == spec, "Task contract must use canonical normalized fields")
    mission, bindings = reviewed_phase(source)
    m = source["mission"]
    require(spec["queueId"] == q["id"] and spec["seedHash"] == q["seedHash"] and
            spec["packetDigest"] == q["packetDigest"], "Task contract seed or packet changed")
    require(spec["missionHash"] == m["documentHash"] and spec["reviewReceiptHash"] == m["receiptHash"], "Task contract mission review changed")
    seed = source["seeds"].get(q["id"])
    require(isinstance(seed, dict) and digest(seed) == q["seedHash"], "Task contract seed integrity is required")
    validate_seed(seed)
    repo = next((r for r in source["repos"] if r["id"] == q["repository"]), None)
    require(repo and seed["repository"] == q["repository"] and seed["packetId"] == q["packetId"] and
            seed["packetDigest"] == q["packetDigest"] and seed["policyProfile"] == repo["policyProfile"], "Task contract repository binding changed")
    scope = next((r for r in mission["phase"]["scope"] if r["repository"] == q["repository"]), None)
    require(scope and len(seed["allowedPaths"]) <= 80 and
            all(contained_path(p, scope["allowedPaths"]) for p in seed["allowedPaths"]), "Packet paths are not proven inside the phase")
    require(set(spec["operations"]) <= set(scope["operations"]), "Task operations exceed the reviewed phase")
    require(not ("merge" in spec["operations"] and repo["mergePolicy"] == "manual"), "Manual-merge policy cannot be overridden")
    require("merge" not in seed["completionAxes"] or "merge" in spec["operations"], "Required merge completion needs a declared merge operation")
    authority = mission["authority"]
    require(spec["estimatedTokens"] <= authority["tokenBudget"] - authority["checkpointReserveTokens"], "Estimate must preserve phase checkpoint reserve")
    return next(b for b in bindings if b["repository"] == q["repository"])


def evaluate(q, source, doc):
    pointer = q.get("taskContract")
    result = {"status": "not_declared", "executionAuthorized": False,
              "legacyDispatchBlocked": "taskContract" in q, "contractHash": None, "version": None}
    if "taskContract" not in q: return result
    try:
        require(isinstance(pointer, dict) and set(pointer) == {"hash", "version"}, "Invalid contract pointer")
        require(isinstance(pointer["hash"], str) and SHA.fullmatch(pointer["hash"]), "Invalid contract hash")
        missions.integer(pointer["version"], "Contract pointer version", 1, 1_000_000_000)
        result.update(contractHash=pointer["hash"], version=pointer["version"])
        require(isinstance(doc, dict) and set(doc) == DOC_FIELDS and digest(doc) == pointer["hash"], "Invalid task contract document")
        require(doc["schemaVersion"] == 1 and doc["kind"] == "task_contract" and doc["actor"] == "designated_brain" and
                doc["executionAuthorized"] is False, "Invalid task contract envelope")
        require(doc["workspaceId"] == source["workspaceId"], "Foreign workspace declaration")
        missions.integer(doc["version"], "Contract version", 1, 1_000_000_000)
        missions.integer(doc["missionRevision"], "Mission revision", 1, 1_000_000_000)
        require(type(doc["createdAt"]) in (int, float) and math.isfinite(doc["createdAt"]) and doc["createdAt"] > 0, "Invalid creation time")
        require(doc["previousHash"] is None or isinstance(doc["previousHash"], str) and SHA.fullmatch(doc["previousHash"]), "Invalid previous version")
        require(type(pointer["version"]) is int and pointer["version"] == doc["version"], "Invalid contract version")
        require(shape(doc["spec"]) == doc["spec"], "Invalid contract spec")
    except (ValueError, KeyError, TypeError, AttributeError):
        return {**result, "status": "invalid", "issue": "Task declaration is missing, oversized or invalid; its legacy fence remains."}
    result.update(status="bound", operations=doc["spec"]["operations"], estimatedTokens=doc["spec"]["estimatedTokens"],
                  settings={"requested": doc["spec"]["requestedSettings"], "applied": None, "observed": None,
                            "capabilityStatus": "unverified", "policyStatus": "not_authorized", "fallback": "block"})
    try:
        binding = validate_binding(doc["spec"], q, source)
        require(doc["workspaceId"] == source["workspaceId"] and doc["brainId"] == source["meta"]["brainId"] and
                doc["missionRevision"] == source["mission"]["revision"] and
                doc["phaseId"] == source["mission"]["document"]["spec"]["phase"]["id"] and
                doc["repositoryBinding"] == binding, "Contract identity or phase binding changed")
    except (ValueError, KeyError, TypeError, AttributeError):
        result.update(status="stale", issue="Mission, review, seed, scope or repository binding changed; propose a new exact contract.")
    return result


def propose(ledger, token, request):
    wid = missions.workspace(ledger)
    require(isinstance(request, dict) and set(request) == {"id", "expectedRevision", "spec"}, "Invalid task contract request")
    require(isinstance(request["id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request["id"]), "Invalid task contract request ID")
    missions.integer(request["expectedRevision"], "Ledger revision", 0, 1_000_000_000)
    spec = shape(request["spec"])
    fingerprint = digest({"workspaceId": wid, "request": request})
    request_key = digest({"kind": "task_contract_request", "workspaceId": wid, "id": request["id"]})
    with ledger.tx() as db:
        from .decisions import authorize_brain
        from .brain_control import stopped
        from .workspace_pause import fence_new_work
        meta = authorize_brain(ledger, db, token)
        prior = db.execute("SELECT data FROM snapshots WHERE id=? AND kind='task_contract_request'", (request_key,)).fetchone()
        if prior:
            retained = json.loads(prior[0])
            require(retained["fingerprint"] == fingerprint, "Task contract request ID reused with different content")
            return retained["receipt"]  # Historical acknowledgment, never reapply authority.
        require(not stopped(meta), "Stopped brain cannot propose a task contract")
        fence_new_work(meta)
        require(meta["revision"] == request["expectedRevision"], "Workspace changed; inspect before proposing again")
        if meta["schemaVersion"] == 1:
            require(meta["paused"] and meta.get("runner") is None and
                    not any(w["status"] in ACTIVE for w in ledger.all(db, "workers")),
                    "First task declaration requires paused dispatch and no retained active worker/runner; upgrade all older processes first")
        q = ledger.get(db, "queue", spec["queueId"])
        require(q["status"] in ("proposed", "approved") and not db.execute("SELECT 1 FROM workers WHERE queue_id=?", (q["id"],)).fetchone(),
                "An owned or dispatched packet cannot be replaced")
        source = context_in(ledger, db, q)
        binding = validate_binding(spec, q, source)
        previous = None; version = 1
        if "taskContract" in q:
            pointer = q["taskContract"]
            require(isinstance(pointer, dict), "Prior contract is invalid; preserve its fence for explicit recovery")
            previous_doc = document_in(db, pointer.get("hash"), "task_contract")
            require(evaluate(q, source, previous_doc)["status"] != "invalid", "Prior contract is invalid; explicit recovery required")
            previous = pointer["hash"]; version = pointer["version"] + 1
        doc = {"schemaVersion": 1, "kind": "task_contract", "workspaceId": wid, "brainId": meta["brainId"],
               "version": version, "createdAt": time.time(), "actor": "designated_brain", "previousHash": previous,
               "missionRevision": source["mission"]["revision"], "phaseId": source["mission"]["document"]["spec"]["phase"]["id"],
               "repositoryBinding": binding, "spec": spec, "executionAuthorized": False}
        require(len(canonical(doc).encode()) <= MAX_DOCUMENT_BYTES, "Task contract exceeds its bound")
        sid = digest(doc)
        # Atomic with the first declaration: older v1-only helpers must refuse
        # reopening instead of treating this queue item as a legacy seed.
        meta["schemaVersion"] = max(meta["schemaVersion"], 2)
        ledger.put(db, "meta", 1, meta)
        db.execute("INSERT INTO snapshots VALUES(?,?,?)", (sid, "task_contract", canonical(doc)))
        q.update(taskContract={"hash": sid, "version": version}, status="proposed", approval=None, preflight=None,
                 reason="Phase-bound declaration prepared; run-aware activation and approval are not implemented.")
        ledger.put(db, "queue", q["id"], q)
        receipt = {"requestId": request["id"], "queueId": q["id"], "contractHash": sid, "version": version,
                   "at": doc["createdAt"], "status": "prepared", "executionAuthorized": False, "nativeNotificationSent": False}
        db.execute("INSERT INTO snapshots VALUES(?,?,?)", (request_key, "task_contract_request", canonical({"fingerprint": fingerprint, "receipt": receipt})))
        ledger.event(db, "task_contract_prepared", receipt)
        return receipt


def read(ledger, queue_id):
    try: return _read(ledger, queue_id)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error):
        raise Refusal("Task declaration is unavailable: verify workspace identity and retained records. Legacy approval remains blocked for declared packets.") from None


def _read(ledger, queue_id):
    missions.workspace(ledger)
    with contextlib.closing(ledger.connect()) as db:
        db.execute("BEGIN")
        q = ledger.get(db, "queue", queue_id)
        pointer = q.get("taskContract") or {}
        sid = pointer.get("hash") if isinstance(pointer, dict) else None
        if not isinstance(sid, str) or not SHA.fullmatch(sid): sid = None
        doc = document_in(db, sid, "task_contract")
        result = {"queueId": queue_id, **evaluate(q, context_in(ledger, db, q), doc)}
        result["document"] = doc if result["status"] in ("bound", "stale") else None
        result["history"] = []
        seen = set()
        while sid and len(result["history"]) < 20 and sid not in seen:
            seen.add(sid); old = document_in(db, sid, "task_contract")
            if not old or not DOC_FIELDS <= set(old): break
            result["history"].append({"hash": sid, "version": old["version"], "createdAt": old["createdAt"]})
            sid = old["previousHash"]
        result["olderDocumentHash"] = sid if sid and sid not in seen else None
        return result
