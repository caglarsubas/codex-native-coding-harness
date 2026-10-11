"""Owner-only evidence record for an exhausted, unreceived Pause recovery.

This is NOT another recovery or terminal closeout. Even a successful inspection
leaves the run, original commands, usage, expiry and every uncertainty unchanged.
Historical effects stay unknown; this record cannot satisfy a receipt/checkpoint.
"""
import copy
import contextlib
import json
import time

from .core import Refusal, canonical, digest, require
from .enrollment import fence_exists, record_in
from . import pause_receipt_recovery as receipt
from . import turn_host_continuity as continuity
from .turn_recovery import state_in as base_state_in, observe, membership
from .native_project_assignment import _scope
from .native_read_client import ReadProxy, validate_endpoint

KIND = "standard_ended_recovery_record"
WORKFLOW = "phase_ended_recovery_record"
BOUNDARY = ("Record a blocked, unqualified owner inspection of this ended recovery. "
            "No brain receipt, checkpoint, closeout, ownership release, notification, thread load, "
            "permission response, Play, Resume, retry, usage reset or clock extension. "
            "Current empty tracked terminals do not reconcile historical effects.")
RESULT = ("Inspection recorded; the phase remains stopped and unqualified. "
          "Historical effects and terminal coverage still need independent reconciliation. "
          "Do not repeat Play, Pause or recovery.")


def state_in(ledger, db):
    return {**base_state_in(ledger, db), "decisions": ledger.all(db, "decisions")}


def saved_state(ledger):
    with contextlib.closing(ledger.connect()) as db:
        db.execute("BEGIN")
        return state_in(ledger, db)


def eligible(state):
    run = state["meta"].get("standardRun") or {}
    permit = run.get("pauseReceiptRecovery") or {}
    require(permit.get("status") == "queued", "Only an exhausted recovery without a ledger receipt can use this record")
    original = receipt.eligible(state, permit.get("id"))
    commands = state.get("commands") or []
    recovery = next((c for c in commands if c["id"] == permit.get("id")), None)
    require(recovery and recovery.get("kind") == receipt.KIND and recovery.get("status") == "queued" and
            recovery.get("actor") == "assistant_owner_confirmed" and
            not recovery.get("receivedAt") and not recovery.get("checkpointHash") and
            recovery.get("payload", {}).get("pauseId") == original["id"] and
            recovery["payload"].get("runId") == run["id"] and
            recovery["payload"].get("brainId") == state["meta"]["brainId"] and
            recovery["payload"].get("bindingHash") == original["notification"]["hostBindingHash"],
            "The exact unreceived recovery and original Pause must remain intact")
    n = recovery.get("notification") or {}
    stream, profile = n.get("nativeThreadObservation") or {}, n.get("nativeResumeProfile") or {}
    from .app_server_wake import NATIVE_APPROVAL_POLICY
    require(n.get("status") == "accepted" and n.get("nativeDelivery") == "owned_turn_start" and
            n.get("wakeId") == digest({"commandId": recovery["id"]}) and
            n.get("brainId") == state["meta"]["brainId"] and n.get("hostRunId") == run["id"] and
            n.get("hostBindingHash") == original["notification"]["hostBindingHash"] and
            n.get("nativeTurnStatus") == "completed" and isinstance(n.get("nativeTurnId"), str) and
            n["nativeTurnId"] and not n.get("nativeApprovals") and not n.get("turnRecovery") and
            stream.get("version") == 1 and stream.get("rootThreadId") == state["meta"]["brainId"] and
            stream.get("nativeTurnId") == n["nativeTurnId"] and stream.get("streamStatus") == "closed" and
            stream.get("events") == [] and receipt.finite(stream.get("monitoringEndedAt")) and
            0 < stream["monitoringEndedAt"] <= time.time() and
            profile.get("version") == 1 and profile.get("brainId") == state["meta"]["brainId"] and
            profile.get("commandId") == recovery["id"] and profile.get("nativeTurnId") == n["nativeTurnId"] and
            profile.get("bindingHash") == n["hostBindingHash"] and
            profile.get("requested") == NATIVE_APPROVAL_POLICY and profile.get("resumeAcknowledged") is True,
            "Recovery delivery, completed turn, closed observer and restricted profile must be exact; uncertainty cannot be retried")
    require(not any(c.get("kind") == KIND and c.get("payload", {}).get("recoveryId") == recovery["id"]
                    for c in commands), "This ended recovery already has its owner inspection record")
    return original, recovery


def availability(state):
    try:
        original, recovery = eligible(state)
        return {"available": True, "pauseId": original["id"], "recoveryId": recovery["id"], "reason": None}
    except (Refusal, KeyError, TypeError) as error:
        return {"available": False, "reason": str(error)}


