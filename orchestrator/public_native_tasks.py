"""Opt-in public app-server task transport for the designated standard brain.

The owned observer, not the sandbox or a background dispatcher, consumes each
explicit request. Creation and first-turn claims are permanent and separate.
This does not use, impersonate or forward the protected desktop tools pipe.
"""
import copy
from pathlib import Path
import threading
import time
import uuid

from . import standard
from .core import ACTIVE, Refusal, canonical, digest, require
from .decisions import authorize_brain
from .native_policy_evidence import collect, matches, reported, validate_contract as policy_contract
from .native_auth_readiness import require_ready as require_authentication
from .native_project_assignment import _scope
from .standard_host_inspection import (_context as owned_context, _read_private,
                                       _write_once, binding_file, _mailbox)
from .standard_native_observation import _base_in, _brain_identity, _terminals

PROTOCOL = "public_app_server_tasks_v1"
CONTRACT_FIELDS = {"protocol", "sourceCommit", "sourceTree", "trust", "desktopBridge", "repositoryMode"}
REQUEST_FIELDS = {"version", "runId", "commandId", "taskId", "seedHash", "bindingHash",
                  "contextHash", "controllerHash", "requestedAt"}
REQUEST_SECONDS = 30
TASK_FIELDS = {"version", "protocol", "bindingHash", "commandId", "seedHash", "stage",
               "threadId", "turnId", "responseHash", "observedAt", "terminalCoverage", "sourceBase"}
STAGES = {"creation_claimed", "created", "turn_claimed", "started", "ended",
          "pre_turn_blocked", "uncertain", "native_attention_required"}


def validate_contract(value, policy):
    require(isinstance(value, dict) and set(value) == CONTRACT_FIELDS and
            value.get("protocol") == PROTOCOL and value.get("trust") == "operator_reviewed_build_v1" and
            value.get("desktopBridge") == "absent" and value.get("repositoryMode") == "repo_exclusive",
            "Exact application-owned public task contract required; desktop trust is not transferable")
    policy_contract(policy)
    require(all(value[k] == policy[k] for k in ("sourceCommit", "sourceTree")),
            "Task and effective-policy native builds differ")
    return value


def _paths(ledger, command_id, task_id):
    from .admission import identifier
    identifier(task_id)
    # No caller-supplied path or endpoint is carried across the sandbox boundary.
    return {name: _mailbox(ledger, command_id, "-public-task-" + digest(task_id) + "-" + name)
            for name in ("request", "claim", "reply")}


def _context(registry, ledger, token, run_id, command_id, task_id, *, sending=False):
    context = owned_context(registry, ledger, token, run_id, command_id)
    require(context["transport"] == "owned_observer_v1", "Public task effects require the owned observer")
    with registry.tx() as registry_db, standard.read_db(ledger.db) as db:
        meta, run, _ = _base_in(registry, ledger, token, registry_db, db, run_id)
        require(run["status"] == "running" and not standard.current_blockers(ledger, db, run),
                "Run, policy, usage, Pause or duration fences new public native effects")
        require(standard.worktrees.repository_mode(run) == "repo_exclusive",
                "Public adapter does not qualify isolated native worktree creation")
        require(len(run["tasks"]) <= 16, "Public task inventory exceeds its qualified bound")
        require(not context["approvals"] or all(a.get("status") in ("resolved", "resolved_without_response")
                for a in context["approvals"]), "A native permission request retains ownership")
        task = standard.find_task(run, {"taskId": task_id})
        _capacity_in(registry_db, ledger, db, run, task)
        if sending:
            require(task["status"] == "creating" and task.get("publicNative"), "Exact public creation claim required")
        else:
            require(task["status"] == "claimed" and not task["effectIssued"] and not task.get("publicNative"),
                    "Existing or uncertain native issue cannot become a public task fallback")
        require(not any(t["id"] != task_id and t["status"] not in standard.TERMINAL and
                t["repositoryIdentity"] == task["repositoryIdentity"] for t in run["tasks"]),
                "Repository ownership is not exclusive")
        require(not any(m.get("status") in ("prepared", "issued", "uncertain") for m in run.get("merges", [])),
                "A phase merge retains ownership")
        repo = ledger.get(db, "repos", task["repository"])
        row = db.execute("SELECT kind,data FROM snapshots WHERE id=?", (task["seedHash"],)).fetchone()
        require(row and row["kind"] == "standard_seed", "Immutable standard seed is missing")
        from .native_read_client import decode
        seed = decode(row["data"])
        require(digest(seed) == task["seedHash"] and seed["runId"] == run_id and seed["taskId"] == task_id and
                seed["repository"] == repo and all(task.get(k) == v for k,v in seed["task"].items()) and
                standard.git_root(repo["path"]) == task["repositoryIdentity"] == run["identities"][repo["id"]],
                "Source, task or inheritance binding changed")
        # Controller and revision rechecks below pin these local reads at effects.
        return {"owned": context, "revision": meta["revision"], "runHash": digest(run),
                "task": copy.deepcopy(task), "repository": repo, "seed": seed, "sourceBase": _source_base(repo["path"])}


