"""One separately reviewed checkpoint wake for a provably pre-turn failed Pause.

Never reset or resend the original delivery claim. This narrow empty-run path
is not effect reconciliation, Resume, phase completion or pilot qualification.
"""
import contextlib
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
    require(not permit or permit.get("id") == recovery_id, "This Pause already has its one recovery attempt; follow its receipt")
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
    for c in commands:
        if c["id"] in (original["id"], recovery_id):
            continue
        require(not (c.get("kind") == KIND and c.get("payload", {}).get("pauseId") == original["id"]),
                "This Pause already has its one recovery attempt; follow its receipt")
        require(c.get("status") not in ("queued", "processing") and not c.get("needsBrainReceipt"),
                "Another pending request needs its own reconciliation")
    return original


def availability(state):
    try:
        original = eligible(state)
        return {"available": True, "pauseId": original["id"], "reason": None}
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
    require(command["kind"] == KIND and command["actor"] == "assistant_owner_confirmed" and set(p) == FIELDS,
            "Exact signed Pause recovery required")
    original = eligible(state_in(ledger, db, meta), command["id"], controller)
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
    require(controller or not permit or time.time() <= permit["receiveBy"], "Pause recovery permit expired; no retry")
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
        run["pauseRecovery"] = {"id": command["id"], "pauseId": command["payload"]["pauseId"],
            "status": "queued", "authorizedAt": command["createdAt"], "receiveBy": command["createdAt"]+3600,
            "allowanceTokens": ALLOWANCE, "boundary": BOUNDARY}
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
