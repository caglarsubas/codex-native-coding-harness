"""Owner closeout of an empty expired standard run, never native recovery.

This records an unqualified blocked outcome. It cannot settle task ownership,
clear an uncertain effect, refresh usage, or start the successor preparation.
"""
import json
import time

from .core import Refusal, digest, require
from .enrollment import fence_exists, record_in
from .standard import PROTOCOL, save
from .conversation import pending

KIND = "standard_closeout"
BOUNDARY = ("Close this expired, empty phase as blocked and unqualified. Preserve its usage, "
            "evidence gaps and recovery records. No brain wake, Resume, Play or pilot acceptance.")
SUMMARY = "Expired phase closed as blocked and unqualified by the owner. No development or qualification is claimed."


def eligible(state):
    """Only saved-state checks; native inactivity is checked explicitly later."""
    meta = state["meta"]
    run = meta.get("standardRun") or {}
    require(meta.get("schemaVersion") == 4 and run.get("protocol") == PROTOCOL and
            run.get("status") == "paused" and run.get("brainId") == meta.get("brainId") and
            meta.get("paused") is True, "An exact paused standard phase is required")
    require(type(run.get("expiresAt")) in (int, float) and run["expiresAt"] <= time.time(),
            "Only an expired phase can use this closeout")
    require(not run.get("ownerCloseout"), "This phase already has its closeout receipt")
    require(not run.get("tasks") and not run.get("merges") and not state.get("workers") and
            not state.get("queue") and not meta.get("runner"),
            "Registered tasks, packets or effects need their own reconciliation; empty-phase closeout cannot release them")
    require(meta.get("controller") is None, "Wait for the brain to release its controller")
    require((meta.get("brainControl") or {}).get("desired") != "stopped",
            "Brain Stop needs its own checkpoint; closeout cannot bypass it")
    require(not meta.get("admissionBinding") and not state.get("admission", {}).get("dispatchBlocked"),
            "Maintenance or managed ownership blocks standard closeout")
    require((meta.get("brainHandoff") or {}).get("status") not in ("prepared", "candidate", "received"),
            "Finish the existing brain handoff first")
    repos = state.get("repositories") or []
    require(repos and all(r.get("policyProfile") == "standard" for r in repos), "Standard repositories only")
    recovery = run.get("recovery") or {}
    require(recovery.get("status") == "replied", "Follow the recovery receipt and saved reply before closeout")
    commands = state.get("commands") or []
    require(not any(c.get("status") in ("queued", "processing") or c.get("needsBrainReceipt") or pending(c)
                    for c in commands), "Follow the existing saved request before closeout")
    command = next((c for c in commands if c["id"] == recovery.get("id")), None)
    message = next((c for c in commands if c["id"] == recovery.get("messageId")), None)
    require(command and command.get("kind") == "standard_recovery" and command.get("status") == "completed" and
            command.get("receivedAt") and command["payload"].get("runId") == run["id"] and
            command["payload"].get("brainId") == meta["brainId"] and
            command["payload"].get("messageId") == recovery.get("messageId"),
            "The exact recovery receipt is missing or changed")
    require(message and message.get("status") == "completed" and message.get("conversationReceivedAt") and
            message.get("payload", {}).get("brainId") == meta["brainId"] and message.get("conversationReply"),
            "The exact recovery message and reply are required")
    reply = message["conversationReply"]
    require(reply.get("hash") == digest({k: reply[k] for k in ("message", "artifactIds", "decisionIds")}),
            "Recovery reply integrity is unavailable")
    n = command.get("notification") or {}
    require(n.get("status") == "accepted" and n.get("nativeDelivery") == "owned_turn_start" and
            n.get("brainId") == meta["brainId"] and isinstance(n.get("nativeTurnId"), str) and n["nativeTurnId"],
            "Recovery native delivery is unconfirmed; reconcile the existing attempt")
    return command


def availability(state):
    try:
        eligible(state)
        require(state.get("brainNotification", {}).get("transport") == "owned_app_server",
                "Closeout needs an explicit ended-turn read from the reviewed owned host")
        return {"available": True, "reason": None}
    except (Refusal, KeyError, TypeError) as error:
        return {"available": False, "reason": str(error)}


