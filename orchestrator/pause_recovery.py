"""One separately reviewed checkpoint wake for a provably pre-turn failed Pause.

Never reset or resend the original delivery claim. This narrow empty-run path
is not effect reconciliation, Resume, phase completion or pilot qualification.
"""
import contextlib
import copy
import math
from pathlib import Path
import sqlite3
import time

from .core import Refusal, digest, require

KIND = "standard_pause_recovery"
FIELDS = {"runId", "phaseId", "pauseId", "pauseFingerprint", "notificationHash",
          "brainId", "bindingHash", "observation", "scopeHash"}
BOUNDARY = ("One checkpoint-only turn for the saved Pause. Development stays stopped. "
            "No Play, Resume, workers, ordinary messages, approvals, source edits, settings, "
            "policy changes, merges or effect retries. Preserve usage and unknown coverage.")
ALLOWANCE = 500_000  # Cooperative one-turn guidance, not a phase/provider cap.
REPLACEMENT_FIELDS = FIELDS | {"replacement"}
CONTINUITY_FIELDS = REPLACEMENT_FIELDS | {"hostContinuity"}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def pre_turn_failure(command):
    n = command.get("notification") or {}
    if (n.get("status") != "unavailable" or
            n.get("wakeId") != digest({"commandId": command["id"]}) or
            any(k in n for k in ("nativeTurnId", "nativeThreadObservation", "nativeDelivery", "nativeTurnStatus")) or
            not finite(n.get("attemptedAt")) or not finite(n.get("finishedAt")) or
            not 0 < n["attemptedAt"] <= n["finishedAt"] <= time.time()):
        return False
    failure = n.get("nativeFailure")
    if failure is None:
        # Closed pre-diagnostic bridge outcome, never arbitrary unavailable prose.
        return n.get("detail") == "Bound Codex app-server inspection failed before a turn was sent."
    from .app_server_wake import WAKE_FAILURE_STAGES
    return (isinstance(failure, dict) and set(failure) in (
            {"version", "stage", "reason", "resumeAttempted", "turnStartAttempted"},
            {"version", "stage", "reason", "resumeAttempted", "turnStartAttempted", "rpcCode"}) and
            type(failure.get("version")) is int and failure["version"] == 1 and
            failure.get("turnStartAttempted") is False and type(failure.get("resumeAttempted")) is bool and
            failure.get("stage") in WAKE_FAILURE_STAGES and failure["stage"] not in ("observation_record", "turn_start") and
            failure.get("reason") in ("connection_lost", "io_unavailable", "validation_failed", "rpc_error",
                                      "unexpected_response", "notification_limit", "deadline_exceeded", "proxy_closed") and
            ("rpcCode" not in failure or (type(failure["rpcCode"]) is int and -32768 <= failure["rpcCode"] <= -32000)))


def scope_hash(run):
    return digest({k: v for k, v in run.items() if k not in ("pauseRecovery", "checkpoint", "status", "revision", "updatedAt")})


def fingerprint(command):
    return digest({k: command[k] for k in ("id", "kind", "payload", "actor", "createdAt")})


def retired_attempt(command, replacement_id, at):
    """A failed disposition, never a brain receipt or a reset delivery claim."""
    result = copy.deepcopy(command)
    result.update(status="failed", replacement={"id": replacement_id, "at": at},
        result="Pre-turn recovery failure retained; separately reviewed replacement saved. No brain receipt is implied.")
    return result


