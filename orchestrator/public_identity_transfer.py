"""Explicit one-brain public-protocol identity transfer, not run continuation.

The native project restore is an operator-reviewed-build extension; stock
project/import is never a fallback. Only one flat root rollout is copied. No
native database/auth/plugin store is copied or edited. Original ledgers/bindings
remain read-only and historical/current source terminal safety stays unknown.
"""
import copy
import hashlib
import os
from pathlib import Path
import time

from . import standard
from .app_server_wake import load_binding
from .core import ACTIVE, Refusal, canonical, digest, require
from .host_runtime import safe_path as inspect_path
from .native_policy_evidence import matches, reported
from .native_project_assignment import _scope
from .native_read_client import ReadProxy, decode, file_identity
from .public_host_lifecycle import CONFIG, sync_directory, write_record

KIND = "public_identity_transfer_v1"
MAX_ROLLOUT = 16_000_000
ENDED = {"completed", "interrupted", "failed"}
IDENTITY_FIELDS = ("workspaceId", "cwd", "projectId", "catalogProjectId", "nativePolicy")
SPEC_FIELDS = {"version", "kind", "sourceBindingPath", "destinationBindingPath", "sourceBindingHash", "destinationBindingHash",
               "context", "brainId", "cwd", "catalogProjectId", "snapshot", "archivePath", "archivePin", "destinationHome", "fencePath"}


def validate_contract(value, backend):
    require(isinstance(value, dict) and set(value) == {"protocol", "sourceCommit", "sourceTree"} and
            value["protocol"] == KIND and isinstance(backend, dict) and
            all(value.get(key) == backend.get(key) for key in ("sourceCommit", "sourceTree")),
            "Separately reviewed exact identity-transfer native build contract required")
    for key in ("sourceCommit", "sourceTree"):
        require(isinstance(value[key], str) and len(value[key]) == 40 and all(c in "0123456789abcdef" for c in value[key]),
                "Exact native source commit/tree required")
    return value


def safe_path(value, *, directory=False, private=True):
    path = Path(value)
    info = inspect_path(path, directory=directory)
    require(info.st_uid == os.getuid() and (not private or not info.st_mode & 0o077), "Owner-private transfer path required")
    return path


def read_archive(value):
    path = safe_path(value)
    before = path.stat()
    require(before.st_nlink == 1 and 0 < before.st_size <= MAX_ROLLOUT, "Bounded unaliased archive required")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        require(file_identity(os.fstat(stream.fileno())) == file_identity(before), "Archive changed")
        raw = stream.read(MAX_ROLLOUT + 1)
        require(file_identity(os.fstat(stream.fileno())) == file_identity(before) == file_identity(path.stat()), "Archive changed")
    require(len(raw) <= MAX_ROLLOUT, "Archive bound exceeded")
    return raw


