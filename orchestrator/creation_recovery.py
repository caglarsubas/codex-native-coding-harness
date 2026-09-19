"""Explicit non-creation accounting, not absence inference or retry authority.

Uses the existing terminal journal and shared-first receipt protocol. No native
transport or independent host observation; supplied evidence remains assertions.
"""
import copy
import hashlib
import json

from . import run_authority as runs
from .admission import counters, exact, identifier, resource, sha
from .core import Refusal, canonical, digest, require
from .native_lifecycle import request_shape, table_exists
from .ownership_settlement import OwnershipSettlement, local_binding, observation


def source_hash(worker, claim):
    return digest({"claim": claim, "localBinding": local_binding(worker)})


def validate(request):
    request_shape(request, {"inventory", "resources", "usage", "reconciliationArtifactId"})
    sha(request["expectedHash"]); sha(request["reconciliationArtifactId"])
    inventory = request["inventory"]
    exact(inventory, {"intentHash", "hostId", "clientThreadId", "outcome", "requestFinal", "complete", "includesDescendants",
                      "pendingResolved", "effectsComplete", "tasks", "observedAt", "evidenceHash"})
    sha(inventory["intentHash"]); identifier(inventory["hostId"]); observation(inventory)
    if inventory["clientThreadId"] is not None: identifier(inventory["clientThreadId"])
    require(inventory["outcome"] == "not_created" and inventory["tasks"] == [], "Explicit no-task creation outcome required")
    for field in ("requestFinal", "complete", "includesDescendants", "pendingResolved", "effectsComplete"):
        require(inventory[field] is True, "Final request, complete absence inventory and resolved effects required")
    require(isinstance(request["resources"], list) and 1 <= len(request["resources"]) <= 4, "Exact repository cleanup required")
    seen = set()
    for row in request["resources"]:
        exact(row, {"key", "processesExited", "cleanupObserved", "observedAt", "evidenceHash"})
        resource(row["key"]); observation(row)
        require(row["key"] not in seen and row["processesExited"] is True and row["cleanupObserved"] is True,
                "Unique resources with complete exit and cleanup evidence required")
        seen.add(row["key"])
    usage = request["usage"]
    exact(usage, {"intentHash", "counterEpoch", "counters", "complete", "observedAt", "evidenceHash"})
    sha(usage["intentHash"]); sha(usage["counterEpoch"]); observation(usage)
    require(usage["complete"] is True and counters(usage["counters"]) == 0,
            "Explicit complete zero task usage required; missing or consumed tokens are not absence")


def artifact_in(db, request, worker_id, intent_hash, repository, lower=0):
    row = db.execute("SELECT data,CASE WHEN length(content)<=16000 THEN content ELSE NULL END FROM artifact_versions WHERE id=?",
                     (request["reconciliationArtifactId"],)).fetchone()
    require(row is not None, "Retained attempt-scoped reconciliation artifact required")
    info, raw = json.loads(row[0]), row[1]
    require(raw is not None and hashlib.sha256(raw).hexdigest() == info["sha256"] and
            info["id"] == request["reconciliationArtifactId"] == digest([info["key"], info["version"], info["sha256"]]),
            "Reconciliation artifact bytes or version changed")
    require(info["repository"] == repository and lower <= info["observedAt"] <= request["inventory"]["observedAt"] and
            any(r.get("workerId") == worker_id and r.get("intentHash") == intent_hash for r in info.get("references", [])),
            "Post-attempt artifact must bind this worker and exact dispatch intent")


