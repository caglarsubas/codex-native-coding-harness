"""Private workspace registry. Registration never changes an existing ledger."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sqlite3
import time
import uuid

from .core import LEDGER_VERSIONS, Ledger, Refusal, canonical, digest, require, supported_ledger_metadata

IDENTITY = re.compile(r"[a-z][a-z0-9-]{0,47}\Z")
PROFILE_KEYS = {"goal", "successCriteria", "architecture", "techStack", "roadmap", "references"}


def identity(value):
    require(isinstance(value, str) and bool(IDENTITY.fullmatch(value)), "Invalid workspace ID")
    return value


def private_path(path, *, existing=False):
    path = Path(path).absolute()
    require(path == path.resolve(), "Use a canonical path without symlinks or traversal")
    if existing:
        require(path.is_dir(), "Workspace state directory is unavailable")
    if path.exists():
        require(path.is_dir() and path.stat().st_uid == os.getuid(), "State directory must belong to the local owner")
        require(path.stat().st_mode & 0o077 == 0, "State directory must be private (mode 700)")
    return path


def private_database(path):
    """Validate an existing private SQLite file, not a 64KiB runtime record.

    Read only the fixed header. Database growth is legitimate; callers validate
    schema/rows through their bounded read-only transaction and pin the inode.
    This does not initialize, checkpoint, repair or open a SQLite writer.
    """
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path,
            'Use a canonical private database path without symlinks')
    for parent in path.parents:
        info = parent.stat()
        require(info.st_uid in (0, os.getuid()) and
                (not info.st_mode & 0o022 or info.st_uid == 0 and info.st_mode & stat.S_ISVTX),
                'Unsafe private database ancestor')
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and
            not before.st_mode & 0o077 and before.st_nlink == 1,
            'Private regular database without write aliases required')
    fields = ('st_dev', 'st_ino', 'st_uid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    identity = lambda info: tuple(getattr(info, field) for field in fields)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        require(identity(os.fstat(fd)) == identity(before), 'Private database changed before read')
        require(os.pread(fd, 16, 0) == b'SQLite format 3\x00', 'Existing SQLite database required')
        require(identity(os.fstat(fd)) == identity(path.lstat()) == identity(before),
                'Private database changed during inspection')
    finally:
        os.close(fd)
    return path


def inspect_ledger(root):
    root = private_path(root, existing=True)
    path = root / "ledger.sqlite3"
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1,
            "Existing regular ledger database required")
    require(path.stat().st_uid == os.getuid() and path.stat().st_mode & 0o077 == 0,
            "Ledger database must be private (mode 600)")
    try:
        with contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            row = db.execute("SELECT data FROM meta WHERE id=1").fetchone()
            require(row is not None, "Ledger metadata missing")
            meta = json.loads(row[0])
            require(supported_ledger_metadata(meta), "Unsupported ledger schema")
            brain = meta.get("brainId")
            require(isinstance(brain, str) and 0 < len(brain) <= 200, "Configure the existing workspace brain first")
            repos = [json.loads(r[0]) for r in db.execute("SELECT data FROM repos ORDER BY id")]
    except (sqlite3.Error, ValueError, KeyError) as error:
        raise Refusal("Workspace ledger is unavailable or invalid") from error
    stat = path.stat()
    return {"brainId": brain, "revision": meta["revision"], "repositories": repos,
            "databaseIdentity": [stat.st_dev, stat.st_ino],
            "admissionFenced": "admissionBinding" in meta or (root / "admission-fence.json").exists()
                or (root / "admission-fence.json").is_symlink()}


def fingerprint(db):
    """Logical checksums only. Never publish records, credentials or local paths."""
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    result = {}
    for table in tables:
        require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table) is not None, "Unsupported ledger table")
        # Retained artifact bodies are SQLite BLOBs; hash bytes without decoding
        # or emitting them. SQLite scalar values cannot collide with this tag.
        rows = sorted(canonical([{"blobSHA256": hashlib.sha256(value).hexdigest(), "bytes": len(value)}
                                 if isinstance(value, bytes) else value for value in row])
                      for row in db.execute('SELECT * FROM "' + table + '"'))
        result[table] = {"rows": len(rows), "sha256": digest(rows)}
    return result


def validate_profile(value):
    require(isinstance(value, dict) and set(value) == PROFILE_KEYS, "Expected the six project profile fields")
    for key in ("goal", "architecture", "roadmap"):
        require(isinstance(value[key], str) and len(value[key]) <= 4000, "Invalid profile " + key)
    for key in ("successCriteria", "techStack", "references"):
        require(isinstance(value[key], list) and len(value[key]) <= 30 and
                all(isinstance(item, str) and 0 < len(item.strip()) <= 1000 for item in value[key]),
                "Invalid profile " + key)
    require(len(canonical(value).encode()) <= 16000, "Project profile is too large")
    return value


class Registry:
    def __init__(self, root, *, create=False, read_only=False):
        require(not (create and read_only), 'Read-only registry cannot be created')
        self.read_only = read_only
        self.root = private_path(root, existing=not create)
        if create:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = self.root / "platform.sqlite3"
        require(not self.db.is_symlink(), "Registry symlink refused")
        if not create:
            require(self.db.is_file(), "Workspace registry is not initialized")
        if self.db.exists():
            require(self.db.stat().st_uid == os.getuid() and self.db.stat().st_mode & 0o077 == 0
                    and self.db.stat().st_nlink == 1, "Registry must be a private regular database")
        elif create:
            os.close(os.open(self.db, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        with self.tx() as db:
            if create:
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS registry_meta(id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER);
                    INSERT OR IGNORE INTO registry_meta VALUES(1,1);
                    CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY, name TEXT NOT NULL,
                        root TEXT UNIQUE NOT NULL, brain TEXT UNIQUE NOT NULL, data TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS profiles(workspace TEXT NOT NULL, version INTEGER NOT NULL,
                        data TEXT NOT NULL, PRIMARY KEY(workspace,version));
                """)
            row = db.execute("SELECT version FROM registry_meta WHERE id=1").fetchone()
            require(row and row[0] == 1, "Unsupported workspace registry version")

    @contextlib.contextmanager
    def tx(self):
        db = (sqlite3.connect(self.db.as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=10)
              if self.read_only else sqlite3.connect(self.db, isolation_level=None, timeout=10))
        db.row_factory = sqlite3.Row
        try:
            if self.read_only:
                db.execute('PRAGMA query_only=ON')
                db.execute('BEGIN')
            else:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def preview(self, workspace_id, name, root):
        identity(workspace_id)
        require(isinstance(name, str) and 0 < len(name.strip()) <= 100, "Workspace name required (1–100 characters)")
        inspected = inspect_ledger(root)
        require(not inspected["admissionFenced"], "Fenced workspace belongs to an enrollment; explicit migration required")
        with self.tx() as db:
            from .enrollment import require_registration_open
            require_registration_open(db)
            rows = list(db.execute("SELECT * FROM workspaces"))
        for row in rows:
            require(row["id"] != workspace_id and row["root"] != str(Path(root).absolute()) and
                    row["brain"] != inspected["brainId"], "Workspace ID, ledger or brain already registered")
            other = Path(row["root"])
            candidate = Path(root).absolute()
            require(not candidate.is_relative_to(other) and not other.is_relative_to(candidate),
                    "Workspace state roots must not overlap")
        return {"id": workspace_id, "name": name.strip(), "brainId": inspected["brainId"],
                "ledgerRevision": inspected["revision"], "repositoryCount": len(inspected["repositories"]),
                "changesLedger": False, "startsWork": False}

    def register(self, workspace_id, name, root):
        preview = self.preview(workspace_id, name, root)
        root = private_path(root, existing=True)
        inspected = inspect_ledger(root)
        # SQLite backup includes committed WAL data; copying just the db file does not.
        backups = self.root / "backups"
        backups.mkdir(mode=0o700, exist_ok=True)
        private_path(backups, existing=True)
        backup_id = str(uuid.uuid4())
        backup_path = backups / (backup_id + ".sqlite3")
        os.close(os.open(backup_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        with contextlib.closing(sqlite3.connect((root / "ledger.sqlite3").as_uri() + "?mode=ro", uri=True)) as source:
            with contextlib.closing(sqlite3.connect(backup_path)) as target:
                source.backup(target)
                require(target.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "Backup integrity check failed")
                proof = fingerprint(target)
                backed_meta = json.loads(target.execute("SELECT data FROM meta WHERE id=1").fetchone()[0])
                require(backed_meta["brainId"] == inspected["brainId"], "Brain changed during registration")
        data = {"id": workspace_id, "name": preview["name"], "brainId": inspected["brainId"],
                "registeredAt": time.time(), "databaseIdentity": inspected["databaseIdentity"],
                "backup": {"id": backup_id, "ledgerRevision": backed_meta["revision"], "tables": proof}}
        try:
            with self.tx() as db:
                # Recheck overlap inside the write transaction, including concurrent registrations.
                from .enrollment import require_registration_open
                require_registration_open(db)
                require(not inspect_ledger(root)["admissionFenced"], "Workspace enrollment changed during registration")
                for row in db.execute("SELECT root FROM workspaces"):
                    other = Path(row[0])
                    require(not root.is_relative_to(other) and not other.is_relative_to(root), "Workspace state roots must not overlap")
                db.execute("INSERT INTO workspaces VALUES(?,?,?,?,?)",
                           (workspace_id, preview["name"], str(root), inspected["brainId"], canonical(data)))
        except sqlite3.IntegrityError as error:
            raise Refusal("Workspace ID, ledger or brain already registered; verified backup retained") from error
        return self.public(data)

    @staticmethod
    def public(data):
        return {k: data[k] for k in ("id", "name", "brainId", "registeredAt")}

    def list(self):
        with self.read() as db:
            return [self.public(json.loads(row[0])) for row in db.execute("SELECT data FROM workspaces ORDER BY rowid")]

    def root_for(self, workspace_id):
        identity(workspace_id)
        with self.read() as db:
            row = db.execute("SELECT root,data FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        require(row is not None, "Unknown workspace")
        data = json.loads(row["data"])
        inspected = inspect_ledger(row["root"])
        require(inspected["brainId"] == data["brainId"] and inspected["databaseIdentity"] == data["databaseIdentity"],
                "Workspace identity changed; explicit recovery required")
        if os.path.lexists(Path(row['root'])/'empty-setup-transition.claim.json') or 'emptySetupTransition' in data:
            from .empty_setup_transition import retained
            receipt = retained(Path(row['root']))
            require(receipt is not None and data.get('emptySetupTransition') == receipt['reviewHash'] and
                inspected['brainId'] == receipt['request']['spec']['brainId'], 'Partial setup transition remains fenced')
        return Path(row["root"])

    @contextlib.contextmanager
    def read(self):
        """Status reads must not contend for the registry writer reservation.

        This snapshot is not an effect gate; all writers retain tx() and their
        transaction-bound authority/identity checks.
        """
        # Preserve an explicitly read-only registry's filesystem boundary. A
        # normal registry uses its existing read/write-capable handle so SQLite
        # can retire its own cold-WAL sidecars on close; query_only still forbids
        # SQL writes, and BEGIN (not IMMEDIATE) reserves no writer lock.
        db = (sqlite3.connect(self.db.as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=10)
              if self.read_only else sqlite3.connect(self.db, isolation_level=None, timeout=10))
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
            yield db
        finally:
            db.rollback(); db.close()

    def ledger(self, workspace_id):
        ledger = Ledger(self.root_for(workspace_id), read_only=self.read_only)
        ledger.workspace_id, ledger.platform_root = workspace_id, self.root
        return ledger

    def profile(self, workspace_id):
        self.root_for(workspace_id)
        with self.tx() as db:
            row = db.execute("SELECT data FROM profiles WHERE workspace=? ORDER BY version DESC LIMIT 1", (workspace_id,)).fetchone()
        return json.loads(row[0]) if row else {"version": 0, "hash": None, "profile": None, "updatedAt": None}

    def save_profile(self, workspace_id, value, expected_version):
        self.root_for(workspace_id)
        validate_profile(value)
        require(type(expected_version) is int and expected_version >= 0, "Profile version required")
        with self.tx() as db:
            row = db.execute("SELECT data FROM profiles WHERE workspace=? ORDER BY version DESC LIMIT 1", (workspace_id,)).fetchone()
            prior = json.loads(row[0]) if row else {"version": 0}
            require(prior["version"] == expected_version, "Project profile changed; review the current version")
            if prior.get("profile") == value:
                return prior
            record = {"version": expected_version + 1, "hash": digest(value), "profile": value, "updatedAt": time.time()}
            db.execute("INSERT INTO profiles VALUES(?,?,?)", (workspace_id, record["version"], canonical(record)))
            return record

    def verify_backup(self, workspace_id):
        identity(workspace_id)
        with self.tx() as db:
            row = db.execute("SELECT data FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        require(row is not None, "Unknown workspace")
        proof = json.loads(row[0])["backup"]
        private_path(self.root / "backups", existing=True)
        path = self.root / "backups" / (proof["id"] + ".sqlite3")
        require(path.is_file() and not path.is_symlink(), "Retained backup unavailable")
        with contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            valid = db.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and fingerprint(db) == proof["tables"]
        return {"workspaceId": workspace_id, "backupId": proof["id"], "verified": valid,
                "ledgerRevision": proof["ledgerRevision"], "restored": False}

    def summary(self, workspace_ids=None):
        """Recorded cross-workspace measurements only. Never scan or notify on read."""
        from .repository import aggregate
        from . import portfolio_metrics
        from .projects import catalog
        names = {p["id"]: p["name"] for p in catalog(self)["projects"] if p["managed"]}
        rows, repositories, sessions, workers, artifacts, roadmaps = [], [], {}, {}, {}, {}
        conflicts = set()
        for workspace in self.list():
            wid = workspace["id"]
            workspace = {**workspace, "name": names.get(wid, workspace["name"])}
            if workspace_ids is not None and wid not in workspace_ids:
                continue
            try:
                state = self.ledger(wid).snapshot()
            except Refusal:
                rows.append({**workspace, "status": "unavailable"})
                continue
            summary = aggregate(state)
            standard_run = state["meta"].get("standardRun")
            cooperative = None if not standard_run else {
                "status": standard_run["status"], "tasks": len(standard_run["tasks"]),
                "completed": sum(t["status"] == "completed" for t in standard_run["tasks"]),
                "active": sum(t["status"] not in ("completed", "failed", "not_created") for t in standard_run["tasks"])}
            usage = state["observations"].get("usage") or {}
            # No filesystem resolution on a summary read. Code identity was bound
            # at explicit collection; roadmaps retain their configured-path basis.
            repo_paths = {r["id"]: r["path"] for r in state["repositories"] if r.get("path")}
            repositories.extend({**m, "workspaceId": wid} for m in summary["repositories"])
            for session in usage.get("sessions", []):
                # A shared task can have partially observed history in two scopes.
                # Without event-level union, differing summaries cannot safely be added.
                key = session["id"]
                vector = {k: session[k] for k in ("input_tokens", "cached_input_tokens", "output_tokens",
                          "reasoning_output_tokens", "total_tokens", "userMessages", "assistantMessages", "samples")}
                if key in sessions and sessions[key] != vector:
                    conflicts.add(key)
                sessions[key] = vector
            for worker in state["workers"]:
                key = worker.get("threadId") or wid + ":" + worker["id"]
                workers.setdefault(key, []).append(worker["status"])
            for item in state["observations"].get("artifacts", []):
                key = (item["key"], item["version"], item["sha256"])
                if key not in artifacts or item["orderAt"] < artifacts[key]["orderAt"]:
                    artifacts[key] = {"workspaceId": wid, "workspace": workspace["name"],
                        **{k: item[k] for k in ("id", "name", "version", "orderAt")}}
            for plan in state["observations"].get("roadmaps", {}).get("plans", []):
                key = (repo_paths.get(plan["repository"], wid + ":" + plan["repository"]), plan["path"])
                if key not in roadmaps or plan.get("at", 0) > roadmaps[key]["at"]:
                    roadmaps[key] = {"workspaceId": wid, "workspace": workspace["name"], "title": plan.get("title") or plan["path"],
                        "at": plan.get("at", 0), "status": plan["status"], "total": len(plan.get("items", [])),
                        "checked": sum(bool(i["checked"]) for i in plan.get("items", []))}
            rows.append({**workspace, "status": "recorded", "revision": state["meta"]["revision"],
                "paused": state["meta"]["paused"], "lastReconciled": state["meta"]["lastReconciled"],
                "repositories": len(state["repositories"]), "metrics": summary["aggregate"],
                "codeCoverage": summary["coverage"],
                "cooperative": cooperative,
                "usage": usage.get("aggregate") if usage.get("status") == "measured" else None,
                "activeWorkers": sum(w["status"] not in ("complete", "settled") for w in state["workers"]),
                "settledWorkers": sum(w["status"] == "settled" for w in state["workers"]),
                "artifacts": len(state["observations"].get("artifacts", []))})
        code = portfolio_metrics.summarize(repositories)
        included = [value for key, value in sessions.items() if key not in conflicts and value["samples"]]
        totals = dict(code["aggregate"])
        totals.update(cooperativeTasks=sum((r.get("cooperative") or {}).get("tasks", 0) for r in rows),
                      cooperativeCompletedTasks=sum((r.get("cooperative") or {}).get("completed", 0) for r in rows))
        totals.update(managedTasks=len(workers), completedTasks=sum(all(s == "complete" for s in statuses) for statuses in workers.values()),
            settledTasks=sum(all(s == "settled" for s in statuses) for statuses in workers.values()),
            distinctObservedSessions=len(sessions), conflictingSessionsExcluded=len(conflicts),
            tokens=sum(s["total_tokens"] for s in included) if included else None,
            cachedInput=sum(s["cached_input_tokens"] for s in included) if included else None,
            uniqueArtifactVersions=len(artifacts))
        return {"observedAt": time.time(), "workspaces": rows, "aggregate": totals,
                "codeSnapshots": code["snapshots"], "codeCoverage": code["coverage"],
                "artifacts": sorted(artifacts.values(), key=lambda a: (a["orderAt"], a["workspaceId"], a["id"])),
                "roadmaps": list(roadmaps.values()),
                "method": code["method"] + " Tokens include identical task summaries once; conflicting shared-task summaries are excluded, not added. Cached input is part of input. Artifact identity is source key, version and content hash; roadmap identity remains configured checkout plus source path."}
