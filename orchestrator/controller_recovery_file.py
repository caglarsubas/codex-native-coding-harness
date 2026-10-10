"""Retire only the exact owner-reviewed abandoned controller credential.

Keep its private bytes, using an exclusive hard link and recoverable unlink.
This is filesystem credential hygiene, not native/process ownership release.
"""
import hashlib
import json
import os
import stat

from .core import require


def _read(path, controller):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                info.st_mode & 0o077 == 0 and info.st_nlink in (1, 2) and info.st_size < 2048,
                "Invalid private controller credential; ownership stays retained")
        raw = stream.read(2048)
        value = json.loads(raw)
        require(isinstance(value, dict) and set(value) == {"owner", "token"} and
                value == {k: controller[k] for k in ("owner", "token")},
                "Changed controller credential requires separate recovery")
        pin = {"device": info.st_dev, "inode": info.st_ino, "owner": info.st_uid,
               "mode": stat.S_IMODE(info.st_mode), "size": info.st_size,
               "sha256": hashlib.sha256(raw).hexdigest()}
        return pin, info.st_nlink


def pin(ledger, controller):
    try:
        value, links = _read(ledger.root / "standard-controller.json", controller)
        require(links == 1, "Linked controller credential requires its existing recovery receipt")
        return value
    except FileNotFoundError:
        return None


def _sync(ledger):
    fd = os.open(ledger.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def retire(ledger, controller, expected):
    source = ledger.root / "standard-controller.json"
    if expected is None:
        require(not source.exists() and not source.is_symlink(), "Unexpected controller credential; ownership stays retained")
        return {"status": "not_present"}
    sha = expected["sha256"]
    require(isinstance(sha, str) and len(sha) == 64 and all(c in "0123456789abcdef" for c in sha),
            "Invalid reviewed credential fingerprint")
    archive = ledger.root / ("standard-controller-recovered-" + sha + ".json")
    try:
        current, links = _read(source, controller)
    except FileNotFoundError:
        current, links = None, None
    try:
        retained, retained_links = _read(archive, controller)
    except FileNotFoundError:
        retained, retained_links = None, None
    require((current is None or current == expected) and (retained is None or retained == expected),
            "Controller credential identity changed; nothing is replaced")
    if current is None:
        require(retained == expected and retained_links == 1, "Retained controller credential is missing or ambiguous")
    else:
        if retained is None:
            require(links == 1, "Unreviewed controller hard link")
            os.link(source, archive, follow_symlinks=False)  # Exclusive: never overwrite an archive.
        current, links = _read(source, controller)
        retained, retained_links = _read(archive, controller)
        require(current == retained == expected and links == retained_links == 2,
                "Credential changed during retirement")
        _sync(ledger)
        os.unlink(source)
        _sync(ledger)
    return {"status": "retired", "archive": archive.name, "fingerprint": expected}
