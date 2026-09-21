"""Designated-brain result workflow. Evidence is inert; review is a separate step."""
import json
import time

from . import github_evidence as github, result_review as results, run_authority as runs, source_observation as source
from .admission import exact, identifier, integer, sha, timestamp
from .core import AXES, Refusal, canonical, digest, require
from .observations import capture, read_regular

KIND = "result_handoff_evidence"
REQUEST = "result_handoff_evidence_request"
PROVENANCE = "result_handoff_evidence_v1"


def read_request(path):
    path = path.absolute()
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, "Duplicate result handoff field")
            out[key] = value
        return out
    try:
        value = json.loads(read_regular(path, path.parent, 16000), object_pairs_hook=unique)
        canonical(value)
        return value
    except (ValueError, RecursionError, UnicodeError):
        raise Refusal("Result handoff requires bounded finite JSON") from None


def subject_allowed(subject, seed):
    allowed = set(AXES) - {"source", "ci", "merge"}
    allowed.update(("preservation", "independent_review"))
    allowed.update("criterion:"+str(i) for i in range(len(seed["acceptance"])))
    require(isinstance(subject, str) and subject in allowed, "Subject requires a collector or is outside the task criteria")


def proof_request(request):
    exact(request, {"id", "expectedRevision", "settlementHash", "commit", "subject", "observedAt", "content"})
    identifier(request["id"]); integer(request["expectedRevision"]); sha(request["settlementHash"])
    source.oid(request["commit"]); timestamp(request["observedAt"])
    require(isinstance(request["subject"], str) and len(request["subject"]) <= 80, "Bounded proof subject required")
    require(isinstance(request["content"], str) and 0 < len(request["content"].encode()) <= 8000,
            "Nonempty proof text of at most 8000 UTF-8 bytes required")
    require(len(canonical(request).encode()) <= 12000, "Proof request exceeds its bound")


def request_key(intent, request):
    return digest({"kind": REQUEST, "workspaceId": intent["workspaceId"], "workerId": intent["workerId"], "id": request["id"]})


def receipt_for(report, info):
    return {"evidenceHash": digest(report), "artifactId": info["id"], "workerId": report["workerId"],
            "observedAt": report["request"]["observedAt"], "retainedAt": info["observedAt"],
            "packetAccepted": False, "executionAuthorized": False, "nativeCallMade": False,
            "trustBoundary": "caller_supplied_evidence_not_independent_attestation"}


def receipt_in(db, key):
    row = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=2000 THEN data END FROM snapshots WHERE id=?", (key,)).fetchone()
    if row is None: return None
    require(row[0] == REQUEST and row[1] is not None, "Invalid result evidence receipt")
    try: receipt = json.loads(row[1])
    except (ValueError, TypeError, RecursionError): raise Refusal("Invalid result evidence receipt") from None
    require(isinstance(receipt, dict), "Invalid result evidence receipt")
    exact(receipt, {"evidenceHash", "artifactId", "workerId", "observedAt", "retainedAt", "packetAccepted",
                    "executionAuthorized", "nativeCallMade", "trustBoundary"})
    return receipt


def validate_proof(db, info, raw, intent, subject, commit):
    """Called by the shared artifact reader, including historical result validation."""
    tagged = (info.get("provenance") == PROVENANCE or "resultEvidenceHash" in info or
              str(info.get("key", "")).startswith("result-evidence:"))
    if not tagged: return None
    require(info.get("provenance") == PROVENANCE, "Result evidence provenance changed")
    report = runs.document(db, info.get("resultEvidenceHash"), KIND)
    request = report.get("request"); proof_request(request)
    seed = runs.document(db, intent["seedHash"], "seed"); subject_allowed(subject, seed)
    require(report["workerId"] == intent["workerId"] and report["intentHash"] == digest(intent) and
            report["repository"] == intent["repository"] and report["requestKey"] == request_key(intent, request) and
            request["subject"] == subject and request["commit"] == commit and raw == request["content"].encode(),
            "Result evidence task, subject, commit or bytes changed")
    terminal = runs.document(db, request["settlementHash"], "ownership_settlement")
    require(terminal["workerId"] == intent["workerId"] and terminal["intentHash"] == digest(intent), "Result evidence settlement changed")
    require(terminal["at"] <= request["observedAt"] == info.get("resultEvidenceObservedAt") <= report["at"] <= info["observedAt"],
            "Result evidence observation time changed")
    require(receipt_in(db, report["requestKey"]) == receipt_for(report, info), "Result evidence receipt changed or missing")
    return request["observedAt"]