class MetadataProxy(ReadProxy):
    """No write permit exists, including inspection loading or cancellation."""
    def __init__(self, endpoint, scope):
        super().__init__(endpoint, timeout=15)
        self.scope = scope

    def _rpc(self, method, params):
        brain = self.scope["brainId"]
        allowed = {"project/read": {"projectId": self.scope["projectId"]},
                   "thread/read": {"threadId": brain, "includeTurns": False},
                   "thread/turns/list": {"threadId": brain, "cursor": None, "limit": 1,
                                         "sortDirection": "desc", "itemsView": "notLoaded"},
                   "thread/backgroundTerminals/list": {"threadId": brain, "cursor": None, "limit": 64}}
        require((method == "initialize" and self.sequence == 0) or
                (method in allowed and params == allowed[method]), "Ended-recovery records allow only exact metadata reads")
        return super()._rpc(method, params)


def context(state):
    return digest({k: state[k] for k in ("meta", "repositories", "commands", "workers", "queue", "decisions")})


def inspect(registry, ledger, wake, controls):
    """Explicit review/confirmation only. GETs, Help and polling never call this."""
    state = saved_state(ledger)
    original, recovery = eligible(state)
    require(wake is not None and wake.orphan_recovery_idle(),
            "The original observer or native prompt is still active; nothing was resent")
    require(not fence_exists(ledger.root), "Maintenance blocks this inspection")
    with registry.tx() as db:
        require(record_in(db) is None, "Platform maintenance blocks this inspection")
    binding = copy.deepcopy(wake.binding)
    scope = _scope(registry, ledger.workspace_id, binding)
    require(scope["root"] == ledger.root and scope["brainId"] == state["meta"]["brainId"] and
            scope["ledgerRevision"] == state["meta"]["revision"] and scope["hostId"] == "local",
            "Registered project, brain or ledger changed")
    proof, retired = None, None
    if digest(binding) != recovery["notification"]["hostBindingHash"]:
        proof = continuity.proof(controls.prior_binding, binding, recovery, scope)
        retired = continuity.retirement(controls.retired_host, proof["previousBinding"])
    else:
        from .app_server_wake import NATIVE_APPROVAL_POLICY
        require(set(binding["brains"]) == {scope["brainId"]} and
                binding["brains"][scope["brainId"]].get("nativePolicy") == NATIVE_APPROVAL_POLICY,
                "One exact restricted brain binding is required")
        proof = {"version": 1, "previousBinding": binding, "candidateBinding": binding,
                 **{k: scope[k] for k in ("ledgerIdentity", "catalogHash", "hostId")},
                 "projectLocationHash": scope["locationHash"]}
    with MetadataProxy(binding["endpoint"], scope) as proxy:
        observed = observe(proxy, scope, recovery["notification"]["nativeTurnId"], require_loaded=True)
    require(observed["status"] == "completed" and receipt.finite(observed["completedAt"]) and
            0 < observed["completedAt"] <= time.time(), "The exact latest recovery turn must be completed")
    validate_endpoint(binding["endpoint"])
    membership(registry, ledger, binding, scope)
    require(wake.binding == binding and wake.orphan_recovery_idle() and
            context(saved_state(ledger)) == context(state), "Project or host changed during inspection")
    if retired:
        require(controls.prior_binding == proof["previousBinding"] and controls.retired_host == retired,
                "Separately reviewed host continuity changed")
        continuity.retirement(retired, proof["previousBinding"])
    return {"contextHash": context(state), "runHash": digest(state["meta"]["standardRun"]),
            "pauseHash": digest(original), "recoveryHash": digest(recovery),
            "bindingHash": digest(binding), "scopeHash": digest({k: str(v) for k, v in scope.items()}),
            "observation": {**observed, "brainId": scope["brainId"], "projectId": scope["projectId"],
                            "catalogProjectId": scope["catalogProjectId"], "checkout": scope["cwd"],
                            "bindingHash": digest(binding), "historicalTerminalCoverage": "unknown"},
            "hostContinuity": continuity.for_browser(proof), "retiredHost": retired}


def same_evidence(a, b):
    # A fresh confirmation samples again; only the new observation time differs.
    left, right = copy.deepcopy(a), copy.deepcopy(b)
    for value in (left, right):
        value["observation"].pop("observedAt", None)
    require(left == right, "Reviewed identity, original records, usage, expiry or native metadata changed")


def retained(ledger, db, command, request):
    """Historical receipt recovery validates bytes, never renews observations."""
    require(command.get("kind") == KIND and command.get("status") == "completed" and
            command.get("payload", {}).get("requestHash") == digest(request), "Record ID reused")
    row = db.execute("SELECT data FROM snapshots WHERE id=? AND kind=?",
                     (command["payload"].get("recordHash"), KIND)).fetchone()
    require(row is not None, "Owner inspection record is unavailable; no replay or safety inference")
    value = json.loads(row[0])
    require(digest(value) == command["payload"]["recordHash"] and value.get("request") == request and
            value.get("outcome") == "blocked" and value.get("qualification") == "unqualified" and
            value.get("boundary") == BOUNDARY, "Owner inspection record integrity changed")
    return command