class CreationRecovery(OwnershipSettlement):
    kind = "creation_recovery"
    queue_reason = "Creation reconciled as not created; attempt closed and packet held; no retry authorized"
    validate = staticmethod(validate)

    def history_in(self, kernel, intent, claim):
        require(claim["native"] is None and not claim.get("continuationReservedTokens") and not claim.get("runnerBinding"),
                "Known native work, continuation or runner requires its own terminal coordinator")
        if claim["status"] == "reserved":
            require(not claim.get("startedAt") and not claim.get("clientNative") and not claim.get("nativeLifecycleHash") and
                    (not table_exists(kernel) or not kernel.execute("SELECT 1 FROM native_records WHERE claim=?", (claim["id"],)).fetchone()),
                    "Reserved claim has conflicting creation history")
            return claim, None, None  # Local-only creation boundary is checked separately.
        _, record, state = super().history_in(kernel, intent, claim)
        # Walk the whole bounded chain: no earlier confirmed task/descendant can
        # become absent merely because the latest projection is unknown.
        current, count, size = record, 0, 0
        while current:
            count += 1; size += len(canonical(current).encode())
            require(count <= 1000 and size <= 2_000_000, "Creation history requires explicit archival")
            creation, retained = current["state"]["creation"], current["state"]
            require(creation and creation["threadId"] is None and creation["outcome"] in ("pending", "uncertain") and
                    not retained["continuation"] and not retained.get("runner") and not retained["reservedTokens"],
                    "Previously observed native work cannot be declared not created")
            previous = current["previousHash"]
            if previous is None:
                require(current["version"] == 1, "Creation journal chain is incomplete")
                break
            prior = self.lifecycle.record_in(kernel, previous, intent)
            require(prior["version"] + 1 == current["version"], "Creation journal chain changed")
            current = prior
        return claim, record, state

    def candidate_in(self, db, worker, intent, kernel):
        claim = self.bridge.owned_claim_in(kernel, intent)
        _, record, state = self.history_in(kernel, intent, claim)
        require(not worker["threadId"] and not worker.get("ownershipSettlementHash") and
                not worker.get("nativeContinuationIntentHash") and not worker.get("runnerLaunchIntentHash") and
                not worker.get("runnerBinding"), "Local native work or terminal marker requires explicit reconciliation")
        require(worker["dispatchAdmission"]["claimHash"] == digest(claim), "Recover the exact claim receipt first")
        if record:
            require(worker.get("nativeLifecycleHash") == digest(record), "Recover the exact native receipt first")
            self.lifecycle.attach_in(db, worker, claim, record)  # Same-hash validation, no writes.
        else:
            require(not worker.get("nativeLifecycleHash") and worker["clientThreadId"] is None and
                    worker["status"] == "starting" and worker["dispatchAdmission"]["stage"] == (
                        "creation_pending" if claim["status"] == "reserved" else "creation_intent"),
                    "An attached attempted creation boundary is required; unattempted or detached reservation refused")
        return claim, record, state

    def inspect(self, token, worker_id):
        """Diagnostic binding only. Does not infer absence, refresh or retain evidence."""
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, settled = self.record_in(kernel, intent)
                if settled: return self.receipt(worker, settled)
                claim, record, _ = self.candidate_in(db, worker, intent, kernel)
            return {"workerId": worker_id, "sourceHash": source_hash(worker, claim), "intentHash": digest(intent),
                    "nativeRecordHash": digest(record) if record else None, "hostId": worker["hostId"],
                    "clientThreadId": worker["clientThreadId"], "reconciliationRequired": True,
                    "executionAuthorized": False, "ownershipReleased": False, "nativeCallMade": False}

    def no_known_tasks(self, db, meta, worker):
        retained_workers = (meta.get("brainControl") or {}).get("retainedWorkers", [])
        require(not any(w["id"] == worker["id"] and w.get("threadId") for w in retained_workers),
                "Pause retained a native task for this attempt")
        rows = db.execute("SELECT id,CASE WHEN length(CAST(data AS BLOB))<=600000 THEN data ELSE NULL END FROM snapshots WHERE kind='workspace_pause_evidence' LIMIT 1001")
        size = 0
        for count, (key, raw) in enumerate(rows, 1):
            require(raw is not None, "Pause history exceeds its bound")
            size += len(raw.encode())
            require(count <= 1000 and size <= 2_000_000, "Pause history requires explicit archival")
            record = json.loads(raw)
            require(digest(record) == key, "Pause history integrity changed")
            require(not any(t["workerId"] == worker["id"] or (worker["clientThreadId"] and
                        t["hostId"] == worker["hostId"] and t["threadId"] == worker["clientThreadId"])
                        for t in record["document"]["tasks"]), "Previously observed tasks contradict non-creation")

    def check_in(self, db, meta, kernel, worker, intent, request):
        self.maintenance_check(kernel)
        require(meta["runner"] is None, "Local runner ownership must be reconciled first")
        claim, record, _ = self.candidate_in(db, worker, intent, kernel)
        require(request["expectedHash"] == source_hash(worker, claim), "Creation source changed; inspect and reconcile again")
        require(not any(c["kind"] in ("checkpoint", "archive") and c["status"] in ("queued", "processing") and
                        c["payload"].get("workerId") == worker["id"] for c in self.ledger.all(db, "commands")), "Worker control remains unresolved")
        self.no_known_tasks(db, meta, worker)
        allocation = self.store.get(kernel, "allocations", intent["allocationId"])
        require(allocation["fingerprint"] == intent["allocationFingerprint"] == digest(allocation["spec"]) and
                allocation["spec"]["repositories"][intent["repository"]] == intent["resourceKeys"], "Phase allocation changed")
        inventory, usage = request["inventory"], request["usage"]
        require(inventory["intentHash"] == usage["intentHash"] == digest(intent) and inventory["hostId"] == worker["hostId"] and
                inventory["clientThreadId"] == worker["clientThreadId"], "Exact creation intent, host and retained pending ID required")
        policy = self.store.get(kernel, "meta", 1)["policy"]
        lower = max(claim.get("startedAt", claim["createdAt"]), worker["updatedAt"], record["at"] if record else 0)
        def fresh(row, after):
            self.store.fresh(row["observedAt"], policy)
            require(row["observedAt"] >= after, "Non-creation evidence predates the retained attempt or observation")
        fresh(inventory, lower)
        artifact_in(db, request, worker["id"], digest(intent), intent["repository"], lower)
        require(sorted(r["key"] for r in request["resources"]) == intent["resourceKeys"], "Exact owned repository cleanup required")
        for cleanup in request["resources"]: fresh(cleanup, inventory["observedAt"])
        fresh(usage, max(r["observedAt"] for r in request["resources"]))
        return claim, record, copy.deepcopy(usage["counters"])

    def attach_in(self, db, worker, claim, record):
        artifact_in(db, record["request"], worker["id"], record["intentHash"], worker["repository"])
        return super().attach_in(db, worker, claim, record)

    @staticmethod
    def settled_claim(record):
        return {**OwnershipSettlement.settled_claim(record), "creationOutcome": "not_created"}

    @staticmethod
    def receipt(worker, record):
        return {**OwnershipSettlement.receipt(worker, record), "creationOutcome": "not_created", "retryAuthorized": False}


def local_absence_receipt(db, worker):
    """Local hash-bound projection for Pause; never shared release or fresh evidence."""
    key = worker.get("ownershipSettlementHash")
    if not key or worker.get("threadId"): return False
    try:
        record = runs.document(db, key, CreationRecovery.kind)
        validate(record["request"])
        artifact_in(db, record["request"], worker["id"], record["intentHash"], worker["repository"])
        claim = CreationRecovery.settled_claim(record)
        expected = copy.deepcopy(record["localBinding"])
        expected["status"] = "settled"
        expected["dispatchAdmission"].update(stage="settled", claimHash=digest(claim))
        return (record["workerId"] == worker["id"] and record["intentHash"] == worker["dispatchAdmission"]["intentHash"] and
                record["priorClaim"]["native"] is None and record["request"]["inventory"]["outcome"] == "not_created" and
                local_binding(worker) == expected)
    except (Refusal, KeyError, TypeError, ValueError):
        return False  # Missing/corrupt receipts must still block parking.