def _source_base(root):
    from .resources import git_metadata
    from .source_observation import inspect_base, oid
    base = oid(git_metadata(root, "rev-parse", "--verify", "HEAD"))
    proof = inspect_base(root, standard.worktrees.resource_key(root), base)
    return {k: proof[k] for k in ("baseSHA", "baseTree", "resourceKey", "layoutHash")}


def _capacity_in(registry_db, ledger, db, run, task):
    active = [t for t in run["tasks"] if t["status"] not in standard.TERMINAL]
    require(len(active) <= run["limits"]["maxParallelTasks"] and
            standard.charged(run) + run["limits"]["checkpointReserveTokens"] < run["limits"]["tokenBudget"],
            "Capacity or conservative budget changed before public native effect")
    require(not any(q["status"] == "approved" for q in ledger.all(db, "queue")), "Legacy queue authority is unresolved")
    owners = active[:]
    for row in registry_db.execute("SELECT id,root FROM workspaces WHERE id<>?", (ledger.workspace_id,)):
        with standard.read_db(Path(row["root"])/"ledger.sqlite3") as other:
            meta = ledger.get(other, "meta", 1)
            require(not any(w["status"] in ACTIVE for w in ledger.all(other, "workers")), "Foreign legacy owner is unresolved")
            foreign_run = meta.get("standardRun") or {}
            foreign = [t for t in foreign_run.get("tasks", []) if t["status"] not in standard.TERMINAL]
            require(not any(t["repositoryIdentity"] == task["repositoryIdentity"] for t in foreign) and
                    not any(m["repositoryIdentity"] == task["repositoryIdentity"] and
                    m["status"] in ("prepared", "issued", "uncertain") for m in foreign_run.get("merges", [])),
                    "Cross-workspace repository ownership changed")
            owners.extend(foreign)
    require(len(owners) <= 16, "Registered platform capacity changed")


def arguments(seed, record):
    """Translate only the retained task seed, never model/browser-authored RPC."""
    task, repo = seed["task"], seed["repository"]
    require(repo["path"] == record["cwd"], "First public adapter supports the bound brain repository only")
    validate_contract(record.get("nativeTaskBackend"), record.get("policyEvidence"))
    instructions = ("Implement only this exact owner-reviewed standard task. Do not create other tasks, "
                    "merge, change policy, reset usage or retry uncertain effects. Honor repository AGENTS.md. "
                    "Stop at the task's acceptance/checkpoint boundary.\nImmutable seed SHA-256: " + digest(seed) +
                    "\nAllowed files: " + canonical(task["paths"]) + "\nTask instructions: " + seed["instructions"] +
                    "\nAcceptance: " + canonical(seed["acceptance"]) + "\nReviewed mission: " + canonical(seed["mission"]))
    require(len(instructions.encode()) <= 48000, "Public task inheritance exceeds its bound")
    start = {"cwd": repo["path"], "projectId": record["projectId"], "model": task["model"],
             "approvalPolicy": "on-request", "approvalsReviewer": "user", "sandbox": "workspace-write",
             "config": {"features": {"code_mode": {"enabled": False}}, "model_reasoning_effort": task["effort"]},
             "ephemeral": False}
    return start, {"input": [{"type": "text", "text": instructions, "text_elements": []}],
                   "model": task["model"], "effort": task["effort"],
                   "approvalPolicy": "on-request", "approvalsReviewer": "user"}


