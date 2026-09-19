"""Internal terminal accounting/release; not acceptance or native attestation.

Registry -> workspace -> admission. Shared settlement commits before its local
receipt. An interrupted local attachment keeps the old local owner conservative;
the sealed shared claim prevents any further native lifecycle operation.
"""
import copy
import hashlib
import json
import time

from . import run_authority as runs
from .admission import COUNTERS, counters, exact, identifier, resource, sha, timestamp
from .admission_legacy import require_open
from .core import Refusal, canonical, digest, require
from .native_lifecycle import NativeLifecycle


def pair(row):
    return row["hostId"], row["threadId"]


def observation(row):
    timestamp(row["observedAt"]); sha(row["evidenceHash"])


def local_binding(worker):
    return {k: copy.deepcopy(worker.get(k)) for k in ("status", "hostId", "threadId", "clientThreadId",
            "nativeLifecycleHash", "nativeContinuationIntentHash", "noProgressCycles", "dispatchAdmission")} | {
            k: copy.deepcopy(worker[k]) for k in ("runnerLaunchIntentHash", "runnerBinding") if k in worker}


def validate(request):
    exact(request, {"id", "expectedHash", "inventory", "resources", "usage"})
    identifier(request["id"]); sha(request["expectedHash"])
    try:
        size = len(canonical(request).encode())
    except (TypeError, ValueError, RecursionError) as error:
        raise Refusal("Settlement evidence must be bounded finite JSON") from error
    require(size <= 16000, "Settlement evidence exceeds its bound")
    inventory = request["inventory"]
    exact(inventory, {"observedAt", "evidenceHash", "complete", "includesDescendants", "pendingResolved", "effectsComplete", "tasks"})
    observation(inventory)
    for field in ("complete", "includesDescendants", "pendingResolved", "effectsComplete"):
        require(inventory[field] is True, "Complete terminal inventory and resolved effects required")
    require(isinstance(inventory["tasks"], list) and 1 <= len(inventory["tasks"]) <= 16, "Bounded terminal task inventory required")
    seen = set()
    for task in inventory["tasks"]:
        exact(task, {"hostId", "threadId", "parent", "status", "observedAt", "evidenceHash", "checkpointArtifactId"})
        identifier(task["hostId"]); identifier(task["threadId"]); observation(task); sha(task["checkpointArtifactId"])
        require(task["status"] == "idle", "Every terminal task must be observed idle")
        require(pair(task) not in seen, "Duplicate terminal task")
        seen.add(pair(task))
        if task["parent"] is not None:
            exact(task["parent"], {"hostId", "threadId"})
            identifier(task["parent"]["hostId"]); identifier(task["parent"]["threadId"])
    require(isinstance(request["resources"], list) and 1 <= len(request["resources"]) <= 4, "Exact repository cleanup required")
    seen = set()
    for row in request["resources"]:
        exact(row, {"key", "processesExited", "cleanupObserved", "observedAt", "evidenceHash"})
        resource(row["key"]); observation(row)
        require(row["key"] not in seen, "Duplicate cleanup resource")
        require(row["processesExited"] is True and row["cleanupObserved"] is True, "Independent exit and cleanup observations required")
        seen.add(row["key"])
    usage = request["usage"]
    exact(usage, {"observedAt", "evidenceHash", "complete", "sessions"}); observation(usage)
    require(usage["complete"] is True and isinstance(usage["sessions"], list) and
            len(usage["sessions"]) == len(inventory["tasks"]), "Complete task usage coverage required")
    seen = set()
    for row in usage["sessions"]:
        exact(row, {"hostId", "threadId", "counterEpoch", "counters", "complete", "observedAt", "evidenceHash"})
        identifier(row["hostId"]); identifier(row["threadId"]); sha(row["counterEpoch"]); observation(row)
        require(row["complete"] is True, "Complete cumulative task counters required")
        counters(row["counters"])
        require(pair(row) not in seen, "Duplicate task usage")
        seen.add(pair(row))
    require(seen == {pair(t) for t in inventory["tasks"]}, "Exact task usage identities required")


