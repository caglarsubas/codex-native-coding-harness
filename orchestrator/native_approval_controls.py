"""Owner-reviewed responses to an exact pending, owned app-server request.

The native request is ephemeral and stays out of the ledger and inference
projection. A hash-only decision intent is durable before the one-shot native
response boundary. Losing that response is uncertainty, never retry authority.
"""
import copy
import hmac
import time

from .admission import exact, sha
from .core import Refusal, canonical, digest, require
from .retention_controls import RetentionControls, identity

TTL = 120
BOUNDARY = ("Native permission only. This is not mission, Play, task, budget, "
            "repository, merge or acceptance authority. No decision is sent "
            "until you confirm the exact pending request.")
DECISIONS = {"accept", "decline", "cancel"}


def _scope(ledger, wake):
    require(wake is not None and getattr(ledger, "workspace_id", None),
            "No owner-bound standard Codex host is configured")
    state = ledger.snapshot()
    require(state["repositories"] and all(r["policyProfile"] == "standard" for r in state["repositories"]),
            "Native approval relay is limited to registered standard projects")
    brain_id = state["meta"]["brainId"]
    require(wake.configured(brain_id), "Reviewed native brain binding is unavailable")
    return state, brain_id


def _current(ledger, wake):
    state, brain_id = _scope(ledger, wake)
    pending = wake.pending_approval(brain_id)
    require(isinstance(pending, dict) and pending.get("brainId") == brain_id,
            "No current native permission request; inspect the brain before retrying")
    require(isinstance(pending.get("commandId"), str) and isinstance(pending.get("turnId"), str) and
            isinstance(pending.get("requestHash"), str), "Native request identity is incomplete")
    sha(pending["requestHash"])
    require(len(canonical(pending).encode()) <= 16_000, "Native permission request exceeds the review bound")
    command = next((c for c in state["commands"] if c["id"] == pending["commandId"]), None)
    note = (command or {}).get("notification") or {}
    require(note.get("brainId") == brain_id and note.get("nativeTurnId") == pending["turnId"] and
            note.get("status") == "accepted", "Native request has no matching delivered control")
    require(not any(item.get("requestHash") == pending["requestHash"] for item in note.get("nativeApprovals", [])),
            "This native permission request already has a one-shot decision intent")
    return state, pending


def inspect(ledger, wake):
    """Authenticated owner-only view; this never starts a native connection."""
    if wake is None:
        return {"status": "disabled", "boundary": BOUNDARY}
    try:
        state, pending = _current(ledger, wake)
    except Refusal as error:
        state = ledger.snapshot()
        brain_id = state["meta"]["brainId"]
        entries = [(item.get("claimedAt", 0), item, command["id"])
                   for command in state["commands"]
                   if (command.get("notification") or {}).get("brainId") == brain_id
                   for item in (command.get("notification") or {}).get("nativeApprovals", [])
                   if isinstance(item, dict) and type(item.get("claimedAt")) in (int, float) and
                   item.get("decision") in DECISIONS and item.get("status") in
                   ("claimed", "queued", "response_written", "resolved", "resolved_without_response", "blocked", "uncertain")]
        if entries:
            _, last, command_id = max(entries, key=lambda row: row[0])
            if 0 <= time.time() - last["claimedAt"] <= 86400:
                details = {"claimed": "A one-shot response was claimed but its delivery is not known.",
                           "queued": "The one-shot response is queued on the owned connection; it has not been written yet.",
                           "response_written": "The one-shot response frame was written; native resolution and the brain reply are separate.",
                           "resolved": "Codex reported that the exact native request resolved after the response frame.",
                           "resolved_without_response": "Codex resolved the exact request before this response could be written.",
                           "blocked": "The response was blocked before its native write by a changed safety condition.",
                           "uncertain": "Native response delivery or resolution is uncertain; do not retry."}
                return {"status": "response_claimed", "commandId": command_id,
                        "decision": last["decision"], "delivery": last["status"],
                        "detail": details[last["status"]] + " Do not resend this one-shot decision; the brain reply is separate.",
                        "boundary": BOUNDARY}
        return {"status": "unavailable", "detail": str(error), "boundary": BOUNDARY}
    from .brain_control import stopped
    run = state["meta"].get("standardRun") or {}
    visible = copy.deepcopy(pending)
    # Native prompt shape is only one half of acceptability. Keep the owner
    # view aligned with the current phase even before a new signed preview.
    visible["canAccept"] = bool(visible.get("canAccept") and
                                run.get("status") == "running" and
                                not stopped(state["meta"]))
    return {"status": "pending", "workspaceId": ledger.workspace_id,
            "brainId": state["meta"]["brainId"], "pending": visible, "boundary": BOUNDARY}


