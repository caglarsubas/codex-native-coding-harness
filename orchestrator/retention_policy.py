"""Explicit phase-run retention delegation, never native archival or cleanup.

Owner methods are internal authenticated-caller seams; the brain CLI cannot review
or revoke policy. Retained request counts are not released by cancellation/review.
"""
import copy
import json
import time

from . import missions, run_authority as runs
from .admission import exact, integer, sha, timestamp
from .core import Refusal, canonical, digest, require

POLICY = "retention_policy"
DELEGATION = "retention_delegation"
SLOT = "retention_delegation_slot"
ACTOR = "designated_brain_retention"
MAX_HISTORY = 1000


def policy_in(db, key):
    doc = runs.document(db, key, POLICY)
    exact(doc, {"kind", "actor", "workspaceId", "brainId", "runHash", "missionHash", "phaseId", "maxArchives",
                "minimumRetentionSeconds", "allowManagedWorktreeCleanup", "version", "previousHash", "at"})
    require(doc["kind"] == POLICY, "Invalid retention policy kind")
    integer(doc["version"], 1, MAX_HISTORY); timestamp(doc["at"])
    if doc["previousHash"] is not None: sha(doc["previousHash"])
    grant = runs.document(db, doc["runHash"], "run_authorization")
    require(doc["actor"] == "dashboard_owner" and doc["workspaceId"] == grant["workspaceId"] and
            doc["brainId"] == grant["brainId"] and doc["phaseId"] == grant["phaseId"] and
            doc["missionHash"] == grant["missionHash"] and grant["authority"]["approvalMode"] == "phase_delegated" and
            grant["createdAt"] <= doc["at"] < grant["expiresAt"],
            "Retention owner/run binding changed")
    integer(doc["maxArchives"], 1, min(64, grant["authority"]["maxTasks"]))
    integer(doc["minimumRetentionSeconds"], 0, 86400)
    require(doc["allowManagedWorktreeCleanup"] is True, "Explicit managed-worktree cleanup acknowledgment required")
    return doc


def latest_in(ledger, db):
    meta = ledger.get(db, "meta", 1); key = meta.get("retentionPolicyHash")
    count = db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (POLICY,)).fetchone()[0]
    require(count <= MAX_HISTORY, "Retention history requires explicit maintenance")
    require(key or count == 0, "Retention policy pointer missing; no fallback")
    if not key: return None
    doc = policy_in(db, key)
    require(doc["version"] == count and doc["workspaceId"] == missions.workspace(ledger) and
            doc["brainId"] == meta["brainId"], "Retention policy history or identity changed")
    require((doc["previousHash"] is None) == (count == 1), "Retention policy predecessor missing")
    if doc["previousHash"]:
        previous = policy_in(db, doc["previousHash"])
        require(previous["version"]+1 == count and previous["workspaceId"] == doc["workspaceId"] and
                previous["brainId"] == doc["brainId"], "Retention policy history incomplete")
    return doc


def current_in(ledger, db, key, run_hash):
    doc = latest_in(ledger, db)
    require(doc and digest(doc) == key and ledger.get(db, "meta", 1).get("retentionPolicyRevoked") is False,
            "Retention policy missing, revoked or superseded")
    require(doc["runHash"] == run_hash, "Retention policy belongs to another run generation")
    runs.require_current(ledger, db, run_hash)
    return doc


