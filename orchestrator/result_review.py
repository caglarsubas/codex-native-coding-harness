"""Internal standard-policy result acceptance, separate from ownership release.

Retained bytes and bindings are checked here; their external truth must be
independently verified by the trusted caller. No Git, test, native or model calls.
Only the workspace transaction writes; shared accounting is never modified.
"""
import copy
import hashlib
import json
from pathlib import PurePosixPath
import time
from urllib.parse import urlsplit

from . import run_authority as runs, task_contracts
from .admission import exact, identifier, integer, sha, timestamp
from .core import AXES, COMMIT, Refusal, canonical, digest, require, safe_relative
from .ownership_settlement import OwnershipSettlement, local_binding, pair
from .phase_scope import contained_path

STATUSES = ("verified", "unverified", "not_applicable", "failed")


def commit(value):
    require(isinstance(value, str) and COMMIT.fullmatch(value), "Exact result commit required")


def proof_shape(value):
    exact(value, {"status", "artifactId", "observedAt"})
    require(value["status"] in STATUSES, "Invalid result evidence status")
    timestamp(value["observedAt"])
    if value["artifactId"] is not None: sha(value["artifactId"])
    require(value["status"] == "unverified" or value["artifactId"] is not None,
            "Verified, failed and not-applicable facts need retained proof")


def validate(request):
    exact(request, {"id", "expectedRevision", "settlementHash", "outcome", "result", "reviewArtifactId"})
    try: size = len(canonical(request).encode())
    except (TypeError, ValueError, RecursionError) as error:
        raise Refusal("Result review must be bounded finite JSON") from error
    require(size <= 16000, "Result review exceeds its bound")
    identifier(request["id"]); integer(request["expectedRevision"])
    sha(request["settlementHash"]); sha(request["reviewArtifactId"])
    require(request["outcome"] in ("accepted", "changes_required"), "Invalid review outcome")
    result = request["result"]
    exact(result, {"seedHash", "baseSHA", "commit", "branch", "changedPaths", "diffComplete",
                   "pr", "ci", "evidence", "criteria", "preservation", "observedAt"})
    sha(result["seedHash"]); commit(result["baseSHA"]); commit(result["commit"]); timestamp(result["observedAt"])
    require(isinstance(result["branch"], str) and result["branch"].startswith("codex/") and
            len(result["branch"]) <= 200, "Exact result branch required")
    paths = result["changedPaths"]
    require(isinstance(paths, list) and 1 <= len(paths) <= 200 and result["diffComplete"] is True,
            "Complete bounded changed-path inventory required")
    for path in paths:
        safe_relative(path)
        require(len(path) <= 500 and str(PurePosixPath(path)) == path and
                not any(c in path for c in "*?[]\x00\r\n"), "Concrete canonical changed paths required")
    require(len(set(paths)) == len(paths), "Duplicate changed path")
    pr = result["pr"]
    exact(pr, {"url", "headSHA", "baseSHA", "state", "mergeCommit"})
    require(isinstance(pr["url"], str) and len(pr["url"]) <= 1000, "Bounded PR reference required")
    try: url = urlsplit(pr["url"])
    except ValueError: raise Refusal("Invalid PR reference") from None
    require(url.scheme == "https" and url.hostname and not url.username and not url.password and
            not url.query and not url.fragment, "Credential-free HTTPS PR reference required")
    commit(pr["headSHA"]); commit(pr["baseSHA"])
    require(pr["state"] in ("open", "closed", "merged"), "Explicit PR state required")
    if pr["state"] == "merged": commit(pr["mergeCommit"])
    else: require(pr["mergeCommit"] is None, "Unmerged PR cannot claim a merge commit")
    exact(result["evidence"], AXES)
    for proof in result["evidence"].values(): proof_shape(proof)
    proof_shape(result["preservation"])
    criteria = result["criteria"]
    require(isinstance(criteria, list) and 1 <= len(criteria) <= 80, "Exact bounded acceptance criteria required")
    for row in criteria:
        exact(row, {"index", "criterionHash", "proof"}); integer(row["index"], 0, 79)
        sha(row["criterionHash"]); proof_shape(row["proof"])
    ci = result["ci"]
    exact(ci, {"headSHA", "complete", "requiredChecks", "checks"}); commit(ci["headSHA"])
    require(type(ci["complete"]) is bool and isinstance(ci["requiredChecks"], list) and
            len(ci["requiredChecks"]) <= 80 and isinstance(ci["checks"], list) and len(ci["checks"]) <= 80,
            "Bounded explicit CI coverage required")
    def check_name(name):
        require(isinstance(name, str) and 0 < len(name.strip()) <= 200, "Bounded CI check name required")
    for name in ci["requiredChecks"]: check_name(name)
    require(len(set(ci["requiredChecks"])) == len(ci["requiredChecks"]), "Duplicate required CI check")
    names = []
    for check in ci["checks"]:
        exact(check, {"name", "headSHA", "status"}); check_name(check["name"]); commit(check["headSHA"])
        require(check["status"] in ("passed", "failed", "pending"), "Explicit CI check result required")
        names.append(check["name"])
    require(len(set(names)) == len(names), "Duplicate observed CI check")


