"""Private, read-only observations. No dispatch, repo writes or transcript storage."""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from .core import Refusal, canonical, digest, require, safe_relative
from .repository import blob, git, head, measure

TOKENS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")
EXTENSIONS = {".md", ".txt", ".json", ".csv", ".html", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".pdf", ".docx", ".xlsx", ".pptx"}
MAX_ARTIFACT = 8 * 1024 * 1024
MAX_LINE = 16 * 1024 * 1024
IMPORTER_VERSION = 2


def setup(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS observation_records (id TEXT PRIMARY KEY, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS rollout_cursors (id TEXT PRIMARY KEY, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS usage_events (id TEXT PRIMARY KEY, session TEXT NOT NULL, data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS artifact_versions (id TEXT PRIMARY KEY, data TEXT NOT NULL, content BLOB NOT NULL);
    """)


def stamp(value):
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def contained(path, root):
    try:
        if ".." in Path(path).parts or ".." in Path(root).parts:
            return False
        Path(path).absolute().relative_to(Path(root).absolute())
        return True
    except (ValueError, TypeError):
        return False


def read_regular(path, root, maximum):
    """Open beneath an explicit root, refusing symlinks at every path component."""
    path, root = Path(path).absolute(), Path(root).absolute()
    require(contained(path, root), "Path is outside the configured artifact root")
    parts = path.parts
    fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(child, "rb") as stream:
            import stat
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum, "Not a bounded regular file")
            raw = stream.read(maximum + 1)
            require(len(raw) <= maximum, "File exceeds snapshot limit")
            return raw
    finally:
        os.close(fd)


def config(ledger):
    path = ledger.root / "observations.json"
    if not path.exists():
        return {"codexHome": None, "artifactRoots": [], "roadmaps": []}
    value = json.loads(path.read_text())
    require(set(value) <= {"codexHome", "artifactRoots", "roadmaps"}, "Unknown observation setting")
    for root in value.get("artifactRoots", []):
        require(set(root) == {"repository", "path"} and Path(root["path"]).is_absolute(), "Explicit artifact roots required")
        require(len(Path(root["path"]).parts) >= 4, "Artifact root is too broad")
    return value


def save(db, key, value):
    db.execute("INSERT INTO observation_records VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (key, canonical(value)))


def event(db, session, value):
    # Duplicate archives and overlapping continuation segments collapse identically.
    db.execute("INSERT OR IGNORE INTO usage_events VALUES (?,?,?)", (digest([session, value]), session, canonical(value)))


def token_vector(value):
    if not isinstance(value, dict) or not all(type(value.get(k)) is int and value[k] >= 0 for k in TOKENS):
        return None
    if value["cached_input_tokens"] > value["input_tokens"] or value["reasoning_output_tokens"] > value["output_tokens"]:
        return None
    if value["total_tokens"] != value["input_tokens"] + value["output_tokens"]:
        return None
    return {k: value[k] for k in TOKENS}


def repository_for(cwd, aliases):
    matches = [(len(path), repo) for path, repo in aliases.items() if cwd and contained(cwd, path)]
    return max(matches)[1] if matches else None


def ingest_rollout(db, path, aliases, artifact_roots):
    stat = path.stat()
    row = db.execute("SELECT data FROM rollout_cursors WHERE id=?", (str(path),)).fetchone()
    old = json.loads(row[0]) if row else {}
    scope = digest([aliases, artifact_roots])
    if old.get("scope") == scope and old.get("size") == stat.st_size and old.get("mtime") == stat.st_mtime_ns:
        return {"read": 0, "skipped": 1}
    ctx = old if old.get("scope") == scope and old.get("inode") == stat.st_ino and old.get("offset", 0) <= stat.st_size else {}
    if ctx.get("outOfScope"):
        ctx.update(size=stat.st_size, mtime=stat.st_mtime_ns)
        db.execute("UPDATE rollout_cursors SET data=? WHERE id=?", (canonical(ctx), str(path)))
        return {"read": 0, "skipped": 1}
    read = 0
    with path.open("rb") as stream:
        stream.seek(ctx.get("offset", 0))
        while True:
            offset = stream.tell()
            raw = stream.readline(MAX_LINE + 1)
            if not raw:
                break
            if len(raw) > MAX_LINE:
                # Consume oversized records without parsing or retaining their contents.
                while raw and not raw.endswith(b"\n"):
                    raw = stream.readline(MAX_LINE + 1)
                ctx["oversized"] = ctx.get("oversized", 0) + 1
                ctx["offset"] = stream.tell()
                continue
            if not raw.endswith(b"\n"):
                break  # An active writer may finish this record on the next scan.
            ctx["offset"] = stream.tell()
            try:
                record = json.loads(raw)
                payload, kind = record.get("payload", {}), record.get("type")
                if not isinstance(payload, dict):
                    continue
                at = stamp(record.get("timestamp"))
                if kind == "session_meta":
                    if ctx.get("session"):
                        continue  # A fork can carry a copied parent's session header.
                    sid = payload.get("id") or payload.get("session_id")
                    if not isinstance(sid, str):
                        continue
                    ctx.update(session=sid, repository=repository_for(payload.get("cwd"), aliases),
                        started=max(stamp(payload.get("timestamp")) or 0, at or 0), fork=payload.get("forked_from_id"),
                        agent=isinstance(payload.get("source"), dict) or payload.get("thread_source") == "subagent")
                    if not ctx["repository"]:
                        # Scope by initial task cwd. Never read unrelated conversation bodies.
                        ctx["outOfScope"] = True
                        break
                elif kind == "turn_context":
                    ctx.update(model=payload.get("model", "unknown"), effort=payload.get("effort") or payload.get("reasoning_effort") or "unknown",
                        turn=payload.get("turn_id"), repository=repository_for(payload.get("cwd"), aliases) or ctx.get("repository"))
                if not ctx.get("session") or not ctx.get("repository") or not at:
                    continue
                if ctx.get("fork") and at <= (ctx.get("started") or 0):
                    continue  # Copied parent history is not new work in the child.
                base = {"at": at, "repository": ctx["repository"], "model": ctx.get("model", "unknown"),
                    "effort": ctx.get("effort", "unknown"), "turn": ctx.get("turn"), "agent": ctx.get("agent", False)}
                for setting in ("model", "effort"):
                    if not isinstance(base[setting], str):
                        base[setting] = "unknown"
                if kind == "event_msg" and payload.get("type") == "token_count":
                    info = payload.get("info") or {}
                    total, last = token_vector(info.get("total_token_usage")), token_vector(info.get("last_token_usage"))
                    if total and last:
                        event(db, ctx["session"], {**base, "kind": "usage", "total": total, "last": last})
                    elif info:
                        ctx["invalidUsage"] = ctx.get("invalidUsage", 0) + 1
                elif kind == "response_item" and payload.get("type") == "message" and payload.get("role") in ("user", "assistant"):
                    role = payload["role"]
                    content = payload.get("content", [])
                    event(db, ctx["session"], {**base, "kind": "message", "role": role, "fingerprint": digest(content)})
                    if role == "assistant":
                        text = "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
                        for link in re.findall(r"\]\(<?(/[^\n)]+?)>?\)", text):
                            candidate = re.sub(r":\d+(?::\d+)?$", "", link)
                            if Path(candidate).suffix.lower() not in EXTENSIONS:
                                continue
                            if any(contained(candidate, r["path"]) for r in artifact_roots):
                                value = {"kind": "artifact_link", "at": at, "repository": ctx["repository"], "path": candidate}
                                event(db, ctx["session"], value)
                read += 1
            except (ValueError, TypeError, KeyError):
                ctx["malformed"] = ctx.get("malformed", 0) + 1
    ctx.update(inode=stat.st_ino, size=stat.st_size, mtime=stat.st_mtime_ns, scope=scope)
    db.execute("INSERT INTO rollout_cursors VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (str(path), canonical(ctx)))
    return {"read": read, "skipped": 0}


def usage_summary(db):
    sessions, groups, days, repos = {}, {}, {}, {}
    gaps = resets = duplicates = ambiguous = 0
    fields = (*TOKENS, "userMessages", "assistantMessages", "samples")
    def bucket(mapping, key):
        return mapping.setdefault(key, {k: 0 for k in fields})
    for row in db.execute("SELECT session,data FROM usage_events ORDER BY session,json_extract(data,'$.at'),id"):
        item, sid = json.loads(row["data"]), row["session"]
        if item["kind"] == "artifact_link":
            continue
        session = sessions.setdefault(sid, {"id": sid, "repositories": set(), "models": set(), "firstAt": item["at"],
            "lastAt": item["at"], "agent": item.get("agent", False), "previous": None, **{k: 0 for k in fields}})
        session["repositories"].add(item["repository"])
        session["models"].add(item["model"] + " / " + item["effort"])
        session["lastAt"] = max(session["lastAt"], item["at"])
        delta = {k: 0 for k in fields}
        if item["kind"] == "usage":
            total, last, previous = item["total"], item["last"], session["previous"]
            if previous == total:
                duplicates += 1
                continue
            if previous is not None and all(total[k] >= previous[k] for k in TOKENS):
                change = {k: total[k] - previous[k] for k in TOKENS}
                if change == last:
                    delta.update(change)
                else:
                    # Context accounting adjustments or missing samples are not safely
                    # attributable to this model/effort. Keep only the reported last call.
                    delta.update(last)
                    ambiguous += 1
            else:
                # A missing prefix / counter reset cannot be assigned to the current model.
                delta.update(last)
                if previous is not None:
                    resets += 1
                elif total != last:
                    gaps += 1
            session["previous"] = total
            delta["samples"] = 1
        else:
            delta["userMessages" if item["role"] == "user" else "assistantMessages"] = 1
        targets = [session, bucket(groups, (item["repository"], item["model"], item["effort"])),
            bucket(days, dt.datetime.fromtimestamp(item["at"], dt.timezone.utc).strftime("%Y-%m-%d")), bucket(repos, item["repository"])]
        for target in targets:
            for key, value in delta.items():
                target[key] += value
    for session in sessions.values():
        session.pop("previous")
        session["repositories"] = sorted(session["repositories"])
        session["models"] = sorted(session["models"])
    totals = {k: sum(s[k] for s in sessions.values()) for k in fields}
    totals.update(sessions=len(sessions), userTasks=sum(not s["agent"] for s in sessions.values()), agentTasks=sum(s["agent"] for s in sessions.values()))
    totals["cacheRate"] = totals["cached_input_tokens"] / totals["input_tokens"] if totals["input_tokens"] else None
    cursors = [json.loads(r[0]) for r in db.execute("SELECT data FROM rollout_cursors")]
    warnings = {k: sum(c.get(k, 0) for c in cursors) for k in ("malformed", "oversized", "invalidUsage")}
    return {"status": "measured" if totals["samples"] else "unavailable", "aggregate": totals,
        "repositories": [{"repository": k, **v} for k, v in sorted(repos.items())],
        "modelEffort": [{"repository": k[0], "model": k[1], "effort": k[2], **v} for k, v in sorted(groups.items())],
        "days": [{"day": k, **v} for k, v in sorted(days.items())], "sessions": sorted(sessions.values(), key=lambda s: s["firstAt"]),
        "coverage": {"missingPrefixes": gaps, "counterResets": resets, "ambiguousDeltas": ambiguous, "repeatedCountersIgnored": duplicates, **warnings},
        "reason": "Retained local rollout observations only; attributed by task working directory, not files edited. Cached input is part of input; reasoning is part of output. Missing prefixes and reset gaps are excluded. Message counts are logged user/assistant records, not semantic turns. No transcript text is retained. No billing or causal model-effect claim."}


def capture(db, key, raw, metadata):
    content_hash = hashlib.sha256(raw).hexdigest()
    rows = [json.loads(r[0]) for r in db.execute("SELECT data FROM artifact_versions WHERE json_extract(data,'$.key')=? ORDER BY json_extract(data,'$.version')", (key,))]
    if rows and rows[-1]["sha256"] == content_hash:
        existing = rows[-1]
        # New task references do not manufacture a new byte version.
        previous_refs = [] if existing.get("provenance") == "assistant_link_current_bytes" else existing.get("references", [])
        references = {canonical(r): r for r in previous_refs + metadata.get("references", [])}
        existing["references"] = sorted(references.values(), key=lambda r: r["at"])
        existing["orderAt"] = min(existing["orderAt"], metadata["orderAt"])
        db.execute("UPDATE artifact_versions SET data=? WHERE id=?", (canonical(existing), existing["id"]))
        return existing
    at = time.time()
    record = {**metadata, "key": key, "sha256": content_hash, "size": len(raw), "version": len(rows) + 1, "observedAt": at}
    record["id"] = digest([key, record["version"], content_hash])
    db.execute("INSERT INTO artifact_versions VALUES (?,?,?)", (record["id"], canonical(record), raw))
    return record


def capture_artifacts(db, roots):
    links, errors = {}, []
    for row in db.execute("SELECT session,data FROM usage_events WHERE json_extract(data,'$.kind')='artifact_link'"):
        item = json.loads(row["data"])
        links.setdefault(item["path"], []).append({"session": row["session"], "at": item["at"]})
    # Only explicitly linked files are imported, never a recursive home/source crawl.
    for path, references in links.items():
        root = next((r for r in roots if contained(path, r["path"])), None)
        if not root:
            continue
        try:
            raw = read_regular(path, root["path"], MAX_ARTIFACT)
            capture(db, path, raw, {"name": Path(path).name, "repository": root["repository"], "path": path,
                "references": sorted(references, key=lambda r: r["at"]), "orderAt": min(r["at"] for r in references),
                "provenance": "assistant_link_current_bytes", "createdAt": None})
        except (OSError, Refusal) as error:
            errors.append({"path": path, "reason": str(error)[:200]})
    return errors


def register_artifact(ledger, path, repository, session=None, created_at=None):
    settings = config(ledger)
    root = next((r for r in settings.get("artifactRoots", []) if r["repository"] == repository and contained(path, r["path"])), None)
    require(root is not None, "Register an explicit artifact root first")
    require(Path(path).suffix.lower() in EXTENSIONS, "Unsupported artifact format")
    raw = read_regular(path, root["path"], MAX_ARTIFACT)
    with ledger.tx() as db:
        return capture(db, str(Path(path).absolute()), raw, {"name": Path(path).name, "path": str(Path(path).absolute()),
            "repository": repository, "references": [{"session": session, "at": created_at or time.time()}] if session else [],
            "createdAt": created_at, "orderAt": created_at or time.time(), "provenance": "explicit_registration"})


def artifact(ledger, identity):
    require(re.fullmatch(r"[a-f0-9]{64}", identity), "Invalid artifact identity")
    with contextlib.closing(ledger.connect()) as db:
        row = db.execute("SELECT data,content FROM artifact_versions WHERE id=?", (identity,)).fetchone()
        require(row is not None, "Unknown artifact")
        return json.loads(row["data"]), bytes(row["content"])


def git_observation(repo, remote=False):
    result = {"repository": repo["id"], "at": time.time(), "status": "unavailable", "worktrees": [], "branches": [], "pullRequests": [], "remoteStatus": "not_requested"}
    try:
        path = repo["path"]
        result["configuredCommit"] = head(path, repo["ref"])
        result["ref"] = repo["ref"]
        records = git(path, "worktree", "list", "--porcelain").split("\n\n")
        for record in records:
            worktree = dict(line.split(" ", 1) if " " in line else (line, True) for line in record.splitlines())
            if "worktree" not in worktree:
                continue
            item = {"path": worktree["worktree"], "commit": worktree.get("HEAD"), "branch": str(worktree.get("branch", "detached")).removeprefix("refs/heads/"), "locked": "locked" in worktree, "prunable": "prunable" in worktree}
            try:
                raw = git(item["path"], "--no-optional-locks", "status", "--porcelain=v1", "-z", "--untracked-files=normal", binary=True)
                item["dirty"] = bool(raw)
                item["status"] = "dirty" if raw else "clean"
            except (Refusal, OSError, subprocess.SubprocessError):
                item.update(dirty=None, status="unavailable")
            result["worktrees"].append(item)
        fmt = "%(refname:short)%09%(objectname)%09%(upstream:short)%09%(upstream:track)%09."
        for line in git(path, "for-each-ref", "--format=" + fmt, "refs/heads").splitlines():
            branch, commit, upstream, tracking, _ = line.split("\t")
            result["branches"].append({"branch": branch, "commit": commit, "upstream": upstream or None,
                "tracking": tracking, "pushStatus": "not_observed"})
        result["status"] = "measured"
        if remote:
            # Fixed GitHub REST GET endpoints, no fetch/push/checkout and no mutation.
            origin = git(path, "remote", "get-url", "origin")
            match = re.fullmatch(r"(?:git@github.com:|https://github.com/)([\w.-]+/[\w.-]+?)(?:\.git)?", origin)
            require(match is not None, "Only configured GitHub origins can be observed")
            slug = match[1]
            def gh(endpoint):
                output = subprocess.run(["gh", "api", "--method", "GET", f"repos/{slug}/{endpoint}"], capture_output=True, timeout=30)
                require(output.returncode == 0, "GitHub observation unavailable; check local gh authentication/network")
                return json.loads(output.stdout)
            pulls = gh("pulls?state=all&sort=updated&direction=desc&per_page=100")
            result["pullRequests"] = [{"number": p["number"], "url": p["html_url"], "title": p["title"], "state": "merged" if p.get("merged_at") else p["state"],
                "draft": p.get("draft", False), "branch": p["head"]["ref"], "head": p["head"]["sha"], "base": p["base"]["ref"],
                "mergedAt": p.get("merged_at"), "mergeCommit": p.get("merge_commit_sha") if p.get("merged_at") else None} for p in pulls]
            remote_branches = {b["name"]: b["commit"]["sha"] for b in gh("branches?per_page=100")}
            for branch in result["branches"]:
                remote_name = branch["branch"]
                observed = remote_branches.get(remote_name)
                branch.update(remoteRef="refs/heads/" + remote_name, remoteCommit=observed, pushStatus="matches_remote" if observed == branch["commit"] else "differs_remote" if observed else "not_in_remote_page")
            result.update(remoteStatus="observed", remoteAt=time.time(), remoteLimit=100)
    except (Refusal, OSError, subprocess.SubprocessError, ValueError, KeyError) as error:
        result["reason"] = str(error)[:300]
        if result["status"] == "measured":
            result["remoteStatus"] = "unavailable"
    return result


def parse_checklist(text):
    items, headings, fenced = [], [], False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        if fenced:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)", line)
        if heading:
            depth = len(heading[1]); headings = headings[:depth - 1] + [heading[2]]
        item = re.match(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+)", line)
        if item:
            items.append({"line": number, "label": item[2], "checked": item[1].lower() == "x", "section": " / ".join(headings)})
    return items


def first_status_table(text):
    """Keep source labels verbatim. Only the first status table, not old snapshots."""
    lines = text.splitlines()
    for index, line in enumerate(lines[:-1]):
        if not line.startswith("|"):
            continue
        headers = [cell.strip() for cell in line.strip("|").split("|")]
        if "status" not in [h.lower() for h in headers] or not re.match(r"^\|[\s:|-]+\|$", lines[index + 1]):
            continue
        rows = []
        for row in lines[index + 2:]:
            if not row.startswith("|"):
                break
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            if len(cells) == len(headers):
                rows.append(cells)
        return {"headers": headers, "rows": rows, "line": index + 1}
    return None


def roadmap_observation(db, spec, repos):
    record = {**spec, "at": time.time(), "status": "unavailable", "items": []}
    try:
        repo = next(r for r in repos if r["id"] == spec["repository"])
        safe_relative(spec["path"])
        commit = head(repo["path"], repo["ref"])
        raw = blob(repo["path"], commit, spec["path"])
        require(len(raw) <= MAX_ARTIFACT, "Roadmap too large")
        document = capture(db, "roadmap:" + spec["repository"] + ":" + spec["path"], raw,
            {"name": Path(spec["path"]).name, "repository": spec["repository"], "path": spec["path"],
                "provenance": "git_roadmap", "commit": commit, "references": [], "createdAt": None, "orderAt": time.time()})
        text = raw.decode("utf-8")
        record.update(status="observed", commit=commit, documentId=document["id"], items=parse_checklist(text), statusTable=first_status_table(text))
    except (Refusal, OSError, subprocess.SubprocessError, UnicodeError, StopIteration) as error:
        record["reason"] = str(error)
    return record


def refresh_observations(ledger, remote=False):
    """One bounded local scan. The dashboard may request it; it cannot dispatch."""
    lock = open(ledger.root / "observations.lock", "a")
    try:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Refusal("Observation refresh already running") from error
        settings, state = config(ledger), ledger.snapshot()
        with ledger.tx() as db:
            prior = db.execute("SELECT data FROM observation_records WHERE id='importer'").fetchone()
            version = json.loads(prior[0]).get("version") if prior else None
            if version != IMPORTER_VERSION:
                # These are rebuildable sanitized indexes, never original logs,
                # approvals, worker evidence or immutable artifact bytes.
                db.execute("DELETE FROM usage_events")
                db.execute("DELETE FROM rollout_cursors")
                save(db, "importer", {"version": IMPORTER_VERSION})
        repos, aliases, errors = state["repositories"], {}, []
        roots = settings.get("artifactRoots", [])
        for root in roots:
            require(root["repository"] in {r["id"] for r in repos}, "Artifact root repository is not registered")
        for repo in repos:
            observed = git_observation(repo, remote)
            if repo.get("path"):
                aliases[repo["path"]] = repo["id"]
            for tree in observed["worktrees"]:
                aliases[tree["path"]] = repo["id"]
            with ledger.tx() as db:
                # Local scans don't erase the previous timestamped remote observation.
                prior = db.execute("SELECT data FROM observation_records WHERE id=?", ("git:" + repo["id"],)).fetchone()
                if prior and not remote:
                    previous = json.loads(prior[0])
                    observed["previousRemote"] = {k: previous.get(k) for k in ("remoteAt", "remoteStatus", "pullRequests", "branches")} if previous.get("remoteAt") else previous.get("previousRemote")
                save(db, "git:" + repo["id"], observed)
            ledger.metric(measure(repo))
        imported = skipped = 0
        codex_home = settings.get("codexHome")
        if codex_home:
            for folder in (Path(codex_home) / "sessions", Path(codex_home) / "archived_sessions"):
                if not folder.is_dir():
                    errors.append({"source": folder.name, "reason": "Source directory unavailable"})
                    continue
                for path in sorted(folder.rglob("*.jsonl")):
                    if path.is_symlink():
                        continue
                    try:
                        with ledger.tx() as db:
                            stats = ingest_rollout(db, path, aliases, roots)
                        imported += stats["read"]; skipped += stats["skipped"]
                    except (OSError, ValueError) as error:
                        errors.append({"source": path.name, "reason": str(error)[:150]})
        with ledger.tx() as db:
            usage = usage_summary(db)
            usage["at"] = time.time()
            save(db, "usage", usage)
            errors.extend(capture_artifacts(db, roots))
            plans = [roadmap_observation(db, spec, repos) for spec in settings.get("roadmaps", [])]
            save(db, "roadmaps", {"at": time.time(), "plans": plans})
            result = {"at": time.time(), "status": "partial" if errors else "complete", "remoteRequested": remote,
                "importedRecords": imported, "unchangedFiles": skipped, "errors": errors, "usageConfigured": bool(codex_home)}
            save(db, "refresh", result)
        return result
    finally:
        lock.close()


def snapshot(db):
    values = {r["id"]: json.loads(r["data"]) for r in db.execute("SELECT * FROM observation_records")}
    artifacts = [json.loads(r[0]) for r in db.execute("SELECT data FROM artifact_versions")]
    return {"usage": values.get("usage"), "git": [v for k, v in values.items() if k.startswith("git:")],
        "roadmaps": values.get("roadmaps", {"plans": []}), "refresh": values.get("refresh"), "executive": values.get("executive"),
        "artifacts": sorted(artifacts, key=lambda a: (a["orderAt"], a["key"], a["version"]))}
