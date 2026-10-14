"""Closed macOS source-built package inspection, separate from vendor trust.

No packaged executable, native RPC, host, credential or ledger operation runs.
Pins are integrity/provenance inputs to owner review, not build attestation or
desktop peer authorization. The first profile supports monolithic arg0 only.
"""
import os
from pathlib import Path
import re
import stat
import struct

from .core import digest, require
from .host_runtime import file_record, safe_path, stamp
from .native_read_client import decode

PROFILE = "public_app_server_host_v1"
FILES = ("public-runtime.json", "bin/codex", "source.bundle")
LAYOUT_FIELDS = {"schemaVersion", "profile", "trust", "desktopBridge", "target", "version",
                 "sourceCommit", "sourceTree", "sourceBundleSha256", "executableSha256",
                 "entrypoint", "helperMode", "dependencies"}
PIN_FIELDS = {"root", "inventoryHash", "manifestHash", "executableHash", "sourceBundleHash",
              "sourceCommit", "sourceTree", "target", "version", "fileCount", "totalBytes", "libraryHash"}
MAX_BYTES = 1024 * 1024 * 1024


def closed_entries(path, allowed):
    found = set()
    with os.scandir(path) as entries:
        for entry in entries:
            require(entry.name in allowed and entry.name not in found, "Unsupported public runtime entry")
            found.add(entry.name)
    require(found == allowed, "Incomplete public runtime layout")


def system_libraries(path):
    """Parse bounded ARM64 Mach-O load commands without running the binary.

    Reject relative/loader paths, rpaths and dyld environment commands. System
    framework dependencies are OS dependencies, not bundled/vendor attestations.
    """
    info = safe_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        require(stamp(os.fstat(stream.fileno())) == stamp(info), "Executable changed before load-command inspection")
        header = stream.read(32)
        require(len(header) == 32, "ARM64 Mach-O executable required")
        magic, cpu, _, kind, count, size, _, _ = struct.unpack("<8I", header)
        require(magic == 0xfeedfacf and cpu == 0x100000c and kind == 2 and
                0 < count <= 512 and 0 < size <= 2_000_000 and 32+size <= info.st_size,
                "Closed macOS ARM64 monolithic runtime required")
        raw = stream.read(size)
        require(len(raw) == size and stamp(os.fstat(stream.fileno())) == stamp(info), "Executable changed during load-command inspection")
    libraries, offset = [], 0
    for _ in range(count):
        require(offset+8 <= size, "Truncated Mach-O load command")
        command, length = struct.unpack_from("<2I", raw, offset)
        require(length >= 8 and length % 8 == 0 and offset+length <= size, "Invalid Mach-O load command")
        require(command not in (0x8000001c, 0x27), "Runtime rpaths and dyld environment overrides are unsupported")
        require(command in {0x19,0x2,0xb,0xe,0x1b,0x32,0x2a,0x80000028,0xc,0x26,0x29,0x1d,
                            0x80000022,0x24,0x80000034,0x80000033,0x80000018,0x8000001f,0x80000023},
                "Unsupported Mach-O load command needs separate runtime qualification")
        if command in (0xc, 0x80000018, 0x8000001f, 0x80000023, 0xe):
            minimum = 12 if command == 0xe else 24
            require(length >= minimum, "Truncated runtime dependency command")
            start = struct.unpack_from("<I", raw, offset+8)[0]
            require(minimum <= start < length, "Invalid runtime dependency offset")
            name_bytes = raw[offset+start:offset+length]
            end = name_bytes.find(b"\0")
            require(0 < end <= 4096, "Bounded terminated runtime dependency required")
            name = name_bytes[:end].decode("utf-8")
            require(name.startswith(("/usr/lib/", "/System/Library/")) and
                    str(Path(name)) == name and ".." not in Path(name).parts and
                    (command != 0xe or name == "/usr/lib/dyld"), "Only fixed macOS system dependencies are supported")
            libraries.append([command, name])
        offset += length
    require(offset == size and libraries and stamp(path.lstat()) == stamp(info), "Runtime dependency view is incomplete or changed")
    return libraries


