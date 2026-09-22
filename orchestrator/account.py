"""One local administrator, owner-only scrypt verifier and durable throttling."""
from contextlib import contextmanager
import fcntl
import getpass
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import time

from .browser_auth import BrowserAuth
from .core import Refusal

UNAVAILABLE = "Local account storage is unavailable or changed. Ask the local operator to check it and restart the backend."


class Throttled(Refusal):
    pass


def password_hash(password, salt):
    # OWASP's standard-library-compatible scrypt profile; one verification at a time.
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**17,
                          r=8, p=1, maxmem=256 * 1024 * 1024, dklen=64).hex()


class LocalAccount:
    def __init__(self, path, clock=time.time):
        self.path = Path(path).absolute()
        self.clock = clock
        with self.locked() as directory:
            self.identity = self.identity_of(self.read(directory))

    @contextmanager
    def locked(self):
        try:
            if self.path != self.path.resolve():
                raise Refusal(UNAVAILABLE)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                info = os.fstat(directory)
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise Refusal(UNAVAILABLE)
                fd = os.open(self.path.name + ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
                try:
                    BrowserAuth._check_file(fd)
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    yield directory
                finally:
                    os.close(fd)
            finally:
                os.close(directory)
        except Refusal:
            raise
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise Refusal(UNAVAILABLE) from error

    def read(self, directory):
        fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd) as stream:
            BrowserAuth._check_file(stream.fileno())
            if os.fstat(stream.fileno()).st_size > 4096:
                raise Refusal(UNAVAILABLE)
            row = json.load(stream)
        if not isinstance(row, dict) or set(row) != {"version", "username", "salt", "verifier", "failures", "blockedUntil"}:
            raise Refusal(UNAVAILABLE)
        if type(row["version"]) is not int or row["version"] != 1:
            raise Refusal(UNAVAILABLE)
        if not isinstance(row["username"], str) or not 1 <= len(row["username"]) <= 254 or row["username"] != row["username"].strip().casefold():
            raise Refusal(UNAVAILABLE)
        for key, size in (("salt", 32), ("verifier", 128)):
            if not isinstance(row[key], str) or not re.fullmatch(f"[0-9a-f]{{{size}}}", row[key]):
                raise Refusal(UNAVAILABLE)
        if type(row["failures"]) is not int or not 0 <= row["failures"] <= 5:
            raise Refusal(UNAVAILABLE)
        if type(row["blockedUntil"]) not in (int, float) or not math.isfinite(row["blockedUntil"]) or row["blockedUntil"] < 0:
            raise Refusal(UNAVAILABLE)
        return row

    @staticmethod
    def identity_of(row):
        return hashlib.sha256(json.dumps({k: row[k] for k in ("version", "username", "salt", "verifier")}, sort_keys=True).encode()).hexdigest()

    def write(self, directory, row):
        name = self.path.name + "." + secrets.token_hex(8) + ".tmp"
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(row, stream); stream.flush(); os.fsync(stream.fileno())
            os.replace(name, self.path.name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try: os.unlink(name, dir_fd=directory)
            except FileNotFoundError: pass

    def checked(self, directory):
        row = self.read(directory)
        if self.identity_of(row) != self.identity:
            raise Refusal(UNAVAILABLE)
        return row

    def ensure_current(self):
        with self.locked() as directory:
            self.checked(directory)

    def verify(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str) or not 1 <= len(username) <= 254 or not 1 <= len(password.encode()) <= 1024:
            return False
        with self.locked() as directory:
            row = self.checked(directory)
            now = self.clock()
            if row["blockedUntil"] > now:
                raise Throttled("Too many sign-in attempts. Wait five minutes before trying again.")
            if row["blockedUntil"]:
                row.update(failures=0, blockedUntil=0)
            # Retain each attempt before hashing, including interrupted attempts.
            row["failures"] += 1
            if row["failures"] >= 5:
                row["blockedUntil"] = now + 300
            self.write(directory, row)
            candidate = password_hash(password, row["salt"])
            valid_password = hmac.compare_digest(candidate, row["verifier"])
            valid_name = hmac.compare_digest(username.strip().casefold().encode(), row["username"].encode())
            if valid_password and valid_name:
                row.update(failures=0, blockedUntil=0)
                self.write(directory, row)
                return True
            return False


def configure(path, username, password, replace=False):
    if not isinstance(username, str) or not 1 <= len(username.strip()) <= 254:
        raise Refusal("An account name is required")
    if not isinstance(password, str) or not 10 <= len(password) or len(password.encode()) > 1024:
        raise Refusal("Use a password of at least 10 characters and at most 1024 UTF-8 bytes")
    account = object.__new__(LocalAccount)
    account.path = Path(path).absolute()
    account.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with account.locked() as directory:
        if account.path.exists() or account.path.is_symlink():
            account.read(directory)  # Never overwrite an unsafe file.
            if not replace:
                raise Refusal("Account already configured; use --replace for an explicit password reset")
        salt = secrets.token_hex(16)
        account.write(directory, {"version": 1, "username": username.strip().casefold(), "salt": salt,
                                  "verifier": password_hash(password, salt), "failures": 0, "blockedUntil": 0})


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Configure one private local dashboard account; password is prompted, never an argument")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--username", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    try:
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            raise Refusal("Passwords do not match")
        configure(args.file, args.username, password, args.replace)
        print("Local account configured. Restart the backend with --account-file. Existing sessions are invalidated on reset.")
    except Refusal as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
