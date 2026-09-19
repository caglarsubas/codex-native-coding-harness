"""Model suggestions are inert; only a signed owner confirmation submits a control."""
import contextlib
import hashlib
import hmac
import json
import secrets
import time
import uuid

from .core import canonical, digest, require

TTL = 300


def catalog(state, links):
    """Fixed actions/targets, not model-authored commands or browser-owned IDs."""
    meta = state["meta"]
    control = meta.get("brainControl") or {}
    stopped = control.get("desired") == "stopped"
    pending = [c for c in state["commands"] if c["status"] in ("queued", "processing")]
    result = {}

    def add(key, title, kind, payload, impact, view="overview", reason=None, target="Designated brain", details=None):
        if any(c["kind"] == kind and c["payload"] == payload for c in pending):
            reason = "An equivalent request is already awaiting completion."
        result[key] = {"key": key, "title": title, "target": target, "impact": impact,
                       "available": reason is None, "unavailableReason": reason,
                       "href": "#/" + view, "details": details or {}, "kind": kind, "payload": payload}

    brain_missing = None if meta.get("brainId") else "No designated brain is configured."
    add("brain_stop", "Stop brain at a safe checkpoint", "brain_stop", {},
        "Pause new worker dispatch immediately. Ask the brain to preserve evidence and reconcile workers/runner before parking. This does not kill or interrupt tasks.",
        reason=brain_missing or ("The brain is already stopping or stopped." if stopped else None))
    add("brain_resume", "Resume / wake the brain", "brain_resume", {},
        "Notify the existing brain to continue from its recorded state after any active turn. This supersedes a pending stop. Worker dispatch stays unchanged; no packet is approved.",
        reason=brain_missing or ("Brain resume is already requested." if control.get("phase") == "resume_requested" else None),
        details={"recordedBrainPhase": control.get("phase"), "checkpointAt": (control.get("checkpoint") or {}).get("at")})
    add("dispatch_pause", "Pause worker dispatch", "pause", {},
        "Prevent new worker launches. Existing work continues; the brain is not stopped.",
        reason="Worker dispatch is already paused." if meta["paused"] else None)
    add("dispatch_resume", "Resume worker dispatch", "resume", {},
        "Request enabling dispatch of already-approved packets after the brain checks current gates. This can start eligible workers; it is not packet approval.",
        reason=state.get("admission", {}).get("reason") if state.get("admission", {}).get("dispatchBlocked") else
            brain_missing or ("Resume the brain first." if stopped else "Worker dispatch is already enabled." if not meta["paused"] else None))
    add("reconcile", "Request brain reconciliation", "reconcile", {},
        "Ask the designated brain to reconcile recorded controls, ownership and evidence. No new packet approval. Saved until explicit resume if the brain is stopped.",
        reason=brain_missing)
    enabled = meta.get("decisionListener", {}).get("enabled", False)
    for value in (False, True):
        add("periodic_checks" if value else "event_waiting", "Enable periodic idle checks" if value else "Use event-driven waiting",
            "listening", {"enabled": value},
            "Save the supervision preference. The brain applies and observes the native schedule separately. Periodic checks consume model usage; this does not change dispatch or wake a stopped brain.",
            "decisions", "This preference is already selected." if enabled == value else None)
    for i, q in enumerate(sorted(state["queue"], key=lambda q: q["id"])[:8], 1):
        if q["status"] not in ("proposed", "approved"):
            continue
        add("hold_Q" + str(i), "Release packet hold" if q["held"] else "Hold packet", "hold",
            {"queueId": q["id"], "held": not q["held"]},
            "Change only this packet's hold. Releasing a hold can make an already-approved packet eligible for dispatch; all preflight gates still apply.",
            "queue", target=q["repository"] + " / " + q["packetId"], details={"packetDigest": q["packetDigest"], "seedHash": q["seedHash"]})
    for i, w in enumerate(sorted(state["workers"], key=lambda w: w["id"])[:8], 1):
        target = w["repository"] + " / " + w.get("packetId", w["queueId"])
        add("checkpoint_W" + str(i), "Request worker checkpoint", "checkpoint", {"workerId": w["id"]},
            "Ask the brain to request a checkpoint from this existing worker. It does not kill, archive or accept its work.",
            "workers", None if w.get("threadId") else "Native task identity is unresolved.", target)
        add("archive_W" + str(i), "Archive completed worker", "archive", {"workerId": w["id"]},
            "Ask the brain to archive this verified, evidence-preserved worker task. No files or branches are deleted.",
            "workers", None if w.get("threadId") and w["status"] == "complete" and w.get("preserved") and not w.get("archived") else
            "Requires a resolved, completed, preserved and not-yet-archived worker.", target)
    for alias, link in links.items():
        if not alias.startswith("D"):
            continue
        d = next((d for d in state.get("decisions", []) if link["href"] == "#/decisions/" + d["id"]), None)
        if not d or d["status"] != "open":
            continue
        add("answer_" + alias, "Record a free-text decision answer", "decision_response",
            {"decisionId": d["id"], "decisionHash": d["decisionHash"], "optionId": None, "confirmed": True},
            "Save only the exact text you review below as design/input for this version. No option is inferred. This does not approve a packet, grant execution or wake a stopped brain.",
            "decisions/" + d["id"], target=d["spec"]["title"], details={"scope": d["spec"]["scope"], "decisionHash": d["decisionHash"]})
    return result