def inspect_package(root):
    root = Path(root)
    initial = safe_path(root, directory=True)
    require(initial.st_uid == os.getuid() and not initial.st_mode & 0o077, "Owner-private public runtime root required")
    closed_entries(root, {"public-runtime.json", "bin", "source.bundle"})
    directory = safe_path(root/"bin", directory=True)
    closed_entries(root/"bin", {"codex"})
    manifest_path = root/"public-runtime.json"
    manifest_info = safe_path(manifest_path)
    require(0 < manifest_info.st_size <= 65536, "Small public package manifest required")
    fd = os.open(manifest_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        require(stamp(os.fstat(stream.fileno())) == stamp(manifest_info), "Public manifest changed")
        manifest = decode(stream.read(65537))
        require(stamp(os.fstat(stream.fileno())) == stamp(manifest_info), "Public manifest changed during read")
    require(isinstance(manifest, dict) and set(manifest) == LAYOUT_FIELDS and
            type(manifest["schemaVersion"]) is int and manifest["schemaVersion"] == 1 and
            manifest["profile"] == PROFILE and manifest["trust"] == "operator_reviewed_build_v1" and
            manifest["desktopBridge"] == "absent" and manifest["target"] == "aarch64-apple-darwin" and
            manifest["entrypoint"] == "bin/codex" and manifest["helperMode"] == "monolithic_arg0" and
            manifest["dependencies"] == "macos_system_libraries_only" and
            isinstance(manifest["version"], str) and re.fullmatch(r"[A-Za-z0-9_.+-]{1,128}", manifest["version"]) and
            all(isinstance(manifest[k], str) and re.fullmatch(r"[0-9a-f]{40}", manifest[k]) for k in ("sourceCommit", "sourceTree")) and
            all(isinstance(manifest[k], str) and re.fullmatch(r"[0-9a-f]{64}", manifest[k]) for k in ("sourceBundleSha256", "executableSha256")),
            "Exact source-built public runtime layout required")
    records, total = [], 0
    for relative in FILES:
        record = file_record(root, relative, MAX_BYTES-total)
        records.append(record); total += record["bytes"]
    by_path = {r["path"]:r for r in records}
    require(by_path["bin/codex"]["mode"] & 0o111 and os.access(root/"bin/codex", os.X_OK), "Public CLI must be executable")
    require(by_path["bin/codex"]["sha256"] == manifest["executableSha256"] and
            by_path["source.bundle"]["sha256"] == manifest["sourceBundleSha256"], "Binary or source-bundle hash differs from review")
    libraries = system_libraries(root/"bin/codex")
    require(stamp(root.lstat()) == stamp(initial) and stamp((root/"bin").lstat()) == stamp(directory) and
            stamp(manifest_path.lstat()) == stamp(manifest_info), "Public package directory or manifest changed")
    for row in records:
        final = (root/row["path"]).lstat()
        require((final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns, stat.S_IMODE(final.st_mode)) ==
                (row["device"], row["inode"], row["bytes"], row["modifiedNs"], row["changedNs"], row["mode"]),
                "Public runtime file changed after inspection")
    return {"root":str(root), "inventoryHash":digest({"files":records,"root":stamp(initial),"bin":stamp(directory)}),
            "manifestHash":by_path["public-runtime.json"]["sha256"], "executableHash":by_path["bin/codex"]["sha256"],
            "sourceBundleHash":by_path["source.bundle"]["sha256"], "sourceCommit":manifest["sourceCommit"],
            "sourceTree":manifest["sourceTree"], "target":manifest["target"], "version":manifest["version"],
            "fileCount":len(records), "totalBytes":total, "libraryHash":digest(libraries)}


def validate_pin(pin):
    require(isinstance(pin, dict) and set(pin) == PIN_FIELDS, "Closed public runtime pin required")
    require(inspect_package(pin["root"]) == pin, "Reviewed public runtime changed; no repair in place or fallback")