def _uuid(value):
    require(isinstance(value, str) and str(uuid.UUID(value)) == value, "Confirmed native UUID required")
    return value


class PublicTaskProxy:
    """Narrow facade: two fixed writes; no arbitrary RPC or permission response."""
    def __init__(self, endpoint, start, turn, brain_id=None):
        from .app_server_wake import WakeProxy
        self.proxy = WakeProxy(endpoint)
        self.proxy.request_limit = 65536
        self.start, self.turn = copy.deepcopy(start), copy.deepcopy(turn)
        self.brain_id = brain_id
        self.thread_id = None
        self.start_attempted = self.turn_attempted = False

    def __enter__(self):
        self.proxy.__enter__()
        return self

    def __exit__(self, *args):
        return self.proxy.__exit__(*args)

    def call(self, method, params):
        if method == "project/read":
            require(params == {"projectId": self.start["projectId"]}, "Exact public project only")
            return self.proxy._rpc(method, params)
        require(method in ("thread/read", "thread/backgroundTerminals/list") and isinstance(params, dict) and
                params.get("threadId") in {self.brain_id, self.thread_id} - {None}, "Exact brain or created task only")
        return self.proxy.call(method, params)

    def _rpc(self, method, params):
        # Fixed policy/authentication reads, never a generic write API.
        if method == "account/read":
            require(params == {"refreshToken": False}, "Non-refreshing public authentication read only")
            return self.proxy._rpc(method, params)
        require(method == "thread/effectivePolicy/read" and set(params) == {"threadId"} and
                params["threadId"] in {self.brain_id, self.thread_id} - {None}, "Exact public policy reads only")
        return self.proxy._rpc(method, params)

    def public_environment(self):
        params = {"cursor": None, "limit": 64, "detail": "toolsAndAuthOnly"}
        if self.thread_id:
            params["threadId"] = self.thread_id
        result = self.proxy._rpc("mcpServerStatus/list", params)
        require(isinstance(result, dict) and result.get("data") == [] and result.get("nextCursor", "unknown") is None,
                "Application-owned task runtime must not inherit desktop tools or external MCP servers")

    def create(self):
        require(not self.start_attempted, "Thread creation is one-shot")
        self.start_attempted = True
        result = self.proxy._rpc("thread/start", self.start)
        thread = result.get("thread") if isinstance(result, dict) else None
        require(isinstance(thread, dict), "Native task creation response is missing")
        self.thread_id = _uuid(thread.get("id"))
        require(thread.get("cwd") == self.start["cwd"] and thread.get("projectId") == self.start["projectId"] and
                result.get("model") == self.start["model"] and result.get("reasoningEffort") ==
                self.start["config"]["model_reasoning_effort"], "Native task settings or project differ")
        return self.thread_id, digest(result)

    def begin(self):
        require(self.thread_id and not self.turn_attempted, "First task turn is one-shot")
        self.turn_attempted = True
        self.proxy._awaiting_start = True
        try:
            result = self.proxy._rpc("turn/start", {"threadId": self.thread_id, **self.turn})
        finally:
            self.proxy._awaiting_start = False
        turn = result.get("turn") if isinstance(result, dict) else None
        require(isinstance(turn, dict), "Native task turn response is missing")
        return _uuid(turn.get("id")), digest(result)

    def ended(self, turn_id):
        """Observe this connection only; never reconnect or accept a permission."""
        from .app_server_wake import OWNED_TURN_SECONDS
        self.proxy.deadline = time.monotonic() + OWNED_TURN_SECONDS
        early = getattr(self.proxy, "_early_completion", None)
        if early and early[:2] == (self.thread_id, turn_id):
            return "ended" if early[2] in ("completed", "failed", "interrupted") else "uncertain"
        if callable(getattr(self.proxy, "watch_connection", None)):
            self.proxy.watch_connection()
        rows = list(getattr(self.proxy, "_early_requests", ()))
        for _ in range(100000):
            row = rows.pop(0) if rows else self.proxy._line()
            if not isinstance(row, dict):
                return "uncertain"
            if "id" in row and isinstance(row.get("method"), str):
                return "native_attention_required"  # No worker approval relay qualification yet.
            params = row.get("params")
            if not isinstance(params, dict) or params.get("threadId") != self.thread_id:
                continue
            if row.get("method") == "turn/completed":
                turn = params.get("turn")
                if isinstance(turn, dict) and turn.get("id") == turn_id:
                    return "ended" if turn.get("status") in ("completed", "failed", "interrupted") else "uncertain"
        return "uncertain"


