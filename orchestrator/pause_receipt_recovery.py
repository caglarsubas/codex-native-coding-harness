"""One owner-reviewed receipt/checkpoint turn after an ended, unreceived Pause.

An unloaded tracker is unknown. The existing one-shot wake may load for inspection,
but must prove loaded-idle and empty current terminals before starting this turn.
Historical effects and terminal coverage are never inferred from that fresh tracker.
"""
import contextlib
from pathlib import Path
import sqlite3
import time

from .core import Refusal, digest, require
from .pause_recovery import ALLOWANCE, finite, fingerprint, state_in

KIND = "standard_pause_receipt_recovery"
FIELDS = {"runId", "phaseId", "pauseId", "pauseFingerprint", "notificationHash",
          "brainId", "bindingHash", "observation", "scopeHash"}
BOUNDARY = ("One receipt/checkpoint-only turn for the exact ended Pause on its unchanged reviewed host. "
            "Load for inspection if necessary, then require loaded-idle and known-empty current tracked terminals. "
            "Unknown terminal status never permits turn start. No Play, Resume, diagnostic replay, workers, "
            "ordinary messages, approvals, source edits, settings, merge, usage reset or clock extension. "
            "Preserve historical terminal/effect uncertainty; a checkpoint is not pilot acceptance.")


def scope_hash(run):
    return digest({k: v for k, v in run.items() if k not in
                   ("pauseReceiptRecovery", "checkpoint", "status", "revision", "updatedAt")})


def eligible(state, recovery_id=None, controller=False):
    meta, run = state["meta"], state["meta"].get("standardRun") or {}
    require(meta.get("schemaVersion") == 4 and meta.get("paused") is True and
            run.get("protocol") == "standard_cooperative_v1" and run.get("status") == "stopping" and
            run.get("brainId") == meta.get("brainId") and not run.get("ownerCloseout"),
            "An exact stopping standard phase is required")
    require(state.get("repositories") and all(r.get("policyProfile") == "standard" for r in state["repositories"]),
            "Strict Harness cannot use Pause receipt recovery")
    require(not run.get("tasks") and not run.get("merges") and not state.get("workers") and
            not state.get("queue") and not meta.get("runner") and not meta.get("admissionBinding") and
            not state.get("admission", {}).get("dispatchBlocked"), "Recorded ownership needs separate reconciliation")
    require((controller or meta.get("controller") is None) and
            (meta.get("brainControl") or {}).get("desired") != "stopped" and
            (meta.get("brainHandoff") or {}).get("status") not in ("prepared", "candidate", "received"),
            "Controller, Brain Stop or replacement needs its own recovery")
    require(not run.get("pauseRecovery") and not run.get("recovery"), "Another recovery cannot migrate to this path")
    permit = run.get("pauseReceiptRecovery") or {}
    require(not permit or recovery_id == permit.get("id"), "This Pause already has a one-shot receipt recovery")
    received = controller and permit.get("status") == "processing"
    commands = state.get("commands") or []
    originals = [c for c in commands if c.get("kind") == "standard_pause" and
                 c.get("payload", {}).get("runId") == run["id"] and
                 c.get("status") == ("completed" if received else "queued") and
                 (not received or c["id"] == permit.get("pauseId"))]
    require(len(originals) == 1, "One exact unreceived Pause is required")
    original = originals[0]
    n, profile = original.get("notification") or {}, (original.get("notification") or {}).get("nativeResumeProfile") or {}
    stream = n.get("nativeThreadObservation") or {}
    from .app_server_wake import NATIVE_APPROVAL_POLICY
    require(original.get("actor") == "dashboard" and not original.get("receivedAt") and
            (original.get("completedAt") == permit.get("receivedAt") if received else not original.get("completedAt")) and
            n.get("status") == "accepted" and n.get("wakeId") == digest({"commandId": original["id"]}) and
            n.get("brainId") == meta["brainId"] and n.get("hostRunId") == run["id"] and
            n.get("nativeDelivery") == "owned_turn_start" and n.get("nativeTurnStatus") == "completed" and
            isinstance(n.get("nativeTurnId"), str) and n["nativeTurnId"] and not n.get("nativeApprovals") and
            stream.get("version") == 1 and stream.get("rootThreadId") == meta["brainId"] and
            stream.get("nativeTurnId") == n["nativeTurnId"] and stream.get("streamStatus") == "closed" and
            stream.get("events") == [] and finite(stream.get("monitoringEndedAt")) and
            0 < stream["monitoringEndedAt"] <= time.time(),
            "The original Pause must have an acknowledged completed turn and closed observer; uncertainty is not recovery authority")
    require(profile.get("version") == 1 and profile.get("brainId") == meta["brainId"] and
            profile.get("commandId") == original["id"] and profile.get("nativeTurnId") == n["nativeTurnId"] and
            profile.get("bindingHash") == n.get("hostBindingHash") and
            profile.get("requested") == NATIVE_APPROVAL_POLICY and profile.get("resumeAcknowledged") is True,
            "The exact original native profile is required")
    for c in commands:
        if c["id"] in (original["id"], recovery_id):
            continue
        require(not (c.get("kind") == KIND and c.get("payload", {}).get("pauseId") == original["id"]) and
                c.get("status") not in ("queued", "processing") and not c.get("needsBrainReceipt") and
                (c.get("notification") or {}).get("status") not in ("sending", "uncertain"),
                "Other pending or uncertain requests require separate reconciliation")
    require(not any(d.get("status") in ("open", "answered") for d in state.get("decisions", [])),
            "An outstanding decision needs its own receipt")
    return original


