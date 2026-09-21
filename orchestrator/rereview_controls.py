"""Explicit owner permission UI; never collects evidence or accepts a result."""
import contextlib
import copy
import hmac
import sqlite3
import time
import uuid

from . import missions, result_reauthorization as authority, result_review as results, run_authority as runs
from .admission import exact, identifier, integer, sha
from .core import Refusal, canonical, digest, require
from .ownership_settlement import OwnershipSettlement
from .retention_controls import RetentionControls, identity, TTL

INVALID = (Refusal, KeyError, TypeError, ValueError, RecursionError)
BOUNDARY = "Review permission only. No result is accepted, task resumed, budget reset or Play enabled."


def inspect_in(ledger, db, worker_id):
    identifier(worker_id)
    meta = ledger.get(db, "meta", 1)
    out = {"workspaceId": missions.workspace(ledger), "workspaceRevision": meta["revision"], "workerId": worker_id,
        "inspectedAt": time.time(), "status": "unavailable", "task": None, "candidate": None,
        "authority": None, "permissions": [], "reviews": [], "canAuthorize": False, "canRevoke": False,
        "blocker": "Result or permission evidence is unavailable. Ask the brain/operator to reconcile it.",
        "executionAuthorized": False, "nativeCallMade": False, "boundary": BOUNDARY}
    try:
        worker = ledger.get(db, "workers", worker_id)
        intent = runs.document(db, worker.get("dispatchAdmission", {}).get("intentHash"), "dispatch_intent")
        require(intent["workerId"] == worker_id and intent["workspaceId"] == out["workspaceId"], "Foreign result intent")
        runs.standard_handoff_scope(db, intent)
        current = authority.current_in(db, worker)
        for record in reversed(authority.history_in(db, worker_id)):
            require(record["workspaceId"] == out["workspaceId"], "Foreign permission history")
            out["permissions"].append({"authorityHash": digest(record), "status": record["status"], "at": record["at"],
                "expiresAt": record["expiresAt"], "reason": record["request"]["reason"]})
        if current:
            out["authority"] = out["permissions"][0] | {"consumed": current["status"] == "approved" and
                current["request"]["previousReviewHash"] != worker.get("resultReviewHash"),
                "expired": time.time() >= current["expiresAt"]}
            out["canRevoke"] = current["status"] == "approved"
        # An intact current permission remains revocable even when result proof
        # is damaged. Missing permission history itself never gains a fallback.
        out["status"] = "recorded"
        terminal = runs.document(db, worker.get("ownershipSettlementHash"), "ownership_settlement")
        require(terminal["workerId"] == worker_id and terminal["intentHash"] == digest(intent), "Settlement identity changed")
        old = None
        if worker.get("resultReviewHash"):
            old = results.reviewed_worker_in(db, worker, OwnershipSettlement.settled_claim(terminal), terminal)
        else:
            authority.settled_in(ledger, db, worker, intent)
        if old:
            for r in results.history_in(db, digest(old), intent, terminal):
                req = r["request"]
                out["reviews"].append({"reviewHash": digest(r), "outcome": req["outcome"], "commit": req["result"]["commit"],
                    "at": r["at"], "reviewArtifactId": req["reviewArtifactId"],
                    "axes": {k: p["status"] for k, p in req["result"]["evidence"].items()}})
        seed = runs.document(db, intent["seedHash"], "seed")
        out["task"] = {"packetId": worker["packetId"], "repository": intent["repository"], "status": worker["status"],
            "intentHash": digest(intent), "settlementHash": digest(terminal), "settledAt": terminal["at"],
            "previousReviewHash": digest(old) if old else None, "commit": old["request"]["result"]["commit"] if old else None,
            "originalRunHash": intent["runHash"], "seedHash": intent["seedHash"], "baseSHA": seed["baseSHA"],
            "allowedPaths": seed["allowedPaths"], "acceptance": seed["acceptance"]}
        out["status"] = "recorded"
        try:
            state = runs.current_in(ledger, db)
            require(state is not None, "No current authorized run; a reviewed mission alone is not run authority.")
            authority.scope_in(ledger, db, meta, worker, intent, state["runHash"])
            authority.settled_in(ledger, db, worker, intent)
            require(len(out["reviews"]) < 32, "Result history limit reached; explicit migration is required.")
            require(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (authority.KIND,)).fetchone()[0] < 127,
                    "Permission history limit reached; explicit migration is required.")
            grant = runs.document(db, state["runHash"], "run_authorization")
            mission = runs.document(db, grant["missionHash"], "mission_configuration")
            out["candidate"] = {"runHash": state["runHash"], "generation": grant["generation"], "phaseId": grant["phaseId"],
                "expiresAt": grant["expiresAt"], "missionHash": grant["missionHash"], "reviewReceiptHash": grant["reviewReceiptHash"],
                "goal": mission["spec"]["goal"], "scope": mission["spec"]["phase"]["scope"]}
            out.update(canAuthorize=True, blocker=None)
        except INVALID as error:
            out["blocker"] = str(error) if isinstance(error, Refusal) else "Current run or task scope is invalid. Ask the operator to reconcile it."
    except INVALID:
        out.update(task=None, candidate=None, reviews=[], canAuthorize=False)
        if out["status"] != "recorded":
            out.update(status="unavailable", authority=None, permissions=[], canRevoke=False)
    out["contextHash"] = digest({k: v for k, v in out.items() if k not in ("inspectedAt", "blocker")})
    require(len(canonical(out).encode()) <= 128000, "Result inspection exceeds its bound; use the operator's bounded evidence tools")
    return out


