"""One-shot, owner-reviewed preparation wake for a paused standard phase.

This is not Resume: the old phase remains paused and its consumed usage, expiry,
task ownership and effect fences remain unchanged. The wake can deliver exactly
one saved conversation request for read-only reconciliation and a new draft.
"""
import json
import time

from .core import digest, require
from .enrollment import fence_exists, record_in
from .standard import PROTOCOL, save
from .conversation import pending, validate as validate_message

KIND = "standard_recovery"
SUGGESTED_TOKENS = 500_000
MAX_TOKENS = 2_000_000
RECEIVE_SECONDS = 3600


def pending_message(commands, brain_id):
    messages = [c for c in commands if pending(c)]
    require(len(messages) <= 1, "Multiple pending brain messages need reconciliation")
    message = messages[0] if messages else None
    require(not message or message["payload"].get("brainId") == brain_id,
            "Pending message belongs to another brain; reconcile its identity")
    require(not message or not message.get("notification"),
            "Existing message delivery is already claimed; reconcile it before a recovery wake")
    return message


def instruction(run):
    return (
        "Recovery-only preparation for paused run " + run["id"] + ", phase " + run["phaseId"] + ". "
        "Read the current ledger, checkpoint, registered task and native-effect receipts. "
        "Refresh permitted read-only local usage and exact native evidence; do not treat a missing measurement as zero. "
        "Reconcile existing effects only, preserving uncertainty and ownership. Classify the actual blockers and "
        "prepare a bounded successor mission draft only if the old run can safely reach a terminal checkpoint. "
        "Keep the phase paused; no Play, Resume, worker creation/continuation, merge, policy change, retry, "
        "budget reset or new scope. Save a concise reply: checked facts, unresolved evidence, proposed changes, "
        "and the one exact owner decision needed next. Stop after this single preparation turn."
    )


def eligibility(ledger, db, meta, run):
    require(run and run.get("protocol") == PROTOCOL and run.get("status") == "paused" and
            run.get("brainId") == meta.get("brainId"), "A paused, exact standard phase is required")
    require(meta.get("controller") is None, "Release the existing brain controller before recovery review")
    require((meta.get("brainControl") or {}).get("desired") != "stopped", "Brain Stop needs its own explicit review")
    require(not meta.get("admissionBinding") and not fence_exists(ledger.root),
            "Strict enrollment or admission blocks standard recovery")
    repos = ledger.all(db, "repos")
    require(repos and all(r["policyProfile"] == "standard" for r in repos), "Standard repositories only")
    handoff = meta.get("brainHandoff") or {}
    require(handoff.get("status") not in ("prepared", "candidate", "received"),
            "Finish the existing brain handoff first")
    require(not run.get("recovery"), "This phase already has a one-shot recovery wake; inspect its receipt")
    require(not any(c["kind"] in ("standard_play", "standard_pause", "standard_resume") and
                    c.get("status") in ("queued", "processing") for c in ledger.all(db, "commands")),
            "A phase control still needs its receipt")
    return pending_message(ledger.all(db, "commands"), meta["brainId"])


