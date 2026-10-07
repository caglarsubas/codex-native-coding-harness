"""Exact-owner device-number recovery, never database replacement or activation.

macOS can renumber a mounted volume after reboot. Ordinary registry reads still
refuse drift. This operator-only path compares the unchanged inode/brain and all
logical bytes to a separately retained private backup before reviewing new pins.
"""
import contextlib
import copy
import fcntl
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid

from .core import LEDGER_VERSIONS, Refusal, canonical, digest, require
from .enrollment import fence_exists, require_registration_open
from .native_read_client import decode
from .projects import _read as project_records
from .run_authority import managed
from .standard import PROTOCOL, TERMINAL
from .workspaces import fingerprint, identity, private_path

KIND = "workspace_device_recovery_v1"
PENDING_PLAY_KIND = "workspace_device_pending_play_recovery_v1"
MAX_BYTES = 128 * 1024 * 1024
MAX_ROWS = 50_000
MAX_HISTORY = 32
BOUNDARY = {"changesLedger": False, "startsWork": False, "nativeCallMade": False,
            "renewsRun": False, "changesHostBinding": False, "resetsUsage": False}


def file_pin(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path,
            "Recovery paths must be canonical without symlinks")
    private_path(path.parent, existing=True)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
            not info.st_mode & 0o077 and info.st_nlink == 1 and info.st_size <= MAX_BYTES,
            "Recovery requires bounded private regular databases")
    return {"device": info.st_dev, "inode": info.st_ino, "owner": info.st_uid,
            "mode": stat.S_IMODE(info.st_mode)}


