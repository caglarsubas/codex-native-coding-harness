"""Explicit read-only export of one bound root brain from shared ~/.codex.

Never lists sessions, opens credentials/databases, loads a thread or changes
permissions. A private archive is not native transfer or continuation authority.
"""
import hashlib
import os
from pathlib import Path
import pwd
import stat
import time

from . import public_identity_transfer as transfer
from .app_server_wake import load_binding
from .core import Refusal, digest, require
from .enrollment import record_in
from .native_project_assignment import _scope, _read_registry
from .native_read_client import decode, file_identity
from .public_host_lifecycle import sync_directory, write_record

KIND = "shared_codex_exact_brain_export_v1"
FIELDS = {"version", "kind", "createdAt", "sourceBindingPath", "sourceBindingHash", "scope", "context",
          "snapshot", "archivePath", "archivePin"}


def shared_home():
    # A CLI/browser/manifest cannot nominate another user's home or a test root.
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / ".codex"


class SourceProxy(transfer.TransferProxy):
    def __init__(self, endpoint, scope):
        self.scope = scope
        super().__init__(endpoint)

    def _rpc(self, method, params):
        require(method == "initialize" or
                method == "project/read" and params == {"projectId": self.scope["projectId"]} or
                method == "thread/read" and params == {"threadId": self.scope["brainId"], "includeTurns": True},
                "Export permits only exact project/brain metadata reads")
        return super()._rpc(method, params)


def directory_pin(path, info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022,
            "Shared source directory is not owner-controlled")
    # Other brains may create files here. Their directory timestamps are not
    # this brain's identity, and no directory contents are inspected.
    return {"path": str(path), "device": info.st_dev, "inode": info.st_ino,
            "owner": info.st_uid, "mode": stat.S_IMODE(info.st_mode)}