def artifact_in(db, key, intent, subject, result_commit):
    row = db.execute("SELECT CASE WHEN length(CAST(data AS BLOB))<=16000 THEN data END,"
                     "CASE WHEN length(content)<=16000 THEN content END FROM artifact_versions WHERE id=?", (key,)).fetchone()
    require(row is not None and row[0] is not None and row[1] is not None, "Bounded retained result artifact required")
    try: info = json.loads(row[0])
    except (ValueError, TypeError, RecursionError): raise Refusal("Invalid result artifact metadata") from None
    require(isinstance(info, dict) and isinstance(info.get("references"), list), "Invalid result artifact metadata")
    raw = row[1]
    require(isinstance(raw, bytes), "Retained result artifact must contain bytes")
    require(info.get("sha256") == hashlib.sha256(raw).hexdigest() and info.get("id") == key ==
            digest([info.get("key"), info.get("version"), info.get("sha256")]), "Result artifact bytes or version changed")
    require(info.get("repository") == intent["repository"] and any(
        isinstance(ref, dict) and ref.get("workerId") == intent["workerId"] and
        ref.get("intentHash") == digest(intent) and ref.get("commit") == result_commit and ref.get("subject") == subject
        for ref in info.get("references", [])), "Result artifact needs exact task, commit and subject binding")
    timestamp(info.get("observedAt"))
    from .result_handoff import validate_proof
    validate_proof(db, info, raw, intent, subject, result_commit)
    return info, raw