def request(registry, ledger, token, run_id, command_id, task_id, *, read_existing_only=False):
    """Brain request. Never reads a protected binding/socket or starts a runtime."""
    paths = _paths(ledger, command_id, task_id)
    if paths["request"].exists():
        saved = _read_private(paths["request"])
        require(isinstance(saved, dict) and set(saved) == REQUEST_FIELDS and type(saved["version"]) is int and saved["version"] == 1 and
                saved["runId"] == run_id and saved["commandId"] == command_id and saved["taskId"] == task_id and
                saved["controllerHash"] == digest(token), "Public task request changed; no retry")
        with standard.read_db(ledger.db) as db:
            meta = authorize_brain(ledger, db, token)
            run = meta.get("standardRun") or {}
            task = standard.find_task(run, {"taskId": task_id})
            require(run.get("id") == run_id and task["seedHash"] == saved["seedHash"], "Public task ownership changed")
    else:
        require(not read_existing_only, "Wait requires an existing explicit task request; it cannot prepare or send one")
        context = _context(registry, ledger, token, run_id, command_id, task_id)
        with standard.read_db(ledger.db) as db:
            note = ledger.get(db, "commands", command_id).get("notification") or {}
        contract = note.get("nativeTaskContract")
        validate_contract(contract, context["owned"]["policyContract"])
        saved = {"version": 1, "runId": run_id, "commandId": command_id, "taskId": task_id,
                 "seedHash": context["task"]["seedHash"], "bindingHash": context["owned"]["bindingHash"],
                 "contextHash": digest(context), "controllerHash": digest(token), "requestedAt": time.time()}
        _write_once(paths["request"], saved)
    # Return durable status immediately. No approval TTL or waiting loop is added.
    if paths["reply"].exists():
        reply = _read_private(paths["reply"])
        require(isinstance(reply, dict) and set(reply) == {"requestHash", "stage"} and
                reply["requestHash"] == digest(saved) and reply["stage"] in STAGES | {"refused"},
                "Public task reply changed")
        return {"taskId": task_id, "stage": reply["stage"], "retryAllowed": False}
    with standard.read_db(ledger.db) as db:
        meta = authorize_brain(ledger, db, token)
        task = standard.find_task(meta.get("standardRun") or {}, {"taskId": task_id})
        proof = task.get("publicNative")
    if proof:
        require(set(proof) == TASK_FIELDS and proof["bindingHash"] == saved["bindingHash"] and
                proof["seedHash"] == saved["seedHash"] and proof["commandId"] == command_id and
                proof["stage"] in STAGES, "Saved public native progress changed")
        return {"taskId": task_id, "stage": proof["stage"], "retryAllowed": False,
                "observedAt": proof["observedAt"], "terminalCoverage": proof["terminalCoverage"]}
    return {"taskId": task_id, "stage": "requested", "retryAllowed": False,
            "requestedAt": saved["requestedAt"], "detail": "Follow the registered task; do not submit another creation."}


