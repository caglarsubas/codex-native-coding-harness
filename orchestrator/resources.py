"""Explicit, read-only Git identity observation and cross-workspace owner audit.

No network, checkout, fetch, hooks, source reads or ownership changes. A diagnostic
snapshot is not a lock, and literal remote identity is not a verified host alias.
"""
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from .core import ACTIVE, Refusal, digest, require


def remote_key(value):
    """Normalize conventional network remotes; refuse credentials/ambiguous syntax.

    GitHub's owner/repository names are case-insensitive. Other path case stays
    significant. Non-default ports are not equated across protocols. Host aliases,
    insteadOf rewrites, redirects and local-file remotes need future explicit mapping.
    """
    require(isinstance(value, str) and 0 < len(value) <= 2048 and not any(c.isspace() for c in value),
            "Remote identity unavailable")
    require(not any(c in value for c in ("%", "?", "#", "\\")), "Ambiguous remote identity")
    if "://" not in value:
        match = re.fullmatch(r"git@([A-Za-z0-9.-]+):([^:]+)", value)
        require(match is not None, "Unsupported remote identity; explicit mapping required")
        host, path, port = match[1].lower(), match[2], None
    else:
        try:
            parsed = urlsplit(value)
            require(parsed.scheme in ("https", "http", "ssh") and parsed.hostname is not None,
                    "Unsupported remote identity; explicit mapping required")
            require(parsed.password is None and (parsed.username is None or
                    (parsed.scheme == "ssh" and parsed.username == "git")), "Credential-bearing or ambiguous remote refused")
            require(parsed.path.startswith("/") and not parsed.path.startswith("//"), "Ambiguous remote path")
            host, path, port = parsed.hostname.lower(), parsed.path[1:], parsed.port
            default = {"https": 443, "http": 80, "ssh": 22}[parsed.scheme]
            if port == default:
                port = None
            elif port is not None:
                # Port 443 on SSH is not necessarily the HTTPS repository service.
                host = parsed.scheme + ":" + host
        except ValueError as error:
            raise Refusal("Invalid remote identity") from error
    require("." in host and not host.endswith(".") and not path.startswith("/") and "//" not in path,
            "Host alias or ambiguous remote path needs explicit mapping")
    if host == "github.com":
        path = path.lower()
    path = path.removesuffix("/").removesuffix(".git")
    require(path and all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in (".", "..") for part in path.split("/")),
            "Unsupported remote path")
    if host == "github.com":
        require(len(path.split("/")) == 2, "Invalid GitHub repository path")
        path = path.lower()
    return "repo-remote:" + digest({"host": host, "port": port, "path": path})


def git_metadata(path, *args):
    # Ignore inherited Git targeting and global/system includes or URL rewrites.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
    # Never capture stderr (it could contain a credential-bearing URL). Bound data
    # read into memory even if an untrusted local config returns enormous output.
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(["git", "--no-optional-locks", "-C", str(path), *args],
                                env=env, stdout=output, stderr=subprocess.DEVNULL, timeout=3, check=False)
        output.seek(0)
        data = output.read(8193)
    require(result.returncode == 0 and len(data) <= 8192, "Required Git metadata unavailable")
    return data.decode("utf-8", errors="strict").strip()


def repository_identity(path):
    keys = []
    try:
        root = Path(path)
        require(root.is_absolute(), "Explicit absolute checkout path required")
        root = root.resolve(strict=True)
        common = git_metadata(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        common_path = Path(common)
        require(common_path.is_absolute() and common_path.is_dir(), "Git common directory unavailable")
        stat = common_path.resolve(strict=True).stat()
        keys.append("repo-local:" + digest({"device": stat.st_dev, "inode": stat.st_ino}))
        # get-all detects ambiguous multiple origins, rather than choosing one.
        origin = git_metadata(root, "config", "--local", "--no-includes", "--get-all", "remote.origin.url")
        require(len(origin.splitlines()) == 1, "Multiple origin URLs need explicit mapping")
        keys.append(remote_key(origin))
        return {"status": "observed", "keys": sorted(keys), "reason": None}
    except (ValueError, TypeError, OSError, subprocess.SubprocessError):
        # Keep any established local key to detect worktree conflicts, but do not
        # treat partial identity as safe cross-clone admission. No paths/URLs leak.
        return {"status": "unknown", "keys": keys, "reason": "Canonical identity incomplete; explicit mapping or metadata recovery required."}


def audit(registry):
    """Explicit inventory, no global point-in-time/transactional admission claim."""
    started = time.time()
    workspaces, repos, owners, problems = [], [], [], []
    rows = registry.list()
    require(len(rows) <= 32, "Resource audit is limited to 32 workspaces")
    for row in rows:
        wid = row["id"]
        try:
            state = registry.ledger(wid).snapshot()
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            problems.append({"workspaceId": wid, "code": "ledger_unavailable"})
            continue
        workspaces.append({"workspaceId": wid, "ledgerRevision": state["meta"]["revision"]})
        identities = {}
        for repo in state["repositories"]:
            if len(repos) >= 100 or time.time() - started > 25:
                observed = {"status": "unknown", "keys": [], "reason": "Audit bound reached; not inspected."}
            else:
                observed = repository_identity(repo["path"])
            identities[repo["id"]] = observed
            repos.append({"workspaceId": wid, "repositoryId": repo["id"], **observed})
            if observed["status"] != "observed":
                problems.append({"workspaceId": wid, "repositoryId": repo["id"], "code": "identity_unknown"})
        for worker in state["workers"]:
            if worker["status"] not in ACTIVE:
                continue
            observed = identities.get(worker["repository"], {"status": "unknown", "keys": []})
            owners.append({"workspaceId": wid, "workerId": worker["id"], "repositoryId": worker["repository"],
                           "status": worker["status"], "resourceKeys": observed["keys"],
                           "native": {"hostId": worker.get("hostId"), "threadId": worker.get("threadId")},
                           "runnerRecorded": (state["meta"].get("runner") or {}).get("workerId") == worker["id"]})
            if observed["status"] != "observed":
                problems.append({"workspaceId": wid, "workerId": worker["id"], "code": "owner_identity_unknown"})
        if state["meta"].get("runner"):
            # Legacy runner ownership has no global operator ID; never guess that
            # two workspaces' runner labels name separate hardware.
            problems.append({"workspaceId": wid, "code": "runner_global_identity_unknown"})
    groups = {}
    for repo in repos:
        for key in repo["keys"]:
            groups.setdefault(key, []).append({"workspaceId": repo["workspaceId"], "repositoryId": repo["repositoryId"]})
    conflicts = []
    for index, owner in enumerate(owners):
        for other in owners[index + 1:]:
            shared = sorted(set(owner["resourceKeys"]) & set(other["resourceKeys"]))
            same_native = bool(owner["native"].get("threadId")) and owner["native"] == other["native"]
            if shared or same_native:
                conflicts.append({"owners": [{k: v[k] for k in ("workspaceId", "workerId")} for v in (owner, other)],
                                  "sharedResourceKeys": shared, "duplicateNativeTask": same_native})
    return {"schemaVersion": 1, "observedAt": time.time(), "executionAuthorized": False,
            "atomicSnapshot": False, "dispatchIntegrated": False, "workspaces": workspaces,
            "repositories": repos, "owners": owners, "conflicts": conflicts, "issues": problems,
            "aliases": [{"key": key, "repositories": refs} for key, refs in sorted(groups.items()) if len(refs) > 1],
            "coverage": "Registered local ledgers and conventional literal origin identities only; unmanaged tasks, host aliases and external runner occupancy are not verified."}