def replacement_context(state, original, recovery_id=None):
    run = state["meta"]["standardRun"]
    permit = run.get("pauseRecovery") or {}
    if not permit or (permit.get("id") == recovery_id and not permit.get("priorAttempt")):
        return None
    archived = permit.get("id") == recovery_id
    if archived:
        saved = permit.get("priorAttempt")
        require(isinstance(saved, dict) and set(saved) == {"command", "permit"}, "Retained failed attempt is incomplete")
        previous, previous_permit = saved["command"], saved["permit"]
    else:
        require(not permit.get("priorAttempt"), "The replacement recovery was already attempted; no third wake is permitted")
        previous_permit = permit
        previous = next((c for c in state.get("commands", []) if c["id"] == permit.get("id")), None)
    require(isinstance(previous, dict) and isinstance(previous_permit, dict), "The failed recovery record is missing")
    p, n = previous.get("payload") or {}, previous.get("notification") or {}
    require(isinstance(p, dict) and isinstance(n, dict), "The failed recovery shape is invalid")
    require(previous.get("kind") == KIND and previous.get("actor") == "assistant_owner_confirmed" and
            previous.get("status") == "queued" and set(p) == FIELDS and
            not any(k in previous for k in ("receivedAt", "completedAt", "checkpointHash", "replacement")) and
            not previous.get("needsBrainReceipt") and pre_turn_failure(previous) and
            isinstance(n.get("nativeFailure"), dict) and n.get("brainId") == state["meta"]["brainId"] and
            finite(previous.get("createdAt")) and previous["createdAt"] <= n["attemptedAt"],
            "The prior recovery lacks closed proof of failure before turn start; inspect it without replay")
    require(set(previous_permit) == {"id", "pauseId", "status", "authorizedAt", "receiveBy", "allowanceTokens", "boundary"} and
            previous_permit.get("id") == previous["id"] and previous_permit.get("pauseId") == original["id"] and
            previous_permit.get("status") == "queued" and previous_permit.get("authorizedAt") == previous["createdAt"] and
            previous_permit.get("receiveBy") == previous["createdAt"]+3600 and
            previous_permit.get("allowanceTokens") == ALLOWANCE and previous_permit.get("boundary") == BOUNDARY,
            "Prior recovery permit changed or already received")
    require(p.get("runId") == run["id"] and p.get("phaseId") == run["phaseId"] and
            p.get("pauseId") == original["id"] and p.get("pauseFingerprint") == fingerprint(original) and
            p.get("notificationHash") == digest(original["notification"]) and
            p.get("brainId") == state["meta"]["brainId"] and p.get("scopeHash") == scope_hash(run),
            "Prior recovery scope, usage, expiry or original Pause changed")
    if archived:
        current = next((c for c in state.get("commands", []) if c["id"] == previous["id"]), None)
        require(current == retired_attempt(previous, recovery_id, permit["authorizedAt"]),
                "Retained failed attempt or its disposition changed")
    return {"command": previous, "permit": previous_permit}


def replacement_binding(context):
    if context is None:
        return None
    c = context["command"]
    return {"id": c["id"], "commandHash": digest(c), "notificationHash": digest(c["notification"]),
            "permitHash": digest(context["permit"])}


def check_replacement(context, binding_hash, observation, continuity=None):
    if continuity is not None:
        from .pause_host_continuity import validate
        validate(continuity, context, binding_hash, observation)
        return
    if context:
        p = context["command"]["payload"]
        require(isinstance(p.get("observation"), dict) and p["bindingHash"] == binding_hash and
                same_turn(p["observation"], observation),
                "Prior recovery host or latest native turn changed; replacement is not permitted")