class NativeApprovalControls(RetentionControls):
    def preview(self, ledger, wake, body, session):
        body = copy.deepcopy(body)
        exact(body, {"commandId", "requestHash", "decision"})
        sha(body["requestHash"])
        require(body["decision"] in DECISIONS, "Select one supported native decision")
        state, pending = _current(ledger, wake)
        require(body["commandId"] == pending["commandId"] and
                body["requestHash"] == pending["requestHash"], "Native permission request changed")
        require(body["decision"] in pending.get("allowedDecisions", []),
                "The native request does not offer that decision")
        if body["decision"] == "accept":
            require(pending.get("canAccept") is True,
                    "This request cannot be safely approved here; decline or inspect it in Codex")
            run = (state["meta"].get("standardRun") or {})
            from .brain_control import stopped
            require(run.get("status") == "running" and not stopped(state["meta"]),
                    "A stopped or non-running standard phase cannot receive a native approval here")
        now = time.time()
        doc = {"kind": "native_permission_preview", "workspaceId": ledger.workspace_id,
               "ledgerIdentity": identity(ledger), "session": digest(session),
               "ledgerRevision": state["meta"]["revision"],
               "brainId": state["meta"]["brainId"], "commandId": pending["commandId"],
               "turnId": pending["turnId"], "requestHash": pending["requestHash"],
               "pendingHash": digest(pending), "pending": pending,
               "decision": body["decision"], "createdAt": now,
               "expiresAt": min(now + TTL, pending["expiresAt"]), "boundary": BOUNDARY}
        require(len(canonical(doc).encode()) <= 28_000, "Native permission preview exceeds its bound")
        return {"document": doc, "signature": self.sign(doc)}

    def confirm(self, ledger, wake, body, session):
        body = copy.deepcopy(body)
        exact(body, {"proposal", "confirmed"})
        require(body["confirmed"] is True, "Explicit owner confirmation required")
        proposal = body["proposal"]
        exact(proposal, {"document", "signature"}); sha(proposal["signature"])
        doc = proposal["document"]
        require(hmac.compare_digest(proposal["signature"], self.sign(doc)),
                "Native permission preview changed or dashboard restarted")
        require(doc["kind"] == "native_permission_preview" and
                doc["workspaceId"] == ledger.workspace_id and
                doc["ledgerIdentity"] == identity(ledger) and doc["session"] == digest(session),
                "Native permission preview belongs to another session or project")
        require(0 <= time.time() - doc["createdAt"] <= TTL and time.time() <= doc["expiresAt"],
                "Native permission preview expired; inspect the current request")
        state, pending = _current(ledger, wake)
        require(state["meta"]["revision"] == doc["ledgerRevision"],
                "Project authority changed after native permission review")
        require(digest(pending) == doc["pendingHash"] and pending == doc["pending"] and
                pending["brainId"] == doc["brainId"] and pending["commandId"] == doc["commandId"] and
                pending["turnId"] == doc["turnId"] and pending["requestHash"] == doc["requestHash"],
                "Native permission request changed; inspect again")
        decision = doc["decision"]
        require(decision in DECISIONS and decision in pending.get("allowedDecisions", []),
                "Unsupported native decision")
        if decision == "accept":
            from .brain_control import stopped
            require(pending.get("canAccept") is True and not stopped(state["meta"]) and
                    (state["meta"].get("standardRun") or {}).get("status") == "running",
                    "Native approval is no longer allowed in this phase")
        at = time.time()
        with ledger.tx() as db:
            meta = ledger.get(db, "meta", 1)
            from .brain_control import stopped
            require(meta["brainId"] == doc["brainId"] and meta["revision"] == doc["ledgerRevision"] and
                    (decision != "accept" or not stopped(meta) and
                     (meta.get("standardRun") or {}).get("status") == "running"),
                    "Brain or phase changed before native permission confirmation")
            command = ledger.get(db, "commands", doc["commandId"])
            note = command.get("notification") or {}
            require(note.get("status") == "accepted" and note.get("brainId") == doc["brainId"] and
                    note.get("nativeTurnId") == doc["turnId"], "Native control delivery changed")
            previous = note.get("nativeApprovals", [])
            require(isinstance(previous, list) and len(previous) < 16 and
                    not any(item.get("requestHash") == doc["requestHash"] for item in previous),
                    "Native permission was already decided or the review limit was reached")
            entry = {"requestHash": doc["requestHash"], "turnId": doc["turnId"],
                     "method": pending["method"], "decision": decision,
                     "status": "claimed", "claimedAt": at}
            note["nativeApprovals"] = [*previous, entry]
            command["notification"] = note
            ledger.put(db, "commands", command["id"], command)
            ledger.event(db, "native_permission_claimed", {"commandId": command["id"],
                         "requestHash": doc["requestHash"], "decision": decision})
        # The native boundary follows a durable claim. Any error is uncertain;
        # neither this API nor a restarted dashboard may answer it a second time.
        outcome = "uncertain"
        try:
            result = wake.confirm_approval(doc["brainId"], doc["commandId"], doc["requestHash"], decision)
            if isinstance(result, dict) and result.get("status") == "queued":
                outcome = "queued"
        except (OSError, Refusal, RuntimeError, ValueError):
            pass
        with ledger.tx() as db:
            command = ledger.get(db, "commands", doc["commandId"])
            note = command.get("notification") or {}
            entries = note.get("nativeApprovals", [])
            for item in entries:
                if item.get("requestHash") == doc["requestHash"] and item.get("status") == "claimed":
                    item["status"] = outcome
                    item["observedAt"] = time.time()
            note["nativeApprovals"] = entries
            command["notification"] = note
            ledger.put(db, "commands", command["id"], command)
        return {"status": outcome, "requestHash": doc["requestHash"],
                "decision": decision, "nativeCompletionVerified": False,
                "detail": ("The one-shot response was queued to the owned native connection; the brain reply is separate."
                           if outcome == "queued" else "Native response delivery is uncertain. Do not retry or resend the brain request.")}