def inspect(ledger, worker_id):
    with contextlib.closing(sqlite3.connect(ledger.db.as_uri()+"?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row; db.execute("BEGIN")
        return inspect_in(ledger, db, worker_id)


def summary(report, revision):
    if not report: return {"status": "not_inspected", "executionAuthorized": False}
    return {"status": report["status"], "workspaceRevision": report["workspaceRevision"], "inspectedAt": report["inspectedAt"],
        "historical": True, "workspaceChanged": revision != report["workspaceRevision"],
        "expired": not 0 <= time.time()-report["inspectedAt"] <= 60, "executionAuthorized": False,
        "recordedVersions": len(report["reviews"]), "recordedPermissions": len(report["permissions"])}


class RereviewControls(RetentionControls):
    def preview(self, ledger, body, session):
        body = copy.deepcopy(body)
        require(isinstance(body, dict) and body.get("operation") in ("authorize", "revoke"), "Review permission authorization or revocation required")
        op = body["operation"]
        exact(body, {"operation", "workerId", "expectedRevision", "contextHash", "reason", *( {"commit"} if op == "authorize" else {"authorityHash"})})
        identifier(body["workerId"]); integer(body["expectedRevision"]); sha(body["contextHash"])
        missions.text(body["reason"], "Non-secret review permission reason")
        report = inspect(ledger, body["workerId"])
        require(report["status"] == "recorded" and body["expectedRevision"] == report["workspaceRevision"] and
                body["contextHash"] == report["contextHash"], "Workspace changed; inspect this result again")
        request = {"id": str(uuid.uuid4()), "expectedRevision": body["expectedRevision"], "workerId": body["workerId"],
                   "reason": body["reason"], "confirmed": True}
        if op == "authorize":
            require(report["canAuthorize"], report["blocker"]); results.commit(body["commit"])
            task = report["task"]
            require(body["commit"] != task["baseSHA"] and (task["commit"] is None or body["commit"] == task["commit"]),
                    "Use the exact unchanged result commit, not the base or a correction commit")
            request.update({k: task[k] for k in ("intentHash", "settlementHash", "previousReviewHash")},
                runHash=report["candidate"]["runHash"], commit=body["commit"])
        else:
            sha(body["authorityHash"])
            require(report["canRevoke"] and body["authorityHash"] == report["authority"]["authorityHash"], "Exact current review permission required")
            request["authorityHash"] = body["authorityHash"]
        now = time.time()
        doc = {"kind": "result_review_owner_preview", "operation": op, "request": request,
            "scope": {"task": report["task"], "run": report["candidate"], "authority": report["authority"]},
            "workspaceId": report["workspaceId"], "ledgerIdentity": identity(ledger), "session": digest(session),
            "contextHash": report["contextHash"], "createdAt": now, "expiresAt": now+TTL, "boundary": BOUNDARY}
        require(len(canonical(doc).encode()) <= 28000, "Review permission preview exceeds its bound; operator review required")
        return {"document": doc, "signature": self.sign(doc)}

    def confirm(self, ledger, body, session):
        body = copy.deepcopy(body); exact(body, {"proposal", "confirmed"})
        require(body["confirmed"] is True, "Explicit owner confirmation required")
        exact(body["proposal"], {"document", "signature"})
        doc = body["proposal"]["document"]; signature = body["proposal"]["signature"]; sha(signature)
        require(hmac.compare_digest(signature, self.sign(doc)), "Preview changed or dashboard restarted; inspect saved permission before preparing again")
        require(doc["kind"] == "result_review_owner_preview" and doc["session"] == digest(session) and
                doc["workspaceId"] == missions.workspace(ledger) and doc["ledgerIdentity"] == identity(ledger), "Preview belongs to another session or workspace")
        op, req = doc["operation"], doc["request"]
        fields = authority.FIELDS if op == "authorize" else {"workerId", "authorityHash", "reason", "confirmed"}
        with ledger.tx() as db:
            _, _, _, prior = runs.request_in(ledger, db, req, "dashboard_owner", "result_review_"+("approved" if op == "authorize" else "revoked"), fields)
            if not prior:
                require(0 <= time.time()-doc["createdAt"] <= TTL and time.time() <= doc["expiresAt"], "Preview expired; inspect and preview again")
                require(inspect_in(ledger, db, req["workerId"])["contextHash"] == doc["contextHash"], "Workspace changed; inspect this result again")
            method = authority.authorize if op == "authorize" else authority.revoke
            receipt = method(ledger, req, actor="dashboard_owner", _db=db)
            return {"receipt": receipt, "replayed": prior is not None, "executionAuthorized": False, "nativeCallMade": False}