def evidence_in(db, intent, settlement, request):
    """Byte integrity and immutable semantics, reusable on historical reads."""
    for task in settlement["request"]["inventory"]["tasks"]:
        OwnershipSettlement.artifact_in(db, intent, task, settlement["nativeRecord"]["at"])
    result = request["result"]
    require(result["observedAt"] >= settlement["at"], "Final result observation must follow terminal settlement")
    seed = runs.document(db, intent["seedHash"], "seed")
    require(result["seedHash"] == intent["seedHash"] and result["baseSHA"] == seed["baseSHA"] and
            result["branch"] == seed["branch"], "Result seed, base or branch changed")
    require(result["commit"] != result["baseSHA"], "A changed result needs a distinct commit")
    if request["outcome"] == "accepted":
        require(all(contained_path(p, seed["allowedPaths"]) for p in result["changedPaths"]), "Out-of-scope changed path")
    require(result["pr"]["headSHA"] == result["ci"]["headSHA"] == result["commit"] and
            result["pr"]["baseSHA"] == result["baseSHA"], "PR/CI result commit or base mismatch")
    criteria = result["criteria"]
    require([r["index"] for r in criteria] == list(range(len(seed["acceptance"]))) and
            all(r["criterionHash"] == digest(seed["acceptance"][r["index"]]) for r in criteria),
            "Every exact seed acceptance criterion must be covered once in order")
    proofs = [(axis, result["evidence"][axis]) for axis in AXES]
    proofs += [("criterion:"+str(r["index"]), r["proof"]) for r in criteria]
    proofs += [("preservation", result["preservation"])]
    times = [result["observedAt"]]
    for subject, proof in proofs:
        require(settlement["priorClaim"]["startedAt"] <= proof["observedAt"] <= result["observedAt"],
                "Evidence observation is outside the result interval")
        if proof["artifactId"] is not None:
            info, raw = artifact_in(db, proof["artifactId"], intent, subject, result["commit"])
            require(settlement["priorClaim"]["startedAt"] <= info["observedAt"] <= proof["observedAt"],
                    "Proof bytes must be retained before their review observation")
            if "resultEvidenceObservedAt" in info: times.append(info["resultEvidenceObservedAt"])
            if subject == "source":
                from .source_observation import validate_source_proof
                collected_at = validate_source_proof(db, info, raw, intent, settlement, result)
                if collected_at is not None: times.append(collected_at)
            from .github_evidence import validate_github_proof
            collected_at = validate_github_proof(db, info, raw, intent, settlement, result, subject)
            if collected_at is not None: times.append(collected_at)
        times.append(proof["observedAt"])
    ci = result["ci"]; checks = {c["name"]: c for c in ci["checks"]}
    require(all(c["headSHA"] == result["commit"] for c in checks.values()), "CI check belongs to a different commit")
    if result["evidence"]["ci"]["status"] == "verified":
        require(ci["complete"] is True and ci["requiredChecks"] and all(
            n in checks and checks[n]["status"] == "passed" for n in ci["requiredChecks"]),
            "Verified CI requires complete passing required checks; empty checks are not success")
    require(result["evidence"]["merge"]["status"] != "verified" or result["pr"]["state"] == "merged",
            "Merge evidence cannot verify an unmerged PR")
    if request["outcome"] == "accepted":
        require(all(result["evidence"][axis]["status"] == "verified" for axis in seed["completionAxes"]),
                "Required completion axes are not verified")
        require(all(r["proof"]["status"] == "verified" for r in criteria), "Acceptance criteria are not verified")
        require(result["preservation"]["status"] == "verified" and result["pr"]["state"] != "closed",
                "Acceptance requires preserved result bytes and an open or merged PR")
    info, raw = artifact_in(db, request["reviewArtifactId"], intent, "independent_review", result["commit"])
    def unique_fields(pairs):
        fields = {}
        for key, value in pairs:
            require(key not in fields, "Duplicate independent review field")
            fields[key] = value
        return fields
    try: report = json.loads(raw, object_pairs_hook=unique_fields)
    except (ValueError, TypeError, UnicodeError, RecursionError): raise Refusal("Independent review must be retained JSON with unique fields") from None
    exact(report, {"kind", "workerId", "intentHash", "settlementHash", "resultHash", "outcome", "reviewer", "observedAt", "summary"})
    require(report["kind"] == "independent_result_review" and report["workerId"] == intent["workerId"] and
            report["intentHash"] == digest(intent) and report["settlementHash"] == digest(settlement) == request["settlementHash"] and
            report["resultHash"] == digest(result) and report["outcome"] == request["outcome"], "Independent review binding changed")
    exact(report["reviewer"], {"hostId", "threadId"})
    identifier(report["reviewer"]["hostId"]); identifier(report["reviewer"]["threadId"])
    require(pair(report["reviewer"]) not in {pair(t) for t in settlement["request"]["inventory"]["tasks"]} and
            report["reviewer"]["threadId"] != settlement["localBinding"]["clientThreadId"], "Worker or descendant cannot independently review itself")
    require(isinstance(report["summary"], str) and 0 < len(report["summary"].strip()) <= 2000, "Bounded independent review summary required")
    timestamp(report["observedAt"])
    require(max(result["observedAt"], settlement["at"]) <= report["observedAt"] <= info["observedAt"],
            "Independent review must follow the exact result and terminal settlement")
    times.extend([report["observedAt"], info["observedAt"]])
    if "resultEvidenceObservedAt" in info: times.append(info["resultEvidenceObservedAt"])
    return report, times