def review(ledger, request, *, actor):
    require(actor == "dashboard_owner", "Only the owner can review retention policy")
    request = copy.deepcopy(request)
    with ledger.tx() as db:
        meta, key, fp, prior = runs.request_in(ledger, db, request, actor, "retention_review",
            {"runHash", "expectedPolicyHash", "maxArchives", "minimumRetentionSeconds", "allowManagedWorktreeCleanup", "confirmed"})
        if prior: return prior
        require(meta["paused"] is True and request["confirmed"] is True, "Explicit owner review while paused required")
        old = latest_in(ledger, db)
        require(request["expectedPolicyHash"] == (digest(old) if old else None), "Retention policy version changed")
        grant = runs.require_current(ledger, db, request["runHash"])
        require(grant["authority"]["approvalMode"] == "phase_delegated", "Retention delegation requires a phase-delegated run")
        integer(request["maxArchives"], 1, min(64, grant["authority"]["maxTasks"]))
        integer(request["minimumRetentionSeconds"], 0, 86400)
        require(request["allowManagedWorktreeCleanup"] is True, "Owner must explicitly acknowledge managed-worktree cleanup")
        version = old["version"]+1 if old else 1
        require(version <= MAX_HISTORY, "Retention history requires explicit maintenance")
        doc = {"kind": POLICY, "actor": actor, "workspaceId": grant["workspaceId"], "brainId": grant["brainId"],
               "runHash": request["runHash"], "missionHash": grant["missionHash"], "phaseId": grant["phaseId"],
               "maxArchives": request["maxArchives"], "minimumRetentionSeconds": request["minimumRetentionSeconds"],
               "allowManagedWorktreeCleanup": True, "version": version, "previousHash": digest(old) if old else None, "at": time.time()}
        value = runs.retain(db, POLICY, doc)
        meta.update(retentionPolicyHash=value, retentionPolicyRevoked=False); ledger.put(db, "meta", 1, meta)
        return runs.receipt_in(ledger, db, key, fp, "retention_review", policyHash=value)


def revoke(ledger, request, *, actor):
    require(actor == "dashboard_owner", "Only the owner can revoke retention policy")
    request = copy.deepcopy(request)
    with ledger.tx() as db:
        meta, key, fp, prior = runs.request_in(ledger, db, request, actor, "retention_revoke", {"policyHash", "reason"})
        if prior: return prior
        sha(request["policyHash"]); missions.text(request["reason"], "Revocation reason")
        doc = latest_in(ledger, db)
        require(doc and digest(doc) == request["policyHash"], "Exact retention policy required")
        meta["retentionPolicyRevoked"] = True; ledger.put(db, "meta", 1, meta)
        return runs.receipt_in(ledger, db, key, fp, "retention_revoke", policyHash=request["policyHash"])


def slot(worker_id): return digest({"kind": SLOT, "workerId": worker_id})


def pointer_data(raw, fields):
    try: pointer = json.loads(raw)
    except (ValueError, TypeError): raise Refusal("Invalid retained retention pointer") from None
    exact(pointer, fields)
    for value in pointer.values(): sha(value)
    return pointer


def delegation_in(db, worker_id):
    row = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=200 THEN data END FROM snapshots WHERE id=?", (slot(worker_id),)).fetchone()
    if not row: return None
    require(row[0] == SLOT and row[1] is not None, "Retention request pointer changed")
    pointer = pointer_data(row[1], {"delegationHash"})
    doc = runs.document(db, pointer["delegationHash"], DELEGATION)
    require(doc["workerId"] == worker_id, "Retention request belongs to another worker")
    return doc


def inventory_in(ledger, db):
    count, size = db.execute("SELECT count(*),coalesce(sum(length(CAST(data AS BLOB))),0) FROM snapshots WHERE kind=?", (DELEGATION,)).fetchone()
    require(count <= MAX_HISTORY and size <= 2_000_000, "Retention inventory requires explicit maintenance")
    meta = ledger.get(db, "meta", 1)
    require(meta.get("retentionDelegationCount", 0) == count and
            db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (SLOT,)).fetchone()[0] == count,
            "Retention request history or attempt count changed")
    docs = []
    for row in db.execute("SELECT id FROM snapshots WHERE kind=? ORDER BY id", (DELEGATION,)):
        doc = runs.document(db, row[0], DELEGATION)
        require(delegation_in(db, doc["workerId"]) == doc, "Retention request history is missing its pointer")
        docs.append(doc)
    return docs