def availability(state):
    try:
        original = eligible(state)
        return {"available": True, "pauseId": original["id"], "reason": None}
    except Refusal as error:
        return {"available": False, "reason": str(error)}


def stalled(state, now=None):
    """Explain retained progress only; no RPC, ledger write or retry permission."""
    run = (state.get("standard") or {}).get("run") or {}
    permit = run.get("pauseReceiptRecovery") or {}
    if run.get("status") != "stopping" or permit.get("status") not in ("queued", "processing"):
        return None
    command = next((c for c in state.get("commands", []) if c["id"] == permit.get("id") and c.get("kind") == KIND), None)
    note = (command or {}).get("notification") or {}
    ended = (note.get("nativeDelivery") == "owned_turn_start" and
             note.get("nativeTurnStatus") in ("completed", "failed", "interrupted") and
             (note.get("nativeThreadObservation") or {}).get("streamStatus") == "closed")
    if ended and not command.get("checkpointHash"):
        return {"title": "Recovery ended without its checkpoint" if command.get("receivedAt") else "Recovery ended without a Pause receipt",
                "detail": "This attempt cannot be resent. An operator must repair and verify the runtime, then establish a separately reviewed continuation. "
                          "Historical terminal and effect status remains unknown. Do not repeat Play, Pause or recovery."}
    if finite(permit.get("receiveBy")) and (time.time() if now is None else now) > permit["receiveBy"]:
        return {"title": "Recovery receipt window has ended",
                "detail": "The saved attempt remains one-shot. Its outcome needs operator reconciliation; expiry is not permission to resend. "
                          "Historical terminal and effect status remains unknown."}
    return None


def observe(proxy, binding, original, *, require_loaded=False):
    from .turn_recovery import observe as metadata
    brain = original["notification"]["brainId"]
    row = binding["brains"][brain]
    scope = {"brainId": brain, "projectId": row["projectId"], "cwd": row["cwd"],
             "hostId": "local", "locationHash": digest(["local", row["cwd"]])}
    require(digest(binding) == original["notification"]["hostBindingHash"],
            "Receipt recovery cannot change the original host binding")
    result = metadata(proxy, scope, original["notification"]["nativeTurnId"],
                      require_loaded=require_loaded, allow_unloaded=not require_loaded)
    require(result["status"] == "completed" and finite(result.get("completedAt")) and
            0 < result["completedAt"] <= time.time(), "The exact latest Pause turn must be completed")
    return {**result, "brainId": brain, "projectId": row["projectId"], "bindingHash": digest(binding),
            "historicalTerminalCoverage": "unknown"}


def same_turn(a, b):
    return all(a.get(k) == b.get(k) for k in ("turnId", "status", "completedAt", "brainId", "projectId", "bindingHash"))


