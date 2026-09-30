"""Finite, owner-requested preparation through the existing brain conversation.

Reading a plan only signs a preview. The visible Help button confirms that exact
preparation request, never the Review/Play controls that may follow its reply.
"""
from .core import require

PREFIX = "Guided development help (preparation only). "
FOLLOWUP = "Follow up the existing guided preparation request "
SUMMARY = [
    "Check the current phase, saved results, policy blockers and existing task receipts.",
    "Ask the brain to refresh permitted evidence, reconcile existing work and prepare the next safe step.",
    "Show its progress and reply here. Ask you only for a decision or evidence it cannot obtain.",
]
BOUNDARY = ("Preparation uses the existing Codex brain and consumes tokens. It does not start Play, "
            "resume workers, change limits, retry a task or approve a phase.")


def context_prefix(state):
    run = (state.get("standard") or {}).get("run") or {}
    return PREFIX + "Read the latest project ledger first; the saved context is run " + str(run.get("id") or "none") + ", phase " + str(run.get("phaseId") or "none") + ". "


def message(state):
    return context_prefix(state) + (
        "Do the permitted preparation end to end; do not ask the owner to write prompts or navigate pages. "
        "Inspect configured roadmap sources, mission/version, saved results, current policy gates and existing effect receipts. "
        "Classify all blockers: usage/coverage, time, task or parallel limits, scope/authority, native readiness, "
        "unresolved identity/effects, external dependencies and owner decisions. "
        "Refresh registered local usage and, where permitted, the native capability catalog using existing commands. "
        "Reconcile only existing effects through supported read-only observations and retain exact results within existing authority. "
        "Try the available bounded evidence checks before asking the owner for anything. A pending client ID is not a task ID; "
        "missing listing entries do not prove non-creation. Keep ownership, prior consumption and unknown coverage intact. "
        "If the current run is still open, explain the exact safe recovery step; do not replace it with another phase. "
        "If it is settled, reuse an appropriate current draft or prepare the next unfinished bounded roadmap phase for review. "
        "If policy changes are necessary, propose only the minimal exact changes with reasons in a new draft, not applied settings. "
        "Include goal, success criteria, repository/paths, token budget/reserve, duration, task/parallel limits, model and merge policy, "
        "exclusions and stopping checkpoint. Never review or approve a mission, change active limits, reset consumption, "
        "start Play or Resume, implement code, create/continue workers, retry a native effect, merge, install or restart services. "
        "Do not create a scheduler or send another help request. Respect brain stop and Pause; this is one bounded preparation turn. "
        "Receive this exact conversation request and retain a concise reply here before releasing the controller: "
        "Checks completed; Changes prepared; Still blocked; Your next decision. Distinguish observed facts from proposals. "
        "If evidence is unavailable, name the exact missing item and why it cannot be obtained; never claim recovery succeeded. "
        "Return the prepared result or the precise blocker, not instructions to compose another prompt."
    )


def validate_in(ledger, db, meta):
    """Recheck preparation fences in the same transaction as the saved message."""
    from .enrollment import fence_exists
    from .standard import PROTOCOL
    repos = ledger.all(db, "repos")
    require(repos and all(r["policyProfile"] == "standard" for r in repos) and
            (meta["schemaVersion"] == 1 or (meta["schemaVersion"] == 4 and
             (meta.get("standardRun") or {}).get("protocol") == PROTOCOL)) and
            "admissionBinding" not in meta and not fence_exists(ledger.root),
            "Guided help requires an unfenced standard project")
    run = meta.get("standardRun") or {}
    require((meta.get("brainControl") or {}).get("desired") != "stopped" and
            run.get("status") not in ("stopping", "paused"), "The safe checkpoint needs explicit Resume; help cannot resume it")
    require((meta.get("brainHandoff") or {}).get("status") not in ("prepared", "candidate", "received"),
            "Finish the existing brain handoff first")
    require(not any(c["status"] in ("queued", "processing") or c.get("needsBrainReceipt") for c in ledger.all(db, "commands")),
            "Follow the existing request before asking for more preparation")


