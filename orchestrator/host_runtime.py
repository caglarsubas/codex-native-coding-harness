"""Bounded, non-executing inspection of a complete local Codex CLI package.

This is a file-integrity prerequisite, not native tool qualification. It does
not run Doctor, a helper, a host or a turn, and never reads Codex user state.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from .core import digest, require

PIN_FIELDS = {"root", "inventoryHash", "manifestHash", "cliHash", "helperHash",
              "fileCount", "totalBytes", "version", "target"}
TREES = ("bin", "CodexCLI.app", "codex-resources", "codex-path")
REQUIRED = ("codex-package.json", "bin/codex", "bin/codex-code-mode-host",
            "CodexCLI.app/Contents/MacOS/codex", "codex-path/rg")
MAX_FILES, MAX_BYTES, MAX_FILE_BYTES = 512, 1024 * 1024 * 1024, 512 * 1024 * 1024


def stamp(info):
    # Reading a file or directory may update atime. That is not content drift
    # and must not make the non-mutating guard refuse a first real package read.
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def safe_path(path, *, directory=False):
    require(path.is_absolute() and path.resolve(strict=True) == path, "Runtime paths must be canonical without symlinks")
    for parent in (path, *path.parents):
        info = parent.lstat()
        require(info.st_uid in (0, os.getuid()) and
                (not info.st_mode & 0o022 or info.st_uid == 0 and stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX),
                "Runtime package has an unsafe owner or writable ancestor")
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),
            "Runtime package requires real directories and regular files")
    return info


def file_record(root, relative, remaining):
    path = root / relative
    before = safe_path(path)
    require(before.st_nlink == 1 and 0 < before.st_size <= min(MAX_FILE_BYTES, remaining),
            "Runtime files must be bounded and have no hard-link aliases")
    # O_NOFOLLOW also fences a last-component substitution between lstat/open.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        require(stamp(os.fstat(stream.fileno())) == stamp(before), "Runtime file changed before inspection")
        value = hashlib.sha256()
        count = 0
        while chunk := stream.read(1024 * 1024):
            count += len(chunk)
            require(count <= before.st_size, "Runtime file grew during inspection")
            value.update(chunk)
        require(count == before.st_size and stamp(os.fstat(stream.fileno())) == stamp(before), "Runtime file changed during inspection")
    require(stamp(path.lstat()) == stamp(before), "Runtime file changed after inspection")
    return {"path": relative, "sha256": value.hexdigest(), "bytes": before.st_size,
            "mode": stat.S_IMODE(before.st_mode), "device": before.st_dev, "inode": before.st_ino,
            "modifiedNs": before.st_mtime_ns, "changedNs": before.st_ctime_ns}


def inventory_paths(root):
    # Do not scan the surrounding private host directory: it may hold credentials
    # and journals. Only the closed vendor package trees are inspected.
    files, directories = ["codex-package.json"], {}
    for name in TREES:
        safe_path(root / name, directory=True)
        pending = [root / name]
        while pending:
            current = pending.pop()
            directories[str(current.relative_to(root))] = stamp(safe_path(current, directory=True))
            require(len(directories) <= MAX_FILES, "Runtime directory inventory exceeds the bound")
            entries = []
            with os.scandir(current) as scan:
                for entry in scan:
                    entries.append(Path(entry.path))
                    require(len(entries) <= MAX_FILES, "Runtime directory exceeds the bound")
            entries.sort()
            for path in entries:
                relative = str(path.relative_to(root))
                require(len(relative) <= 1024 and len(path.relative_to(root).parts) <= 16,
                        "Runtime path exceeds the bound")
                info = path.lstat()
                if stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                else:
                    safe_path(path)
                    files.append(relative)
                    require(len(files) <= MAX_FILES, "Runtime file inventory exceeds the bound")
    return sorted(files), directories


def inspect_package(root):
    root = Path(root)
    before = safe_path(root, directory=True)
    manifest_path = root / "codex-package.json"
    info = safe_path(manifest_path)
    require(info.st_size <= 65536, "Small package manifest required")
    fd = os.open(manifest_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        require(stamp(os.fstat(stream.fileno())) == stamp(info), "Package manifest changed before inspection")
        data = stream.read(65537)
        require(len(data) == info.st_size and len(data) <= 65536 and
                stamp(os.fstat(stream.fileno())) == stamp(info), "Package manifest changed during inspection")
    require(stamp(manifest_path.lstat()) == stamp(info), "Package manifest changed after inspection")
    layout = json.loads(data)
    require(isinstance(layout, dict) and set(layout) == {"layoutVersion", "version", "target", "variant",
            "entrypoint", "resourcesDir", "pathDir"} and type(layout["layoutVersion"]) is int and
            layout["layoutVersion"] == 1 and layout["variant"] == "codex" and
            layout["entrypoint"] == "bin/codex" and layout["resourcesDir"] == "codex-resources" and
            layout["pathDir"] == "codex-path" and
            all(isinstance(layout[k], str) and re.fullmatch(r"[A-Za-z0-9_.+-]{1,128}", layout[k])
                for k in ("version", "target")), "Unsupported Codex package layout; require a new explicit review")
    paths, directories = inventory_paths(root)
    require(all(p in paths for p in REQUIRED) and any(p.startswith("codex-resources/") for p in paths),
            "Complete CLI, runtime helper, resources and search package required before launch")
    records, total = [], 0
    for relative in paths:
        record = file_record(root, relative, MAX_BYTES-total)
        records.append(record)
        total += record["bytes"]
    by_path = {r["path"]: r for r in records}
    for executable in REQUIRED[1:]:
        require(by_path[executable]["mode"] & 0o111 and os.access(root / executable, os.X_OK),
                "Runtime entrypoint, CLI, helper and search must be executable")
    again, after_directories = inventory_paths(root)
    require(stamp(root.lstat()) == stamp(before) and paths == again and directories == after_directories and
            stamp(manifest_path.lstat()) == stamp(info), "Runtime inventory changed during inspection")
    # Recheck previously read files too; mutations to an earlier file cannot hide
    # behind stable directory entries or a later helper's successful inspection.
    for record in records:
        final = (root / record["path"]).lstat()
        require((final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns,
                 stat.S_IMODE(final.st_mode)) ==
                (record["device"], record["inode"], record["bytes"], record["modifiedNs"], record["changedNs"], record["mode"]),
                "Runtime file changed before inspection completed")
    inventory = {"files": records, "directories": sorted(directories.items()),
                 "rootIdentity": [before.st_dev, before.st_ino, before.st_mode, before.st_uid, before.st_gid]}
    return {"root": str(root), "inventoryHash": digest(inventory), "manifestHash": by_path["codex-package.json"]["sha256"],
            "cliHash": by_path["CodexCLI.app/Contents/MacOS/codex"]["sha256"],
            "helperHash": by_path["bin/codex-code-mode-host"]["sha256"], "fileCount": len(records),
            "totalBytes": total, "version": layout["version"], "target": layout["target"]}


def validate_pin(pin):
    require(isinstance(pin, dict) and set(pin) == PIN_FIELDS and
            all(isinstance(pin[k], str) and re.fullmatch(r"[0-9a-f]{64}", pin[k])
                for k in ("inventoryHash", "manifestHash", "cliHash", "helperHash")) and
            type(pin["fileCount"]) is int and 0 < pin["fileCount"] <= MAX_FILES and
            type(pin["totalBytes"]) is int and 0 < pin["totalBytes"] <= MAX_BYTES and
            isinstance(pin["root"], str), "Exact runtime package pin required")
    require(inspect_package(pin["root"]) == pin, "Reviewed runtime package changed; prepare a new review, never repair in place")
