"""Internal native observations and correction journal; no native transport.

Evidence is a designated-brain assertion, never authentication of native state.
Receipt recovery can retain ownership after Pause, but cannot resume or release.
"""
import contextlib
import copy
import hashlib
import json
import sqlite3
import time

from . import run_authority as runs
from .admission import HELD, exact, identifier, integer, sha, timestamp
from .core import Refusal, canonical, digest, require

OBSERVATION = {"outcome", "hostId", "threadId", "clientThreadId", "activity", "observedAt", "evidenceHash"}
CONTINUATION = {"operation", "instructionArtifactId", "estimates"}
DELIVERY = {"continuationHash", "hostId", "threadId", "outcome", "observedAt", "evidenceHash", "progress", "activity"}
INFLIGHT = {"intent", "acknowledged", "uncertain"}


def request_shape(request, fields):
    exact(request, {"id", "expectedHash", *fields})
    identifier(request["id"])
    if request["expectedHash"] is not None: sha(request["expectedHash"])
    try:
        size = len(canonical(request).encode())
    except (TypeError, ValueError, RecursionError) as error:
        raise Refusal("Native lifecycle request must be bounded finite JSON") from error
    require(size <= 16000, "Native lifecycle request exceeds its bound")


def table_exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_records'").fetchone() is not None


def native(state):
    creation = state["creation"]
    return {"hostId": creation["hostId"], "threadId": creation["threadId"]} if creation and creation["threadId"] else None


def client(state):
    creation = state["creation"]
    return {"hostId": creation["hostId"], "clientThreadId": creation["clientThreadId"]} if creation and creation["clientThreadId"] else None


def claim_status(state):
    if state.get("runner") and state["runner"]["status"] not in ("reserved", "released"):
        return "starting"  # In-flight acceptance remains capacity-owned.
    creation, continuation = state["creation"], state["continuation"]
    if continuation and continuation["status"] in INFLIGHT: return "starting"
    if creation["outcome"] == "pending": return "starting"
    if creation["outcome"] == "uncertain": return "blocked" if native(state) else "uncertain"
    return "running"  # Ownership/lifecycle, not a claim of currently running activity.


def runner_binding(state):
    runner = state.get("runner")
    return {k: runner[k] for k in ("key", "reservationId", "at", "status")} if runner else None


def runner_owner(worker_id, binding):
    if not binding or binding["status"] == "released": return None
    return {"workerId": worker_id, "key": binding["key"], "reservationId": binding["reservationId"], "since": binding["at"]}


def worker_status(claim, state):
    runner = state.get("runner")
    if runner and runner["status"] != "released":
        return "awaiting_acceptance" if runner["status"] == "reserved" else "accepting"
    return "starting" if claim["status"] == "uncertain" else claim["status"]


def require_runner_clear(state):
    require(not state.get("runner") or state["runner"]["status"] == "released", "Runner still owned; use runner coordination")


def lifecycle_stage(state):
    if state.get("runner") and state["runner"]["status"] != "released": return "runner_" + state["runner"]["status"]
    continuation = state["continuation"]
    return "continuation_inflight" if continuation and continuation["status"] in INFLIGHT else "native_observed"


