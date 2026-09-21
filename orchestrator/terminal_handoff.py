"""Scoped terminal CLI adapter. Supplied evidence is not native attestation."""
import hashlib
import json
import time

from . import creation_recovery as absence, run_authority as runs
from .admission import exact, identifier, integer, sha, timestamp
from .core import canonical, digest, require
from .observations import capture
from .ownership_settlement import OwnershipSettlement, local_binding
from .result_handoff import scope_in

KIND = "terminal_handoff_proof"
REQUEST = "terminal_handoff_request"
PROVENANCE = "terminal_handoff_v1"


class ScopedBridge:
    """Apply historical scope inside every original transaction, including recovery."""
    def __init__(self, bridge): self.original = bridge
    def __getattr__(self, name): return getattr(self.original, name)

    def intent_in(self, db, worker_id):
        worker, intent = self.original.intent_in(db, worker_id)
        scope_in(db, intent)
        require(worker["hostId"] in (None, "local"), "Terminal handoff supports local tasks only")
        return worker, intent


def proof_request(request):
    exact(request, {"id", "expectedRevision", "expectedHash", "threadId", "observedAt", "content"})
    identifier(request["id"]); integer(request["expectedRevision"]); sha(request["expectedHash"])
    timestamp(request["observedAt"])
    if request["threadId"] is not None: identifier(request["threadId"])
    require(isinstance(request["content"], str) and 0 < len(request["content"].encode()) <= 8000,
            "Nonempty terminal proof of at most 8000 UTF-8 bytes required")
    require(len(canonical(request).encode()) <= 12000, "Terminal proof exceeds its bound")


def request_key(intent, outcome, request):
    return digest({"kind": REQUEST, "intentHash": digest(intent), "outcome": outcome, "id": request["id"]})


def pointer_in(db, key):
    row = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=1000 THEN data END FROM snapshots WHERE id=?", (key,)).fetchone()
    if row is None: return None
    require(row[0] == REQUEST and row[1] is not None, "Terminal proof receipt changed")
    pointer = json.loads(row[1]); exact(pointer, {"reportHash", "artifactId", "retainedAt"})
    sha(pointer["reportHash"]); sha(pointer["artifactId"]); timestamp(pointer["retainedAt"])
    return pointer


def proof_in(db, artifact_id, intent, expected_hash, outcome, thread_id):
    row = db.execute("SELECT CASE WHEN length(CAST(data AS BLOB))<=8000 THEN data END,"
                     "CASE WHEN length(content)<=8000 THEN content END FROM artifact_versions WHERE id=?", (artifact_id,)).fetchone()
    require(row is not None and row[0] is not None and row[1] is not None, "Bounded terminal handoff proof required")
    info, raw = json.loads(row[0]), row[1]
    require(info.get("provenance") == PROVENANCE and info["id"] == artifact_id ==
            digest([info["key"], info["version"], info["sha256"]]) and hashlib.sha256(raw).hexdigest() == info["sha256"],
            "Terminal proof bytes or provenance changed")
    report = runs.document(db, info.get("terminalProofHash"), KIND)
    request = report["request"]; proof_request(request)
    key = request_key(intent, outcome, request)
    require(report["workerId"] == intent["workerId"] and report["intentHash"] == digest(intent) and
            report["outcome"] == outcome and request["expectedHash"] == expected_hash and request["threadId"] == thread_id and
            info["repository"] == intent["repository"] and info["key"] == "terminal-proof:"+key and
            raw == request["content"].encode() and request["observedAt"] <= report["at"] <= info["observedAt"] and
            info["orderAt"] == request["observedAt"] and info["references"] == [{"workerId": intent["workerId"],
                "intentHash": digest(intent), "hostId": "local", "session": thread_id, "at": request["observedAt"]}] and
            pointer_in(db, key) == {"reportHash": digest(report), "artifactId": artifact_id, "retainedAt": info["observedAt"]},
            "Terminal proof task, attempt, outcome or receipt changed")
    return report, info


class BoundProofs:
    def proofs_in(self, db, intent, request):
        if self.kind == "creation_recovery":
            require(request["inventory"]["hostId"] == "local", "Local non-creation evidence required")
            proofs = [(request["reconciliationArtifactId"], None)]
            outcome = "not_created"
        else:
            require(all(t["hostId"] == "local" for t in request["inventory"]["tasks"]), "Local terminal inventory required")
            proofs = [(t["checkpointArtifactId"], t["threadId"]) for t in request["inventory"]["tasks"]]
            outcome = "confirmed"
        for artifact_id, thread_id in proofs:
            proof_in(db, artifact_id, intent, request["expectedHash"], outcome, thread_id)

    def check_in(self, db, meta, kernel, worker, intent, request):
        self.proofs_in(db, intent, request)
        return super().check_in(db, meta, kernel, worker, intent, request)

    def attach_in(self, db, worker, claim, record):
        _, intent = self.bridge.intent_in(db, worker["id"])
        self.proofs_in(db, intent, record["request"])
        return super().attach_in(db, worker, claim, record)


class ConfirmedSettlement(BoundProofs, OwnershipSettlement): pass
class AbsentSettlement(BoundProofs, absence.CreationRecovery): pass


