"""Retained native Codex project inventory, separate from execution ledgers.

Only an explicit import writes this catalog. No filesystem discovery, native
transport, registration, brain creation or authority changes happen here.
"""
import json
import time

from .core import digest, require

SOURCE = "codex.list_projects"
MAX_PROJECTS = 500


def text(value, limit=200):
    require(isinstance(value, str) and 0 < len(value) <= limit and
            not any(ord(c) < 32 for c in value), "Invalid native project metadata")
    return value


def normalize(result):
    require(isinstance(result, dict) and result.get("schemaVersion") == 2 and
            isinstance(result.get("projects"), list) and len(result["projects"]) <= MAX_PROJECTS,
            "Expected the complete schemaVersion 2 Codex list_projects result")
    rows, seen = [], set()
    for p in result["projects"]:
        require(isinstance(p, dict), "Invalid native project row")
        if p.get("projectKind") == "chatgpt":
            continue  # ChatGPT projects are a different product's namespace.
        require(p.get("projectKind") in ("local", "remote"), "Unsupported Codex project kind")
        pid, host = text(p.get("projectId")), text(p.get("hostId"))
        key = digest([host, pid])
        require(key not in seen, "Duplicate native project identity")
        seen.add(key)
        require(type(p.get("isGitRepository")) is bool, "Git repository observation required")
        path = text(p.get("path"), 4096)
        rows.append({"key": key, "id": "p-" + key[:40], "projectId": pid, "hostId": host,
                     "name": text(p.get("label")), "projectKind": p["projectKind"],
                     "isGitRepository": p["isGitRepository"], "locationHash": digest([host, path])})
    return rows


def _read(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_catalog'").fetchone():
        return None, {}
    row = db.execute("SELECT data FROM project_catalog WHERE id=1").fetchone()
    record = json.loads(row[0]) if row else None
    bindings = {r[0]: json.loads(r[1]) for r in db.execute("SELECT project_key,data FROM project_bindings")}
    return record, bindings


def record(registry, result, observed_at):
    rows = normalize(result)
    require(type(observed_at) in (int, float) and 0 < observed_at <= time.time() + 30,
            "Original native observation time required")
    with registry.tx() as db:
        previous, _ = _read(db)
        if previous:
            require(observed_at >= previous["observedAt"], "Older catalog cannot replace a newer observation")
            if observed_at == previous["observedAt"]:
                require(previous["hash"] == digest(rows), "Conflicting catalog at the same observation time")
                return previous
        db.execute("CREATE TABLE IF NOT EXISTS project_catalog(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS project_bindings(project_key TEXT PRIMARY KEY, workspace TEXT UNIQUE NOT NULL, data TEXT NOT NULL)")
        value = {"source": SOURCE, "observedAt": observed_at, "recordedAt": time.time(),
                 "hash": digest(rows), "projects": rows}
        db.execute("INSERT OR REPLACE INTO project_catalog VALUES(1,?)", (json.dumps(value),))
    return value


def bind(registry, workspace_id, host_id, project_id, catalog_hash):
    """Explicit owner mapping. Identity/location changes never silently retarget it."""
    key = digest([host_id, project_id])
    with registry.tx() as db:
        catalog, bindings = _read(db)
        require(catalog and catalog["hash"] == catalog_hash, "Review the current catalog hash before binding")
        project = next((p for p in catalog["projects"] if p["key"] == key), None)
        row = db.execute("SELECT data FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        require(project is not None and row is not None, "Exact saved project and registered ledger required")
        workspace = json.loads(row[0])
        value = {"workspaceId": workspace_id, "brainId": workspace["brainId"],
                 "databaseIdentity": workspace["databaseIdentity"], "locationHash": project["locationHash"]}
        require(key not in bindings or bindings[key] == value, "Existing project binding cannot be reassigned")
        require(not any(k != key and b["workspaceId"] == workspace_id for k, b in bindings.items()),
                "Ledger already belongs to a native project")
        db.execute("INSERT OR IGNORE INTO project_bindings VALUES(?,?,?)", (key, workspace_id, json.dumps(value)))
    return {"workspaceId": workspace_id, "projectId": project_id, "name": project["name"], "startsWork": False}


def catalog(registry, served=None):
    with registry.tx() as db:
        saved, bindings = _read(db)
        ledgers = {r[0]: json.loads(r[1]) for r in db.execute("SELECT id,data FROM workspaces ORDER BY rowid")
                   if served is None or r[0] in served}
    projects, linked = [], set()
    for p in saved["projects"] if saved else []:
        binding = bindings.get(p["key"])
        w = ledgers.get(binding["workspaceId"]) if binding else None
        matched = bool(w and all(binding[k] == w[k] for k in ("brainId", "databaseIdentity"))
                       and binding["locationHash"] == p["locationHash"])
        item = {k: p[k] for k in ("id", "projectId", "hostId", "name", "projectKind", "isGitRepository")}
        item.update(managed=matched, bindingStatus="linked" if matched else "needs_review" if binding else "not_configured")
        if matched:
            item.update(id=w["id"], brainId=w["brainId"])
            linked.add(w["id"])
        projects.append(item)
    # Keep old ledgers reachable without claiming they still appear in Codex.
    unlisted = [{"id": w["id"], "name": w["name"], "brainId": w["brainId"], "managed": True,
                 "bindingStatus": "not_listed"} for wid, w in ledgers.items() if wid not in linked]
    return {"source": SOURCE if saved else None, "observedAt": saved["observedAt"] if saved else None,
            "hash": saved["hash"] if saved else None, "projects": projects, "unlisted": unlisted,
            "status": "retained" if saved else "not_synced", "live": False}


def display_name(registry, workspace_id, fallback):
    return next((p["name"] for p in catalog(registry)["projects"] if p["id"] == workspace_id), fallback)