def wait(registry, ledger, token, run_id, command_id, task_id, seconds=30):
    """Bounded private progress wait. No native read, collection, send or renewal."""
    require(type(seconds) is int and 1 <= seconds <= 30, "Public progress wait must be 1–30 seconds")
    deadline = time.monotonic()+seconds
    while True:
        result = request(registry, ledger, token, run_id, command_id, task_id, read_existing_only=True)
        with standard.read_db(ledger.db) as db:
            meta = authorize_brain(ledger, db, token)
            run = meta.get("standardRun") or {}
            require(run.get("id") == run_id, "Wait run changed")
        if (result["stage"] in {"ended", "refused", "pre_turn_blocked", "uncertain", "native_attention_required"} or
                run.get("status") != "running" or time.monotonic() >= deadline):
            return result
        time.sleep(0.1)


def _claim(registry, ledger, token, request, binding, context):
    """Commit the creation claim under the same registry/ledger effect fences."""
    with registry.tx() as registry_db, ledger.tx() as db:
        meta, run, _ = _base_in(registry, ledger, token, registry_db, db, request["runId"])
        require(meta["revision"] == context["revision"] and digest(run) == context["runHash"] and
                not standard.current_blockers(ledger, db, run) and run["status"] == "running",
                "Pause, budget or context changed before native creation")
        task = standard.find_task(run, request)
        _capacity_in(registry_db, ledger, db, run, task)
        require(task == context["task"] and not task["effectIssued"] and task["status"] == "claimed",
                "Native creation already issued; no adapter fallback")
        task.update(status="creating", effectIssued=True, issuedAt=time.time(), publicNative={
            "version": 1, "protocol": PROTOCOL, "bindingHash": digest(binding), "commandId": request["commandId"],
            "seedHash": task["seedHash"], "stage": "creation_claimed", "threadId": None, "turnId": None,
            "responseHash": None, "observedAt": time.time(), "terminalCoverage": "unknown",
            "sourceBase": context["sourceBase"]})
        meta["publicTaskLedgerVersion"] = 1
        run["publicTaskProtocol"] = PROTOCOL
        standard.save(ledger, db, meta, run, "public_task_creation_claim")


def _record(ledger, request, stage, *, thread_id=None, turn_id=None, response_hash=None):
    """Late facts remain retainable after Pause; no ownership or usage release."""
    require(stage in STAGES, "Invalid public native stage")
    with ledger.tx() as db:
        meta = ledger.get(db, "meta", 1)
        run = meta.get("standardRun") or {}
        require(run.get("id") == request["runId"], "Public native run changed; keep private claim for reconciliation")
        task = standard.find_task(run, request)
        proof = task.get("publicNative")
        require(isinstance(proof, dict) and set(proof) == TASK_FIELDS and proof["seedHash"] == request["seedHash"] and
                proof["bindingHash"] == request["bindingHash"] and proof["commandId"] == request["commandId"],
                "Public native claim changed")
        if thread_id:
            _uuid(thread_id)
            require(thread_id != run["brainId"] and proof["threadId"] in (None, thread_id) and
                    not any(t["id"] != task["id"] and t.get("threadId") == thread_id for t in run["tasks"]),
                    "Native worker identity is duplicate or changed")
            proof["threadId"] = task["threadId"] = thread_id
            task.update(hostId="local", status="active", nativeStatus="unknown", trackedTerminals="unknown")
        if turn_id:
            _uuid(turn_id)
            require(proof["turnId"] in (None, turn_id), "Native first-turn identity changed")
            proof["turnId"] = turn_id
        proof.update(stage=stage, responseHash=response_hash or proof["responseHash"], observedAt=time.time())
        # Ended does not imply successful result, idle or empty terminals.
        standard.save(ledger, db, meta, run, "public_task_" + stage)