def confirm(registry, ledger, request, notification_status):
    """Commit the exact signed proposal before its single native notification."""
    require(notification_status.get("status") == "configured" and
            notification_status.get("transport") == "owned_app_server",
            "An owner-bound Codex app-server wake is required; no queue-only recovery send")
    require(isinstance(request, dict) and set(request) == {"id", "messageId", "existingMessageId",
            "messageHash", "message", "runId", "runHash", "brainId", "expectedRevision",
            "allowanceTokens", "usage", "phaseId"}, "Recovery preview fields changed")
    require(type(request["allowanceTokens"]) is int and 1 <= request["allowanceTokens"] <= MAX_TOKENS,
            "Bounded recovery allowance required")
    require(request["messageHash"] == digest(request["message"]), "Recovery instruction changed")
    with registry.tx() as registry_db, ledger.tx() as db:
        previous = db.execute("SELECT data FROM commands WHERE id=?", (request["id"],)).fetchone()
        if previous:
            old = json.loads(previous[0])
            require(old["kind"] == KIND and old["payload"]["messageId"] == request["messageId"] and
                    old["payload"]["runId"] == request["runId"] and
                    old["payload"].get("requestHash") == digest(request), "Recovery request ID reused")
            return old
        require(record_in(registry_db) is None, "Strict platform enrollment blocks recovery")
        meta = ledger.get(db, "meta", 1)
        require(meta["revision"] == request["expectedRevision"] and meta["brainId"] == request["brainId"],
                "Project or brain changed; review a fresh recovery preview")
        run = meta.get("standardRun")
        require(run and run["id"] == request["runId"] and digest(run) == request["runHash"] and
                run["phaseId"] == request["phaseId"], "Run changed; review a fresh recovery preview")
        existing = eligibility(ledger, db, meta, run)
        require((existing or {}).get("id") == request["existingMessageId"],
                "Pending message changed; review a fresh recovery preview")
        if existing:
            require(existing["id"] == request["messageId"] and
                    digest(existing["payload"]["message"]) == request["messageHash"],
                    "Saved message changed; no duplicate was sent")
        else:
            require(request["existingMessageId"] is None and request["messageId"] != request["id"],
                    "A new, distinct conversation request is required")
            message = {"id": request["messageId"], "kind": "reconcile", "expectedRevision": meta["revision"],
                       "payload": {"brainId": meta["brainId"], "message": request["message"], "confirmed": True}}
            validate_message(ledger, db, message, meta, "dashboard")
            message.update(fingerprint=digest(message), actor="dashboard", status="queued",
                           createdAt=time.time(), result=None)
            ledger.put(db, "commands", message["id"], message)
        now = time.time()
        run["recovery"] = {"id": request["id"], "messageId": request["messageId"],
                           "allowanceTokens": request["allowanceTokens"], "authorizedAt": now,
                           "receiveBy": now + RECEIVE_SECONDS, "status": "queued",
                           "usageAtAuthorization": request["usage"],
                           "boundary": "One cooperative preparation turn only; not phase budget, Play, Resume or a provider cap."}
        save(ledger, db, meta, run, "recovery_authorized")
        command = {"id": request["id"], "kind": KIND, "actor": "dashboard", "status": "queued",
                   "createdAt": now, "payload": {"runId": run["id"], "brainId": meta["brainId"],
                   "messageId": request["messageId"], "allowanceTokens": request["allowanceTokens"],
                   "requestHash": digest(request)},
                   "result": "Recovery-only wake saved; phase remains paused."}
        ledger.put(db, "commands", command["id"], command)
        if not existing:
            ledger.event(db, "brain_message_saved_for_recovery", {"id": request["messageId"]})
        ledger.event(db, "standard_recovery_requested", {"id": command["id"], "runId": run["id"]})
        return command


def receive(ledger, db, meta, run, request_id):
    recovery = run.get("recovery") or {}
    require(recovery.get("id") == request_id and recovery.get("status") in ("queued", "processing") and
            run["status"] == "paused" and time.time() < recovery["receiveBy"],
            "Recovery permit is absent, expired or no longer at the paused checkpoint")
    require((meta.get("brainControl") or {}).get("desired") != "stopped", "Brain Stop takes priority")
    command = ledger.get(db, "commands", request_id)
    require(command["kind"] == KIND and command["payload"]["runId"] == run["id"] and
            command["payload"]["brainId"] == meta["brainId"] and command.get("notification") and
            command["notification"]["status"] in ("sending", "accepted", "uncertain"),
            "Exact owner-confirmed native wake claim required")
    message = ledger.get(db, "commands", recovery["messageId"])
    require(pending(message) and message["payload"]["brainId"] == meta["brainId"],
            "Exact pending conversation request required")
    from .conversation import receive_in
    receive_in(ledger, db, message, meta, recovery_id=request_id)
    if recovery["status"] == "queued":
        command.update(status="processing", receivedAt=time.time(), result="Recovery-only request received; reply pending.")
        ledger.put(db, "commands", command["id"], command)
        recovery.update(status="processing", receivedAt=command["receivedAt"])
        ledger.event(db, "standard_recovery_received", {"id": command["id"], "messageId": message["id"]})
    return command


def replied(ledger, db, meta, message):
    run = meta.get("standardRun") or {}
    recovery = run.get("recovery") or {}
    if recovery.get("messageId") != message["id"] or recovery.get("status") != "processing":
        return
    command = ledger.get(db, "commands", recovery["id"])
    command.update(status="completed", completedAt=time.time(),
                   result="Recovery preparation reply retained; phase authority unchanged.")
    ledger.put(db, "commands", command["id"], command)
    recovery.update(status="replied", repliedAt=command["completedAt"])
    save(ledger, db, meta, run, "recovery_replied")
    ledger.event(db, "standard_recovery_replied", {"id": command["id"], "messageId": message["id"]})
