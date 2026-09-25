"""Conversation entry points for existing owner controls; no new execution path."""
import contextlib
import hmac
import json
import time
import uuid

from .assistant_actions import ActionProposals, TTL
from .core import digest, require
from .recovery import describe

KINDS = {"phase_prepare", "phase_review", "phase_play", "phase_pause", "phase_resume", "usage_check", "codex_check", "brain_message"}
PREPARE_MESSAGE = (
    "Review this project's configured roadmap sources and latest retained results. "
    "Prepare the next unfinished, bounded phase as a mission draft. Include goal, success criteria, "
    "repository and path scope, token budget, parallel-task limit, merge policy, exclusions and stopping "
    "checkpoint. Explain unresolved prerequisites. Preserve consumed usage and previous results. "
    "Save the draft for my review and reply in the project conversation. Do not start Play or approve the phase."
)


def prepare_message(state):
    recovery = state.get("recovery") or describe(state)
    if not recovery or recovery["phaseStatus"] != "blocked":
        return PREPARE_MESSAGE
    return (
        "The recorded phase " + str(recovery["phaseId"] or "unknown") + " stopped at a safety checkpoint. "
        "Its reviewed token budget was " + str(recovery["budget"]) + " with " +
        str(recovery["checkpointReserve"]) + " reserved for checkpointing. "
        "Local telemetry observed " + str(recovery["observedTotal"] if recovery["observedTotal"] is not None else "unknown") +
        " total tokens; coverage is " + recovery["coverage"] + " with " + str(recovery["gapCount"]) +
        " gap(s). First reconcile the exact recorded reason and usage evidence, preserving high-water and unknown coverage. "
        "Do not waive a gap, reset consumption, retry an uncertain native effect, or reuse this phase ID. "
        "Then prepare a genuinely new bounded mission draft for my review, stating the correction, why it is needed, "
        "prior consumption, proposed token budget, reserve, task limits, scope, success criteria and stopping checkpoint. "
        "If the evidence cannot be reconciled, retain the blocker and ask me for the exact missing decision. "
        "Reply with a concise explanation and the proposed next step. Do not review the mission, start Play, or perform worker effects."
    )


def catalog(state):
    s, m = state.get("standard"), state.get("mission") or {}
    repos = state.get("repositories") or []
    if not state.get("workspace") or not s or not repos or any(r.get("policyProfile") != "standard" for r in repos):
        return {}
    run = s.get("run") or {}
    active = run.get("status") in ("running", "stopping", "paused")
    pending = any(c.get("kind") == "reconcile" and "message" in c.get("payload", {}) and
                  not c.get("conversationReply") for c in state.get("commands", []))
    stopped = (state["meta"].get("brainControl") or {}).get("desired") == "stopped"
    handoff = (state.get("brainHandoff") or {}).get("handoff") or {}
    blocked_handoff = handoff.get("status") in ("prepared", "candidate", "received")
    message_reason = ("The previous brain message is awaiting its reply." if pending else
                      "Resume the project at its safe checkpoint before sending another instruction." if stopped or run.get("status") in ("stopping", "paused") else
                      "No project brain is configured." if not state["meta"].get("brainId") else None)
    result = {}

    def add(key, title, impact, reason=None):
        result[key] = {"key": key, "kind": key, "title": title, "impact": impact,
                       "available": reason is None, "unavailableReason": reason,
                       "target": state["workspace"].get("name", "Selected project"),
                       "href": "#/roadmap", "details": {}, "payload": {}}

    recovering = run.get("status") == "blocked" and bool(state.get("recovery") or describe(state))
    add("phase_prepare", "Prepare a recovery proposal" if recovering else "Prepare the next phase",
        ("Ask the project brain to reconcile the stopped phase and draft an exact new plan for your review. "
         "This does not change its controls or start work." if recovering else
         "Ask the project brain to save the next roadmap phase for review."),
        message_reason or ("Finish the existing brain handoff first." if blocked_handoff else
                           "The current phase needs its checkpoint first." if active else None))
    add("brain_message", "Send your instruction to the project brain", "Send the exact text shown below and follow its reply here.", message_reason)
    add("phase_review", "Review this phase plan", "Record your review of the exact scope and limits. Play is a separate confirmation.",
        "Finish the current phase or handoff first." if active or blocked_handoff else
        "A current, unchanged mission draft is required." if m.get("effectiveStatus") != "draft" or m.get("bindingIssues") else None)
    add("phase_play", "Play this phase", "Start the reviewed phase and stop at its agreed checkpoint.",
        "The existing phase needs Pause or Resume, not another Play." if active else
        "Finish the existing brain handoff first." if blocked_handoff else
        None if s.get("available") else s.get("blocker") or "Review the phase and its prerequisites first.")
    add("phase_pause", "Pause this phase", "Stop new work and settle registered tasks at a safe checkpoint.",
        None if run.get("status") == "running" else "There is no running phase to pause.")
    add("phase_resume", "Resume this phase", "Continue the saved phase with its existing limits and consumed usage.",
        "Finish the existing brain handoff first." if blocked_handoff else
        None if run.get("status") == "paused" and not s.get("blockers") else "A paused phase with resolved prerequisites is required.")
    add("usage_check", "Refresh phase usage", "Read registered local session counters. Missing measurements stay unknown; this never resumes the phase.",
        None if run else "Start a reviewed phase before measuring its usage.")
    add("codex_check", "Check Codex readiness", "Ask the brain to refresh available native models and efforts.",
        message_reason or ("The current phase owns its capability catalog." if active else
        "A capability request is already pending." if (s.get("catalogRefresh") or {}).get("status") in ("queued", "processing") else
        None if s.get("catalogRequired") else "The native capability catalog is current."))
    return result


