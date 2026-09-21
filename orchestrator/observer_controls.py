"""Owner endpoint setup and saved metadata; never connects or invokes a process."""
import contextlib
import copy
import functools
import hmac
import json
import sqlite3
import time
import uuid

from . import budget_views as views, native_evidence as evidence, run_authority as runs
from .admission import exact, identifier, integer, sha
from .core import Refusal, canonical, digest, require
from .native_read_client import inspect_endpoint
from .retention_controls import RetentionControls, TTL

INVALID = (Refusal, OSError, sqlite3.Error, KeyError, TypeError, ValueError, RecursionError)
KIND = "native_evidence_endpoint"
BOUNDARY = "Approve only a future bounded native metadata read. No connection, task, model call, usage change or Play is started."
GAP_LABELS = {
    "complete_task_tree_source_unavailable": "Complete ephemeral task membership is unavailable.",
    "lifetime_token_counter_source_unavailable": "Full-lifetime task token counters are unavailable.",
    "os_process_cleanup_source_unavailable": "Whole-process-tree cleanup is not verified.",
    "per_turn_settings_telemetry_unavailable": "Configured settings are not per-turn execution telemetry.",
}


def safe_io(method):
    @functools.wraps(method)
    def guarded(*args, **kwargs):
        try: return method(*args, **kwargs)
        except (OSError, sqlite3.Error):
            raise Refusal("Observer storage or endpoint is unavailable or busy; inspect saved state before retrying.") from None
    return guarded