def projection(record):
    request = record["request"]; result = request["result"]; accepted = request["outcome"] == "accepted"
    fields = {"resultReviewHash": digest(record), "reviewOutcome": request["outcome"]}
    if accepted:
        fields.update(status="complete", completedAt=record["at"], completionHash=digest(record),
            evidence={axis: {"status": p["status"], "reference": "Retained artifact " + p["artifactId"] if p["artifactId"] else None}
                      for axis, p in result["evidence"].items()}, preserved=True, pr=result["pr"]["url"], commit=result["commit"])
    return fields


def reviewed_worker_in(db, worker, claim, settlement):
    """Validate a later review without replaying/undoing terminal settlement."""
    record = runs.document(db, worker.get("resultReviewHash"), "result_review")
    validate(record["request"])
    require(record["kind"] == "result_review" and record["workerId"] == worker["id"] and
            record["intentHash"] == settlement["intentHash"] and record["request"]["settlementHash"] == digest(settlement),
            "Result review identity changed")
    expected = copy.deepcopy(settlement["localBinding"])
    expected["status"] = "complete" if record["request"]["outcome"] == "accepted" else "settled"
    expected["dispatchAdmission"].update(stage="settled", claimHash=digest(claim))
    require(local_binding(worker) == expected and worker.get("ownershipSettlementHash") == digest(settlement) and
            runs.document(db, digest(settlement), "ownership_settlement") == settlement and
            all(worker.get(k) == v for k, v in projection(record).items()) and not worker.get("archived"),
            "Reviewed worker projection diverged")
    if record["request"]["outcome"] == "changes_required": unaccepted_worker(worker)
    intent = runs.document(db, settlement["intentHash"], "dispatch_intent")
    report, _ = evidence_in(db, intent, settlement, record["request"])
    require(report == record["review"], "Retained independent report changed")
    row = db.execute("SELECT data FROM queue WHERE id=?", (intent["queueId"],)).fetchone()
    require(row is not None, "Reviewed queue is missing")
    q = json.loads(row[0])
    require(q.get("resultReviewHash") == digest(record) and q.get("seedHash") == intent["seedHash"] and
            q["held"] is (record["request"]["outcome"] != "accepted") and
            q["status"] == ("complete" if record["request"]["outcome"] == "accepted" else "blocked"),
            "Reviewed queue projection diverged")
    return record


def unaccepted_worker(worker):
    require(worker.get("preserved") is False and worker.get("archived") is False and
            not any(k in worker for k in ("completionHash", "completedAt", "pr", "commit")) and
            worker.get("evidence") == {axis: {"status": "unverified", "reference": None} for axis in AXES},
            "Unreviewed result projection changed")


