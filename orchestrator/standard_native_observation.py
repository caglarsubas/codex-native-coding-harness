"""Explicit owned-host observations for the cooperative registered-task contract.

This is not the managed/legacy complete-tree observer, a cleanup adapter, a
scheduler or a wake. Native reads never resume a thread. Only the designated
brain can retain observations, including after a phase Pause or budget stop.
"""
import copy
import json
from pathlib import Path
import subprocess
import time

from .activity import common_directory
from .admission import identifier, sha
from .app_server_wake import load_binding
from .core import ACTIVE, Refusal, canonical, digest, require
from .decisions import authorize_brain
from .enrollment import fence_exists, record_in
from .native_project_assignment import _scope
from .native_read_client import ReadProxy, validate_endpoint
from . import standard

KIND = "standard_native_observation_v1"
MAX_TASKS = 16
MAX_TERMINALS = 64
BOUNDARY = {
    "scope": "registered_standard_tasks_only", "nativeMutationMade": False,
    "taskTreeComplete": False, "processTreeCleanupVerified": False,
    "tokenUsageMeasured": False, "ownershipReleased": False,
    "executionAuthorized": False,
}


def repository_identity(path):
    """Bounded Git pointer files only; never execute Git or read source files."""
    common = common_directory(path)
    require(common == common.resolve(strict=True), "Repository common directory changed")
    info = common.stat()
    return digest({"path": str(common), "device": info.st_dev, "inode": info.st_ino})


class TaskReadProxy(ReadProxy):
    """Restrict the existing read client to this exact brain and task inventory."""
    def __init__(self, endpoint, project_id, thread_ids):
        super().__init__(endpoint)
        self.project_id, self.thread_ids = project_id, frozenset(thread_ids)

    def call(self, method, params):
        if method == "project/read":
            require(params == {"projectId": self.project_id}, "Exact native project read required")
            return self._rpc(method, params)
        require(method in ("thread/read", "thread/backgroundTerminals/list") and
                isinstance(params, dict) and params.get("threadId") in self.thread_ids,
                "Only exact registered native task reads are permitted")
        return super().call(method, params)


def _base_in(registry, ledger, token, registry_db, db, run_id):
    meta = authorize_brain(ledger, db, token)
    run = meta.get("standardRun")
    require(run and run.get("protocol") == standard.PROTOCOL and
            run.get("id") == run_id and run.get("brainId") == meta["brainId"],
            "Exact cooperative standard run required")
    require(record_in(registry_db) is None and not fence_exists(ledger.root) and
            "admissionBinding" not in meta, "Strict enrollment is outside cooperative observation")
    repos = ledger.all(db, "repos")
    require(repos and all(r["policyProfile"] == "standard" for r in repos),
            "Harness requires its trusted observation adapter")
    require(meta["paused"] is True and meta.get("runner") is None and
            not any(w["status"] in ACTIVE for w in ledger.all(db, "workers")),
            "Legacy native ownership must be reconciled separately")
    row = registry_db.execute("SELECT root,brain FROM workspaces WHERE id=?",
                              (getattr(ledger, "workspace_id", None),)).fetchone()
    require(row and row["root"] == str(ledger.root) and row["brain"] == meta["brainId"],
            "Exact registered workspace and brain required")
    return meta, run, {r["id"]: r for r in repos}


