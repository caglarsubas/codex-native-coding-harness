"""Read-only Git measurements and packet preparation; never executes repo code."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from .core import Refusal, canonical, require, safe_relative, validate_seed
from . import portfolio_metrics

EXCLUDED = {"node_modules", "vendor", "dist", "build", "coverage", ".git", ".venv", "__pycache__", "generated"}
LOCKS = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "uv.lock", "requirements.lock", "Cargo.lock", "poetry.lock"}
SOURCE = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".cs", ".swift", ".rb", ".sh", ".css", ".html", ".sql", ".vue", ".svelte"}


def git_environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1", LC_ALL="C")
    return env


def git(path, *args, binary=False):
    require(path and Path(path).is_dir(), "Repository not present on disk")
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", str(path), *args],
        capture_output=True, timeout=60, check=False, env=git_environment())
    require(result.returncode == 0, "Git read failed: " + result.stderr.decode(errors="replace")[:300])
    return result.stdout if binary else result.stdout.decode().strip()


def head(path, ref):
    require(isinstance(ref, str) and ref and not ref.startswith("-"), "Invalid Git reference")
    return git(path, "rev-parse", "--verify", ref + "^{commit}")


def blob(path, commit, relative):
    safe_relative(relative)
    return git(path, "show", f"{commit}:{relative}", binary=True)


def measure(repo):
    stamp = time.time()
    result = {"schemaVersion": 1, "repository": repo["id"], "at": stamp, "commit": None,
        "status": "unavailable", "reason": None, "groups": {}, "files": 0, "lines": 0,
        "characters": 0, "bytes": 0, "excluded": 0, "binary": 0, "sessions": None,
        "messages": None, "tokens": None, "cacheRate": None, "modelEffort": None,
        "methodology": "Tracked UTF-8 text at configured ref; Unicode code points and physical lines, including blanks/comments. No worktree or untracked files. Excludes vendor/build/generated directories, lockfiles, symlinks, binaries and files over 2 MiB. Not SLOC or coverage."}
    try:
        identity = portfolio_metrics.observe_identity(repo)
        commit = head(repo["path"], repo["ref"])
        result["commit"] = commit
        entries = git(repo["path"], "ls-tree", "-r", "-l", "-z", commit, binary=True).split(b"\0")
        selected = []
        for entry in entries:
            if not entry:
                continue
            metadata, filename = entry.split(b"\t", 1)
            mode, kind, oid, size = metadata.split()
            path = Path(filename.decode("utf-8", errors="replace"))
            if kind != b"blob" or mode == b"120000" or any(p in EXCLUDED for p in path.parts) or path.name in LOCKS or int(size) > 2 * 1024 * 1024:
                result["excluded"] += 1
                continue
            selected.append((oid.decode(), path))
        # Batch reads use immutable blob IDs; no checked-out file or symlink is opened.
        require(sum(int(e.split(b"\t")[0].split()[-1]) for e in entries if e and e.split(b"\t")[0].split()[1] == b"blob") < 512 * 1024 * 1024, "Tree too large for bounded metrics scan")
        output = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-C", repo["path"], "cat-file", "--batch"],
            input="".join(oid + "\n" for oid, _ in selected).encode(), capture_output=True, timeout=120, check=True,
            env=git_environment()).stdout
        offset = 0
        for _, path in selected:
            end = output.index(b"\n", offset)
            size = int(output[offset:end].split()[-1])
            raw = output[end + 1:end + 1 + size]
            offset = end + 2 + size
            try:
                require(b"\0" not in raw, "Binary")
                text = raw.decode("utf-8")
            except (UnicodeError, Refusal):
                result["binary"] += 1
                continue
            group = "tests" if any(x in ("tests", "test", "__tests__") for x in path.parts) or path.name.startswith("test_") or ".test." in path.name or ".spec." in path.name else "docs" if path.suffix.lower() in (".md", ".rst", ".txt") else "source" if path.suffix.lower() in SOURCE else "config/data"
            values = {"files": 1, "lines": len(text.splitlines()), "characters": len(text), "bytes": len(raw)}
            target = result["groups"].setdefault(group, {key: 0 for key in values})
            for key, value in values.items():
                target[key] += value
                result[key] += value
        after = portfolio_metrics.observe_identity(repo)
        if after != identity:
            identity = {**identity, "status": "unavailable"}
        result.update(status="measured", identity=identity, measurementPolicy=portfolio_metrics.POLICY)
    except (Refusal, subprocess.SubprocessError, OSError, ValueError) as error:
        result["reason"] = str(error)
        result["groups"] = {}
        for key in ("files", "lines", "characters", "bytes", "excluded", "binary"):
            result[key] = None
    return result


def prepare_packet(catalog, repo, manifest):
    """Read packet data at an immutable commit. User-supplied approvals are separate."""
    try:
        import yaml
    except ImportError as error:
        raise Refusal("PyYAML is not installed; no runtime download is allowed") from error
    required = {"packetPath", "catalogCommit", "baseSHA", "rationale", "predecessors", "locks", "completionAxes"}
    require(set(manifest) == required, "Invalid preparation manifest")
    commit = head(catalog, manifest["catalogCommit"])
    require(commit == manifest["catalogCommit"], "Pin exact catalog commit")
    raw = blob(catalog, commit, manifest["packetPath"])
    packet = yaml.safe_load(raw)
    require(packet["repository"] == repo["id"], "Packet belongs to another repository")
    require(set(packet.get("predecessors", [])) == {d["packetId"] for d in manifest["predecessors"]}, "Every predecessor needs pinned evidence")
    # Provenance fields/sourceReuse are intentionally not copied into worker context.
    ex = packet.get("offlineExecution", {})
    seed = {"schemaVersion": 1, "repository": repo["id"], "policyProfile": repo["policyProfile"],
        "packetId": packet["id"], "packetDigest": hashlib.sha256(raw).hexdigest(),
        "packetPath": manifest["packetPath"], "catalogCommit": commit, "baseSHA": manifest["baseSHA"],
        "branch": packet["branch"], "objective": packet["objective"], "rationale": manifest["rationale"],
        "allowedPaths": packet["allowedPaths"], "contracts": packet["contracts"], "predecessors": manifest["predecessors"],
        "locks": manifest["locks"], "execution": {"wrapperArgv": ex["wrapperArgv"],
            "prefetchCommands": packet.get("prefetchCommands", []), "offlineAcceptanceCommands": packet["offlineAcceptanceCommands"],
            "isolation": ex["isolation"]}, "acceptance": packet.get("expectedEvidence", packet.get("deliverables", [])),
        "stopConditions": ["Packet, base, lock or ownership mismatch", "Missing authority, unavailable isolation or runner",
            "Public contract, tenant isolation, destructive data, licensing, privileges or billing decision"],
        "completionAxes": manifest["completionAxes"]}
    validate_seed(seed)
    return seed


def verify_git_inputs(catalog, repo, seed):
    """Recheck bytes and current base. Does not assert predecessor acceptance."""
    require(head(repo["path"], repo["ref"]) == seed["baseSHA"], "Configured base SHA changed")
    raw = blob(catalog, seed["catalogCommit"], seed["packetPath"])
    require(hashlib.sha256(raw).hexdigest() == seed["packetDigest"], "Pinned packet bytes differ")
    current = blob(catalog, head(catalog, "origin/main"), seed["packetPath"])
    require(hashlib.sha256(current).hexdigest() == seed["packetDigest"], "Current catalog packet changed")
    for lock in seed["locks"]:
        raw = blob(catalog, seed["catalogCommit"], lock["path"])
        require(hashlib.sha256(raw).hexdigest() == lock["sha256"], "Source lock digest differs")
    return {"packetCurrent": True, "baseCurrent": True, "locksVerified": True}


def aggregate(state):
    code = portfolio_metrics.summarize(portfolio_metrics.candidates(state))
    totals = code["aggregate"]
    completed = [w for w in state["workers"] if w["status"] == "complete"]
    cycles = [w["completedAt"] - w["createdAt"] for w in completed]
    totals.update(repositoryCount=len(state["repositories"]), managedTasks=len(state["workers"]), completedPackets=len(completed),
        meanCycleSeconds=sum(cycles) / len(cycles) if cycles else None)
    tasks = (state.get("meta", {}).get("standardRun") or {}).get("tasks", [])
    totals.update(cooperativeTasks=len(tasks), cooperativeCompletedTasks=sum(t["status"] == "completed" for t in tasks))
    return {**code, "aggregate": totals, "delivery": state.get("delivery"), "usage": state.get("observations", {}).get("usage") or {"status": "unavailable",
        "reason": "No validated per-task usage source connected. Model/effort, tokens, cache, messages and historical sessions are not inferred from task counts."}}


def report(state):
    metrics = aggregate(state)
    text = ["# Codex Orchestrator — portfolio snapshot", "", f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"Ledger revision: {state['meta']['revision']}. Dispatch paused: {state['meta']['paused']}.", "",
        "## Aggregate", "", "```json", json.dumps(metrics["aggregate"], indent=2), "```", "",
        "## Counting coverage", "", metrics["method"], "", "```json", json.dumps(metrics["coverage"], indent=2), "```", "",
        "## Repository distribution", "", "| Repository | Commit | Status | Files | Lines | Characters | Counting |", "|---|---|---|---:|---:|---:|---|"]
    for m in metrics["repositories"]:
        measured = m["status"] == "measured"
        text.append(f"| {m['repository']} | {(m['commit'] or '—')[:12]} | {m['status']} | {m['files'] if measured else '—'} | {m['lines'] if measured else '—'} | {m['characters'] if measured else '—'} | {m['counting']['status']} |")
    if state.get("delivery"):
        text += ["", "## Managed delivery", "", "| Repository | Tasks | Completed in 7 days | Blocked minutes | Runner wait minutes | No-progress cycles |", "|---|---:|---:|---:|---:|---:|"]
        for row in state["delivery"]["repositories"]:
            text.append(f"| {row['repository']} | {row['tasks']} | {row['completedLast7Days']} | {row['blockedSeconds']/60:.1f} | {row['runnerWaitSeconds']/60:.1f} | {row['noProgressCycles']} |")
    observations = state.get("observations", {})
    for title, value in (("Local token usage", observations.get("usage")), ("Git and pull requests", observations.get("git")), ("Artifact versions", observations.get("artifacts")), ("Roadmap checklist", observations.get("roadmaps")), ("Executive brief (advisory snapshot, not current verification)", observations.get("executive"))):
        if value:
            text += ["", "## " + title, "", "```json", json.dumps(value, indent=2, ensure_ascii=False), "```"]
    text += ["", "## Method and limitations", "", "Counts cover tracked UTF-8 text at exact commits, including blank/comment lines; they are not executable SLOC. Vendor/build/generated directories, lockfiles, binaries, symlinks and files over 2 MiB are excluded. Untracked work is not counted. Clones/worktrees at the same identified commit count once; different commits remain separate snapshots. Missing or unqualified measurements are unavailable, not zero.", "", metrics["usage"]["reason"], "", "No API-equivalent cost is a subscription bill. Model/effort comparisons require measured, comparable tasks and do not establish causation. Artifact dates distinguish supplied creation dates, first references and observation times. Checklist states are recorded source claims, never dispatch or acceptance authority.", "", "## Brain checkpoint", "", state["meta"]["checkpoint"], ""]
    return "\n".join(text)
