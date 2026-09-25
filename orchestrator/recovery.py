"""Read-only, bounded explanations for cooperative phase safety stops.

This is a presentation projection, not a permission or a repair controller.
"""


GAP_LABELS = {
    "invalid_token_record": "A Codex token record could not be validated.",
    "incomplete_or_malformed_record": "A local token record was incomplete or malformed.",
    "counter_reset_or_regression": "A token counter reset or moved backwards.",
    "configured_log_discovery_unavailable": "The configured local token logs were unavailable.",
    "unresolved_native_identity": "A task's native identity is unresolved.",
}


def reason_label(reason):
    """Translate only known control messages; never forward arbitrary exception text."""
    value = reason.lower()
    if "mission changed" in value:
        return "The reviewed mission changed; a new exact phase review is required."
    if "duration expired" in value or "time limit" in value:
        return "The reviewed phase time limit expired."
    if "usage observation expired" in value:
        return "The local usage observation expired."
    if "measure exact run usage" in value:
        return "A fresh phase-scoped usage measurement is required."
    if "usage coverage has gaps" in value:
        return "The phase-scoped usage measurement has unresolved gaps."
    if "observed phase usage reached" in value:
        return "Known usage reached the reviewed checkpoint budget boundary."
    return "An additional recorded execution prerequisite needs review."


def describe(state):
    """Return only recorded facts and closed, non-authorizing recovery guidance."""
    standard = state.get("standard") or {}
    run = standard.get("run") or {}
    if not run or run.get("status") not in ("running", "paused", "blocked"):
        return None
    mission_phase = (((state.get("mission") or {}).get("document") or {}).get("spec") or {}).get("phase") or {}
    if run.get("status") == "blocked" and mission_phase.get("id") not in (None, run.get("phaseId")):
        # The old stop remains in run history, but no longer drives the next-phase CTA.
        return None
    report = run.get("usageReport") or {}
    limits = run.get("limits") or {}
    tokens = report.get("tokens") or {}
    gaps = report.get("gaps") or []
    observed = tokens.get("total_tokens") if report.get("records") else None
    cached = tokens.get("cached_input_tokens") if observed is not None else None
    input_total = tokens.get("input_tokens") if observed is not None else None
    output = tokens.get("output_tokens") if observed is not None else None
    budget = limits.get("tokenBudget")
    reserve = limits.get("checkpointReserveTokens")
    high_water = run.get("usageHighWater", 0)
    known = max(observed or 0, high_water)
    reached = (budget is not None and reserve is not None and (observed is not None or high_water > 0) and
               known + reserve >= budget)
    blockers = standard.get("blockers") or []
    if not gaps and not reached and not blockers and run["status"] != "blocked":
        return None
    if gaps and reached:
        kind, title = "usage_and_budget", "Token boundary reached; evidence incomplete"
        explanation = ("Known usage plus the checkpoint reserve reached the reviewed limit. "
                       "Missing or invalid telemetry also makes the full phase total unknown.")
    elif gaps:
        kind, title = "usage_incomplete", "Usage evidence is incomplete"
        explanation = "Missing or invalid local telemetry makes the remaining measured budget unknown."
    elif reached:
        kind, title = "budget_boundary", "Phase token boundary reached"
        explanation = "Observed usage plus the checkpoint reserve reached the reviewed phase limit."
    elif run["status"] == "blocked":
        kind, title = "checkpoint_blocked", "Phase stopped at a blocker"
        explanation = "The brain recorded a blocked checkpoint; the phase cannot be replayed."
    else:
        kind, title = "control_blocked", "A phase prerequisite needs attention"
        explanation = "New effects must wait until the recorded control blocker is resolved."
    labels = list(dict.fromkeys(GAP_LABELS.get(gap, "Other incomplete local telemetry.") for gap in gaps))[:5]
    reasons = list(dict.fromkeys(reason_label(reason) for reason in blockers))[:5]
    return {
        "kind": kind, "title": title, "explanation": explanation,
        "phaseStatus": run["status"], "phaseId": run.get("phaseId"),
        "registeredTasks": len(run.get("tasks") or []),
        "budget": budget, "checkpointReserve": reserve,
        "observedTotal": observed, "knownUsageLowerBound": known if observed is not None or high_water > 0 else None,
        "cachedInput": cached,
        "uncachedInput": max(0, input_total - cached) if input_total is not None and cached is not None else None,
        "output": output, "observedAt": report.get("collectedAt"),
        "coverage": report.get("coverage", "unknown"), "gapCount": len(gaps), "gapLabels": labels,
        "reasonLabels": reasons,
        "remainingMeasured": (standard.get("measuredUsage") or {}).get("remainingMeasured"),
        "budgetBoundaryReached": reached,
        "requiresOwnerReview": run["status"] == "blocked" or reached,
        "nextStep": ("Ask the brain to reconcile the evidence and draft a genuinely new bounded phase. "
                     "Review its exact changes and Play separately; neither happens automatically."
                     if run["status"] == "blocked" else
                     "Do not Resume this exhausted phase. Reconcile the evidence and review a new bounded phase."
                     if run["status"] == "paused" and reached else
                     "Reconcile the recorded blocker before Resume." if run["status"] == "paused" else
                     "Pause at a safe checkpoint, then reconcile the recorded blocker before another effect."),
        "boundary": "No budget reset, gap waiver, native retry, phase review or Play is authorized by this explanation.",
    }