def validate_in(ledger, db, command, meta, controller=False):
    from .enrollment import fence_exists, record_in
    require(not fence_exists(ledger.root), "Strict enrollment blocks Pause receipt recovery")
    try:
        path = Path(ledger.platform_root) / "platform.sqlite3"
        with contextlib.closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True)) as registry:
            require(record_in(registry) is None, "Strict platform enrollment blocks recovery")
    except (OSError, sqlite3.Error, TypeError, AttributeError) as error:
        raise Refusal("Registered platform unavailable; recovery stays blocked") from error
    p = command["payload"]
    require(command["kind"] == KIND and command["actor"] == "assistant_owner_confirmed" and set(p) == FIELDS,
            "Exact signed Pause receipt recovery required")
    original = eligible(state_in(ledger, db, meta), command["id"], controller)
    run, observation = meta["standardRun"], p["observation"]
    require(original["id"] == p["pauseId"] and fingerprint(original) == p["pauseFingerprint"] and
            digest(original["notification"]) == p["notificationHash"] and scope_hash(run) == p["scopeHash"] and
            run["id"] == p["runId"] and run["phaseId"] == p["phaseId"] and meta["brainId"] == p["brainId"] and
            original["notification"]["hostBindingHash"] == p["bindingHash"], "Reviewed Pause, host, usage or expiry changed")
    require(isinstance(observation, dict) and set(observation) == {"turnId", "status", "completedAt", "activity",
            "trackedTerminals", "terminalCoverage", "observedAt", "effectOutcome", "taskTreeComplete", "brainId",
            "projectId", "bindingHash", "historicalTerminalCoverage"} and
            observation["turnId"] == original["notification"]["nativeTurnId"] and observation["status"] == "completed" and
            observation["brainId"] == p["brainId"] and observation["bindingHash"] == p["bindingHash"] and
            finite(observation["completedAt"]) and 0 < observation["completedAt"] <= time.time() and
            isinstance(observation["projectId"], str) and bool(observation["projectId"]) and
            observation["effectOutcome"] == "unknown" and observation["taskTreeComplete"] is False and
            observation["historicalTerminalCoverage"] == "unknown" and
            ((observation["activity"] == "notLoaded" and observation["trackedTerminals"] is None and
              observation["terminalCoverage"] == "unknown") or
             (observation["activity"] == "idle" and type(observation["trackedTerminals"]) is int and
              observation["trackedTerminals"] == 0 and observation["terminalCoverage"] == "observed_current_host")),
            "Unloaded terminal coverage must remain unknown")
    permit = run.get("pauseReceiptRecovery") or {}
    require(finite(observation["observedAt"]) and (controller or 0 <= time.time()-observation["observedAt"] <= 300),
            "Observation expired; no retry")
    require(not permit or permit["id"] != command["id"] or time.time() <= permit["receiveBy"], "Recovery permit expired; no retry")
    return original


def confirm(registry, ledger, request):
    from .enrollment import record_in
    from .standard import save
    require(set(request) == {"id", "expectedRevision", "payload", "runHash"}, "Unexpected receipt recovery fields")
    with registry.tx() as registry_db, ledger.tx() as db:
        existing = next((c for c in ledger.all(db, "commands") if c["id"] == request["id"]), None)
        if existing:
            require(existing.get("kind") == KIND and existing.get("fingerprint") == digest(request),
                    "Recovery ID belongs to a different request")
            return existing, False  # Race/replay reads the original receipt only.
        require(record_in(registry_db) is None, "Strict enrollment blocks recovery")
        meta = ledger.get(db, "meta", 1)
        require(meta["revision"] == request["expectedRevision"] and digest(meta["standardRun"]) == request["runHash"],
                "Project changed; review again")
        command = {"id": request["id"], "kind": KIND, "actor": "assistant_owner_confirmed", "status": "queued",
                   "payload": request["payload"], "fingerprint": digest(request), "createdAt": time.time(),
                   "result": "Receipt/checkpoint-only recovery saved; development remains stopped."}
        validate_in(ledger, db, command, meta)
        run = meta["standardRun"]
        run["pauseReceiptRecovery"] = {"id": command["id"], "pauseId": command["payload"]["pauseId"],
             "status": "queued", "authorizedAt": command["createdAt"], "receiveBy": command["createdAt"]+3600,
             "allowanceTokens": ALLOWANCE, "boundary": BOUNDARY, "historicalTerminalCoverage": "unknown", "effectOutcome": "unknown"}
        ledger.put(db, "commands", command["id"], command)
        save(ledger, db, meta, run, "pause_receipt_recovery_authorized")
        return command, True


