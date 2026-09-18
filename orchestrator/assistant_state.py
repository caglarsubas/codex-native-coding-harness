"""Bounded, allowlisted operational awareness; never raw ledger/event/transcript dumps."""
from collections import Counter

from .repository import aggregate


def fields(row, names):
    row = row or {}
    return {k: row.get(k) for k in names.split()}


def short(value, limit=240):
    return str(value or "")[:limit]


def extend_context(state, facts, view="overview"):
    meta, obs = state["meta"], state.get("observations", {})
    def fact(number, label, data):
        facts.append({"id": "F" + str(number), "label": label, "data": data})
    def bounded(rows, total):
        return {"rows": rows, "included": len(rows), "total": total, "omitted": max(0, total-len(rows))}

    activity, readiness, provenance = (state.get(k) or {} for k in ("brainActivity", "readiness", "provenance"))
    fact(12, "Observed activity, ownership, readiness and runtime; timestamps do not advance evidence", {
        "activity": fields(activity, "status lastKnownStatus fresh observedAt checkedAt source phase"),
        "notification": fields(state.get("brainNotification"), "status"),
        "controller": {"owned": bool(meta.get("controller")), "since": (meta.get("controller") or {}).get("since")},
        "runner": {"owned": bool(meta.get("runner")), "since": (meta.get("runner") or {}).get("since")},
        "brainControlRecorded": bool(meta.get("brainControl")),
        "safeCheckpoint": fields((meta.get("brainControl") or {}).get("checkpoint"), "at"),
        "readiness": fields(readiness, "status checkedAt localObservedAt nativeObservedAt localFresh nativeFresh launchAuthorized"),
        "runtime": {**fields(provenance, "status localFresh remoteFresh restartRecommended startupMatchesRemote checkoutMatchesRemote"),
                    **{k: fields(provenance.get(k), "status at commit dirty") for k in ("startup", "current", "remote")}},
        "jobs": {k: fields(state.get(k), "status startedAt finishedAt operation") for k in ("observationJob",)},
        "readinessJob": fields(readiness.get("job"), "status operation startedAt finishedAt"),
        "runtimeJob": fields(provenance.get("job"), "status startedAt finishedAt"),
        "inference": {**fields(state.get("inference"), "configured model assistantModel stale"),
                      "briefJob": fields((state.get("inference") or {}).get("job"), "status startedAt finishedAt")}})
    metrics = {m["repository"]: m for m in aggregate(state)["repositories"]}
    git = {g["repository"]: g for g in obs.get("git", [])}
    ready = {r["repository"]: r for r in readiness.get("repositories", [])}
    repos = []
    for r in state["repositories"][:30]:
        m, g, rd = metrics.get(r["id"], {}), git.get(r["id"], {}), ready.get(r["id"], {})
        remote = g if g.get("remoteAt") else g.get("previousRemote") or {}
        if view not in ("metrics", "gitStatus", "readiness"):
            repos.append({"name": short(r["id"], 100), "mapped": bool(r.get("projectId")),
                          "mergePolicy": r.get("mergePolicy"), "sizeStatus": m.get("status", "not_measured"),
                          "gitStatus": g.get("status", "not_observed"),
                          "readiness": fields(rd, "registrationReady mappingObserved")})
            continue
        repos.append({"name": short(r["id"], 100), "mapped": bool(r.get("projectId")),
                      **fields(r, "mergePolicy policyProfile"), "size": fields(m, "status at commit files lines characters"),
                      "git": {**fields(g, "status at remoteStatus remoteAt"), "priorRemoteAt": remote.get("remoteAt"),
                              "worktrees": len(g.get("worktrees", [])) if g.get("status") == "measured" else None,
                              "dirtyWorktrees": sum(w.get("dirty") is True for w in g.get("worktrees", [])) if g.get("status") == "measured" else None,
                              "branches": len(g.get("branches", [])) if g.get("status") == "measured" else None,
                              "prStates": dict(Counter(p["state"] for p in remote.get("pullRequests", []))) if remote.get("remoteAt") else None},
                      "readiness": {**fields(rd, "registrationReady mappingObserved"), "issueCount": len(rd.get("issues", [])) if rd else None,
                                    "issues": [short(s) for s in rd.get("issues", [])[:2]] if view == "readiness" else []}})
    fact(13, "Repository distribution; missing measurements are unknown, not zero", bounded(repos, len(state["repositories"])))
    gates = {p["queueId"]: p for p in readiness.get("packets", [])}
    fact(14, "Prepared packet states and recorded eligibility, not approval or live preflight", bounded([
        {"alias": "Q"+str(i), **fields(q, "repository packetId status held priority"),
         "reason": short(q.get("reason")), "approved": bool(q.get("approval")),
         "preflightAt": (q.get("preflight") or {}).get("at"),
         "gateIssues": [short(s.get("detail")) for s in gates.get(q["id"], {}).get("issues", [])[:5]]}
        for i, q in enumerate(sorted(state["queue"], key=lambda q: q["id"])[:20], 1)], len(state["queue"])))
    fact(15, "Managed workers; separate lifecycle and evidence axes", bounded([
        {"alias": "W"+str(i), **fields(w, "repository packetId status preserved archived"), "nativeTaskBound": bool(w.get("threadId")),
         "evidence": {k: fields(v, "status at") for k, v in w.get("evidence", {}).items()},
         "ownsRunner": (meta.get("runner") or {}).get("workerId") == w["id"]}
        for i, w in enumerate(sorted(state["workers"], key=lambda w: w["id"])[:20], 1)], len(state["workers"])))
    commands = sorted(state["commands"], key=lambda c: (not (c["status"] in ("queued", "processing") or c.get("needsBrainReceipt")), -c["createdAt"]))
    pending_count = sum(c["status"] in ("queued", "processing") or bool(c.get("needsBrainReceipt")) for c in commands)
    command_limit = 12 if view == "decisions" else max(3, min(12, pending_count))
    fact(16, "Control receipts: pending first, then recent outcomes; delivery is not execution", bounded([
        {**fields(c, "kind status createdAt receivedAt needsBrainReceipt"),
         "result": short(c.get("result")), "notification": fields(c.get("notification"), "status attemptedAt finishedAt")}
        for c in commands[:command_limit]], len(commands)))
    followups = state.get("continuations", [])
    fact(17, "Retained follow-ups; answered historical questions must not be reopened", bounded([
        {"title": short(c.get("title")), "status": c["status"], "ownerAnswerRecorded": bool(c.get("response")),
         "outcome": short((c.get("outcome") or {}).get("summary")),
         "nextStep": short(((c.get("proposal") or {}).get("spec") or {}).get("summary")),
         "externalBlocker": short(((c.get("proposal") or {}).get("spec") or {}).get("externalBlocker"))}
        for c in followups[:8]], len(followups)))
    plans = obs.get("roadmaps", {}).get("plans", [])
    fact(18, "Roadmap source checklists, not verified delivery", bounded([
        {"repository": short(p.get("repository"), 100), **fields(p, "status at"), "items": len(p.get("items", [])),
         "checked": sum(bool(i.get("checked")) for i in p.get("items", [])),
         "nextUnchecked": [short(i.get("text")) for i in p.get("items", []) if not i.get("checked")][:3]}
        for p in plans[:12]], len(plans)))
    groups = (obs.get("usage") or {}).get("modelEffort", [])
    fact(19, "Usage by repository/model/effort; retained telemetry, not billing or causal effects", bounded([
        {**{k: short(g.get(k), 100) for k in ("repository", "model", "effort")},
         **fields(g, "input_tokens cached_input_tokens output_tokens total_tokens userMessages assistantMessages samples")}
        for g in sorted(groups, key=lambda g: -(g.get("total_tokens") or 0))[:16 if view == "usage" else 3]], len(groups)))
    branches, prs = [], []
    for g in obs.get("git", []):
        remote = g if g.get("remoteAt") else g.get("previousRemote") or {}
        for b in g.get("branches", []):
            branches.append({"repository": short(g["repository"], 100), "branch": short(b.get("branch"), 120),
                             **fields(b, "commit tracking pushStatus"), "observedAt": g.get("at")})
        for p in remote.get("pullRequests", []):
            prs.append({"repository": short(g["repository"], 100), **fields(p, "number state draft mergedAt"),
                        "branch": short(p.get("branch"), 120), "observedAt": remote.get("remoteAt")})
    fact(20, "Bounded branch observations; push state is not inferred from local tracking", bounded(branches[:16 if view == "gitStatus" else 3], len(branches)))
    fact(21, "Bounded pull request observations; merge is separate from CI, runtime and acceptance", bounded(prs[:16 if view == "gitStatus" else 3], len(prs)))


