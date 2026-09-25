"""Bounded, read-only explanations for cooperative phase safety stops.

Fixed labels only: brain-reported codes are leads, not verified policy causes.
"""
import time


GAP_LABELS = {
    "invalid_token_record": "A Codex token record could not be validated.",
    "incomplete_or_malformed_record": "A local token record was incomplete or malformed.",
    "counter_reset_or_regression": "A token counter reset or moved backwards.",
    "configured_log_discovery_unavailable": "The configured local token logs were unavailable.",
    "unresolved_native_identity": "A task's native identity is unresolved.",
}


CHECKPOINT_REASONS = {
    "token_budget": ("Reviewed token boundary", "Review measured usage and the next phase limit.", "policy_review"),
    "usage_evidence": ("Usage evidence incomplete", "Refresh or reconcile the missing observation.", "evidence"),
    "duration": ("Reviewed duration ended", "Review the time limit for a new phase.", "policy_review"),
    "task_limit": ("Reviewed task count reached", "Review completed tasks and the next phase task limit.", "policy_review"),
    "parallel_capacity": ("Parallel capacity occupied", "Settle or reconcile registered tasks before more work.", "native_reconciliation"),
    "scope": ("Requested work outside reviewed scope", "Review the exact repository, path and operation scope.", "policy_review"),
    "model_catalog": ("Model or effort unavailable", "Refresh the native catalog and review the selected setting.", "evidence"),
    "repository_identity": ("Repository identity changed", "Verify the registered repository before new effects.", "native_reconciliation"),
    "merge_prerequisite": ("Merge prerequisite unresolved", "Reconcile the exact PR and required evidence.", "native_reconciliation"),
    "external_dependency": ("External prerequisite unresolved", "Identify the external owner and evidence needed.", "external"),
    "owner_decision": ("Owner decision required", "Present the exact choice and its consequences.", "owner_decision"),
    "other_policy": ("Other policy stop reported", "Inspect the exact recorded policy and evidence.", "investigate"),
}


def issue(code, label, next_step, source, route):
    return {"code": code, "label": label, "nextStep": next_step,
            "source": source, "route": route}


