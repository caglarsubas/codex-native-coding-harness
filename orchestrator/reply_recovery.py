"""Owner-reviewed receipt-only wake for an interrupted pre-phase conversation.

No original instruction is resent. Metadata checks are explicit, bounded reads;
only the designated brain can close the original conversation with its reply.
"""
import contextlib
import time

from .core import Refusal, digest, require
from .conversation import pending
from .admission import identifier

KIND = "brain_reply_recovery"
FIELDS = {"messageId", "messageFingerprint", "brainId", "bindingHash", "observation"}
TERMINAL = {"completed", "interrupted", "failed"}
MAX_PAGES = 4
FRESH_SECONDS = 300
BOUNDARY = ("One receipt-only turn for the original received request. Do not repeat its "
            "commands or answer native approvals. No Play, Resume, workers, settings, "
            "source edits, policy changes, identity changes or merges.")


def eligible(state, recovery_id=None, controller=False):
    """Saved-state gates only; no connection, mutation or evidence refresh."""
    meta = state["meta"]
    require(meta.get("paused") is True and not meta.get("standardRun"),
            "Receipt recovery is only for paused pre-phase projects; use phase recovery for an activated run")
    require(not (meta.get("brainControl") or {}).get("desired") == "stopped",
            "Brain Stop takes priority; finish its checkpoint first")
    require(not meta.get("runner") and (controller or not meta.get("controller")),
            "Existing controller or runner must be reconciled first")
    require(not state.get("workers") and not state.get("queue"),
            "Existing task or packet ownership requires its own reconciliation")
    require(not state.get("admission", {}).get("dispatchBlocked") and
            not meta.get("admissionBinding") and meta.get("schemaVersion", 1) == 1,
            "Maintenance and managed-run fences remain in force")
    repos = state.get("repositories") or []
    require(repos and all(r.get("policyProfile") == "standard" for r in repos),
            "Receipt recovery requires a registered standard project")
    commands = state.get("commands") or []
    messages = [c for c in commands if pending(c)]
    require(len(messages) == 1, "One exact unanswered brain request is required")
    original = messages[0]
    n = original.get("notification") or {}
    require(original.get("conversationReceivedAt") and original.get("status") == "processing" and
            original.get("actor") == "dashboard" and original["payload"].get("brainId") == meta.get("brainId") and
            n.get("brainId") == meta["brainId"] and n.get("status") == "accepted" and
            n.get("nativeDelivery") == "owned_turn_start", "Exact received owned-host request required")
    identifier(n.get("nativeTurnId"))
    for c in commands:
        if c["id"] in (original["id"], recovery_id):
            continue
        require(not (c.get("kind") == KIND and c.get("payload", {}).get("messageId") == original["id"]),
                "This request already has its one receipt-recovery attempt; inspect its receipt")
        require(c.get("status") not in ("queued", "processing") and not c.get("needsBrainReceipt"),
                "Another pending control must be reconciled first")
    return original


def catalog(state):
    try:
        original = eligible(state)
        require(state.get("workspace") and
                state.get("brainNotification", {}).get("transport") == "owned_app_server",
                "A reviewed owned Codex host is required")
    except Refusal:
        return {}
    return {"reply_recovery": {"key": "reply_recovery", "kind": KIND,
        "title": "Check missing brain reply", "target": "Designated brain",
        "impact": BOUNDARY, "available": True, "unavailableReason": None,
        "href": "#/conversation", "details": {"messageId": original["id"]}, "payload": {}}}


def observe(proxy, binding, original):
    """Check the exact stored turn twice, bracketed by metadata-only brain reads.

    Absence, unloaded status alone and an ended turn are not effect reconciliation.
    No turn items, command/error bodies or transcripts enter the result.
    """
    brain_id = original["payload"]["brainId"]
    record = binding["brains"].get(brain_id)
    require(record is not None, "Exact reviewed brain binding required")
    turn_id = original["notification"]["nativeTurnId"]

    def identity():
        result = proxy.call("thread/read", {"threadId": brain_id, "includeTurns": False})
        thread = result.get("thread") if isinstance(result, dict) else None
        require(isinstance(thread, dict) and thread.get("id") == brain_id and
                thread.get("cwd") == record["cwd"] and thread.get("projectId") == record["projectId"],
                "Native brain, project or checkout changed")
        status = thread.get("status")
        require(isinstance(status, dict) and status.get("type") in ("idle", "notLoaded"),
                "Brain activity is active or unknown; no receipt wake is eligible")
        return status["type"]

    def turn():
        cursor, seen, turns = None, set(), set()
        for _ in range(MAX_PAGES):
            result = proxy.call("thread/turns/list", {"threadId": brain_id, "cursor": cursor,
                "limit": 64, "sortDirection": "desc", "itemsView": "notLoaded"})
            require(isinstance(result, dict) and isinstance(result.get("data"), list) and
                    len(result["data"]) <= 64 and "nextCursor" in result, "Incomplete native turn page")
            found = None
            for row in result["data"]:
                require(isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"] not in turns,
                        "Duplicate or invalid native turn")
                turns.add(row["id"])
                require(row.get("status") in TERMINAL, "An active or unknown stored turn blocks receipt recovery")
                if row["id"] == turn_id:
                    require(type(row.get("completedAt")) in (int, float) and
                            0 < row["completedAt"] <= time.time(),
                            "Exact turn has no valid completion time")
                    found = {"turnId": turn_id, "status": row["status"], "completedAt": row["completedAt"]}
            if found:
                return found
            cursor = result["nextCursor"]
            require(cursor is not None and isinstance(cursor, str) and 0 < len(cursor) <= 256 and
                    cursor not in seen, "Exact turn absent or pagination incomplete; outcome stays unknown")
            seen.add(cursor)
        raise Refusal("Exact turn outside bounded history; outcome stays unknown")

    before = identity()
    first, second = turn(), turn()
    after = identity()
    require(before == after and first == second, "Native observation changed; inspect before recovery")
    return {**first, "brainId": brain_id, "projectId": record["projectId"],
            "bindingHash": digest(binding), "observedAt": time.time(),
            "activity": after, "effectOutcome": "not_reconciled"}