def send_check(ledger, binding, command_id, proxy, *, require_loaded=False):
    from .reply_recovery import check_binding
    with contextlib.closing(ledger.connect()) as db:
        command, meta = ledger.get(db, "commands", command_id), ledger.get(db, "meta", 1)
        original = validate_in(ledger, db, command, meta)
        check_binding({**state_in(ledger, db, meta), "workspace": {"id": ledger.workspace_id}}, binding)
        require(digest(binding) == command["payload"]["bindingHash"], "Reviewed host changed")
    observation = observe(proxy, binding, original, require_loaded=require_loaded)
    require(same_turn(observation, command["payload"]["observation"]), "Reviewed latest turn changed")
    with ledger.tx() as db:
        current = ledger.get(db, "commands", command_id)
        validate_in(ledger, db, current, ledger.get(db, "meta", 1))
        note = current.get("notification") or {}
        require(note.get("status") == "sending", "Exact one-shot delivery claim required")
        if require_loaded:
            require("receiptRecoveryObservation" not in note, "Inspection already consumed")
            note["receiptRecoveryObservation"] = observation
            ledger.put(db, "commands", command_id, current)


def guard(run, operation):
    if (run.get("pauseReceiptRecovery") or {}).get("status") in ("queued", "processing"):
        require(operation in ("pause_receipt_recovery_receive", "checkpoint"), "This turn is receipt/checkpoint-only")


def receive(ledger, db, meta, run, request_id):
    permit = run.get("pauseReceiptRecovery") or {}
    require(permit.get("id") == request_id and permit.get("status") in ("queued", "processing") and
            time.time() <= permit["receiveBy"], "Exact recovery permit absent or expired")
    command = ledger.get(db, "commands", request_id)
    if permit["status"] == "processing":
        return command
    original = validate_in(ledger, db, command, meta, controller=True)
    note = command.get("notification") or {}
    observation = note.get("receiptRecoveryObservation") or {}
    require(note.get("status") in ("sending", "accepted") and note.get("brainId") == meta["brainId"] and
            note.get("wakeId") == digest({"commandId": request_id}) and
            observation.get("activity") == "idle" and observation.get("trackedTerminals") == 0 and
            observation.get("terminalCoverage") == "observed_current_host" and
            same_turn(observation, command["payload"]["observation"]), "Loaded-idle send-boundary evidence is required")
    now = time.time()
    original.update(status="completed", completedAt=now,
                    result="Pause receipted through its separate ended-turn recovery; historical effects remain unknown.")
    command.update(status="processing", receivedAt=now, result="Pause received; stopped checkpoint pending.")
    ledger.put(db, "commands", original["id"], original)
    ledger.put(db, "commands", request_id, command)
    permit.update(status="processing", receivedAt=now)
    ledger.event(db, "standard_pause_receipt_recovery_received", {"id": request_id, "pauseId": original["id"]})
    return command


def checkpointed(ledger, db, run, request):
    permit = run.get("pauseReceiptRecovery") or {}
    if permit.get("status") not in ("queued", "processing"):
        return
    require(permit["status"] == "processing" and request["outcome"] == "paused" and not run.get("tasks") and
            not run.get("merges") and request["brainObservedTokens"] is None,
            "Receive first; only an empty paused checkpoint preserving usage is permitted")
    run["checkpoint"].update(effectOutcome="unknown", historicalTerminalCoverage="unknown", taskTreeComplete=False,
                             receiptRecoveryId=permit["id"])
    command = ledger.get(db, "commands", permit["id"])
    command.update(status="completed", completedAt=time.time(), checkpointHash=digest(run["checkpoint"]),
                   result="Stopped checkpoint retained; historical effects remain unknown. Not pilot acceptance.")
    ledger.put(db, "commands", command["id"], command)
    permit.update(status="checkpointed", checkpointAt=command["completedAt"])
