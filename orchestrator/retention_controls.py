"""Explicit owner policy previews; no controller, native effects or shared-store setup."""
import contextlib
import copy
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid

from . import missions, retention_policy as policy, run_authority as runs
from .admission import exact, integer, sha
from .core import Refusal, canonical, digest, require

TTL = 300
INVALID = (Refusal, KeyError, TypeError, ValueError, RecursionError)
REVIEW = {"runHash", "expectedPolicyHash", "maxArchives", "minimumRetentionSeconds"}
BOUNDARY = "Retention delegation only. No task is archived, Play enabled or native activity inspected."


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate retention request field")
            result[key] = value
        return result
    def invalid(_): raise Refusal("Finite JSON required")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def identity(ledger):
    stat = ledger.db.stat()
    return digest([str(ledger.root), stat.st_dev, stat.st_ino])


def metadata(db, doc, attempts):
    grant = runs.document(db, doc["runHash"], "run_authorization")
    return {k: doc[k] for k in ("version", "phaseId", "runHash", "maxArchives", "minimumRetentionSeconds", "at")} | {
        "policyHash": digest(doc), "generation": grant["generation"], "expiresAt": grant["expiresAt"],
        "recordedAttempts": sum(d["runHash"] == doc["runHash"] for d in attempts)}


def inspect_in(ledger, db):
    meta = ledger.get(db, "meta", 1)
    out = {"workspaceId": missions.workspace(ledger), "workspaceRevision": meta["revision"], "inspectedAt": time.time(),
           "status": "unavailable", "policy": None, "history": [], "omittedHistory": 0, "currentRun": None,
           "canReview": False, "canRevoke": False, "reviewBlocker": "Retained policy or run evidence needs operator review.",
           "executionAuthorized": False, "nativeCallMade": False, "boundary": BOUNDARY}
    try:
        count, size = db.execute("SELECT count(*),coalesce(sum(length(CAST(data AS BLOB))),0) FROM snapshots WHERE kind=?", (policy.POLICY,)).fetchone()
        require(count <= policy.MAX_HISTORY and size <= 2_000_000, "Retention history bound")
        latest = policy.latest_in(ledger, db); attempts = policy.inventory_in(ledger, db)
        if latest:
            require(type(meta.get("retentionPolicyRevoked")) is bool, "Missing policy revocation state")
            out["policy"] = metadata(db, latest, attempts) | {"revoked": meta["retentionPolicyRevoked"]}
        for row in db.execute("SELECT id FROM snapshots WHERE kind=? ORDER BY rowid DESC LIMIT 20", (policy.POLICY,)):
            doc = policy.policy_in(db, row[0])
            require(doc["workspaceId"] == out["workspaceId"] and doc["brainId"] == meta["brainId"], "Foreign policy history")
            out["history"].append(metadata(db, doc, attempts))
        out.update(status="recorded" if latest else "not_delegated", omittedHistory=max(0, count-20),
                   canRevoke=latest is not None and not meta["retentionPolicyRevoked"],
                   reviewBlocker="No current authorized run. Mission review alone does not authorize a run; Play remains separately gated.")
        try:
            state = runs.current_in(ledger, db)
            require(state is not None, "No run")
            grant = runs.require_current(ledger, db, state["runHash"])
            out["currentRun"] = {"runHash": state["runHash"], "generation": grant["generation"], "phaseId": grant["phaseId"],
                                 "expiresAt": grant["expiresAt"], "maxArchives": min(64, grant["authority"]["maxTasks"])}
            if grant["authority"]["approvalMode"] != "phase_delegated":
                out["reviewBlocker"] = "This run requires exact owner task approvals. A newly reviewed phase-delegated mission/run is required."
            elif meta["paused"] is not True:
                out["reviewBlocker"] = "Review is available only during paused run setup. Pausing an active run fences it; a new run then needs checkpoint release."
            else:
                out.update(canReview=True, reviewBlocker=None)
        except INVALID:
            pass  # Retained policy remains revocable even when its run is no longer current.
        if out["policy"]:
            out["policy"]["matchesCurrentRun"] = bool(out["currentRun"] and out["currentRun"]["runHash"] == latest["runHash"])
    except INVALID:
        out.update(status="unavailable", policy=None, history=[], currentRun=None, canReview=False, canRevoke=False)
    out["contextHash"] = digest({k: out[k] for k in ("workspaceId", "workspaceRevision", "status", "policy", "currentRun", "canReview", "canRevoke")})
    return out


