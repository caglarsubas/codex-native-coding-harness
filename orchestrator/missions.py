"""Versioned, workspace-bound mission configuration. Deliberately not admission.

Owner review records the exact proposed contract, not a packet approval or a run.
No value in this module can enable dispatch, change native settings, or schedule
work. Activation must be introduced with resource/budget admission and run gates.
"""
import contextlib
import json
import re
import time

from .core import canonical, digest, require, safe_relative

MODES = ("prepare_only", "exact_owner", "phase_delegated")
OPERATIONS = ("edit", "test", "commit", "push", "open_pr", "merge")
BLOCKERS = [
    "Internal run-authority records are not native activation; owner-facing autonomous Play is not implemented.",
    "Shared capacity checks are not connected to native task creation; fresh usage and reconciliation of existing owners are still required.",
    "Internal version-bound approvals/checkpoint releases are not connected to native effects or owner-facing Play.",
]


def text(value, label, limit=2000):
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit,
            label + " must be non-empty bounded text")
    require(not any(ord(c) < 32 and c not in "\n\t" for c in value), label + " contains control characters")
    return value.strip()


def strings(value, label, minimum=1, maximum=20):
    require(isinstance(value, list) and minimum <= len(value) <= maximum, label + " requires a bounded list")
    result = [text(item, label, 1000) for item in value]
    require(len(set(result)) == len(result), label + " contains duplicate entries")
    return result


def integer(value, label, lower, upper):
    require(type(value) is int and lower <= value <= upper, label + f" must be an integer from {lower} to {upper}")
    return value


