"""Explicit owner policy controls; no native/provider calls or automatic choice."""
import contextlib
import copy
import hmac
import sqlite3
import time
import uuid

from . import missions, model_policy as models, run_authority as runs, task_contracts
from .admission import exact, integer, sha
from .core import Refusal, canonical, digest, require
from .retention_controls import RetentionControls, identity, TTL

INVALID = (Refusal, KeyError, TypeError, ValueError, RecursionError)
CHOICES = {"profiles", "qualityFloors", "maxEscalations"}
BOUNDARY = "Policy only. Existing run authority is fenced; no task settings, usage, native task or Play is changed."


def history_in(ledger, db):
    count, size = db.execute("SELECT count(*),coalesce(sum(length(CAST(data AS BLOB))),0) FROM snapshots WHERE kind='model_policy'").fetchone()
    require(count <= 128 and size <= 2_000_000, "Policy history needs explicit bounded migration")
    meta = ledger.get(db, "meta", 1); history = []; previous = None
    for row in db.execute("SELECT id FROM snapshots WHERE kind='model_policy' ORDER BY rowid"):
        doc = models.policy_in(ledger, db, {"mode": "adaptive", "policyHash": row[0]}, current=False)
        require(doc["previousHash"] == previous, "Policy history chain changed")
        previous = row[0]
        history.append({"policyHash": row[0], **{k: doc[k] for k in ("at", "missionHash", "reviewReceiptHash", "catalogHash", "profiles", "qualityFloors", "maxEscalations")}})
    require(meta.get("modelPolicyHash") == previous, "Policy pointer changed; operator recovery required")
    if previous:
        require(type(meta.get("modelPolicyRevoked")) is bool and type(meta.get("modelPolicyCatalogInvalidated")) is bool,
                "Policy status missing; operator recovery required")
    return list(reversed(history))


def inspect_in(ledger, db):
    meta = ledger.get(db, "meta", 1)
    out = {"workspaceId": missions.workspace(ledger), "workspaceRevision": meta["revision"], "inspectedAt": time.time(),
        "status": "unavailable", "paused": meta["paused"], "capability": None, "capabilityStatus": "not_recorded",
        "candidate": None, "policy": None, "history": [], "canReview": False, "canRevoke": False,
        "reviewBlocker": "Policy history is unavailable; ask the operator to reconcile it.",
        "policyIssue": None, "executionAuthorized": False, "nativeCallMade": False, "boundary": BOUNDARY}
    try:
        out["history"] = history_in(ledger, db)
        if out["history"]:
            out["policy"] = out["history"][0] | {"revoked": meta["modelPolicyRevoked"],
                "catalogInvalidated": meta["modelPolicyCatalogInvalidated"]}
            out["canRevoke"] = not meta["modelPolicyRevoked"]
            try: models.policy_in(ledger, db, {"mode": "adaptive", "policyHash": meta["modelPolicyHash"]})
            except INVALID as error:
                out["policyIssue"] = str(error) if isinstance(error, Refusal) else "Policy evidence needs reconciliation."
        out["status"] = "recorded"
        try:
            require(meta.get("modelCapabilityHash") is not None, "Ask the designated brain to record the actual local model/effort catalog. This page cannot collect or invent it.")
            out["capabilityStatus"] = "unavailable"
            cap = models.capability_in(ledger, db, current=False)
            out["capability"] = {"capabilityHash": digest(cap), "catalogHash": cap["catalogHash"], "version": cap["version"],
                "observedAt": cap["observedAt"], "catalog": cap["catalog"], "trustBoundary": cap["trustBoundary"]}
            out["capabilityStatus"] = "stale"
            models.fresh(cap["observedAt"], models.CAP_AGE); out["capabilityStatus"] = "fresh_recorded"
            source = runs.mission_source(ledger, db); task_contracts.reviewed_phase(source)
            m = source["mission"]
            out["candidate"] = {"missionHash": m["documentHash"], "reviewReceiptHash": m["receiptHash"],
                "phaseId": m["document"]["spec"]["phase"]["id"], "mission": m["document"]}
            require(meta["paused"] is True, "Pause dispatch before reviewing a policy. For active work, use safe workspace Pause and reconcile its checkpoint first.")
            require(len(out["history"]) < 128, "Policy history limit reached; explicit migration required")
            require(any(e != "ultra" for row in cap["catalog"]["models"] for e in row["efforts"]), "No qualified model/effort combination is recorded")
            out.update(canReview=True, reviewBlocker=None)
        except INVALID as error:
            out["reviewBlocker"] = str(error) if isinstance(error, Refusal) else "Mission or model evidence is invalid; ask the operator to reconcile it."
    except INVALID:
        out.update(status="unavailable", history=[], policy=None, canReview=False, canRevoke=False)
    out["contextHash"] = digest({k: v for k, v in out.items() if k not in ("inspectedAt", "reviewBlocker", "policyIssue")})
    require(len(canonical(out).encode()) <= 128000, "Policy inspection exceeds its bound; operator migration required")
    return out