def archive_pin(value):
    path = safe_path(value)
    raw = read_archive(path)
    return {"identity": list(file_identity(path.stat())), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def fence_path(ledger, saved):
    # Same original run/Play, regardless of a different review directory,
    # changed usage snapshot or replacement endpoint. A new preview cannot
    # turn an uncertain attempted transfer into another native send.
    root = safe_path(ledger.root, directory=True)
    key = digest({"runId": saved["runId"], "originalPlayId": saved["originalPlayId"]})
    return root / ("public-identity-transfer-" + key + ".json")


class TransferProxy(ReadProxy):
    """Only this separately reviewed operator path may use these fixed writes."""
    request_limit = 32000
    total_limit = 32_000_000

    def _rpc(self, method, params):
        require(method in {"initialize", "project/read", "project/list", "thread/read", "thread/list",
                "mcpServerStatus/list", "project/restoreMetadata", "thread/resume", "thread/metadata/update",
                "thread/effectivePolicy/read", "thread/backgroundTerminals/list"}, "Transfer method not allowed")
        result = super()._rpc(method, params)
        if method == "initialize": self.initialization = copy.deepcopy(result)
        return result


def context(ledger, source):
    from .enrollment import fence_exists
    require(not fence_exists(ledger.root), "Strict enrollment refuses transfer")
    with standard.read_db(ledger.db) as db:
        meta = ledger.get(db, "meta", 1)
        control = meta.get("brainControl") or {"desired": "running", "phase": "ready"}
        require((control.get("desired"), control.get("phase")) == ("running", "ready"), "Brain Stop retains its fence")
        run = meta.get("standardRun")
        commands = ledger.all(db, "commands")
        repos, workers, queue = [ledger.all(db, table) for table in ("repos", "workers", "queue")]
        require(meta.get("schemaVersion") == 4 and meta.get("paused") is True and
                not meta.get("controller") and not meta.get("runner") and not meta.get("admissionBinding") and
                run and run["protocol"] == standard.PROTOCOL and run["status"] == "paused" and
                run["brainId"] == meta["brainId"] and not run["tasks"] and
                not any(m["status"] in {"prepared", "issued", "uncertain"} for m in run.get("merges", [])),
                "Exact empty unowned paused standard run required")
        require(repos and all(r["policyProfile"] == "standard" for r in repos) and
                not any(w["status"] in ACTIVE for w in workers) and
                not any(q["status"] == "approved" for q in queue) and
                not any(c["status"] in {"queued", "processing"} or
                        (c.get("notification") or {}).get("status") in {"sending", "uncertain"}
                        for c in commands), "Pending ownership refuses transfer")
        play = [c for c in commands if c["kind"] == "standard_play" and c.get("payload", {}).get("runId") == run["id"]]
        require(len(play) == 1 and play[0]["status"] == "completed" and
                (play[0].get("notification") or {}).get("hostBindingHash") == digest(source) and
                isinstance((play[0].get("notification") or {}).get("nativeTurnId"), str),
                "Immutable original receipted Play and source binding required")
        note = play[0]["notification"]
        observation = note.get("nativeThreadObservation") or {}
        require(note.get("status") == "accepted" and note.get("brainId") == meta["brainId"] and
                note.get("hostRunId") == run["id"] and note.get("nativeTurnStatus") in ENDED and
                observation.get("streamStatus") == "closed" and observation.get("rootThreadId") == meta["brainId"] and
                observation.get("nativeTurnId") == note["nativeTurnId"],
                "Exact closed original owned-turn observation required; unknown delivery cannot transfer")
        return {"runId": run["id"], "runHash": digest(run), "originalPlayId": play[0]["id"], "originalPlayHash": digest(play[0]),
                "originalTurnId": play[0]["notification"]["nativeTurnId"],
                "originalTurnStatus": note["nativeTurnStatus"],
                "contextHash": digest({"meta": meta, "commands": commands, "repos": repos, "workers": workers, "queue": queue})}


def bindings(registry, ledger, source_path, destination_path):
    from .enrollment import record_in
    from .native_project_assignment import _read_registry
    with _read_registry(registry) as db:
        require(record_in(db) is None, "Platform enrollment refuses transfer")
    source, destination = load_binding(source_path), load_binding(destination_path)
    first = _scope(registry, ledger.workspace_id, source)
    brain = first["brainId"]
    require(len(source["brains"]) == len(destination["brains"]) == 1 and brain in destination["brains"] and
            all(source["brains"][brain].get(k) == destination["brains"][brain].get(k) for k in IDENTITY_FIELDS),
            "Brain, checkout, workspace, both project IDs or restricted policy changed")
    last = _scope(registry, ledger.workspace_id, destination)
    policy = source["brains"][brain]["nativePolicy"]
    require(policy.get("approvalsReviewer", "user") == "user" and
            {k: v for k, v in policy.items() if k != "approvalsReviewer"} ==
            {"approvalPolicy": "on-request", "sandbox": "workspace-write", "codeMode": False},
            "Exact restricted native policy required")
    # Public tasks and metadata restoration are independently named capabilities.
    # The old accepted Play receives neither by backfill.
    from .public_native_tasks import validate_contract as task_contract
    task_contract(destination["brains"][brain].get("nativeTaskBackend"), destination["brains"][brain].get("policyEvidence"))
    validate_contract(destination["brains"][brain].get("identityTransferEvidence"), destination["brains"][brain].get("nativeTaskBackend"))
    require(source["endpoint"] != destination["endpoint"], "Distinct separately reviewed empty destination required")
    return source, destination, first, last


def rollout(path, home, brain, cwd):
    # Native JSONL is sometimes 0644 beneath an owner-private home. Do not
    # chmod the original: that ancestor remains mandatory and write aliases
    # stay forbidden. Retained/exported archives themselves must be private.
    path = safe_path(path, private=False)
    home = safe_path(home, directory=True)
    require(path.is_relative_to(home / "sessions") and path.suffix == ".jsonl", "One native sessions rollout required")
    before = path.stat()
    require(before.st_nlink == 1 and before.st_uid == os.getuid() and not before.st_mode & 0o022 and
            0 < before.st_size <= MAX_ROLLOUT, "Private bounded unaliased rollout required")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        require(file_identity(os.fstat(stream.fileno())) == file_identity(before), "Rollout changed")
        data = stream.read(MAX_ROLLOUT + 1)
        require(file_identity(os.fstat(stream.fileno())) == file_identity(before) == file_identity(path.stat()), "Rollout changed")
    validate_rollout_data(data, brain, cwd)
    pin = {"path": str(path), "identity": list(file_identity(before)), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return data, pin


def validate_rollout_data(data, brain, cwd):
    """Unchanged history-format gates, shared by private and exact shared export."""
    require(len(data) <= MAX_ROLLOUT and data.endswith(b"\n"), "Incomplete rollout snapshot")
    lines = data.splitlines()
    require(len(lines) <= 100000 and all(0 < len(line) <= 1_000_000 for line in lines), "Rollout record bound exceeded")
    rows = [decode(line) for line in lines]
    require(rows and all(isinstance(row, dict) for row in rows), "Native history records must be objects")
    require(rows[0].get("type") == "session_meta", "Native session metadata required")
    meta = rows[0].get("payload") or {}
    require(isinstance(meta, dict), "Native session metadata must be an object")
    require(meta.get("id") == brain and meta.get("session_id", brain) == brain and meta.get("cwd") == cwd and
            meta.get("history_mode", "legacy") in {"legacy", "paginated"} and
            all(not meta.get(k) for k in ("parent_thread_id", "forked_from_id", "history_base", "dynamic_tools", "selected_capability_roots")) and
            all(r.get("type") != "session_meta" for r in rows[1:]), "Only one exact flat independent root history is supported")
    if meta.get("history_mode") == "paginated":
        require(all(type(r.get("ordinal")) is int and r["ordinal"] == index for index, r in enumerate(rows)),
                "Paginated root export requires a complete contiguous zero-based native ordinal stream")
    require(all("goal" not in str((r.get("payload") or {}).get("type", "")).lower() for r in rows if isinstance(r.get("payload"), dict)),
            "Goal-bearing history needs a separately qualified path")
    settings = [r["payload"].get("thread_settings") or {} for r in rows if isinstance(r.get("payload"), dict) and
                r["payload"].get("type") == "thread_settings_applied"]
    require(all(isinstance(item, dict) for item in settings), "Native settings records must be objects")
    require(all(not item.get(k) for item in [meta, *settings] for k in
                ("selected_capability_roots", "dynamic_tools", "plugins", "plugin_refs", "environment")),
            "Persisted capabilities need a separately qualified transfer path")
    require(all(item.get("runtime_workspace_roots") in (None, [], [cwd]) for item in [meta, *settings]),
            "Additional historical workspace roots refuse transfer")


def source_projection(proxy, scope):
    project = proxy._rpc("project/read", {"projectId": scope["projectId"]})["project"]
    thread = proxy._rpc("thread/read", {"threadId": scope["brainId"], "includeTurns": True})["thread"]
    require(project["id"] == scope["projectId"] and project["roots"] == [{"path": scope["cwd"]}] and
            thread["id"] == scope["brainId"] and thread.get("sessionId", scope["brainId"]) == scope["brainId"] and
            thread["projectId"] == scope["projectId"] and thread["cwd"] == scope["cwd"] and
            thread["status"]["type"] in {"notLoaded", "idle"} and not thread.get("archived") and
            not thread["status"].get("activeFlags") and not thread.get("forkedFromId"), "Source identity/activity changed")
    require(len(canonical(project).encode()) <= 24000, "Exact project metadata exceeds the fixed restore request bound")
    turns = thread.get("turns") or []
    require(turns and turns[-1].get("status") in ENDED and isinstance(turns[-1].get("id"), str), "Exact latest ended turn required")
    return project, thread


def snapshot_record(project, thread, home, pin):
    turns = thread["turns"]
    return {"project": project, "threadHash": digest(thread), "turnsHash": digest(turns), "rollout": pin, "sourceHome": home,
            "latestTurnId": turns[-1]["id"], "latestTurnStatus": turns[-1]["status"]}


def source_snapshot(proxy, scope):
    project, thread = source_projection(proxy, scope)
    home = proxy.initialization["codexHome"]
    data, pin = rollout(thread["path"], home, scope["brainId"], scope["cwd"])
    return snapshot_record(project, thread, home, pin), data


def prepared_source(proxy, scope, export, source_path, source, saved):
    if export is None:
        return source_snapshot(proxy, scope)
    from .public_brain_export import for_transfer
    return for_transfer(proxy, scope, export, source_path, digest(source), saved)


def empty_destination(proxy, source_home):
    home = safe_path(proxy.initialization["codexHome"], directory=True)
    require(home != Path(source_home) and home != Path.home() / ".codex", "Isolated destination home required")
    for path in ("auth.json", ".credentials.json", "plugins", "hooks", "managed-config.toml"):
        require(not (home / path).exists(), "Credential/plugin/config inheritance refuses transfer")
    require(read_archive(home / "config.toml") == CONFIG.encode(), "Restricted public-host configuration changed")
    projects = proxy._rpc("project/list", {"limit": 100})
    require(projects == {"data": [], "nextCursor": None}, "Empty destination project catalog required")
    for archived in (False, True):
        threads = proxy._rpc("thread/list", {"limit": 100, "archived": archived,
            "sourceKinds": ["cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview", "subAgentCompact", "subAgentThreadSpawn", "subAgentOther", "unknown"]})
        require(threads.get("data") == [] and threads.get("nextCursor") is None, "Empty destination thread store required")
    mcp = proxy._rpc("mcpServerStatus/list", {"detail": "toolsAndAuthOnly"})
    require(mcp == {"data": [], "nextCursor": None}, "No complete empty MCP inventory")
    return str(home)


def prepare(registry, ledger, source_path, destination_path, directory, *, source_export=None):
    source, destination, scope, _ = bindings(registry, ledger, source_path, destination_path)
    saved = context(ledger, source)
    fence = fence_path(ledger, saved)
    require(not fence.exists(), "Original run/Play already consumed an identity transfer; no new preview or endpoint retry")
    export = None
    if source_export is not None:
        from .public_brain_export import descriptor
        export = descriptor(source_export)
    with TransferProxy(source["endpoint"]) as proxy:
        first, data = prepared_source(proxy, scope, export, source_path, source, saved)
        second, _ = prepared_source(proxy, scope, export, source_path, source, saved)
        require(first == second and first["latestTurnId"] == saved["originalTurnId"] and
                first["latestTurnStatus"] == saved["originalTurnStatus"], "Source original-turn view changed during snapshot")
    with TransferProxy(destination["endpoint"]) as proxy:
        home = empty_destination(proxy, first["sourceHome"])
    require(context(ledger, source) == saved and bindings(registry, ledger, source_path, destination_path)[:2] == (source, destination),
            "Run or bindings changed during preparation")
    directory = Path(directory)
    require(directory.is_absolute() and str(directory.parent.resolve(strict=True) / directory.name) == str(directory), "Canonical new private transfer directory required")
    safe_path(directory.parent, directory=True)
    require(not directory.is_relative_to(Path(scope["cwd"])) and not Path(scope["cwd"]).is_relative_to(directory) and
            all(not directory.is_relative_to(Path(native_home)) and not Path(native_home).is_relative_to(directory)
                for native_home in (first["sourceHome"], home)), "Protected transfer archive must be disjoint from checkout and native homes")
    directory.mkdir(mode=0o700)  # Partial preparation is retained, never overwritten.
    sync_directory(directory.parent)
    archive = directory / "history.jsonl"
    with os.fdopen(os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    os.chmod(archive, 0o400)
    spec = {"version": 2 if export else 1, "kind": KIND, "sourceBindingPath": str(source_path), "destinationBindingPath": str(destination_path),
            "sourceBindingHash": digest(source), "destinationBindingHash": digest(destination), "context": saved,
            "brainId": scope["brainId"], "cwd": scope["cwd"], "catalogProjectId": scope["catalogProjectId"],
            "snapshot": first, "archivePath": str(archive), "archivePin": archive_pin(archive), "destinationHome": home, "fencePath": str(fence)}
    if export:
        spec["sourceExport"] = export
    write_record(directory / "transfer.json", spec)
    return preview(spec)


def preview(spec):
    require(isinstance(spec, dict) and type(spec.get("version")) is int and
            ((spec["version"] == 1 and set(spec) == SPEC_FIELDS) or
             (spec["version"] == 2 and set(spec) == SPEC_FIELDS | {"sourceExport"})) and
            spec.get("kind") == KIND, "Closed identity transfer specification required")
    if spec["version"] == 2:
        from .public_brain_export import validate_descriptor
        validate_descriptor(spec["sourceExport"])
    return {"kind": KIND, "reviewHash": digest({"kind": KIND, "spec": spec}), "validity": "until_scope_changes",
            "brainId": spec["brainId"], "projectId": spec["snapshot"]["project"]["id"], "catalogProjectId": spec["catalogProjectId"],
            "historySha256": spec["snapshot"]["rollout"]["sha256"], "historyBytes": spec["snapshot"]["rollout"]["bytes"],
            "nativeWrites": ["project/restoreMetadata", "thread/resume (inspection load only)", "thread/metadata/update"],
            "boundary": {"turnStarted": False, "bindingInstalled": False, "runChanged": False, "migrationQualified": False,
                         "resumeAuthorized": False, "terminalSafety": "unknown", "pilotAccepted": False}}


def load_spec(path):
    raw = read_archive(path)
    require(len(raw) <= 65536, "Transfer specification exceeds bound")
    spec = decode(raw)
    preview(spec)  # Closed non-executing schema, not confirmation or native proof.
    return spec


def apply(registry, ledger, spec, confirm_hash):
    require(confirm_hash == preview(spec)["reviewHash"], "Exact identity-transfer owner hash required")
    require(spec.get("version") in (1, 2) and spec.get("kind") == KIND, "Exact transfer contract required")
    directory = safe_path(str(Path(spec["archivePath"]).parent), directory=True)
    attempt = directory / "attempt"
    fence = fence_path(ledger, spec["context"])
    require(str(fence) == spec["fencePath"] and not fence.exists() and not attempt.exists(),
            "Original run/Play transfer intent already consumed; read evidence, never resend")
    source, destination, scope, _ = bindings(registry, ledger, spec["sourceBindingPath"], spec["destinationBindingPath"])
    hold = None
    def fresh():
        require(digest(source) == spec["sourceBindingHash"] and digest(destination) == spec["destinationBindingHash"] and
                context(ledger, source) == spec["context"] and
                bindings(registry, ledger, spec["sourceBindingPath"], spec["destinationBindingPath"])[:2] == (source, destination),
                "Reviewed run or binding scope changed")
        require(hold is None or decode(read_archive(fence)) == hold, "Permanent original-Play transfer fence changed")
        require(read_archive(Path(spec["destinationHome"]) / "config.toml") == CONFIG.encode(), "Destination restricted configuration changed")
        with TransferProxy(source["endpoint"]) as proxy:
            for _ in range(2):
                snapshot, _ = prepared_source(proxy, scope, spec.get("sourceExport"), spec["sourceBindingPath"], source, spec["context"])
                require(snapshot == spec["snapshot"], "Original native snapshot changed")
        raw = read_archive(spec["archivePath"])
        require(archive_pin(spec["archivePath"]) == spec["archivePin"] and
                len(raw) == spec["snapshot"]["rollout"]["bytes"] and hashlib.sha256(raw).hexdigest() ==
                spec["snapshot"]["rollout"]["sha256"], "Retained history changed")
        return raw
    raw = fresh()
    with TransferProxy(destination["endpoint"]) as proxy:
        require(empty_destination(proxy, spec["snapshot"]["sourceHome"]) == spec["destinationHome"], "Destination home changed")
        try: attempt.mkdir(mode=0o700)
        except FileExistsError: raise Refusal("Transfer intent already consumed; read evidence, never resend") from None
        sync_directory(directory)
        write_record(attempt / "intent.json", {"specHash": digest(spec), "reviewHash": confirm_hash, "createdAt": time.time()})
        hold = {"kind": KIND, "specHash": digest(spec), "reviewHash": confirm_hash,
                "runId": spec["context"]["runId"], "originalPlayId": spec["context"]["originalPlayId"],
                "originalPlayHash": spec["context"]["originalPlayHash"], "attemptDirectory": str(attempt)}
        fd = os.open(fence, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(canonical(hold))
            stream.flush(); os.fsync(stream.fileno())
        sync_directory(fence.parent)  # Interrupted persistence still consumes the canonical fence.
        def claim(name):
            fresh()
            with os.fdopen(os.open(attempt / (name + ".claim"), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "w") as stream:
                stream.flush(); os.fsync(stream.fileno())
            sync_directory(attempt)
            fresh()
        claim("project_restore")
        restored = proxy._rpc("project/restoreMetadata", {"version": 1, "project": spec["snapshot"]["project"]})
        expected = dict(spec["snapshot"]["project"], recencyAt=None)
        require(restored == {"version": 1, "project": expected}, "Native exact project restore mismatch")
        copy_dir = Path(spec["destinationHome"]) / "sessions" / ("transfer-" + spec["brainId"])
        # These are exact claimed artifacts, not an arbitrary native database copy.
        copy_dir.parent.mkdir(mode=0o700, exist_ok=True)
        safe_path(str(copy_dir.parent), directory=True)
        copy_dir.mkdir(mode=0o700)
        target = copy_dir / Path(spec["snapshot"]["rollout"]["path"]).name
        pending = copy_dir / "history.pending"
        with os.fdopen(os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        # Publish a complete JSONL atomically without overwriting an existing
        # target. Native scanners never see the half-written history prefix.
        os.link(pending, target, follow_symlinks=False)
        pending.unlink()
        sync_directory(copy_dir)
        claim("inspection_load")
        loaded = proxy._rpc("thread/resume", {"threadId": spec["brainId"], "path": str(target), "cwd": spec["cwd"],
            "excludeTurns": True, "approvalPolicy": "on-request", "approvalsReviewer": "user", "sandbox": "workspace-write",
            "config": {"features": {"code_mode": {"enabled": False}, "goals": False, "apps": False, "plugins": False, "hooks": False}}})
        thread = loaded.get("thread") or {}
        require(thread.get("id") == spec["brainId"] and thread.get("sessionId", spec["brainId"]) == spec["brainId"] and
                thread.get("cwd") == spec["cwd"] and thread.get("status", {}).get("type") == "idle", "Inspection load identity/activity mismatch")
        policies = [proxy._rpc("thread/effectivePolicy/read", {"threadId": spec["brainId"]}) for _ in range(2)]
        require(policies[0] == policies[1] and matches(reported(policies[0], spec["brainId"], spec["cwd"])), "Loaded destination policy unverified")
        claim("project_assignment")
        proxy._rpc("thread/metadata/update", {"threadId": spec["brainId"], "projectId": scope["projectId"]})
        current = [proxy._rpc("thread/read", {"threadId": spec["brainId"], "includeTurns": True})["thread"] for _ in range(2)]
        require(current[0] == current[1] and current[0]["id"] == spec["brainId"] and current[0]["projectId"] == scope["projectId"] and
                current[0]["cwd"] == spec["cwd"] and current[0]["status"]["type"] == "idle" and
                digest(current[0]["turns"]) == spec["snapshot"]["turnsHash"] and
                current[0]["turns"][-1]["id"] == spec["snapshot"]["latestTurnId"] and
                current[0]["turns"][-1]["status"] == spec["snapshot"]["latestTurnStatus"], "Transferred identity/history view changed")
        require(read_archive(target).startswith(raw), "Native resume altered the preserved history prefix")
        fresh()
        result = {"version": 1, "specHash": digest(spec), "reviewHash": confirm_hash, "status": "metadata_transferred",
                  "brainId": spec["brainId"], "projectId": scope["projectId"], "historySha256": hashlib.sha256(raw).hexdigest(),
                  "historicalTerminalSafety": "unknown", "sourceCurrentTerminalSafety": "unknown",
                  "migrationQualified": False, "bindingInstalled": False, "resumeAuthorized": False, "pilotAccepted": False}
        write_record(attempt / "result.json", result)
        return result


def status(directory):
    """Historical file-only progress; no connection, refresh, load or replay."""
    directory = safe_path(directory, directory=True)
    attempt = directory / "attempt"
    if not attempt.exists():
        spec = load_spec(directory / "transfer.json")
        consumed = Path(spec["fencePath"]).exists()
        return {"status": "consumed_elsewhere_outcome_unknown" if consumed else "prepared_not_submitted",
                "consumed": consumed, "terminalSafety": "unknown", "migrationQualified": False}
    safe_path(attempt, directory=True)
    require(read_archive(attempt / "intent.json"), "Transfer intent missing")
    claims = [name for name in ("project_restore", "inspection_load", "project_assignment") if (attempt / (name + ".claim")).exists()]
    result_path = attempt / "result.json"
    result = decode(read_archive(result_path)) if result_path.exists() else None
    return {"status": "metadata_transferred" if result and result.get("status") == "metadata_transferred" else "outcome_unknown",
            "consumed": True, "claimedStages": claims, "result": result, "terminalSafety": "unknown", "migrationQualified": False}