def eligible(state, recovery_id=None, controller=False):
    meta = state["meta"]
    run = meta.get("standardRun") or {}
    require(run.get("protocol") == "standard_cooperative_v1" and run.get("status") == "stopping" and
            run.get("brainId") == meta.get("brainId") and meta.get("paused") is True,
            "An exact stopping standard phase is required")
    require(not run.get("tasks") and not run.get("merges") and not state.get("workers") and not state.get("queue"),
            "Task, packet or effect ownership needs its own reconciliation")
    require(not meta.get("runner") and (controller or not meta.get("controller")),
            "Release the existing controller and reconcile its runner first")
    require((meta.get("brainControl") or {}).get("desired") != "stopped" and
            (meta.get("brainHandoff") or {}).get("status") not in ("prepared", "candidate", "received"),
            "Brain Stop and handoff take priority")
    require(meta.get("schemaVersion") == 4 and not meta.get("admissionBinding") and
            not state.get("admission", {}).get("dispatchBlocked"), "Managed and strict fences remain in force")
    repos = state.get("repositories") or []
    require(repos and all(r.get("policyProfile") == "standard" for r in repos), "Registered standard project required")
    require(not any(d.get("status") in ("open", "answered") for d in state.get("decisions", [])),
            "An outstanding decision needs its own receipt")
    commands = state.get("commands") or []
    permit = run.get("pauseRecovery") or {}
    received = controller and permit.get("status") == "processing"
    originals = [c for c in commands if c.get("kind") == "standard_pause" and
                 c.get("payload", {}).get("runId") == run["id"] and
                 c.get("status") == ("completed" if received else "queued") and
                 (not received or c["id"] == permit.get("pauseId"))]
    require(len(originals) == 1, "One exact unreceived Pause is required")
    original = originals[0]
    require(original.get("actor") == "dashboard" and original.get("notification", {}).get("brainId") == meta["brainId"] and
            (original.get("completedAt") == permit.get("receivedAt") if received else not original.get("completedAt")) and
            not original.get("receivedAt") and pre_turn_failure(original),
            "The saved Pause lacks proof that no turn was started; reconcile its existing delivery")
    replacement = replacement_context(state, original, recovery_id)
    previous_id = replacement["command"]["id"] if replacement else None
    for c in commands:
        if c["id"] in (original["id"], recovery_id, previous_id):
            continue
        require(not (c.get("kind") == KIND and c.get("payload", {}).get("pauseId") == original["id"]),
                "An unbound recovery attempt needs its own reconciliation")
        require(c.get("status") not in ("queued", "processing") and not c.get("needsBrainReceipt"),
                "Another pending request needs its own reconciliation")
    return original


def availability(state):
    try:
        original = eligible(state)
        prior = replacement_binding(replacement_context(state, original))
        return {"available": True, "pauseId": original["id"], "replacementOf": prior["id"] if prior else None,
                "reason": None}
    except Refusal as exc:
        return {"available": False, "reason": str(exc)}


def observe(proxy, binding, original):
    """Two matching latest-ended reads, bracketed by exact identity/activity.

    No transcript/items, discovery, resume, native write or absence inference.
    Ended metadata does not reconcile any historic effect.
    """
    from .reply_recovery import observe as exact_turn
    brain = original["notification"]["brainId"]
    first = proxy.call("thread/turns/list", {"threadId": brain, "cursor": None,
        "limit": 1, "sortDirection": "desc", "itemsView": "notLoaded"})
    require(isinstance(first, dict) and isinstance(first.get("data"), list) and len(first["data"]) == 1 and
            "nextCursor" in first and isinstance(first["data"][0], dict), "Latest native turn is absent or unknown")
    row = first["data"][0]
    require(isinstance(row.get("id"), str) and 0 < len(row["id"]) <= 100 and row.get("status") == "completed" and
            finite(row.get("completedAt")) and 0 < row["completedAt"] <= time.time(),
            "Latest native turn must be completed; no recovery from unknown activity")
    # Reuse bounded exact-turn identity/privacy checks, and independently verify
    # that no newer completed turn appeared while those checks ran.
    context = {**original, "payload": {"brainId": brain}, "notification": {"nativeTurnId": row["id"]}}
    observed = exact_turn(proxy, binding, context)
    last = proxy.call("thread/turns/list", {"threadId": brain, "cursor": None,
        "limit": 1, "sortDirection": "desc", "itemsView": "notLoaded"})
    require(isinstance(last, dict) and isinstance(last.get("data"), list) and len(last["data"]) == 1 and
            "nextCursor" in last and isinstance(last["data"][0], dict) and
            all(last["data"][0].get(k) == row.get(k) for k in ("id", "status", "completedAt")),
            "Latest native turn changed; inspect before recovery")
    return observed


def same_turn(a, b):
    return all(a.get(k) == b.get(k) for k in ("turnId", "status", "completedAt", "brainId", "projectId", "bindingHash"))


def state_in(ledger, db, meta):
    return {"meta": meta, "repositories": ledger.all(db, "repos"), "commands": ledger.all(db, "commands"),
            "workers": ledger.all(db, "workers"), "queue": ledger.all(db, "queue"), "decisions": ledger.all(db, "decisions")}


