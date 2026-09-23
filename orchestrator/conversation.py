"""Durable owner/brain conversation; no execution or transport authority."""
import contextlib
import json
import time

from .core import SHA, digest, require
from .decisions import authorize_brain, text

FIELDS = {"message", "brainId", "confirmed"}
BOUNDARY = "Conversation input, not packet approval or permission to bypass workspace controls."


def is_message(command):
    return command.get("kind") == "reconcile" and "message" in command.get("payload", {})


def pending(command):
    return is_message(command) and not command.get("conversationReply")


def validate(ledger, db, command, meta, actor):
    p = command["payload"]
    require(actor == "dashboard", "Brain messages require the authenticated owner's direct submission")
    require(set(p) == FIELDS and p["confirmed"] is True, "Explicit message confirmation required")
    require(p["brainId"] == meta["brainId"] and bool(meta["brainId"]), "Workspace brain changed; review the recipient")
    text(p["message"], "brain message", 8000)
    require(not any(ord(c) < 32 and c not in "\n\t" for c in p["message"]), "Message contains control characters")
    require(not any(pending(c) for c in ledger.all(db, "commands")), "A brain message is awaiting a reply; use the existing conversation and controls")


def receive_in(ledger, db, command, meta):
    require(is_message(command), "Not a brain conversation request")
    require(command["payload"]["brainId"] == meta["brainId"], "Message belongs to a different brain")
    from .brain_control import stopped
    run = meta.get("standardRun")
    require(not stopped(meta) and not (run and run["status"] in ("stopping", "paused")), "Resume the brain before receiving saved messages")
    if command.get("conversationReply"):
        return command
    if not command.get("conversationReceivedAt"):
        command.update(conversationReceivedAt=time.time(), status="processing", result="Received by workspace brain; reply pending.")
        ledger.put(db, "commands", command["id"], command)
        ledger.event(db, "brain_message_received", {"id": command["id"]})
    return command


def receive(ledger, token, command_id):
    with ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        return receive_in(ledger, db, ledger.get(db, "commands", command_id), meta)


def reply(ledger, token, command_id, result):
    require(isinstance(result, dict) and set(result) == {"message", "artifactIds", "decisionIds"}, "Reply requires message, artifactIds and decisionIds")
    text(result["message"], "brain reply", 12000)
    require(not any(ord(c) < 32 and c not in "\n\t" for c in result["message"]), "Reply contains control characters")
    for key in ("artifactIds", "decisionIds"):
        require(isinstance(result[key], list) and len(result[key]) <= 12 and
                all(isinstance(i, str) and SHA.fullmatch(i) for i in result[key]) and
                len(set(result[key])) == len(result[key]), "Use bounded unique retained references")
    with ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        command = ledger.get(db, "commands", command_id)
        require(is_message(command) and command["payload"]["brainId"] == meta["brainId"], "Exact workspace brain message required")
        if command.get("conversationReply"):
            require(command["conversationReply"]["hash"] == digest(result), "A different reply is already retained")
            return command
        require(command.get("conversationReceivedAt"), "Receive the message before recording its reply")
        for item in result["artifactIds"]:
            ledger.get(db, "artifact_versions", item)
        for item in result["decisionIds"]:
            ledger.get(db, "decisions", item)
        command.update(status="completed", result="Workspace brain reply retained.",
                       conversationReply={**result, "hash": digest(result), "at": time.time()})
        ledger.put(db, "commands", command_id, command)
        ledger.event(db, "brain_message_replied", {"id": command_id, "replyHash": digest(result)})
        return command


def read(ledger, page=0):
    from .conversation_activity import snapshot as activity_snapshot
    require(type(page) is int and 0 <= page <= 1_000_000, "Invalid conversation page")
    with contextlib.closing(ledger.connect()) as db:
        db.execute("BEGIN")
        meta = ledger.get(db, "meta", 1)
        messages = sorted((c for c in ledger.all(db, "commands") if is_message(c)),
                          key=lambda c: (c["createdAt"], c["id"]), reverse=True)
        selected = messages[page * 30:(page + 1) * 30]
        return {"brainId": meta["brainId"], "page": page, "hasOlder": len(messages) > (page + 1) * 30,
                "total": len(messages), "pending": sum(pending(c) for c in messages), "boundary": BOUNDARY,
                "activity": activity_snapshot(db, meta) if page == 0 else None,
                "messages": [{"id": c["id"], "brainId": c["payload"]["brainId"],
                    "message": c["payload"]["message"], "createdAt": c["createdAt"],
                    "receivedAt": c.get("conversationReceivedAt"), "notification": c.get("notification"),
                    "reply": c.get("conversationReply")} for c in reversed(selected)]}


def read_reply(path):
    from .observations import read_regular
    path = path.absolute()
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "Duplicate reply field")
            value[key] = item
        return value
    return json.loads(read_regular(path, path.parent, 65536), object_pairs_hook=unique)