def read_shared_rollout(path, home, brain, cwd):
    home = Path(home)
    require(home == shared_home(), "Only the current OS user's exact shared Codex home is supported")
    transfer.safe_path(home, directory=True, private=False)
    path = transfer.safe_path(path, private=False)
    require(path.is_relative_to(home / "sessions") and path.suffix == ".jsonl" and
            path.name.startswith("rollout-") and path.name.endswith("-" + brain + ".jsonl"),
            "Only the native-returned exact brain rollout under sessions is supported")
    relative = path.relative_to(home)
    require(2 <= len(relative.parts) <= 8, "Native rollout path exceeds its bounded depth")
    directories, descriptors = [], []
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        current = os.open(home, flags); descriptors.append(current)
        directories.append(directory_pin(home, os.fstat(current)))
        parent = home
        for part in relative.parts[:-1]:
            current = os.open(part, flags, dir_fd=current); descriptors.append(current)
            parent = parent / part
            directories.append(directory_pin(parent, os.fstat(current)))
        fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1 and
                    not before.st_mode & 0o022 and before.st_dev == directories[0]["device"] and
                    0 < before.st_size <= transfer.MAX_ROLLOUT, "Bounded owner-controlled unaliased source rollout required")
            raw = stream.read(transfer.MAX_ROLLOUT + 1)
            require(file_identity(before) == file_identity(os.fstat(stream.fileno())) ==
                    file_identity(os.stat(relative.name, dir_fd=current, follow_symlinks=False)), "Source rollout changed during read")
        # Revalidate both the opened chain and the public path. Renames,
        # permissions races or an ancestor replaced by a symlink refuse.
        transfer.safe_path(home, directory=True, private=False)
        transfer.safe_path(path, private=False)
        require(directories == [directory_pin(Path(pin["path"]), os.fstat(fd)) for pin, fd in zip(directories, descriptors)] and
                directories == [directory_pin(Path(pin["path"]), Path(pin["path"]).lstat()) for pin in directories] and
                file_identity(path.lstat()) == file_identity(before), "Shared source path identity changed")
        transfer.validate_rollout_data(raw, brain, cwd)
        return raw, {"path": str(path), "identity": list(file_identity(before)),
                     "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}, directories
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def shared_snapshot(proxy, scope):
    project, thread = transfer.source_projection(proxy, scope)
    home = proxy.initialization["codexHome"]
    raw, pin, directories = read_shared_rollout(thread["path"], home, scope["brainId"], scope["cwd"])
    snapshot = transfer.snapshot_record(project, thread, home, pin)
    snapshot["sourceDirectoryIdentities"] = directories
    return snapshot, raw


def source_scope(registry, ledger, source_path):
    with _read_registry(registry) as db:
        require(record_in(db) is None, "Strict enrollment refuses shared brain export")
    source = load_binding(source_path)
    scope = _scope(registry, ledger.workspace_id, source)
    require(len(source["brains"]) == 1, "Shared export is scoped to exactly one registered brain")
    policy = source["brains"][scope["brainId"]]["nativePolicy"]
    require(policy.get("approvalsReviewer", "user") == "user" and
            {k: v for k, v in policy.items() if k != "approvalsReviewer"} ==
            {"sandbox": "workspace-write", "approvalPolicy": "on-request", "codeMode": False},
            "Unchanged restricted original policy required")
    return source, scope, transfer.context(ledger, source)


def boundary():
    return {"nativeWrites": 0, "historyLoaded": False, "bindingInstalled": False, "runChanged": False,
            "usageReset": False, "expiryExtended": False, "terminalSafety": "unknown", "pilotAccepted": False}


def portable_scope(scope):
    return dict(scope, root=str(scope["root"]))


def export(registry, ledger, source_path, directory):
    """Explicit owner/operator read-only collection, not an exact native permit."""
    source, scope, saved = source_scope(registry, ledger, source_path)
    directory = Path(directory)
    require(directory.is_absolute() and str(directory.parent.resolve(strict=True) / directory.name) == str(directory),
            "Canonical new private export directory required")
    transfer.safe_path(directory.parent, directory=True)
    require(not directory.exists() and not directory.is_symlink(), "Export directory already exists; retain it, never overwrite")
    for root in (shared_home(), Path(scope["cwd"]), ledger.root, registry.root):
        require(not directory.is_relative_to(root) and not root.is_relative_to(directory),
                "Export must be disjoint from shared home, checkout and live stores")
    with SourceProxy(source["endpoint"], scope) as proxy:
        first, raw = shared_snapshot(proxy, scope)
        second, _ = shared_snapshot(proxy, scope)
        require(first == second and first["latestTurnId"] == saved["originalTurnId"] and
                first["latestTurnStatus"] == saved["originalTurnStatus"], "Original ended-turn/history view changed")
    require(source_scope(registry, ledger, source_path) == (source, scope, saved), "Source scope changed before retention")
    directory.mkdir(mode=0o700); sync_directory(directory.parent)
    write_record(directory / "intent.json", {"kind": KIND, "sourceBindingHash": digest(source),
                 "context": saved, "snapshotHash": digest(first), "createdAt": time.time()})
    pending, archive = directory / "history.pending", directory / "history.jsonl"
    with os.fdopen(os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.chmod(pending, 0o400)
    os.link(pending, archive, follow_symlinks=False); pending.unlink(); sync_directory(directory)
    with SourceProxy(source["endpoint"], scope) as proxy:
        last, _ = shared_snapshot(proxy, scope)
    require(first == last and source_scope(registry, ledger, source_path) == (source, scope, saved) and
            transfer.read_archive(archive) == raw, "Source changed while retaining export; partial evidence stays unknown")
    record = {"version": 1, "kind": KIND, "createdAt": time.time(), "sourceBindingPath": str(source_path),
              "sourceBindingHash": digest(source), "scope": portable_scope(scope), "context": saved, "snapshot": first,
              "archivePath": str(archive), "archivePin": transfer.archive_pin(archive)}
    write_record(directory / "export.json", record)
    return status(directory)


def load_record(path):
    path = transfer.safe_path(path)
    require(path.name == "export.json", "Exact private export manifest required")
    transfer.safe_path(path.parent, directory=True)
    raw = transfer.read_archive(path)
    require(len(raw) <= 65536, "Export manifest exceeds bound")
    record = decode(raw)
    require(isinstance(record, dict) and set(record) == FIELDS and type(record["version"]) is int and
            record["version"] == 1 and record["kind"] == KIND and
            record["archivePath"] == str(path.parent / "history.jsonl"), "Closed exact export record required")
    archive = record["archivePath"]
    require(transfer.archive_pin(archive) == record["archivePin"], "Private export bytes or identity changed")
    transfer.validate_rollout_data(transfer.read_archive(archive), record["scope"]["brainId"], record["scope"]["cwd"])
    require(record["snapshot"]["rollout"]["sha256"] == record["archivePin"]["sha256"] and
            record["snapshot"]["rollout"]["bytes"] == record["archivePin"]["bytes"], "Original/export byte pins disagree")
    return record


def validate_descriptor(value):
    require(isinstance(value, dict) and set(value) == {"path", "pin"} and isinstance(value["path"], str) and
            isinstance(value["pin"], dict) and set(value["pin"]) == {"identity", "sha256", "bytes"},
            "Closed shared-source export descriptor required")


def descriptor(path):
    load_record(path)
    return {"path": str(path), "pin": transfer.archive_pin(path)}


def for_transfer(proxy, scope, value, source_path, binding_hash, saved):
    """A retained export never substitutes for fresh original-host/file reads."""
    validate_descriptor(value)
    require(transfer.archive_pin(value["path"]) == value["pin"], "Reviewed source export changed")
    record = load_record(value["path"])
    require(record["sourceBindingPath"] == str(source_path) and record["sourceBindingHash"] == binding_hash and
            record["context"] == saved and record["scope"] == portable_scope(scope), "Export belongs to a different source/run/brain")
    snapshot, raw = shared_snapshot(proxy, scope)
    require(snapshot == record["snapshot"] and raw == transfer.read_archive(record["archivePath"]),
            "Original shared source changed after export")
    return snapshot, raw


def status(directory):
    """File-only historical status. Does not renew native/source freshness."""
    directory = transfer.safe_path(directory, directory=True)
    if not (directory / "export.json").exists():
        return {"kind": KIND, "status": "partial_export_unknown", "boundary": boundary()}
    record = load_record(directory / "export.json")
    return {"kind": KIND, "status": "private_export_retained", "manifestPath": str(directory / "export.json"),
            "brainId": record["scope"]["brainId"], "historySha256": record["archivePin"]["sha256"],
            "historyBytes": record["archivePin"]["bytes"], "collectedAt": record["createdAt"],
            "sourceFreshness": "historical_only; rechecked at transfer", "boundary": boundary()}