def scope_in(db, intent):
    seed = runs.document(db, intent["seedHash"], "seed")
    require(seed["policyProfile"] == "standard", "Harness requires its trusted result adapter")
    contract = runs.document(db, intent["contractHash"], "task_contract")
    require(contract["repositoryBinding"]["policyProfile"] == "standard", "Harness requires its trusted result adapter")
    runs.standard_handoff_scope(db, intent)
    return seed


def handoff_proof(db, key, intent, subject, commit):
    info, raw = results.artifact_in(db, key, intent, subject, commit)
    from .local_preservation import PROVENANCE as PRESERVATION_PROVENANCE
    if subject == "preservation" and info.get("provenance") == PRESERVATION_PROVENANCE:
        return info, raw  # Shared artifact reader has validated bundle and inventory.
    expected = source.PROVENANCE if subject == "source" else github.PROVENANCE if subject in ("ci", "merge") else PROVENANCE
    require(info.get("provenance") == expected, "Result handoff requires measured source/CI and bound supplemental evidence")
    if expected == source.PROVENANCE: source.collector_binding_in(db, info, raw, intent)
    elif expected == github.PROVENANCE: github.collector_binding(db, info, raw, intent)
    return info, raw


class HandoffReview(results.ResultReview):
    def authority_in(self, db, meta, worker, intent):
        scope_in(db, intent)
        return super().authority_in(db, meta, worker, intent)

    def evidence_in(self, db, intent, settlement, request):
        result = request["result"]
        proofs = [(axis, p) for axis, p in result["evidence"].items()]
        proofs += [("criterion:"+str(r["index"]), r["proof"]) for r in result["criteria"]]
        proofs += [("preservation", result["preservation"])]
        for subject, proof in proofs:
            if proof["artifactId"] is not None or subject in ("source", "ci"):
                handoff_proof(db, proof["artifactId"], intent, subject, result["commit"])
        handoff_proof(db, request["reviewArtifactId"], intent, "independent_review", result["commit"])
        return super().evidence_in(db, intent, settlement, request)