class OwnershipSettlement:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.lifecycle = NativeLifecycle(bridge)

    def record_in(self, kernel, intent):
        claim = self.bridge.bound_claim_in(kernel, intent)
        exists = kernel.execute("SELECT 1 FROM sqlite_master WHERE name='ownership_settlements'").fetchone()
        row = kernel.execute("SELECT hash,CASE WHEN length(CAST(data AS BLOB))<=32768 THEN data ELSE NULL END FROM ownership_settlements WHERE claim=?", (claim["id"],)).fetchone() if exists else None
        if not row:
            require(not claim.get("settlementHash") and claim["status"] != "settled", "Settlement journal is missing; explicit recovery required")
            return claim, None
        require(row[1] is not None, "Settlement journal exceeds its bound")
        record = json.loads(row[1])
        require(digest(record) == row[0] == claim.get("settlementHash") and record["intentHash"] == digest(intent),
                "Settlement journal integrity or binding changed")
        expected = self.settled_claim(record)
        require(claim == expected, "Shared settlement diverged from its journal")
        require(not kernel.execute("SELECT 1 FROM resources WHERE claim=?", (claim["id"],)).fetchone(), "Settled claim still owns resources")
        # Receipt recovery must not hide removal/corruption of native history.
        _, native_record, _ = self.lifecycle.journal_in(kernel, intent, record["priorClaim"])
        require(native_record == record["nativeRecord"], "Terminal native history changed")
        return claim, record

    @staticmethod
    def settled_claim(record):
        return {**record["priorClaim"], "status": "settled", "actual": record["actual"], "settledAt": record["at"],
                "settlementHash": digest(record), "settledNativeIdentities": [
                    {k: t[k] for k in ("hostId", "threadId")} for t in record["request"]["inventory"]["tasks"]]}

    def maintenance_check(self, kernel):
        # Pause/expired approval do not prevent relinquishment, but an in-progress
        # enrollment/adoption inventory cannot be changed behind its review.
        require_open(self.store.root, self.store.get(kernel, "meta", 1))

    def known_descendants(self, db, root):
        known = {root}
        rows = db.execute("SELECT id,CASE WHEN length(CAST(data AS BLOB))<=600000 THEN data ELSE NULL END FROM snapshots WHERE kind='workspace_pause_evidence' LIMIT 1001")
        total = 0
        for count, (key, raw) in enumerate(rows, 1):
            require(raw is not None, "Pause history exceeds its bound")
            total += len(raw.encode())
            require(count <= 1000 and total <= 2_000_000, "Pause history requires explicit archival before settlement")
            record = json.loads(raw)
            require(digest(record) == key, "Pause history integrity changed")
            tasks = {pair(t): t for t in record["document"]["tasks"]}
            # Only this root's descendants, never unrelated tasks in the pause.
            for task in tasks:
                cursor, seen = task, set()
                while cursor is not None and cursor not in seen:
                    if cursor == root:
                        known.add(task); break
                    if cursor not in tasks: break
                    seen.add(cursor)
                    parent = tasks[cursor]["parent"]
                    cursor = pair(parent) if parent else None
        return known

    def artifact_in(self, db, intent, task, lower):
        row = db.execute("SELECT data,CASE WHEN length(content)<=16000 THEN content ELSE NULL END FROM artifact_versions WHERE id=?",
                         (task["checkpointArtifactId"],)).fetchone()
        require(row is not None, "Retained task handoff artifact required")
        info, raw = json.loads(row[0]), row[1]
        require(raw is not None and hashlib.sha256(raw).hexdigest() == info["sha256"] and
                info["id"] == task["checkpointArtifactId"] == digest([info["key"], info["version"], info["sha256"]]), "Handoff artifact bytes or version changed")
        require(info["repository"] == intent["repository"] and lower <= info["observedAt"] <= task["observedAt"] and
                any(r.get("session") == task["threadId"] for r in info.get("references", [])), "Task-scoped post-operation handoff required")

    def check_in(self, db, meta, kernel, worker, intent, request):
        self.maintenance_check(kernel)
        require(meta["runner"] is None, "Local runner ownership must be reconciled first")
        require(not kernel.execute("SELECT 1 FROM resources WHERE claim=? AND id LIKE 'runner:%'", (worker["id"],)).fetchone(), "Shared runner is still owned")
        claim, native_record, state = self.lifecycle.state_in(kernel, intent)
        require(request["expectedHash"] == claim.get("nativeLifecycleHash"), "Native journal changed before settlement")
        self.lifecycle.no_unmatched_intent(worker, state)
        require(native_record is not None and state["creation"]["outcome"] == "confirmed" and
                state["creation"]["activity"] == "idle", "Confirmed idle task required; unresolved creation cannot settle")
        require(not state["continuation"] or state["continuation"]["status"] == "finished", "Continuation remains unresolved")
        # Do not implicitly repair a detached or corrupted local native receipt.
        require(worker.get("nativeLifecycleHash") == request["expectedHash"] and
                worker["dispatchAdmission"]["claimHash"] == digest(claim) and
                worker["status"] == "running" and worker["noProgressCycles"] == state["noProgress"] and
                worker["dispatchAdmission"]["stage"] == "native_observed" and
                {k: worker[k] for k in ("hostId", "threadId")} == claim["native"] and
                worker["clientThreadId"] == state["creation"]["clientThreadId"], "Recover exact local native receipt before settlement")
        require(not any(c["kind"] in ("checkpoint", "archive") and c["status"] in ("queued", "processing") and
                        c["payload"].get("workerId") == worker["id"] for c in self.ledger.all(db, "commands")), "Worker control remains unresolved")
        allocation = self.store.get(kernel, "allocations", intent["allocationId"])
        require(allocation["fingerprint"] == intent["allocationFingerprint"] == digest(allocation["spec"]) and
                allocation["spec"]["repositories"][intent["repository"]] == intent["resourceKeys"], "Phase allocation changed")
        policy = self.store.get(kernel, "meta", 1)["policy"]
        def fresh(row, lower):
            self.store.fresh(row["observedAt"], policy)
            require(row["observedAt"] >= lower, "Terminal evidence predates the retained operation or observation")
        fresh(state["creation"], claim["startedAt"])
        inventory, usage = request["inventory"], request["usage"]
        tasks = {pair(t): t for t in inventory["tasks"]}; root = pair(claim["native"])
        require(root in tasks and tasks[root]["parent"] is None, "Exact root task required")
        require(self.known_descendants(db, root) <= set(tasks), "Retained descendant missing from terminal inventory")
        lower = max(claim["startedAt"], native_record["at"], (state["continuation"] or {}).get("at", 0))
        for key, task in tasks.items():
            cursor, seen = key, set()
            while cursor != root:
                require(cursor in tasks and cursor not in seen and tasks[cursor]["parent"] is not None, "Foreign or cyclic task ancestry")
                seen.add(cursor); cursor = pair(tasks[cursor]["parent"])
            self.lifecycle.unique_identity(kernel, worker["id"], {**task, "clientThreadId": None})
            require(task["threadId"] != state["creation"]["clientThreadId"], "Pending client ID is not a task")
            fresh(task, max(lower, native_record["at"]))
            self.artifact_in(db, intent, task, lower)
        latest = max(t["observedAt"] for t in tasks.values())
        fresh(inventory, latest)
        require(sorted(r["key"] for r in request["resources"]) == intent["resourceKeys"], "Exact owned repository cleanup required")
        for row in request["resources"]: fresh(row, latest)
        actual = {k: 0 for k in COUNTERS}
        for row in usage["sessions"]:
            fresh(row, max(inventory["observedAt"], tasks[pair(row)]["observedAt"]))
            for k in COUNTERS: actual[k] += row["counters"][k]
        fresh(usage, max(r["observedAt"] for r in usage["sessions"]))
        counters(actual)
        return claim, native_record, actual

    def commit_in(self, kernel, record):
        key = digest(record)
        require(len(canonical(record).encode()) <= 32768, "Settlement record exceeds its bound")
        kernel.execute("CREATE TABLE IF NOT EXISTS ownership_settlements(claim TEXT PRIMARY KEY, hash TEXT UNIQUE NOT NULL, data TEXT NOT NULL)")
        kernel.execute("INSERT INTO ownership_settlements VALUES(?,?,?)", (record["workerId"], key, canonical(record)))
        claim = self.settled_claim(record)
        self.store.put(kernel, "claims", claim["id"], claim)
        # check_in verified the exact owned key set, including absence of runners.
        kernel.execute("DELETE FROM resources WHERE claim=?", (claim["id"],))
        self.store.event(kernel, "ownership_settled", id=claim["id"], settlementHash=key)
        return claim

    def attach_in(self, db, worker, claim, record):
        key = digest(record)
        if worker.get("ownershipSettlementHash") == key:
            expected = copy.deepcopy(record["localBinding"])
            expected["status"] = "settled"
            expected["dispatchAdmission"].update(stage="settled", claimHash=digest(claim))
            require(local_binding(worker) == expected and runs.document(db, key, "ownership_settlement") == record,
                    "Local settlement receipt diverged")
            return self.receipt(worker, record)
        require(not worker.get("ownershipSettlementHash") and local_binding(worker) == record["localBinding"],
                "Local owner changed; explicit settlement recovery required")
        runs.retain(db, "ownership_settlement", record)
        worker.update(status="settled", ownershipSettlementHash=key, settledAt=record["at"], updatedAt=time.time())
        worker["dispatchAdmission"].update(stage="settled", claimHash=digest(claim))
        self.ledger.put(db, "workers", worker["id"], worker)
        q = self.ledger.get(db, "queue", worker["queueId"])
        q.update(status="blocked", held=True, reason="Native ownership settled; packet acceptance requires separate result review")
        self.ledger.put(db, "queue", q["id"], q)
        self.ledger.event(db, "ownership_settlement_attached", {"workerId": worker["id"], "settlementHash": key})
        return self.receipt(worker, record)

    @staticmethod
    def receipt(worker, record):
        return {"workerId": worker["id"], "settlementHash": digest(record), "stage": "settled",
                "actualTokens": counters(record["actual"]), "ownershipReleased": True, "packetAccepted": False,
                "executionAuthorized": False, "nativeCallMade": False,
                "trustBoundary": "caller_supplied_external_evidence_not_native_attestation"}

    def settle(self, token, worker_id, request):
        validate(request)
        with self.bridge.locked(token, ownership_change=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record = self.record_in(kernel, intent)
                if record:
                    require(record["request"] == request, "Settlement already recorded with different evidence")
                else:
                    claim, native_record, actual = self.check_in(db, meta, kernel, worker, intent, request)
                    record = {"kind": "ownership_settlement", "schemaVersion": 1, "workerId": worker_id,
                              "intentHash": digest(intent), "request": copy.deepcopy(request), "priorClaim": claim,
                              "nativeRecord": native_record, "localBinding": local_binding(worker), "actual": actual, "at": self.store.clock()}
                    claim = self.commit_in(kernel, record)
            return self.attach_in(db, worker, claim, record)

    def recover(self, token, worker_id):
        """Receipt only, including after Pause/expiry; never create a settlement."""
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record = self.record_in(kernel, intent)
                require(record is not None, "No committed settlement to recover")
            return self.attach_in(db, worker, claim, record)