def confirm(registry, ledger, request, fresh_evidence, expires_at):
    require(isinstance(request, dict) and set(request) == {"id", "expectedRevision", "recoveryId", "evidence"},
            "Unexpected ended-recovery record fields")
    with registry.tx() as registry_db, ledger.tx() as db:
        prior = db.execute("SELECT data FROM commands WHERE id=?", (request["id"],)).fetchone()
        if prior:
            old = json.loads(prior[0])
            return retained(ledger, db, old, request)
        require(record_in(registry_db) is None and not fence_exists(ledger.root), "Maintenance blocks owner record")
        state = state_in(ledger, db)
        original, recovery = eligible(state)
        evidence = request["evidence"]
        same_evidence(evidence, fresh_evidence)
        from .admission import exact
        exact(evidence, {"contextHash", "runHash", "pauseHash", "recoveryHash", "bindingHash", "scopeHash",
                         "observation", "hostContinuity", "retiredHost"})
        proof = continuity.from_browser(evidence["hostContinuity"])
        validate_endpoint(proof["candidateBinding"]["endpoint"])
        from .pause_host_continuity import check_catalog
        check_catalog(ledger, proof)
        require(digest(proof["candidateBinding"]) == evidence["bindingHash"] and
                digest(proof["previousBinding"]) == recovery["notification"]["hostBindingHash"] and
                proof["previousBinding"]["brains"] == proof["candidateBinding"]["brains"],
                "Preserved original binding and current host identity must remain exact")
        if evidence["retiredHost"]:
            continuity.retirement(evidence["retiredHost"], proof["previousBinding"])
        else:
            require(proof["previousBinding"] == proof["candidateBinding"], "Replacement host retirement is required")
        require(state["meta"]["revision"] == request["expectedRevision"] and
                context(state) == evidence["contextHash"] and recovery["id"] == request["recoveryId"] and
                digest(original) == evidence["pauseHash"] and digest(recovery) == evidence["recoveryHash"] and
                digest(state["meta"]["standardRun"]) == evidence["runHash"], "Project changed; review again")
        observed = evidence["observation"]
        exact(observed, {"turnId", "status", "completedAt", "activity", "trackedTerminals", "terminalCoverage",
                         "observedAt", "effectOutcome", "taskTreeComplete", "brainId", "projectId",
                         "catalogProjectId", "checkout", "bindingHash", "historicalTerminalCoverage"})
        row = proof["candidateBinding"]["brains"][state["meta"]["brainId"]]
        require(observed.get("turnId") == recovery["notification"]["nativeTurnId"] and
                observed["brainId"] == state["meta"]["brainId"] and observed["projectId"] == row["projectId"] and
                observed["catalogProjectId"] == row.get("catalogProjectId", row["projectId"]) and
                observed["checkout"] == row["cwd"] and observed["bindingHash"] == evidence["bindingHash"] and
                receipt.finite(observed["completedAt"]) and 0 < observed["completedAt"] <= time.time() and
                observed.get("status") == "completed" and observed.get("activity") == "idle" and
                type(observed.get("trackedTerminals")) is int and observed["trackedTerminals"] == 0 and
                observed.get("terminalCoverage") == "observed_current_host" and
                observed.get("effectOutcome") == "unknown" and observed.get("taskTreeComplete") is False and
                observed.get("historicalTerminalCoverage") == "unknown" and
                receipt.finite(observed.get("observedAt")) and 0 <= time.time()-observed["observedAt"] <= 300,
                "Fresh loaded-idle current tracker evidence required; historical effects remain unknown")
        now = time.time()
        # A single transaction retains complete private original versions and
        # its local receipt. An interrupted transaction rolls back both. Never
        # edit the old commands, run or checkpoint, or create a notify-able kind.
        require(receipt.finite(fresh_evidence["observation"]["observedAt"]) and
                0 <= time.time()-fresh_evidence["observation"]["observedAt"] <= 300, "Confirmation observation expired")
        require(receipt.finite(expires_at) and time.time() <= expires_at,
                "Preview expired during inspection; review again. Nothing was recorded")
        record = {"version": 1, "request": copy.deepcopy(request), "confirmationEvidence": copy.deepcopy(fresh_evidence),
                  "at": now, "outcome": "blocked",
                  "qualification": "unqualified", "originalPause": original, "exhaustedRecovery": recovery,
                  "preservedRun": state["meta"]["standardRun"], "boundary": BOUNDARY}
        record_hash = digest(record)
        db.execute("INSERT INTO snapshots VALUES (?,?,?)", (record_hash, KIND, canonical(record)))
        command = {"id": request["id"], "kind": KIND, "actor": "assistant_owner_confirmed", "status": "completed",
                   "createdAt": now, "completedAt": now,
                   "payload": {"runId": state["meta"]["standardRun"]["id"], "recoveryId": recovery["id"],
                               "requestHash": digest(request), "recordHash": record_hash}, "result": RESULT}
        ledger.put(db, "commands", command["id"], command)
        ledger.event(db, KIND, {"id": command["id"], "recordHash": record_hash})
        return command