def inspect(ledger):
    with contextlib.closing(sqlite3.connect(ledger.db.as_uri()+"?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row; db.execute("BEGIN")
        return inspect_in(ledger, db)


def summary(report, revision):
    """Closed cache projection: no hashes, paths, IDs, reasons, rationale or proof bodies."""
    if not report: return {"status": "not_inspected", "executionAuthorized": False}
    value = {k: report[k] for k in ("status", "workspaceRevision", "inspectedAt", "executionAuthorized")}
    value.update(historical=True, workspaceChanged=revision != report["workspaceRevision"],
                 expired=not 0 <= time.time()-report["inspectedAt"] <= 60)
    retained = report["policy"]
    if retained:
        value["policy"] = {k: retained[k] for k in ("version", "maxArchives", "minimumRetentionSeconds", "at", "expiresAt", "recordedAttempts", "revoked", "matchesCurrentRun")}
    return value


def assistant_summary(cached):
    out = {k: cached[k] for k in ("status", "workspaceRevision", "inspectedAt", "executionAuthorized", "historical", "workspaceChanged", "expired") if k in cached}
    if cached.get("policy"):
        out["policy"] = {k: cached["policy"][k] for k in ("version", "maxArchives", "minimumRetentionSeconds", "at", "expiresAt", "recordedAttempts", "revoked", "matchesCurrentRun") if k in cached["policy"]}
    return out


class RetentionControls:
    def __init__(self): self.key = secrets.token_bytes(32)

    def sign(self, doc): return hmac.new(self.key, canonical(doc).encode(), hashlib.sha256).hexdigest()

    def preview(self, ledger, request, session):
        request = copy.deepcopy(request)
        require(isinstance(request, dict) and request.get("operation") in ("review", "revoke"), "Retention review or revoke required")
        operation = request["operation"]
        exact(request, {"operation", "expectedRevision", "contextHash", *(REVIEW if operation == "review" else {"policyHash", "reason"})})
        integer(request["expectedRevision"]); sha(request["contextHash"])
        report = inspect(ledger)
        require(report["status"] != "unavailable" and request["contextHash"] == report["contextHash"] and
                request["expectedRevision"] == report["workspaceRevision"], "Workspace changed; inspect retention again")
        fields = {k: v for k, v in request.items() if k not in ("operation", "contextHash")}
        if operation == "review":
            require(report["canReview"], report["reviewBlocker"])
            require(request["runHash"] == report["currentRun"]["runHash"] and request["expectedPolicyHash"] ==
                    (report["policy"]["policyHash"] if report["policy"] else None), "Exact inspected run and policy required")
            integer(request["maxArchives"], 1, report["currentRun"]["maxArchives"])
            integer(request["minimumRetentionSeconds"], 0, 86400)
            fields.update(confirmed=True, allowManagedWorktreeCleanup=True)
        else:
            require(report["canRevoke"] and request["policyHash"] == report["policy"]["policyHash"], "Exact revocable policy required")
            missions.text(request["reason"], "Revocation reason")
        fields["id"] = str(uuid.uuid4())
        now = time.time()
        doc = {"operation": operation, "request": fields, "workspaceId": report["workspaceId"], "ledgerIdentity": identity(ledger),
               "session": digest(session), "contextHash": report["contextHash"], "createdAt": now, "expiresAt": now+TTL,
               "run": report["currentRun"] if operation == "review" else report["policy"], "boundary": BOUNDARY}
        return {"document": doc, "signature": self.sign(doc)}

    def confirm(self, ledger, body, session):
        body = copy.deepcopy(body)
        exact(body, {"proposal", "confirmed", "cleanupAcknowledged"})
        require(body["confirmed"] is True and type(body["cleanupAcknowledged"]) is bool, "Explicit owner confirmation required")
        exact(body["proposal"], {"document", "signature"})
        doc = body["proposal"]["document"]; signature = body["proposal"]["signature"]; sha(signature)
        require(hmac.compare_digest(signature, self.sign(doc)), "Preview changed or dashboard restarted; inspect and preview again")
        require(doc["session"] == digest(session) and doc["workspaceId"] == missions.workspace(ledger) and
                doc["ledgerIdentity"] == identity(ledger), "Preview belongs to another session or workspace")
        operation = doc["operation"]; request = doc["request"]
        require(body["cleanupAcknowledged"] is (operation == "review"), "Explicit cleanup acknowledgment required for delegation")
        fields = REVIEW | {"confirmed", "allowManagedWorktreeCleanup"} if operation == "review" else {"policyHash", "reason"}
        with ledger.tx() as db:
            _, _, _, prior = runs.request_in(ledger, db, request, "dashboard_owner", "retention_"+operation, fields)
            if prior: return {"receipt": prior, "replayed": True, "nativeCallMade": False}
            require(0 <= time.time()-doc["createdAt"] <= TTL and time.time() <= doc["expiresAt"], "Preview expired; inspect and preview again")
            require(inspect_in(ledger, db)["contextHash"] == doc["contextHash"], "Workspace changed; inspect and preview again")
            method = policy.review_in if operation == "review" else policy.revoke_in
            receipt = method(ledger, db, request, actor="dashboard_owner")
            return {"receipt": receipt, "replayed": False, "nativeCallMade": False}
