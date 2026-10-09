"""Exact owner reallocation for an empty, paused cooperative phase.

No native collection, wake, Resume, new phase budget, or usage forgiveness.
"""
import copy
import hmac
import json
import time
import uuid

from . import standard
from .conversation import pending
from .core import Refusal, digest, require
from .enrollment import record_in
from .retention_controls import identity

KIND = "standard_brain_budget"
BOUNDARY = ("Reallocate the brain allowance inside the reviewed phase total. Preserve the checkpoint reserve, "
            "scope, task limits, expiry, consumed usage, gaps and receipts. The phase stays paused. "
            "No native action or Resume; fresh usage and a separate exact Resume review are still required.")


def context_in(ledger, db):
    meta = ledger.get(db, "meta", 1)
    return digest({"workspace": ledger.workspace_id, "identity": identity(ledger), "meta": meta,
                   "commands": ledger.all(db, "commands"), "workers": ledger.all(db, "workers"),
                   "queue": ledger.all(db, "queue"), "repos": ledger.all(db, "repos")})


def guard(ledger, db):
    meta, mission = standard.eligible(ledger, db)
    run = meta.get("standardRun") or {}
    require(meta.get("schemaVersion") == 4 and run.get("protocol") == standard.PROTOCOL and
            run.get("status") == "paused" and run.get("brainId") == meta["brainId"],
            "An exact paused standard phase is required")
    require(mission["documentHash"] == run["missionHash"] and mission["receiptHash"] == run["reviewHash"],
            "Mission changed; review a new phase instead")
    require(run["limits"] == mission["document"]["spec"]["authority"] and run.get("checkpoint"),
            "Exact reviewed limits and retained checkpoint required")
    require(time.time() < run["expiresAt"], "The phase expired; reallocation cannot extend it")
    require(meta.get("controller") is None and not standard.controller_file(ledger).exists(),
            "Wait for the brain to release its controller")
    require(not run.get("tasks") and not run.get("merges") and not ledger.all(db, "workers") and
            not ledger.all(db, "queue"), "Tasks, packets or effects need their own reconciliation")
    require((meta.get("brainControl") or {}).get("desired") != "stopped",
            "Brain Stop remains in force")
    require((meta.get("brainHandoff") or {}).get("status") not in ("prepared", "candidate", "received"),
            "Finish the existing brain handoff first")
    from .reply_recovery import fence_development
    fence_development(ledger, db)
    require(not run.get("recovery") or run["recovery"].get("status") == "replied",
            "Follow the existing recovery reply first")
    commands = ledger.all(db, "commands")
    require(not any(c.get("status") in ("queued", "processing") or c.get("needsBrainReceipt") or pending(c)
                    for c in commands), "Follow the pending request before changing an allowance")
    owned = [c["notification"] for c in commands if (c.get("notification") or {}).get("brainId") == meta["brainId"]]
    require(owned, "An ended owned-host turn is required")
    require(not any(n.get("hostRunId") == run["id"] and
                    (n.get("status") in ("sending", "uncertain") or
                     n.get("nativeTurnStatus") in ("unconfirmed", "connection_lost", "native_attention_required"))
                    for n in owned), "An earlier owned delivery remains unresolved; reallocation cannot reconcile it")
    latest = max(owned, key=lambda n: n.get("attemptedAt", 0))
    require(latest.get("status") == "accepted" and latest.get("nativeDelivery") == "owned_turn_start" and
            latest.get("hostRunId") == run["id"] and latest.get("nativeTurnStatus") == "completed" and
            (latest.get("nativeThreadObservation") or {}).get("streamStatus") == "closed",
            "The latest owned delivery is unfinished or uncertain; reconcile it first")
    require(not any(a.get("status") not in ("resolved", "resolved_without_response")
                    for note in owned for a in note.get("nativeApprovals", [])),
            "A native approval needs its own reconciliation")
    require(len(run.get("budgetReviews", [])) < 200, "Allowance review history is full; retain it and review a new phase")
    maximum = run["limits"]["tokenBudget"] - run["limits"]["checkpointReserveTokens"] - 1
    require(run["brainAllowance"] < maximum, "No larger brain allowance fits inside this phase")
    require(run.get("brainUsageCoverage") == "not_observed" or run.get("brainObservedTokens", 0) < maximum,
            "Recorded brain usage leaves no headroom within this phase")
    return meta, run, maximum


