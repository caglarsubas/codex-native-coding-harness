"""Internal run-authority kernel; deliberately no public activation route.

These receipts bind owner intent, not native execution. A future adapter must
couple checks to admission and native-effect receipts. Never consume them as argv
or as a standalone permit. No native tools, allocations or notifications here.
"""
import contextlib
import json
import re
import time

from . import missions, task_contracts
from .admission import exact, sha, timestamp
from .core import ACTIVE, Refusal, canonical, digest, require
from .decisions import authorize_brain

STOP_REASONS = {"phase_checkpoint", "roadmap_complete", "plan_revision", "budget_revision",
                "corrections_exhausted", "evidence_lost"}
STATE_FIELDS = {"kind", "workspaceId", "generation", "runHash", "status", "reason",
                "stopReasons", "stopCommandId", "checkpointHash", "at", "previousHash"}


def managed(meta):
    return "runAuthority" in meta or "runAuthorityInvalidated" in meta or meta.get("schemaVersion") == 3


def retain(db, kind, document):
    require(len(canonical(document).encode()) <= 32768, "Run record exceeds its bound")
    key = digest(document)
    db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?)", (key, kind, canonical(document)))
    return key


def document(db, key, kind):
    value = task_contracts.document_in(db, key, kind)
    require(value is not None, "Run record is missing or invalid; retain its legacy fence for recovery")
    return value


def current_in(ledger, db):
    meta = ledger.get(db, "meta", 1)
    require(not meta.get("runAuthorityInvalidated"), "Run authority was invalidated; explicit recovery required")
    if "runAuthority" not in meta:
        require(not managed(meta), "Run authority pointer is missing; explicit recovery required")
        return None
    pointer = meta["runAuthority"]
    exact(pointer, {"hash", "generation"}); sha(pointer["hash"])
    missions.integer(pointer["generation"], "Run generation", 1, 1_000_000_000)
    state = document(db, pointer["hash"], "run_state")
    exact(state, STATE_FIELDS)
    missions.integer(state["generation"], "Retained run generation", 1, 1_000_000_000)
    require(state["kind"] == "run_state" and state["status"] in ("authorized_intent", "fenced", "checkpointed"), "Invalid run state")
    require(isinstance(state["stopReasons"], list) and len(state["stopReasons"]) <= 32 and
            all(isinstance(r, str) and len(r) <= 100 for r in state["stopReasons"]), "Invalid stop reasons")
    sha(state["runHash"]); timestamp(state["at"])
    for field in ("previousHash", "checkpointHash"):
        if state[field] is not None: sha(state[field])
    require(state["workspaceId"] == missions.workspace(ledger) and
            state["generation"] == pointer["generation"], "Run state identity changed")
    return state


def save_state(ledger, db, meta, state):
    state = {**state, "at": time.time(), "previousHash": (meta.get("runAuthority") or {}).get("hash")}
    key = retain(db, "run_state", state)
    meta["runAuthority"] = {"hash": key, "generation": state["generation"]}
    ledger.put(db, "meta", 1, meta)
    return key