class NativeLifecycle:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store

    def record_in(self, kernel, key, intent):
        sha(key)
        require(table_exists(kernel), "Native journal is missing; retain ownership")
        row = kernel.execute("SELECT data FROM native_records WHERE hash=? AND claim=? AND length(CAST(data AS BLOB))<=32768",
                             (key, intent["workerId"])).fetchone()
        require(row is not None, "Native journal record is missing or oversized")
        record = json.loads(row[0])
        require(digest(record) == key and record["intentHash"] == digest(intent), "Native journal integrity or owner changed")
        return record

    def state_in(self, kernel, intent):
        claim = self.bridge.owned_claim_in(kernel, intent)
        return self.journal_in(kernel, intent, claim)

    def journal_in(self, kernel, intent, claim):
        """Validate retained native history, including a sealed pre-settlement claim.

        This does not verify current resource ownership or authorize a write;
        active lifecycle callers must continue to use state_in.
        """
        key = claim.get("nativeLifecycleHash")
        if key:
            record = self.record_in(kernel, key, intent); state = record["state"]
            count = kernel.execute("SELECT count(*) FROM native_records WHERE claim=?", (claim["id"],)).fetchone()[0]
            require(record["version"] == count, "Native journal history is incomplete")
            if record["previousHash"] is not None:
                previous = self.record_in(kernel, record["previousHash"], intent)
                require(previous["version"]+1 == record["version"], "Native journal version chain changed")
            require(claim["native"] == native(state) and claim.get("clientNative") == client(state) and
                    claim["status"] == claim_status(state) and
                    claim.get("runnerBinding") == runner_binding(state) and
                    claim.get("continuationReservedTokens", 0) == state["reservedTokens"], "Shared native state diverged from its journal")
        else:
            require(not table_exists(kernel) or not kernel.execute("SELECT 1 FROM native_records WHERE claim=?", (claim["id"],)).fetchone(),
                    "Native journal pointer is missing; explicit recovery required")
            require(claim["status"] == "starting" and claim["native"] is None and
                    not claim.get("clientNative") and not claim.get("continuationReservedTokens"),
                    "Committed shared creation boundary required")
            state = {"creation": None, "continuation": None, "sequence": 0, "noProgress": 0, "reservedTokens": 0}
            record = None
        return claim, record, copy.deepcopy(state)

    def replay_in(self, kernel, intent, kind, request):
        if not table_exists(kernel): return None
        row = kernel.execute("SELECT hash FROM native_records WHERE claim=? AND request=?", (intent["workerId"], request["id"])).fetchone()
        if not row: return None
        record = self.record_in(kernel, row[0], intent)
        require(record["event"] == kind and record["request"] == request, "Native request ID reused with different content")
        return row[0]

    def fresh(self, kernel, observed_at, claim, state):
        timestamp(observed_at)
        self.store.fresh(observed_at, self.store.get(kernel, "meta", 1)["policy"])
        latest = (state["creation"] or {}).get("observedAt", claim["startedAt"])
        if state["continuation"]:
            latest = max(latest, state["continuation"].get("observedAt", state["continuation"]["at"]))
        if state.get("runner"):
            latest = max(latest, state["runner"].get("observedAt", 0), state["runner"].get("launchAt", 0), state["runner"]["at"])
        require(observed_at >= claim["startedAt"] and observed_at > latest, "Native observation is not newer than retained evidence")

    def unique_identity(self, kernel, worker_id, observation):
        host = observation["hostId"]
        ids = {v for k in ("threadId", "clientThreadId") if (v := observation[k]) is not None}
        # Registry write lock is already held by bridge.locked. A separate read
        # connection observes its unchanged committed membership without relocking.
        with contextlib.closing(sqlite3.connect(self.bridge.registry.db.as_uri()+"?mode=ro", uri=True)) as db:
            require(not any(row[0] in ids for row in db.execute("SELECT brain FROM workspaces")), "Native identity belongs to a registered brain")
        for other in self.store.rows(kernel, "claims"):
            if other["id"] == worker_id: continue
            for binding in (other.get("native"), other.get("clientNative"), *other.get("settledNativeIdentities", [])):
                require(not binding or binding["hostId"] != host or not ids.intersection(binding.values()),
                        "Native identity already belongs to another shared claim")
        if kernel.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_claims'").fetchone():
            for other in self.store.rows(kernel, "legacy_claims"):
                require(not ids.intersection(other["pendingClientIds"]), "Native client ID has quarantined ownership")
                for binding in other["nativeIdentities"]:
                    require(binding["hostId"] != host or not ids.intersection(binding.values()), "Native identity has quarantined ownership")

    def append_in(self, kernel, claim, intent, kind, request, state, *, source=None):
        kernel.execute("CREATE TABLE IF NOT EXISTS native_records(hash TEXT PRIMARY KEY, claim TEXT NOT NULL, request TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(claim,request))")
        count = kernel.execute("SELECT count(*) FROM native_records WHERE claim=?", (claim["id"],)).fetchone()[0]
        require(count < 1000, "Native journal requires explicit archival migration")
        record = {"kind": "native_lifecycle", "schemaVersion": 1, "workerId": claim["id"], "intentHash": digest(intent),
                  "version": count+1, "previousHash": claim.get("nativeLifecycleHash"), "event": kind,
                  "request": request, "state": state, "at": time.time()}
        if source is not None: record["source"] = source
        require(len(canonical(record).encode()) <= 32768, "Native journal record exceeds its bound")
        key = digest(record)
        kernel.execute("INSERT INTO native_records VALUES(?,?,?,?)", (key, claim["id"], request["id"], canonical(record)))
        claim.update(nativeLifecycleHash=key, native=native(state), clientNative=client(state), status=claim_status(state),
                     continuationReservedTokens=state["reservedTokens"], estimatedTokens=sum(intent["estimates"].values())+state["reservedTokens"])
        if state.get("runner"): claim["runnerBinding"] = runner_binding(state)
        self.store.put(kernel, "claims", claim["id"], claim)
        self.store.event(kernel, "native_"+kind, id=claim["id"], recordHash=key)
        return record

    def attach_in(self, db, worker, claim, record):
        require(record is not None, "No native result is retained")
        state = record["state"]; continuation = state["continuation"]
        creation = state["creation"]
        for field in ("threadId", "clientThreadId"):
            require(worker.get(field) in (None, creation[field]), "Local native identity diverged; explicit recovery required")
        require(not (worker.get("threadId") or worker.get("clientThreadId")) or worker["hostId"] == creation["hostId"],
                "Local native host diverged; explicit recovery required")
        marker = worker.get("nativeContinuationIntentHash")
        launch_marker = worker.get("runnerLaunchIntentHash")
        if launch_marker or (state.get("runner") or {}).get("intentHash"):
            local = runs.document(db, launch_marker, "runner_launch_intent")
            require(local["workerId"] == worker["id"] and local["intentHash"] == worker["dispatchAdmission"]["intentHash"],
                    "Local runner launch binding changed")
        if launch_marker and launch_marker != (state.get("runner") or {}).get("intentHash"):
            require(worker["status"] == "accepting" and worker["dispatchAdmission"]["stage"] == "runner_launch_pending",
                    "Unmatched runner launch lost its in-flight marker; explicit recovery required")
            return self.receipt(worker, record)
        if marker and (not continuation or continuation["intentHash"] != marker):
            # A local intent may have committed without a shared journal entry.
            # Copying older native state must never clear its in-flight marker.
            require(worker["status"] == "starting" and worker["dispatchAdmission"]["stage"] == "continuation_pending",
                    "Unmatched continuation lost its in-flight marker; explicit recovery required")
            return self.receipt(worker, record)
        key = digest(record)
        meta = self.ledger.get(db, "meta", 1)
        if state.get("runner") or worker.get("runnerBinding"):
            old_owner = runner_owner(worker["id"], worker.get("runnerBinding"))
            new_owner = runner_owner(worker["id"], runner_binding(state))
            require(meta["runner"] == old_owner if old_owner or new_owner else
                    not meta["runner"] or meta["runner"].get("workerId") != worker["id"],
                    "Local runner ownership diverged; explicit recovery required")
        if worker.get("nativeLifecycleHash") == key:
            require(worker["threadId"] == creation["threadId"] and worker["clientThreadId"] == creation["clientThreadId"] and
                    worker["status"] == worker_status(claim, state) and
                    worker.get("runnerBinding") == runner_binding(state) and
                    (not state.get("runner") or worker["dispatchAdmission"]["stage"] == lifecycle_stage(state)) and
                    worker["noProgressCycles"] == state["noProgress"] and worker["dispatchAdmission"]["claimHash"] == digest(claim),
                    "Local native receipt diverged; explicit recovery required")
            return self.receipt(worker, record)
        worker.update(nativeLifecycleHash=key, threadId=creation["threadId"], clientThreadId=creation["clientThreadId"],
                      hostId=creation["hostId"], status=worker_status(claim, state),
                      nativeActivity={k: creation[k] for k in ("activity", "observedAt", "evidenceHash")},
                      noProgressCycles=state["noProgress"], updatedAt=time.time())
        stage = lifecycle_stage(state)
        if state.get("runner"):
            worker["runnerBinding"] = runner_binding(state)
            if old_owner or new_owner:
                meta["runner"] = new_owner
                self.ledger.put(db, "meta", 1, meta)
        worker["dispatchAdmission"].update(stage=stage, claimHash=digest(claim))
        runs.retain(db, "native_lifecycle", record)
        self.ledger.put(db, "workers", worker["id"], worker)
        self.ledger.event(db, "native_lifecycle_attached", {"workerId": worker["id"], "recordHash": key})
        return self.receipt(worker, record)

    @staticmethod
    def receipt(worker, record, historical=None):
        return {"workerId": worker["id"], "recordHash": historical or digest(record),
                "currentHash": digest(record), "attachedHash": worker.get("nativeLifecycleHash"),
                "stage": worker["dispatchAdmission"]["stage"], "executionAuthorized": False,
                "nativeCallMade": False, "ownershipReleased": False,
                **({"runnerStatus": record["state"]["runner"]["status"],
                    "runnerResourceReleased": record["state"]["runner"]["status"] == "released"} if record["state"].get("runner") else {}),
                "trustBoundary": "caller_supplied_external_evidence_not_native_attestation"}

    def observe(self, token, worker_id, request, *, source=None):
        request_shape(request, OBSERVATION)
        if source is not None:
            from .native_supervision import validate_source
            validate_source(source, request)
        require(request["outcome"] in ("pending", "confirmed", "uncertain"), "Invalid creation outcome")
        identifier(request["hostId"]); sha(request["evidenceHash"])
        for key in ("threadId", "clientThreadId"):
            if request[key] is not None: identifier(request[key])
        require(request["activity"] in ("idle", "running", "unknown"), "Invalid native activity")
        require(request["threadId"] is None or request["threadId"] != request["clientThreadId"], "Client ID cannot be used as a task ID")
        if request["outcome"] == "pending": require(request["clientThreadId"] and request["threadId"] is None, "Pending creation needs a client ID only")
        if request["outcome"] == "confirmed": require(request["threadId"] is not None, "Confirmed task ID required")
        if request["outcome"] != "confirmed": require(request["activity"] == "unknown", "Uncertain/pending activity must be unknown")
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record, state = self.state_in(kernel, intent)
                prior = self.replay_in(kernel, intent, "observation", request)
                if not prior:
                    require(request["expectedHash"] == claim.get("nativeLifecycleHash"), "Native journal changed; inspect before recording")
                    self.no_unmatched_intent(worker, state)
                    require_runner_clear(state)
                    self.fresh(kernel, request["observedAt"], claim, state)
                    old = state["creation"]
                    if old:
                        for field in ("hostId", "threadId", "clientThreadId"):
                            require(old[field] is None or old[field] == request[field], "Retained native identity cannot be replaced or erased")
                    self.unique_identity(kernel, worker_id, request)
                    state["creation"] = {key: request[key] for key in OBSERVATION}
                    record = self.append_in(kernel, claim, intent, "observation", request, state, source=source)
            self.attach_in(db, worker, claim, record)
            return self.receipt(worker, record, prior)

    @staticmethod
    def no_unmatched_intent(worker, state):
        launch_marker = worker.get("runnerLaunchIntentHash")
        require(not launch_marker or launch_marker == (state.get("runner") or {}).get("intentHash"),
                "Unmatched local runner launch intent; retain ownership for explicit recovery")
        marker = worker.get("nativeContinuationIntentHash")
        continuation = state["continuation"]
        require(not marker or continuation and continuation["intentHash"] == marker,
                "Unmatched local continuation intent; retain in-flight ownership for explicit recovery")

    def continuation_checks(self, db, meta, kernel, worker, intent, claim, state, request):
        require_runner_clear(state)
        self.bridge.task_in(db, meta, intent["runHash"], intent["queueId"], intent["approvalHash"], worker["id"])
        runs.check_task_in(self.ledger, db, run_hash=intent["runHash"], queue_id=intent["queueId"],
                           approval_hash=intent["approvalHash"], operation="edit")
        allocation = self.bridge.allocation_in(db, kernel, intent["runHash"])
        require(allocation["fingerprint"] == intent["allocationFingerprint"], "Phase allocation changed")
        creation = state["creation"]
        require(creation and creation["outcome"] == "confirmed" and creation["activity"] == "idle", "Fresh confirmed idle task required")
        self.store.fresh(creation["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
        require(not state["continuation"] or state["continuation"]["status"] == "finished", "Continuation already in flight; never resend blindly")
        require(state["noProgress"] < 2, "Two no-progress corrections require a reviewed stop/correction scope")
        rows = self.store.rows(kernel, "claims"); held = [c for c in rows if c["status"] in HELD]
        require(len(held) <= self.store.get(kernel, "meta", 1)["policy"]["maxParallelTasks"] and
                sum(c["allocationId"] == allocation["id"] for c in held) <= allocation["spec"]["limits"]["maxParallelTasks"], "Shared capacity changed")
        self.store.check_budget(kernel, allocation, sum(request["estimates"].values()))
        row = db.execute("SELECT data, CASE WHEN length(content)<=16000 THEN content ELSE NULL END FROM artifact_versions WHERE id=?",
                         (request["instructionArtifactId"],)).fetchone()
        require(row is not None, "Retained correction instruction artifact required")
        artifact = json.loads(row[0]); raw = row[1]
        require(artifact["repository"] == intent["repository"] and raw is not None and
                hashlib.sha256(raw).hexdigest() == artifact["sha256"] and
                artifact["id"] == digest([artifact["key"], artifact["version"], artifact["sha256"]]), "Correction artifact binding or bytes changed")
        # Artifact is retained data. Its contents are never parsed or executed.

    def begin_continuation(self, token, worker_id, request, *, one_shot=False):
        request_shape(request, CONTINUATION)
        require(request["operation"] == "edit", "Only same-scope edit corrections are supported")
        sha(request["instructionArtifactId"])
        exact(request["estimates"], {"workTokens", "reviewTokens", "handoffTokens"})
        for value in request["estimates"].values(): integer(value, 1, 1_000_000_000)
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record, state = self.state_in(kernel, intent)
                prior = self.replay_in(kernel, intent, "continuation", request)
            if prior:
                require(not one_shot, "Continuation send boundary already crossed; never resend")
                self.attach_in(db, worker, claim, record)
                return self.receipt(worker, record, prior)  # Historical receipt, never a second send.
        with self.bridge.locked(token, effects=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record, state = self.state_in(kernel, intent)
                require(request["expectedHash"] == claim.get("nativeLifecycleHash"), "Native journal changed; inspect before continuation")
                self.no_unmatched_intent(worker, state)
                self.continuation_checks(db, meta, kernel, worker, intent, claim, state, request)
            local = {"kind": "native_continuation_intent", "workerId": worker_id, "intentHash": digest(intent), "request": request}
            marker = runs.retain(db, "native_continuation_intent", local)
            require(worker.get("nativeContinuationIntentHash") != marker, "Continuation intent already retained; recover, never resend")
            worker.update(nativeContinuationIntentHash=marker, status="starting", updatedAt=time.time())
            worker["dispatchAdmission"]["stage"] = "continuation_pending"
            self.ledger.put(db, "workers", worker_id, worker)
            self.ledger.event(db, "native_continuation_intent", {"workerId": worker_id, "intentHash": marker})
        with self.bridge.locked(token, effects=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            require(worker.get("nativeContinuationIntentHash") == marker, "Local continuation intent changed")
            with self.store.tx() as kernel:
                claim, record, state = self.state_in(kernel, intent)
                require(request["expectedHash"] == claim.get("nativeLifecycleHash"), "Native journal changed; retain in-flight intent")
                self.continuation_checks(db, meta, kernel, worker, intent, claim, state, request)
                state["sequence"] += 1
                state["reservedTokens"] += sum(request["estimates"].values())
                state["continuation"] = {"intentHash": marker, "sequence": state["sequence"], "status": "intent", "at": time.time()}
                state["creation"]["activity"] = "unknown"
                record = self.append_in(kernel, claim, intent, "continuation", request, state)
            self.attach_in(db, worker, claim, record)
            return self.receipt(worker, record)

    def delivery(self, token, worker_id, request):
        request_shape(request, DELIVERY)
        sha(request["continuationHash"]); sha(request["evidenceHash"])
        identifier(request["hostId"]); identifier(request["threadId"])
        require(request["outcome"] in ("acknowledged", "uncertain", "finished"), "Invalid continuation outcome")
        require(type(request["progress"]) is bool if request["outcome"] == "finished" else request["progress"] is None,
                "Only a finished turn can report progress")
        require(request["activity"] == ("idle" if request["outcome"] == "finished" else "unknown"),
                "Finished turn requires an explicit fresh idle observation")
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record, state = self.state_in(kernel, intent)
                prior = self.replay_in(kernel, intent, "delivery", request)
                if not prior:
                    require(request["expectedHash"] == claim.get("nativeLifecycleHash"), "Native journal changed; inspect before recording")
                    self.no_unmatched_intent(worker, state)
                    continuation = state["continuation"]
                    require_runner_clear(state)
                    require(continuation and continuation["intentHash"] == request["continuationHash"] and
                            continuation["status"] in INFLIGHT, "Exact in-flight continuation required")
                    require(claim["native"] == {k: request[k] for k in ("hostId", "threadId")}, "Continuation result belongs to a different task")
                    self.fresh(kernel, request["observedAt"], claim, state)
                    if request["outcome"] == "finished":
                        require(continuation["status"] == "acknowledged", "Acknowledge or reconcile delivery before finishing its turn")
                        state["noProgress"] = 0 if request["progress"] else state["noProgress"]+1
                        state["creation"].update(outcome="confirmed", activity="idle", observedAt=request["observedAt"], evidenceHash=request["evidenceHash"])
                    continuation.update(status=request["outcome"], observedAt=request["observedAt"], evidenceHash=request["evidenceHash"])
                    record = self.append_in(kernel, claim, intent, "delivery", request, state)
            self.attach_in(db, worker, claim, record)
            return self.receipt(worker, record, prior)

    def recover(self, token, worker_id):
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record, _ = self.state_in(kernel, intent)
            return self.attach_in(db, worker, claim, record)
