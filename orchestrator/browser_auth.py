"""Local browser pairing. Only hashes of bearer cookies are retained on disk.

One dashboard owns an origin. File locks serialize durable session changes;
normal eight-hour sessions remain process-local unless the owner opts in.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time

from .core import Refusal

UNAUTHENTICATED = "Sign in once with this dashboard's private link. Choose Remember this browser to stay signed in through restarts."
UNAVAILABLE = "Browser access storage is unavailable. No access was granted; check the private local authentication files."
DAYS = (7, 30, 90)


def remember_days(value):
    if type(value) is not int or value not in (0, *DAYS):
        raise Refusal("Remember duration must be 0, 7, 30 or 90 days")
    return value


class BrowserAuth:
    def __init__(self, root, origin, clock=time.time):
        self.clock = clock
        self.root = Path(root).resolve() / "browser-auth"
        self.root.mkdir(mode=0o700, exist_ok=True)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Refusal(UNAVAILABLE)
        namespace = hashlib.sha256((str(self.root) + "\n" + origin).encode()).hexdigest()[:24]
        self.cookie = "orchestrator_session_" + namespace
        self.filename = namespace + ".json"
        self.temporary = {}
        self.lock = threading.RLock()
        with self._locked() as directory:
            try:
                self._read(directory)
            except FileNotFoundError:
                self._write(directory, {})

    @staticmethod
    def _check_file(fd):
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
            raise Refusal(UNAVAILABLE)

    @contextmanager
    def _locked(self):
        with self.lock:
            try:
                directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    info = os.fstat(directory)
                    if info.st_uid != os.getuid() or info.st_mode & 0o077:
                        raise Refusal(UNAVAILABLE)
                    fd = os.open(self.filename + ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
                    try:
                        self._check_file(fd)
                        fcntl.flock(fd, fcntl.LOCK_EX)
                        yield directory
                    finally:
                        os.close(fd)
                finally:
                    os.close(directory)
            except (OSError, ValueError, TypeError, KeyError) as error:
                raise Refusal(UNAVAILABLE) from error

    def _read(self, directory):
        fd = os.open(self.filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "r") as stream:
            self._check_file(stream.fileno())
            if os.fstat(stream.fileno()).st_size > 32768:
                raise Refusal(UNAVAILABLE)
            record = json.load(stream)
        if not isinstance(record, dict) or set(record) != {"version", "sessions"} or record["version"] != 1:
            raise Refusal(UNAVAILABLE)
        sessions = record["sessions"]
        if not isinstance(sessions, dict) or len(sessions) > 32:
            raise Refusal(UNAVAILABLE)
        for key, row in sessions.items():
            if not re.fullmatch(r"[0-9a-f]{64}", key) or not isinstance(row, dict) or set(row) != {"csrf", "created", "expires", "days"}:
                raise Refusal(UNAVAILABLE)
            if not isinstance(row["csrf"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", row["csrf"]):
                raise Refusal(UNAVAILABLE)
            if type(row["days"]) is not int or row["days"] not in DAYS:
                raise Refusal(UNAVAILABLE)
            if any(type(row[k]) not in (int, float) or not math.isfinite(row[k]) for k in ("created", "expires")):
                raise Refusal(UNAVAILABLE)
            if row["expires"] - row["created"] != row["days"] * 86400:
                raise Refusal(UNAVAILABLE)
        return sessions

    def _write(self, directory, sessions):
        name = self.filename + "." + secrets.token_hex(8) + ".tmp"
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump({"version": 1, "sessions": sessions}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.filename, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(name, dir_fd=directory)
            except FileNotFoundError:
                pass

    @staticmethod
    def key(sid):
        return hashlib.sha256(sid.encode()).hexdigest()

    def session(self, sid):
        if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", sid):
            return None
        with self._locked() as directory:
            sessions = self._read(directory)
            row = sessions.get(self.key(sid)) or self.temporary.get(self.key(sid))
            return dict(row) if row and row["expires"] > self.clock() else None

    def issue(self, days=0, replacing=None):
        remember_days(days)
        with self._locked() as directory:
            now = self.clock()
            sessions = {k: v for k, v in self._read(directory).items() if v["expires"] > now}
            temporary = {k: v for k, v in self.temporary.items() if v["expires"] > now}
            if replacing:
                key = self.key(replacing)
                if key not in sessions and key not in temporary:
                    raise Refusal("Browser session expired; sign in again")
                sessions.pop(key, None)
                temporary.pop(key, None)
            if len(sessions) + len(temporary) >= 32:
                raise Refusal("Local session limit reached; revoke browser sessions before pairing another browser")
            sid = secrets.token_urlsafe(32)
            row = {"csrf": secrets.token_urlsafe(32), "created": now,
                   "expires": now + (days * 86400 if days else 8 * 3600), "days": days}
            (sessions if days else temporary)[self.key(sid)] = row
            self._write(directory, sessions)
            self.temporary = temporary
            return sid, row

    def revoke(self, sid, all_browsers=False):
        with self._locked() as directory:
            sessions = self._read(directory)
            sessions.pop(self.key(sid), None)
            self._write(directory, {} if all_browsers else sessions)
            if all_browsers:
                self.temporary.clear()
            else:
                self.temporary.pop(self.key(sid), None)

    def cookie_header(self, sid, row=None):
        seconds = max(0, int(row["expires"] - self.clock())) if row else 0
        return f"{self.cookie}={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={seconds}"

    @staticmethod
    def public(row):
        return {"csrf": row["csrf"], "remembered": bool(row["days"]),
                "rememberDays": row["days"], "expiresAt": row["expires"]}