def summary_in(ledger, db):
    run = ledger.get(db, "meta", 1).get("standardRun") or {}
    result = {"available": False, "reason": None, "contextHash": context_in(ledger, db), "boundary": BOUNDARY,
              "currentAllowance": run.get("brainAllowance"), "maximumAllowance": None}
    try:
        _, _, maximum = guard(ledger, db)
        result.update(available=True, maximumAllowance=maximum,
                      suggestedAllowance=min(maximum, max(run["brainAllowance"] + max(1, run["limits"]["tokenBudget"] // 5),
                                                        run["limits"]["tokenBudget"] // 2)))
    except (Refusal, KeyError, TypeError, OSError) as error:
        result["reason"] = str(error)
    return result


class Controls(standard.Controls):
    def preview(self, registry, ledger, request, session):
        standard.exact(request, "runId contextHash brainAllowance")
        with registry.tx() as registry_db, standard.read_db(ledger.db) as db:
            require(record_in(registry_db) is None, "Strict platform enrollment blocks reallocation")
            meta, run, maximum = guard(ledger, db)
            require(request["runId"] == run["id"] and request["contextHash"] == context_in(ledger, db),
                    "Phase changed; review its current allowance")
            amount = standard.missions.integer(request["brainAllowance"], "Brain allowance", run["brainAllowance"] + 1, maximum)
            known = run.get("brainObservedTokens") if run.get("brainUsageCoverage") != "not_observed" else None
            require(known is None or amount > known, "The proposed allowance leaves no recorded brain headroom")
            now = time.time()
            doc = {**request, "id": str(uuid.uuid4()), "workspaceId": ledger.workspace_id,
                   "ledgerIdentity": identity(ledger), "session": digest(session), "brainId": meta["brainId"],
                   "previousAllowance": run["brainAllowance"], "phaseBudget": run["limits"]["tokenBudget"],
                   "checkpointReserve": run["limits"]["checkpointReserveTokens"], "runExpiresAt": run["expiresAt"],
                   "missionHash": run["missionHash"], "reviewHash": run["reviewHash"],
                   "recordedBrainTokens": known, "recordedCoverage": run.get("brainUsageCoverage"),
                   "usageReport": copy.deepcopy(run.get("usageReport")),
                   "closeoutReport": copy.deepcopy(run.get("closeoutReport")),
                   "issuedAt": now, "expiresAt": min(now + 300, run["expiresAt"]), "boundary": BOUNDARY}
            return {"preview": doc, "signature": self.sign(doc)}

    def confirm(self, registry, ledger, body, session):
        standard.exact(body, "preview signature confirmed")
        require(body["confirmed"] is True and isinstance(body["signature"], str), "Exact owner confirmation required")
        doc = body["preview"]
        require(isinstance(doc, dict) and hmac.compare_digest(self.sign(doc), body["signature"]), "Invalid allowance signature")
        require(doc["workspaceId"] == ledger.workspace_id and doc["ledgerIdentity"] == identity(ledger) and
                doc["session"] == digest(session), "Foreign allowance review")
        with registry.tx() as registry_db, ledger.tx() as db:
            prior = db.execute("SELECT data FROM commands WHERE id=?", (doc["id"],)).fetchone()
            if prior:
                command = json.loads(prior[0])
                require(command["kind"] == KIND and command["payload"]["reviewHash"] == digest(doc), "Allowance review ID reused")
                return command  # Historical receipt only, even after expiry or a later change.
            require(doc["issuedAt"] <= time.time() < doc["expiresAt"], "Allowance review expired")
            require(record_in(registry_db) is None, "Strict platform enrollment blocks reallocation")
            meta, run, maximum = guard(ledger, db)
            require(doc["contextHash"] == context_in(ledger, db) and doc["runId"] == run["id"],
                    "Phase or evidence changed; review again")
            standard.missions.integer(doc["brainAllowance"], "Brain allowance", run["brainAllowance"] + 1, maximum)
            review = {"id": doc["id"], "reviewHash": digest(doc), "at": time.time(),
                      "previousAllowance": run["brainAllowance"], "brainAllowance": doc["brainAllowance"]}
            run.setdefault("budgetReviews", []).append(review)
            run["brainAllowance"] = doc["brainAllowance"]
            standard.save(ledger, db, meta, run, "brain_budget")
            command = {"id": doc["id"], "kind": KIND, "actor": "owner_confirmed", "status": "completed",
                       "createdAt": review["at"], "completedAt": review["at"], "payload": {"runId": run["id"],
                       "reviewHash": digest(doc)}, "result": "Brain allowance adjusted; phase remains paused. Refresh usage and separately review Resume."}
            ledger.put(db, "commands", command["id"], command)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (digest(doc), KIND, standard.canonical(doc)))
            return command