def state_in(ledger, db, worker, intent):
    policy = latest_in(ledger, db); docs = inventory_in(ledger, db)
    doc = delegation_in(db, worker["id"])
    if doc: validate_command(db, worker, ledger.get(db, "commands", doc["commandId"]))
    matches = policy is not None and policy["runHash"] == intent["runHash"]
    revoked = ledger.get(db, "meta", 1).get("retentionPolicyRevoked") is True
    return {"policyHash": digest(policy) if matches else None,
            "status": "not_delegated" if not matches else "revoked" if revoked else "reviewed_policy",
            "maxArchives": policy["maxArchives"] if matches else None,
            "minimumRetentionSeconds": policy["minimumRetentionSeconds"] if matches else None,
            "recordedAttempts": sum(d["runHash"] == intent["runHash"] for d in docs),
            "commandId": doc["commandId"] if doc else None, "delegationHash": digest(doc) if doc else None,
            "currentSafetyChecked": False, "sendPermit": False}


def validate_command(db, worker, command, *, ledger=None, current=False):
    """Historical binding remains valid after policy revocation/expiry or Pause."""
    meta = json.loads(db.execute("SELECT data FROM meta WHERE id=1").fetchone()[0])
    require(meta.get("retentionDelegationCount", 0) == db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (DELEGATION,)).fetchone()[0] ==
            db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (SLOT,)).fetchone()[0], "Retention history changed; no owner fallback")
    doc = delegation_in(db, worker["id"])
    if doc is None:
        require(command["actor"] != ACTOR and "retentionHash" not in command, "Retention request proof is missing")
        return None
    require(command["actor"] == ACTOR and command.get("retentionHash") == digest(doc) and
            command["id"] == doc["commandId"] and command["fingerprint"] == doc["commandFingerprint"] and
            command["payload"] == doc["payload"], "Retention command binding changed; no owner fallback")
    policy = policy_in(db, doc["policyHash"])
    intent = runs.document(db, worker["dispatchAdmission"]["intentHash"], "dispatch_intent")
    require(doc["runHash"] == policy["runHash"] == intent["runHash"] and doc["intentHash"] == digest(intent) and
            policy["workspaceId"] == intent["workspaceId"] and doc["at"] == command["createdAt"], "Retention task/run identity changed")
    result = runs.document(db, doc["payload"]["reviewHash"], "result_review")
    require(result["workerId"] == worker["id"] and doc["at"] >= max(policy["at"], result["at"]+policy["minimumRetentionSeconds"]),
            "Retention policy or age binding changed")
    # New command construction precedes its atomic request receipt. Every retained
    # command (including historical reads) must have that exact receipt thereafter.
    if db.execute("SELECT 1 FROM commands WHERE id=?", (command["id"],)).fetchone():
        request_key = digest({"kind": "run_request", "workspaceId": policy["workspaceId"], "id": doc["request"]["id"]})
        row = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=512 THEN data END FROM snapshots WHERE id=?", (request_key,)).fetchone()
        require(row and row[0] == "run_request" and row[1] is not None, "Retention request receipt missing")
        pointer = pointer_data(row[1], {"fingerprint", "receiptHash"})
        require(pointer["fingerprint"] == digest({"workspaceId": policy["workspaceId"], "operation": "retention_request",
                "actor": "designated_brain", "request": doc["request"]}), "Retention request fingerprint changed")
        receipt = runs.document(db, pointer["receiptHash"], "run_receipt")
        require(receipt["operation"] == "retention_request" and receipt["workerId"] == worker["id"] and
                receipt["delegationHash"] == digest(doc) and receipt["commandId"] == command["id"], "Retention receipt binding changed")
    if current:
        current_in(ledger, db, doc["policyHash"], doc["runHash"])
        docs = inventory_in(ledger, db)
        require(sum(d["runHash"] == doc["runHash"] for d in docs) <= policy["maxArchives"], "Retention attempt cap exceeded")
    return doc