class JourneyProposals(ActionProposals):
    """Signed chat previews compose the same mission, conversation and Play adapters."""
    def __init__(self, runtime):
        super().__init__()
        self.runtime = runtime

    def prepare(self, action, state, session):
        kind = action["kind"]
        if kind not in KINDS:
            return super().prepare(action, state, session)
        require(kind in catalog(state) and catalog(state)[kind]["available"], "Refresh the project before preparing this action")
        ident, now = str(uuid.uuid4()), time.time()
        mission, standard = state.get("mission") or {}, state["standard"]
        preview = {k: action[k] for k in ("title", "target", "impact", "href", "details")}
        request = {}
        if kind == "phase_review":
            request = {"id": ident, "operation": "review", "expectedRevision": mission["revision"],
                       "documentHash": mission["documentHash"], "confirmed": True}
        elif kind in ("phase_play", "phase_pause", "phase_resume"):
            op = kind.removeprefix("phase_")
            run = standard.get("run") or {}
            # Safe Pause must not depend on a still-valid mission document.
            allowance = (max(1, mission["document"]["spec"]["authority"]["tokenBudget"] // 5)
                         if op == "play" else run["brainAllowance"])
            request = self.runtime.standard_controls.preview(self.runtime.ledger, {
                "operation": op, "contextHash": standard["contextHash"],
                "brainAllowance": allowance,
                "durationHours": 8, "measureUsage": op == "play"}, session)
            ident = request["preview"]["id"]
            if op == "play":
                preview["runSettings"] = {k: request["preview"][k] for k in ("brainAllowance", "durationHours", "measureUsage")}
            else:
                preview["retainedRun"] = {"expiresAt": run["expiresAt"], "brainAllowance": run["brainAllowance"]}
        elif kind == "codex_check":
            request = {"id": ident, "contextHash": standard["contextHash"]}
        elif kind == "usage_check":
            request = {"id": ident, "runId": standard["run"]["id"], "contextHash": standard["contextHash"]}
        else:
            message = prepare_message(state) if kind == "phase_prepare" else action["payload"]["message"]
            request = {"id": ident, "kind": "reconcile", "expectedRevision": state["meta"]["revision"],
                       "payload": {"brainId": state["meta"]["brainId"], "message": message, "confirmed": True}}
            preview["message"] = message
        if kind in ("phase_review", "phase_play", "phase_resume"):
            preview["mission"] = {"version": mission["version"], "documentHash": mission["documentHash"],
                                  "spec": mission["document"]["spec"]}
        doc = {"workflow": kind, "id": ident, "request": request, "preview": preview,
               "workspaceId": state["workspace"]["id"], "ledger": digest(str(self.runtime.ledger.db)),
               "session": digest(session), "brainId": state["meta"]["brainId"],
               "createdAt": now, "expiresAt": now + TTL}
        return {"document": doc, "signature": self.sign(doc)}

    def confirm(self, ledger, body, session):
        require(isinstance(body, dict) and isinstance(body.get("proposal"), dict) and
                isinstance(body["proposal"].get("document"), dict), "Invalid action preview")
        doc = body["proposal"]["document"]
        if "workflow" not in doc:
            return super().confirm(ledger, body, session)
        require(set(body) == {"proposal", "confirmed"} and body["confirmed"] is True, "Confirm the displayed action first")
        p = body["proposal"]
        require(set(p) == {"document", "signature"} and isinstance(p["signature"], str) and
                hmac.compare_digest(self.sign(doc), p["signature"]), "Preview changed or server restarted; request a fresh preview")
        require(doc["session"] == digest(session) and doc["ledger"] == digest(str(ledger.db)), "Foreign project or browser preview")
        from . import missions, standard
        require(doc["workspaceId"] == missions.workspace(ledger), "Foreign project preview")
        kind, request = doc["workflow"], doc["request"]
        # Existing adapters own durable replay. Expired previews may recover an
        # exact retained result, never apply a new effect or re-notify a task.
        with contextlib.closing(ledger.connect()) as db:
            prior = db.execute("SELECT data FROM commands WHERE id=?", (doc["id"],)).fetchone()
            mission_prior = db.execute("SELECT data FROM snapshots WHERE id=? AND kind='mission_request'",
                (digest({"kind": "mission_request", "workspaceId": doc["workspaceId"], "id": doc["id"]}),)).fetchone()
            if kind == "usage_check":
                usage_prior = db.execute("SELECT data FROM snapshots WHERE id=? AND kind='standard_usage_request'",
                    (digest({"kind": "standard_usage_request", "id": doc["id"], "runId": request["runId"]}),)).fetchone()
                if usage_prior:
                    return self.result(doc, json.loads(usage_prior[0])), False
        if prior:
            return self.result(doc, json.loads(prior[0])), False
        if not mission_prior:
            require(time.time() <= doc["expiresAt"], "Preview expired; request a fresh preview")
            require(ledger.snapshot()["meta"]["brainId"] == doc["brainId"], "Project brain changed; request a fresh preview")
        if kind == "phase_review":
            result = missions.change(ledger, request)
            return self.result(doc, result), False
        if kind == "usage_check":
            from .brain_memory import refresh
            require(standard.read(ledger)["contextHash"] == request["contextHash"], "Run changed; review a fresh usage request")
            return self.result(doc, refresh(ledger, request["runId"], doc["id"])), False
        if kind in ("phase_play", "phase_pause", "phase_resume"):
            result = self.runtime.standard_controls.confirm(self.runtime.registry, ledger, {**request, "confirmed": True}, session)
        elif kind == "codex_check":
            result = standard.request_catalog_refresh(ledger, request)
        else:
            require(kind in ("phase_prepare", "brain_message"), "Unknown conversation action")
            result = ledger.submit(request, actor="dashboard")
        return self.result(doc, result), True

    @staticmethod
    def result(doc, result):
        return {"workflow": doc["workflow"], "id": doc["id"], "result": result,
                "message": "Phase plan reviewed. You can now review Play here." if doc["workflow"] == "phase_review" else
                           "Usage refreshed. Remaining measured budget is unknown." if doc["workflow"] == "usage_check" and result.get("gaps") else
                           "Usage refreshed. Existing budget and checkpoint gates still apply." if doc["workflow"] == "usage_check" else
                           "Request saved. Follow its receipt and the brain's response here."}