def _before_turn(registry, ledger, token, saved, binding, scope, proxy):
    """Recheck fences after creation, then claim the first turn before sending."""
    context = owned_context(registry, ledger, token, saved["runId"], saved["commandId"])
    require(context["bindingHash"] == digest(binding), "Native binding changed after task creation")
    from .app_server_wake import load_binding
    current_scope = _scope(registry, ledger.workspace_id, binding)
    require(load_binding(binding_file(ledger, saved["bindingHash"])) == binding and
            {k:v for k,v in current_scope.items() if k != "ledgerRevision"} ==
            {k:v for k,v in scope.items() if k != "ledgerRevision"},
            "Endpoint or catalog changed before the first task turn")
    identity = _brain_identity(proxy, scope, include_flags=True)
    require(identity["nativeStatus"] == "active" and identity["activeFlags"] == [], "Brain native attention is unresolved")
    first = proxy.call("thread/read", {"threadId": proxy.thread_id, "includeTurns": False}).get("thread")
    require(isinstance(first, dict) and first.get("id") == proxy.thread_id and
            first.get("cwd") == scope["cwd"] and first.get("projectId") == scope["projectId"] and
            first.get("status", {}).get("type") == "idle", "Created worker is not exactly loaded-idle")
    terminals = [_terminals(proxy, proxy.thread_id) for _ in range(2)]
    second = proxy.call("thread/read", {"threadId": proxy.thread_id, "includeTurns": False}).get("thread")
    require(first == second and terminals == [[], []], "Created worker activity or tracked terminals are unknown")
    with registry.tx() as registry_db, ledger.tx() as db:
        meta, run, _ = _base_in(registry, ledger, token, registry_db, db, saved["runId"])
        require(run["status"] == "running" and not standard.current_blockers(ledger, db, run),
                "Pause, policy, usage or duration fences the first task turn")
        task = standard.find_task(run, saved)
        _capacity_in(registry_db, ledger, db, run, task)
        proof = task.get("publicNative") or {}
        require(proof.get("stage") == "created" and proof.get("threadId") == proxy.thread_id and
                proof.get("bindingHash") == digest(binding) and proof.get("seedHash") == saved["seedHash"],
                "First public turn already claimed or creation changed")
        repo = ledger.get(db, "repos", task["repository"])
        require(_source_base(repo["path"]) == proof["sourceBase"], "Source base changed before worker turn")
        row = db.execute("SELECT data FROM snapshots WHERE id=? AND kind='standard_seed'", (saved["seedHash"],)).fetchone()
        from .native_read_client import decode
        seed = decode(row[0]) if row else None
        require(seed and digest(seed) == saved["seedHash"] and seed["repository"] == repo and
                all(task.get(k) == v for k,v in seed["task"].items()), "Task inheritance changed before worker turn")
        proof["stage"] = "turn_claimed"
        standard.save(ledger, db, meta, run, "public_task_turn_claim")