@contextlib.contextmanager
def read_database(path):
    file_pin(path)
    with contextlib.closing(sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        yield db


def checked_fingerprint(db):
    deadline = time.monotonic() + 10
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    try:
        require(db.execute("PRAGMA page_count").fetchone()[0] *
                db.execute("PRAGMA page_size").fetchone()[0] <= MAX_BYTES,
                "Recovery database exceeds its bound")
        require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                "Recovery database integrity check failed")
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        require(len(tables) <= 128, "Recovery table count exceeds its bound")
        count = 0
        for table in tables:
            require(table.replace("_", "").isalnum(), "Unsupported recovery table")
            count += db.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0]
            require(count <= MAX_ROWS, "Recovery row count exceeds its bound")
        schema = [list(r) for r in db.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
        return {"schemaHash": digest(schema), "tables": fingerprint(db)}
    except sqlite3.Error as error:
        raise Refusal("Recovery database is unavailable or exceeds its read deadline") from error
    finally:
        db.set_progress_handler(None, 0)


def selected_row(db, workspace_id):
    identity(workspace_id)
    require_registration_open(db)
    row = db.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
    require(row is not None, "Unknown workspace")
    return dict(row), json.loads(row["data"])


def validate_history(data):
    history = data.get("identityRecoveries", [])
    require(isinstance(history, list) and len(history) <= MAX_HISTORY,
            "Recovery history needs an explicit migration")
    for record in history:
        require(isinstance(record, dict) and isinstance(record.get("document"), dict) and
                record["document"].get("kind") in (KIND, PENDING_PLAY_KIND) and
                record["document"].get("workspaceId") == data["id"] and
                record.get("documentHash") == digest(record["document"]),
                "Recovery history is invalid")
    return history


def pending_play_context(meta, commands, workers, ledger_db, workspace_id):
    """Preserve one unreceipted native Play, never reconcile or reissue it.

    Restoring an unchanged database's device pin is not a native-effect result.
    This separate review admits no registered work or permission response and
    carries the original unknown outcome through the registry-only transaction.
    """
    run = meta.get("standardRun")
    require(type(meta.get("schemaVersion")) is int and meta["schemaVersion"] == 4 and
            isinstance(run, dict) and run.get("protocol") == PROTOCOL and
            run.get("brainId") == meta["brainId"] and run.get("status") == "running" and
            run.get("tasks") == [] and run.get("merges", []) == [] and
            run.get("checkpoint") is None and run.get("recovery") is None and not workers and
            type(run.get("usageGuardVersion")) is int and run["usageGuardVersion"] == 1 and
            run.get("brainUsageCoverage") == "not_observed" and
            ledger_db.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 0,
            "Pending-Play recovery requires an empty, uncheckpointed standard run")
    pending = [c for c in commands if c.get("status") not in
               ("completed", "failed", "cancelled", "rejected")]
    require(len(pending) == 1, "Exactly one unreceipted Play must be preserved")
    command = pending[0]
    notification = command.get("notification") or {}
    require(isinstance(notification, dict), "Retained owned notification metadata required")
    observation = notification.get("nativeThreadObservation") or {}
    receipt = run.get("ownerReceipt") or {}
    require(isinstance(observation, dict) and isinstance(receipt, dict),
            "Retained owned turn and owner receipt metadata required")
    command_id, turn_id = command.get("id"), notification.get("nativeTurnId")
    try:
        valid_ids = all(isinstance(v, str) and str(uuid.UUID(v)) == v
                        for v in (command_id, turn_id, run.get("id")))
    except (ValueError, AttributeError):
        valid_ids = False
    require(valid_ids and command.get("kind") == "standard_play" and
            command.get("actor") in ("dashboard", "assistant_owner_confirmed") and
            command.get("status") == "queued" and
            command.get("payload") == {"runId": run["id"]} and
            receipt.get("id") == command_id and receipt.get("operation") == "play" and
            receipt.get("workspaceId") == workspace_id and receipt.get("measureUsage") is True,
            "Exact owner-confirmed pending Play required")
    stored = ledger_db.execute("SELECT data FROM commands WHERE id=?", (command_id,)).fetchone()
    require(stored is not None and json.loads(stored[0]) == command,
            "Pending Play row identity changed")
    require(notification.get("status") == "accepted" and
            notification.get("wakeId") == digest({"commandId": command_id}) and
            notification.get("brainId") == meta["brainId"] and
            notification.get("nativeDelivery") == "owned_turn_start" and
            notification.get("nativeTurnStatus") in ("unconfirmed", "connection_lost") and
            notification.get("nativeApprovals", []) == [] and
            type(observation.get("version")) is int and observation["version"] == 1 and
            observation.get("complete") is False and
            observation.get("rootThreadId") == meta["brainId"] and
            observation.get("nativeTurnId") == turn_id and observation.get("events") == [] and
            observation.get("streamStatus") in ("unconfirmed", "connection_lost") and
            isinstance(observation.get("gaps"), list) and
            "owned_stream_not_exhaustive" in observation["gaps"] and
            all(type(observation.get(key)) in (int, float) and
                math.isfinite(observation[key]) and observation[key] > 0
                for key in ("monitoringStartedAt", "monitoringEndedAt")) and
            observation["monitoringStartedAt"] <= observation["monitoringEndedAt"],
            "Retained unknown owned turn without registered effects required")
    return {"runId": run["id"], "commandId": command_id, "nativeTurnId": turn_id,
            "status": "unresolved", "commandHash": digest(command),
            "runHash": digest(run),
            "boundary": "Original Play and native outcome remain unresolved. No receipt, inactivity, absence, retry, wake or continuation is established."}


def context(registry, workspace_id, reference, registry_db, ledger_db, *, preserve_pending_play=False):
    registry_proof = checked_fingerprint(registry_db)
    proof = checked_fingerprint(ledger_db)
    row, data = selected_row(registry_db, workspace_id)
    validate_history(data)
    root = private_path(row["root"], existing=True)
    require(not fence_exists(root), "Enrollment fence requires its separate migration")
    ledger_path = root / "ledger.sqlite3"
    pin = file_pin(ledger_path)
    old = data.get("databaseIdentity")
    require(isinstance(old, list) and len(old) == 2 and all(type(v) is int for v in old) and
            old[1] == pin["inode"] and old[0] != pin["device"],
            "Only device-number drift with an unchanged ledger inode may use this recovery")
    meta_row = ledger_db.execute("SELECT data FROM meta WHERE id=1").fetchone()
    require(meta_row is not None, "Ledger metadata missing")
    meta = json.loads(meta_row[0])
    require(meta.get("schemaVersion") in LEDGER_VERSIONS and
            meta.get("brainId") == row["brain"] == data.get("brainId"),
            "Recovery cannot replace a brain or change ledger schema")
    require(not managed(meta) and "admissionBinding" not in meta,
            "Managed ownership requires its separate identity migration")
    require(meta.get("paused") is True and meta.get("controller") is None and meta.get("runner") is None,
            "Stop all writers and retain a paused, unowned controller before recovery")
    require(not (root / "standard-controller.json").exists() and
            not (root / "standard-controller.json").is_symlink(),
            "Private controller ownership requires reconciliation")
    repos = [json.loads(r[0]) for r in ledger_db.execute("SELECT data FROM repos")]
    require(repos and all(r.get("policyProfile") == "standard" for r in repos),
            "Strict Harness identity recovery is not supported")
    workers = [json.loads(r[0]) for r in ledger_db.execute("SELECT data FROM workers")]
    require(all(w.get("status") == "complete" for w in workers),
            "Unsettled legacy worker ownership requires separate reconciliation")
    commands = [json.loads(r[0]) for r in ledger_db.execute("SELECT data FROM commands")]
    run = meta.get("standardRun")
    pending = None
    if preserve_pending_play:
        pending = pending_play_context(meta, commands, workers, ledger_db, workspace_id)
    else:
        require(all(c.get("status") in ("completed", "failed", "cancelled", "rejected") for c in commands),
                "Pending commands or uncertain effects cannot use device recovery")
        if run:
            require(run.get("protocol") == PROTOCOL and run.get("brainId") == meta["brainId"] and
                    run.get("status") in ("paused", "blocked", "completed") and
                    all(t.get("status") in TERMINAL for t in run.get("tasks", [])) and
                    not any(m.get("status") in ("prepared", "issued", "uncertain") for m in run.get("merges", [])),
                    "Active or unresolved standard effects require separate reconciliation")
    reference = Path(reference)
    require(reference != ledger_path and reference != registry.db,
            "Use a separately retained reference backup, not the current database")
    reference_pin = file_pin(reference)
    with read_database(reference) as reference_db:
        reference_proof = checked_fingerprint(reference_db)
    require(proof == reference_proof, "Ledger contents do not match the retained reference backup")
    saved_catalog, bindings = project_records(registry_db)
    linked = {key: value for key, value in bindings.items() if value.get("workspaceId") == workspace_id}
    require(len(linked) <= 1, "Ambiguous retained project binding")
    for key, binding in linked.items():
        require(binding.get("brainId") == meta["brainId"] and binding.get("databaseIdentity") == old and
                saved_catalog and any(p["key"] == key and p["locationHash"] == binding.get("locationHash")
                                      for p in saved_catalog["projects"]),
                "Changed project mapping requires its separate owner review")
    document = {"kind": PENDING_PLAY_KIND if preserve_pending_play else KIND,
            "workspaceId": workspace_id, "root": str(root), "brainId": meta["brainId"],
            "registryPin": file_pin(registry.db), "registryHash": digest(registry_proof),
            "workspaceRecordHash": digest(row), "oldIdentity": old,
            "newIdentity": [pin["device"], pin["inode"]], "ledgerPin": pin,
            "ledgerRevision": meta["revision"], "ledgerHash": digest(proof),
            "reference": {"path": str(reference), "pin": reference_pin, "hash": digest(reference_proof)},
            "projectBindings": linked, "boundary": BOUNDARY}
    if pending is not None:
        document["pendingPlay"] = pending
    return document


def preview(registry, workspace_id, reference, *, preserve_pending_play=False):
    """No database initialization, mutation, locks on native hosts or notification."""
    require(type(preserve_pending_play) is bool, "Explicit pending-Play preview mode required")
    with read_database(registry.db) as registry_db:
        row, _ = selected_row(registry_db, workspace_id)
        with read_database(Path(row["root"]) / "ledger.sqlite3") as ledger_db:
            document = context(registry, workspace_id, reference, registry_db, ledger_db,
                               preserve_pending_play=preserve_pending_play)
    return {"documentHash": digest(document), "document": document}


@contextlib.contextmanager
def dashboard_lock(root):
    path = root / "dashboard.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1,
                "Unsafe dashboard lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Refusal("Stop the dashboard before identity recovery") from error
        yield
    finally:
        os.close(fd)


def backup_database(source_path, destination, expected_hash):
    os.close(os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    with read_database(source_path) as source, contextlib.closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        require(digest(checked_fingerprint(target)) == expected_hash, "Recovery backup verification failed")


def confirm(registry, workspace_id, proposal, confirm_hash, *, confirmed=False, writers_stopped=False):
    require(confirmed is True and writers_stopped is True,
            "Exact owner confirmation and stopped-writer acknowledgment are required")
    require(isinstance(proposal, dict) and set(proposal) == {"documentHash", "document"} and
            isinstance(proposal["document"], dict) and
            proposal["documentHash"] == confirm_hash == digest(proposal["document"]),
            "Exact recovery preview hash required")
    document = proposal["document"]
    require(document.get("kind") in (KIND, PENDING_PLAY_KIND) and document.get("workspaceId") == workspace_id,
            "Exact selected workspace recovery required")
    require(isinstance(document.get("reference"), dict) and
            isinstance(document["reference"].get("path"), str), "Recovery reference is missing")
    # Registry -> local SQLite lock order. No Ledger constructor/schema upgrades.
    with contextlib.ExitStack() as local_locks, registry.tx() as registry_db:
        row, data = selected_row(registry_db, workspace_id)
        history = validate_history(data)
        for record in history:
            if record["documentHash"] == confirm_hash:
                require(record["document"] == document, "Conflicting historical recovery")
                return copy.deepcopy(record)  # Historical replay never re-adopts old pins.
        require(len(history) < MAX_HISTORY, "Recovery history needs an explicit migration")
        root = private_path(row["root"], existing=True)
        local_locks.enter_context(dashboard_lock(root))
        ledger_db = local_locks.enter_context(contextlib.closing(sqlite3.connect(
            (root / "ledger.sqlite3").as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=5)))
        ledger_db.row_factory = sqlite3.Row
        ledger_db.execute("BEGIN IMMEDIATE")
        # Keep the local and dashboard locks until AFTER the registry commit.
        # The local transaction makes no writes and is always rolled back.
        local_locks.callback(ledger_db.rollback)
        pending_mode = document["kind"] == PENDING_PLAY_KIND
        current = context(registry, workspace_id, document["reference"]["path"], registry_db, ledger_db,
                          preserve_pending_play=pending_mode)
        require(current == document, "Recovery scope or evidence changed; prepare a new preview")
        backup_id = "device-recovery-" + str(uuid.uuid4())
        backups = registry.root / "backups"
        backups.mkdir(mode=0o700, exist_ok=True)
        private_path(backups, existing=True)
        retained = backups / backup_id
        retained.mkdir(mode=0o700)
        backup_database(registry.db, retained / "platform.sqlite3", document["registryHash"])
        backup_database(root / "ledger.sqlite3", retained / "ledger.sqlite3", document["ledgerHash"])
        require(context(registry, workspace_id, document["reference"]["path"], registry_db, ledger_db,
                        preserve_pending_play=pending_mode) == document,
                "Recovery scope changed during backup")
        receipt = {"id": backup_id, "documentHash": confirm_hash, "document": document,
                   "appliedAt": time.time(), "backupId": backup_id, "boundary": BOUNDARY}
        updated = {**data, "databaseIdentity": document["newIdentity"],
                   "identityRecoveries": [*history, receipt]}
        registry_db.execute("UPDATE workspaces SET data=? WHERE id=?", (canonical(updated), workspace_id))
        for key, binding in document["projectBindings"].items():
            registry_db.execute("UPDATE project_bindings SET data=? WHERE project_key=? AND workspace=?",
                                (canonical({**binding, "databaseIdentity": document["newIdentity"]}), key, workspace_id))
        return receipt


def read_preview(path):
    """Owner setup files remain private; reject aliases and duplicate JSON keys."""
    before = file_pin(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require([info.st_dev, info.st_ino] == [before["device"], before["inode"]] and info.st_size <= 64_000,
                "Bounded unchanged recovery preview required")
        raw = stream.read(64_001)
        require(len(raw) <= 64_000 and file_pin(path) == before,
                "Recovery preview changed or exceeds its bound")
    try:
        return decode(raw)
    except Refusal as error:
        raise Refusal("Invalid recovery preview JSON") from error