def validate_in(ledger, db, command, meta, controller=False):
    from .enrollment import fence_exists, record_in
    require(not fence_exists(ledger.root), "Strict enrollment blocks Pause recovery")
    # Enrollment's shared journal precedes its per-workspace sidecars. A read-only
    # check also fences interrupted staging; do not acquire locks in reverse order.
    try:
        path = Path(ledger.platform_root) / "platform.sqlite3"
        with contextlib.closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as registry_db:
            require(record_in(registry_db) is None, "Strict platform enrollment blocks Pause recovery")
    except (OSError, sqlite3.Error, TypeError, AttributeError) as exc:
        raise Refusal("Registered platform is unavailable; Pause recovery stays blocked") from exc
    p = command["payload"]
    require(command["kind"] == KIND and command["actor"] == "assistant_owner_confirmed" and set(p) in (FIELDS, REPLACEMENT_FIELDS, CONTINUITY_FIELDS),
            "Exact signed Pause recovery required")
    state = state_in(ledger, db, meta)
    original = eligible(state, command["id"], controller)
    replacement = replacement_context(state, original, command["id"])
    require((set(p) in (REPLACEMENT_FIELDS, CONTINUITY_FIELDS) if replacement else set(p) == FIELDS) and
            p.get("replacement") == replacement_binding(replacement), "Review the exact failed attempt separately")
    check_replacement(replacement, p["bindingHash"], p["observation"], p.get("hostContinuity"))
    if "hostContinuity" in p:
        from .pause_host_continuity import check_catalog
        check_catalog(ledger, p["hostContinuity"])
    run, o = meta["standardRun"], p["observation"]
    require(original["id"] == p["pauseId"] and fingerprint(original) == p["pauseFingerprint"] and
            digest(original["notification"]) == p["notificationHash"] and run["id"] == p["runId"] and
            run["phaseId"] == p["phaseId"] and meta["brainId"] == p["brainId"] and scope_hash(run) == p["scopeHash"],
            "Reviewed Pause, run scope or brain changed")
    require(isinstance(o, dict) and set(o) == {"turnId", "status", "completedAt", "brainId", "projectId",
            "bindingHash", "observedAt", "activity", "effectOutcome"} and o["status"] == "completed" and
            o["brainId"] == p["brainId"] and o["bindingHash"] == p["bindingHash"] and
            o["activity"] in ("idle", "notLoaded") and o["effectOutcome"] == "not_reconciled",
            "Exact latest-ended native observation required")
    require(controller or (finite(o.get("observedAt")) and 0 <= time.time()-o["observedAt"] <= 300),
            "Native observation expired; nothing was sent")
    permit = run.get("pauseRecovery") or {}
    require(controller or permit.get("id") != command["id"] or time.time() <= permit["receiveBy"],
            "Pause recovery permit expired; no retry")
    return original


def confirm(registry, ledger, request):
    from .enrollment import record_in
    from .standard import save
    require(set(request) == {"id", "expectedRevision", "payload", "runHash"}, "Unexpected Pause recovery fields")
    with registry.tx() as registry_db, ledger.tx() as db:
        require(record_in(registry_db) is None, "Strict platform enrollment blocks recovery")
        meta = ledger.get(db, "meta", 1)
        require(meta["revision"] == request["expectedRevision"] and digest(meta["standardRun"]) == request["runHash"],
                "Project changed; review a fresh Pause recovery")
        command = {"id": request["id"], "kind": KIND, "actor": "assistant_owner_confirmed", "status": "queued",
            "payload": request["payload"], "fingerprint": digest(request), "createdAt": time.time(),
            "result": "Checkpoint-only recovery saved; development remains stopped."}
        validate_in(ledger, db, command, meta)
        run = meta["standardRun"]
        previous = replacement_context(state_in(ledger, db, meta),
            ledger.get(db, "commands", command["payload"]["pauseId"]), command["id"])
        run["pauseRecovery"] = {"id": command["id"], "pauseId": command["payload"]["pauseId"],
            "status": "queued", "authorizedAt": command["createdAt"], "receiveBy": command["createdAt"]+3600,
            "allowanceTokens": ALLOWANCE, "boundary": BOUNDARY}
        if previous:
            run["pauseRecovery"]["priorAttempt"] = copy.deepcopy(previous)
            ledger.put(db, "commands", previous["command"]["id"],
                retired_attempt(previous["command"], command["id"], command["createdAt"]))
        ledger.put(db, "commands", command["id"], command)
        save(ledger, db, meta, run, "pause_recovery_authorized")
        return command