@contextlib.contextmanager
def locked_file(path):
    """No DDL or setup: lock an existing private database, registry -> local -> shared."""
    before = views.file_identity(path)
    with contextlib.closing(sqlite3.connect(path.as_uri()+"?mode=rw", uri=True, timeout=2, isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA trusted_schema=OFF"); db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            require(before == views.file_identity(path), "Database identity changed")
            db.commit()
        except BaseException:
            db.rollback(); raise


def identities(registry, ledger):
    return {"registry": digest([str(registry.root), *views.file_identity(registry.db)]),
            "ledger": digest([str(ledger.root), *views.file_identity(ledger.db)])}


def scope_in(registry, reg, ledger, db, wid):
    row = reg.execute("SELECT root,brain,data FROM workspaces WHERE id=?", (wid,)).fetchone()
    meta = ledger.get(db, "meta", 1)
    require(row and row[0] == str(ledger.root) and row[1] == meta["brainId"] and
            json.loads(row[2])["databaseIdentity"] == list(views.file_identity(ledger.db)) and
            runs.missions.workspace(ledger) == wid, "Workspace registration or brain changed")
    return meta


def endpoint_history(ledger, db, wid):
    count, size = db.execute("SELECT count(*),coalesce(sum(length(CAST(data AS BLOB))),0) FROM snapshots WHERE kind=?", (KIND,)).fetchone()
    require(count <= 1000 and size <= 2_000_000, "Endpoint history needs explicit migration")
    previous, history = None, []
    meta = ledger.get(db, "meta", 1)
    for n, row in enumerate(db.execute("SELECT id FROM snapshots WHERE kind=? ORDER BY rowid", (KIND,)), 1):
        doc = runs.document(db, row[0], KIND)
        require(doc["previousHash"] == previous and doc["version"] == n and doc["workspaceId"] == wid and
                doc["brainId"] == meta["brainId"] and doc["actor"] == "dashboard_owner", "Endpoint history changed")
        previous = row[0]; history.append({"endpointHash": previous, **doc})
    require(meta.get("nativeEvidenceEndpointHash") == previous, "Endpoint pointer changed")
    require(not previous or type(meta.get("nativeEvidenceEndpointRevoked")) is bool, "Endpoint revocation marker missing")
    return list(reversed(history))


def base_in(ledger, db, wid):
    meta = ledger.get(db, "meta", 1)
    out = {"workspaceId": wid, "workspaceRevision": meta["revision"], "inspectedAt": time.time(),
        "status": "unavailable", "endpoint": None, "history": [], "omittedHistory": 0, "allocations": [],
        "sharedStatus": "unavailable", "reports": [], "reportsStatus": "not_inspected", "omittedReports": 0,
        "canReview": False, "canRevoke": False, "reviewBlocker": "Endpoint evidence requires operator recovery.",
        "gaps": GAP_LABELS, "nativeCallMade": False, "executionAuthorized": False, "boundary": BOUNDARY}
    try:
        history = endpoint_history(ledger, db, wid)
        out.update(status="recorded", history=history[:20], omittedHistory=max(0, len(history)-20))
        if history:
            out["endpoint"] = history[0] | {"revoked": meta["nativeEvidenceEndpointRevoked"]}
            out["canRevoke"] = not meta["nativeEvidenceEndpointRevoked"]
        out["reviewBlocker"] = "An existing open standard-policy allocation is required; this page does not create one."
        if len(history) >= 1000: out["reviewBlocker"] = "Endpoint history has reached its bound; explicit operator migration is required."
        if meta["paused"] is not True: out["reviewBlocker"] = "Pause dispatch before reviewing endpoint access."
    except INVALID:
        pass
    out["contextHash"] = digest({"workspaceId": wid, "revision": meta["revision"], "brainId": meta["brainId"],
        "paused": meta["paused"], "status": out["status"], "endpoint": out["endpoint"],
        "versions": len(out["history"])+out["omittedHistory"]})
    return out


def allocations_in(ledger, db, shared, wid):
    # Only scoped allocations can appear in the browser; bounds precede decoding.
    rows = views.objects(shared, "allocations")
    require(len(rows) <= 128, "Allocation inventory exceeds its bound")
    out = []
    for key, a in rows:
        if a["spec"]["workspaceId"] != wid: continue
        require(a["id"] == key and a["fingerprint"] == digest(a["spec"]) and type(a["closed"]) is bool, "Allocation binding changed")
        if a["closed"]: continue
        try: evidence.standard_in(ledger, db, a)
        except Refusal: continue
        out.append(a)
    return out


def allocation_scope(a):
    return {"allocationId": a["id"], "allocationFingerprint": a["fingerprint"],
            "repositories": sorted(a["spec"]["repositories"]), "closed": a["closed"]}


def saved_reports(db, wid, endpoint):
    count, size = db.execute("SELECT count(*),coalesce(sum(length(CAST(data AS BLOB))),0) FROM snapshots WHERE kind=?", (evidence.KIND,)).fetchone()
    require(count <= 1000 and size <= 8_000_000, "Observation history needs explicit migration")
    result = []
    for row in db.execute("SELECT id FROM snapshots WHERE kind=? ORDER BY rowid DESC LIMIT 20", (evidence.KIND,)):
        d = runs.document(db, row[0], evidence.KIND)
        require(d["workspaceId"] == wid and all(d[k] is False for k in evidence.BOUNDARY), "Observation evidence boundary changed")
        samples = d["samples"]; require(isinstance(samples, list) and len(samples) <= 64, "Observation sample bound")
        statuses = {k: sum(s["activity"] == k for s in samples) for k in ("idle", "running", "unknown")}
        require(sum(statuses.values()) == len(samples), "Invalid recorded activity")
        result.append({"reportHash": row[0], "allocationId": d["allocationId"], "version": d["version"],
            "startedAt": d["startedAt"], "finishedAt": d["finishedAt"], "sampleCount": len(samples),
            "activityCounts": statuses, "trackedTerminalCount": sum(len(s["trackedTerminals"]) for s in samples),
            "repeatReadStable": d["repeatReadStable"], "queriesAttempted": d["readOnlyNativeQueriesAttempted"],
            "stale": not 0 <= time.time()-d["startedAt"] <= 60,
            "endpointCurrent": bool(endpoint and not endpoint["revoked"] and d["endpointHash"] == endpoint["endpointHash"]),
            "effectContextChecked": False, "completeEvidence": False,
            "collectionUnavailable": "native_collection_unavailable" in d["issues"]})
    return result, max(0, count-20)


@safe_io
def inspect(registry, ledger, wid):
    with views.readonly(registry.db) as reg, views.readonly(ledger.db) as db:
        db.row_factory = sqlite3.Row; meta = scope_in(registry, reg, ledger, db, wid)
        out = base_in(ledger, db, wid)
        try:
            out["reports"], out["omittedReports"] = saved_reports(db, wid, out["endpoint"])
            out["reportsStatus"] = "recorded"
        except INVALID: out["reportsStatus"] = "unavailable"
        try:
            with views.readonly(registry.root / "admission.sqlite3") as shared:
                out["allocations"] = [allocation_scope(a) for a in allocations_in(ledger, db, shared, wid)]
                out["sharedStatus"] = "recorded"
                if out["status"] == "recorded" and out["allocations"] and meta["paused"] is True and len(out["history"])+out["omittedHistory"] < 1000:
                    out.update(canReview=True, reviewBlocker=None)
        except INVALID:
            out["allocations"] = []
            if out["status"] == "recorded" and meta["paused"] is True:
                out["reviewBlocker"] = "Shared allocation evidence is unavailable. This page never initializes or repairs accounting."
        require(len(canonical(out).encode()) <= 128000, "Observation inspection exceeds its bound; operator recovery required")
        return out


def summary(report, revision):
    if not report: return {"status": "not_inspected", "executionAuthorized": False}
    return {"status": report["status"], "workspaceRevision": report["workspaceRevision"], "inspectedAt": report["inspectedAt"],
        "historical": True, "workspaceChanged": revision != report["workspaceRevision"],
        "expired": not 0 <= time.time()-report["inspectedAt"] <= 60, "executionAuthorized": False,
        "endpointReviewed": report["endpoint"] is not None, "endpointRevoked": report["endpoint"]["revoked"] if report["endpoint"] else None,
        "reportsStatus": report["reportsStatus"], "savedReportCount": len(report["reports"])+report["omittedReports"],
        "completeEvidence": False}


class ObserverControls(RetentionControls):
    @safe_io
    def preview(self, registry, ledger, wid, body, session):
        body = copy.deepcopy(body)
        require(isinstance(body, dict) and body.get("operation") in ("review", "revoke"), "Endpoint review or revocation required")
        op = body["operation"]
        exact(body, {"operation", "expectedRevision", "contextHash", *({"allocationId", "executable", "socket", "serverIdentityHash"} if op == "review" else {"endpointHash"})})
        integer(body["expectedRevision"]); sha(body["contextHash"])
        with views.readonly(registry.db) as reg, views.readonly(ledger.db) as db:
            db.row_factory = sqlite3.Row; scope_in(registry, reg, ledger, db, wid)
            report = base_in(ledger, db, wid)
            require(report["status"] == "recorded" and report["contextHash"] == body["contextHash"] and
                    report["workspaceRevision"] == body["expectedRevision"], "Workspace changed; inspect observer setup again")
            req = {"id": str(uuid.uuid4()), "expectedRevision": body["expectedRevision"]}; allocation = None; shared_id = None
            if op == "review":
                require(ledger.get(db, "meta", 1)["paused"] is True, "Pause dispatch before reviewing endpoint access")
                require(len(report["history"])+report["omittedHistory"] < 1000, "Endpoint history needs explicit migration")
                identifier(body["allocationId"])
                path = registry.root / "admission.sqlite3"
                with views.readonly(path) as shared:
                    candidates = {a["id"]: a for a in allocations_in(ledger, db, shared, wid)}
                    require(body["allocationId"] in candidates, "Exact open standard-policy allocation required")
                    a = candidates[body["allocationId"]]; allocation = allocation_scope(a); shared_id = [str(v) for v in views.file_identity(path)]
                    endpoint = inspect_endpoint(body["executable"], body["socket"], body["serverIdentityHash"])
                    req.update(allocationId=a["id"], endpoint=endpoint, confirmed=True)
                    runs.request_in(ledger, db, req, "dashboard_owner", "native_endpoint_review", {"allocationId", "endpoint", "confirmed"})
                    evidence.validate_endpoint_review_in(ledger, db, wid, a, req)
                    # Nanosecond timestamps exceed JavaScript's exact integer range.
                    # Sign lossless decimal strings; restore only after HMAC verification.
                    req["endpoint"]["socketIdentity"] = {k: str(v) for k, v in endpoint["socketIdentity"].items()}
            else:
                sha(body["endpointHash"])
                require(report["canRevoke"] and body["endpointHash"] == report["endpoint"]["endpointHash"], "Exact current endpoint required")
                req["endpointHash"] = body["endpointHash"]
            now = int(time.time())
            doc = {"kind": "native_observer_owner_preview", "workspaceId": wid, "identities": identities(registry, ledger),
                "session": digest(session), "operation": op, "request": req, "contextHash": body["contextHash"],
                "allocation": allocation, "sharedIdentity": shared_id, "createdAt": now, "expiresAt": now+TTL, "boundary": BOUNDARY}
            require(len(canonical(doc).encode()) <= 28000, "Endpoint preview exceeds its bound")
            return {"document": doc, "signature": self.sign(doc)}

    @safe_io
    def confirm(self, registry, ledger, wid, body, session):
        body = copy.deepcopy(body); exact(body, {"proposal", "confirmed"})
        require(body["confirmed"] is True, "Explicit owner confirmation required")
        exact(body["proposal"], {"document", "signature"})
        doc = body["proposal"]["document"]; signature = body["proposal"]["signature"]; sha(signature)
        require(hmac.compare_digest(signature, self.sign(doc)), "Preview changed or dashboard restarted; inspect saved setup before preparing again")
        require(doc["kind"] == "native_observer_owner_preview" and doc["session"] == digest(session) and doc["workspaceId"] == wid and
                doc["identities"] == identities(registry, ledger), "Preview belongs to another session, registry or workspace")
        op, req = doc["operation"], doc["request"]
        req = copy.deepcopy(req)
        if op == "review":
            req["endpoint"]["socketIdentity"] = {k: int(v) for k, v in req["endpoint"]["socketIdentity"].items()}
        fields = {"allocationId", "endpoint", "confirmed"} if op == "review" else {"endpointHash"}
        with locked_file(registry.db) as reg, ledger.tx() as db:
            scope_in(registry, reg, ledger, db, wid)
            _, _, _, prior = runs.request_in(ledger, db, req, "dashboard_owner", "native_endpoint_"+op, fields)
            if prior:
                runs.document(db, prior["endpointHash"], KIND)
                return {"receipt": prior, "replayed": True, "nativeCallMade": False, "executionAuthorized": False}
            require(0 <= time.time()-doc["createdAt"] <= TTL and time.time() <= doc["expiresAt"], "Preview expired; inspect and preview again")
            require(base_in(ledger, db, wid)["contextHash"] == doc["contextHash"], "Workspace changed; inspect observer setup again")
            if op == "review":
                path = registry.root / "admission.sqlite3"
                require([str(v) for v in views.file_identity(path)] == doc["sharedIdentity"], "Shared store identity changed")
                with locked_file(path) as shared:
                    candidates = {a["id"]: a for a in allocations_in(ledger, db, shared, wid)}
                    a = candidates.get(req["allocationId"])
                    require(a is not None and allocation_scope(a) == doc["allocation"], "Reviewed allocation changed")
                    receipt = evidence.review_endpoint_in(ledger, db, wid, a, req, actor="dashboard_owner")
                    require(doc["identities"] == identities(registry, ledger) and [str(v) for v in views.file_identity(path)] == doc["sharedIdentity"], "Store identity changed")
                    db.commit()  # Shared allocation remains write-locked until the local receipt is durable.
            else:
                receipt = evidence.revoke_endpoint(ledger, req, actor="dashboard_owner", _db=db)
            return {"receipt": receipt, "replayed": False, "nativeCallMade": False, "executionAuthorized": False}
