"""One-shot cooperative merge handoff. Only the designated brain executes gh.

Local source and GitHub metadata are measured; semantic review and local test
results are explicitly brain-supplied evidence, never host/CI attestation.
"""
import base64
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import quote

from . import missions, standard
from .core import ACTIVE, canonical, digest, require
from .decisions import authorize_brain
from .enrollment import record_in
from .github_evidence import (api_read, pr_target, pull_projection, policy_projection,
                              checks_projection, ci_projection, inventory)
from .resources import git_metadata
from .source_observation import (oid, branch_ref, layout, check_objects, object_view,
                                 git_read, commit_tree, changes, ref_value)

MODE = "brain_exact_pr_v1"
MAX_AGE = 300
BOUNDARY = ("Merge observation only; semantic correctness, CI, deployment, runtime, "
            "archival and phase acceptance remain separate. No automatic resend.")


def fresh(value):
    require(type(value) in (int, float) and 0 <= time.time()-value < MAX_AGE,
            "Fresh original observation time required")


def retain(db, kind, value):
    key = digest(value)
    db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?)", (key, kind, canonical(value)))
    return key


def document(ledger, db, key):
    require(isinstance(key, str) and re.fullmatch(r"[a-f0-9]{64}", key), "Exact retained hash required")
    value = ledger.get(db, "snapshots", key)
    require(digest(value) == key, "Retained merge evidence changed")
    return value


def authority(ledger, db, run, task):
    require(run["protocol"] == standard.PROTOCOL and run["status"] == "running" and
            not standard.current_blockers(ledger, db, run), "Merge run stopped, expired or review stale")
    meta = ledger.get(db, "meta", 1)
    require(meta.get("brainControl", {}).get("phase") in (None, "ready") and meta.get("brainControl", {}).get("desired", "running") == "running", "Brain stop fences merge")
    require(run["brainId"] == meta["brainId"], "Designated brain changed")
    require(run["limits"].get("mergeMode") == MODE, "Manual merge is the default; exact opt-in required")
    require(all(t["status"] in standard.TERMINAL for t in run["tasks"]), "Unresolved registered native work")
    require(task["status"] == "completed" and task.get("threadId") and task.get("result"), "Completed registered result required")
    repo = ledger.get(db, "repos", task["repository"])
    require(repo["policyProfile"] == "standard" and repo["mergePolicy"] == "required_checks", "Harness and manual repository policies refuse merge")
    mission = missions.state_in(ledger, db)
    scope = next(s for s in mission["document"]["spec"]["phase"]["scope"] if s["repository"] == task["repository"])
    require("merge" in scope["operations"], "Reviewed merge scope required")
    require(standard.git_root(repo["path"]) == task["repositoryIdentity"] == run["identities"][repo["id"]], "Repository identity changed")
    result = document(ledger, db, task["result"])
    require(result["taskId"] == task["id"] and result["runId"] == run["id"] and result["outcome"] == "completed", "Result binding changed")
    seed = document(ledger, db, task["seedHash"])
    require(seed["repository"] == repo, "Task repository mapping changed")
    return repo


def remote_identity(path):
    # Only config data is read; no remote command, URL helper or credential query.
    value = git_metadata(path, "config", "--file", str(path / "config"),
                         "--no-includes", "--get-all", "remote.origin.url")
    require(len(value) < 1024, "Exact conventional origin required")
    match = re.fullmatch(r"(?:git@github\.com:|https://github\.com/)([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+?)(?:\.git)?\n?", value)
    require(match is not None, "Ambiguous or unsupported origin")
    return match[1].lower()


