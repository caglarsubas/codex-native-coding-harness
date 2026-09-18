"""Process-start source observation, not a deployment or loaded-memory attestation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.parse import quote

from .core import COMMIT, Refusal, require
from .observations import read_regular

FRESH_SECONDS = 900
RUNTIME_PATHS = ("orchestrator", "web", "pyproject.toml")


def git(root, *args):
    result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        capture_output=True, timeout=10, check=True)
    return result.stdout


def fingerprint(root):
    # No credentials, ignored files, transcripts or arbitrary operator paths.
    paths = set(git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *RUNTIME_PATHS).decode().split("\0"))
    paths = sorted(p for p in paths if p and Path(p).suffix in (".py", ".js", ".css", ".html", ".toml")
        and not any(part.startswith(".") for part in Path(p).parts))
    require(0 < len(paths) <= 256, "Runtime source unavailable or exceeds inspection limit")
    result, total = hashlib.sha256(), 0
    for name in paths:
        path = root / name
        if not path.exists() and not path.is_symlink():
            raw, marker = b"", b"deleted\0"
        else:
            raw = read_regular(path, root, 2 * 1024 * 1024)
            marker = b"present\0"
        total += len(raw)
        require(total <= 16 * 1024 * 1024, "Runtime source exceeds inspection limit")
        result.update(name.encode() + b"\0" + marker + hashlib.sha256(raw).digest())
    return result.hexdigest()


def inspect(root):
    root = Path(root).resolve()
    result = {"at": time.time(), "status": "unavailable", "commit": None, "dirty": None,
        "fingerprint": None, "githubRepository": None}
    try:
        require(Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() == root, "Exact Git root required")
        commit = git(root, "rev-parse", "--verify", "HEAD").decode().strip()
        require(COMMIT.fullmatch(commit), "Commit unavailable")
        def status():
            return git(root, "status", "--porcelain=v1", "-z", "--untracked-files=normal", "--ignore-submodules=all")
        before = status()
        source_hash = fingerprint(root)
        require(source_hash == fingerprint(root) and before == status()
            and commit == git(root, "rev-parse", "--verify", "HEAD").decode().strip(), "Checkout changed during inspection")
        result.update(status="observed", commit=commit, dirty=bool(before), fingerprint=source_hash)
        try:
            origin = git(root, "remote", "get-url", "origin").decode().strip()
            match = re.fullmatch(r"(?:git@github.com:|https://github.com/)([\w.-]+/[\w.-]+?)(?:\.git)?", origin)
            if match:
                result["githubRepository"] = match[1]
        except (OSError, subprocess.SubprocessError, UnicodeError):
            pass  # A GitHub origin is optional for local runtime inspection.
    except (OSError, subprocess.SubprocessError, ValueError):
        result["reason"] = "Cannot verify a stable, bounded runtime source snapshot at the exact Git root."
    return result


def remote_revision(repository):
    result = {"at": time.time(), "status": "unavailable", "repository": repository,
        "branch": None, "commit": None}
    try:
        require(isinstance(repository, str) and re.fullmatch(r"[\w.-]+/[\w.-]+", repository), "GitHub origin required")
        def get(endpoint):
            response = subprocess.run(["gh", "api", "--method", "GET", "repos/" + repository + endpoint],
                capture_output=True, timeout=20, check=True)
            require(len(response.stdout) <= 1024 * 1024, "Oversized remote metadata")
            return json.loads(response.stdout)
        branch = get("")["default_branch"]
        require(isinstance(branch, str) and 0 < len(branch) <= 250, "Invalid default branch")
        ref = get("/git/ref/heads/" + quote(branch, safe=""))
        commit = ref["object"]["sha"]
        require(ref["ref"] == "refs/heads/" + branch and ref["object"]["type"] == "commit"
            and isinstance(commit, str) and COMMIT.fullmatch(commit), "Invalid branch commit")
        result.update(status="observed", branch=branch, commit=commit)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError):
        result["reason"] = "GitHub revision unavailable. Check the configured origin, gh authentication and network; no fetch or mutation was attempted."
    return result


class Provenance:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.started_at = time.time()
        self.startup = inspect(self.root)
        self.current = deepcopy(self.startup)
        self.remote = {"status": "not_requested", "at": None, "repository": None, "branch": None, "commit": None}
        self.lock = threading.Lock()

    def refresh(self, remote=False):
        current = inspect(self.root)
        observed = remote_revision(current["githubRepository"]) if remote else None
        with self.lock:
            self.current = current
            if observed is not None:
                self.remote = observed  # Failed refresh must not present old success as current.

    def snapshot(self):
        with self.lock:
            start, current, remote = deepcopy((self.startup, self.current, self.remote))
        now = time.time()
        fresh = lambda at: at is not None and 0 <= now - at <= FRESH_SECONDS
        local_fresh = fresh(current["at"])
        status, restart = "unknown", None
        if start["status"] == current["status"] == "observed" and local_fresh:
            if start["fingerprint"] != current["fingerprint"]:
                status, restart = "source_changed", True
            elif start["commit"] != current["commit"]:
                status, restart = "revision_changed", True
            elif start["dirty"] or current["dirty"]:
                status = "unverified_workspace"
            else:
                status, restart = "matching_snapshot", False
        remote_fresh = remote["status"] == "observed" and fresh(remote["at"])
        same_origin = bool(current["githubRepository"]) and current["githubRepository"] == remote["repository"]
        comparable = remote_fresh and same_origin and current["status"] == "observed" and local_fresh
        def match(record):
            return record["commit"] == remote["commit"] if comparable and record["status"] == "observed" and record["dirty"] is False and record["githubRepository"] == remote["repository"] else None
        return {"startedAt": self.started_at, "startup": start, "current": current, "remote": remote,
            "status": status, "restartRecommended": restart, "localFresh": local_fresh, "remoteFresh": remote_fresh,
            "remoteComparable": bool(comparable), "startupMatchesRemote": match(start), "checkoutMatchesRemote": match(current),
            "limits": "Server-start checkout observation, not a loaded-memory or deployment attestation. Python can import lazily and web assets are served from disk. Runtime hashes cover bounded first-party Python/web files and pyproject.toml, not dependencies or environment. Polling never scans, fetches, restarts or changes controller authority."}
