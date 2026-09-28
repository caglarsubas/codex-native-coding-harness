"""Explicit, one-shot qualification of a standard brain's native project ID.

This operator maintenance action does not bind a dashboard host, notify a brain,
start a turn, or activate Play. A committed private intent precedes the single
native metadata write. After any uncertain result, reconciliation only reads.
"""
import contextlib
import json
from pathlib import Path
import sqlite3
import time

from .admission import sha
from .app_server_wake import UUID, WakeProxy
from .activity import common_directory
from .core import ACTIVE, Ledger, Refusal, canonical, digest, require
from .enrollment import fence_exists
from .native_read_client import ReadProxy, validate_endpoint
from .projects import _read as read_catalog
from .standard import PROTOCOL, TERMINAL
from .workspaces import inspect_ledger, private_path


KIND = "native_project_assignment_v1"
TABLE = "native_project_assignments"
TTL = 300
MAX_PREVIEW = 16_384
UNRESOLVED_NOTIFICATIONS = {"sending", "uncertain"}
UNRESOLVED_MERGES = {"prepared", "issued", "uncertain"}


def _read_database(root):
    db = sqlite3.connect((root / "ledger.sqlite3").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN")
    return contextlib.closing(db)


def _read_registry(registry):
    db = sqlite3.connect(registry.db.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN")
    return contextlib.closing(db)


def _registered(registry, workspace_id):
    with _read_registry(registry) as db:
        row = db.execute("SELECT root,data FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        require(row is not None, "Exact registered workspace required")
        saved, bindings = read_catalog(db)
    root = private_path(row["root"], existing=True)
    inspected = inspect_ledger(root)
    registered = json.loads(row["data"])
    require(registered.get("brainId") == inspected["brainId"] and
            registered.get("databaseIdentity") == inspected["databaseIdentity"],
            "Registered brain or ledger identity changed")
    return root, inspected, saved, bindings


def _row(db, brain_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone():
        return None
    row = db.execute("SELECT data FROM " + TABLE + " WHERE id=?", (brain_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def _safe_state(db, brain_id, root):
    meta_row = db.execute("SELECT data FROM meta WHERE id=1").fetchone()
    require(meta_row is not None, "Workspace ledger metadata is unavailable")
    meta = json.loads(meta_row["data"])
    require(meta.get("brainId") == brain_id and meta.get("paused") is True and
            meta.get("controller") is None and meta.get("runner") is None,
            "Brain identity, dispatch, controller or runner is not settled")
    control = meta.get("brainControl") or {"desired": "running", "phase": "ready"}
    require((control.get("desired"), control.get("phase")) in
            (("running", "ready"), ("stopped", "parked")),
            "Brain stop or resume has not reached a settled boundary")
    require(not meta.get("admissionBinding") and not fence_exists(root),
            "Strict enrollment cannot assign a standard brain project")
    repos = [json.loads(row[0]) for row in db.execute("SELECT data FROM repos")]
    require(repos and all(repo.get("policyProfile") == "standard" for repo in repos),
            "Only registered all-standard projects qualify")
    workers = [json.loads(row[0]) for row in db.execute("SELECT data FROM workers")]
    require(not any(worker.get("status") in ACTIVE for worker in workers),
            "Unsettled legacy or strict worker retains ownership")
    run = meta.get("standardRun")
    if run:
        require(run.get("protocol") == PROTOCOL and run.get("brainId") == brain_id and
                run.get("status") in ("paused", "completed", "blocked") and
                all(task.get("status") in TERMINAL for task in run.get("tasks", [])) and
                not any(merge.get("status") in UNRESOLVED_MERGES for merge in run.get("merges", [])),
                "The standard phase or a registered native effect is unresolved")
        require((run.get("recovery") or {}).get("status") not in ("queued", "processing"),
                "A recovery-only brain turn is pending")
    handoff = meta.get("brainHandoff") or {}
    require(handoff.get("status") not in ("prepared", "candidate", "received"),
            "A brain replacement is unresolved")
    commands = [json.loads(row[0]) for row in db.execute("SELECT data FROM commands")]
    require(not any((command.get("notification") or {}).get("status") in UNRESOLVED_NOTIFICATIONS or
                    ((command.get("notification") or {}).get("status") == "accepted" and
                     command.get("status") in ("queued", "processing"))
                    for command in commands), "An unresolved native notification or brain receipt needs reconciliation")
    require(not any(command.get("kind") in ("standard_play", "standard_pause", "standard_resume") and
                    command.get("status") in ("queued", "processing") for command in commands),
            "A phase control still needs its brain receipt")
    require(not any(command.get("kind") in ("brain_stop", "brain_resume") and
                    command.get("status") in ("queued", "processing") for command in commands),
            "A brain stop or resume control is unresolved")
    return meta


def _scope(registry, workspace_id, binding):
    """Read existing identities only; never initialize a ledger or catalog."""
    require(isinstance(binding, dict) and set(binding) == {"endpoint", "brains"},
            "Exact private app-server binding required")
    validate_endpoint(binding["endpoint"])
    root, inspected, saved, bindings = _registered(registry, workspace_id)
    brain_id = inspected["brainId"]
    record = binding["brains"].get(brain_id)
    require(record and record.get("workspaceId") == workspace_id,
            "Binding does not name this registered brain and workspace")
    project_id, cwd = record.get("projectId"), record.get("cwd")
    require(isinstance(project_id, str) and UUID.fullmatch(project_id) and
            isinstance(brain_id, str) and UUID.fullmatch(brain_id) and
            isinstance(cwd, str) and
            Path(cwd).is_absolute() and str(Path(cwd).resolve(strict=True)) == cwd,
            "Reviewed native project or checkout binding changed")
    linked = [item for item in (saved or {}).get("projects", [])
              if item["projectId"] == project_id and item["projectKind"] == "local" and
              (bindings.get(item["key"]) or {}).get("workspaceId") == workspace_id and
              (bindings.get(item["key"]) or {}).get("brainId") == brain_id and
              (bindings.get(item["key"]) or {}).get("databaseIdentity") == inspected["databaseIdentity"] and
              (bindings.get(item["key"]) or {}).get("locationHash") == item["locationHash"]]
    require(len(linked) == 1 and linked[0]["locationHash"],
            "Native catalog must retain one exact local project mapping")
    require(inspected["databaseIdentity"] and inspected["revision"] >= 0,
            "Registered ledger identity is unavailable")
    return {"root": root, "brainId": brain_id, "projectId": project_id, "cwd": cwd,
            "hostId": linked[0]["hostId"], "ledgerIdentity": inspected["databaseIdentity"],
            "ledgerRevision": inspected["revision"], "endpointHash": digest(binding["endpoint"]),
            "bindingHash": digest(binding), "catalogHash": saved["hash"],
            "locationHash": linked[0]["locationHash"]}


def _native_identity(proxy, scope, *, require_idle=True, allow_conflict=False):
    project_result = proxy._rpc("project/read", {"projectId": scope["projectId"]})
    project = project_result.get("project") if isinstance(project_result, dict) else None
    require(isinstance(project, dict) and project.get("id") == scope["projectId"] and
            isinstance(project.get("roots"), list) and len(project["roots"]) == 1,
            "One exact native project root is required for this qualification")
    # The retained catalog's location is a hash of the complete list_projects
    # path. project/read must independently return that exact root; a checkout
    # sibling is accepted only when Git proves the same common repository.
    linked = []
    try:
        checkout_common = common_directory(scope["cwd"])
    except (OSError, ValueError, UnicodeError) as error:
        raise Refusal("Bound brain checkout has no verified Git common directory") from error
    for item in project["roots"]:
        path = item.get("path") if isinstance(item, dict) else None
        if isinstance(path, str) and len(path) <= 4096:
            try:
                if Path(path).is_absolute() and str(Path(path).resolve(strict=True)) == path and \
                        digest([scope["hostId"], path]) == scope["locationHash"] and \
                        common_directory(path) == checkout_common:
                    linked.append(path)
            except (OSError, ValueError, UnicodeError):
                continue
    require(len(linked) == 1, "Native project root does not identify the bound checkout repository")
    thread_result = proxy._rpc("thread/read", {"threadId": scope["brainId"], "includeTurns": False})
    thread = thread_result.get("thread") if isinstance(thread_result, dict) else None
    require(isinstance(thread, dict) and thread.get("id") == scope["brainId"] and
            thread.get("cwd") == scope["cwd"] and
            (allow_conflict or thread.get("projectId") in (None, scope["projectId"])),
            "Native brain task, checkout or current project differs from review")
    require(thread.get("projectId") is None or isinstance(thread.get("projectId"), str) and
            len(thread["projectId"]) <= 200,
            "Native project identity is malformed")
    status = thread.get("status")
    require(isinstance(status, dict) and status.get("type") in
            (("idle", "notLoaded") if require_idle else ("active", "idle", "notLoaded")),
            "Native brain activity is not safe for this project operation")
    return thread, sorted(linked)


def _observed(registry, workspace_id, binding):
    scope = _scope(registry, workspace_id, binding)
    with _read_database(scope["root"]) as db:
        meta = _safe_state(db, scope["brainId"], scope["root"])
        previous = _row(db, scope["brainId"])
        require(meta["revision"] == scope["ledgerRevision"], "Ledger changed during project inspection")
    with ReadProxy(binding["endpoint"]) as proxy:
        thread, roots = _native_identity(proxy, scope)
    return scope, previous, thread, roots


def preview(registry, workspace_id, binding):
    """Read-only exact review; a prior intent can never authorize another send."""
    scope, previous, thread, roots = _observed(registry, workspace_id, binding)
    require(previous is None, "A project assignment intent already exists; inspect or reconcile it")
    require(thread["projectId"] is None,
            "Native brain already has the reviewed project; no metadata write is necessary")
    now = time.time()
    doc = {"kind": KIND, "workspaceId": workspace_id,
           "brainId": scope["brainId"], "projectId": scope["projectId"],
           "checkout": scope["cwd"], "projectRoots": roots,
           "ledgerIdentity": scope["ledgerIdentity"], "ledgerRevision": scope["ledgerRevision"],
           "catalogHash": scope["catalogHash"],
           "projectLocationHash": scope["locationHash"],
           "endpointHash": scope["endpointHash"], "bindingHash": scope["bindingHash"],
           "nativeBeforeProjectId": None, "nativeStatus": thread["status"]["type"],
           "createdAt": now, "expiresAt": now + TTL,
           "effect": "One native thread/metadata/update project assignment; no turn, Play or host activation"}
    require(len(canonical(doc).encode("utf-8")) <= MAX_PREVIEW, "Project review exceeds its bound")
    return {"preview": doc, "previewHash": digest(doc)}


def status(registry, workspace_id):
    root, inspected, _, _ = _registered(registry, workspace_id)
    brain_id = inspected["brainId"]
    with _read_database(root) as db:
        return _row(db, brain_id) or {"status": "not_started", "brainId": brain_id,
                                      "nativeAttempted": False, "nativeOutcome": "not_observed"}


def _update_row(ledger, brain_id, state, after, observed_project_id=None):
    with ledger.tx() as db:
        current = _row(db, brain_id)
        require(current and current["previewHash"] == state["previewHash"],
                "Project assignment intent changed; native result is uncertain")
        observed_at = time.time()
        if after == "verified" and not current.get("verifiedAt"):
            current["verifiedAt"] = observed_at
        current.update(status=after, observedAt=observed_at,
                       observedProjectId=observed_project_id,
                       nativeOutcome="project_id_observed" if after == "verified"
                       else "attempted_unconfirmed" if current.get("nativeAttempted")
                       else "claim_unresolved")
        ledger.put(db, TABLE, brain_id, current)
        ledger.event(db, "native_project_assignment_" + after, {"brainId": brain_id})
        return current


def _catalog_still_bound(db, workspace_id, scope, doc):
    row = db.execute("SELECT root,data FROM workspaces WHERE id=? AND brain=?",
                     (workspace_id, scope["brainId"])).fetchone()
    registered = json.loads(row["data"]) if row else {}
    require(row and row["root"] == str(scope["root"]) and
            registered.get("databaseIdentity") == scope["ledgerIdentity"],
            "Registered brain or ledger identity changed during confirmation")
    saved, bindings = read_catalog(db)
    key = digest([scope["hostId"], scope["projectId"]])
    require(saved and saved["hash"] == doc["catalogHash"] and
            any(item["key"] == key and item["locationHash"] == doc["projectLocationHash"]
                for item in saved["projects"]) and
            (bindings.get(key) or {}).get("workspaceId") == workspace_id and
            (bindings.get(key) or {}).get("brainId") == scope["brainId"] and
            (bindings.get(key) or {}).get("databaseIdentity") == scope["ledgerIdentity"] and
            (bindings.get(key) or {}).get("locationHash") == doc["projectLocationHash"],
            "Native catalog mapping changed after review")


def confirm(registry, workspace_id, binding, proposal, confirmation_hash):
    """Claim exactly once before write; never retry an existing intent."""
    require(isinstance(proposal, dict) and set(proposal) == {"preview", "previewHash"},
            "Exact saved project preview required")
    doc = proposal["preview"]
    sha(confirmation_hash)
    require(isinstance(doc, dict) and len(canonical(doc).encode("utf-8")) <= MAX_PREVIEW and
            proposal["previewHash"] == digest(doc) == confirmation_hash and
            doc.get("kind") == KIND and doc.get("workspaceId") == workspace_id and
            type(doc.get("createdAt")) in (int, float) and
            0 <= time.time() - doc["createdAt"] <= TTL and
            doc.get("expiresAt") == doc["createdAt"] + TTL and time.time() <= doc["expiresAt"],
            "Preview was changed, expired or not explicitly confirmed")
    current = preview(registry, workspace_id, binding)["preview"]
    # Native status may move between idle and notLoaded without authorizing a
    # different target. Everything else, including the revision, is exact.
    for key in ("workspaceId", "brainId", "projectId", "checkout", "projectRoots",
                "ledgerIdentity", "ledgerRevision", "catalogHash", "projectLocationHash",
                "endpointHash", "bindingHash", "nativeBeforeProjectId"):
        require(doc.get(key) == current[key], "Native project or ledger changed; inspect a fresh preview")
    scope = _scope(registry, workspace_id, binding)
    # Confirm is maintenance, and the only operation that creates this table.
    # The registry lock precedes the ledger lock, as in standard coordination.
    ledger = registry.ledger(workspace_id)
    with registry.tx() as registry_db, ledger.tx() as db:
        _catalog_still_bound(registry_db, workspace_id, scope, doc)
        meta = _safe_state(db, scope["brainId"], scope["root"])
        require(meta["revision"] == doc["ledgerRevision"], "Ledger changed after project review")
        db.execute("CREATE TABLE IF NOT EXISTS " + TABLE + "(id TEXT PRIMARY KEY, data TEXT NOT NULL)")
        require(_row(db, scope["brainId"]) is None,
                "Native project assignment was already claimed; reconcile, never resend")
        attempt = {"kind": KIND, "workspaceId": workspace_id, "brainId": scope["brainId"],
                   "projectId": scope["projectId"], "checkout": scope["cwd"],
                   "ledgerIdentity": scope["ledgerIdentity"], "endpointHash": scope["endpointHash"],
                   "bindingHash": scope["bindingHash"], "previewHash": confirmation_hash,
                   "claimedAt": time.time(), "status": "intent_committed", "nativeAttempted": False,
                   "nativeBeforeProjectId": None, "nativeOutcome": "not_observed"}
        ledger.put(db, TABLE, scope["brainId"], attempt)
        ledger.event(db, "native_project_assignment_claimed", {"brainId": scope["brainId"]})
        attempt["intentRevision"] = ledger.get(db, "meta", 1)["revision"]
        ledger.put(db, TABLE, scope["brainId"], attempt)
    # A crash at any point after the claim leaves a durable, non-retryable
    # intent. Even a pre-send error requires explicit read-only reconciliation.
    try:
        with WakeProxy(binding["endpoint"]) as proxy:
            thread, roots = _native_identity(proxy, scope)
            require(thread["projectId"] is None and roots == doc["projectRoots"],
                    "Native project changed after assignment claim")
            rpc_error = None
            # Keep the local owner/state locks through the bounded RPC response.
            # The host has no shared transaction with SQLite; if its response is
            # lost, the committed intent still forbids a second native send.
            with registry.tx() as registry_db, ledger.tx() as db:
                _catalog_still_bound(registry_db, workspace_id, scope, doc)
                meta = _safe_state(db, scope["brainId"], scope["root"])
                current = _row(db, scope["brainId"])
                require(meta["revision"] == attempt["intentRevision"] and
                        current and current["previewHash"] == confirmation_hash and
                        current["status"] == "intent_committed" and not current["nativeAttempted"],
                        "Local phase or project assignment changed before native write")
                current.update(nativeAttempted=True, attemptedAt=time.time(), status="uncertain",
                               nativeOutcome="attempted_unconfirmed")
                ledger.put(db, TABLE, scope["brainId"], current)
                try:
                    # Installed app-server v2 schema: exactly threadId + existing projectId.
                    proxy._rpc("thread/metadata/update", {"threadId": scope["brainId"],
                                                           "projectId": scope["projectId"]})
                except BaseException as error:
                    rpc_error = error
            if rpc_error is not None:
                raise rpc_error
            after, _ = _native_identity(proxy, scope, require_idle=False)
            require(after["projectId"] == scope["projectId"],
                    "Native update returned without a verified project assignment")
        return _update_row(ledger, scope["brainId"], attempt, "verified", scope["projectId"])
    except (OSError, Refusal, ValueError, KeyError, RuntimeError, sqlite3.Error):
        return _update_row(ledger, scope["brainId"], attempt, "uncertain")


def reconcile(registry, workspace_id, binding):
    """Read-only native observation; update only the local receipt, never resend."""
    scope = _scope(registry, workspace_id, binding)
    prior = status(registry, workspace_id)
    require(prior.get("kind") == KIND and prior.get("brainId") == scope["brainId"] and
            prior.get("projectId") == scope["projectId"] and
            prior.get("endpointHash") == scope["endpointHash"] and
            prior.get("bindingHash") == scope["bindingHash"],
            "Exact prior assignment intent and host binding required")
    with ReadProxy(binding["endpoint"]) as proxy:
        thread, _ = _native_identity(proxy, scope, require_idle=False, allow_conflict=True)
    outcome = ("verified" if thread["projectId"] == scope["projectId"] else
               "uncertain" if thread["projectId"] is None else "conflict")
    ledger = registry.ledger(workspace_id)
    return _update_row(ledger, scope["brainId"], prior, outcome, thread["projectId"])
