"""Internal standard-policy runner journal. No process or native execution.

One reservation/launch per worker pending a separately approved retry contract.
External occupancy/process/cleanup evidence remains a trusted caller assertion.
"""
import hashlib
import json
import time

from . import run_authority as runs
from .admission import HELD, exact, identifier, integer, resource, sha
from .admission_legacy import require_open
from .core import digest, require
from .native_lifecycle import NativeLifecycle, request_shape
from .task_contracts import document_in

ACQUIRE = {"runnerKey", "executionHash", "instructionArtifactId", "estimates", "observation"}
BEGIN = {"runnerKey", "reservationId", "observation"}
OBSERVE = {"runnerKey", "reservationId", "hostId", "threadId", "outcome", "processIdentityHash", "exitCode",
           "processTreeExited", "observedAt", "evidenceHash"}
RELEASE = {"runnerKey", "reservationId", "outcome", "observedAt", "evidenceHash", "nativeEvidenceHash", "nativeIdle",
           "runnerIdle", "cleanupObserved", "processesExited", "complete"}


def standard_policy(seed):
    require(seed["policyProfile"] == "standard", "Harness requires the trusted acceptance adapter and packet attempt contract")


class RunnerCoordination(NativeLifecycle):
    def attached(self, db, worker, claim, record):
        require(record and worker.get("nativeLifecycleHash") == digest(record), "Recover the latest native/runner receipt first")
        self.attach_in(db, worker, claim, record)  # Exact same-hash branch validates without writing.

    def idle_proof(self, kernel, claim, record, state, observation):
        exact(observation, {"state", "complete", "cleanupObserved", "observedAt", "evidenceHash"})
        require(observation["state"] == "idle" and observation["complete"] is True and observation["cleanupObserved"] is True,
                "Complete idle and clean runner observation required")
        sha(observation["evidenceHash"])
        self.fresh(kernel, observation["observedAt"], claim, state)
        require(observation["observedAt"] > record["at"], "Runner observation predates retained journal")

    def work_checks(self, db, meta, kernel, worker, intent, claim, state, request, *, launching=False):
        from .model_policy import require_observed
        require_observed(self.ledger, db, worker, intent, state)
        self.bridge.task_in(db, meta, intent["runHash"], intent["queueId"], intent["approvalHash"], worker["id"],
                            runner_owner=worker["id"] if launching else None)
        runs.check_task_in(self.ledger, db, run_hash=intent["runHash"], queue_id=intent["queueId"],
                           approval_hash=intent["approvalHash"], operation="test")
        allocation = self.bridge.allocation_in(db, kernel, intent["runHash"])
        require(allocation["fingerprint"] == intent["allocationFingerprint"] and request["runnerKey"] in allocation["spec"]["runners"],
                "Runner is outside the pinned phase allocation")
        require(not any(c["kind"] in ("checkpoint", "archive") and c["status"] in ("queued", "processing") and
                        c["payload"].get("workerId") == worker["id"] for c in self.ledger.all(db, "commands")), "Worker control is unresolved")
        creation = state["creation"]
        require(creation and creation["outcome"] == "confirmed" and creation["activity"] == "idle", "Confirmed idle native task required")
        self.store.fresh(creation["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
        require(not state["continuation"] or state["continuation"]["status"] == "finished", "Correction remains in flight")
        require(state["noProgress"] < 2, "Exhausted correction scope requires review before acceptance")
        held = [c for c in self.store.rows(kernel, "claims") if c["status"] in HELD]
        require(len(held) <= self.store.get(kernel, "meta", 1)["policy"]["maxParallelTasks"] and
                sum(c["allocationId"] == allocation["id"] for c in held) <= allocation["spec"]["limits"]["maxParallelTasks"], "Shared capacity changed")
        seed = document_in(db, intent["seedHash"], "seed", 512000)
        require(seed is not None, "Retained exact seed required")
        standard_policy(seed)
        binding = state["runner"] if launching else request
        require(binding["executionHash"] == digest(seed["execution"]), "Runner execution contract does not match the approved seed")
        aid = binding["instructionArtifactId"]
        row = db.execute("SELECT data,CASE WHEN length(content)<=16000 THEN content ELSE NULL END FROM artifact_versions WHERE id=?", (aid,)).fetchone()
        require(row is not None, "Retained runner instruction artifact required")
        artifact, raw = json.loads(row[0]), row[1]
        require(raw is not None and hashlib.sha256(raw).hexdigest() == artifact["sha256"] and
                artifact["repository"] == intent["repository"] and
                aid == artifact["id"] == digest([artifact["key"], artifact["version"], artifact["sha256"]]), "Runner instruction binding or bytes changed")
        if not launching: self.store.check_budget(kernel, allocation, sum(request["estimates"].values()))

    def current_runner(self, state, request):
        runner = state.get("runner")
        require(runner and runner["key"] == request["runnerKey"] and runner["reservationId"] == request["reservationId"],
                "Exact retained runner reservation required")
        return runner

    def replay(self, token, worker_id, kind, request):
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record, _ = self.state_in(kernel, intent)
                prior = self.replay_in(kernel, intent, kind, request)
            if prior:
                self.attach_in(db, worker, claim, record)
                return self.receipt(worker, record, prior)

    def acquire(self, token, worker_id, request):
        request_shape(request, ACQUIRE); resource(request["runnerKey"], "runner")
        sha(request["executionHash"]); sha(request["instructionArtifactId"])
        exact(request["estimates"], {"workTokens", "reviewTokens", "handoffTokens"})
        for amount in request["estimates"].values(): integer(amount, 1, 1_000_000_000)
        prior = self.replay(token, worker_id, "runner_acquire", request)
        if prior: return prior
        with self.bridge.locked(token, effects=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record, state = self.state_in(kernel, intent)
                require(request["expectedHash"] == digest(record), "Native journal changed before runner reservation")
                self.no_unmatched_intent(worker, state); self.attached(db, worker, claim, record)
                require(not state.get("runner"), "One runner attempt per worker; explicit retry contract required")
                self.work_checks(db, meta, kernel, worker, intent, claim, state, request)
                self.idle_proof(kernel, claim, record, state, request["observation"])
                require(not kernel.execute("SELECT 1 FROM resources WHERE id=?", (request["runnerKey"],)).fetchone(), "Shared runner already owned")
                at = time.time()
                state["runner"] = {"key": request["runnerKey"], "reservationId": request["id"], "status": "reserved", "at": at,
                    "executionHash": request["executionHash"], "instructionArtifactId": request["instructionArtifactId"],
                    "estimates": request["estimates"], "observedAt": request["observation"]["observedAt"], "attempt": 1}
                state["reservedTokens"] += sum(request["estimates"].values())
                kernel.execute("INSERT INTO resources VALUES(?,?,?)", (request["runnerKey"], worker_id, at))
                record = self.append_in(kernel, claim, intent, "runner_acquire", request, state)
            self.attach_in(db, worker, claim, record)
            return self.receipt(worker, record)

    def begin(self, token, worker_id, request, *, one_shot=False):
        request_shape(request, BEGIN); resource(request["runnerKey"], "runner"); identifier(request["reservationId"])
        # A receipt replay is useful for the internal coordinator, but must never
        # become a second send permission in the designated-brain handoff.
        if not one_shot:
            prior = self.replay(token, worker_id, "runner_launch", request)
            if prior: return prior
        # Local one-shot marker first. There is no native call; any retained
        # marker nevertheless forbids retry because an adapter may have sent.
        for phase in ("local", "shared"):
            with self.bridge.locked(token, effects=True) as (db, meta):
                worker, intent = self.bridge.intent_in(db, worker_id)
                with self.store.tx() as kernel:
                    claim, record, state = self.state_in(kernel, intent)
                    require(request["expectedHash"] == digest(record), "Runner journal changed before launch")
                    if one_shot and phase == "local":
                        require(self.replay_in(kernel, intent, "runner_launch", request) is None,
                                "Runner launch already recorded; reconcile, never resend")
                    runner = self.current_runner(state, request)
                    require(runner["status"] == "reserved", "Runner launch already attempted; reconcile, never resend")
                    if phase == "local":
                        self.no_unmatched_intent(worker, state); self.attached(db, worker, claim, record)
                    else:
                        require(digest(worker) == pending_worker_hash and worker.get("runnerLaunchIntentHash") == marker and worker["status"] == "accepting" and
                                worker["dispatchAdmission"]["stage"] == "runner_launch_pending", "Local runner launch marker changed")
                        require(runs.document(db, marker, "runner_launch_intent") == local, "Local runner launch instruction changed")
                        # Apart from the marker/status, ownership cannot change in the gap.
                        require(worker["dispatchAdmission"]["claimHash"] == digest(claim) and
                                meta["runner"] == retained_owner, "Runner ownership changed before launch")
                    self.work_checks(db, meta, kernel, worker, intent, claim, state, request, launching=True)
                    self.idle_proof(kernel, claim, record, state, request["observation"])
                    if phase == "shared":
                        runner.update(status="launch_intent", intentHash=marker, launchAt=time.time())
                        state["creation"]["activity"] = "unknown"
                        record = self.append_in(kernel, claim, intent, "runner_launch", request, state)
                if phase == "local":
                    local = {"kind": "runner_launch_intent", "workerId": worker_id, "intentHash": digest(intent), "request": request}
                    marker = runs.retain(db, "runner_launch_intent", local)
                    retained_owner = meta["runner"]
                    worker.update(runnerLaunchIntentHash=marker, status="accepting", updatedAt=time.time())
                    worker["dispatchAdmission"]["stage"] = "runner_launch_pending"
                    pending_worker_hash = digest(worker)
                    self.ledger.put(db, "workers", worker_id, worker)
                    self.ledger.event(db, "runner_launch_intent", {"workerId": worker_id, "intentHash": marker})
                else:
                    self.attach_in(db, worker, claim, record)
                    return self.receipt(worker, record)

    def observe_process(self, token, worker_id, request):
        request_shape(request, OBSERVE); resource(request["runnerKey"], "runner"); identifier(request["reservationId"])
        identifier(request["hostId"]); identifier(request["threadId"]); sha(request["evidenceHash"])
        require(request["outcome"] in ("uncertain", "running", "exited"), "Unknown runner process outcome")
        if request["processIdentityHash"] is not None: sha(request["processIdentityHash"])
        require(request["outcome"] == "uncertain" or request["processIdentityHash"] is not None, "Exact process identity required")
        if request["outcome"] == "exited": integer(request["exitCode"], -255, 255)
        else: require(request["exitCode"] is None, "Only exited processes have exit codes")
        require(request["processTreeExited"] is (request["outcome"] == "exited"), "Explicit process-tree exit status required")
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                claim, record, state = self.state_in(kernel, intent)
                prior = self.replay_in(kernel, intent, "runner_process", request)
                if not prior:
                    require(request["expectedHash"] == digest(record), "Runner journal changed before observation")
                    self.no_unmatched_intent(worker, state); self.attached(db, worker, claim, record)
                    runner = self.current_runner(state, request)
                    require(runner["status"] in ("launch_intent", "uncertain", "running"), "Exact unfinished runner launch required")
                    require(claim["native"] == {k: request[k] for k in ("hostId", "threadId")}, "Process evidence belongs to another task")
                    require(not runner.get("processIdentityHash") or runner["processIdentityHash"] == request["processIdentityHash"], "Retained process identity cannot change or disappear")
                    self.fresh(kernel, request["observedAt"], claim, state)
                    require(request["observedAt"] > record["at"], "Process evidence predates journal")
                    runner.update({k: request[k] for k in ("processIdentityHash", "exitCode", "processTreeExited", "observedAt", "evidenceHash")})
                    runner["status"] = request["outcome"]
                    record = self.append_in(kernel, claim, intent, "runner_process", request, state)
            self.attach_in(db, worker, claim, record)
            return self.receipt(worker, record, prior)

    def release(self, token, worker_id, request):
        request_shape(request, RELEASE); resource(request["runnerKey"], "runner"); identifier(request["reservationId"])
        sha(request["evidenceHash"]); sha(request["nativeEvidenceHash"])
        require(request["outcome"] in ("unlaunched", "exited"), "Explicit runner release outcome required")
        for field in ("nativeIdle", "runnerIdle", "cleanupObserved", "processesExited", "complete"):
            require(request[field] is True, "Complete process exit, native idle and cleanup observations required")
        prior = self.replay(token, worker_id, "runner_release", request)
        if prior: return prior
        with self.bridge.locked(token, ownership_change=True) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                require_open(self.store.root, self.store.get(kernel, "meta", 1))
                claim, record, state = self.state_in(kernel, intent)
                require(request["expectedHash"] == digest(record), "Runner journal changed before release")
                self.no_unmatched_intent(worker, state); self.attached(db, worker, claim, record)
                runner = self.current_runner(state, request)
                require(runner["status"] == ("reserved" if request["outcome"] == "unlaunched" else "exited"),
                        "Runner needs reconciled exit before release; an unknown send is not unlaunched")
                self.fresh(kernel, request["observedAt"], claim, state)
                require(request["observedAt"] > record["at"], "Cleanup evidence predates journal")
                kernel.execute("DELETE FROM resources WHERE id=? AND claim=?", (runner["key"], worker_id))
                runner.update(status="released", observedAt=request["observedAt"], releaseEvidenceHash=request["evidenceHash"], releaseOutcome=request["outcome"])
                state["creation"].update(activity="idle", observedAt=request["observedAt"], evidenceHash=request["nativeEvidenceHash"])
                record = self.append_in(kernel, claim, intent, "runner_release", request, state)
            self.attach_in(db, worker, claim, record)
            return self.receipt(worker, record)