def public_catalog(actions):
    # IDs, exact hashes, payloads and full scope stay server-side until owner preview.
    return [{k: a[k] for k in ("key", "title", "target", "impact", "available", "unavailableReason")} for a in actions.values()]


def resolve_action(intent, actions, latest_message):
    require(isinstance(intent, dict) and isinstance(intent.get("key"), str) and intent["key"] in actions,
            "Assistant proposed an unsupported action; no control was submitted")
    action = actions[intent["key"]]
    answer = action["kind"] == "decision_response"
    require(set(intent) == ({"key", "text"} if answer else {"key"}), "Unexpected assistant action fields")
    require(action["available"], action["unavailableReason"] or "Action unavailable")
    payload = dict(action["payload"])
    if answer:
        note = intent["text"]
        require(isinstance(note, str) and 0 < len(note.strip()) <= 4000 and note in latest_message,
                "Decision text must be an exact excerpt from your latest message; no inferred answer was saved")
        payload["note"] = note
    return {**action, "payload": payload}


class ActionProposals:
    """Restart/session-bound signatures; no chat transcript or unconfirmed action persisted."""
    def __init__(self):
        self.key = secrets.token_bytes(32)

    def sign(self, document):
        return hmac.new(self.key, canonical(document).encode(), hashlib.sha256).hexdigest()

    def prepare(self, action, state, session):
        now = time.time()
        preview = {k: action[k] for k in ("title", "target", "impact", "href", "details")}
        preview["details"] = {**preview["details"], "designatedBrainId": state["meta"]["brainId"]}
        if action["target"] == "Designated brain":
            preview["target"] = (state.get("brainActivity") or {}).get("title") or "Designated brain"
        document = {"command": {"id": str(uuid.uuid4()), "kind": action["kind"],
                    "payload": action["payload"], "expectedRevision": state["meta"]["revision"]},
                    "brainId": state["meta"]["brainId"], "session": digest(session),
                    "createdAt": now, "expiresAt": now + TTL,
                    "preview": preview}
        return {"document": document, "signature": self.sign(document)}

    def confirm(self, ledger, body, session):
        require(isinstance(body, dict) and set(body) == {"proposal", "confirmed"} and body["confirmed"] is True,
                "Explicit confirmation of the displayed action is required")
        proposal = body["proposal"]
        require(isinstance(proposal, dict) and set(proposal) == {"document", "signature"}, "Invalid action preview")
        doc, signature = proposal["document"], proposal["signature"]
        require(isinstance(signature, str) and hmac.compare_digest(signature, self.sign(doc)),
                "Action preview changed or the server restarted. Ask for a fresh preview.")
        require(doc["session"] == digest(session), "Review and confirm in the same dashboard session")
        command = doc["command"]
        # A lost response can be recovered with the same signed command ID even
        # after expiry/revision changes. Never repeat notification on this path.
        with contextlib.closing(ledger.connect()) as db:
            row = db.execute("SELECT data FROM commands WHERE id=?", (command["id"],)).fetchone()
        if row:
            recorded = json.loads(row["data"])
            require(recorded["fingerprint"] == digest(command), "Recorded command differs from the preview")
            return recorded, False
        require(0 <= time.time() - doc["createdAt"] <= TTL and time.time() <= doc["expiresAt"],
                "Action preview expired. Ask again to review current state.")
        require(ledger.snapshot()["meta"]["brainId"] == doc["brainId"], "Designated brain changed; request a new preview")
        # Revision and every ordinary typed-control gate are checked atomically by submit.
        return ledger.submit(command, actor="assistant_owner_confirmed"), True
