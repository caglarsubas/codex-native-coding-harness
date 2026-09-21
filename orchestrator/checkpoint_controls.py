"""Authenticated owner adapter; no run grant, native call, notification or scheduler."""
import contextlib
import copy
import hmac
import sqlite3
import time
import uuid

from . import missions, model_policy, phase_checkpoints as phases, run_authority as runs, task_contracts
from .admission import exact, integer, sha
from .core import Refusal, canonical, digest, require
from .retention_controls import RetentionControls, identity, TTL

INVALID = (Refusal, KeyError, TypeError, ValueError, RecursionError)
REVIEW_INPUT = {"reportHash", "artifactId", "missionHash", "reviewReceiptHash", "settingsPolicy", "expiresInSeconds"}
BOUNDARY = "Owner review only. No run is authorized or resumed; admission, maintenance and native evidence gates remain."


def inspect_in(ledger, db):
    meta = ledger.get(db, "meta", 1)
    out = {"workspaceId": missions.workspace(ledger), "workspaceRevision": meta["revision"], "inspectedAt": time.time(),
           "status": "unavailable", "candidate": None, "reviews": [], "canReview": False,
           "reviewBlocker": "Checkpoint review history is unavailable; ask the operator to reconcile it.",
           "executionAuthorized": False, "nativeCallMade": False, "boundary": BOUNDARY}
    try:
        count, size = db.execute("SELECT count(*),coalesce(sum(length(CAST(data AS BLOB))),0) FROM snapshots WHERE kind=?", (phases.REVIEW,)).fetchone()
        require(count <= 128 and size <= 2_000_000, "Checkpoint review history needs bounded migration")
        withdrawn = phases.withdrawals_in(ledger, db)
        for row in db.execute("SELECT id FROM snapshots WHERE kind=? ORDER BY rowid DESC", (phases.REVIEW,)):
            record = phases.owner_review_in(ledger, db, row[0]); req = record["request"]
            out["reviews"].append({"checkpointReviewHash": row[0], "at": record["at"], "withdrawn": row[0] in withdrawn,
                "withdrawnAt": phases.document(db, withdrawn[row[0]], phases.WITHDRAWAL)["at"] if row[0] in withdrawn else None,
                **{k: req[k] for k in ("reportHash", "artifactId", "missionHash", "reviewReceiptHash", "settingsPolicy", "expiresAt")}})
        out["status"] = "recorded"
        try:
            pointer = meta.get("phaseCheckpointReport")
            require(pointer is not None, "No phase report is saved. Ask the designated brain to prepare one after a safe checkpoint.")
            exact(pointer, {"reportHash", "artifactId"})
            source = runs.mission_source(ledger, db); task_contracts.reviewed_phase(source)
            m = source["mission"]
            req = {**pointer, "missionHash": m["documentHash"], "reviewReceiptHash": m["receiptHash"],
                   "settingsPolicy": "native_defaults", "expiresAt": time.time()+3600, "confirmed": True}
            phases.validate_review_in(ledger, db, req)
            settings = [{"value": "native_defaults", "label": "Native defaults · no model override", "policy": None}]
            if meta.get("modelPolicyHash"):
                try:
                    value = {"mode": "adaptive", "policyHash": meta["modelPolicyHash"]}
                    policy = model_policy.policy_in(ledger, db, value)
                    settings.append({"value": value, "label": "Current owner-reviewed adaptive policy", "policy": policy})
                except INVALID: pass  # Invalid optional settings are never silently selected.
            report = phases.read_in(ledger, db, pointer["reportHash"], pointer["artifactId"])["report"]
            info, _ = phases.artifact_bytes(db, pointer["artifactId"])
            out["candidate"] = {**pointer, "reportVersion": info["version"], "generation": report["generation"],
                "reportAt": report["retainedAt"], "checkpointAt": report["checkpointAt"], "summary": report["summary"],
                "missionHash": m["documentHash"], "reviewReceiptHash": m["receiptHash"], "mission": m["document"], "settings": settings}
            require(count < 128, "Review history limit reached; explicit migration required before another review")
            out.update(canReview=True, reviewBlocker=None)
        except INVALID as error:
            out["reviewBlocker"] = str(error) if isinstance(error, Refusal) else "Saved checkpoint or next mission evidence is invalid. Ask the brain/operator to reconcile it."
    except INVALID:
        out.update(status="unavailable", candidate=None, reviews=[], canReview=False)
    out["contextHash"] = digest({k: out[k] for k in ("workspaceId", "workspaceRevision", "status", "candidate", "reviews", "canReview")})
    return out


