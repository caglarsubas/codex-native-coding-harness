"""Bounded brain decisions and admission composition; no scheduler or native calls."""
import copy
import contextlib
import json
import sqlite3
import time

from . import enrollment, missions, run_authority as runs
from .admission import exact, identifier, integer, sha
from .core import Refusal, canonical, digest, eligibility_issues, require
from .dispatch_admission import DispatchAdmission
from .native_lifecycle import NativeLifecycle

KIND = "brain_cycle_decision"
SLOT = "brain_cycle_request"
MAX_ROWS = 500


def slot(workspace, identity):
    return digest({"kind": SLOT, "workspaceId": workspace, "id": identity})


class BrainCoordinator:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.lifecycle = NativeLifecycle(bridge)

    def prior_in(self, db, identity):
        row = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=512 THEN data END "
                         "FROM snapshots WHERE id=?", (slot(self.bridge.workspace_id, identity),)).fetchone()
        if row is None: return None
        require(row[0] == SLOT and row[1] is not None, "Brain decision receipt changed")
        pointer = json.loads(row[1]); exact(pointer, {"decisionHash"})
        return self.document_in(db, pointer["decisionHash"])

    def document_in(self, db, key):
        doc = runs.document(db, key, KIND)
        require(doc["workspaceId"] == self.bridge.workspace_id and
                doc["brainId"] == self.ledger.get(db, "meta", 1)["brainId"], "Brain decision identity changed")
        return doc

    def latest_in(self, db, meta):
        key = meta.get("brainCycleHash")
        count = db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (KIND,)).fetchone()[0]
        require(key or count == 0, "Brain decision pointer missing; explicit recovery required")
        if not key: return None
        doc = self.document_in(db, key)
        require(doc["version"] == count and self.prior_in(db, doc["request"]["id"]) == doc,
                "Brain decision history or receipt changed")
        if doc["previousHash"]:
            old = self.document_in(db, doc["previousHash"])
            require(old["version"] + 1 == doc["version"], "Brain decision version chain changed")
        return doc

    def bounded_in(self, db, tables):
        for table in tables:  # Table names are fixed by the caller, never requests.
            require(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] <= MAX_ROWS,
                    "Lifecycle inventory exceeds its bound; explicit maintenance required")
            if table != "resources":
                require(db.execute(f"SELECT coalesce(sum(length(CAST(data AS BLOB))),0) FROM {table}").fetchone()[0] <= 2_000_000,
                        "Lifecycle inventory exceeds its byte bound; explicit maintenance required")

    def worker_in(self, db, meta, kernel, worker, effects_ready):
        row = {"workerId": worker["id"], "queueId": worker["queueId"], "status": worker["status"],
               "canContinue": False, "next": "inspect_existing_ownership", "reason": None}
        if not worker.get("dispatchAdmission"):
            row["reason"] = "Legacy ownership must be reconciled; never adopt implicitly"
            return row
        worker, intent = self.bridge.intent_in(db, worker["id"])
        row.update(seedHash=intent["seedHash"], runHash=intent["runHash"],
                   stage=worker["dispatchAdmission"]["stage"])
        try:
            runs.standard_handoff_scope(db, intent)
            claim = self.bridge.bound_claim_in(kernel, intent)
            if claim["status"] == "settled":
                row["next"] = "result-handoff-state"
                if worker.get("resultReviewHash"):
                    row["next"] = "inspect_retained_result"
                return row
            if row["stage"] in ("intent", "reserved"):
                row["next"] = "recover_reservation" if row["stage"] == "intent" or not effects_ready else "native-create-begin"
                return row
            claim, record, state = self.lifecycle.state_in(kernel, intent)
            row["next"] = "native-task-plan" if claim.get("native") else "native-create-state"
            row.update(native=claim.get("native"), currentHash=digest(record) if record else None)
            if not record: return row
            require(worker.get("nativeLifecycleHash") == digest(record), "Attach the current native receipt before selection")
            self.lifecycle.no_unmatched_intent(worker, state)
            runner = state.get("runner")
            if runner and runner["status"] != "released":
                row["next"] = "runner-handoff-state"
                return row
            creation, continuation = state["creation"], state["continuation"]
            if not effects_ready or creation["activity"] != "idle" or creation["outcome"] != "confirmed": return row
            if continuation and continuation["status"] != "finished": return row
            require(state["noProgress"] < 2, "Two no-progress corrections require a reviewed stop")
            self.store.fresh(creation["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
            self.bridge.task_in(db, meta, intent["runHash"], intent["queueId"], intent["approvalHash"], worker["id"])
            runs.check_task_in(self.ledger, db, run_hash=intent["runHash"], queue_id=intent["queueId"],
                               approval_hash=intent["approvalHash"], operation="edit")
            require(creation["hostId"] == "local", "Correction needs the confirmed local task")
            from .model_policy import require_observed
            require_observed(self.ledger, db, worker, intent, state)
            row.update(canContinue=True, next="correction-handoff-prepare")
        except Refusal as error:
            row["reason"] = str(error)
        return row

    def context_in(self, db, meta, kernel):
        self.bounded_in(db, ("queue", "workers"))
        self.bounded_in(kernel, ("claims", "allocations", "resources"))
        latest = self.latest_in(db, meta)
        workers = self.ledger.all(db, "workers")
        state = runs.current_in(self.ledger, db)
        blockers, grant, allocation = [], None, None
        if meta["paused"]: blockers.append("Worker dispatch is paused")
        if "admissionBinding" in meta or enrollment.fence_exists(self.ledger.root):
            blockers.append("Workspace maintenance fence remains in force")
        # The registry write lock is held by bridge.locked; this connection only
        # observes committed enrollment state, without acquiring another writer.
        with contextlib.closing(sqlite3.connect(self.bridge.registry.db.as_uri()+"?mode=ro", uri=True)) as registry_db:
            if enrollment.record_in(registry_db) is not None: blockers.append("Platform enrollment maintenance fence remains in force")
        try:
            require(state is not None, "No owner-authorized run; review and onboarding are separate")
            grant = runs.require_current(self.ledger, db, state["runHash"])
            allocation = self.bridge.allocation_in(db, kernel, state["runHash"])
        except Refusal as error: blockers.append(str(error))
        candidates = []
        for q in sorted(self.ledger.all(db, "queue"), key=lambda item: (-item.get("priority", 0), item["id"])):
            if any(w["queueId"] == q["id"] for w in workers): continue
            row = {"queueId": q["id"], "packetId": q["packetId"], "seedHash": q["seedHash"],
                   "canCreate": False, "reason": None}
            try:
                require(grant and not blockers, "Resolve the workspace run/budget blockers first")
                _, contract = runs.contract_in(self.ledger, db, q["id"], (q.get("taskContract") or {}).get("hash"))
                require(contract["repositoryBinding"]["policyProfile"] == "standard", "Harness requires its trusted lifecycle adapter")
                ops = contract["spec"]["operations"]
                require("edit" in ops and set(ops) <= {"edit", "test", "commit", "open_pr"}, "Task operations exceed the native creation adapter")
                seed = runs.document(db, q["seedHash"], "seed")
                repo = self.ledger.get(db, "repos", q["repository"])
                issues = [i for i in eligibility_issues(q, repo, seed, workers)
                          if i["code"] not in ("phase_contract_fence", "approval", "approval_binding")]
                require(not issues, issues[0]["detail"] if issues else "")
                approval = q.get("phaseApprovalHash")
                if approval:
                    for operation in ops:
                        runs.check_task_in(self.ledger, db, run_hash=state["runHash"], queue_id=q["id"],
                                           approval_hash=approval, operation=operation)
                else:
                    require(grant["authority"]["approvalMode"] == "phase_delegated", "Exact owner task approval required")
                self.bridge.local_capacity_in(db, meta, q["repository"], None)
                self.store.check_capacity(kernel, allocation, [q["repository"]])
                from .model_policy import initial_in
                selection = initial_in(self.ledger, db, grant, q, contract)
                work_tokens = max(contract["spec"]["estimatedTokens"], selection["minimumWorkTokens"] if selection else 0)
                self.store.check_budget(kernel, allocation, work_tokens + 2)
                row.update(canCreate=True, contractHash=digest(contract), approvalHash=approval,
                           estimatedWorkTokens=work_tokens,
                           needsDelegatedApproval=approval is None)
            except Refusal as error: row["reason"] = str(error)
            candidates.append(row)
        shared = {"meta": self.store.get(kernel, "meta", 1), "claims": self.store.rows(kernel, "claims"),
                  "allocations": self.store.rows(kernel, "allocations"),
                  "resources": [list(r) for r in kernel.execute("SELECT id,claim,since FROM resources ORDER BY id")]}
        require(len(canonical(shared).encode()) <= 2_000_000, "Shared lifecycle inventory exceeds its byte bound")
        out = {"workspaceId": self.bridge.workspace_id, "brainId": meta["brainId"], "revision": meta["revision"],
               "runHash": state["runHash"] if state else None, "runStatus": state["status"] if state else None,
               "approvalMode": grant["authority"]["approvalMode"] if grant else None,
               "phaseCheckpoint": grant["checkpoint"] if grant else None, "blockers": blockers,
               "candidates": candidates, "workers": [self.worker_in(db, meta, kernel, w, not blockers) for w in workers],
               "budget": self.store.budget(kernel, allocation) if allocation else None,
               "sharedStateHash": digest(shared), "latestDecisionHash": digest(latest) if latest else None,
               "latestDecision": {k: latest["request"][k] for k in ("choice", "rationale", "reuseReason", "resumeEvent")} if latest else None,
               "nativeCallMade": False, "executionAuthorized": False, "automaticSelection": False,
               "note": "Candidates are not reservations. Recheck native handoffs; a final reply is not acceptance."}
        require(len(canonical(out).encode()) <= 128000, "Lifecycle context exceeds its output bound")
        return {**out, "contextHash": digest(out)}

    def inspect(self, token):
        with self.bridge.locked(token) as (db, meta), self.store.tx() as kernel:
            return self.context_in(db, meta, kernel)

    def read(self, token, key):
        with self.bridge.locked(token) as (db, _):
            doc = self.document_in(db, key)
            require(self.prior_in(db, doc["request"]["id"]) == doc, "Brain decision receipt changed")
            return {"decision": doc, **self.receipt(doc)}

    @staticmethod
    def receipt(doc):
        request = doc["request"]
        return {"decisionHash": digest(doc), "choice": request["choice"], "queueId": request["queueId"],
                "workerId": request["workerId"], "approvalHash": doc["approvalHash"],
                "next": {"create": "brain-cycle-reserve", "continue": "correction-handoff-prepare",
                         "handle": "bounded_brain_planning_only", "wait": "wait_for_named_event"}[request["choice"]],
                "resumeEvent": request["resumeEvent"], "executionAuthorized": False, "nativeCallMade": False}

    def decide(self, token, request):
        exact(request, {"id", "expectedRevision", "contextHash", "choice", "queueId", "workerId", "estimates",
                        "rationale", "reuseReason", "scopeAssessment", "resumeEvent"})
        request = copy.deepcopy(request)
        identifier(request["id"]); integer(request["expectedRevision"]); sha(request["contextHash"])
        require(len(canonical(request).encode()) <= 16000, "Brain decision request exceeds its bound")
        choice = request["choice"]
        require(choice in ("create", "continue", "handle", "wait"), "Unknown brain lifecycle choice")
        for name in ("rationale", "reuseReason"): missions.text(request[name], name)
        require((request["queueId"] is not None) == (choice == "create") and
                (request["workerId"] is not None) == (choice == "continue"), "Choice requires an exact matching target")
        if choice == "create":
            missions.text(request["queueId"], "Queue ID", 200)
            missions.text(request["scopeAssessment"], "Scope assessment")
            exact(request["estimates"], {"workTokens", "reviewTokens", "handoffTokens"})
            for amount in request["estimates"].values(): integer(amount, 1, 1_000_000_000)
        else: require(request["estimates"] is None and request["scopeAssessment"] is None, "Only create binds task approval and estimates")
        if choice == "continue": identifier(request["workerId"])
        if choice == "wait": missions.text(request["resumeEvent"], "Named resume event")
        else: require(request["resumeEvent"] is None, "Only wait binds a resume event")
        # Replays are historical, including after Pause; never approve or reserve again.
        with self.bridge.locked(token) as (db, _):
            prior = self.prior_in(db, request["id"])
            if prior:
                require(prior["request"] == request, "Brain decision ID reused with different content")
                return self.receipt(prior)
        with self.bridge.locked(token, effects=choice in ("create", "continue")) as (db, meta):
            prior = self.prior_in(db, request["id"])
            if prior:
                require(prior["request"] == request, "Brain decision ID reused with different content")
                return self.receipt(prior)
            with self.store.tx() as kernel:
                context = self.context_in(db, meta, kernel)
                require(request["expectedRevision"] == meta["revision"] and request["contextHash"] == context["contextHash"],
                        "Lifecycle context changed; inspect and decide again")
                approval, target = None, None
                if choice == "create":
                    target = next((q for q in context["candidates"] if q["queueId"] == request["queueId"]), None)
                    require(target and target["canCreate"], "Selected packet is not eligible for creation")
                    require(request["estimates"]["workTokens"] >= target["estimatedWorkTokens"], "Work estimate undercuts the task declaration")
                    allocation = self.bridge.allocation_in(db, kernel, context["runHash"])
                    self.store.check_budget(kernel, allocation, sum(request["estimates"].values()))
                    approval = target["approvalHash"]
                    if approval is None:
                        approved = runs.approve_task_in(self.ledger, db, {
                            "id": "cycle-" + slot(self.bridge.workspace_id, request["id"]), "expectedRevision": meta["revision"],
                            "runHash": context["runHash"], "queueId": target["queueId"], "contractHash": target["contractHash"],
                            "scopeAssessment": request["scopeAssessment"], "confirmed": True}, actor="designated_brain", token=token)
                        approval = approved["approvalHash"]
                elif choice == "continue":
                    target = next((w for w in context["workers"] if w["workerId"] == request["workerId"]), None)
                    require(target and target["canContinue"], "Selected task cannot continue; reconcile its exact state")
                previous = self.latest_in(db, meta)
                require(not previous or previous["version"] < 1000, "Brain decision history needs explicit maintenance")
                doc = {"kind": KIND, "schemaVersion": 1, "workspaceId": self.bridge.workspace_id, "brainId": meta["brainId"],
                       "version": previous["version"] + 1 if previous else 1, "previousHash": digest(previous) if previous else None,
                       "request": request, "runHash": context["runHash"], "target": target, "approvalHash": approval, "at": time.time()}
                key = runs.retain(db, KIND, doc)
                db.execute("INSERT INTO snapshots VALUES(?,?,?)", (slot(self.bridge.workspace_id, request["id"]), SLOT,
                           canonical({"decisionHash": key})))
                # Approval may have advanced metadata; never overwrite its revision.
                meta = self.ledger.get(db, "meta", 1); meta["brainCycleHash"] = key
                self.ledger.put(db, "meta", 1, meta)
                self.ledger.event(db, "brain_cycle_decided", {"decisionHash": key, "choice": choice})
                return self.receipt(doc)

    def selected_in(self, db, meta, key):
        doc = self.latest_in(db, meta)
        require(doc and digest(doc) == key and doc["request"]["choice"] == "create", "Exact latest create decision required")
        require(0 <= time.time() - doc["at"] <= 60, "Create decision expired; reconcile any reservation before deciding again")
        q, _ = runs.contract_in(self.ledger, db, doc["target"]["queueId"], doc["target"]["contractHash"])
        require(q["seedHash"] == doc["target"]["seedHash"] and q.get("phaseApprovalHash") == doc["approvalHash"],
                "Selected task scope or approval changed")
        return doc

    def reserve(self, token, key):
        sha(key)
        with self.bridge.locked(token, effects=True) as (db, meta):
            doc = self.selected_in(db, meta, key)
        selected = SelectedAdmission(self, key)
        return selected.reserve(token, run_hash=doc["runHash"], queue_id=doc["target"]["queueId"],
                                approval_hash=doc["approvalHash"], estimates=doc["request"]["estimates"])


class SelectedAdmission(DispatchAdmission):
    """Revalidate selection inside both existing reservation transactions."""
    def __init__(self, coordinator, key):
        self.coordinator, self.decision_hash = coordinator, key
        bridge = coordinator.bridge
        super().__init__(bridge.registry, bridge.workspace_id, bridge.store)

    def task_in(self, db, meta, run_hash, queue_id, approval_hash, worker_id, **kwargs):
        doc = self.coordinator.selected_in(db, meta, self.decision_hash)
        require(doc["runHash"] == run_hash and doc["target"]["queueId"] == queue_id and doc["approvalHash"] == approval_hash,
                "Reservation differs from the selected decision")
        return super().task_in(db, meta, run_hash, queue_id, approval_hash, worker_id, **kwargs)