class TerminalHandoff:
    def __init__(self, bridge, outcome):
        require(outcome in ("confirmed", "not_created"), "Explicit terminal outcome required")
        self.bridge = ScopedBridge(bridge)
        self.ledger, self.store, self.outcome = bridge.ledger, bridge.store, outcome
        self.api = (ConfirmedSettlement if outcome == "confirmed" else AbsentSettlement)(self.bridge)

    def candidate_in(self, db, kernel, worker, intent):
        if self.outcome == "not_created":
            claim, record, _ = self.api.candidate_in(db, worker, intent, kernel)
            expected = absence.source_hash(worker, claim)
        else:
            claim, record, state = self.api.lifecycle.state_in(kernel, intent)
            require(record and state["creation"]["outcome"] == "confirmed" and claim["native"]["hostId"] == "local",
                    "Confirmed local native task required")
            require(worker.get("nativeLifecycleHash") == digest(record), "Recover exact native receipt first")
            self.api.lifecycle.attach_in(db, worker, claim, record)  # Same-hash validation only.
            expected = claim["nativeLifecycleHash"]
        lower = max(claim.get("startedAt", claim["createdAt"]), worker["updatedAt"], record["at"] if record else 0)
        return claim, expected, lower

    def state(self, token, worker_id):
        with self.bridge.locked(token) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record = self.api.record_in(kernel, intent)
                attached = False
                if record:
                    self.api.proofs_in(db, intent, record["request"])
                    attached = worker.get("ownershipSettlementHash") == digest(record)
                    if attached: self.api.attach_in(db, worker, claim, record)  # Existing receipt validation only.
                    else:
                        require(not worker.get("ownershipSettlementHash") and local_binding(worker) == record["localBinding"],
                                "Local owner changed; explicit settlement recovery required")
                    expected, lower = record["request"]["expectedHash"], record["at"]
                else: claim, expected, lower = self.candidate_in(db, kernel, worker, intent)
            out = {"workerId": worker_id, "workspaceId": intent["workspaceId"], "outcome": self.outcome,
                   "revision": meta["revision"], "intentHash": digest(intent), "expectedHash": expected,
                   "evidenceAfter": lower, "hostId": worker["hostId"], "threadId": worker["threadId"],
                   "clientThreadId": worker["clientThreadId"], "resourceKeys": intent["resourceKeys"],
                   "settlement": self.api.receipt(worker, record) if record else None,
                   "receiptAttached": attached, "recoveryRequired": bool(record and not attached),
                   "executionAuthorized": False, "nativeCallMade": False, "currentNativeActivity": "not_observed",
                   "trustBoundary": "recorded_binding_not_terminal_evidence"}
            return out

    def proof_add(self, token, worker_id, request):
        proof_request(request)
        require((request["threadId"] is None) == (self.outcome == "not_created"), "Explicit outcome-scoped task identity required")
        # An exact replay never refreshes evidence and remains readable under maintenance.
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            key = request_key(intent, self.outcome, request)
            prior = self.replay_in(db, key, intent, request)
            if prior: return prior
        with self.bridge.locked(token, ownership_change=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            prior = self.replay_in(db, key, intent, request)
            if prior: return prior
            with self.store.tx() as kernel:
                self.api.maintenance_check(kernel)
                _, record = self.api.record_in(kernel, intent)
                require(record is None, "Terminal settlement already committed; no new proof")
                claim, expected, lower = self.candidate_in(db, kernel, worker, intent)
                require(meta["revision"] == request["expectedRevision"] and expected == request["expectedHash"],
                        "Terminal revision or attempt changed")
                require(lower <= request["observedAt"] <= time.time(), "Proof must follow the recorded operation")
                self.store.fresh(request["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
                if request["threadId"]:
                    require(request["threadId"] != worker["clientThreadId"], "Pending client ID is not a task")
                    self.api.lifecycle.unique_identity(kernel, worker_id, {"hostId": "local",
                        "threadId": request["threadId"], "clientThreadId": None})
            report = {"kind": KIND, "workerId": worker_id, "intentHash": digest(intent), "outcome": self.outcome,
                      "request": request, "at": time.time()}
            report_hash = runs.retain(db, KIND, report)
            info = capture(db, "terminal-proof:"+key, request["content"].encode(), {
                "repository": intent["repository"], "name": "terminal-handoff.txt", "orderAt": request["observedAt"],
                "provenance": PROVENANCE, "terminalProofHash": report_hash,
                "references": [{"workerId": worker_id, "intentHash": digest(intent), "hostId": "local",
                                "session": request["threadId"], "at": request["observedAt"]}]})
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, REQUEST, canonical({
                "reportHash": report_hash, "artifactId": info["id"], "retainedAt": info["observedAt"]})))
            self.ledger.event(db, "terminal_proof_retained", {"workerId": worker_id, "artifactId": info["id"]})
            return self.proof_receipt(report, info)

    def replay_in(self, db, key, intent, request):
        prior = pointer_in(db, key)
        if prior is None: return None
        report, info = proof_in(db, prior["artifactId"], intent, request["expectedHash"], self.outcome, request["threadId"])
        require(report["request"] == request, "Terminal proof request ID reused with different content")
        return self.proof_receipt(report, info)

    @staticmethod
    def proof_receipt(report, info):
        return {"artifactId": info["id"], "proofHash": digest(report), "observedAt": report["request"]["observedAt"],
                "retainedAt": info["observedAt"], "packetAccepted": False, "ownershipReleased": False,
                "executionAuthorized": False, "nativeCallMade": False,
                "trustBoundary": "caller_supplied_evidence_not_native_attestation"}

    def settle(self, token, worker_id, request): return self.api.settle(token, worker_id, request)
    def recover(self, token, worker_id): return self.api.recover(token, worker_id)
