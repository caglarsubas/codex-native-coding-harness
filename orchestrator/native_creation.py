"""One-use native task instructions for the designated brain, not a transport.

The brain calls the app tools. This helper never starts a model, sends a message,
or creates a task. Native evidence is a trusted caller assertion, not attestation.
"""
import time

from . import run_authority as runs
from .admission import HELD, exact, identifier, integer, sha, timestamp
from .core import canonical, digest, require, worker_prompt
from .native_lifecycle import NativeLifecycle
from .source_observation import inspect_base, oid

KIND = "native_creation_handoff"
CHECK = "native_creation_check"
MAX_AGE = 60


def check_slot(intent):
    return digest({"kind": "native_creation_check_slot", "intentHash": digest(intent)})


def fresh(at):
    timestamp(at)
    require(0 <= time.time() - at <= MAX_AGE, "Native creation evidence expired; reconcile without retrying creation")


def project_shape(observation):
    exact(observation, {"observedAt", "evidenceHash", "project"})
    timestamp(observation["observedAt"]); sha(observation["evidenceHash"])
    exact(observation["project"], {"projectId", "projectKind", "hostId", "path", "isGitRepository"})
    require(len(canonical(observation).encode()) <= 4096, "Selected project observation exceeds its bound")


def arguments(worker, seed, contract, project):
    operations = contract["spec"]["operations"]
    require("edit" in operations and set(operations) <= {"edit", "test", "commit", "open_pr"},
            "First native handoff supports edit/test/commit/open_pr scope only; no merge or archive")
    prompt = ("Implement the exact phase-authorized packet at the base below in this task.\n"
              "Seed SHA-256: " + digest(seed) + "\n"
              "Mission SHA-256: " + contract["spec"]["missionHash"] + "\n"
              "Task contract SHA-256: " + digest(contract) + "\n"
              "Permitted operations: " + ", ".join(operations) + ". No other operations are authorized.\n"
              "Test/acceptance commands require a separate brain-granted runner reservation; stop before them. "
              "Do not merge, archive, create other tasks or expand scope.\n" + worker_prompt(worker["id"], seed))
    result = {"title": f"{worker['packetId']} · {worker['id'][-8:]}", "prompt": prompt,
              "target": {"type": "project", "projectId": project["projectId"],
                         "environment": {"type": "worktree", "startingState": {
                             "type": "branch", "branchName": oid(seed["baseSHA"])}}}}
    require(len(canonical(result).encode()) <= 20000, "Native inheritance exceeds its 20 KiB handoff bound")
    return result  # Model, effort and speed are deliberately omitted.