def inspect(ledger):
    with contextlib.closing(sqlite3.connect(ledger.db.as_uri()+"?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row; db.execute("BEGIN")
        return inspect_in(ledger, db)


def summary(report, revision):
    if not report: return {"status": "not_inspected", "executionAuthorized": False}
    return {"status": report["status"], "workspaceRevision": report["workspaceRevision"], "inspectedAt": report["inspectedAt"],
            "historical": True, "workspaceChanged": revision != report["workspaceRevision"],
            "expired": not 0 <= time.time()-report["inspectedAt"] <= 60, "executionAuthorized": False,
            "recordedReviews": len(report["reviews"]), "recordedWithdrawals": sum(r["withdrawn"] for r in report["reviews"])}


class CheckpointControls(RetentionControls):
    """Reuse ephemeral signing only; each feature/workspace has its own random key."""
    def preview(self, ledger, body, session):
        body = copy.deepcopy(body)
        require(isinstance(body, dict) and body.get("operation") in ("review", "withdraw"), "Checkpoint review or withdrawal required")
        op = body["operation"]
        exact(body, {"operation", "expectedRevision", "contextHash", *(REVIEW_INPUT if op == "review" else {"checkpointReviewHash", "reason"})})
        integer(body["expectedRevision"]); sha(body["contextHash"])
        report = inspect(ledger)
        require(report["status"] == "recorded" and body["expectedRevision"] == report["workspaceRevision"] and
                body["contextHash"] == report["contextHash"], "Workspace changed; inspect checkpoint decisions again")
        now = time.time()
        request = {"id": str(uuid.uuid4()), "expectedRevision": body["expectedRevision"], "confirmed": True}
        if op == "review":
            require(report["canReview"], report["reviewBlocker"])
            c = report["candidate"]
            require(all(body[k] == c[k] for k in ("reportHash", "artifactId", "missionHash", "reviewReceiptHash")), "Exact inspected report and next mission required")
            require(any(body["settingsPolicy"] == s["value"] for s in c["settings"]), "Select an available settings policy explicitly")
            integer(body["expiresInSeconds"], 60, 86400)
            request.update({k: body[k] for k in REVIEW_INPUT if k != "expiresInSeconds"}, expiresAt=now+body["expiresInSeconds"])
            scope = c
        else:
            sha(body["checkpointReviewHash"]); missions.text(body["reason"], "Withdrawal reason")
            scope = next((r for r in report["reviews"] if r["checkpointReviewHash"] == body["checkpointReviewHash"]), None)
            require(scope and not scope["withdrawn"], "Exact non-withdrawn review required")
            request.update(checkpointReviewHash=body["checkpointReviewHash"], reason=body["reason"])
        doc = {"kind": "checkpoint_owner_preview", "operation": op, "request": request, "scope": scope,
               "workspaceId": report["workspaceId"], "ledgerIdentity": identity(ledger), "session": digest(session),
               "contextHash": report["contextHash"], "createdAt": now, "expiresAt": now+TTL, "boundary": BOUNDARY}
        require(len(canonical(doc).encode()) <= 28000, "Checkpoint preview exceeds its bound; narrow the reviewed mission")
        return {"document": doc, "signature": self.sign(doc)}

    def confirm(self, ledger, body, session):
        body = copy.deepcopy(body); exact(body, {"proposal", "confirmed"})
        require(body["confirmed"] is True, "Explicit owner confirmation required")
        exact(body["proposal"], {"document", "signature"})
        doc = body["proposal"]["document"]; signature = body["proposal"]["signature"]; sha(signature)
        require(hmac.compare_digest(signature, self.sign(doc)), "Preview changed or dashboard restarted; inspect saved decisions before preparing again")
        require(doc["kind"] == "checkpoint_owner_preview" and doc["session"] == digest(session) and
                doc["workspaceId"] == missions.workspace(ledger) and doc["ledgerIdentity"] == identity(ledger), "Preview belongs to another session or workspace")
        op, req = doc["operation"], doc["request"]
        fields = phases.REVIEW_FIELDS if op == "review" else {"checkpointReviewHash", "reason", "confirmed"}
        with ledger.tx() as db:
            _, _, _, prior = runs.request_in(ledger, db, req, "dashboard_owner", "phase_"+op, fields)
            if not prior:
                require(0 <= time.time()-doc["createdAt"] <= TTL and time.time() <= doc["expiresAt"], "Preview expired; inspect and preview again")
                require(inspect_in(ledger, db)["contextHash"] == doc["contextHash"], "Workspace changed; inspect checkpoint decisions again")
            method = phases.review_in if op == "review" else phases.withdraw_in
            receipt = method(ledger, db, req, actor="dashboard_owner")
            return {"receipt": receipt, "replayed": prior is not None, "executionAuthorized": False, "nativeCallMade": False}