class ResultReview:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.settlement = OwnershipSettlement(bridge)

    def evidence_in(self, db, intent, settlement, request):
        return evidence_in(db, intent, settlement, request)

    def authority_in(self, db, meta, worker, intent):
        require(meta["paused"] is False, "Dispatch paused; result acceptance is fenced")
        grant = runs.require_current(self.ledger, db, intent["runHash"])
        q = self.ledger.get(db, "queue", intent["queueId"])
        require(q["status"] == "blocked" and q["held"] is True and q["reason"] == self.settlement.queue_reason,
                "Exact terminal review hold required")
        require(q.get("phaseApprovalHash") == intent["approvalHash"] and
                q.get("taskContract", {}).get("hash") == intent["contractHash"], "Task approval or contract changed")
        approval = runs.document(db, intent["approvalHash"], "run_task_approval")
        require(approval["status"] == "approved" and approval["workspaceId"] == self.bridge.workspace_id and
                approval["queueId"] == q["id"] and approval["runHash"] == intent["runHash"] and
                approval["contractHash"] == intent["contractHash"] and approval["generation"] == grant["generation"],
                "Current exact task approval required")
        require(approval["actor"] == "dashboard_owner" or approval["actor"] == "designated_brain" and
                grant["authority"]["approvalMode"] == "phase_delegated", "Task approval actor exceeds run policy")
        contract = runs.document(db, intent["contractHash"], "task_contract")
        require(contract["repositoryBinding"]["policyProfile"] == "standard", "Harness result acceptance needs its trusted adapter")
        require(task_contracts.evaluate(q, task_contracts.context_in(self.ledger, db, q), contract)["status"] == "bound",
                "Result task contract is stale or invalid")
        require(not any(c["kind"] in ("checkpoint", "archive") and c["status"] in ("queued", "processing") and
                        c["payload"].get("workerId") == worker["id"] for c in self.ledger.all(db, "commands")),
                "Worker control remains unresolved")
        require(meta["runner"] is None, "Local runner ownership must be reconciled first")
        return q

    @staticmethod
    def receipt(record):
        return {"workerId": record["workerId"], "reviewHash": digest(record), "outcome": record["request"]["outcome"],
                "packetAccepted": record["request"]["outcome"] == "accepted", "ownershipReleased": True,
                "executionAuthorized": False, "nativeCallMade": False, "retryAuthorized": False,
                "pilotAccepted": False, "archiveAuthorized": False,
                "trustBoundary": "caller_supplied_external_evidence_not_independent_attestation"}

    def review(self, token, worker_id, request):
        validate(request)
        # Maintenance fences prohibit new/replayed acceptance; use read() for
        # historical receipts behind maintenance. No cross-store write gap.
        with self.bridge.locked(token, ownership_change=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, settlement = self.settlement.record_in(kernel, intent)
                require(settlement is not None and request["settlementHash"] == digest(settlement), "Exact confirmed-terminal settlement required")
                if worker.get("resultReviewHash"):
                    record = reviewed_worker_in(db, worker, claim, settlement)
                    require(record["request"] == request, "Result already reviewed with different content")
                    return self.receipt(record)
                require(worker.get("ownershipSettlementHash") == request["settlementHash"] and
                        worker["status"] == "settled", "Recover local settlement receipt before review")
                # Existing-receipt branch only: never attach a missing settlement.
                self.settlement.attach_in(db, worker, claim, settlement)
                self.settlement.maintenance_check(kernel)
                unaccepted_worker(worker)
                allocation = self.store.get(kernel, "allocations", intent["allocationId"])
                require(allocation["fingerprint"] == intent["allocationFingerprint"] == digest(allocation["spec"]),
                        "Phase allocation binding changed")
                require(meta["revision"] == request["expectedRevision"], "Workspace changed before result review")
                q = self.authority_in(db, meta, worker, intent)
                report, times = self.evidence_in(db, intent, settlement, request)
                policy = self.store.get(kernel, "meta", 1)["policy"]
                for at in times: self.store.fresh(at, policy)
            record = {"kind": "result_review", "schemaVersion": 1, "workerId": worker_id,
                      "intentHash": digest(intent), "request": copy.deepcopy(request), "review": report, "at": time.time()}
            key = runs.retain(db, "result_review", record)
            worker.update(projection(record), updatedAt=record["at"])
            self.ledger.put(db, "workers", worker_id, worker)
            q.update(resultReviewHash=key, held=request["outcome"] != "accepted",
                     status="complete" if request["outcome"] == "accepted" else "blocked",
                     reason="Declared packet result accepted; other evidence axes remain separate" if request["outcome"] == "accepted"
                     else "Result changes required; closed attempt remains held without retry authority")
            if request["outcome"] == "accepted": q["completedAt"] = record["at"]
            self.ledger.put(db, "queue", q["id"], q)
            self.ledger.event(db, "result_reviewed", {"workerId": worker_id, "reviewHash": key, "outcome": request["outcome"]})
            return self.receipt(record)

    def read(self, token, worker_id):
        """Historical, integrity-checked receipt, never new acceptance/recovery."""
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, settlement = self.settlement.record_in(kernel, intent)
                require(settlement is not None, "Confirmed-terminal settlement required")
                require(worker.get("resultReviewHash"), "No result review recorded")
                return self.receipt(reviewed_worker_in(db, worker, claim, settlement))