def check_binding(state, binding):
    brain = state["meta"]["brainId"]
    record = binding["brains"].get(brain) or {}
    from .app_server_wake import NATIVE_APPROVAL_POLICY
    require(record.get("workspaceId") == (state.get("workspace") or {}).get("id") and
            record.get("nativePolicy") == NATIVE_APPROVAL_POLICY and
            any(r.get("projectId") == record.get("catalogProjectId", record.get("projectId"))
                for r in state["repositories"]), "Reviewed workspace and catalog binding changed")


def validate_in(ledger, db, command, meta, actor, controller=False):
    require(actor == "assistant_owner_confirmed", "Receipt recovery needs its signed owner preview")
    p = command["payload"]
    require(set(p) == FIELDS, "Unexpected receipt recovery payload")
    from .enrollment import require_legacy_unfenced
    require_legacy_unfenced(ledger, meta)
    state = {"meta": meta, "repositories": ledger.all(db, "repos"),
             "commands": ledger.all(db, "commands"), "queue": ledger.all(db, "queue"),
             "workers": ledger.all(db, "workers")}
    original = eligible(state, command["id"], controller)
    require(original["id"] == p["messageId"] and original["fingerprint"] == p["messageFingerprint"] and
            meta["brainId"] == p["brainId"], "Original request or brain changed")
    o = p["observation"]
    require(isinstance(o, dict) and set(o) == {"turnId", "status", "completedAt", "brainId", "projectId",
            "bindingHash", "observedAt", "activity", "effectOutcome"} and
            o["turnId"] == original["notification"]["nativeTurnId"] and o["brainId"] == meta["brainId"] and
            o["status"] in TERMINAL and o["bindingHash"] == p["bindingHash"] and
            o["effectOutcome"] == "not_reconciled" and o["activity"] in ("idle", "notLoaded"),
            "Exact bounded native turn observation required")
    if not controller:
        require(type(o["observedAt"]) in (int, float) and 0 <= time.time() - o["observedAt"] <= FRESH_SECONDS,
                "Native observation expired; check the exact request again")
    return original


def fence_development(ledger, db):
    require(not any(c["kind"] == KIND and c.get("status") in ("queued", "processing")
                    for c in ledger.all(db, "commands")),
            "Receipt-only recovery still needs its original reply; do not start or resume development")


def receive(ledger, token, recovery_id):
    from .decisions import authorize_brain
    with ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        command = ledger.get(db, "commands", recovery_id)
        require(command["kind"] == KIND, "Exact receipt recovery request required")
        if command["status"] == "completed":
            return command  # Historical read cannot re-arm a turn.
        original = validate_in(ledger, db, command, meta, command["actor"], controller=True)
        n = command.get("notification") or {}
        require(n.get("status") == "accepted" and n.get("nativeDelivery") == "owned_turn_start" and
                n.get("brainId") == meta["brainId"], "Recovery native delivery is not confirmed")
        if not command.get("receivedAt"):
            command.update(status="processing", receivedAt=time.time(), result="Receipt-only recovery received; original reply pending.")
            ledger.put(db, "commands", recovery_id, command)
            ledger.event(db, "brain_reply_recovery_received", {"id": recovery_id, "messageId": original["id"]})
        return {"request": command, "messageId": original["id"], "boundary": BOUNDARY}


def replied(ledger, db, original):
    for c in ledger.all(db, "commands"):
        if c["kind"] == KIND and c["payload"]["messageId"] == original["id"] and (
                c.get("receivedAt") or not c.get("notification")):
            # A late original reply may win before the recovery send claim. Close
            # that unsent intent without manufacturing a recovery receipt. Once
            # delivery is claimed/uncertain, its separate receipt is still required.
            c.update(status="completed", result="Original brain reply retained; receipt recovery is no longer needed.",
                     completedAt=time.time(), replyHash=original["conversationReply"]["hash"])
            ledger.put(db, "commands", c["id"], c)


def send_check(ledger, binding, command_id, proxy):
    # Same retained owned connection as the subsequent resume/start; no fallback.
    with contextlib.closing(ledger.connect()) as db:
        command = ledger.get(db, "commands", command_id)
        if command["kind"] != KIND:
            return
        meta = ledger.get(db, "meta", 1)
        original = validate_in(ledger, db, command, meta, command["actor"])
        require(digest(binding) == command["payload"]["bindingHash"], "Reviewed host binding changed")
    observation = observe(proxy, binding, original)
    require(all(observation[k] == command["payload"]["observation"][k]
                for k in ("turnId", "status", "completedAt", "brainId", "projectId", "bindingHash")),
            "Reviewed native turn changed")
    with ledger.tx() as db:
        current = ledger.get(db, "commands", command_id)
        meta = ledger.get(db, "meta", 1)
        validate_in(ledger, db, current, meta, current["actor"])
        require(current.get("notification", {}).get("status") == "sending",
                "Exact one-shot recovery delivery claim required")