def request_archive(api, token, worker_id, request):
    request = copy.deepcopy(request); ledger = api.ledger
    fields = {"policyHash", "reviewHash", "preservationArtifactId", "rationale"}
    # A historical receipt is readable after Pause; no effect guard is bypassed.
    with api.bridge.locked(token) as (db, _):
        _, _, _, prior = runs.request_in(ledger, db, request, "designated_brain", "retention_request", fields, token)
        if prior:
            require(prior["workerId"] == worker_id, "Retention replay belongs to another worker")
            worker, _ = api.bridge.intent_in(db, worker_id)
            validate_command(db, worker, ledger.get(db, "commands", prior["commandId"]))
            return prior
    with api.bridge.locked(token, effects=True) as (db, meta):
        _, key, fp, prior = runs.request_in(ledger, db, request, "designated_brain", "retention_request", fields, token)
        if prior:
            require(prior["workerId"] == worker_id, "Retention replay belongs to another worker")
            worker, _ = api.bridge.intent_in(db, worker_id)
            validate_command(db, worker, ledger.get(db, "commands", prior["commandId"]))
            return prior
        for field in ("policyHash", "reviewHash", "preservationArtifactId"): sha(request[field])
        missions.text(request["rationale"], "Retention rationale", 2000)
        worker, intent = api.bridge.intent_in(db, worker_id)
        with api.store.tx() as kernel:
            api.results.reviewer.settlement.maintenance_check(kernel)
            _, result, payload, _ = api.context_in(db, kernel, worker, intent)
            pair = (worker["hostId"], worker["threadId"])
            require(api.results.reviewer.settlement.known_descendants(db, pair) == {pair}, "Known descendants prevent root-only retention")
            policy = current_in(ledger, db, request["policyHash"], intent["runHash"])
            require(request["reviewHash"] == payload["reviewHash"] and request["preservationArtifactId"] == payload["preservationArtifactId"],
                    "Exact accepted review and preservation required")
            require(time.time()-result["at"] >= policy["minimumRetentionSeconds"], "Minimum retention age has not elapsed")
            docs = inventory_in(ledger, db)
            require(sum(d["runHash"] == intent["runHash"] for d in docs) < policy["maxArchives"], "Retention attempt cap exhausted")
        require(delegation_in(db, worker_id) is None, "Retention already requested for this worker; never retry")
        command = {"id": "retention-"+key, "kind": "archive", "expectedRevision": meta["revision"], "payload": payload}
        now = time.time(); command.update(fingerprint=digest(command), actor=ACTOR, status="queued", createdAt=now,
            archiveReceivedAt=now, result="Phase-delegated retention request saved; fresh archive safety checks required")
        require(not db.execute("SELECT 1 FROM commands WHERE id=?", (command["id"],)).fetchone(), "Retention command ID collision")
        doc = {"kind": DELEGATION, "workerId": worker_id, "intentHash": digest(intent), "runHash": intent["runHash"],
               "policyHash": request["policyHash"], "commandId": command["id"], "commandFingerprint": command["fingerprint"],
               "payload": payload, "request": request, "at": now}
        value = runs.retain(db, DELEGATION, doc); command["retentionHash"] = value
        db.execute("INSERT INTO snapshots VALUES(?,?,?)", (slot(worker_id), SLOT, canonical({"delegationHash": value})))
        meta["retentionDelegationCount"] = len(docs)+1; ledger.put(db, "meta", 1, meta)
        from .archive_handoff import submit_in
        submit_in(ledger, db, worker, command)
        ledger.put(db, "commands", command["id"], command)
        return runs.receipt_in(ledger, db, key, fp, "retention_request", commandId=command["id"], workerId=worker_id,
                               delegationHash=value, policyHash=request["policyHash"], sendPermit=False, nativeCallMade=False)