def readonly(ledger):
    db = sqlite3.connect(ledger.db.as_uri()+"?mode=ro", uri=True); db.row_factory = sqlite3.Row
    db.execute("BEGIN"); return contextlib.closing(db)


def inspect(ledger):
    with readonly(ledger) as db: return inspect_in(ledger, db)


def summary(report, revision):
    if not report: return {"status": "not_inspected", "executionAuthorized": False}
    return {"status": report["status"], "workspaceRevision": report["workspaceRevision"], "inspectedAt": report["inspectedAt"],
        "historical": True, "workspaceChanged": revision != report["workspaceRevision"],
        "expired": not 0 <= time.time()-report["inspectedAt"] <= 60, "executionAuthorized": False,
        "recordedPolicies": len(report["history"]), "revoked": report["policy"]["revoked"] if report["policy"] else None,
        "recordedProfiles": len(report["policy"]["profiles"]) if report["policy"] else 0,
        "capabilityStatusAtInspection": report["capabilityStatus"]}


class ModelControls(RetentionControls):
    def preview(self, ledger, body, session):
        body = copy.deepcopy(body)
        require(isinstance(body, dict) and body.get("operation") in ("review", "revoke"), "Model policy review or revocation required")
        op = body["operation"]
        exact(body, {"operation", "expectedRevision", "contextHash", *(CHOICES if op == "review" else {"policyHash", "reason"})})
        integer(body["expectedRevision"]); sha(body["contextHash"])
        with readonly(ledger) as db:
            report = inspect_in(ledger, db)
            require(report["status"] == "recorded" and body["expectedRevision"] == report["workspaceRevision"] and
                    body["contextHash"] == report["contextHash"], "Workspace changed; inspect model policy again")
            req = {"id": str(uuid.uuid4()), "expectedRevision": body["expectedRevision"]}
            if op == "review":
                require(report["canReview"], report["reviewBlocker"])
                req.update({k: body[k] for k in CHOICES}, **{k: report["candidate"][k] for k in ("missionHash", "reviewReceiptHash")},
                    capabilityHash=report["capability"]["capabilityHash"], confirmed=True)
                runs.request_in(ledger, db, req, "dashboard_owner", "model_policy_review", models.REVIEW_FIELDS)
                models.validate_review_in(ledger, db, req)
            else:
                require(report["canRevoke"] and body["policyHash"] == report["policy"]["policyHash"], "Exact current non-revoked policy required")
                sha(body["policyHash"]); missions.text(body["reason"], "Non-secret revocation reason")
                req.update(policyHash=body["policyHash"], reason=body["reason"])
            now = time.time()
            doc = {"kind": "model_policy_owner_preview", "operation": op, "request": req,
                "scope": {"mission": report["candidate"], "capability": report["capability"], "previousPolicy": report["policy"]},
                "workspaceId": report["workspaceId"], "ledgerIdentity": identity(ledger), "session": digest(session),
                "contextHash": report["contextHash"], "createdAt": now, "expiresAt": now+TTL, "boundary": BOUNDARY}
            require(len(canonical(doc).encode()) <= 28000, "Policy preview exceeds its bound; narrow the profiles or mission")
            return {"document": doc, "signature": self.sign(doc)}

    def confirm(self, ledger, body, session):
        body = copy.deepcopy(body); exact(body, {"proposal", "confirmed"})
        require(body["confirmed"] is True, "Explicit owner confirmation required")
        exact(body["proposal"], {"document", "signature"})
        doc = body["proposal"]["document"]; signature = body["proposal"]["signature"]; sha(signature)
        require(hmac.compare_digest(signature, self.sign(doc)), "Preview changed or dashboard restarted; inspect saved policy before preparing again")
        require(doc["kind"] == "model_policy_owner_preview" and doc["session"] == digest(session) and
                doc["workspaceId"] == missions.workspace(ledger) and doc["ledgerIdentity"] == identity(ledger), "Preview belongs to another session or workspace")
        op, req = doc["operation"], doc["request"]
        fields = models.REVIEW_FIELDS if op == "review" else {"policyHash", "reason"}
        with ledger.tx() as db:
            _, _, _, prior = runs.request_in(ledger, db, req, "dashboard_owner", "model_policy_"+op, fields)
            if not prior:
                require(0 <= time.time()-doc["createdAt"] <= TTL and time.time() <= doc["expiresAt"], "Preview expired; inspect and preview again")
                require(inspect_in(ledger, db)["contextHash"] == doc["contextHash"], "Workspace changed; inspect model policy again")
            receipt = (models.review if op == "review" else models.revoke)(ledger, req, actor="dashboard_owner", _db=db)
            # The original policy bytes must still be intact, including on replay.
            models.policy_in(ledger, db, {"mode": "adaptive", "policyHash": receipt["policyHash"]}, current=False)
            return {"receipt": receipt, "replayed": prior is not None, "executionAuthorized": False, "nativeCallMade": False}
