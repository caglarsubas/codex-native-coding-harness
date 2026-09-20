"""Internal authority/admission journal. No native adapter or activation route.

Registry -> workspace -> admission lock order. Admission commits before the
workspace receipt; durable intent makes this gap recoverable, not atomic.
"""
import contextlib
import json
import time

from . import enrollment, run_authority as runs
from .admission import HELD, exact, integer, resource, sha
from .core import ACTIVE, AXES, canonical, digest, eligibility_issues, require
from .decisions import authorize_brain
from .workspaces import identity, inspect_ledger

LIMITS = ("maxParallelTasks", "maxTasks", "tokenBudget", "checkpointReserveTokens")


def phase_allocation(grant, repositories, runners=()):
    """Pure binding helper, NOT allocation initialization or identity attestation."""
    identity(grant["workspaceId"])
    require(isinstance(repositories, dict) and
            set(repositories) == {b["repository"] for b in grant["repositoryBindings"]},
            "Exact phase repository resource mapping required")
    clean = {}
    for repo, keys in repositories.items():
        require(isinstance(keys, list) and 1 <= len(keys) <= 4, "Canonical repository keys required")
        clean[repo] = sorted({resource(key) for key in keys})
    require(isinstance(runners, (list, tuple)) and len(runners) <= 10, "Invalid runner identities")
    runners = sorted({resource(key, "runner") for key in runners})
    limits = {k: grant["authority"][k] for k in LIMITS}
    binding = {"protocol": "dispatch-admission-v1", "workspaceId": grant["workspaceId"],
               "brainId": grant["brainId"], "phaseId": grant["phaseId"], "limits": limits,
               "repositoryBindings": grant["repositoryBindings"], "repositories": clean, "runners": runners}
    # Review/run generations can change; the same phase must never get a new
    # accounting epoch just by changing a request or authorization hash.
    aid = "phase-" + digest({"workspaceId": grant["workspaceId"], "phaseId": grant["phaseId"]})
    return {"id": aid, "spec": {"workspaceId": grant["workspaceId"], "bindingHash": digest(binding),
                                "limits": limits, "repositories": clean, "runners": runners}}