def send_check(ledger, binding, command_id, proxy):
    from .reply_recovery import check_binding
    with contextlib.closing(ledger.connect()) as db:
        command = ledger.get(db, "commands", command_id)
        meta = ledger.get(db, "meta", 1)
        original = validate_in(ledger, db, command, meta)
        check_binding({**state_in(ledger, db, meta), "workspace": {"id": ledger.workspace_id}}, binding)
        require(digest(binding) == command["payload"]["bindingHash"], "Reviewed host binding changed")
    if "hostContinuity" in command["payload"]:
        from .pause_host_continuity import inspect, registry_view
        state = ledger.snapshot()
        previous = replacement_context(state, original, command_id)
        observed, proof = inspect(registry_view(ledger), ledger.workspace_id, state, previous,
            command["payload"]["hostContinuity"]["previousBinding"], binding, proxy)
        require(proof == command["payload"]["hostContinuity"] and same_turn(observed, command["payload"]["observation"]),
                "Reviewed host continuity changed")
    else:
        require(same_turn(observe(proxy, binding, original), command["payload"]["observation"]),
                "Reviewed native turn changed")
    with ledger.tx() as db:
        current = ledger.get(db, "commands", command_id)
        validate_in(ledger, db, current, ledger.get(db, "meta", 1))
        require(current.get("notification", {}).get("status") == "sending", "Exact one-shot delivery claim required")


def guard(run, operation):
    permit = run.get("pauseRecovery") or {}
    if permit.get("status") in ("queued", "processing"):
        require(operation in ("pause_recovery_receive", "checkpoint"),
                "Use the dedicated Pause recovery receipt; this turn is checkpoint-only")


def receive(ledger, db, meta, run, request_id):
    permit = run.get("pauseRecovery") or {}
    require(permit.get("id") == request_id and permit.get("status") in ("queued", "processing") and
            time.time() <= permit["receiveBy"], "Pause recovery permit absent or expired; no retry")
    command = ledger.get(db, "commands", request_id)
    if permit["status"] == "processing":
        return command  # Exact historical receipt, not a second native permission.
    original = validate_in(ledger, db, command, meta, controller=True)
    n = command.get("notification") or {}
    require(n.get("status") in ("sending", "accepted") and n.get("brainId") == meta["brainId"] and
            n.get("wakeId") == digest({"commandId": request_id}), "Exact native recovery delivery claim required")
    now = time.time()
    original.update(status="completed", completedAt=now,
                    result="Saved Pause received through its separate checkpoint-only recovery; checkpoint pending.")
    command.update(status="processing", receivedAt=now, result="Pause received; safe checkpoint pending.")
    ledger.put(db, "commands", original["id"], original)
    ledger.put(db, "commands", request_id, command)
    permit.update(status="processing", receivedAt=now)
    ledger.event(db, "standard_pause_recovery_received", {"id": request_id, "pauseId": original["id"]})
    return command


def checkpointed(ledger, db, run, request):
    permit = run.get("pauseRecovery") or {}
    if permit.get("status") not in ("queued", "processing"):
        return
    require(permit["status"] == "processing" and request["outcome"] == "paused" and not run.get("tasks") and
            not run.get("merges"), "Receive the exact recovery first; only an empty paused checkpoint is permitted")
    command = ledger.get(db, "commands", permit["id"])
    command.update(status="completed", completedAt=time.time(), checkpointHash=digest(run["checkpoint"]),
                   result="Pause checkpoint retained; development remains paused. Pilot acceptance is not implied.")
    ledger.put(db, "commands", command["id"], command)
    permit.update(status="checkpointed", checkpointAt=command["completedAt"])