class ResultHandoff:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.reviewer = HandoffReview(bridge)
        self.source = source.SourceObserver(bridge); self.github = github.GitHubObserver(bridge)
        # The extra first-handoff scope restriction is checked inside both I/O
        # boundaries, not as a racy precheck outside the collectors' authority.
        self.source.review = self.github.review = self.reviewer

    def collect_source(self, token, worker_id, request): return self.source.observe(token, worker_id, request)
    def collect_github(self, token, worker_id, request): return self.github.observe(token, worker_id, request)
    def collect_preservation(self, token, worker_id, request):
        from .local_preservation import LocalPreservation
        return LocalPreservation(self).collect(token, worker_id, request)
    def review(self, token, worker_id, request): return self.reviewer.review(token, worker_id, request)

    def terminal_in(self, db, kernel, worker, intent):
        seed = scope_in(db, intent)
        claim, terminal = self.reviewer.settlement.record_in(kernel, intent)
        require(terminal and worker.get("ownershipSettlementHash") == digest(terminal),
                "Exact attached terminal settlement required; this read cannot recover it")
        self.reviewer.settlement.attach_in(db, worker, claim, terminal)  # Exact existing receipt only.
        if not worker.get("resultReviewHash"): results.unaccepted_worker(worker)
        allocation = self.store.get(kernel, "allocations", intent["allocationId"])
        require(allocation["fingerprint"] == intent["allocationFingerprint"] == digest(allocation["spec"]), "Phase allocation binding changed")
        return seed, terminal

    def state(self, token, worker_id):
        with self.bridge.locked(token) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel: seed, terminal = self.terminal_in(db, kernel, worker, intent)
            review = runs.document(db, worker["resultReviewHash"], "result_review") if worker.get("resultReviewHash") else None
            from .result_reauthorization import current_in
            authority = current_in(db, worker)
            out = {"workerId": worker_id, "workspaceId": intent["workspaceId"], "repository": intent["repository"],
                   "revision": meta["revision"], "intentHash": digest(intent), "seedHash": intent["seedHash"],
                   "settlementHash": digest(terminal), "settledAt": terminal["at"], "workerStatus": worker["status"],
                   "review": self.reviewer.receipt(review) if review else None,
                   "reviewHistory": [self.reviewer.receipt(r) for r in results.history_in(db, digest(review), intent, terminal)] if review else [],
                   "reviewAuthority": {"hash": digest(authority), "status": authority["status"], "expiresAt": authority["expiresAt"],
                       "historical": True, "consumed": authority["status"] == "approved" and authority["request"]["previousReviewHash"] != worker.get("resultReviewHash")} if authority else None,
                   "requirements": {"baseSHA": seed["baseSHA"], "branch": seed["branch"], "allowedPaths": seed["allowedPaths"],
                       "completionAxes": seed["completionAxes"], "criteria": [{"index": i, "criterionHash": digest(c), "text": c}
                                                                           for i, c in enumerate(seed["acceptance"])]},
                   "executionAuthorized": False, "nativeCallMade": False, "archiveAuthorized": False,
                   "currentNativeActivity": "not_observed", "trustBoundary": "historical_state_not_run_readiness"}
            require(len(canonical(out).encode()) <= 128000, "Result state exceeds its output bound")
            return out

    def proof_read(self, token, worker_id, request):
        exact(request, {"artifactId", "commit", "subject"}); sha(request["artifactId"]); source.oid(request["commit"])
        require(isinstance(request["subject"], str), "Explicit proof subject required")
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel: self.terminal_in(db, kernel, worker, intent)
            info, raw = handoff_proof(db, request["artifactId"], intent, request["subject"], request["commit"])
            observed_at = info["resultEvidenceObservedAt"] if info["provenance"] == PROVENANCE else json.loads(raw)["observedAt"]
            return {"artifactId": info["id"], "subject": request["subject"], "commit": request["commit"],
                    "provenance": info["provenance"], "observedAt": observed_at,
                    "retainedAt": info["observedAt"], "content": raw.decode("utf-8"),
                    "historical": True, "executionAuthorized": False, "nativeCallMade": False}

    def proof_add(self, token, worker_id, request):
        proof_request(request); request = dict(request)
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel: self.terminal_in(db, kernel, worker, intent)
            key = request_key(intent, request); prior = receipt_in(db, key)
            if prior:
                report = runs.document(db, prior["evidenceHash"], KIND)
                require(report["request"] == request, "Result evidence request ID reused with different content")
                handoff_proof(db, prior["artifactId"], intent, request["subject"], request["commit"])
                return prior
        with self.bridge.locked(token, ownership_change=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            # Concurrent identical add may have committed since the first read.
            prior = receipt_in(db, key)
            if prior:
                report = runs.document(db, prior["evidenceHash"], KIND)
                require(report["request"] == request, "Result evidence request ID reused with different content")
                handoff_proof(db, prior["artifactId"], intent, request["subject"], request["commit"])
                return prior
            with self.store.tx() as kernel:
                seed, terminal = self.terminal_in(db, kernel, worker, intent)
                self.reviewer.settlement.maintenance_check(kernel); results.unaccepted_worker(worker)
                self.reviewer.authority_in(db, meta, worker, intent)
                if "resultReviewAuthorityHash" in worker:
                    from .result_reauthorization import check_in
                    check_in(self.ledger, db, meta, worker, intent, commit=request["commit"])
                require(meta["revision"] == request["expectedRevision"] and digest(terminal) == request["settlementHash"],
                        "Result evidence revision or settlement changed")
                subject_allowed(request["subject"], seed)
                require(terminal["at"] <= request["observedAt"] <= time.time(), "Proof observation must follow terminal settlement")
                self.store.fresh(request["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
            report = {"kind": KIND, "schemaVersion": 1, "workerId": worker_id, "intentHash": digest(intent),
                      "repository": intent["repository"], "requestKey": key, "request": request, "at": time.time()}
            require(len(canonical(report).encode()) <= 16000, "Retained result evidence exceeds its bound")
            key_hash = runs.retain(db, KIND, report)
            info = capture(db, "result-evidence:"+key, request["content"].encode(), {
                "repository": intent["repository"], "name": request["subject"].replace(":", "-")+".txt",
                "orderAt": request["observedAt"], "provenance": PROVENANCE, "resultEvidenceHash": key_hash,
                "resultEvidenceObservedAt": request["observedAt"], "references": [{"workerId": worker_id,
                    "intentHash": digest(intent), "commit": request["commit"], "subject": request["subject"], "at": request["observedAt"]}]})
            receipt = receipt_for(report, info)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, REQUEST, canonical(receipt)))
            self.ledger.event(db, "result_evidence_retained", {"workerId": worker_id, "evidenceHash": key_hash, "artifactId": info["id"]})
            return receipt
