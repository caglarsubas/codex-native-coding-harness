"""Deterministic operating diagnostics. Never authorizes or dispatches work."""
from __future__ import annotations

from pathlib import Path
import subprocess
import time

from .core import ACTIVE, digest, eligibility_issues, require
from .observations import save

FRESH_SECONDS = 15 * 60


def native_observation(ledger, record):
    """Import a bounded operator observation from native Codex tools, not private APIs."""
    require(isinstance(record, dict) and set(record) == {"schemaVersion", "observedAt", "brain", "projects"}, "Invalid native observation")
    require(record["schemaVersion"] == 1 and type(record["observedAt"]) in (int, float)
        and 0 <= time.time() - record["observedAt"] <= 300, "Native observation must be current (five minutes)")
    brain = record["brain"]
    require(isinstance(brain, dict) and {"id", "status"} <= set(brain) <= {"id", "status", "title"}, "Invalid brain observation")
    if "title" in brain:
        require(isinstance(brain["title"], str) and 0 < len(brain["title"]) <= 200
            and all(ord(c) >= 32 for c in brain["title"]), "Invalid brain title")
    state = ledger.snapshot()
    require(isinstance(brain["id"], str) and bool(brain["id"]) and brain["id"] == state["meta"]["brainId"]
        and brain["status"] in ("idle", "running", "unavailable", "unknown"), "Native brain observation does not match portfolio")
    projects = record["projects"]
    require(isinstance(projects, list) and len(projects) <= 500, "Bounded native project inventory required")
    paths = {str(Path(r["path"]).resolve()) for r in state["repositories"] if r["path"]}
    selected, identities = [], set()
    for p in projects:
        require(isinstance(p, dict) and set(p) == {"projectId", "path", "hostId", "isGitRepository"}, "Invalid native project entry")
        require(all(isinstance(p[k], str) and 0 < len(p[k]) <= 4096 for k in ("projectId", "path", "hostId"))
            and type(p["isGitRepository"]) is bool and Path(p["path"]).is_absolute(), "Invalid native project values")
        require(p["projectId"] not in identities, "Duplicate native project identity")
        identities.add(p["projectId"])
        if str(Path(p["path"]).resolve()) in paths:
            selected.append(p)
    retained = {**record, "projects": selected, "source": "operator_recorded_native_tools", "authorization": False}
    with ledger.tx() as db:
        save(db, "native", retained)
    return {"status": "recorded", "matchedProjects": len(selected), "observedAt": record["observedAt"]}


def inspect_repository(repo):
    row = {"repository": repo["id"], "configurationHash": digest(repo), "status": "unavailable", "commit": None,
        "reason": None, "hasAgents": False, "workflowCount": None, "setupReview": "not_verified"}
    if not repo["path"] or not Path(repo["path"]).is_dir():
        return {**row, "reason": "Configured checkout is absent; do not bootstrap it implicitly."}
    root = Path(repo["path"]).resolve()
    try:
        def git(*args):
            return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                timeout=10, check=True).stdout.strip()
        require(Path(git("rev-parse", "--show-toplevel")).resolve() == root, "Configured path is not the exact repository root")
        commit = git("rev-parse", "--verify", "--end-of-options", repo["ref"] + "^{commit}")
        agents = root / "AGENTS.md"
        workflows = root / ".github" / "workflows"
        count = None if workflows.is_symlink() or not workflows.resolve().is_relative_to(root) else sum(p.is_file() and not p.is_symlink() for pattern in ("*.yml", "*.yaml") for p in workflows.glob(pattern))
        row.update(status="observed", commit=commit, hasAgents=agents.is_file() and not agents.is_symlink(), workflowCount=count,
            worktreeIncludePresent=(root / ".worktreeinclude").exists(), localEnvironmentPresent=(root / ".codex" / "environments").exists())
    except (OSError, subprocess.SubprocessError, ValueError):
        row["reason"] = "Cannot verify the exact configured Git root/ref. Review its path and commit before dispatch."
    return row


def collect(ledger):
    state = ledger.snapshot()
    record = {"at": time.time(), "repositories": [inspect_repository(r) for r in state["repositories"]],
        "method": "Local Git metadata only. No fetch, repository code, acceptance, model request or native action."}
    with ledger.tx() as db:
        save(db, "readiness", record)
    return {"status": "complete", "repositories": len(record["repositories"]), "observedAt": record["at"]}