def plan(state):
    """Closed deterministic next step. No model, evidence collection or writes."""
    from .assistant_journey import catalog
    actions = catalog(state)
    if not actions:
        return {"mode": "unavailable", "title": "Guided help is for standard projects",
                "detail": "This project retains its existing packet approval controls."}
    commands = sorted(state.get("commands", []), key=lambda c: (c.get("createdAt", 0), c["id"]), reverse=True)
    # Follow only this run's exact preparation and its explicit follow-up chain.
    # An old phase reply must not become the new phase's evidence request.
    related = {}
    for c in reversed(commands):
        text = c.get("payload", {}).get("message", "")
        parent = text[len(FOLLOWUP):].split(". ", 1)[0] if text.startswith(FOLLOWUP) else None
        if c.get("payload", {}).get("brainId") == state["meta"].get("brainId") and (text.startswith(context_prefix(state)) or parent in related):
            related[c["id"]] = c
    latest = next(reversed(related.values()), None)
    result = {"requestId": latest["id"] if latest else None, "summary": SUMMARY, "boundary": BOUNDARY}

    def step(mode, title, detail, key=None):
        return {**result, "mode": mode, "title": title, "detail": detail, "key": key}

    s, m = state["standard"], state.get("mission") or {}
    run = s.get("run") or {}
    pause = state.get("workspacePause") or {}
    control = state["meta"].get("brainControl") or {}
    if (control.get("desired") == "stopped" and control.get("phase") == "checkpointing" and
            pause.get("status") == "pausing"):
        codes = {item.get("code") for item in pause.get("blockers", []) if isinstance(item, dict)}
        if codes & {"inventory_missing", "inventory_incomplete"}:
            return step("blocked", "Native checkpoint evidence is missing",
                        "The saved Pause is still checkpointing. The designated brain needs complete native task and descendant evidence. "
                        "If its observation tools are unavailable, this is an operator capability gap; another Help, Play or message cannot clear it. "
                        "Keep the existing stop and ownership intact while the observer is qualified.")
        return step("blocked", "The saved Pause is still checkpointing",
                    "Follow its recorded blockers. Help cannot replace the checkpoint, repeat Pause or resume development.")
    authorized = run.get("recovery") or {}
    recovery_replied = authorized.get("status") == "replied"
    if run.get("status") == "paused" and (s.get("blockers") or
            (state.get("recovery") and not recovery_replied) or
            (authorized and not recovery_replied)):
        if authorized:
            result["requestId"] = authorized["id"]
            if authorized.get("status") in ("queued", "processing"):
                return step("follow", "Recovery preparation is underway",
                            "Follow the one-shot native delivery, brain receipt and reply. The phase remains paused.")
            return step("blocked", "Review the recovery result",
                        "The one-shot preparation turn has ended. Review its reply and the exact remaining decision; no automatic Resume or Play.")
        if actions["phase_recovery"]["available"]:
            from .checkpoint_recovery import pending_message
            held = pending_message(commands, state["meta"]["brainId"])
            result["requestId"] = held["id"] if held else None
            return step("prepare", "Prepare safely from this checkpoint",
                        "Review one bounded preparation wake. We reuse the saved message if present; no phase Resume or worker effect.",
                        "phase_recovery")
        return step("blocked", "Checkpoint recovery needs attention",
                    actions["phase_recovery"]["unavailableReason"])

    pending = next((c for c in commands if c.get("status") in ("queued", "processing") or c.get("needsBrainReceipt") or
                    (c.get("kind") == "reconcile" and c.get("payload", {}).get("message") and not c.get("conversationReply"))), None)
    if pending:
        result["requestId"] = pending["id"]
        return step("follow", "Following your saved request", "No duplicate request will be sent. Delivery, receipt and reply are shown separately.")
    if ((state.get("brainHandoff") or {}).get("handoff") or {}).get("status") in ("prepared", "candidate", "received"):
        return step("blocked", "Brain handoff needs your review", "Help cannot replace a brain or bypass its identity checks.")
    if (state["meta"].get("brainControl") or {}).get("desired") == "stopped":
        return step("blocked", "The brain is stopped", "An explicit brain Resume is required at its safe checkpoint. No help request was sent.")
    if run.get("status") == "stopping":
        return step("blocked", "Waiting for the safe checkpoint", "The existing Pause must settle first. Help does not restart it.")
    if run.get("status") == "paused":
        if actions["phase_resume"]["available"]:
            return step("decision", "Ready to review Resume", "The saved phase keeps its existing scope and consumed usage.", "phase_resume")
        if any("usage" in b.lower() for b in s.get("blockers", [])):
            return step("decision", "Check usage at this checkpoint", "Refresh the evidence without changing limits or resuming the phase.", "usage_check")
        return step("blocked", "The checkpoint still has blockers", "The phase stays paused. Its saved conditions must be resolved before Resume.")
    active = run.get("status") == "running"
    ended_same = run.get("status") in ("completed", "blocked") and run.get("phaseId") == (m.get("document") or {}).get("spec", {}).get("phase", {}).get("id")
    if not active and not ended_same and actions["phase_review"]["available"]:
        return step("decision", "Your phase plan is ready for review", "Review the exact scope, limits and stopping point here. Review does not start development.", "phase_review")
    if not active and not ended_same and actions["phase_play"]["available"]:
        return step("decision", "Ready to review Play", "The prerequisites are recorded. Starting development still needs your separate confirmation.", "phase_play")
    if latest and latest.get("conversationReply") and active and state.get("recovery"):
        value = step("needs_input", "Preparation finished; recovery is still blocked",
                     "The brain's result above explains what it could not resolve. Provide just the missing evidence or decision below; we will prepare the instruction for you.")
        return value
    if actions["phase_help"]["available"]:
        return step("prepare", "Help me continue development", "One preparation request to this project's existing brain. No prompt writing or page switching.", "phase_help")
    return step("blocked", "Preparation is not available", actions["phase_help"]["unavailableReason"])
