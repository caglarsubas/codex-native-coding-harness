"""Closed external-evidence contract and conservative reconciliation diagnostics.

Evidence hashes identify caller-supplied observations, not authenticated native
attestations. A consistent report never authorizes execution or releases owners.
"""
import math

from .admission import counters, exact, identifier, resource, sha, timestamp
from .core import canonical, require
from .workspaces import identity


def rows(value, limit=2000):
    require(isinstance(value, list) and len(value) <= limit, "Evidence list exceeds its bound")
    return value


def boolean(value):
    require(type(value) is bool, "Explicit evidence boolean required")


def native(value):
    exact(value, {"hostId", "threadId"})
    identifier(value["hostId"]); identifier(value["threadId"])
    return value["hostId"], value["threadId"]


def pair(value):
    return value["hostId"], value["threadId"]


def unique(values):
    require(len(values) == len(set(values)), "Duplicate evidence identity")


def observed(value):
    timestamp(value["observedAt"]); sha(value["evidenceHash"])


def validate(evidence):
    exact(evidence, {"schemaVersion", "adoptionHash", "account", "inventory", "claims", "resources", "runners", "usage"})
    require(type(evidence["schemaVersion"]) is int and evidence["schemaVersion"] == 1, "Unsupported reconciliation schema")
    require(len(canonical(evidence).encode()) <= 2_000_000, "Reconciliation evidence is too large")
    sha(evidence["adoptionHash"])
    account = evidence["account"]
    exact(account, {"identityHash", "observedAt", "evidenceHash", "windows"})
    sha(account["identityHash"]); observed(account)
    exact(account["windows"], {"short", "long"})
    for window in account["windows"].values():
        exact(window, {"usedPercent", "resetsAt"})
        used = window["usedPercent"]
        require(used is None or (type(used) in (int, float) and math.isfinite(used) and 0 <= used <= 100),
                "Invalid account usage percentage")
        if window["resetsAt"] is not None: timestamp(window["resetsAt"])
    inventory = evidence["inventory"]
    exact(inventory, {"accountIdentityHash", "observedAt", "evidenceHash", "complete", "includesDescendants",
                      "includesUnmanaged", "workspaceIds", "hostIds", "tasks", "pending"})
    observed(inventory); sha(inventory["accountIdentityHash"])
    for key in ("complete", "includesDescendants", "includesUnmanaged"): boolean(inventory[key])
    for wid in rows(inventory["workspaceIds"], 32): identity(wid)
    for host in rows(inventory["hostIds"], 64): identifier(host)
    unique(inventory["workspaceIds"]); unique(inventory["hostIds"])
    for task in rows(inventory["tasks"]):
        exact(task, {"hostId", "threadId", "workspaceId", "role", "parent", "state", "checkpointHash", "observedAt", "evidenceHash"})
        identifier(task["hostId"]); identifier(task["threadId"]); observed(task)
        if task["workspaceId"] is not None: identity(task["workspaceId"])
        require(task["role"] in ("brain", "worker", "reviewer", "nested", "external"), "Unknown task role")
        require(task["state"] in ("idle", "running", "unknown"), "Unknown native activity state")
        if task["parent"] is not None: native(task["parent"])
        if task["checkpointHash"] is not None: sha(task["checkpointHash"])
    unique([pair(t) for t in inventory["tasks"]])
    for pending in rows(inventory["pending"]):
        exact(pending, {"hostId", "clientThreadId", "outcome", "threadId", "observedAt", "evidenceHash"})
        identifier(pending["hostId"]); identifier(pending["clientThreadId"]); observed(pending)
        require(pending["outcome"] in ("resolved", "not_created", "unknown"), "Unknown pending outcome")
        if pending["outcome"] == "resolved": identifier(pending["threadId"])
        else: require(pending["threadId"] is None, "Pending ID is not a native task ID")
    unique([(p["hostId"], p["clientThreadId"]) for p in inventory["pending"]])
    for claim in rows(evidence["claims"]):
        exact(claim, {"claimId", "outcome", "native", "observedAt", "evidenceHash"})
        sha(claim["claimId"]); observed(claim)
        require(claim["outcome"] in ("quiescent", "not_created", "unknown"), "Unknown ownership outcome")
        for value in rows(claim["native"], 50): native(value)
        unique([pair(n) for n in claim["native"]])
    unique([c["claimId"] for c in evidence["claims"]])
    for row in rows(evidence["resources"], 8000):
        exact(row, {"key", "verified", "observedAt", "evidenceHash"})
        resource(row["key"], "runner" if isinstance(row["key"], str) and row["key"].startswith("runner:") else "repo")
        boolean(row["verified"]); observed(row)
    unique([r["key"] for r in evidence["resources"]])
    for runner in rows(evidence["runners"]):
        exact(runner, {"key", "state", "cleanupObserved", "observedAt", "evidenceHash"})
        resource(runner["key"], "runner"); boolean(runner["cleanupObserved"]); observed(runner)
        require(runner["state"] in ("idle", "busy", "unknown"), "Unknown runner state")
    unique([r["key"] for r in evidence["runners"]])
    usage = evidence["usage"]
    exact(usage, {"accountIdentityHash", "observedAt", "evidenceHash", "complete", "sessions"})
    sha(usage["accountIdentityHash"]); observed(usage); boolean(usage["complete"])
    for session in rows(usage["sessions"]):
        exact(session, {"hostId", "threadId", "counterEpoch", "counters", "complete", "observedAt", "evidenceHash"})
        identifier(session["hostId"]); identifier(session["threadId"]); sha(session["counterEpoch"])
        observed(session); boolean(session["complete"])
        if session["counters"] is not None: counters(session["counters"])
    unique([pair(s) for s in usage["sessions"]])