def _context_in(registry, ledger, token, registry_db, db, run_id, scope):
    meta, run, repos = _base_in(registry, ledger, token, registry_db, db, run_id)
    require(scope["root"] == ledger.root and scope["brainId"] == meta["brainId"] and
            scope["ledgerRevision"] == meta["revision"] and scope["hostId"] == "local",
            "Owned host scope or ledger changed")
    tasks = [t for t in run["tasks"] if t["status"] not in standard.TERMINAL]
    require(len(tasks) <= MAX_TASKS, "Registered native task inventory exceeds its bound")
    identities = {meta["brainId"]}
    others = list(registry_db.execute("SELECT brain,root FROM workspaces WHERE id<>?", (ledger.workspace_id,)))
    require(len(others) <= 32, "Registered workspace observation bound exceeded")
    foreign = {row["brain"] for row in others}
    for row in others:
        with standard.read_db(Path(row["root"]) / "ledger.sqlite3") as other_db:
            other = ledger.get(other_db, "meta", 1)
            foreign.update(t["threadId"] for t in (other.get("standardRun") or {}).get("tasks", [])
                           if t.get("threadId"))
    foreign |= set(scope.get("otherBrains", []))
    targets = []
    for task in tasks:
        repo = repos.get(task["repository"])
        require(repo and repository_identity(repo["path"]) == task["repositoryIdentity"] ==
                run["identities"].get(repo["id"]), "Registered task repository identity changed")
        tid = task.get("threadId")
        if tid:
            identifier(tid)
            require(tid not in identities and tid not in foreign,
                    "Foreign, duplicate or pending-only native task identity")
            identities.add(tid)
        worktree = task.get("worktree")
        targets.append({"taskId": task["id"], "threadId": tid, "hostId": task.get("hostId"),
                        "repositoryIdentity": task["repositoryIdentity"],
                        "checkout": worktree["root"] if worktree else None,
                        "worktreeRequired": standard.worktrees.repository_mode(run) == standard.worktrees.MODE,
                        "effectIssued": task["effectIssued"]})
    return meta, run, {
        "workspaceId": ledger.workspace_id, "brainId": meta["brainId"],
        "runId": run_id, "runHash": digest(run), "revision": meta["revision"],
        "scopeHash": digest({k: str(v) if isinstance(v, Path) else v for k, v in scope.items()}),
        "targets": targets,
    }


def plan(registry, ledger, token, binding_path, run_id):
    # Refuse strict/foreign runs before inspecting the host or checkout paths.
    with registry.tx() as registry_db, standard.read_db(ledger.db) as db:
        _base_in(registry, ledger, token, registry_db, db, run_id)
    binding = load_binding(binding_path)
    scope = _scope(registry, ledger.workspace_id, binding)
    scope["otherBrains"] = sorted(set(binding["brains"]) - {scope["brainId"]})
    with registry.tx() as registry_db, standard.read_db(ledger.db) as db:
        meta, _, context = _context_in(registry, ledger, token, registry_db, db, run_id, scope)
    return {"runId": run_id, "expectedRevision": meta["revision"],
            "contextHash": digest(context), "bindingHash": digest(binding),
            "registeredTasks": [{"taskId": t["taskId"], "threadId": t["threadId"]}
                                for t in context["targets"]],
            "readOnlyNativeQueriesAttempted": False, "boundary": BOUNDARY}


def _activity(thread):
    status = thread.get("status")
    kind = status.get("type") if isinstance(status, dict) else None
    if kind == "idle" and status.get("activeFlags") in (None, []):
        return "idle"
    return "active" if kind == "active" else "unknown"


def _brain_identity(client, scope, *, include_flags=False):
    project = client.call("project/read", {"projectId": scope["projectId"]}).get("project")
    require(isinstance(project, dict) and project.get("id") == scope["projectId"] and
            isinstance(project.get("roots"), list) and len(project["roots"]) == 1,
            "Exact native project root unavailable")
    path = project["roots"][0].get("path") if isinstance(project["roots"][0], dict) else None
    require(isinstance(path, str) and len(path) <= 4096 and
            digest([scope["hostId"], path]) == scope["locationHash"] and
            repository_identity(path) == repository_identity(scope["cwd"]),
            "Native project repository differs from the reviewed catalog")
    result = client.call("thread/read", {"threadId": scope["brainId"], "includeTurns": False})
    thread = result.get("thread") if isinstance(result, dict) else None
    require(isinstance(thread, dict) and thread.get("id") == scope["brainId"] and
            thread.get("projectId") == scope["projectId"] and thread.get("cwd") == scope["cwd"],
            "Native brain identity differs from the reviewed host binding")
    result = {"nativeStatus": _activity(thread),
              "sourceHash": digest({"id": thread["id"], "projectId": thread["projectId"],
                                    "cwd": thread["cwd"], "status": thread.get("status"), "root": path})}
    if include_flags:
        status = thread.get("status")
        flags = status.get("activeFlags") if isinstance(status, dict) else None
        result["activeFlags"] = flags if isinstance(flags, list) and len(flags) <= 2 and \
            all(f in ("waitingOnApproval", "waitingOnUserInput") for f in flags) and \
            len(set(flags)) == len(flags) else None
    return result