def request_in(ledger, db, request, actor, operation, fields, token=None):
    wid = missions.workspace(ledger)
    exact(request, {"id", "expectedRevision", *fields})
    require(isinstance(request["id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request["id"]), "Invalid run request ID")
    missions.integer(request["expectedRevision"], "Ledger revision", 0, 1_000_000_000)
    try: raw = canonical(request).encode()
    except (ValueError, TypeError): raise Refusal("Run request must be finite JSON") from None
    require(len(raw) <= 16000, "Run request exceeds its bound")
    for field in ("runHash", "missionHash", "reviewReceiptHash", "approvalHash", "contractHash"):
        if field in request: sha(request[field])
    if request.get("checkpointHash") is not None: sha(request["checkpointHash"])
    if "queueId" in request: missions.text(request["queueId"], "Queue ID", 200)
    require(actor in ("dashboard_owner", "designated_brain"), "Invalid run actor")
    meta = authorize_brain(ledger, db, token) if actor == "designated_brain" else ledger.get(db, "meta", 1)
    fingerprint = digest({"workspaceId": wid, "operation": operation, "actor": actor, "request": request})
    key = digest({"kind": "run_request", "workspaceId": wid, "id": request["id"]})
    row = db.execute("SELECT kind, CASE WHEN length(CAST(data AS BLOB))<=32768 THEN data ELSE NULL END FROM snapshots WHERE id=?", (key,)).fetchone()
    if row:
        # Request IDs use a lookup key rather than a document digest.
        require(row[0] == "run_request" and row[1] is not None, "Invalid retained run request")
        try: old = json.loads(row[1])
        except (ValueError, TypeError): raise Refusal("Invalid retained run request") from None
        exact(old, {"fingerprint", "receiptHash"}); sha(old["fingerprint"]); sha(old["receiptHash"])
        require(old["fingerprint"] == fingerprint, "Run request ID reused with different content")
        receipt = document(db, old["receiptHash"], "run_receipt")
        require(receipt.get("operation") == operation and receipt.get("executionAuthorized") is False, "Invalid retained run receipt")
        return meta, key, fingerprint, receipt
    require(meta["revision"] == request["expectedRevision"], "Workspace changed; review before requesting run authority")
    return meta, key, fingerprint, None


def receipt_in(ledger, db, key, fingerprint, operation, **fields):
    receipt = {"kind": "run_receipt", "operation": operation, "at": time.time(),
               "executionAuthorized": False, "nativeNotificationSent": False, **fields}
    receipt_hash = retain(db, "run_receipt", receipt)
    db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, "run_request", canonical({"fingerprint": fingerprint, "receiptHash": receipt_hash})))
    ledger.event(db, "run_" + operation, {"receiptHash": receipt_hash, **fields})
    return receipt


def mission_source(ledger, db):
    m = missions.state_in(ledger, db)
    return {"workspaceId": missions.workspace(ledger), "meta": ledger.get(db, "meta", 1), "mission": m,
            "receipt": task_contracts.document_in(db, m.get("receiptHash"), "mission_receipt"),
            "repos": ledger.all(db, "repos")}


def authorize(ledger, request, *, actor):
    """Retain exact owner run intent. Internal only; does not activate dispatch."""
    require(actor == "dashboard_owner", "Only the authenticated owner may authorize a run")
    with ledger.tx() as db:
        meta, key, fingerprint, prior = request_in(ledger, db, request, actor, "authorize",
            {"missionHash", "reviewReceiptHash", "checkpointHash", "expiresAt", "settingsPolicy", "confirmed"})
        if prior: return prior
        require(request["confirmed"] is True and request["settingsPolicy"] == "native_defaults",
                "Explicit owner confirmation of native defaults is required; adaptive policy is not implemented")
        timestamp(request["expiresAt"])
        now = time.time()
        require(now < request["expiresAt"] <= now + 86400, "Run intent needs an expiry within 24 hours")
        source = mission_source(ledger, db)
        spec, bindings = task_contracts.reviewed_phase(source)
        m = source["mission"]
        require(request["missionHash"] == m["documentHash"] and request["reviewReceiptHash"] == m["receiptHash"], "Exact reviewed mission required")
        require(spec["authority"]["approvalMode"] != "prepare_only", "Prepare-only mission cannot authorize task execution")
        previous = current_in(ledger, db)
        require(meta["paused"] is True, "Pause legacy dispatch before retaining run intent")
        if previous is None:
            require(request["checkpointHash"] is None, "Initial run cannot release an unknown checkpoint")
            require(meta.get("runner") is None and not any(w["status"] in ACTIVE for w in ledger.all(db, "workers")),
                    "Initial run requires no retained active legacy workers or runner; reconcile ownership first")
            generation = 1
        else:
            control = meta.get("brainControl") or {}
            checkpoint = control.get("checkpoint") or {}
            require(previous["status"] == "checkpointed" and control.get("phase") == "parked" and
                    request["checkpointHash"] == previous.get("checkpointHash") == checkpoint.get("documentHash") and
                    previous.get("stopCommandId") == control.get("commandId"), "Release the exact retained safe checkpoint before another generation")
            proof = document(db, request["checkpointHash"], "brain_checkpoint")
            require(proof["commandId"] == previous["stopCommandId"], "Checkpoint belongs to a different stop")
            if set(previous["stopReasons"]) & STOP_REASONS:
                old_grant = document(db, previous["runHash"], "run_authorization")
                require(m["documentHash"] != old_grant["missionHash"],
                        "Brain stop boundary requires a newly reviewed mission or bounded correction scope")
            generation = previous["generation"] + 1
        missions.integer(generation, "Run generation", 1, 1_000_000_000)
        grant = {"kind": "run_authorization", "schemaVersion": 1, "workspaceId": source["workspaceId"],
                 "brainId": meta["brainId"], "generation": generation, "actor": actor, "createdAt": now,
                 "expiresAt": request["expiresAt"], "missionHash": m["documentHash"], "reviewReceiptHash": m["receiptHash"],
                 "missionRevision": m["revision"], "phaseId": spec["phase"]["id"], "authority": spec["authority"],
                 "repositoryBindings": bindings, "settingsPolicy": "native_defaults", "checkpoint": spec["phase"]["checkpoint"],
                 "releasedCheckpointHash": request["checkpointHash"], "previousRunHash": previous["runHash"] if previous else None}
        run_hash = retain(db, "run_authorization", grant)
        meta["schemaVersion"] = 3
        save_state(ledger, db, meta, {"kind": "run_state", "workspaceId": source["workspaceId"], "generation": generation,
                   "runHash": run_hash, "status": "authorized_intent", "reason": None, "stopReasons": [], "stopCommandId": None, "checkpointHash": None})
        return receipt_in(ledger, db, key, fingerprint, "authorize", runHash=run_hash, generation=generation)


def require_current(ledger, db, run_hash):
    sha(run_hash)
    state = current_in(ledger, db)
    require(state and state["runHash"] == run_hash and state["status"] == "authorized_intent", "Run generation is absent, superseded or fenced")
    grant = document(db, run_hash, "run_authorization")
    source = mission_source(ledger, db)
    spec, bindings = task_contracts.reviewed_phase(source)
    m, meta = source["mission"], source["meta"]
    require(grant["workspaceId"] == source["workspaceId"] and grant["brainId"] == meta["brainId"] and
            grant["generation"] == state["generation"] and grant["missionHash"] == m["documentHash"] and
            grant["reviewReceiptHash"] == m["receiptHash"] and grant["missionRevision"] == m["revision"] and
            grant["phaseId"] == spec["phase"]["id"] and grant["authority"] == spec["authority"] and
            grant["repositoryBindings"] == bindings, "Run mission or identity binding changed")
    require(grant["actor"] == "dashboard_owner" and grant["settingsPolicy"] == "native_defaults", "Unsupported run policy")
    require(grant["createdAt"] <= time.time() < grant["expiresAt"], "Run authority expired or future-dated; checkpoint required")
    from .brain_control import stopped
    require(not stopped(meta), "Brain is stopping or parked; no new task authority")
    return grant


def contract_in(ledger, db, queue_id, contract_hash):
    sha(contract_hash)
    q = ledger.get(db, "queue", queue_id)
    require(q["status"] in ("proposed", "approved", "dispatched"), "Completed or invalid task cannot gain further run authority")
    pointer = q.get("taskContract")
    require(isinstance(pointer, dict) and pointer.get("hash") == contract_hash, "Exact current task contract required")
    doc = document(db, contract_hash, "task_contract")
    result = task_contracts.evaluate(q, task_contracts.context_in(ledger, db, q), doc)
    require(result["status"] == "bound" and not q["held"], "Task contract is stale, invalid or held")
    require(all(v is None for v in doc["spec"]["requestedSettings"].values()), "Task settings exceed the authorized native-defaults policy")
    return q, doc


def approve_task(ledger, request, *, actor, token=None):
    with ledger.tx() as db:
        return approve_task_in(ledger, db, request, actor=actor, token=token)


def approve_task_in(ledger, db, request, *, actor, token=None):
    """Same approval checks, composable with a retained brain decision atomically."""
    require(db.in_transaction, "Task approval requires a transaction")
    _, key, fingerprint, prior = request_in(ledger, db, request, actor, "approve_task",
        {"runHash", "queueId", "contractHash", "scopeAssessment", "confirmed"}, token)
    if prior: return prior
    require(request["confirmed"] is True, "Explicit exact task confirmation required")
    assessment = missions.text(request["scopeAssessment"], "Task scope assessment")
    grant = require_current(ledger, db, request["runHash"])
    q, contract = contract_in(ledger, db, request["queueId"], request["contractHash"])
    require(q["status"] in ("proposed", "approved") and not db.execute("SELECT 1 FROM workers WHERE queue_id=?", (q["id"],)).fetchone(),
            "Owned task requires future continuation authority, not a new approval")
    require(actor == "dashboard_owner" or grant["authority"]["approvalMode"] == "phase_delegated", "Exact owner task approval required")
    require(actor == "dashboard_owner" or contract["repositoryBinding"]["policyProfile"] != "harness", "Harness requires exact owner task approval")
    old_hash = q.get("phaseApprovalHash")
    if old_hash is not None: document(db, old_hash, "run_task_approval")
    approval = {"kind": "run_task_approval", "workspaceId": missions.workspace(ledger), "runHash": request["runHash"],
                "generation": grant["generation"], "queueId": q["id"], "contractHash": request["contractHash"],
                "actor": actor, "scopeAssessment": assessment, "at": time.time(), "previousHash": old_hash, "status": "approved"}
    approval_hash = retain(db, "run_task_approval", approval)
    q["phaseApprovalHash"] = approval_hash
    ledger.put(db, "queue", q["id"], q)
    return receipt_in(ledger, db, key, fingerprint, "approve_task", approvalHash=approval_hash, runHash=request["runHash"], queueId=q["id"])


def standard_handoff_scope(db, intent):
    """Historical scope binding, NOT a substitute for current effect authority."""
    approval = document(db, intent["approvalHash"], "run_task_approval")
    grant = document(db, intent["runHash"], "run_authorization")
    contract = document(db, intent["contractHash"], "task_contract")
    require(contract["repositoryBinding"]["policyProfile"] == "standard", "Harness requires its trusted handoff adapter")
    require(grant["actor"] == "dashboard_owner" and grant["settingsPolicy"] == "native_defaults" and
            approval["workspaceId"] == grant["workspaceId"] == intent["workspaceId"] and
            approval["runHash"] == intent["runHash"] and approval["queueId"] == intent["queueId"] and
            approval["contractHash"] == intent["contractHash"] and approval["generation"] == grant["generation"] and
            approval["status"] == "approved", "Exact owner-authorized run and task binding required")
    require(approval["actor"] == "dashboard_owner" or (approval["actor"] == "designated_brain" and
            grant["authority"]["approvalMode"] == "phase_delegated"), "Handoff requires exact owner approval or owner-delegated phase authority")
    return approval


def check_task_in(ledger, db, *, run_hash, queue_id, approval_hash, operation):
    """Check authority inside the future adapter's transaction; not admission."""
    require(db.in_transaction, "Task authority must be checked inside the effect coordinator transaction")
    grant = require_current(ledger, db, run_hash)
    require(operation in missions.OPERATIONS, "Unknown operation")
    q = ledger.get(db, "queue", queue_id)
    require(q.get("phaseApprovalHash") == approval_hash, "Exact current task approval required")
    approval = document(db, approval_hash, "run_task_approval")
    require(approval["workspaceId"] == missions.workspace(ledger) and approval["queueId"] == queue_id and
            approval["runHash"] == run_hash and approval["generation"] == grant["generation"] and
            approval["status"] == "approved", "Task approval is revoked or belongs to another generation")
    require(approval["actor"] == "dashboard_owner" or (approval["actor"] == "designated_brain" and
            grant["authority"]["approvalMode"] == "phase_delegated"), "Task approval actor exceeds run policy")
    _, contract = contract_in(ledger, db, queue_id, approval["contractHash"])
    require(operation in contract["spec"]["operations"], "Operation not declared for this task")
    require(approval["actor"] == "dashboard_owner" or contract["repositoryBinding"]["policyProfile"] != "harness", "Harness requires exact owner task approval")
    return {"authoritySatisfied": True, "executionAuthorized": False, "runHash": run_hash,
            "generation": grant["generation"], "approvalHash": approval_hash, "contractHash": approval["contractHash"],
            "limits": grant["authority"], "estimatedTokens": contract["spec"]["estimatedTokens"],
            "admissionRequired": True, "nativeAdapterAvailable": False}


def revoke_task(ledger, request, *, actor, token=None):
    with ledger.tx() as db:
        _, key, fingerprint, prior = request_in(ledger, db, request, actor, "revoke_task",
            {"queueId", "approvalHash", "reason"}, token)
        if prior: return prior
        reason = missions.text(request["reason"], "Revocation reason")
        q = ledger.get(db, "queue", request["queueId"])
        require(q.get("phaseApprovalHash") == request["approvalHash"], "Exact current approval required")
        old = document(db, request["approvalHash"], "run_task_approval")
        require(old["status"] == "approved" and old["workspaceId"] == missions.workspace(ledger) and old["queueId"] == q["id"], "Approval is not current")
        new = {**old, "actor": actor, "status": "revoked", "reason": reason, "at": time.time(), "previousHash": request["approvalHash"]}
        q["phaseApprovalHash"] = retain(db, "run_task_approval", new)
        ledger.put(db, "queue", q["id"], q)
        return receipt_in(ledger, db, key, fingerprint, "revoke_task", approvalHash=q["phaseApprovalHash"], queueId=q["id"])


def fence_in(ledger, db, meta, reason, command_id=None):
    """Called atomically with safety controls. Corruption must never block Pause."""
    if not managed(meta): return
    try: state = current_in(ledger, db)
    except (ValueError, KeyError, TypeError, AttributeError):
        meta["runAuthorityInvalidated"] = True
        ledger.put(db, "meta", 1, meta)
        return
    if state["status"] == "checkpointed" and not command_id: return
    reasons = sorted(set(state["stopReasons"]) | {reason})
    # A later safe-stop command may attach to an earlier mission/dispatch fence.
    if state["status"] == "fenced" and reasons == state["stopReasons"] and (not command_id or state.get("stopCommandId") == command_id): return
    save_state(ledger, db, meta, {**state, "status": "fenced", "reason": state.get("reason") or reason,
                                "stopReasons": reasons, "stopCommandId": command_id or state.get("stopCommandId"), "checkpointHash": None})


def checkpoint_in(ledger, db, meta, command_id, checkpoint_hash):
    if not managed(meta) or meta.get("runAuthorityInvalidated"): return
    try: state = current_in(ledger, db)
    except (ValueError, KeyError, TypeError, AttributeError):
        meta["runAuthorityInvalidated"] = True
        return
    if state["status"] == "fenced" and state.get("stopCommandId") == command_id:
        save_state(ledger, db, meta, {**state, "status": "checkpointed", "checkpointHash": checkpoint_hash})


def stop(ledger, token, request):
    """Brain stop conditions use the same cooperative worker-checkpoint protocol."""
    with ledger.tx() as db:
        meta, key, fingerprint, prior = request_in(ledger, db, request, "designated_brain", "stop",
                                                   {"runHash", "reason"}, token)
        if prior: return prior
        state = current_in(ledger, db)
        require(state and state["runHash"] == request["runHash"] and state["status"] != "checkpointed", "Exact unfinished run required")
        require(isinstance(request["reason"], str) and request["reason"] in STOP_REASONS, "Unknown brain stop condition")
        from .brain_control import request as brain_request, stopped
        if not stopped(meta):
            command = {"id": "run-stop-" + key, "kind": "brain_stop", "expectedRevision": meta["revision"],
                       "payload": {}, "actor": "designated_brain", "status": "queued", "createdAt": time.time(), "result": None}
            command["fingerprint"] = digest(command)
            # The hook in brain_request captures this same command on the run.
            fence_in(ledger, db, meta, request["reason"])
            brain_request(ledger, db, command, meta)
            ledger.put(db, "commands", command["id"], command)
        else:
            command = {"id": meta["brainControl"]["commandId"]}
            fence_in(ledger, db, meta, request["reason"], command["id"])
        return receipt_in(ledger, db, key, fingerprint, "stop", runHash=request["runHash"], commandId=command["id"])


def read(ledger):
    missions.workspace(ledger)
    with contextlib.closing(ledger.connect()) as db:
        db.execute("BEGIN")
        state = current_in(ledger, db)
        return {"state": state, "executionAuthorized": False, "activationAvailable": False,
                "boundary": "Internal authority only; shared admission and native-effect integration are required."}