def observe(proxy, binding, command):
    """Bracket two latest-turn reads; no items, commands or conversation bodies."""
    brain = command["payload"]["brainId"]
    record = binding["brains"][brain]
    turn_id = command["notification"]["nativeTurnId"]

    def identity():
        thread = proxy.call("thread/read", {"threadId": brain, "includeTurns": False}).get("thread")
        require(isinstance(thread, dict) and thread.get("id") == brain and
                thread.get("cwd") == record["cwd"] and thread.get("projectId") == record["projectId"],
                "Native brain, project or checkout changed; phase stays paused")
        require(isinstance(thread.get("status"), dict) and
                thread["status"].get("type") in ("idle", "notLoaded"),
                "Brain activity is active or unknown; wait for the existing turn")
        return thread["status"]["type"]

    def latest():
        page = proxy.call("thread/turns/list", {"threadId": brain, "cursor": None,
            "limit": 64, "sortDirection": "desc", "itemsView": "notLoaded"})
        require(isinstance(page, dict) and isinstance(page.get("data"), list) and 1 <= len(page["data"]) <= 64 and
                "nextCursor" in page, "Exact latest native turn is unavailable; phase stays paused")
        require(all(isinstance(row, dict) and row.get("status") in ("completed", "interrupted", "failed")
                    for row in page["data"]), "Active or unknown native history needs reconciliation")
        row = page["data"][0]
        require(isinstance(row, dict) and row.get("id") == turn_id and row.get("status") == "completed" and
                type(row.get("completedAt")) in (int, float) and 0 < row["completedAt"] <= time.time(),
                "The exact recovery turn has not completed or a later turn exists; inspect it before closeout")
        return {"turnId": turn_id, "status": "completed", "completedAt": row["completedAt"]}

    before, first = identity(), latest()
    second, after = latest(), identity()
    require(before == after and first == second, "Native state changed during inspection; check again")
    return {**first, "activity": after, "brainId": brain, "projectId": record["projectId"],
            "bindingHash": digest(binding), "observedAt": time.time(), "effectOutcome": "unqualified"}


def confirm(registry, ledger, request):
    require(isinstance(request, dict) and set(request) == {"id", "expectedRevision", "runId", "runHash",
            "brainId", "recoveryId", "replyHash", "observation"}, "Closeout preview fields changed")
    with registry.tx() as registry_db, ledger.tx() as db:
        prior = db.execute("SELECT data FROM commands WHERE id=?", (request["id"],)).fetchone()
        if prior:
            old = json.loads(prior[0])
            require(old["kind"] == KIND and old["payload"]["requestHash"] == digest(request), "Closeout ID reused")
            return old
        require(record_in(registry_db) is None and not fence_exists(ledger.root), "Maintenance blocks closeout")
        meta = ledger.get(db, "meta", 1)
        require(meta["revision"] == request["expectedRevision"] and meta["brainId"] == request["brainId"],
                "Project changed; review a fresh closeout")
        run = meta.get("standardRun") or {}
        require(run.get("id") == request["runId"] and digest(run) == request["runHash"],
                "Run changed; review a fresh closeout")
        state = {"meta": meta, "repositories": ledger.all(db, "repos"), "commands": ledger.all(db, "commands"),
                 "workers": ledger.all(db, "workers"), "queue": ledger.all(db, "queue")}
        recovery = eligible(state)
        reply = ledger.get(db, "commands", run["recovery"]["messageId"])["conversationReply"]
        require(recovery["id"] == request["recoveryId"] and reply["hash"] == request["replyHash"],
                "Recovery result changed; review again")
        observation = request["observation"]
        require(observation.get("turnId") == recovery["notification"]["nativeTurnId"] and
                observation.get("status") == "completed" and observation.get("brainId") == meta["brainId"] and
                observation.get("effectOutcome") == "unqualified" and
                0 <= time.time() - observation["observedAt"] <= 300,
                "Fresh exact ended-turn observation required")
        now = time.time()
        # Keep the old checkpoint verbatim and every usage field unchanged. This
        # is an owner outcome, not a brain checkpoint, settlement or acceptance.
        run["ownerCloseout"] = {"requestId": request["id"], "at": now, "outcome": "blocked",
            "qualification": "unqualified", "previousCheckpoint": run.get("checkpoint"),
            "recoveryId": recovery["id"], "replyHash": reply["hash"], "observation": observation,
            "boundary": BOUNDARY}
        run["status"] = "blocked"
        run["checkpoint"] = {"summary": SUMMARY, "reasonCodes": ["duration"], "at": now}
        save(ledger, db, meta, run, "owner_closeout")
        command = {"id": request["id"], "kind": KIND, "actor": "assistant_owner_confirmed", "status": "completed",
            "createdAt": now, "completedAt": now, "payload": {"runId": run["id"], "requestHash": digest(request)},
            "result": "Stopped phase closed as blocked and unqualified. Next: Help me continue development prepares a new proposal; Review and Play remain separate."}
        ledger.put(db, "commands", command["id"], command)
        ledger.event(db, "standard_closeout_retained", {"id": command["id"], "runId": run["id"]})
        return command