class DispatchAdmission:
    """Trusted internal seam; tests only until activation/adapter qualification.

    Construction does not seed admission or change a dispatch flag. All returned
    receipts are non-executable. Only the designated brain controller can write.
    """

    def __init__(self, registry, workspace_id, store):
        self.registry, self.store = registry, store
        self.workspace_id = identity(workspace_id)
        require(store.root == registry.root, "Admission store belongs to another platform")
        self.registry_id = enrollment.registry_identity(registry)
        self.ledger = registry.ledger(workspace_id)
        self.ledger_id = inspect_ledger(self.ledger.root)["databaseIdentity"]

    @contextlib.contextmanager
    def locked(self, token, *, effects=False, ownership_change=False):
        require(enrollment.registry_identity(self.registry) == self.registry_id, "Registry identity changed")
        with self.registry.tx() as registry_db:
            row = registry_db.execute("SELECT root,brain,data FROM workspaces WHERE id=?", (self.workspace_id,)).fetchone()
            require(row is not None and row["root"] == str(self.ledger.root), "Workspace registration changed")
            inspected = inspect_ledger(self.ledger.root)
            require(inspected["databaseIdentity"] == self.ledger_id == json.loads(row["data"])["databaseIdentity"]
                    and inspected["brainId"] == row["brain"], "Workspace database or brain identity changed")
            if effects or ownership_change:
                enrollment.require_registration_open(registry_db)
                require(not inspected["admissionFenced"], "Workspace maintenance fence remains in force")
            with self.ledger.tx() as db:
                meta = authorize_brain(self.ledger, db, token)
                require(meta["brainId"] == row["brain"], "Workspace brain identity changed")
                if effects or ownership_change:
                    require("admissionBinding" not in meta and not enrollment.fence_exists(self.ledger.root),
                            "Workspace maintenance fence remains in force")
                if effects:
                    require(meta["paused"] is False, "Dispatch paused; run intent is not activation")
                yield db, meta

    def allocation_in(self, db, kernel, run_hash):
        grant = runs.require_current(self.ledger, db, run_hash)
        aid = "phase-" + digest({"workspaceId": self.workspace_id, "phaseId": grant["phaseId"]})
        allocation = self.store.get(kernel, "allocations", aid)
        spec = allocation["spec"]
        expected = phase_allocation(grant, spec["repositories"], spec["runners"])
        require(allocation["id"] == expected["id"] and spec == expected["spec"] and
                allocation["fingerprint"] == digest(spec), "Phase allocation binding changed; explicit migration required")
        from .phase_usage import enforce_context
        enforce_context(self, db, kernel, allocation)
        self.store.check_budget(kernel, allocation)
        return allocation

    def task_in(self, db, meta, run_hash, queue_id, approval_hash, worker_id, *, runner_owner=None):
        approval = runs.document(db, approval_hash, "run_task_approval")
        contract = runs.document(db, approval["contractHash"], "task_contract")
        for operation in contract["spec"]["operations"]:
            runs.check_task_in(self.ledger, db, run_hash=run_hash, queue_id=queue_id,
                               approval_hash=approval_hash, operation=operation)
        q = self.ledger.get(db, "queue", queue_id)
        repo = self.ledger.get(db, "repos", q["repository"])
        from .task_contracts import document_in
        seed = document_in(db, q["seedHash"], "seed", 512000)
        require(seed is not None, "Exact seed required")
        workers = self.ledger.all(db, "workers")
        issues = [i for i in eligibility_issues(q, repo, seed, workers)
                  if i["code"] not in ("phase_contract_fence", "approval", "approval_binding")]
        require(not issues, issues[0]["detail"] if issues else "")
        self.local_capacity_in(db, meta, q["repository"], worker_id, runner_owner=runner_owner)
        return q, contract

    def local_capacity_in(self, db, meta, repository, worker_id, *, runner_owner=None):
        others = [w for w in self.ledger.all(db, "workers") if w["status"] in ACTIVE and w["id"] != worker_id]
        limit = min(meta["concurrency"], meta["maximumConcurrency"], 1 if not meta["pilotPassed"] else 16)
        require(len(others) < limit, "Local worker capacity exhausted")
        require(not any(w["repository"] == repository for w in others), "Local repository already owned")
        require(meta["runner"] is None or runner_owner == worker_id == meta["runner"].get("workerId"),
                "Local runner ownership must be reconciled first")

    def intent_in(self, db, worker_id):
        worker = self.ledger.get(db, "workers", worker_id)
        pointer = worker.get("dispatchAdmission")
        require(isinstance(pointer, dict), "Worker has no dispatch admission intent")
        intent = runs.document(db, pointer.get("intentHash"), "dispatch_intent")
        require(intent["workerId"] == worker_id and intent["workspaceId"] == self.workspace_id and
                intent["registryIdentity"] == self.registry_id and intent["ledgerIdentity"] == self.ledger_id and
                intent["admissionIdentity"] == list(self.store.database_identity) and
                intent["queueId"] == worker["queueId"] and intent["seedHash"] == worker["seedHash"] and
                intent["repository"] == worker["repository"], "Dispatch intent identity changed; explicit recovery required")
        return worker, intent

    def claim_in(self, kernel, intent):
        claim = self.owned_claim_in(kernel, intent)
        require(claim["status"] in ("reserved", "starting") and not claim.get("nativeLifecycleHash"),
                "Shared claim needs native reconciliation, not admission retry")
        require(claim["native"] is None, "Native ownership requires the result coordinator")
        return claim

    def owned_claim_in(self, kernel, intent):
        """Exact ownership binding shared by creation and native lifecycle code."""
        claim = self.bound_claim_in(kernel, intent)
        require(claim["status"] in HELD, "Shared claim no longer retains ownership")
        keys = list(intent["resourceKeys"])
        runner = claim.get("runnerBinding")
        if runner and runner["status"] != "released": keys.append(resource(runner["key"], "runner"))
        owned = sorted(r[0] for r in kernel.execute("SELECT id FROM resources WHERE claim=?", (claim["id"],)))
        require(owned == sorted(keys), "Shared resource ownership changed; explicit recovery required")
        return claim

    def bound_claim_in(self, kernel, intent):
        """Immutable claim binding, also usable for terminal receipt recovery."""
        claim = self.store.get(kernel, "claims", intent["workerId"])
        extra = claim.get("continuationReservedTokens", 0)
        integer(extra)
        spec = {"allocationId": intent["allocationId"], "repositories": [intent["repository"]],
                "estimates": intent["estimates"], "role": "worker", "bindingHash": digest(intent)}
        require(claim["id"] == intent["workerId"] and claim["fingerprint"] == digest(spec) and
                all(claim[k] == v for k, v in spec.items()) and
                claim["estimatedTokens"] == sum(intent["estimates"].values()) + extra, "Shared claim binding changed")
        return claim

    def attach_in(self, db, worker, claim):
        # Call only AFTER the admission transaction has committed. A failure here
        # leaves the prior local intent, allowing receipt-only recovery.
        value = {"claimHash": digest(claim), "stage": "reserved" if claim["status"] == "reserved" else "creation_intent"}
        pointer = worker["dispatchAdmission"]
        if pointer["stage"] == "creation_pending" and claim["status"] == "reserved":
            return self.result(worker)  # A local boundary also prohibits retries.
        if all(pointer.get(k) == v for k, v in value.items()):
            return self.result(worker)
        require(pointer["stage"] != "creation_intent" or value["stage"] == "creation_intent", "Creation intent cannot move backwards")
        worker["dispatchAdmission"] = {**pointer, **value}
        worker.update(status=claim["status"], updatedAt=time.time())
        self.ledger.put(db, "workers", worker["id"], worker)
        runs.retain(db, "dispatch_claim_receipt", claim)
        self.ledger.event(db, "dispatch_admission_attached", {"workerId": worker["id"], **value})
        return self.result(worker)

    @staticmethod
    def result(worker):
        return {"workerId": worker["id"], **worker["dispatchAdmission"],
                "executionAuthorized": False, "nativeAdapterAvailable": False, "nativeCallMade": False}

    def reserve(self, token, *, run_hash, queue_id, approval_hash, estimates):
        sha(run_hash); sha(approval_hash)
        exact(estimates, {"workTokens", "reviewTokens", "handoffTokens"})
        for amount in estimates.values(): integer(amount, 1, 1_000_000_000)
        worker_id = "dispatch-" + digest({"workspaceId": self.workspace_id, "queueId": queue_id})
        # Stage 1: local intent commits before any shared reservation.
        with self.locked(token, effects=True) as (db, meta):
            q, contract = self.task_in(db, meta, run_hash, queue_id, approval_hash, worker_id)
            require(estimates["workTokens"] >= contract["spec"]["estimatedTokens"], "Work estimate undercuts the task declaration")
            from .model_policy import initial_in
            selection = initial_in(self.ledger, db, runs.require_current(self.ledger, db, run_hash), q, contract)
            require(selection is None or estimates["workTokens"] >= selection["minimumWorkTokens"],
                    "Work estimate undercuts the selected model profile")
            with self.store.tx() as kernel:
                allocation = self.allocation_in(db, kernel, run_hash)
            intent = {"kind": "dispatch_intent", "schemaVersion": 1, "workspaceId": self.workspace_id,
                      "registryIdentity": self.registry_id, "ledgerIdentity": self.ledger_id,
                      "admissionIdentity": list(self.store.database_identity), "workerId": worker_id,
                      "runHash": run_hash, "approvalHash": approval_hash, "contractHash": q["taskContract"]["hash"],
                      "queueId": queue_id, "seedHash": q["seedHash"], "repository": q["repository"],
                      "allocationId": allocation["id"], "allocationFingerprint": allocation["fingerprint"],
                      "resourceKeys": allocation["spec"]["repositories"][q["repository"]], "estimates": estimates}
            existing = db.execute("SELECT id FROM workers WHERE queue_id=?", (queue_id,)).fetchone()
            if existing:
                worker, prior = self.intent_in(db, existing[0])
                require(prior == intent, "Task already owned by a different dispatch intent")
                require(worker["dispatchAdmission"]["stage"] in ("intent", "reserved"),
                        "Creation intent already retained; recover receipts only")
            else:
                pointer = {"intentHash": runs.retain(db, "dispatch_intent", intent), "stage": "intent", "claimHash": None}
                now = time.time()
                worker = {"id": worker_id, "queueId": queue_id, "repository": q["repository"], "packetId": q["packetId"],
                          "seedHash": q["seedHash"], "status": "reserved", "createdAt": now, "updatedAt": now,
                          "threadId": None, "clientThreadId": None, "hostId": "local", "noProgressCycles": 0,
                          "preserved": False, "archived": False, "dispatchAdmission": pointer,
                          "evidence": {axis: {"status": "unverified", "reference": None} for axis in AXES}}
                db.execute("INSERT INTO workers VALUES(?,?,?)", (worker_id, queue_id, canonical(worker)))
                q.update(status="dispatched", reason="Admission intent retained; no native task created")
                self.ledger.put(db, "queue", queue_id, q)
                self.ledger.event(db, "dispatch_admission_intent", {"workerId": worker_id, **pointer})
        # Stage 2: revalidate after the gap, then commit shared -> local.
        with self.locked(token, effects=True) as (db, meta):
            worker, intent = self.intent_in(db, worker_id)
            require(worker["dispatchAdmission"]["stage"] in ("intent", "reserved"),
                    "Creation intent already retained; recover receipts only")
            self.task_in(db, meta, run_hash, queue_id, approval_hash, worker_id)
            with self.store.tx() as kernel:
                allocation = self.allocation_in(db, kernel, run_hash)
                require(allocation["fingerprint"] == intent["allocationFingerprint"], "Allocation changed since intent")
                if worker["dispatchAdmission"]["stage"] == "reserved":
                    # A receipt proves a claim existed. Its disappearance is not
                    # permission to reset its attempt count or token reservation.
                    retained = self.claim_in(kernel, intent)
                    require(worker["dispatchAdmission"]["claimHash"] == digest(retained), "Claim changed; recover receipts only")
                else:
                    self.store.reserve_in(kernel, worker_id, allocation["id"], repositories=[intent["repository"]],
                                          estimates=estimates, binding_hash=digest(intent))
                claim = self.claim_in(kernel, intent)
                require(claim["status"] == "reserved", "Creation intent already retained; recover receipts only")
            return self.attach_in(db, worker, claim)

    def begin_creation(self, token, worker_id, *, expected_revision=None):
        """One-shot journal boundary only. No native call or reusable permit."""
        if expected_revision is not None: integer(expected_revision)
        with self.locked(token, effects=True) as (db, meta):
            require(expected_revision is None or meta["revision"] == expected_revision,
                    "Workspace changed before the creation boundary")
            worker, intent = self.intent_in(db, worker_id)
            require(worker["dispatchAdmission"]["stage"] == "reserved" and worker["status"] == "reserved",
                    "Reservation receipt required; never retry creation intent")
            self.task_in(db, meta, intent["runHash"], intent["queueId"], intent["approvalHash"], worker_id)
            with self.store.tx() as kernel:
                allocation = self.allocation_in(db, kernel, intent["runHash"])
                require(allocation["fingerprint"] == intent["allocationFingerprint"], "Allocation changed since intent")
                claim = self.claim_in(kernel, intent)
                require(worker["dispatchAdmission"]["claimHash"] == digest(claim), "Claim changed; recover before proceeding")
                held = [c for c in self.store.rows(kernel, "claims") if c["status"] in HELD]
                require(len(held) <= self.store.get(kernel, "meta", 1)["policy"]["maxParallelTasks"] and
                        sum(c["allocationId"] == allocation["id"] for c in held) <= allocation["spec"]["limits"]["maxParallelTasks"],
                        "Shared task capacity changed")
            # Commit a local in-flight owner BEFORE advancing the shared boundary.
            # Pause must not mistake an attachment failure for an unstarted worker.
            worker["dispatchAdmission"]["stage"] = "creation_pending"
            worker.update(status="starting", updatedAt=time.time())
            self.ledger.put(db, "workers", worker_id, worker)
            self.ledger.event(db, "dispatch_creation_intent", {"workerId": worker_id})
        with self.locked(token, effects=True) as (db, meta):
            worker, intent = self.intent_in(db, worker_id)
            require(worker["dispatchAdmission"]["stage"] == "creation_pending" and worker["status"] == "starting",
                    "Creation intent changed; recover receipts only")
            self.task_in(db, meta, intent["runHash"], intent["queueId"], intent["approvalHash"], worker_id)
            with self.store.tx() as kernel:
                allocation = self.allocation_in(db, kernel, intent["runHash"])
                require(allocation["fingerprint"] == intent["allocationFingerprint"], "Allocation changed since intent")
                claim = self.claim_in(kernel, intent)
                require(worker["dispatchAdmission"]["claimHash"] == digest(claim), "Claim changed; recover receipts only")
                claim = self.store.begin_in(kernel, worker_id)
            return self.attach_in(db, worker, claim)

    def recover(self, token, worker_id):
        """Receipt-only recovery, including after pause/fencing/expiry.

        No authority check that could obstruct retaining an already-owned claim;
        no reservation, creation, ownership release or native observation.
        """
        with self.locked(token) as (db, _):
            worker, intent = self.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                row = kernel.execute("SELECT 1 FROM claims WHERE id=?", (worker_id,)).fetchone()
                if not row:
                    require(worker["dispatchAdmission"]["stage"] == "intent", "Retained shared claim is missing; explicit recovery required")
                    return self.result(worker)
                claim = self.claim_in(kernel, intent)
            return self.attach_in(db, worker, claim)