CAPABILITIES = [
    {"view": "overview", "capability": "Brain activity and control receipts, cooperative checkpoint stop/resume, separate worker dispatch control"},
    {"view": "decisions", "capability": "Version-bound suggested or free-text owner answers, outcomes, follow-up proposals and event-driven/periodic waiting"},
    {"view": "queue", "capability": "Inspect inheritance and exact hashes, approve one packet, hold/release and prioritize; only the brain dispatches after fresh gates"},
    {"view": "workers", "capability": "Inspect managed workers and eight independent evidence axes; request checkpoint or archive verified preserved work"},
    {"view": "knowledge", "capability": "Read retained knowledge and checkpoint documents; no automatic retrieval of file bodies into chat"},
    {"view": "metrics", "capability": "Aggregate and per-repository tracked-text files, LOC, characters, lifecycle measurements; observations may be missing/stale"},
    {"view": "usage", "capability": "Retained Codex token/cache, model/effort, message and task statistics; attribution is initial cwd, not a bill or causal productivity"},
    {"view": "gitStatus", "capability": "Observed worktrees, branches, ahead/behind, pushes, pull requests and merges; observation refresh is explicit"},
    {"view": "artifacts", "capability": "Read/download retained cross-task artifacts in creation/reference order and versions; coverage is bounded"},
    {"view": "roadmap", "capability": "Inspect plan source checklists and progress; checkmarks do not authorize execution or prove acceptance"},
    {"view": "readiness", "capability": "Local readiness inspection, isolated rehearsal and runtime/GitHub provenance checks; no fetch, deployment or runtime restart"},
]

BOUNDARIES = [
    "Chat can propose only listed available actions. Nothing happens until the owner confirms an exact preview.",
    "Ambiguous resume/stop requests require clarification: brain and worker dispatch are different controls.",
    "Packet approval, priority edits, observations, briefs and diagnostics use their review views, not chat confirmation in this version.",
    "No shell, arbitrary API/tool, code/file edit, provisioning, merge, direct task creation, credential or model-setting change from chat.",
    "Only the designated brain executes native work under existing packet/seed approval, repository, runner and evidence rules.",
]