def workspace(ledger):
    wid = getattr(ledger, "workspace_id", None)
    require(isinstance(wid, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", wid),
            "Mission configuration requires an explicit registered workspace")
    return wid


def bindings(repositories, scope):
    """Pin policy AND mapping without exposing private checkout paths in contracts."""
    by_id = {r["id"]: r for r in repositories}
    result = []
    for row in scope:
        require(row["repository"] in by_id, "Mission references an unregistered repository")
        repo = by_id[row["repository"]]
        result.append({"repository": repo["id"], "policyProfile": repo["policyProfile"],
                       "mergePolicy": repo["mergePolicy"], "mappingHash": digest(repo)})
    return result


def validate(spec, repositories):
    require(isinstance(spec, dict) and set(spec) == {"goal", "successCriteria", "exclusions", "phase", "authority"},
            "Mission fields must match the v1 contract")
    require(len(canonical(spec).encode()) <= 32768, "Mission exceeds 32 KiB")
    goal = text(spec["goal"], "Mission goal")
    criteria = strings(spec["successCriteria"], "Success criteria")
    exclusions = strings(spec["exclusions"], "Exclusions")
    phase = spec["phase"]
    require(isinstance(phase, dict) and set(phase) == {"id", "title", "objective", "checkpoint", "stopConditions", "scope"},
            "Phase fields must match the v1 contract")
    require(isinstance(phase["id"], str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", phase["id"]), "Invalid phase ID")
    clean_phase = {key: text(phase[key], "Phase " + key) for key in ("title", "objective", "checkpoint")}
    clean_phase.update(id=phase["id"], stopConditions=strings(phase["stopConditions"], "Stop conditions"))
    require(isinstance(phase["scope"], list) and 1 <= len(phase["scope"]) <= 20, "Select 1–20 repositories for the phase")
    scope = []
    for row in phase["scope"]:
        require(isinstance(row, dict) and set(row) == {"repository", "allowedPaths", "operations"}, "Invalid repository scope")
        repo = text(row["repository"], "Repository ID", 100)
        paths = strings(row["allowedPaths"], "Allowed paths", maximum=40)
        for path in paths:
            safe_relative(path)
            require(not path.startswith(("*", "?", "[", "!")) and not path.endswith("/") and "//" not in path
                    and not any(p in ("", ".", "..") for p in path.split("/")),
                    "Allowed paths need an explicit repository-relative prefix, not a whole-repository wildcard")
        ops = strings(row["operations"], "Operations", maximum=len(OPERATIONS))
        require(set(ops) <= set(OPERATIONS), "Unknown operation; arbitrary commands are not allowed")
        scope.append({"repository": repo, "allowedPaths": paths, "operations": sorted(ops)})
    require(len({s["repository"] for s in scope}) == len(scope), "Duplicate repository scope")
    scope.sort(key=lambda s: s["repository"])
    repo_bindings = bindings(repositories, scope)
    authority = spec["authority"]
    require(isinstance(authority, dict) and set(authority) in ({"approvalMode", "maxParallelTasks", "maxTasks", "tokenBudget", "checkpointReserveTokens"}, {"approvalMode", "maxParallelTasks", "maxTasks", "tokenBudget", "checkpointReserveTokens", "mergeMode"}),
            "Authority fields must match the v1 contract")
    require(authority["approvalMode"] in MODES, "Unknown approval mode")
    clean_authority = {"approvalMode": authority["approvalMode"]}
    if "mergeMode" in authority:
        require(authority["mergeMode"] in ("manual", "brain_exact_pr_v1"), "Unknown phase merge mode")
        clean_authority["mergeMode"] = authority["mergeMode"]
    if authority.get("mergeMode") == "brain_exact_pr_v1":
        require(authority["approvalMode"] == "phase_delegated" and
                all(b["policyProfile"] == "standard" for b in repo_bindings),
                "Merge delegation requires a standard phase-delegated mission")
        require(sum("merge" in s["operations"] for s in scope) == 1,
                "Merge delegation requires exactly one repository with merge scope")
    for key, upper in (("maxParallelTasks", 16), ("maxTasks", 1000), ("tokenBudget", 1_000_000_000), ("checkpointReserveTokens", 1_000_000_000)):
        clean_authority[key] = integer(authority[key], key, 1, upper)
    require(authority["maxParallelTasks"] <= authority["maxTasks"], "Parallel task limit exceeds total task limit")
    require(authority["checkpointReserveTokens"] < authority["tokenBudget"], "Checkpoint reserve must be smaller than the phase token budget")
    for row, binding in zip(scope, repo_bindings):
        require(not (binding["policyProfile"] == "harness" and authority["approvalMode"] == "phase_delegated"),
                "Harness requires exact owner-approved packets; phase delegation is not allowed")
        require(not (binding["mergePolicy"] == "manual" and "merge" in row["operations"]),
                "Manual-merge repository cannot grant automatic merge authority")
    clean_phase["scope"] = scope
    return {"goal": goal, "successCriteria": criteria, "exclusions": exclusions,
            "phase": clean_phase, "authority": clean_authority}, repo_bindings


def state_in(ledger, db):
    meta = ledger.get(db, "meta", 1)
    current = meta.get("missionConfiguration") or {"revision": 0, "version": 0, "status": "not_configured", "documentHash": None}
    document = ledger.get(db, "snapshots", current["documentHash"]) if current["documentHash"] else None
    issues = []
    if document:
        if document["workspaceId"] != workspace(ledger) or document["brainId"] != meta["brainId"]:
            issues.append("Workspace or brain identity changed; propose a new version.")
        try:
            now = bindings(ledger.all(db, "repos"), document["spec"]["phase"]["scope"])
            if now != document["repositoryBindings"]:
                issues.append("Repository mapping or policy changed; propose and review a new version.")
        except ValueError:
            issues.append("A scoped repository is no longer registered.")
    return {**current, "document": document, "bindingIssues": issues,
            "effectiveStatus": "stale" if issues else current["status"],
            "activation": {"available": False, "status": "not_implemented", "blockers": BLOCKERS},
            "executionAuthority": "Existing exact packet approvals only. This configuration grants no execution authority."}


def read(ledger):
    workspace(ledger)
    with contextlib.closing(ledger.connect()) as db:
        db.execute("BEGIN")
        result = state_in(ledger, db)
        # Linked immutable versions avoid a growing list in ordinary state responses.
        result["history"] = []
        current = result["documentHash"]
        for _ in range(20):
            if not current:
                break
            doc = ledger.get(db, "snapshots", current)
            result["history"].append({"version": doc["version"], "documentHash": current,
                "title": doc["spec"]["phase"]["title"], "createdAt": doc["createdAt"], "actor": doc["actor"]})
            current = doc["previousHash"]
        result["olderDocumentHash"] = current
        return result


def change(ledger, request, actor="dashboard_owner", token=None):
    """Atomic optimistic writes with exact replay receipts; never calls native tools."""
    wid = workspace(ledger)
    require(isinstance(request, dict), "Mission request must be an object")
    operation = request.get("operation")
    require(operation in ("save", "review", "revoke"), "Unknown mission operation")
    fields = {"id", "operation", "expectedRevision", "spec"} if operation == "save" else {
        "id", "operation", "expectedRevision", "documentHash", "confirmed"}
    require(set(request) == fields, "Mission request fields do not match operation")
    require(isinstance(request["id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request["id"]), "Invalid mission request ID")
    integer(request["expectedRevision"], "Mission revision", 0, 1_000_000_000)
    require(actor in ("dashboard_owner", "designated_brain"), "Unsupported mission actor")
    require(actor == "dashboard_owner" or operation == "save", "Only the authenticated owner can review or revoke a mission")
    if operation != "save":
        require(request["confirmed"] is True, "Explicit owner confirmation required")
    fingerprint = digest({"workspaceId": wid, "actor": actor, "request": request})
    request_hash = digest({"kind": "mission_request", "workspaceId": wid, "id": request["id"]})
    with ledger.tx() as db:
        if actor == "designated_brain":
            from .decisions import authorize_brain
            from .brain_control import stopped
            brain_meta = authorize_brain(ledger, db, token)
            require(not stopped(brain_meta), "Stopped brain cannot propose mission changes")
        prior = db.execute("SELECT data FROM snapshots WHERE id=? AND kind='mission_request'", (request_hash,)).fetchone()
        if prior:
            receipt = json.loads(prior[0])
            require(receipt["fingerprint"] == fingerprint, "Mission request ID reused with different content")
            return {"receipt": receipt["result"], "current": state_in(ledger, db)}
        meta = ledger.get(db, "meta", 1)
        current = state_in(ledger, db)
        require(current["revision"] == request["expectedRevision"], "Mission changed; reload and review the current version")
        at = time.time()
        updated = {"revision": current["revision"] + 1, "version": current["version"],
                   "documentHash": current["documentHash"], "status": current["status"]}
        if operation == "save":
            spec, repo_bindings = validate(request["spec"], ledger.all(db, "repos"))
            document = {"schemaVersion": 1, "kind": "mission_configuration", "workspaceId": wid,
                "brainId": meta["brainId"], "version": current["version"] + 1, "createdAt": at, "actor": actor,
                "previousHash": current["documentHash"], "repositoryBindings": repo_bindings, "spec": spec}
            document_hash = digest(document)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (document_hash, "mission_configuration", canonical(document)))
            updated.update(version=document["version"], documentHash=document_hash, status="draft")
        else:
            require(current["documentHash"] is not None and request["documentHash"] == current["documentHash"], "Exact current mission hash required")
            if operation == "review":
                require(current["status"] == "draft", "Only a new draft can be reviewed")
                require(not current["bindingIssues"], "Repository or identity binding changed; save a new version")
                # Revalidate even if the draft was created by an older tool version.
                validate(current["document"]["spec"], ledger.all(db, "repos"))
                updated["status"] = "reviewed"
            else:
                require(current["status"] == "reviewed", "Only a reviewed configuration can be revoked")
                updated["status"] = "revoked"
        receipt = {"id": request["id"], "operation": operation, "actor": actor, "at": at,
                   **updated, "executionAuthorized": False, "nativeNotificationSent": False}
        receipt_hash = digest(receipt)
        db.execute("INSERT INTO snapshots VALUES(?,?,?)", (receipt_hash, "mission_receipt", canonical(receipt)))
        updated["receiptHash"] = receipt_hash
        meta["missionConfiguration"] = updated
        from .run_authority import fence_in
        fence_in(ledger, db, meta, "mission_" + operation)
        ledger.put(db, "meta", 1, meta)
        db.execute("INSERT INTO snapshots VALUES(?,?,?)", (request_hash, "mission_request", canonical({"fingerprint": fingerprint, "result": receipt})))
        ledger.event(db, "mission_configuration_" + operation, {**updated, "actor": actor})
        return {"receipt": receipt, "current": state_in(ledger, db)}
