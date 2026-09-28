"""Fail-closed local worktree evidence for opt-in cooperative producer tasks.

The designated brain supplies a separate, fresh native thread/read metadata
observation. Git checks independently establish the linked worktree, revision,
branch and exact committed source scope. Neither observation is host attestation
or permission to create a task; standard.py retains the one-shot effect boundary.
"""
from pathlib import Path, PurePosixPath
import re
import stat
import time
import unicodedata

from .core import digest, require, safe_relative
from .resources import git_metadata
from .source_observation import (branch_ref, check_objects, commit_tree, git_read,
                                 changes, inspect_base, inspect_source, layout, object_view,
                                 oid, ref_value)

MODE = "isolated_worktrees"
DEFAULT = "repo_exclusive"
NATIVE_AGE = 120
MAX_HISTORY_COMMITS = 80


def repository_mode(run):
    return run["limits"].get("repositoryMode", DEFAULT)


def resource_key(root):
    common = Path(git_metadata(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve(strict=True)
    info = common.stat()
    return "repo-local:" + digest({"device": info.st_dev, "inode": info.st_ino})


def start_commit(root):
    value = oid(git_metadata(root, "rev-parse", "--verify", "HEAD"))
    inspect_base(root, resource_key(root), value)
    return value


def exact_files(root, paths):
    """No globs, aliases, symlink ancestors or directory-wide producer scopes."""
    require(isinstance(paths, list) and paths, "Exact producer files required")
    canonical = Path(root).resolve(strict=True)
    names = []
    for path in paths:
        safe_relative(path)
        require(isinstance(path, str) and len(path) <= 500 and
                PurePosixPath(path).as_posix() == path and
                unicodedata.normalize("NFC", path) == path and
                all(p not in ("", ".", "..") for p in path.split("/")) and
                not any(c in path for c in "*?[]\n\r\x00"),
                "Producer scope needs exact repository-relative files")
        current = canonical
        for index, part in enumerate(path.split("/")):
            current = current / part
            if current.exists() or current.is_symlink():
                info = current.lstat()
                require(not stat.S_ISLNK(info.st_mode), "Producer scope cannot follow a symlink")
                require(stat.S_ISDIR(info.st_mode) if index < len(path.split("/"))-1 else stat.S_ISREG(info.st_mode),
                        "Producer scope must name files, not directories")
        names.append(unicodedata.normalize("NFC", path).casefold())
    require(len(set(names)) == len(names), "Duplicate or case-aliased producer files")
    return paths


def disjoint(left, right):
    return not ({unicodedata.normalize("NFC", p).casefold() for p in left} &
                {unicodedata.normalize("NFC", p).casefold() for p in right})


def _listed_worktree(source, root, branch):
    """Check Git's own linked-worktree inventory, not just a .git file."""
    raw = git_metadata(source, "worktree", "list", "--porcelain")
    rows = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        entry = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            require(key not in entry, "Ambiguous Git worktree inventory")
            entry[key] = value
        rows.append(entry)
    matching = [row for row in rows if row.get("worktree") == str(root)]
    require(len(matching) == 1 and matching[0].get("branch") == branch_ref(branch) and
            "prunable" not in matching[0] and "locked" not in matching[0] and "detached" not in matching[0],
            "Native task worktree is absent, ambiguous or not on its pinned branch")
    oid(matching[0].get("HEAD"))
    return matching[0]["HEAD"]


def verify_worktree(source, task, value, *, fresh_native):
    """Check separate native metadata against a registered linked Git worktree."""
    require(isinstance(value, dict), "Worktree identity required")
    require(set(value) == {"root", "branch", "startCommit", "nativeObservation", "nativeCreation"},
            "Unexpected worktree identity fields")
    root_text = value["root"]
    require(isinstance(root_text, str) and 0 < len(root_text) <= 4096 and Path(root_text).is_absolute(),
            "Absolute native worktree required")
    root = Path(root_text)
    require(root == root.resolve(strict=True) and root != Path(source).resolve(strict=True),
            "A distinct canonical native worktree is required")
    require(root.is_dir() and (root / ".git").is_file(), "A linked native Git worktree is required")
    branch_ref(value["branch"]); oid(value["startCommit"])
    creation = value["nativeCreation"]
    require(isinstance(creation, dict) and set(creation) ==
            {"projectId", "environment", "startingCommit", "seedHash", "threadId", "hostId"},
            "Exact one-shot native creation request/result record required")
    require(creation["environment"] == "worktree" and creation["startingCommit"] == task["startCommit"] and
            creation["seedHash"] == task["seedHash"] and
            creation["threadId"] == task["threadId"] and creation["hostId"] == task["hostId"] == "local" and
            creation["projectId"] == task["nativeProjectId"],
            "Native worktree creation does not match the pinned request and result")
    observation = value["nativeObservation"]
    require(isinstance(observation, dict) and set(observation) ==
            {"threadId", "hostId", "cwd", "observedAt", "sourceHash"},
            "Exact native thread/read observation required")
    require(observation["threadId"] == task["threadId"] and observation["hostId"] == task["hostId"] == "local" and
            observation["cwd"] == str(root), "Native task and worktree association is unverified")
    require(isinstance(observation["sourceHash"], str) and re.fullmatch(r"[a-f0-9]{64}", observation["sourceHash"]),
            "Native metadata source hash required")
    observed = observation["observedAt"]
    require(type(observed) in (int, float) and observed > 0 and
            (not fresh_native or 0 <= time.time()-observed < NATIVE_AGE),
            "Native task/worktree observation is stale")
    require(value["startCommit"] == task["startCommit"], "Worktree starts from a different pinned commit")
    require(git_metadata(root, "rev-parse", "--show-toplevel") == str(root) and
            resource_key(root) == resource_key(source), "Worktree belongs to a different repository")
    common, objects, pin = layout(root, resource_key(source))
    gitdir = Path(git_metadata(root, "rev-parse", "--path-format=absolute", "--git-dir")).resolve(strict=True)
    require(gitdir.parent == common / "worktrees", "Git directory is not a registered linked worktree")
    head = _listed_worktree(source, root, value["branch"])
    require(ref_value(common, branch_ref(value["branch"])) == head, "Worktree branch changed")
    check_objects(objects)
    with object_view(objects) as view:
        commit_tree(view, value["startCommit"])
        commit_tree(view, head)
        git_read(view, ["merge-base", "--is-ancestor", value["startCommit"], head], bound=0)
    require(layout(root, resource_key(source))[2] == pin and
            _listed_worktree(source, root, value["branch"]), "Worktree changed during verification")
    return {"root": str(root), "branch": value["branch"], "startCommit": value["startCommit"],
            "layoutHash": pin, "headAtObservation": head, "nativeObservedAt": observed,
            "nativeSourceHash": observation["sourceHash"], "nativeSource": "codex_thread_read_supplied",
            "nativeCreation": creation,
            "verifiedAt": time.time()}


def source_proof(source, task, head):
    """Verify committed changes from this task's exact pinned worktree."""
    binding = task.get("worktree")
    require(binding is not None, "Confirmed native worktree binding required")
    value = {"root": binding["root"], "branch": binding["branch"],
             "startCommit": binding["startCommit"],
             "nativeCreation": binding["nativeCreation"],
             "nativeObservation": {"threadId": task["threadId"], "hostId": task["hostId"],
                                   "cwd": binding["root"], "observedAt": binding["nativeObservedAt"],
                                   "sourceHash": binding["nativeSourceHash"]}}
    verify_worktree(source, task, value, fresh_native=True)
    oid(head)
    allowed = set(task["paths"])
    if task["taskKind"] == "integration":
        allowed.update(path for producer in task["producerSources"] for path in producer["paths"])
    report = inspect_source(binding["root"], resource_key(source), binding["startCommit"], head,
                            binding["branch"], sorted(allowed))
    report["historyScope"] = committed_history_scope(source, binding, head, allowed)
    if task["taskKind"] == "producer":
        require(report["changedPaths"] and set(report["changedPaths"]) <= set(task["paths"]),
                "Producer committed changes exceed exact-file scope")
    else:
        require(report["changedPaths"] and set(report["changedPaths"]) <= allowed,
                "Integration changed files outside pinned producer and integration exact-file scopes")
    return report


def committed_history_scope(source, binding, head, allowed):
    """Inspect every reachable commit edge, so a reverted bad commit is not hidden.

    Merge commits are checked against each parent and their side-branch commits
    are included by rev-list. Histories outside the bounded adapter refuse.
    """
    started = time.monotonic()
    root = binding["root"]
    key = resource_key(source)
    common, objects, pin = layout(root, key)
    check_objects(objects)
    checked = []
    with object_view(objects) as view:
        raw = git_read(view, ["rev-list", "--parents", "--topo-order",
                              binding["startCommit"] + ".." + head], bound=65536)
        lines = raw.decode("ascii").splitlines()
        require(0 < len(lines) <= MAX_HISTORY_COMMITS,
                "Committed history exceeds the bounded exact-scope verifier")
        seen = set()
        for line in lines:
            require(time.monotonic()-started < 25, "Committed history verification timed out")
            commits = line.split(" ")
            require(2 <= len(commits) <= 3 and all(oid(value) for value in commits),
                    "Unsupported root or octopus merge in producer history")
            commit, parents = commits[0], commits[1:]
            for value in commits:
                if value not in seen:
                    commit_tree(view, value)
                    seen.add(value)
            for parent in parents:
                delta_raw = git_read(view, ["diff-tree", "--no-commit-id", "--no-ext-diff", "--no-textconv",
                                            "--no-renames", "--no-abbrev", "-r", "--raw", "-z",
                                            parent, commit, "--"], bound=65536)
                delta = changes(delta_raw) if delta_raw else []
                paths = [row["path"] for row in delta]
                require(set(paths) <= allowed,
                        "An out-of-scope committed change was hidden by later history")
                checked.append({"commit": commit, "parent": parent, "paths": paths})
    require(layout(root, key)[2] == pin and
            ref_value(common, branch_ref(binding["branch"])) == head,
            "Worktree changed during committed-history verification")
    return {"commitsChecked": len(lines), "parentDiffsChecked": len(checked),
            "historyDigest": digest(checked), "bounded": True}


def integrated(source, task, report, producer_heads):
    """An integration head must include every pinned producer commit."""
    require(task["taskKind"] == "integration" and producer_heads, "Pinned producer commits required")
    _, objects, _ = layout(task["worktree"]["root"], resource_key(source))
    check_objects(objects)
    with object_view(objects) as view:
        for head in producer_heads:
            oid(head)
            commit_tree(view, head)
            git_read(view, ["merge-base", "--is-ancestor", head, report["commit"]], bound=0)
    return True