def platform_issue(reason):
    """Translate only known platform refusals; never forward arbitrary text."""
    value = reason.lower()
    known = (
        ("mission changed", "mission_changed", "Reviewed mission changed", "Review an exact new phase.", "policy_review"),
        ("duration expired", "duration", "Reviewed duration ended", "Review the time limit for a new phase.", "policy_review"),
        ("usage observation expired", "usage_stale", "Usage observation expired", "Refresh phase-scoped usage.", "evidence"),
        ("measure exact run usage", "usage_missing", "Usage measurement required", "Measure phase-scoped usage.", "evidence"),
        ("usage coverage has gaps", "usage_gap", "Usage coverage has gaps", "Reconcile missing local telemetry.", "evidence"),
        ("observed phase usage reached", "token_budget", "Reviewed token boundary", "Review measured usage and the next phase limit.", "policy_review"),
        ("native model/effort catalog", "model_catalog", "Native model or effort catalog unavailable", "Ask the brain for a fresh native catalog.", "evidence"),
        ("reconcile existing workers", "legacy_worker", "Existing worker ownership unresolved", "Reconcile existing workers.", "native_reconciliation"),
        ("hold legacy approved packets", "legacy_queue", "Legacy approved work remains", "Review the existing approved queue.", "native_reconciliation"),
        ("legacy dispatch must stay paused", "legacy_dispatch", "Legacy dispatch state conflicts", "Review dispatch ownership and setup.", "investigate"),
        ("review an exact mission", "mission_review", "Exact mission review required", "Review the current phase plan.", "policy_review"),
        ("phase-delegated authority", "authority_mode", "Approval authority differs from reviewed mode", "Review the exact authority mode.", "policy_review"),
        ("cooperative merge needs", "merge_policy", "Merge authority is not reviewed", "Review the exact merge policy.", "policy_review"),
        ("only all-standard workspaces", "project_profile", "Project profile is incompatible", "Review the project profile; do not switch protocols implicitly.", "investigate"),
        ("strict or enrolled workspaces", "strict_enrollment", "Strict enrollment blocks cooperative control", "Use the strict workflow; do not bypass enrollment.", "investigate"),
    )
    for marker, code, label, step, route in known:
        if marker in value:
            return issue(code, label, step, "platform", route)
    return issue("unclassified_prerequisite", "An execution prerequisite needs review",
                 "Inspect the exact local refusal and supporting evidence.", "platform", "investigate")


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
    issues = []
    if reached:
        issues.append(issue("token_budget", "Reviewed token boundary reached",
                            "Reconcile measured usage and review a successor phase if needed.", "platform", "policy_review"))
    if gaps:
        issues.append(issue("usage_gap", "Usage coverage incomplete",
                            "Reconcile missing local observations; remaining measured budget is unknown.", "platform", "evidence"))
    if type(run.get("expiresAt")) in (int, float) and run["expiresAt"] <= time.time():
        issues.append(issue("duration", "Reviewed duration ended",
                            "Review the time limit for a new phase.", "platform", "policy_review"))
    issues.extend(platform_issue(reason) for reason in standard.get("blockers") or [])
    if standard.get("blocker"):
        issues.append(platform_issue(standard["blocker"]))
    if run["status"] in ("paused", "blocked"):
        for code in (run.get("checkpoint") or {}).get("reasonCodes") or []:
            if code in CHECKPOINT_REASONS:
                label, step, route = CHECKPOINT_REASONS[code]
                issues.append(issue(code, label, step, "brain_reported", route))
    if run["status"] in ("paused", "blocked"):
        if len(run.get("tasks") or []) >= limits.get("maxTasks", float("inf")):
            issues.append(issue("task_limit", "Reviewed task count reached",
                                "Review completed work and the next phase task limit.", "platform", "policy_review"))
        if any(t.get("status") not in ("completed", "failed", "not_created") for t in run.get("tasks") or []):
            issues.append(issue("unresolved_task", "Registered native task unresolved",
                                "Reconcile its exact task receipt before another effect.", "platform", "native_reconciliation"))
        if any(m.get("status") in ("prepared", "issued", "uncertain") for m in run.get("merges") or []):
            issues.append(issue("unresolved_merge", "Native merge handoff unresolved",
                                "Reconcile the exact PR before another effect.", "platform", "native_reconciliation"))
    unique = list({(row["code"], row["source"]): row for row in issues}.values())
    if not unique and run["status"] != "blocked":
        return None
    if not unique:
        unique = [issue("unclassified_checkpoint", "Blocked checkpoint needs investigation",
                        "Inspect the exact checkpoint and policy before proposing a change.", "brain_recorded", "investigate")]
    shown = unique[:8]
    usage_related = any(row["code"].startswith("usage_") or row["code"] == "token_budget" for row in unique)
    non_usage = any(not (row["code"].startswith("usage_") or row["code"] == "token_budget") for row in unique)
    if non_usage and usage_related:
        kind, title = "multiple_policy_conditions", "Multiple phase conditions need review"
    elif gaps and reached:
        kind, title = "usage_and_budget", "Token boundary reached; evidence incomplete"
    elif gaps:
        kind, title = "usage_incomplete", "Usage evidence is incomplete"
    elif reached:
        kind, title = "budget_boundary", "Phase token boundary reached"
    elif run["status"] == "blocked":
        kind, title = "checkpoint_blocked", "Phase stopped at a blocker"
    else:
        kind, title = "control_blocked", "A phase prerequisite needs attention"
    labels = list(dict.fromkeys(GAP_LABELS.get(gap, "Other incomplete local telemetry.") for gap in gaps))[:5]
    return {
        "kind": kind, "title": title,
        "explanation": "Multiple recorded conditions need reconciliation before another effect." if len(unique) > 1 else shown[0]["label"] + ".",
        "phaseStatus": run["status"], "phaseId": run.get("phaseId"),
        "issues": shown, "issueCount": len(unique), "issuesTruncated": len(unique) > len(shown),
        "usageRelevant": usage_related, "maxTasks": limits.get("maxTasks"),
        "maxParallelTasks": limits.get("maxParallelTasks"), "expiresAt": run.get("expiresAt"),
        "registeredTasks": len(run.get("tasks") or []),
        "budget": budget, "checkpointReserve": reserve,
        "observedTotal": observed, "knownUsageLowerBound": known if observed is not None or high_water > 0 else None,
        "cachedInput": cached,
        "uncachedInput": max(0, input_total - cached) if input_total is not None and cached is not None else None,
        "output": output, "observedAt": report.get("collectedAt"),
        "coverage": report.get("coverage", "unknown"), "gapCount": len(gaps), "gapLabels": labels,
        "reasonLabels": list(dict.fromkeys(row["label"] + "." for row in shown)),
        "remainingMeasured": (standard.get("measuredUsage") or {}).get("remainingMeasured"),
        "budgetBoundaryReached": reached,
        "requiresOwnerReview": run["status"] == "blocked" or reached,
        "nextStep": ("Ask the brain to reconcile every recorded stop and propose only the exact changes needed. "
                     "Review any new phase and Play separately; neither happens automatically."
                     if run["status"] == "blocked" else
                     "Do not Resume until the recorded conditions are resolved; review a new phase if a reviewed limit must change."
                     if run["status"] == "paused" else
                     "Pause at a safe checkpoint and reconcile the conditions before another effect."),
        "boundary": "No policy waiver, budget reset, native retry, phase review or Play is authorized by this explanation.",
    }
