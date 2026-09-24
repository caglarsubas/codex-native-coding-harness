"""Private, project-scoped code index. Git and ledger remain the source of truth.

Graphify is an optional code-only adapter. No installer, hooks, model keys or
provider-generated text is needed for the bounded source search fallback.
"""
from __future__ import annotations

import hashlib
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time

from .core import Refusal, canonical, digest, require, safe_relative

VERSION = 1
GRAPHIFY_VERSION = "0.9.66"
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".cs", ".rb", ".swift", ".kt", ".sh"}
SECRET_PARTS = {".env", "secrets", "credentials", "private", "node_modules", "vendor", "dist", "build", ".git"}
MAX_FILES = 3000
MAX_FILE = 256 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_QUERY = 300
MAX_EXCERPTS = 24 * 1024
STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from", "how", "in", "is", "of", "on", "or", "the", "to", "was", "were", "what", "when", "where", "which", "who", "with"}
PEM_PRIVATE_KEY = re.compile(rb"(?m)^[ \t]*-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[ \t]*\r?$")


def _git(repo, *args, timeout=15, maximum=MAX_TOTAL + 1000):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=timeout, check=False)
    require(result.returncode == 0 and len(result.stdout) <= maximum, "Git source observation unavailable")
    return result.stdout


def config(ledger):
    path = ledger.root / "knowledge.json"
    if not path.exists():
        return None
    require(not path.is_symlink() and path.stat().st_size <= 16_000, "Invalid private knowledge configuration")
    value = json.loads(path.read_text())
    require(isinstance(value, dict) and set(value) == {"schemaVersion", "repositories", "graphify"}
            and value["schemaVersion"] == VERSION, "Invalid knowledge configuration")
    require(isinstance(value["repositories"], dict) and len(value["repositories"]) <= 32, "Repository allowlist required")
    for repo_id, prefixes in value["repositories"].items():
        require(isinstance(repo_id, str) and isinstance(prefixes, list) and 1 <= len(prefixes) <= 32,
                "Exact repository prefixes required")
        for prefix in prefixes:
            require(isinstance(prefix, str) and prefix.endswith("/") and safe_relative(prefix[:-1]),
                    "Repository prefix must be a relative directory")
    provider = value["graphify"]
    require(provider is None or (isinstance(provider, dict) and set(provider) == {"executable", "version", "sha256"}
            and provider["version"] == GRAPHIFY_VERSION and isinstance(provider["executable"], str)
            and Path(provider["executable"]).is_absolute()
            and isinstance(provider["sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", provider["sha256"])),
            "Pinned Graphify executable or null required")
    return value


def _repo(ledger, repository):
    with ledger.tx() as db:
        row = ledger.get(db, "repos", repository)
    require(row["policyProfile"] == "standard", "Knowledge indexing is standard-project only")
    path = Path(row["path"])
    require(path.is_absolute() and path.is_dir(), "Registered repository unavailable")
    resolved = path.resolve()
    for forbidden in os.environ.get("HARNESS_WARM_SOURCE_ROOTS", "").splitlines():
        if not forbidden.strip():
            continue
        root = Path(forbidden)
        require(root.is_absolute(), "Warm-source root setting must be absolute")
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        raise Refusal("Prohibited warm-source repository cannot be indexed")
    return path


def _allowed(path, prefixes):
    try:
        safe_relative(path)
    except (Refusal, ValueError):
        return False
    parts = path.lower().split("/")
    return (path.startswith(tuple(prefixes)) and Path(path).suffix.lower() in CODE_SUFFIXES
            and not any(p.startswith(".") or p in SECRET_PARTS or "secret" in p or "credential" in p for p in parts))


def source_manifest(ledger, repository, prefixes):
    repo = _repo(ledger, repository)
    commit = _git(repo, "rev-parse", "HEAD", maximum=100).decode().strip()
    require(re.fullmatch(r"[a-f0-9]{40,64}", commit), "Git revision unavailable")
    names = _git(repo, "ls-tree", "-rz", "--full-tree", commit, maximum=1_000_000).split(b"\0")
    files, total = [], 0
    for entry in names:
        if not entry:
            continue
        header, _, raw_path = entry.partition(b"\t")
        fields = header.split()
        if len(fields) != 3 or fields[1] != b"blob" or fields[0] not in (b"100644", b"100755"):
            continue
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not _allowed(path, prefixes):
            continue
        raw = _git(repo, "show", fields[2].decode(), maximum=MAX_FILE + 1)
        require(len(raw) <= MAX_FILE, "Allowlisted source exceeds per-file bound")
        require(not PEM_PRIVATE_KEY.search(raw), "Secret-bearing source cannot be indexed")
        total += len(raw)
        require(total <= MAX_TOTAL and len(files) < MAX_FILES, "Knowledge source limit exceeded")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        files.append({"path": path, "blob": fields[2].decode(), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    return repo, commit, files


def _directory(ledger, repository):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", repository), "Invalid repository ID")
    root = ledger.root / "knowledge"
    for item in (root, root / repository):
        require(not item.is_symlink(), "Symlinked private index path refused")
    return root / repository


def _manifest(ledger, repository, index_hash=None):
    if index_hash is not None:
        require(isinstance(index_hash, str) and re.fullmatch(r"[a-f0-9]{64}", index_hash), "Exact index hash required")
        require(not (_directory(ledger, repository) / index_hash).is_symlink(), "Symlinked index version refused")
    path = _directory(ledger, repository) / index_hash / "manifest.json" if index_hash else _directory(ledger, repository) / "active.json"
    if not path.exists():
        return None
    from .observations import read_regular
    require(not path.is_symlink(), "Symlinked index manifest refused")
    try:
        value = json.loads(read_regular(path, _directory(ledger, repository), 1_000_000))
    except OSError as error:
        raise Refusal("Index manifest unavailable") from error
    require(value["documentHash"] == digest({key: val for key, val in value.items() if key != "documentHash"})
            and value["repository"] == repository, "Index manifest provenance changed")
    return value


def _provider(provider, stage):
    if provider is None:
        return {"status": "unavailable", "detail": "Graphify is not configured; bounded source search remains available"}
    exe = Path(provider["executable"])
    require(exe.is_file() and not exe.is_symlink() and os.access(exe, os.X_OK), "Pinned Graphify binary unavailable")
    require(exe.stat().st_size <= MAX_TOTAL and hashlib.sha256(exe.read_bytes()).hexdigest() == provider["sha256"],
            "Graphify executable digest differs from the reviewed pin")
    # Explicit allowlist removes model credentials and provider endpoints.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
    env["HOME"] = str(stage)
    env["TMPDIR"] = str(stage)
    env["XDG_CONFIG_HOME"] = str(stage)
    env["XDG_CACHE_HOME"] = str(stage)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    version = subprocess.run([str(exe), "--version"], env=env, capture_output=True, timeout=10, check=False)
    require(version.returncode == 0 and GRAPHIFY_VERSION.encode() in version.stdout + version.stderr,
            "Graphify version differs from the reviewed pin")
    result = subprocess.run([str(exe), "extract", str(stage / "src"), "--code-only", "--no-cluster",
                             "--max-workers", "2", "--out", str(stage)],
                            cwd=stage, env=env, capture_output=True, timeout=180, check=False)
    require(result.returncode == 0, "Graphify code-only extraction failed")
    graph = stage / "graphify-out" / "graph.json"
    require(not graph.is_symlink() and graph.is_file() and graph.stat().st_size <= MAX_TOTAL,
            "Graphify output unavailable or oversized")
    return {"status": "ready", "version": GRAPHIFY_VERSION, "graphSha256": hashlib.sha256(graph.read_bytes()).hexdigest(),
            "graphPath": str(graph.relative_to(stage))}


def refresh(ledger, repository):
    cfg = config(ledger)
    require(cfg is not None and repository in cfg["repositories"], "Repository is not allowlisted for knowledge")
    repo, commit, files = source_manifest(ledger, repository, cfg["repositories"][repository])
    directory = _directory(ledger, repository)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stage-", dir=directory) as temp:
        stage = Path(temp)
        (stage / "src").mkdir(mode=0o700)
        for row in files:
            target = stage / "src" / row["path"]
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            raw = _git(repo, "show", row["blob"], maximum=MAX_FILE + 1)
            require(hashlib.sha256(raw).hexdigest() == row["sha256"], "Git blob changed during extraction")
            target.write_bytes(raw)
        try:
            provider = _provider(cfg["graphify"], stage)
        except (Refusal, OSError, subprocess.TimeoutExpired):
            provider = {"status": "failed", "detail": "Pinned Graphify extraction unavailable; source search remains available"}
        manifest = {"schemaVersion": VERSION, "repository": repository, "commit": commit, "at": time.time(),
                    "configHash": digest(cfg), "files": files, "provider": provider,
                    "boundary": "Derived local code index; source Git revision is authoritative"}
        manifest["documentHash"] = digest(manifest)
        version_dir = directory / manifest["documentHash"]
        require(not version_dir.exists(), "Index version already exists; inspect its provenance")
        (stage / "manifest.json").write_text(canonical(manifest))
        shutil.move(str(stage), str(version_dir))
    active = directory / "active.json"
    temporary = directory / ("active-" + manifest["documentHash"] + ".tmp")
    temporary.write_text(canonical(manifest))
    os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(temporary, active)
    return status(ledger, repository)


def status(ledger, repository):
    cfg = config(ledger)
    if cfg is None or repository not in cfg["repositories"]:
        return {"repository": repository, "status": "unconfigured", "provider": "unavailable",
                "coverageGaps": ["No private repository allowlist"]}
    manifest = _manifest(ledger, repository)
    if manifest is None:
        return {"repository": repository, "status": "not_indexed", "provider": "unavailable",
                "coverageGaps": ["No retained index version"]}
    repo = _repo(ledger, repository)
    head = _git(repo, "rev-parse", "HEAD", maximum=100).decode().strip()
    dirty = bool(_git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--",
                      *cfg["repositories"][repository], maximum=1_000_000))
    current = head == manifest["commit"] and manifest["configHash"] == digest(cfg) and not dirty
    gaps = ["Only configured tracked UTF-8 code files are indexed"]
    if dirty: gaps.append("Allowlisted checkout has uncommitted changes; HEAD does not include them")
    if head != manifest["commit"]: gaps.append("Indexed revision differs from current HEAD")
    if manifest["configHash"] != digest(cfg): gaps.append("Knowledge allowlist or provider configuration changed")
    if manifest["provider"]["status"] != "ready": gaps.append("Graphify relationships unavailable; bounded source search only")
    return {"repository": repository, "status": "current" if current else "checkout_changed" if dirty else "stale",
            "documentHash": manifest["documentHash"], "commit": manifest["commit"],
            "observedAt": manifest["at"], "fileCount": len(manifest["files"]),
            "provider": manifest["provider"], "currentHead": head, "workingTreeChanged": dirty,
            "coverageGaps": gaps}


def record_links(ledger, repository, query=""):
    """Search retained authority metadata only; never copy decision/artifact bodies."""
    cfg = config(ledger)
    require(cfg is not None and repository in cfg["repositories"], "Repository is not allowlisted for knowledge")
    require(isinstance(query, str) and len(query) <= MAX_QUERY, "Bounded record query required")
    words = [word.casefold() for word in re.findall(r"[\w.-]+", query) if len(word) >= 2][:20]
    found = []
    with contextlib.closing(ledger.connect()) as db:
        row = db.execute("SELECT data FROM observation_records WHERE id='roadmaps'").fetchone()
        plans = (json.loads(row[0]).get("plans", []) if row else [])
        for plan in plans[:32]:
            if plan.get("repository") != repository or plan.get("status") != "observed":
                continue
            found.append({"kind": "roadmap", "title": plan.get("title") or plan["path"],
                          "path": plan["path"], "id": plan["documentId"],
                          "version": plan["documentVersion"], "commit": plan["commit"],
                          "observedAt": plan["at"], "provenance": "RECORDED_SOURCE"})
        for row in db.execute("SELECT data FROM decisions LIMIT 5000"):
            decision = json.loads(row[0])
            spec = decision.get("spec", {})
            if spec.get("repository") == repository:
                found.append({"kind": "decision", "title": spec.get("title", "Decision"),
                              "id": decision["id"], "version": decision["version"],
                              "status": decision["status"], "observedAt": decision["createdAt"],
                              "provenance": "RECORDED_DECISION"})
        for row in db.execute("SELECT data FROM artifact_versions LIMIT 5000"):
            artifact = json.loads(row[0])
            if artifact.get("repository") == repository:
                found.append({"kind": "artifact", "title": artifact.get("name") or artifact.get("path", "Artifact"),
                              "path": artifact.get("path"), "id": artifact["id"],
                              "version": artifact["version"], "sha256": artifact["sha256"],
                              "observedAt": artifact.get("observedAt"), "provenance": "RECORDED_ARTIFACT"})
    matched = [item for item in found if not words or any(word in canonical(item).casefold() for word in words)]
    matched.sort(key=lambda item: (-sum(word in canonical(item).casefold() for word in words),
                                   -(item.get("observedAt") or 0), item["kind"], item["id"]))
    return {"records": matched[:10], "truncated": len(matched) > 10,
            "coverage": "retained_metadata_only", "boundary": "Links point to existing retained source/decision/artifact versions; no body is indexed"}


def seed_references(ledger, repository, checkout, paths):
    """Inert references for exact task paths only; never copy graph or conversation."""
    cfg = config(ledger)
    if cfg is None or repository not in cfg["repositories"]:
        return {"status": "unconfigured", "items": []}
    manifest = _manifest(ledger, repository)
    if not manifest:
        return {"status": "not_indexed", "items": []}
    repo = Path(checkout)
    head = _git(repo, "rev-parse", "HEAD", maximum=100).decode().strip()
    dirty = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--",
                 *cfg["repositories"][repository], maximum=1_000_000)
    if head != manifest["commit"] or manifest["configHash"] != digest(cfg) or dirty:
        return {"status": "stale", "items": []}
    exact_paths = set(paths)
    items = [{"path": row["path"], "commit": head, "blob": row["blob"], "sha256": row["sha256"],
              "indexHash": manifest["documentHash"], "provenance": "EXTRACTED_REFERENCE"}
             for row in manifest["files"] if row["path"] in exact_paths]
    return {"status": "current", "items": items[:10], "truncated": len(items) > 10,
            "boundary": "Read source separately at the cited version; reference grants no scope or authority"}


def metadata(ledger):
    """Bounded index metadata for advisory context; no source or active scans."""
    try:
        cfg = config(ledger)
        if cfg is None:
            return {"status": "unconfigured", "repositories": []}
        rows = []
        for repository in sorted(cfg["repositories"])[:10]:
            manifest = _manifest(ledger, repository)
            rows.append({"repository": repository, "indexHash": manifest["documentHash"] if manifest else None,
                         "commit": manifest["commit"] if manifest else None,
                         "observedAt": manifest["at"] if manifest else None,
                         "providerStatus": manifest["provider"]["status"] if manifest else "unavailable"})
        return {"status": "retained_metadata", "repositories": rows,
                "omitted": max(0, len(cfg["repositories"]) - len(rows)),
                "freshness": "not_checked", "boundary": "Index metadata only; no code excerpts or authority"}
    except (Refusal, OSError, ValueError, KeyError):
        return {"status": "unavailable", "repositories": [], "freshness": "not_checked"}


def related(ledger, repository, index_hash, path):
    """Bounded direct Graphify edges, never inferred authority."""
    manifest = _manifest(ledger, repository, index_hash)
    require(manifest is not None and any(row["path"] == path for row in manifest["files"]),
            "Cited source is outside the allowlisted index")
    provider = manifest["provider"]
    if provider.get("status") != "ready":
        return {"status": "unavailable", "items": [], "reason": "Pinned Graphify graph unavailable"}
    relative = provider["graphPath"]
    safe_relative(relative)
    graph_path = _directory(ledger, repository) / index_hash / relative
    from .observations import read_regular
    raw = read_regular(graph_path, _directory(ledger, repository), MAX_TOTAL)
    require(hashlib.sha256(raw).hexdigest() == provider["graphSha256"], "Graph output provenance changed")
    graph = json.loads(raw)
    require(isinstance(graph, dict) and isinstance(graph.get("nodes"), list)
            and isinstance(graph.get("edges", graph.get("links", [])), list)
            and len(graph["nodes"]) <= 100_000, "Invalid graph output")
    allowed = {row["path"] for row in manifest["files"]}
    def source_path(node):
        value = node.get("source_file")
        if not isinstance(value, str):
            return None
        staged_relative = value.split("/src/", 1)[-1]
        for candidate in (value, staged_relative, value.removeprefix("src/"), "src/" + value):
            if candidate in allowed:
                return candidate
        return None
    nodes = {node.get("id"): node for node in graph["nodes"] if isinstance(node, dict)
             and isinstance(node.get("id"), str) and source_path(node)}
    origins = {identity for identity, node in nodes.items() if source_path(node) == path}
    matches = []
    edges = graph.get("edges", graph.get("links", []))
    for edge in edges[:200_000]:
        if not isinstance(edge, dict):
            continue
        source_id, target_id = edge.get("source"), edge.get("target")
        if not isinstance(source_id, str) or not isinstance(target_id, str):
            continue
        if source_id in origins and target_id in nodes and source_path(nodes[target_id]) != path:
            other = nodes[target_id]
        elif target_id in origins and source_id in nodes and source_path(nodes[source_id]) != path:
            other = nodes[source_id]
        else:
            continue
        matches.append({"path": source_path(other), "label": str(other.get("label", ""))[:200],
                        "relation": str(edge.get("relation", "related"))[:80],
                        "provenance": edge["confidence"] if edge.get("confidence") in ("EXTRACTED", "INFERRED", "AMBIGUOUS") else "UNSPECIFIED",
                        "indexHash": index_hash, "commit": manifest["commit"]})
    items = list({canonical(item): item for item in matches}.values())
    return {"status": "ready", "items": items[:10], "truncated": len(items) > 10 or len(edges) > 200_000,
            "boundary": "Provider graph edges are untrusted search hints, not reviewed source or approval evidence"}


def search(ledger, repository, query):
    require(isinstance(query, str) and 0 < len(query.strip()) <= MAX_QUERY, "Bounded query required")
    state = status(ledger, repository)
    require(state["status"] != "unconfigured", "Repository is not allowlisted for knowledge")
    manifest = _manifest(ledger, repository)
    direct = state["status"] != "current"
    if direct:
        cfg = config(ledger)
        _, commit, files = source_manifest(ledger, repository, cfg["repositories"][repository])
        manifest = {"commit": commit, "files": files, "documentHash": None, "at": time.time(),
                    "provider": {"status": "unavailable"}}
    repo = _repo(ledger, repository)
    terms = [w.casefold() for w in re.findall(r"[\w.-]+", query) if len(w) >= 2 and w.casefold() not in STOP_WORDS][:20]
    require(terms, "Search terms required")
    found = []
    for row in manifest["files"]:
        raw = _git(repo, "show", row["blob"], maximum=MAX_FILE + 1)
        require(hashlib.sha256(raw).hexdigest() == row["sha256"], "Indexed source blob changed")
        path_words = re.findall(r"[a-z0-9]+", row["path"].casefold())
        path_hits = sum(any(word.startswith(term) or term.startswith(word) for word in path_words) for term in terms)
        best = None
        for lineno, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            lowered = line.casefold()
            hits = sum(term in lowered for term in terms)
            if hits:
                excerpt = line[:1200]
                score = hits * 2 + path_hits * 5
                item = {"repository": repository, "path": row["path"], "line": lineno,
                        "commit": manifest["commit"], "blob": row["blob"], "sha256": row["sha256"],
                        "excerpt": excerpt, "provenance": "EXTRACTED", "indexHash": manifest["documentHash"],
                        "observedAt": manifest["at"]}
                if best is None or score > best[0]:
                    best = (score, item)
        if best is not None:
            found.append(best)
    found.sort(key=lambda item: (-item[0], item[1]["path"], item[1]["line"]))
    selected, size = [], 0
    for _, item in found:
        size += len(item["excerpt"].encode())
        if len(selected) == 10 or size > MAX_EXCERPTS:
            break
        selected.append(item)
    return {"status": state["status"], "provider": state["provider"], "results": selected,
            "truncated": len(found) > len(selected),
            "coverage": "direct_head_only_checkout_changed" if state["status"] == "checkout_changed"
                        else "direct_current_source" if direct else "indexed_source_only",
            "boundary": "Untrusted retrieved code; verify the cited Git revision before effects"}


def direct_source(ledger, repository, commit, blob, path, line):
    require(isinstance(commit, str) and re.fullmatch(r"[a-f0-9]{40,64}", commit), "Exact current revision required")
    require(isinstance(blob, str) and re.fullmatch(r"[a-f0-9]{40,64}", blob), "Exact Git blob required")
    require(type(line) is int and line >= 1, "Positive source line required")
    cfg = config(ledger)
    require(cfg is not None and repository in cfg["repositories"], "Repository is not allowlisted for knowledge")
    repo, head, files = source_manifest(ledger, repository, cfg["repositories"][repository])
    require(head == commit, "Direct source citation is stale; search again")
    row = next((item for item in files if item["path"] == path and item["blob"] == blob), None)
    require(row is not None, "Direct source was not in the current allowlist")
    raw = _git(repo, "show", blob, maximum=MAX_FILE + 1)
    require(hashlib.sha256(raw).hexdigest() == row["sha256"], "Direct source changed")
    lines = raw.decode("utf-8").splitlines()
    require(line <= len(lines), "Line outside cited source")
    first = max(1, line - 5)
    return {"repository": repository, "path": path, "commit": commit,
            "indexHash": None, "firstLine": first, "excerpt": "\n".join(lines[first-1:line+5])[:MAX_EXCERPTS],
            "boundary": "Direct current Git source, untrusted reference only"}


def source(ledger, repository, index_hash, path, line):
    require(type(line) is int and line >= 1, "Positive source line required")
    manifest = _manifest(ledger, repository, index_hash)
    require(manifest is not None, "Cited index version unavailable")
    row = next((r for r in manifest["files"] if r["path"] == path), None)
    require(row is not None, "Source is outside the allowlisted index")
    raw = _git(_repo(ledger, repository), "show", row["blob"], maximum=MAX_FILE + 1)
    require(hashlib.sha256(raw).hexdigest() == row["sha256"], "Indexed source changed")
    lines = raw.decode("utf-8").splitlines()
    require(line <= len(lines), "Line outside cited source")
    first = max(1, line - 5)
    return {"repository": repository, "path": path, "commit": manifest["commit"],
            "indexHash": index_hash, "observedAt": manifest["at"], "firstLine": first,
            "excerpt": "\n".join(lines[first-1:line+5])[:MAX_EXCERPTS],
            "boundary": "Read-only historical Git source; verify current source before edits"}