def assess(context, evidence, anchor, now):
    validate(evidence)
    issues, clocks = [], []
    def issue(code, **scope):
        value = {"code": code, **scope}
        if value not in issues: issues.append(value)
    policy, start = context["policy"], context["adoptedAt"]
    age = policy["maxObservationAgeSeconds"]
    def fresh(row, kind, **scope):
        at = row["observedAt"]; clocks.append(at + age)
        if at < start: issue("evidence_predates_adoption", kind=kind, **scope)
        if not 0 <= now - at <= age: issue("evidence_not_fresh", kind=kind, **scope)
    if evidence["adoptionHash"] != context["adoptionHash"]: issue("adoption_binding_mismatch")
    account, inventory, usage = (evidence[k] for k in ("account", "inventory", "usage"))
    for key, value in (("account", account), ("inventory", inventory), ("usage", usage)): fresh(value, key)
    account_id = account["identityHash"]
    if inventory["accountIdentityHash"] != account_id or usage["accountIdentityHash"] != account_id:
        issue("account_identity_mismatch")
    for name, window in account["windows"].items():
        if window["usedPercent"] is None or window["resetsAt"] is None: issue("account_window_unknown", window=name)
        else:
            clocks.append(window["resetsAt"])
            if window["resetsAt"] <= max(now, account["observedAt"]): issue("account_window_reset", window=name)
            if 100 - window["usedPercent"] < policy["minAccountRemainingPercent"]: issue("account_headroom_low", window=name)
    if not all(inventory[k] for k in ("complete", "includesDescendants", "includesUnmanaged")):
        issue("inventory_coverage_incomplete")
    workspace_ids = {w["workspaceId"] for w in context["workspaces"]}
    if set(inventory["workspaceIds"]) != workspace_ids: issue("workspace_coverage_mismatch")
    tasks = {pair(t): t for t in inventory["tasks"]}
    sessions = {pair(s): s for s in usage["sessions"]}
    pending = {(p["hostId"], p["clientThreadId"]): p for p in inventory["pending"]}
    expected_pending = set()
    for p in pending.values(): fresh(p, "pending", clientThreadId=p["clientThreadId"])
    for task in tasks.values():
        fresh(task, "task", threadId=task["threadId"])
        if task["hostId"] not in inventory["hostIds"]: issue("host_coverage_missing", hostId=task["hostId"])
        if task["workspaceId"] not in workspace_ids or task["role"] == "external": issue("unmanaged_task", threadId=task["threadId"])
        if task["state"] != "idle": issue("task_not_quiescent", threadId=task["threadId"])
        if not task["checkpointHash"]: issue("checkpoint_missing", threadId=task["threadId"])
        parent = pair(task["parent"]) if task["parent"] else None
        if task["role"] in ("nested", "reviewer") and parent is None: issue("parent_missing", threadId=task["threadId"])
        if parent and (parent not in tasks or tasks[parent]["workspaceId"] != task["workspaceId"]):
            issue("parent_scope_mismatch", threadId=task["threadId"])
        seen, cursor = {pair(task)}, parent
        while cursor in tasks:
            if cursor in seen:
                issue("parent_cycle", threadId=task["threadId"]); break
            seen.add(cursor)
            cursor = pair(tasks[cursor]["parent"]) if tasks[cursor]["parent"] else None
    expected_tasks = set()
    for workspace in context["workspaces"]:
        matches = [key for key, t in tasks.items() if t["threadId"] == workspace["brainId"] and t["workspaceId"] == workspace["workspaceId"] and t["role"] == "brain"]
        if len(matches) != 1: issue("brain_inventory_missing_or_ambiguous", workspaceId=workspace["workspaceId"])
        expected_tasks.update(matches)
    reports = {c["claimId"]: c for c in evidence["claims"]}
    claims = {c["id"]: c for c in context["claims"]}
    if set(reports) - set(claims): issue("foreign_claim_evidence")
    claim_results, bindings = [], {}
    for cid, claim in claims.items():
        before = len(issues)
        report = reports.get(cid)
        known = {pair(n) for n in claim["nativeIdentities"]}
        pending_rows = [v for v in claim["versions"] if v["kind"] == "worker" and v.get("clientThreadId")]
        for version in pending_rows:
            key = version.get("hostId"), version["clientThreadId"]
            expected_pending.add(key)
            p = pending.get(key)
            if not p or p["outcome"] == "unknown": issue("pending_creation_unresolved", claimId=cid)
            elif p["outcome"] == "resolved": known.add((p["hostId"], p["threadId"]))
        for gap in claim["issues"]:
            if gap in ("repository_mapping_unknown", "runner_mapping_unknown", "runner_without_worker_record", "conflicting_native_bindings"):
                issue(gap, claimId=cid)
        if report is None: issue("claim_evidence_missing", claimId=cid)
        else:
            fresh(report, "claim", claimId=cid)
            declared = {pair(n) for n in report["native"]}
            if not known <= declared: issue("native_binding_omitted", claimId=cid)
            if report["outcome"] == "not_created":
                if known or declared: issue("not_created_conflicts_with_native", claimId=cid)
            elif report["outcome"] == "quiescent":
                if not declared: issue("native_identity_unresolved", claimId=cid)
            else: issue("claim_outcome_unknown", claimId=cid)
            for key in declared:
                if key not in tasks: issue("native_task_missing", claimId=cid)
                elif tasks[key]["workspaceId"] != claim["workspaceId"] or tasks[key]["role"] == "brain":
                    issue("native_task_scope_mismatch", claimId=cid)
                bindings.setdefault(key, []).append(cid)
            expected_tasks.update(declared)
        claim_results.append({"claimId": cid, "outcome": report["outcome"] if report else "unknown",
                              "evidenceGaps": len(issues) - before, "ownershipReleased": False})
    if set(pending) - expected_pending: issue("foreign_pending_evidence")
    for key, owners in bindings.items():
        if len(owners) > 1: issue("native_owned_by_multiple_claims", threadId=key[1])
    for key in set(tasks) - expected_tasks: issue("unadopted_task", threadId=key[1])
    # Re-check today's retained ownership, not merely the old import receipt.
    grouped = {(c["workspaceId"], c["workerId"]): c for c in claims.values()}
    for owner in context["currentOwners"]:
        claim = grouped.get((owner["workspaceId"], owner["workerId"]))
        if not claim: issue("new_ledger_owner", workspaceId=owner["workspaceId"]); continue
        if owner["kind"] == "worker":
            old_hashes = {v.get("repositoryBindingHash") for v in claim["versions"] if v["kind"] == "worker"}
            if owner.get("repositoryBindingHash") not in old_hashes: issue("repository_binding_changed", claimId=claim["id"])
            old_pending = {(v.get("hostId"), v.get("clientThreadId")) for v in claim["versions"] if v["kind"] == "worker" and v.get("clientThreadId")}
            if owner.get("clientThreadId") and (owner.get("hostId"), owner["clientThreadId"]) not in old_pending:
                issue("current_pending_binding_unadopted", claimId=claim["id"])
            if owner.get("threadId") and claim["id"] not in bindings.get((owner.get("hostId"), owner["threadId"]), []):
                issue("current_native_binding_uncovered", claimId=claim["id"])
        elif not any(v["kind"] == "runner" and v["recordHash"] == owner["recordHash"] for v in claim["versions"]):
            issue("runner_ownership_changed", claimId=claim["id"])
    keys = {k for c in claims.values() for k in c["resourceKeys"]}
    for key in keys:
        if sum(key in c["resourceKeys"] for c in claims.values()) > 1:
            issue("resource_owned_by_multiple_claims", resource=key)
    mappings = {r["key"]: r for r in evidence["resources"]}
    if set(mappings) != keys: issue("resource_coverage_mismatch")
    for key, row in mappings.items():
        fresh(row, "resource", resource=key)
        if not row["verified"]: issue("resource_identity_unverified", resource=key)
    runners = {r["key"]: r for r in evidence["runners"]}
    if set(runners) != {k for k in keys if k.startswith("runner:")}: issue("runner_coverage_mismatch")
    for key, runner in runners.items():
        fresh(runner, "runner", resource=key)
        if runner["state"] != "idle" or not runner["cleanupObserved"]: issue("runner_not_quiescent", resource=key)
    if not usage["complete"] or set(sessions) != set(tasks): issue("usage_coverage_incomplete")
    totals = {k: 0 for k in ("inputTokens", "cachedInputTokens", "outputTokens", "reasoningOutputTokens")}
    for key, session in sessions.items():
        fresh(session, "usage_session", threadId=key[1])
        if not session["complete"] or session["counters"] is None: issue("session_usage_unknown", threadId=key[1])
        if session["counters"] is not None:
            for name in totals: totals[name] += session["counters"][name]
    if anchor:
        if anchor["account"]["identityHash"] != account_id: issue("account_changed_since_baseline")
        previous = {pair(s): s for s in anchor["usage"]["sessions"]}
        for key, old in previous.items():
            row = sessions.get(key)
            if row is None: issue("baseline_session_dropped", threadId=key[1]); continue
            if row["counterEpoch"] != old["counterEpoch"]: issue("counter_epoch_changed", threadId=key[1])
            if row["observedAt"] < old["observedAt"] or (row["counters"] is not None and
                    any(row["counters"][k] < old["counters"][k] for k in totals)):
                issue("usage_counter_moved_backwards", threadId=key[1])
    return {"status": "consistent" if not issues else "needs_evidence", "evidenceConsistent": not issues,
            "checkedAt": now, "validUntil": min(clocks), "issues": sorted(issues, key=canonical), "claims": claim_results,
            "observedTaskCount": len(tasks), "knownCumulativeTokens": {**totals, "rawTokens": totals["inputTokens"] + totals["outputTokens"]},
            "baselineCandidate": not issues, "executionAuthorized": False, "ownershipReleased": False,
            "activationAvailable": False, "trustBoundary": "caller_supplied_external_evidence_not_native_attestation"}
