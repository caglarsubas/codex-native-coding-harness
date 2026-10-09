"""Non-authoritative suggestions for a *new* standard-project phase.

The caller supplies the brain's structured task outline and an optional retained
usage projection. This module performs no I/O, does not amend a mission or run,
and must not be used as a Play/admission check. The repository/worktree and file
scope checks at native effect boundaries remain authoritative.
"""

from itertools import combinations
import math
import unicodedata


TIERS = ((2, 20_000_000, 3), (5, 30_000_000, 6), (10, 40_000_000, 10))
MAX_OUTLINE_TASKS = 20
MAX_FILES_PER_TASK = 40
MAX_PATH_LENGTH = 500


def suggest_play_settings(reviewed_budget, duration_hours=None):
    """Suggested preview settings for a new phase; never modify a saved run."""
    if type(reviewed_budget) is not int or reviewed_budget < 1:
        raise ValueError("A positive reviewed phase budget is required")
    if duration_hours is not None and (type(duration_hours) is not int or not 1 <= duration_hours <= 24):
        raise ValueError("Reviewed phase hours must be an integer from 1 to 24")
    return {"durationHours": 24 if duration_hours is None else duration_hours,
            "brainAllowanceTokens": max(1, min(reviewed_budget * 3 // 10, 12_000_000))}


def _exact_file(value):
    """Return a conservative comparison key, or None for an ambiguous scope."""
    if not isinstance(value, str) or not value or len(value) > MAX_PATH_LENGTH:
        return None
    if value.startswith("/") or value.endswith("/") or "\\" in value:
        return None
    if any(ord(char) < 32 or char in "*?[]" for char in value):
        return None
    if any(part in ("", ".", "..") for part in value.split("/")):
        return None
    # The host may be case-insensitive and use decomposed Unicode. Treat both
    # spellings as the same proposed file; native validation is still required.
    return unicodedata.normalize("NFC", value).casefold()


def _task_scope(task):
    if (not isinstance(task, dict) or not isinstance(task.get("title"), str)
            or not 0 < len(task["title"].strip()) <= 200):
        return None
    repository = task.get("repository")
    files = task.get("exactFiles")
    if (not isinstance(repository, str) or not 0 < len(repository.strip()) <= 100
            or any(ord(char) < 32 for char in repository) or not isinstance(files, list)):
        return None
    if not 1 <= len(files) <= MAX_FILES_PER_TASK:
        return None
    keys = [_exact_file(path) for path in files]
    if None in keys or len(set(keys)) != len(keys):
        return None
    return frozenset((repository.casefold(), key) for key in keys)


def _independent_count(scopes):
    """At most three workers are proposed; a small exact set search suffices."""
    if not scopes or any(scope is None for scope in scopes):
        return 1
    for count in range(min(3, len(scopes)), 1, -1):
        for group in combinations(scopes, count):
            if len(set().union(*group)) == sum(len(scope) for scope in group):
                return count
    return 1


def _usage_projection(evidence, caveats):
    result = {"coverage": "unknown", "knownTokens": None,
              "remainingMeasured": None, "observedAt": None, "gaps": []}
    if not isinstance(evidence, dict):
        caveats.append("No complete phase-usage observation was supplied; measured remaining budget is unknown.")
        return result
    tokens = evidence.get("tokens")
    count = tokens.get("total_tokens") if isinstance(tokens, dict) else None
    high_water = evidence.get("highWater")
    if type(count) is int and count >= 0:
        result["knownTokens"] = max(count, high_water) if type(high_water) is int and high_water >= 0 else count
    collected = evidence.get("collectedAt")
    if type(collected) in (int, float) and math.isfinite(collected) and collected >= 0:
        result["observedAt"] = collected
    gaps = evidence.get("gaps")
    if (isinstance(gaps, list) and len(gaps) <= 100
            and all(isinstance(gap, str) and len(gap) <= 200 for gap in gaps)):
        result["gaps"] = list(gaps)
    else:
        result["gaps"] = ["coverage_not_established"]
    complete = (evidence.get("coverage") == "observed_local" and not result["gaps"]
                and result["knownTokens"] is not None and result["observedAt"] is not None)
    result["coverage"] = "complete" if complete else "incomplete"
    remaining = evidence.get("remainingMeasured")
    if complete and type(remaining) is int and remaining >= 0:
        result["remainingMeasured"] = remaining
    if not complete:
        caveats.append("Usage evidence is incomplete; known observed tokens remain visible but measured remaining budget is unknown.")
    elif result["remainingMeasured"] is None:
        caveats.append("The supplied complete usage observation has no measured-remaining value; do not infer zero.")
    return result


def suggest_phase_limits(task_outline, usage_evidence=None, *, repository_mode="repo_exclusive"):
    """Return JSON-ready editable proposal values; never execution authority.

    ``task_outline`` is the optional ``phase.taskOutline`` list of rows with
    ``title``, ``repository`` and ``exactFiles``. Scopes only affect the suggested
    concurrency; they never verify a native worktree, Git diff or runtime slot.
    ``usage_evidence`` may be a retained ``standard.measuredUsage`` projection.
    Its remaining budget, when known, pertains to that source run, *not* this
    proposed new phase.
    """
    if repository_mode not in ("repo_exclusive", "isolated_worktrees"):
        raise ValueError("Unknown repository ownership mode")
    caveats = []
    usage = _usage_projection(usage_evidence, caveats)
    if task_outline is None:
        tasks = []
    elif isinstance(task_outline, list) and len(task_outline) <= MAX_OUTLINE_TASKS:
        tasks = task_outline
    else:
        raise ValueError("Task outline must be a list of at most 20 rows")
    planned = len(tasks)
    if planned == 0:
        tier = TIERS[0]
        basis = "provisional"
        caveats.append("No structured task outline is available. These first-tier values are provisional and editable; confirm scope before review.")
    elif planned > TIERS[-1][0]:
        tier = None
        basis = "outside_suggestion_range"
        caveats.append("The outline exceeds ten tasks. Split the phase or enter explicit limits for exact owner review.")
    else:
        tier = next(tier for tier in TIERS if planned <= tier[0])
        basis = "structured"
    scopes = [_task_scope(task) for task in tasks]
    incomplete = bool(tasks) and any(scope is None for scope in scopes)
    if incomplete:
        caveats.append("At least one task lacks an unambiguous exact-file scope; parallelism is suggested as one until the outline is corrected.")
    independent = _independent_count(scopes)
    if not incomplete and planned > 1 and len(set().union(*scopes)) < sum(len(scope) for scope in scopes):
        caveats.append("Some task file scopes overlap; only a disjoint subset counts toward the parallel suggestion.")
    if independent > 1:
        caveats.append("Independent file names are planning evidence only. Distinct native worktrees and effect-boundary checks may reduce current eligibility.")
    if tier is None:
        limits = None
        play = None
    else:
        _, budget, total = tier
        limits = {"maxParallelTasks": min(3, independent), "maxTasks": total,
                  "tokenBudget": budget, "checkpointReserveTokens": budget // 10}
        play = suggest_play_settings(budget)
        if repository_mode == "isolated_worktrees" and tasks:
            repositories = {task.get("repository") for task in tasks
                            if isinstance(task, dict) and isinstance(task.get("repository"), str)}
            required = planned + len(repositories)
            if required > total:
                caveats.append(f"The outline has {planned} producer tasks across {len(repositories)} repositories. "
                               f"Isolated worktrees also need one integration task per repository ({required} total); "
                               "edit the suggested total before owner review or split the phase.")
    return {"plannedTasks": planned, "basis": basis, "limits": limits,
            "play": play, "independentScopes": independent,
            "usage": usage, "caveats": caveats, "proposalOnly": True}