def diagnose(ledger, state=None):
    state = state or ledger.snapshot()
    meta, obs, now = state["meta"], state["observations"], time.time()
    admission = state.get("admission", {})
    local, native = obs.get("readiness") or {}, obs.get("native") or {}
    def fresh(at):
        return bool(at) and 0 <= now - at <= FRESH_SECONDS
    local_fresh, native_fresh = fresh(local.get("at")), fresh(native.get("observedAt"))
    active = [w for w in state["workers"] if w["status"] in ACTIVE]
    rows = []
    for repo in state["repositories"]:
        measured = next((r for r in local.get("repositories", []) if r["repository"] == repo["id"]), {})
        if measured.get("configurationHash") != digest(repo): measured = {}
        candidates = [p for p in native.get("projects", []) if repo["path"] and
            Path(p["path"]).resolve() == Path(repo["path"]).resolve() and p["hostId"] == "local" and p["isGitRepository"]]
        matched = native_fresh and any(p["projectId"] == repo["projectId"] for p in candidates)
        issues = []
        if not local_fresh: issues.append("Refresh local readiness checks; measurements are missing or stale.")
        if measured.get("status") != "observed": issues.append(measured.get("reason") or "Checkout/ref has not been inspected.")
        if not native_fresh: issues.append("Ask the brain to refresh native project inventory; the webpage cannot call native tools.")
        if not matched: issues.append("Register the existing checkout in Codex and record its exact project mapping; no mapping is inferred.")
        if not measured.get("hasAgents"): issues.append("No regular AGENTS.md observed; review the repository's execution contract.")
        rows.append({"repository": repo["id"], "profile": repo["policyProfile"], "mergePolicy": repo["mergePolicy"],
            "configuredProjectId": repo["projectId"], "candidateProjectId": candidates[0]["projectId"] if native_fresh and len(candidates) == 1 else None,
            "mappingObserved": bool(matched), "commit": measured.get("commit"), "workflowCount": measured.get("workflowCount"),
            "registrationReady": not issues, "issues": issues,
            "setupReview": "Review native setup scripts and ignored-file copying before each new worktree. Absence of repository settings is not proof of safe app settings.",
            "ciNote": "Workflow presence does not prove required checks or runner availability." if measured.get("workflowCount") else "No repository workflow observed. Define a valid CI evidence route before approving a pilot; local tests are not automatically CI."})
    packets = []
    for q in state["queue"]:
        repo = next(r for r in state["repositories"] if r["id"] == q["repository"])
        if q["status"] in ("dispatched", "complete"):
            packets.append({"queueId": q["id"], "repository": q["repository"], "packetId": q["packetId"], "seedHash": q["seedHash"],
                "status": q["status"], "ledgerEligible": False, "issues": [{"code": "complete", "detail": "Completed under its recorded evidence contract; no new launch. Merge and archive remain separate."}] if q["status"] == "complete" else
                    [{"code": "owned", "detail": "Already dispatched; reconcile its existing owner, never create a duplicate."}]})
            continue
        issues = eligibility_issues(q, repo, ledger.document(q["seedHash"]), state["workers"], now)
        if admission.get("dispatchBlocked"):
            issues.append({"code": "platform_enrollment", "detail": admission["reason"]})
        if meta["paused"]: issues.append({"code": "paused", "detail": "Dispatch paused; any resume request must be processed by the designated brain."})
        if len(active) >= meta["concurrency"]: issues.append({"code": "capacity", "detail": "Worker capacity is reserved."})
        if any(w["repository"] == q["repository"] for w in active): issues.append({"code": "repository_owned", "detail": "Repository is owned by an existing worker."})
        packets.append({"queueId": q["id"], "repository": q["repository"], "packetId": q["packetId"], "seedHash": q["seedHash"], "status": q["status"], "ledgerEligible": not issues, "issues": issues})
    pending = [c for c in state["commands"] if c["status"] in ("queued", "processing")]
    status = "supervision_required" if active else "parked" if not any(q["status"] == "approved" for q in state["queue"]) else "brain_check_required"
    return {"status": status, "checkedAt": now, "readOnly": True, "launchAuthorized": False,
        "brainId": meta["brainId"], "brainObservedStatus": native.get("brain", {}).get("status", "unknown") if native_fresh else "unknown",
        "lastReconciled": meta["lastReconciled"], "brainFresh": bool(meta["lastReconciled"]) and 0 <= now - meta["lastReconciled"] <= 1800,
        "localObservedAt": local.get("at"), "nativeObservedAt": native.get("observedAt"), "localFresh": local_fresh, "nativeFresh": native_fresh,
        "repositories": rows, "packets": packets, "pendingControls": len(pending), "uncertainControls": sum(c["status"] == "processing" for c in pending),
        "activeWorkers": len(active), "pilotPassed": meta["pilotPassed"], "concurrency": meta["concurrency"],
        "heartbeat": {**meta["heartbeat"], "source": "recorded_ledger_state_not_live_poll"}, "rehearsal": obs.get("rehearsal"),
        "admission": admission,
        "nextAction": admission["reason"] if admission.get("dispatchBlocked") else "Reconcile existing ownership and pending native actions." if active or pending else
            "Ask the brain to reverify the exact approved scope and current external gates. Resume remains a separate request." if status == "brain_check_required" else
            "Prepare one bounded next scope and review its exact inheritance before approval. Pilot acceptance does not authorize more work." if meta["pilotPassed"] else
            "Select one bounded pilot scope, review its inheritance and approve its exact hashes. No blanket roadmap execution.",
        "brainPrompt": "Continue orchestration with $codex-orchestrator in this designated brain only. Start with status and read-only readiness/native project checks. Process only explicitly authorized control requests. Do not approve packets, resume dispatch, activate a heartbeat, create tasks or certify the pilot merely because this message was sent. Report the next exact approval or setup action needed.",
        "limits": "This diagnostic is not preflight or authorization. The brain must independently verify current packet/base/locks, predecessors, native setup, duplicate work, runner availability and repository policy at the creation boundary."}