def _thread(client, target):
    response = client.call("thread/read", {"threadId": target["threadId"], "includeTurns": False})
    thread = response.get("thread") if isinstance(response, dict) else None
    require(isinstance(thread, dict) and thread.get("id") == target["threadId"],
            "Native task identity unavailable")
    cwd = thread.get("cwd")
    require(isinstance(cwd, str) and 0 < len(cwd) <= 4096 and
            repository_identity(cwd) == target["repositoryIdentity"] and
            (target["checkout"] is None or cwd == target["checkout"]),
            "Native task checkout differs from registered scope")
    return {"nativeStatus": _activity(thread), "checkoutHash": digest(cwd),
            "sourceHash": digest({"id": thread["id"], "cwd": cwd, "status": thread.get("status")})}


def _terminals(client, thread_id):
    cursor, seen, cursors, identities = None, set(), set(), []
    for _ in range(8):
        page = client.call("thread/backgroundTerminals/list",
                           {"threadId": thread_id, "cursor": cursor, "limit": 64})
        require(isinstance(page, dict) and isinstance(page.get("data"), list) and
                "nextCursor" in page, "Tracked terminal pagination unavailable")
        for item in page["data"]:
            require(isinstance(item, dict), "Invalid tracked terminal metadata")
            identifier(item.get("processId")); identifier(item.get("itemId"))
            require(item["processId"] not in seen, "Duplicate tracked native terminal")
            seen.add(item["processId"])
            identities.append(digest({"processId": item["processId"], "itemId": item["itemId"]}))
        require(len(identities) <= MAX_TERMINALS, "Tracked terminal inventory exceeds its bound")
        cursor = page["nextCursor"]
        if cursor is None:
            return sorted(identities)
        require(isinstance(cursor, str) and 0 < len(cursor) <= 256 and cursor not in cursors,
                "Tracked terminal cursor repeated or invalid")
        cursors.add(cursor)
    raise Refusal("Tracked terminal page bound exceeded")


def _sample(client, target):
    row = {"taskId": target["taskId"], "threadId": target["threadId"],
           "nativeStatus": "unknown", "trackedTerminals": "unknown",
           "trackedTerminalCount": None, "sourceHash": None, "issues": []}
    if not target["threadId"] or not target["effectIssued"]:
        row["issues"] = ["native_identity_unconfirmed"]
        return row
    if target["hostId"] != "local" or target["worktreeRequired"] and target["checkout"] is None:
        row["issues"] = ["native_checkout_binding_unavailable"]
        return row
    try:
        before = _thread(client, target)
        # notLoaded is not idle. Terminals/list is only documented for loaded
        # threads, and an old completed turn does not establish current safety.
        require(before["nativeStatus"] != "unknown", "Native activity unavailable")
        terminals = _terminals(client, target["threadId"])
        after = _thread(client, target)
        require(before == after, "Native task changed during terminal observation")
        row.update(nativeStatus=after["nativeStatus"],
                   trackedTerminals="running" if terminals else "none",
                   trackedTerminalCount=len(terminals), sourceHash=digest([after, terminals]))
    except (Refusal, OSError, ValueError, TypeError, KeyError, UnicodeError):
        row["issues"] = ["native_task_observation_unavailable"]
    return row