def source(repo, task, binding):
    """Retain complete bounded changed-source bytes and inventories from exact objects."""
    started = time.time()
    # Derive the existing isolated reader's common-dir key from the pinned local
    # directory, then check the standard identity again after all I/O.
    root = Path(repo["path"]).resolve(strict=True)
    common = Path(git_metadata(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve(strict=True)
    stat = common.stat()
    key = "repo-local:" + digest({"device": stat.st_dev, "inode": stat.st_ino})
    common, objects, pin = layout(root, key)
    slug, _, _ = pr_target(binding["prUrl"])
    require(remote_identity(common) == slug, "PR does not match pinned repository origin")
    check_objects(objects)
    require(ref_value(common, branch_ref(binding["headBranch"])) == binding["headSHA"], "Local result branch head drifted")
    with object_view(objects) as view:
        tree = commit_tree(view, binding["headSHA"])
        commit_tree(view, binding["baseSHA"])
        require(git_read(view, ["merge-base", binding["baseSHA"], binding["headSHA"]]).decode().strip() == binding["baseSHA"], "Head must include the exact base")
        raw = git_read(view, ["diff-tree", "--no-commit-id", "--raw", "-r", "--no-renames", "-z", binding["baseSHA"], binding["headSHA"]])
        changed = changes(raw)
        blobs = {}; preserved_bytes = 0
        for row in changed:
            require(any(fnmatch.fnmatchcase(row["path"], p) for p in task["paths"]), "Changed source outside registered task paths")
            if row["change"] != "D" and row["newObject"] not in blobs:
                raw_blob = git_read(view, ["cat-file", "blob", row["newObject"]], bound=2_000_000)
                preserved_bytes += len(raw_blob)
                require(preserved_bytes <= 2_000_000, "Changed-source preservation exceeds its bound")
                require(hashlib.sha1(b"blob "+str(len(raw_blob)).encode()+b"\0"+raw_blob).hexdigest() == row["newObject"],
                        "Preserved source bytes do not match the exact head object")
                blobs[row["newObject"]] = base64.b64encode(raw_blob).decode()
        patch = git_read(view, ["diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index", "--no-renames", binding["baseSHA"], binding["headSHA"]], bound=2_000_000)
        git_read(view, ["diff", "--check", binding["baseSHA"], binding["headSHA"]])
        paths = git_read(view, ["ls-tree", "-r", "--name-only", "-z", binding["headSHA"]], bound=1_000_000).decode().rstrip("\0").split("\0")
        base_paths = git_read(view, ["ls-tree", "-r", "--name-only", "-z", binding["baseSHA"]], bound=1_000_000).decode().rstrip("\0").split("\0")
    require(layout(root, key)[2] == pin and standard.git_root(root) == task["repositoryIdentity"] and remote_identity(common) == slug and
            ref_value(common, branch_ref(binding["headBranch"])) == binding["headSHA"], "Repository changed during collection")
    return {"headSHA": binding["headSHA"], "baseSHA": binding["baseSHA"], "tree": tree,
            "changes": changed, "blobsBase64": blobs, "patchBase64": base64.b64encode(patch).decode(),
            "patchSHA256": hashlib.sha256(patch).hexdigest(), "paths": paths,
            "baseWorkflows": [p for p in base_paths if p.startswith(".github/workflows/")],
            "headWorkflows": [p for p in paths if p.startswith(".github/workflows/")],
            "observedAt": started, "repositoryIdentity": task["repositoryIdentity"]}


def remote(binding, *, terminal=False):
    """Two bounded GET rounds; no ambiguous policy absence or hidden pagination."""
    slug, number, _ = pr_target(binding["prUrl"])
    root = "repos/"+slug+"/"; started = time.time(); deadline = time.monotonic()+45
    def get(suffix):
        require(time.monotonic() < deadline, "Merge inspection deadline exceeded")
        return api_read(root+suffix, deadline)
    rounds = []
    for _ in range(2):
        pull = get("pulls/"+str(number))
        # After a merge the base tip necessarily advances. Still bind the original
        # head/repository/branches, and record the new base separately.
        base = pull.get("base", {}).get("sha") if terminal or pull.get("merged") is True else binding["baseSHA"]
        oid(base)
        pr = pull_projection(pull, slug, number, binding["headSHA"], base, binding["headBranch"])
        require(pr["baseBranch"] == binding["baseBranch"], "PR base branch drifted")
        observed = {**pr, "mergeable": pull.get("mergeable"), "mergeableState": pull.get("mergeable_state")}
        if not terminal and pr["pr"]["state"] == "open":
            target = quote(binding["baseBranch"], safe="")
            branch = get("branches/"+target)
            require(branch.get("commit", {}).get("sha") == binding["baseSHA"] and type(branch.get("protected")) is bool, "Base branch changed or policy unknown")
            classic = get("branches/"+target+"/protection") if branch["protected"] else {"required_status_checks": None}
            rules = get("rules/branches/"+target+"?per_page=100&page=1")
            policy = policy_projection(classic, rules)
            commit = binding["headSHA"]
            suites = get("commits/"+commit+"/check-suites?per_page=100&page=1")
            require(all(s.get("status") == "completed" and s.get("conclusion") == "success" for s in inventory(suites, "check_suites")), "Check suite missing, pending or failed")
            checks = checks_projection(suites,
                get("commits/"+commit+"/check-runs?filter=all&per_page=100&page=1"),
                get("commits/"+commit+"/status?per_page=100&page=1"), commit, slug)
            workflows = inventory(get("actions/workflows?per_page=100&page=1"), "workflows")
            ci, status, issues = ci_projection(policy, checks, commit)
            require(set(checks["suiteIds"]) == {r["suiteId"] for r in checks["runs"]}, "Check-suite run coverage incomplete")
            for required in policy["required"]:
                candidates = [r for r in checks["runs"] if r["name"] == required["context"] and (required["appId"] is None or r["appId"] == required["appId"])]
                if required["appId"] is None:
                    candidates += [r for r in checks["statuses"] if r["name"] == required["context"]]
                require(len(candidates) == 1, "Required check missing or provider/rerun ambiguous")
            observed.update(policy=policy, checks=checks, ci=ci, ciStatus=status, issues=issues,
                            workflowCount=len(workflows), workflowHash=digest(workflows))
        rounds.append(observed)
    require(rounds[0] == rounds[1], "PR, policy or checks changed during verification")
    return {**rounds[0], "observedAt": started, "atomicSnapshot": False}


def validate_evidence(evidence, run, task, binding, measured):
    standard.exact(evidence, "headSHA resultHash reviewer verdict summary local native")
    require(evidence["headSHA"] == binding["headSHA"] and evidence["resultHash"] == task["result"], "Review/result must bind exact head")
    require(evidence["reviewer"] == run["brainId"] and evidence["reviewer"] != task["threadId"] and evidence["verdict"] == "passed", "Independent designated-brain review must pass")
    missions.text(evidence["summary"], "Independent source and result review", 8000)
    native = evidence["native"]
    standard.exact(native, "observedAt tasks")
    fresh(native["observedAt"])
    expected = sorted(t["threadId"] for t in run["tasks"] if t.get("threadId"))
    require(isinstance(native["tasks"], list) and len(native["tasks"]) == len(expected), "Complete registered task inventory required")
    for row in native["tasks"]:
        standard.exact(row, "threadId status trackedTerminals")
        require(row["status"] in ("completed", "idle") and row["trackedTerminals"] == "none", "Native work unresolved")
    require(sorted(r["threadId"] for r in native["tasks"]) == expected, "Native task inventory mismatch")
    local = evidence["local"]
    standard.exact(local, "observedAt headSHA complete python javascript syntax diff")
    fresh(local["observedAt"])
    require(local["headSHA"] == binding["headSHA"] and local["complete"] is True, "Complete exact-head local coverage required")
    paths = measured["paths"]
    expected_commands = {
        "python": [["python3", "-m", "unittest", "discover", "-s", "tests", "-v"]],
        "javascript": [["node", p] for p in sorted(paths) if p.startswith("tests/") and p.endswith(".js")],
        "syntax": [["python3", "-m", "compileall", "-q", "orchestrator", "tests"]] +
                  [["node", "--check", p] for p in sorted(paths) if p.endswith(".js")],
        "diff": [["git", "diff", "--check", binding["baseSHA"], binding["headSHA"]]],
    }
    for kind, commands in expected_commands.items():
        require(isinstance(local[kind], list) and len(local[kind]) == len(commands), "Incomplete local "+kind+" coverage")
        for row, command in zip(local[kind], commands):
            standard.exact(row, "argv exitCode output")
            require(row["argv"] == command and type(row["exitCode"]) is int and row["exitCode"] == 0, "Local checks missing, failed or ambiguous")
            missions.text(row["output"], "Retained local check evidence", 8000)


def merge_ready(report, measured):
    fresh(report["observedAt"])
    require(report["pr"]["state"] == "open" and report["draft"] is False and report["mergeable"] is True and
            report["mergeableState"] == "clean", "PR must be open, non-draft and cleanly mergeable")
    issues = report["issues"]
    no_workflows = report["workflowCount"] == 0 and not measured["headWorkflows"] and not measured["baseWorkflows"]
    require(not issues or (issues == ["no_required_checks"] and no_workflows), "Required-check policy or coverage unavailable")
    require(all(c["status"] == "passed" for c in report["ci"]["checks"]), "Required checks did not succeed")
    require(all(c["status"] == "passed" for c in report["checks"]["runs"]+report["checks"]["statuses"]), "Pending or failed checks refuse merge")
    require(report["policy"]["required"] or no_workflows, "No checks is not success; explicit no-workflow evidence required")
    return no_workflows



def registry_guard(registry_db, ledger, task, binding):
    for row in registry_db.execute("SELECT root FROM workspaces WHERE id<>?", (missions.workspace(ledger),)):
        with standard.read_db(Path(row["root"])/"ledger.sqlite3") as other:
            other_run = ledger.get(other, "meta", 1).get("standardRun") or {}
            require(not any(w["status"] in ACTIVE for w in ledger.all(other, "workers")), "Another workspace has unresolved legacy/strict work")
            require(not any(m["repositoryIdentity"] == task["repositoryIdentity"] and m["status"] in ("prepared", "issued", "uncertain")
                            for m in other_run.get("merges", [])), "Another merge owns this repository")
            require(not any(t["repositoryIdentity"] == task["repositoryIdentity"] and t["status"] not in standard.TERMINAL
                            for t in other_run.get("tasks", [])), "Another registered task owns this repository")
            for prior in other.execute("SELECT data FROM snapshots WHERE kind='standard_merge_binding'"):
                require(json.loads(prior[0])["binding"]["prUrl"] != binding["prUrl"], "Another workspace already owns this PR")

def brain(registry, ledger, token, request):
    operation = request.get("operation")
    fields = {"merge_prepare": "binding evidence", "merge_check": "evidence",
              "merge_receipt": "delivery", "merge_reconcile": ""}
    require(operation in fields, "Unknown merge operation")
    standard.exact(request, "operation runId taskId requestId "+fields[operation])
    missions.text(request["requestId"], "Immutable merge request ID", 100)
    # Copy context under locks. I/O is outside locks so Pause can commit promptly.
    with registry.tx() as rdb, ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        require(record_in(rdb) is None, "Strict enrollment fences merge")
        run = meta.get("standardRun")
        require(run and run["id"] == request["runId"], "Exact current standard run required")
        task = standard.find_task(run, request)
        entry = next((m for m in run.get("merges", []) if m["requestId"] == request["requestId"]), None)
        if entry:
            require(entry["taskId"] == task["id"], "Merge request belongs to another task")
            binding_doc = document(ledger, db, entry["bindingHash"])
            binding = binding_doc["binding"]
            if operation == "merge_prepare":
                require(binding_doc["request"] == request, "Immutable merge request ID reused")
                return {"merge": entry, "replay": True}  # No I/O, freshness or arguments on replay.
            if operation == "merge_reconcile" and entry["status"] in ("merged", "not-merged"):
                return {"merge": entry, "replay": True}
            if operation == "merge_check" and entry["status"] != "prepared":
                return {"merge": entry, "replay": True}
        else:
            require(operation == "merge_prepare", "Prepare the exact merge request first")
            require(not run.get("merges"), "One exact PR per run; no replacement or retry slot")
            binding = request["binding"]
            standard.exact(binding, "prUrl number baseBranch headBranch baseSHA headSHA")
            slug, number, _ = pr_target(binding["prUrl"])
            require(number == binding["number"] and type(binding["number"]) is int, "PR number mismatch")
            require(binding["prUrl"] == f"https://github.com/{slug}/pull/{number}", "Canonical PR URL required")
            oid(binding["headSHA"]); oid(binding["baseSHA"]); branch_ref(binding["headBranch"])
            require(isinstance(binding["baseBranch"], str) and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}", binding["baseBranch"]), "Invalid base branch")
            for row in db.execute("SELECT data FROM snapshots WHERE kind='standard_merge_binding'"):
                prior = json.loads(row[0])
                require(prior["request"]["requestId"] != request["requestId"] and prior["binding"]["prUrl"] != binding["prUrl"], "Duplicate PR or merge request remains permanently retained")
        if operation in ("merge_prepare", "merge_check"):
            repo = authority(ledger, db, run, task)
            require(document(ledger, db, task["result"])["evidence"].get("headSHA") == binding["headSHA"], "Completed result must record the exact merge head")
            registry_guard(registry_db=rdb, ledger=ledger, task=task, binding=binding)
        else:
            require(entry is not None, "Existing merge journal required")
            repo = ledger.get(db, "repos", task["repository"])
        revision = meta["revision"]
        run_revision = run["revision"]
        if operation == "merge_receipt":
            require(request["delivery"] in ("acknowledged", "unknown", "failed"), "Explicit delivery outcome required")
            require(entry["status"] in ("issued", "uncertain"), "No issued merge to receipt")
            if entry["status"] == "uncertain":
                require(entry.get("delivery") == request["delivery"], "Delivery receipt is immutable")
                return {"merge": entry, "replay": True}
            entry.update(status="uncertain", delivery=request["delivery"], receiptAt=time.time())
            entry["receiptHash"] = retain(db, "standard_merge_receipt", {"request": request, "at": entry["receiptAt"]})
            standard.save(ledger, db, meta, run, operation)
            return {"merge": entry}
    measured = None
    if operation in ("merge_prepare", "merge_check"):
        measured = source(repo, task, binding)
        validate_evidence(request["evidence"], run, task, binding, measured)
    report = remote(binding, terminal=operation == "merge_reconcile")
    if operation in ("merge_prepare", "merge_check") and report["pr"]["state"] == "open":
        no_workflows = merge_ready(report, measured)
    else:
        no_workflows = False
    with registry.tx() as rdb, ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        current = meta.get("standardRun")
        require(current and current["id"] == run["id"] and current["revision"] == run_revision and meta["revision"] == revision,
                "Context changed during merge inspection; no permission issued")
        require(record_in(rdb) is None, "Strict enrollment fences merge")
        task = standard.find_task(current, request)
        if operation in ("merge_prepare", "merge_check"):
            authority(ledger, db, current, task)
            registry_guard(registry_db=rdb, ledger=ledger, task=task, binding=binding)
            validate_evidence(request["evidence"], current, task, binding, measured)
            fresh(report["observedAt"])
        if operation == "merge_prepare":
            value = {"request": request, "binding": binding, "workspaceId": missions.workspace(ledger),
                     "runId": run["id"], "taskId": task["id"], "resultHash": task["result"],
                     "repositoryIdentity": task["repositoryIdentity"], "repositoryHash": digest(repo),
                     "missionHash": run["missionHash"], "reviewHash": run["reviewHash"],
                     "sourceHash": retain(db, "standard_merge_source", measured), "boundary": BOUNDARY}
            entry = {"requestId": request["requestId"], "taskId": task["id"], "repositoryIdentity": task["repositoryIdentity"], "prUrl": binding["prUrl"],
                     "headSHA": binding["headSHA"], "status": "prepared", "preparedAt": time.time(),
                     "bindingHash": retain(db, "standard_merge_binding", value)}
            current.setdefault("merges", []).append(entry)
        else:
            entry = next(m for m in current["merges"] if m["requestId"] == request["requestId"])
        state = report["pr"]["state"]
        if state == "merged": entry.update(status="merged", mergeCommit=report["pr"]["mergeCommit"])
        elif state == "closed": entry["status"] = "not-merged"
        elif operation == "merge_check":
            value = document(ledger, db, entry["bindingHash"])
            original = document(ledger, db, value["sourceHash"])
            require({k:v for k,v in original.items() if k != "observedAt"} == {k:v for k,v in measured.items() if k != "observedAt"}, "Preserved source drifted")
            entry.update(status="issued", issuedAt=time.time())
        elif operation == "merge_reconcile" and entry["status"] in ("issued", "uncertain"):
            entry["status"] = "uncertain"  # Open is not proof a delayed send cannot execute.
        observation = {"request": request, "report": report, "noWorkflowObservation": no_workflows,
                       "sourceHash": retain(db, "standard_merge_source", measured) if measured else None,
                       "status": entry["status"], "at": time.time(), "boundary": BOUNDARY}
        entry["observationHash"] = retain(db, "standard_merge_observation", observation)
        entry["observedAt"] = report["observedAt"]
        standard.save(ledger, db, meta, current, operation)
        response = {"merge": entry, "boundary": BOUNDARY}
        if operation == "merge_check" and entry["status"] == "issued":
            response["argv"] = ["gh", "pr", "merge", binding["prUrl"], "--merge", "--match-head-commit", binding["headSHA"]]
        return response