def _retain_current_observation(registry, ledger, token, saved, binding, scope, proxy):
    """Observe only the registered ended worker, under its explicit request.

    Reuses the standard report/result gate, never controller release or token
    measurement. A current replacement tracker says nothing about old effects.
    """
    from .standard_native_observation import _sample, KIND, BOUNDARY
    with registry.tx() as registry_db, standard.read_db(ledger.db) as db:
        meta, run, _ = _base_in(registry, ledger, token, registry_db, db, saved["runId"])
        task = standard.find_task(run, saved)
        require((task.get("publicNative") or {}).get("stage") == "ended" and task["threadId"] == proxy.thread_id,
                "Only the exact confirmed ended public task may retain current evidence")
        revision, context_hash = meta["revision"], digest(run)
        target = {"taskId": task["id"], "threadId": task["threadId"], "hostId": task["hostId"],
                  "effectIssued": task["effectIssued"], "repositoryIdentity": task["repositoryIdentity"],
                  "checkout": scope["cwd"], "worktreeRequired": False}
    started = time.time()
    brain = _brain_identity(proxy, scope)
    samples = [_sample(proxy, target) for _ in range(2)]
    require(samples[0] == samples[1] and _brain_identity(proxy, scope) == brain,
            "Current task or brain metadata changed during post-turn observation")
    from .app_server_wake import load_binding
    current_scope = _scope(registry, ledger.workspace_id, binding)
    require(load_binding(binding_file(ledger, saved["bindingHash"])) == binding and
            {k:v for k,v in current_scope.items() if k != "ledgerRevision"} ==
            {k:v for k,v in scope.items() if k != "ledgerRevision"}, "Current host/catalog changed after worker turn")
    report = {"kind": KIND, "workspaceId": ledger.workspace_id, "brainId": scope["brainId"],
              "runId": saved["runId"], "requestId": "public-task-"+digest(saved),
              "contextHash": context_hash, "bindingHash": saved["bindingHash"],
              "startedAt": started, "observedAt": time.time(), "brain": brain, "samples": [samples[1]],
              "issues": [], "readOnlyNativeQueriesAttempted": True, "boundary": copy.deepcopy(BOUNDARY)}
    key = digest(report)
    with registry.tx() as registry_db, ledger.tx() as db:
        meta, run, _ = _base_in(registry, ledger, token, registry_db, db, saved["runId"])
        require(meta["revision"] == revision and digest(run) == context_hash,
                "Pause, task, controller or run changed during post-turn observation")
        task = standard.find_task(run, saved)
        row = samples[1]
        db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, KIND, canonical(report)))
        task.update(nativeStatus=row["nativeStatus"], trackedTerminals=row["trackedTerminals"],
                    observedAt=report["observedAt"], observationSource="public_app_server.registered_task_read",
                    nativeObservationHash=key)
        task["publicNative"]["terminalCoverage"] = "unknown" if row["issues"] else "current_registered_task_only"
        standard.save(ledger, db, meta, run, "public_task_current_observation")