class NativeCreation:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.lifecycle = NativeLifecycle(bridge)

    def check_in(self, db, worker, intent):
        """A missing pointer cannot hide an already consumed send check."""
        key = worker.get("nativeHandoffCheckHash")
        slot = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=512 THEN data END "
                          "FROM snapshots WHERE id=?", (check_slot(intent),)).fetchone()
        if not key and not slot: return None
        require(key and slot and slot[0] == "native_creation_check_slot" and slot[1] == canonical({"checkHash": key}),
                "Native send check receipt changed or missing; never resend")
        doc = runs.document(db, key, CHECK)
        require(doc["workerId"] == worker["id"] and doc["intentHash"] == digest(intent) and
                doc["handoffHash"] == worker.get("nativeHandoffHash"), "Native send check binding changed")
        return doc

    def context_in(self, db, meta, kernel, worker_id, observation, stage):
        worker, intent = self.bridge.intent_in(db, worker_id)
        require(worker["dispatchAdmission"]["stage"] == stage and
                worker["status"] == ("reserved" if stage == "reserved" else "starting"),
                "Creation boundary already crossed or changed; never reissue a native handoff")
        require(self.check_in(db, worker, intent) is None, "Native send check already consumed; reconcile, never resend")
        _, contract = self.bridge.task_in(db, meta, intent["runHash"], intent["queueId"], intent["approvalHash"], worker_id)
        require(contract["repositoryBinding"]["policyProfile"] == "standard",
                "Native creation requires standard policy; Harness needs its trusted adapter")
        runs.standard_handoff_scope(db, intent)
        repo = self.ledger.get(db, "repos", intent["repository"])
        seed = runs.document(db, intent["seedHash"], "seed")
        require(repo["policyProfile"] == seed["policyProfile"] == "standard", "Standard policy binding required")
        project = observation["project"]
        require(project["projectKind"] == "local" and project["hostId"] == "local" and
                project["isGitRepository"] is True and project["projectId"] == repo["projectId"] and
                project["path"] == repo["path"], "Fresh saved local Git project must exactly match the registered repository")
        fresh(observation["observedAt"])
        allocation = self.bridge.allocation_in(db, kernel, intent["runHash"])
        require(allocation["fingerprint"] == intent["allocationFingerprint"], "Allocation changed since intent")
        claim = self.bridge.claim_in(kernel, intent)
        require(claim["status"] == ("reserved" if stage == "reserved" else "starting") and
                worker["dispatchAdmission"]["claimHash"] == digest(claim), "Exact attached shared claim required")
        held = [c for c in self.store.rows(kernel, "claims") if c["status"] in HELD]
        policy = self.store.get(kernel, "meta", 1)["policy"]
        self.store.fresh(observation["observedAt"], policy)
        require(len(held) <= policy["maxParallelTasks"] and
                sum(c["allocationId"] == allocation["id"] for c in held) <= allocation["spec"]["limits"]["maxParallelTasks"],
                "Shared task capacity changed")
        keys = [k for k in intent["resourceKeys"] if k.startswith("repo-local:")]
        require(len(keys) == 1, "One pinned local common-directory resource is required")
        args = arguments(worker, seed, contract, project)
        from .model_policy import initial_arguments
        args.update(initial_arguments(self.ledger, db, intent))
        require(len(canonical(args).encode()) <= 20000, "Native inheritance exceeds its 20 KiB handoff bound")
        return worker, intent, {"path": repo["path"], "key": keys[0], "base": seed["baseSHA"]}, args

    def begin(self, token, worker_id, request):
        exact(request, {"id", "expectedRevision", "projectObservation"})
        identifier(request["id"]); integer(request["expectedRevision"])
        project_shape(request["projectObservation"])
        with self.bridge.locked(token, effects=True) as (db, meta):
            require(meta["revision"] == request["expectedRevision"], "Workspace changed before native handoff")
            with self.store.tx() as kernel:
                worker, intent, probe, args = self.context_in(db, meta, kernel, worker_id, request["projectObservation"], "reserved")
            require(not worker.get("nativeHandoffHash"), "Native handoff already retained; never reissue")
        base = inspect_base(**probe)  # No repository reads before authority and selected-project checks.
        fresh(request["projectObservation"]["observedAt"])
        self.bridge.begin_creation(token, worker_id, expected_revision=request["expectedRevision"])
        # A crash/Pause after either boundary is in-flight ownership, not a retry.
        with self.bridge.locked(token, effects=True) as (db, meta):
            with self.store.tx() as kernel:
                worker, current, current_probe, current_args = self.context_in(
                    db, meta, kernel, worker_id, request["projectObservation"], "creation_intent")
            require(current == intent and current_probe == probe and current_args == args, "Creation inputs changed; reconcile")
            require(not worker.get("nativeHandoffHash"), "Native handoff already retained; never reissue")
            fresh(base["observedAt"])
            doc = {"kind": KIND, "schemaVersion": 1, "workerId": worker_id, "intentHash": digest(intent),
                   "request": request, "baseObservation": base, "argumentsHash": digest(args), "at": time.time()}
            key = runs.retain(db, KIND, doc)
            worker["nativeHandoffHash"] = key
            worker["updatedAt"] = doc["at"]
            self.ledger.put(db, "workers", worker_id, worker)
            self.ledger.event(db, "native_creation_handoff", {"workerId": worker_id, "handoffHash": key})
        return {"workerId": worker_id, "handoffHash": key, "tool": "create_thread", "arguments": args,
                "mustCheckBeforeSend": True, "oneShot": True, "nativeCallMade": False}

    def handoff_in(self, db, worker_id, key):
        sha(key)
        worker, intent = self.bridge.intent_in(db, worker_id)
        doc = runs.document(db, key, KIND)
        require(worker.get("nativeHandoffHash") == key and doc["workerId"] == worker_id and
                doc["intentHash"] == digest(intent), "Native handoff belongs to a different worker or intent")
        return worker, intent, doc

    def check(self, token, worker_id, key):
        """Consume the send check once, immediately before the brain's tool call."""
        with self.bridge.locked(token, effects=True) as (db, meta):
            _, _, doc = self.handoff_in(db, worker_id, key); fresh(doc["at"])
            with self.store.tx() as kernel:
                _, _, probe, args = self.context_in(db, meta, kernel, worker_id, doc["request"]["projectObservation"], "creation_intent")
            require(digest(args) == doc["argumentsHash"], "Native arguments changed")
            revision = meta["revision"]
        base = inspect_base(**probe)
        require(all(base[k] == doc["baseObservation"][k] for k in ("baseSHA", "baseTree", "resourceKey", "layoutHash")),
                "Local base binding changed; reconcile without sending")
        with self.bridge.locked(token, effects=True) as (db, meta):
            worker, intent, current = self.handoff_in(db, worker_id, key)
            require(meta["revision"] == revision and current == doc, "Workspace changed before native send check")
            fresh(doc["at"]); fresh(base["observedAt"])
            with self.store.tx() as kernel:
                self.context_in(db, meta, kernel, worker_id, doc["request"]["projectObservation"], "creation_intent")
            check = {"kind": CHECK, "workerId": worker_id, "intentHash": digest(intent), "handoffHash": key, "at": time.time()}
            worker["nativeHandoffCheckHash"] = runs.retain(db, CHECK, check)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (check_slot(intent), "native_creation_check_slot",
                       canonical({"checkHash": digest(check)})))
            worker["updatedAt"] = check["at"]
            self.ledger.put(db, "workers", worker_id, worker)
            self.ledger.event(db, "native_creation_send_check", {"workerId": worker_id, "checkHash": digest(check)})
        return {"workerId": worker_id, "handoffHash": key, "checkHash": digest(check),
                "sendNow": True, "reusablePermit": False, "nativeCallMade": False}

    def record(self, token, worker_id, request):
        exact(request, {"id", "handoffHash", "expectedHash", "observedAt", "outcome", "hostId", "threadId", "clientThreadId", "evidenceHash"})
        identifier(request["id"]); sha(request["handoffHash"]); sha(request["evidenceHash"]); timestamp(request["observedAt"])
        require(request["hostId"] == "local", "Native result host differs from the selected local project")
        with self.bridge.locked(token) as (db, _):
            worker, intent, doc = self.handoff_in(db, worker_id, request["handoffHash"])
            check = self.check_in(db, worker, intent)
            require(check and check["handoffHash"] == request["handoffHash"] and check["workerId"] == worker_id and
                    check["intentHash"] == digest(intent) and request["observedAt"] > check["at"] >= doc["at"],
                    "Exact consumed send check and later result observation required")
        # Late facts remain recordable after Pause. NativeLifecycle preserves IDs,
        # shared-first crash recovery, result replay and unknown activity semantics.
        observation = {k: request[k] for k in ("id", "expectedHash", "outcome", "hostId", "threadId", "clientThreadId", "observedAt")}
        observation.update(id="creation-" + digest({"id": request["id"], "handoffHash": request["handoffHash"]}),
                           activity="unknown", evidenceHash=request["evidenceHash"])
        return self.lifecycle.observe(token, worker_id, observation)

    def state(self, token, worker_id):
        """Read-only recovery guidance; no arguments, clock refresh or send retry."""
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            key = worker.get("nativeHandoffHash")
            if key: self.handoff_in(db, worker_id, key)
            self.check_in(db, worker, intent)
            with self.store.tx() as kernel:
                claim = self.bridge.bound_claim_in(kernel, intent)
            return {"workerId": worker_id, "handoffHash": key, "checkHash": worker.get("nativeHandoffCheckHash"),
                    "stage": worker["dispatchAdmission"]["stage"], "claimStatus": claim["status"],
                    "nativeLifecycleHash": claim.get("nativeLifecycleHash"), "attachedHash": worker.get("nativeLifecycleHash"),
                    "native": claim.get("native"), "clientNative": claim.get("clientNative"),
                    "creationBoundaryCrossed": worker["dispatchAdmission"]["stage"] not in ("intent", "reserved"),
                    "creationRetryAllowed": False, "nativeCallMade": False, "executionAuthorized": False}

    def recover(self, token, worker_id):
        """Attach the current native receipt only; never issue or repeat a send."""
        return self.lifecycle.recover(token, worker_id)