def _collect(binding, scope, context):
    proxy = TaskReadProxy(binding["endpoint"], scope["projectId"],
                          [context["brainId"], *[t["threadId"] for t in context["targets"] if t["threadId"]]])
    started = time.time()
    issues, brain, samples = [], None, None
    try:
        with proxy as client:
            brain = _brain_identity(client, scope)
            first = [_sample(client, t) for t in context["targets"]]
            samples = [_sample(client, t) for t in context["targets"]]
            require(_brain_identity(client, scope)["sourceHash"] == brain["sourceHash"],
                    "Native brain or project changed during collection")
            for before, row in zip(first, samples):
                if before != row:
                    row.update(nativeStatus="unknown", trackedTerminals="unknown",
                               trackedTerminalCount=None, issues=["native_task_changed_during_collection"])
        validate_endpoint(binding["endpoint"])
    except (Refusal, OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        issues = ["owned_host_observation_unavailable"]
        brain = None
        samples = [{"taskId": t["taskId"], "threadId": t["threadId"], "nativeStatus": "unknown",
                    "trackedTerminals": "unknown", "trackedTerminalCount": None, "sourceHash": None,
                    "issues": issues} for t in context["targets"]]
    # The timestamp belongs to this collection, never to a later read/replay.
    return {"startedAt": started, "observedAt": time.time(), "brain": brain, "samples": samples,
            "issues": issues, "readOnlyNativeQueriesAttempted": proxy.query_attempted,
            "boundary": BOUNDARY}


def _prior_in(db, request):
    key = digest({"kind": KIND + "_request", "id": request["id"]})
    row = db.execute("SELECT kind,data FROM snapshots WHERE id=?", (key,)).fetchone()
    if not row:
        return key, None
    receipt = json.loads(row["data"])
    require(row["kind"] == KIND + "_request" and receipt["requestHash"] == digest(request),
            "Native observation request ID belongs to different content")
    report = report_in(db, receipt["reportHash"])
    require(receipt["runId"] == report["runId"] == request["runId"] and
            report["requestId"] == request["id"] and report["contextHash"] == request["contextHash"] and
            report["bindingHash"] == request["bindingHash"], "Foreign retained native observation receipt")
    return key, {**receipt, "report": report}


def report_in(db, key):
    row = db.execute("SELECT kind,data FROM snapshots WHERE id=?", (key,)).fetchone()
    require(row and row["kind"] == KIND and isinstance(row["data"], str) and len(row["data"].encode()) <= 100_000,
            "Retained native task observation unavailable")
    try:
        value = json.loads(row["data"])
    except ValueError:
        raise Refusal("Retained native task observation is invalid") from None
    require(isinstance(value, dict) and digest(value) == key and value.get("boundary") == BOUNDARY,
            "Retained native task observation changed")
    return value


def collect(registry, ledger, token, binding_path, request):
    request = copy.deepcopy(request)
    standard.exact(request, "id runId expectedRevision contextHash bindingHash")
    identifier(request["id"]); identifier(request["runId"])
    sha(request["contextHash"]); sha(request["bindingHash"])
    require(type(request["expectedRevision"]) is int and request["expectedRevision"] >= 0,
            "Exact ledger revision required")
    with registry.tx() as registry_db, ledger.tx() as db:
        _base_in(registry, ledger, token, registry_db, db, request["runId"])
        key, prior = _prior_in(db, request)
        if prior:
            return prior  # No binding/file/native reads and no refreshed clock.
    binding = load_binding(binding_path)
    require(digest(binding) == request["bindingHash"], "Reviewed owned host binding changed")
    scope = _scope(registry, ledger.workspace_id, binding)
    scope["otherBrains"] = sorted(set(binding["brains"]) - {scope["brainId"]})
    with registry.tx() as registry_db, ledger.tx() as db:
        meta, _, context = _context_in(registry, ledger, token, registry_db, db, request["runId"], scope)
        require(meta["revision"] == request["expectedRevision"] and digest(context) == request["contextHash"],
                "Registered task observation context changed")
    report = _collect(binding, scope, context)
    require(load_binding(binding_path) == binding and
            _scope(registry, ledger.workspace_id, binding) == {k: v for k, v in scope.items() if k != "otherBrains"},
            "Owned host or catalog changed during observation")
    with registry.tx() as registry_db, ledger.tx() as db:
        meta, run, current = _context_in(registry, ledger, token, registry_db, db, request["runId"], scope)
        _, prior = _prior_in(db, request)
        if prior:
            return prior
        require(meta["revision"] == request["expectedRevision"] and digest(current) == request["contextHash"],
                "Pause, run or registered task context changed during observation")
        report.update(kind=KIND, workspaceId=ledger.workspace_id, brainId=meta["brainId"],
                      runId=run["id"], requestId=request["id"], contextHash=request["contextHash"],
                      bindingHash=request["bindingHash"])
        report_hash = digest(report)
        db.execute("INSERT INTO snapshots VALUES(?,?,?)", (report_hash, KIND, canonical(report)))
        for row in report["samples"]:
            task = standard.find_task(run, row)
            task.update(nativeStatus=row["nativeStatus"], trackedTerminals=row["trackedTerminals"],
                        observedAt=report["observedAt"], observationSource="owned_app_server.registered_task_read",
                        nativeObservationHash=report_hash)
        # Counters, attempt ownership, run status, limits and the legacy Stop are
        # unchanged. Unknown samples invalidate old finish observations.
        run["nativeObservationHash"] = report_hash
        standard.save(ledger, db, meta, run, "native_observation")
        receipt = {"requestHash": digest(request), "runId": run["id"], "reportHash": report_hash,
                   "retainedAt": time.time()}
        db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, KIND + "_request", canonical(receipt)))
        return {**receipt, "report": report}