def service_request(ledger, binding, command_id, brain_id, turn_id, task_id):
    """Only the currently owned observer services an explicit brain request."""
    paths = _paths(ledger, command_id, task_id)
    if not paths["request"].exists() or paths["reply"].exists():
        return
    saved = _read_private(paths["request"])
    try:
        _write_once(paths["claim"], {"requestHash": digest(saved)})
    except FileExistsError:
        return  # Even an interrupted preflight does not recollect or resend.
    claimed, created, turn_claimed = False, False, False
    proxy = None
    stage = "refused"
    try:
        require(isinstance(saved, dict) and set(saved) == REQUEST_FIELDS and type(saved["version"]) is int and saved["version"] == 1 and
                saved["commandId"] == command_id and saved["taskId"] == task_id and
                type(saved["requestedAt"]) in (int, float) and 0 <= time.time()-saved["requestedAt"] < REQUEST_SECONDS,
                "Invalid or expired explicit public task request")
        with standard.read_db(ledger.db) as db:
            token = (ledger.get(db, "meta", 1).get("controller") or {}).get("token")
        require(isinstance(token, str) and digest(token) == saved["controllerHash"], "Task controller changed")
        from .workspaces import Registry
        registry = Registry(ledger.platform_root)
        context = _context(registry, ledger, token, saved["runId"], command_id, task_id)
        require(context["owned"]["brainId"] == brain_id and context["owned"]["nativeTurnId"] == turn_id and
                digest(context) == saved["contextHash"] and context["task"]["seedHash"] == saved["seedHash"] and
                digest(binding) == saved["bindingHash"], "Public task owner request changed")
        from .app_server_wake import load_binding
        require(load_binding(binding_file(ledger, saved["bindingHash"])) == binding, "Reviewed public binding changed")
        record = binding["brains"][brain_id]
        validate_contract(record.get("nativeTaskBackend"), record.get("policyEvidence"))
        scope = _scope(registry, ledger.workspace_id, binding)
        start, turn = arguments(context["seed"], record)
        with PublicTaskProxy(binding["endpoint"], start, turn, brain_id) as proxy:
            proxy.public_environment()
            require_authentication(proxy)
            first = _brain_identity(proxy, scope, include_flags=True)
            effective = collect(proxy, binding, brain_id, command_id)
            second = _brain_identity(proxy, scope, include_flags=True)
            require(first == second and second["nativeStatus"] == "active" and second["activeFlags"] == [] and
                    matches(effective["reported"]), "Loaded brain policy/activity is unknown or changed")
            require(_scope(registry, ledger.workspace_id, binding) == scope and
                    _context(registry, ledger, token, saved["runId"], command_id, task_id) == context and
                    load_binding(binding_file(ledger, saved["bindingHash"])) == binding,
                    "Catalog, endpoint, seed or run changed before public creation")
            _claim(registry, ledger, token, saved, binding, context)
            claimed = True
            thread_id, response_hash = proxy.create()
            _record(ledger, saved, "created", thread_id=thread_id, response_hash=response_hash)
            created = True
            proxy.public_environment()
            samples = [proxy._rpc("thread/effectivePolicy/read", {"threadId": thread_id}) for _ in range(2)]
            require(samples[0] == samples[1] and all(matches(reported(s, thread_id, record["cwd"])) and
                    s["policy"]["model"] == context["task"]["model"] for s in samples),
                    "Worker effective policy is unknown or differs from review")
            require_authentication(proxy)
            _before_turn(registry, ledger, token, saved, binding, scope, proxy)
            turn_claimed = True
            worker_turn, response_hash = proxy.begin()
            _record(ledger, saved, "started", turn_id=worker_turn, response_hash=response_hash)
            stage = proxy.ended(worker_turn)
            _record(ledger, saved, stage)
            if stage == "ended":
                try:
                    _retain_current_observation(registry, ledger, token, saved, binding, scope, proxy)
                except (OSError, Refusal, ValueError, KeyError, TypeError):
                    pass  # Ended fact survives; terminal evidence remains unknown, never recollected.
    except (OSError, Refusal, ValueError, KeyError, TypeError):
        stage = "uncertain" if claimed else "refused"
        if created and not turn_claimed:
            stage = "pre_turn_blocked"
        if claimed:
            _record(ledger, saved, stage, thread_id=getattr(proxy, "thread_id", None))
    _write_once(paths["reply"], {"requestHash": digest(saved), "stage": stage})


def service_pending(host, command_id, brain_id, turn_id):
    """Request-triggered work on an existing observer; never an idle scheduler."""
    if host._closed or not host.binding["brains"][brain_id].get("nativeTaskBackend"):
        return
    with standard.read_db(host.ledger.db) as db:
        run = host.ledger.get(db, "meta", 1).get("standardRun") or {}
        candidates = [t["id"] for t in run.get("tasks", [])[:16] if t.get("status") == "claimed"]
    workers = getattr(host, "_public_task_workers", None)
    if workers is None:
        workers = host._public_task_workers = {}
    for task_id in candidates:
        paths = _paths(host.ledger, command_id, task_id)
        key = (command_id, task_id)
        if paths["request"].exists() and not paths["claim"].exists() and key not in workers:
            def execute(selected=task_id):
                try:
                    service_request(host.ledger, host.binding, command_id, brain_id, turn_id, selected)
                except (OSError, Refusal, ValueError):
                    pass  # Interrupted claim remains unknown, no automatic retry.
            worker = threading.Thread(target=execute, daemon=True)
            workers[key] = worker
            worker.start()


def guard_legacy_issue(ledger, db, run):
    notes = [(c.get("notification") or {}) for c in ledger.all(db, "commands")
             if (c.get("notification") or {}).get("hostRunId") == run["id"]]
    if any(n.get("nativeTaskContract") for n in notes):
        raise Refusal("Reviewed public task backend requires standard-public-task; no desktop fallback")
