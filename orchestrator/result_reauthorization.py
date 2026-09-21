"""Owner-only permission to review closed result bytes, never to resume a task."""
import copy
import time

from . import missions, run_authority as runs, task_contracts
from .admission import exact, sha, timestamp
from .core import digest, require
from .ownership_settlement import OwnershipSettlement, local_binding

KIND = "result_review_authorization"
FIELDS = {"runHash", "workerId", "intentHash", "settlementHash", "previousReviewHash", "commit", "reason", "confirmed"}


def record_in(db, key):
    record = runs.document(db, key, KIND)
    exact(record, {"kind", "workspaceId", "workerId", "actor", "status", "request", "at", "requestKey", "fingerprint", "previousAuthorityHash", "expiresAt"})
    require(record["kind"] == KIND and record["status"] in ("approved", "revoked"), "Invalid result review authority")
    request = record["request"]; operation = "result_review_"+record["status"]
    exact(request, {"id", "expectedRevision", *(FIELDS if record["status"] == "approved" else {"workerId", "authorityHash", "reason", "confirmed"})})
    timestamp(record["at"]); timestamp(record["expiresAt"])
    require(record["workerId"] == request["workerId"] and request["confirmed"] is True and
            record["fingerprint"] == digest({"workspaceId": record["workspaceId"], "operation": operation,
                "actor": record["actor"], "request": request}) and
            record["requestKey"] == digest({"kind": "run_request", "workspaceId": record["workspaceId"], "id": request["id"]}),
            "Result review authority request changed")
    from .phase_checkpoints import receipt_for
    receipt = receipt_for(db, record)
    require(record["actor"] == "dashboard_owner" and record["status"] in ("approved", "revoked") and
            receipt.get("operation") == operation and receipt.get("authorityHash") == key and
            receipt.get("executionAuthorized") is False and receipt.get("nativeNotificationSent") is False,
            "Result review authority receipt changed")
    return record


def history_in(db, worker_id):
    count, size = db.execute("SELECT count(*),coalesce(sum(length(CAST(data AS BLOB))),0) FROM snapshots WHERE kind=?", (KIND,)).fetchone()
    require(count <= 128 and size <= 2_000_000, "Result authority history needs explicit bounded migration")
    records = []
    for row in db.execute("SELECT id FROM snapshots WHERE kind=? ORDER BY rowid", (KIND,)):
        record = record_in(db, row[0])
        if record["workerId"] == worker_id:
            require(record["previousAuthorityHash"] == (digest(records[-1]) if records else None), "Result authority history changed")
            records.append(record)
    return records


def current_in(db, worker):
    history = history_in(db, worker["id"])
    pointer = worker.get("resultReviewAuthorityHash")
    require(pointer == (digest(history[-1]) if history else None), "Result authority pointer changed; explicit recovery required")
    return history[-1] if history else None


def settled_in(ledger, db, worker, intent):
    from . import result_review as results
    require(worker["status"] == "settled" and not worker.get("archived"), "Only an unaccepted settled result can be reviewed again")
    terminal = runs.document(db, worker.get("ownershipSettlementHash"), "ownership_settlement")
    require(terminal["intentHash"] == digest(intent) and terminal["workerId"] == worker["id"], "Exact confirmed settlement required")
    claim = OwnershipSettlement.settled_claim(terminal)
    if worker.get("resultReviewHash"):
        previous = results.reviewed_worker_in(db, worker, claim, terminal)
        require(previous["request"]["outcome"] == "changes_required", "Accepted results cannot be reopened")
    else:
        previous = None
        expected = copy.deepcopy(terminal["localBinding"]); expected["status"] = "settled"
        expected["dispatchAdmission"].update(stage="settled", claimHash=digest(claim))
        require(local_binding(worker) == expected, "Recover exact settlement before review authorization")
    results.unaccepted_worker(worker)
    q = ledger.get(db, "queue", intent["queueId"])
    reason = results.CHANGES_REQUIRED if previous else OwnershipSettlement.queue_reason
    require(q["held"] is True and q["status"] == "blocked" and q["reason"] == reason and
            q.get("resultReviewHash") == worker.get("resultReviewHash"), "Exact settled result hold required")
    return q, terminal, previous


def ancestry_in(db, intent, grant):
    old = runs.document(db, intent["runHash"], "run_authorization")
    require(grant["generation"] > old["generation"], "A later owner-authorized generation is required")
    # The chain must descend from this exact original run, not just have a larger number.
    ancestor = grant
    for _ in range(128):
        require(ancestor.get("previousRunHash"), "Result run is not an ancestor of the current run")
        parent = runs.document(db, ancestor["previousRunHash"], "run_authorization")
        require(parent["workspaceId"] == grant["workspaceId"] == intent["workspaceId"] and
                parent["generation"]+1 == ancestor["generation"], "Invalid run ancestry")
        if ancestor["previousRunHash"] == intent["runHash"]: break
        ancestor = parent
    else: require(False, "Run ancestry exceeds its inspection bound")


