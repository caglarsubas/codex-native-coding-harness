"""Owner-confirmed, fail-closed platform enrollment (WSP-04B1).

Enrollment fences legacy launch paths and journals existing ownership. It does
not activate a mission, import owners as free capacity, or authorize a native
effect. Cross-database writes are recoverable stages, never called atomic.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time

from .core import Ledger, canonical, digest, require
from .workspaces import inspect_ledger, private_path

FENCE_FILE = "admission-fence.json"
REASON = "Workspace enrollment fences new dispatch. Run activation and the native admission bridge are not enabled; reconcile retained owners."
EFFECT = "Fence new dispatch until explicit migration. No activation or native action; this version has no unfence command."


def fence_exists(root):
    path = Path(root) / FENCE_FILE
    return path.exists() or path.is_symlink()


def projection(ledger, meta):
    binding = meta.get("admissionBinding")
    blocked = "admissionBinding" in meta or fence_exists(ledger.root)
    return {"state": "fenced" if isinstance(binding, dict) else "fencing" if blocked else "not_enrolled",
            "dispatchBlocked": blocked, "activationAvailable": False,
            "enrollmentId": binding.get("enrollmentId") if isinstance(binding, dict) else None,
            "workspaceId": binding.get("workspaceId") if isinstance(binding, dict) else None,
            "reason": REASON if blocked else "Legacy exact-owner workflow; shared admission is not connected."}


def require_legacy_unfenced(ledger, meta):
    require(not projection(ledger, meta)["dispatchBlocked"], REASON)


def record_in(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='admission_enrollment'").fetchone():
        return None
    row = db.execute("SELECT data FROM admission_enrollment WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


def require_registration_open(db):
    require(record_in(db) is None, "Platform enrollment has started; workspace membership needs an explicit migration")


def members_in(db):
    result = []
    for row in db.execute("SELECT id,root,brain,data FROM workspaces ORDER BY id"):
        stored = json.loads(row["data"])
        inspected = inspect_ledger(row["root"])
        require(inspected["brainId"] == row["brain"] and inspected["databaseIdentity"] == stored["databaseIdentity"],
                "Workspace identity changed; explicit recovery required")
        result.append({"id": row["id"], "root": row["root"], "brainId": row["brain"],
                       "databaseIdentity": stored["databaseIdentity"]})
    require(0 < len(result) <= 32, "Enroll 1–32 registered workspaces")
    return result


def registry_identity(registry):
    private_path(registry.root, existing=True)
    info = registry.db.stat()
    require(not registry.db.is_symlink() and stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and info.st_mode & 0o077 == 0 and info.st_nlink == 1, "Registry must remain a private regular database")
    return digest({"root": str(registry.root), "database": [info.st_dev, info.st_ino]})


def observe(ledger, db, member):
    meta = ledger.get(db, "meta", 1)
    require(meta["brainId"] == member["brainId"], "Workspace brain identity changed")
    workers = ledger.all(db, "workers")
    repos = {r["id"]: r for r in ledger.all(db, "repos")}
    owners = [{"workerId": w["id"], "repositoryId": w["repository"], "status": w["status"],
               "threadId": w.get("threadId"), "clientThreadId": w.get("clientThreadId"),
               "hostId": w.get("hostId"), "seedHash": w.get("seedHash"),
               "repositoryBindingHash": digest(repos[w["repository"]]) if w["repository"] in repos else None}
              for w in workers if w["status"] != "complete"]
    runner = meta.get("runner")
    commands = ledger.all(db, "commands")
    # No prompt, arbitrary observation text, local path or controller token enters
    # the manifest. Hash exact records so changed evidence still invalidates review.
    source = {"revision": meta["revision"], "brainId": meta["brainId"], "paused": meta["paused"],
              "controllerPresent": meta.get("controller") is not None, "binding": meta.get("admissionBinding"),
              "repositories": ledger.all(db, "repos"), "workers": workers, "runner": runner,
              "queue": ledger.all(db, "queue"), "commands": commands}
    return {"workspaceId": member["id"], "brainId": member["brainId"], "ledgerRevision": meta["revision"],
            "sourceHash": digest(source), "paused": meta["paused"], "controllerPresent": source["controllerPresent"],
            "fenced": projection(ledger, meta)["dispatchBlocked"],
            "enrollmentState": projection(ledger, meta)["state"], "owners": owners,
            "runner": {"workerId": runner.get("workerId"), "recordHash": digest(runner)} if runner else None,
            "queuedResumeCount": sum(c["kind"] == "resume" and c["status"] in ("queued", "processing") for c in commands)}


@contextlib.contextmanager
def locked_ledgers(members):
    # Lock ordering is registry first, then workspace ID. Ordinary workspace
    # operations never acquire the registry while holding a workspace write lock.
    with contextlib.ExitStack() as stack:
        locked = []
        for member in members:
            ledger = Ledger(member["root"])
            db = stack.enter_context(ledger.tx())
            locked.append((member, ledger, db))
        yield locked


def preview(registry):
    with registry.tx() as db:
        require_registration_open(db)
        members = members_in(db)
        with locked_ledgers(members) as locked:
            observations = [observe(ledger, conn, member) for member, ledger, conn in locked]
    now = time.time()
    document = {"schemaVersion": 1, "kind": "platform_enrollment_preview", "observedAt": now,
                "expiresAt": now + 300, "registryIdentity": registry_identity(registry),
                "membershipHash": digest(members), "workspaces": observations,
                "effect": EFFECT}
    return {"documentHash": digest(document), "document": document}


def save_record(db, record, kind, **extra):
    db.execute("UPDATE admission_enrollment SET data=? WHERE id=1", (canonical(record),))
    db.execute("INSERT INTO admission_enrollment_events(data) VALUES(?)",
               (canonical({"at": time.time(), "kind": kind, "enrollmentId": record["id"], **extra}),))


def retain_owners(record, observations):
    # A later missing/completed ledger row is not a native terminal observation.
    # Keep every seen owner binding and runner record; future adoption must
    # reconcile these identities, not interpret a smaller current list as release.
    retained = {digest(row): row for row in record.get("retainedOwnership", [])}
    for row in observations:
        for owner in row["owners"]:
            value = {"workspaceId": row["workspaceId"], "kind": "worker", **owner}
            retained[digest(value)] = value
        if row["runner"]:
            value = {"workspaceId": row["workspaceId"], "kind": "runner", **row["runner"]}
            retained[digest(value)] = value
    record["retainedOwnership"] = list(retained.values())


def read_fence(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
            "Enrollment fence must be a private regular file; retain it for explicit recovery")
    require(info.st_size <= 4096, "Invalid enrollment fence; retain it for explicit recovery")
    with path.open("rb") as handle:
        raw = handle.read(4097)
    require(len(raw) <= 4096, "Invalid enrollment fence")
    return raw


def durable_fence(root, binding):
    """Publish without overwrite; any surviving file fences all launch paths.

    A linked staging file may remain after a crash. Its matching final fence is
    sufficient; recovery never deletes an operator file or releases ownership.
    """
    path = root / FENCE_FILE
    raw = canonical(binding).encode()
    if fence_exists(root):
        require(read_fence(path) == raw, "Enrollment fence identity changed; explicit recovery required")
        return
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".enrollment-", delete=False) as staged:
            name = Path(staged.name)
            staged.write(raw); staged.flush(); os.fsync(staged.fileno())
        try:
            os.link(name, path)
        except FileExistsError:
            require(read_fence(path) == raw, "Enrollment fence identity changed; explicit recovery required")
        directory = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if name is not None:
            name.unlink(missing_ok=True)


def stage_workspace(record, member, ledger, db):
    binding = {"schemaVersion": 1, "enrollmentId": record["id"], "workspaceId": member["id"],
               "registryIdentity": record["registryIdentity"], "membershipHash": record["membershipHash"],
               "state": "fenced", "activationAvailable": False}
    meta = ledger.get(db, "meta", 1)
    require(meta["controller"] is None and meta["paused"] is True,
            "Pause dispatch and release every workspace controller before enrollment or recovery")
    prior = meta.get("admissionBinding")
    require("admissionBinding" not in meta or prior == binding, "Workspace belongs to a different enrollment")
    durable_fence(ledger.root, binding)  # survives a later SQLite rollback/restore
    if prior is None:
        meta["admissionBinding"] = binding
        ledger.put(db, "meta", 1, meta)
        for command in ledger.all(db, "commands"):
            if command["kind"] == "resume" and command["status"] in ("queued", "processing"):
                command.update(status="rejected", result="Superseded by explicit platform enrollment; dispatch remains fenced.")
                ledger.put(db, "commands", command["id"], command)
        ledger.event(db, "platform_enrollment_fenced", {"enrollmentId": record["id"], "workspaceId": member["id"]})
    db.commit()  # intentional stage boundary, not a cross-database atomic claim


def finish(registry, registry_db, record, locked):
    # The registry journal is already durable. Workspace transactions are held
    # before it is prepared; each fence commits independently and can be replayed.
    for member, ledger, db in locked:
        stage_workspace(record, member, ledger, db)
    # Earlier workspace locks were released by their commits. Observations below
    # are therefore diagnostic records, not a global point-in-time/native snapshot.
    observations = []
    for member, ledger, db in locked:
        db.execute("BEGIN")
        observations.append(observe(ledger, db, member))
        db.commit()
    record.update(state="fenced", fencedAt=time.time(), observedOwners=observations)
    registry_db.execute("BEGIN IMMEDIATE")
    saved = record_in(registry_db)
    require(saved and saved["id"] == record["id"], "Enrollment journal identity changed")
    record["retainedOwnership"] = saved["retainedOwnership"]
    retain_owners(record, record["observedOwners"])
    save_record(registry_db, record, "enrollment_fenced", observations=record["observedOwners"])
    return public(record)


def public(record):
    if not record:
        return {"state": "not_enrolled", "activationAvailable": False, "executionAuthorized": False}
    return {key: record[key] for key in ("id", "state", "registryIdentity", "membershipHash", "createdAt",
                                        "previewHash", "observedOwners", "retainedOwnership", "activationAvailable", "executionAuthorized")}


def apply(registry, request):
    require(isinstance(request, dict) and set(request) == {"id", "confirmed", "preview"}, "Invalid enrollment request")
    from .admission import identifier
    identifier(request["id"])
    require(request["confirmed"] is True, "Explicit owner confirmation required")
    selected = request["preview"]
    require(isinstance(selected, dict) and set(selected) == {"documentHash", "document"}, "Exact enrollment preview required")
    document = selected["document"]
    require(isinstance(document, dict) and selected["documentHash"] == digest(document), "Enrollment preview hash mismatch")
    request_hash = digest(request)
    with registry.tx() as db:
        prior = record_in(db)
        if prior:
            require(prior["id"] == request["id"] and prior["requestHash"] == request_hash, "Enrollment already exists; recover its exact ID")
            # Never blindly replay incomplete staging from a submit retry.
            return public(prior)
        require(set(document) == {"schemaVersion", "kind", "observedAt", "expiresAt", "registryIdentity", "membershipHash", "workspaces", "effect"}
                and document["schemaVersion"] == 1 and document["kind"] == "platform_enrollment_preview", "Invalid enrollment preview contract")
        require(document["effect"] == EFFECT, "Enrollment effect must match the maintenance-only fence contract")
        at, until, now = document["observedAt"], document["expiresAt"], time.time()
        require(type(at) in (int, float) and type(until) in (int, float) and math.isfinite(at) and math.isfinite(until)
                and 0 <= now - at <= 300 and until == at + 300 and now <= until, "Fresh enrollment preview required")
        require(document["registryIdentity"] == registry_identity(registry), "Registry identity changed")
        members = members_in(db)
        require(document["membershipHash"] == digest(members), "Workspace membership changed; review a new preview")
        with locked_ledgers(members) as locked:
            current = [observe(ledger, conn, member) for member, ledger, conn in locked]
            require(current == document["workspaces"], "Workspace state changed; review a new enrollment preview")
            require(all(row["paused"] is True and not row["controllerPresent"] and not row["fenced"] for row in current),
                    "Pause dispatch and release all controllers before enrollment; existing workers stay owned")
            record = {"id": request["id"], "state": "prepared", "registryIdentity": document["registryIdentity"],
                      "membershipHash": digest(members), "members": members, "createdAt": now,
                      "requestHash": request_hash, "previewHash": selected["documentHash"],
                      "observedOwners": current, "activationAvailable": False, "executionAuthorized": False}
            retain_owners(record, current)
            db.execute("CREATE TABLE admission_enrollment(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)")
            db.execute("CREATE TABLE admission_enrollment_events(seq INTEGER PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("INSERT INTO admission_enrollment VALUES(1,?)", (canonical(record),))
            save_record(db, record, "enrollment_prepared", preview=selected)
            db.commit()  # journal precedes every per-workspace side effect
            return finish(registry, db, record, locked)


def recover(registry, enrollment_id, *, confirmed=False):
    require(confirmed is True, "Explicit owner confirmation required to resume enrollment fencing")
    with registry.tx() as db:
        record = record_in(db)
        require(record and record["id"] == enrollment_id, "Unknown enrollment ID")
        require(record["registryIdentity"] == registry_identity(registry), "Registry identity changed; explicit recovery required")
        members = members_in(db)
        require(digest(members) == record["membershipHash"], "Workspace identity/membership changed; explicit migration required")
        with locked_ledgers(members) as locked:
            # Recovery is permitted to capture new observations, never to grant
            # capacity. Revalidate identities and idle controllers, retain owners.
            require(all(ledger.get(conn, "meta", 1)["paused"] is True and
                        ledger.get(conn, "meta", 1)["controller"] is None for _, ledger, conn in locked),
                    "Pause dispatch and release all controllers before recovery")
            db.commit()
            return finish(registry, db, record, locked)


def status(registry):
    with registry.tx() as db:
        record = record_in(db)
        result = public(record)
        if record:
            require(record["registryIdentity"] == registry_identity(registry), "Registry identity changed; explicit recovery required")
            members = members_in(db)
            require(digest(members) == record["membershipHash"], "Workspace identity/membership changed")
            result["workspaces"] = []
            for member in members:
                ledger = Ledger(member["root"])
                with contextlib.closing(ledger.connect()) as connection:
                    connection.execute("BEGIN")
                    result["workspaces"].append(observe(ledger, connection, member))
            result["historyEntries"] = db.execute("SELECT count(*) FROM admission_enrollment_events").fetchone()[0]
            result["reason"] = REASON
        return result