def scope_in(ledger, db, meta, worker, intent, run_hash):
    require(meta["paused"] is False and meta["runner"] is None, "Pause or runner ownership fences result review")
    grant = runs.require_current(ledger, db, run_hash)
    ancestry_in(db, intent, grant)
    runs.standard_handoff_scope(db, intent)
    q = ledger.get(db, "queue", intent["queueId"])
    require(q.get("phaseApprovalHash") == intent["approvalHash"] and q.get("taskContract", {}).get("hash") == intent["contractHash"], "Original task approval or contract changed")
    contract = runs.document(db, intent["contractHash"], "task_contract")
    source = task_contracts.context_in(ledger, db, q)
    spec = copy.deepcopy(contract["spec"])
    spec.update(missionHash=grant["missionHash"], reviewReceiptHash=grant["reviewReceiptHash"])
    # Validate against the new mission without replacing the old task/seed/approval.
    binding = task_contracts.validate_binding(spec, q, source)
    require(binding == contract["repositoryBinding"], "Original repository identity or policy changed")
    require(not any(c["kind"] in ("checkpoint", "archive") and c["status"] in ("queued", "processing") and
                    c["payload"].get("workerId") == worker["id"] for c in ledger.all(db, "commands")), "Worker control remains unresolved")
    return q


def authorize(ledger, request, *, actor):
    """Internal owner seam only. No brain/public route can mint this permission."""
    require(actor == "dashboard_owner", "Only the owner may authorize result rereview")
    request = copy.deepcopy(request)
    with ledger.tx() as db:
        meta, key, fp, prior = runs.request_in(ledger, db, request, actor, "result_review_approved", FIELDS)
        if prior:
            record_in(db, prior["authorityHash"])
            return prior
        require(request["confirmed"] is True, "Explicit result review confirmation required")
        missions.text(request["reason"], "Review-only rationale")
        from .result_review import commit
        commit(request["commit"]); sha(request["intentHash"]); sha(request["settlementHash"])
        if request["previousReviewHash"] is not None: sha(request["previousReviewHash"])
        worker = ledger.get(db, "workers", request["workerId"])
        intent = runs.document(db, request["intentHash"], "dispatch_intent")
        require(intent["workerId"] == worker["id"] and intent["workspaceId"] == missions.workspace(ledger) and
                worker.get("dispatchAdmission", {}).get("intentHash") == request["intentHash"], "Exact workspace result intent required")
        history = history_in(db, worker["id"]); current_in(db, worker)
        # Leave one history slot for withdrawal of the final allowed grant.
        require(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (KIND,)).fetchone()[0] < 127, "Result authority history limit reached")
        _, terminal, previous = settled_in(ledger, db, worker, intent)
        require(request["settlementHash"] == digest(terminal) and request["previousReviewHash"] == worker.get("resultReviewHash"), "Exact settlement and previous review required")
        if previous: require(request["commit"] == previous["request"]["result"]["commit"], "Changed source requires a new implementation task, not rereview")
        scope_in(ledger, db, meta, worker, intent, request["runHash"])
        grant = runs.document(db, request["runHash"], "run_authorization")
        record = {"kind": KIND, "workspaceId": missions.workspace(ledger), "workerId": worker["id"], "actor": actor,
            "status": "approved", "request": request, "at": time.time(), "requestKey": key, "fingerprint": fp,
            "previousAuthorityHash": digest(history[-1]) if history else None, "expiresAt": grant["expiresAt"]}
        authority_hash = runs.retain(db, KIND, record)
        worker["resultReviewAuthorityHash"] = authority_hash; ledger.put(db, "workers", worker["id"], worker)
        return runs.receipt_in(ledger, db, key, fp, "result_review_approved", authorityHash=authority_hash)


def revoke(ledger, request, *, actor):
    require(actor == "dashboard_owner", "Only the owner may revoke result rereview")
    request = copy.deepcopy(request)
    with ledger.tx() as db:
        _, key, fp, prior = runs.request_in(ledger, db, request, actor, "result_review_revoked", {"workerId", "authorityHash", "reason", "confirmed"})
        if prior: record_in(db, prior["authorityHash"]); return prior
        require(request["confirmed"] is True, "Explicit review revocation required"); missions.text(request["reason"], "Revocation reason")
        worker = ledger.get(db, "workers", request["workerId"]); previous = current_in(db, worker)
        require(previous and previous["status"] == "approved" and digest(previous) == request["authorityHash"], "Exact current review permission required")
        require(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (KIND,)).fetchone()[0] < 128, "Result authority history limit reached")
        record = {"kind": KIND, "workspaceId": missions.workspace(ledger), "workerId": worker["id"], "actor": actor,
            "status": "revoked", "request": request, "at": time.time(), "requestKey": key, "fingerprint": fp,
            "previousAuthorityHash": digest(previous), "expiresAt": previous["expiresAt"]}
        authority_hash = runs.retain(db, KIND, record)
        worker["resultReviewAuthorityHash"] = authority_hash; ledger.put(db, "workers", worker["id"], worker)
        return runs.receipt_in(ledger, db, key, fp, "result_review_revoked", authorityHash=authority_hash)


def check_in(ledger, db, meta, worker, intent, *, commit=None, key=None):
    record = current_in(db, worker)
    require(record and record["status"] == "approved", "Current owner result review permission required")
    req = record["request"]
    require(record["workspaceId"] == missions.workspace(ledger) and req["intentHash"] == digest(intent) and
            req["settlementHash"] == worker.get("ownershipSettlementHash") and
            req["previousReviewHash"] == worker.get("resultReviewHash"), "Review permission is consumed, stale or foreign")
    if key is not None: require(key == digest(record), "Exact result review permission required")
    if commit is not None: require(commit == req["commit"], "Result commit differs from owner review scope")
    require(record["at"] <= time.time() < record["expiresAt"], "Result review permission expired")
    q = scope_in(ledger, db, meta, worker, intent, req["runHash"])
    settled_in(ledger, db, worker, intent)
    return q
