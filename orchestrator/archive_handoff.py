"""Owner-bound, one-shot native archival handoff; no native transport or cleanup."""
import copy
import json
import time

from . import run_authority as runs
from .admission import exact, identifier, integer, sha, timestamp
from .core import canonical, digest, require
from .local_preservation import PROVENANCE
from .result_handoff import ResultHandoff, scope_in
from .result_review import artifact_in

KIND = "archive_handoff"
CHECK = "archive_handoff_check"
OBSERVATION = "archive_handoff_observation"
SLOT = "archive_handoff_slot"
PAYLOAD = {"workerId", "reviewHash", "preservationArtifactId", "confirmed", "allowManagedWorktreeCleanup"}
OWNERS = {"dashboard", "explicit_user_via_brain"}


def slot(worker_id): return digest({"kind": SLOT, "workerId": worker_id})


def arguments(worker):
    require(worker.get("hostId") == "local" and worker.get("threadId"), "Exact confirmed local archive target required")
    return {"hostId": worker["hostId"], "threadId": worker["threadId"], "archived": True}


def binding_in(ledger, db, worker):
    intent = runs.document(db, worker.get("dispatchAdmission", {}).get("intentHash"), "dispatch_intent")
    scope_in(db, intent)
    record = runs.document(db, worker.get("resultReviewHash"), "result_review")
    require(record["workerId"] == worker["id"] == intent["workerId"] and record["intentHash"] == digest(intent) and
            record["request"]["outcome"] == "accepted" and worker["status"] == "complete" and worker.get("preserved") is True,
            "Accepted exact result required for archival")
    terminal = runs.document(db, record["request"]["settlementHash"], "ownership_settlement")
    require(worker.get("ownershipSettlementHash") == digest(terminal) and terminal["intentHash"] == digest(intent),
            "Archive settlement binding changed")
    tasks = terminal["request"]["inventory"]["tasks"]
    require(len(tasks) == 1 and tasks[0]["parent"] is None and
            (tasks[0]["hostId"], tasks[0]["threadId"]) == (worker.get("hostId"), worker.get("threadId")),
            "First archival handoff supports only a root task without descendants")
    args = arguments(worker)
    require(args["threadId"] != ledger.get(db, "meta", 1)["brainId"], "The brain cannot archive itself through a worker control")
    proof = record["request"]["result"]["preservation"]
    info, _ = artifact_in(db, proof["artifactId"], intent, "preservation", record["request"]["result"]["commit"])
    require(proof["status"] == "verified" and info.get("provenance") == PROVENANCE,
            "Archival requires measured local preservation, not a supplied note")
    return {"workerId": worker["id"], "reviewHash": digest(record), "preservationArtifactId": info["id"],
            "confirmed": True, "allowManagedWorktreeCleanup": True}


def owner_request_in(ledger, db, worker, command, *, current=False):
    exact(command["payload"], PAYLOAD)
    from .retention_policy import validate_command
    delegated = validate_command(db, worker, command, ledger=ledger, current=current)
    require(command["actor"] in OWNERS or delegated is not None, "An explicit owner archival request is required")
    require(command["payload"].get("confirmed") is True and command["payload"].get("allowManagedWorktreeCleanup") is True,
            "Owner must explicitly acknowledge native managed-worktree cleanup")
    require(command["payload"] == binding_in(ledger, db, worker), "Archive request review or preservation changed")
    original = {k: command[k] for k in ("id", "kind", "expectedRevision", "payload")}
    require(command["kind"] == "archive" and command["fingerprint"] == digest(original), "Owner archive request integrity changed")
    return command


def submit_in(ledger, db, worker, command):
    owner_request_in(ledger, db, worker, command, current=True)
    require(not worker.get("archived") and not worker.get("archiveHandoffHash") and
            not db.execute("SELECT 1 FROM snapshots WHERE id=?", (slot(worker["id"]),)).fetchone(),
            "Archive already attempted; retain its receipt and do not retry")
    require(not any(c["kind"] == "archive" and c["payload"].get("workerId") == worker["id"] and
                    c["status"] in ("queued", "processing") for c in ledger.all(db, "commands")), "Archive request already pending")


def process_in(ledger, db, worker, command):
    # Existing helper generations must never emit a generic managed archive action.
    owner_request_in(ledger, db, worker, command, current=True)
    command.update(status="queued", archiveReceivedAt=time.time(),
                   result="Authorized archive request received; dedicated handoff and fresh safety evidence required")
    return {"kind": "archive_handoff_required", "commandId": command["id"], "workerId": worker["id"],
            "nativeCallMade": False, "sendPermit": False}


def observation_shape(request):
    exact(request, {"id", "handoffHash", "expectedObservationHash", "hostId", "threadId", "outcome", "observedAt", "evidenceHash"})
    identifier(request["id"]); sha(request["handoffHash"]); timestamp(request["observedAt"]); sha(request["evidenceHash"])
    identifier(request["hostId"]); identifier(request["threadId"])
    if request["expectedObservationHash"] is not None: sha(request["expectedObservationHash"])
    require(request["outcome"] in ("unknown", "archived", "cancelled"), "Explicit archive observation required")


def validate_projection(db, worker, review):
    """Historical integrity only, called by accepted-result validation; no recursion."""
    key = worker.get("archiveHandoffHash")
    row = db.execute("SELECT kind,data FROM snapshots WHERE id=?", (slot(worker["id"]),)).fetchone()
    if not key and not row:
        require(not worker.get("archived") and not any(k in worker for k in ("archiveHandoffCheckHash", "archiveObservationHash")),
                "Archive projection has no retained handoff")
        return None, None, None
    require(key and row and row[0] == SLOT and row[1] == canonical({"handoffHash": key}), "Archive handoff slot or pointer changed")
    doc = runs.document(db, key, KIND)
    require(doc["workerId"] == worker["id"] and doc["reviewHash"] == digest(review) and
            doc["intentHash"] == review["intentHash"] and doc["arguments"] == arguments(worker), "Archive handoff identity changed")
    row = db.execute("SELECT data FROM commands WHERE id=?", (doc["command"]["id"],)).fetchone()
    require(row is not None, "Archive owner command missing")
    command = json.loads(row[0])
    from .retention_policy import validate_command
    delegated = validate_command(db, worker, command)
    require({k: command.get(k) for k in doc["command"]} == doc["command"] and
            doc["command"]["payload"] == {"workerId": worker["id"], "reviewHash": digest(review),
                "preservationArtifactId": review["request"]["result"]["preservation"]["artifactId"],
                "confirmed": True, "allowManagedWorktreeCleanup": True} and
            (doc["command"]["actor"] in OWNERS or delegated is not None) and
            doc["command"]["fingerprint"] == digest({k: doc["command"][k] for k in ("id", "kind", "expectedRevision", "payload")}),
            "Archive owner binding changed")
    check = runs.document(db, worker["archiveHandoffCheckHash"], CHECK) if worker.get("archiveHandoffCheckHash") else None
    if check:
        require(check["handoffHash"] == key and check["workerId"] == worker["id"] and check["at"] >= doc["at"],
                "Archive send boundary changed")
    latest = runs.document(db, worker["archiveObservationHash"], OBSERVATION) if worker.get("archiveObservationHash") else None
    cursor = latest; count = 0
    while cursor:
        count += 1; require(count <= 16, "Archive observation history requires operator reconciliation")
        request = cursor["request"]; observation_shape(request)
        require(cursor["workerId"] == worker["id"] and request["handoffHash"] == key and
                (request["hostId"], request["threadId"]) == (worker["hostId"], worker["threadId"]) and
                doc["at"] <= request["observedAt"] <= cursor["at"] and
                ((check is None and request["outcome"] == "cancelled") or
                 (check is not None and request["outcome"] != "cancelled" and request["observedAt"] >= check["at"])),
                "Archive observation binding or send boundary changed")
        pointer = db.execute("SELECT kind,data FROM snapshots WHERE id=?", (observation_key(worker["id"], request["id"]),)).fetchone()
        require(pointer and pointer[0] == "archive_observation_request" and pointer[1] == canonical({"observationHash": digest(cursor)}),
                "Archive observation receipt changed or missing")
        prev = runs.document(db, request["expectedObservationHash"], OBSERVATION) if request["expectedObservationHash"] else None
        if prev:
            require(prev["request"]["outcome"] == "unknown" and prev["request"]["observedAt"] <= request["observedAt"],
                    "Archive terminal outcome cannot be replaced or backdated")
        cursor = prev
    outcome = latest["request"]["outcome"] if latest else "pending"
    require(worker.get("archived") is (outcome == "archived") and command["status"] == (
        "completed" if outcome == "archived" else "rejected" if outcome == "cancelled" else "processing"),
        "Archive worker or command projection changed")
    return doc, check, latest


def observation_key(worker_id, request_id):
    return digest({"kind": "archive_observation_request", "workerId": worker_id, "id": request_id})


def receipt(doc):
    return {"workerId": doc["workerId"], "observationHash": digest(doc), "outcome": doc["request"]["outcome"],
            "observedAt": doc["request"]["observedAt"], "sendPermit": False, "nativeCallMade": False,
            "trustBoundary": "brain_supplied_native_outcome_not_independent_attestation"}


class ArchiveHandoff:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.results = ResultHandoff(bridge)

    def context_in(self, db, kernel, worker, intent):
        _, terminal = self.results.terminal_in(db, kernel, worker, intent)
        payload = binding_in(self.ledger, db, worker)
        review = runs.document(db, worker["resultReviewHash"], "result_review")
        return terminal, review, payload, validate_projection(db, worker, review)

    def safety_in(self, db, meta, kernel, worker, intent, command, inventory, lower, *, preparing=False):
        self.results.reviewer.settlement.maintenance_check(kernel)
        runs.require_current(self.ledger, db, intent["runHash"])
        from .brain_control import stopped
        require(not stopped(meta) and meta["runner"] is None, "Brain stop or runner ownership fences archival")
        owner_request_in(self.ledger, db, worker, command, current=True)
        require(command["status"] == ("queued" if preparing else "processing") and command.get("archiveReceivedAt") and
                not worker.get("archived"), "Exact received pending owner archive request required")
        require(not any(c["id"] != command["id"] and c["kind"] in ("archive", "checkpoint") and
                        c["status"] in ("queued", "processing") and c["payload"].get("workerId") == worker["id"]
                        for c in self.ledger.all(db, "commands")), "Other worker controls remain unresolved")
        pair = (worker["hostId"], worker["threadId"])
        require(self.results.reviewer.settlement.known_descendants(db, pair) == {pair}, "Known descendants prevent root-only archival")
        exact(inventory, {"observedAt", "evidenceHash", "complete", "includesDescendants", "effectsComplete", "tasks"})
        sha(inventory["evidenceHash"]); timestamp(inventory["observedAt"])
        require(all(inventory[k] is True for k in ("complete", "includesDescendants", "effectsComplete")) and
                isinstance(inventory["tasks"], list) and len(inventory["tasks"]) == 1, "Complete root-only native inventory required")
        task = inventory["tasks"][0]
        exact(task, {"hostId", "threadId", "status", "observedAt", "evidenceHash", "worktreePreserved"})
        sha(task["evidenceHash"]); timestamp(task["observedAt"])
        require((task["hostId"], task["threadId"]) == pair and task["status"] == "idle" and task["worktreePreserved"] is True,
                "Exact idle task and independently verified worktree preservation required")
        policy = self.store.get(kernel, "meta", 1)["policy"]
        for at in (task["observedAt"], inventory["observedAt"]): self.store.fresh(at, policy)
        require(lower <= task["observedAt"] <= inventory["observedAt"], "Archive safety observation predates this boundary")

    def state(self, token, worker_id):
        with self.bridge.locked(token) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel: _, _, payload, (doc, check, latest) = self.context_in(db, kernel, worker, intent)
            from .retention_policy import state_in
            return {"workerId": worker_id, "revision": meta["revision"], "ownerRequestPayload": payload,
                    "retention": state_in(self.ledger, db, worker, intent),
                    "handoffHash": digest(doc) if doc else None, "checkHash": digest(check) if check else None,
                    "observation": receipt(latest) if latest else None, "archived": worker["archived"],
                    "sendPermit": False, "nativeCallMade": False, "currentNativeActivity": "not_observed"}

    def request_delegated(self, token, worker_id, request):
        from .retention_policy import request_archive
        return request_archive(self, token, worker_id, request)

    def prepare(self, token, worker_id, request):
        exact(request, {"commandId", "expectedRevision", "inventory"}); identifier(request["commandId"]); integer(request["expectedRevision"])
        request = copy.deepcopy(request)
        with self.bridge.locked(token, effects=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                terminal, review, _, (doc, _, _) = self.context_in(db, kernel, worker, intent)
                require(doc is None, "Archive handoff already retained; inspect, never reissue")
                require(meta["revision"] == request["expectedRevision"], "Archive workspace revision changed")
                command = self.ledger.get(db, "commands", request["commandId"])
                self.safety_in(db, meta, kernel, worker, intent, command, request["inventory"],
                               max(command["createdAt"], review["at"], terminal["at"]), preparing=True)
            doc = {"kind": KIND, "workerId": worker_id, "intentHash": digest(intent), "reviewHash": digest(review),
                   "request": request, "arguments": arguments(worker), "at": time.time(),
                   "command": {k: command[k] for k in ("id", "kind", "expectedRevision", "payload", "actor", "fingerprint", "createdAt", "archiveReceivedAt")}}
            if "retentionHash" in command: doc["command"]["retentionHash"] = command["retentionHash"]
            key = runs.retain(db, KIND, doc)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (slot(worker_id), SLOT, canonical({"handoffHash": key})))
            worker["archiveHandoffHash"] = key; self.ledger.put(db, "workers", worker_id, worker)
            command.update(status="processing", result="Archive handoff prepared; fresh one-shot send check required")
            self.ledger.put(db, "commands", command["id"], command)
            self.ledger.event(db, "archive_handoff_prepared", {"workerId": worker_id, "handoffHash": key})
            return {"handoffHash": key, "sendPermit": False, "nativeCallMade": False, "checkRequired": True}

    def check(self, token, worker_id, request):
        exact(request, {"handoffHash", "expectedRevision", "inventory"}); sha(request["handoffHash"]); integer(request["expectedRevision"])
        request = copy.deepcopy(request)
        with self.bridge.locked(token, effects=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                _, _, _, (doc, checked, latest) = self.context_in(db, kernel, worker, intent)
                require(doc and digest(doc) == request["handoffHash"] and not checked and not latest,
                        "Archive send boundary already consumed or unavailable; never resend")
                require(meta["revision"] == request["expectedRevision"], "Archive workspace revision changed")
                command = self.ledger.get(db, "commands", doc["command"]["id"])
                self.store.fresh(doc["at"], self.store.get(kernel, "meta", 1)["policy"])
                self.safety_in(db, meta, kernel, worker, intent, command, request["inventory"], doc["at"])
            checked = {"kind": CHECK, "workerId": worker_id, "handoffHash": digest(doc), "request": request, "at": time.time()}
            worker["archiveHandoffCheckHash"] = runs.retain(db, CHECK, checked)
            self.ledger.put(db, "workers", worker_id, worker)
            self.ledger.event(db, "archive_send_boundary_consumed", {"workerId": worker_id, "checkHash": digest(checked)})
            return {"checkHash": digest(checked), "tool": "set_thread_archived", "arguments": doc["arguments"],
                    "sendPermit": True, "nativeCallMade": False, "retryAllowed": False}

    def record(self, token, worker_id, request):
        observation_shape(request); request = copy.deepcopy(request)
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                _, _, _, (doc, check, latest) = self.context_in(db, kernel, worker, intent)
                require(doc and digest(doc) == request["handoffHash"], "Exact retained archive handoff required")
                require((request["hostId"], request["threadId"]) == (worker["hostId"], worker["threadId"]),
                        "Archive observation belongs to another task or host")
                key = observation_key(worker_id, request["id"])
                row = db.execute("SELECT kind,data FROM snapshots WHERE id=?", (key,)).fetchone()
                if row:
                    require(row[0] == "archive_observation_request", "Invalid archive observation receipt")
                    prior = runs.document(db, json.loads(row[1])["observationHash"], OBSERVATION)
                    require(prior["workerId"] == worker_id and prior["request"] == request, "Archive observation ID reused with different content")
                    return receipt(prior)
                require(request["expectedObservationHash"] == (digest(latest) if latest else None) and
                        (not latest or latest["request"]["outcome"] == "unknown"), "Archive observation changed or already final")
                require((not check and request["outcome"] == "cancelled") or (check and request["outcome"] != "cancelled"),
                        "Archive send uncertainty cannot be cancelled as unsent")
                lower = max(doc["at"], check["at"] if check else 0, latest["request"]["observedAt"] if latest else 0)
                self.store.fresh(request["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
                require(request["observedAt"] >= lower, "Archive result observation is backdated")
            observed = {"kind": OBSERVATION, "workerId": worker_id, "request": request, "at": time.time()}
            obs_hash = runs.retain(db, OBSERVATION, observed)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, "archive_observation_request", canonical({"observationHash": obs_hash})))
            worker.update(archiveObservationHash=obs_hash, archived=request["outcome"] == "archived")
            command = self.ledger.get(db, "commands", doc["command"]["id"])
            command.update(status="completed" if worker["archived"] else "rejected" if request["outcome"] == "cancelled" else "processing",
                           result="Native archive observed" if worker["archived"] else "Unsent archive cancelled" if request["outcome"] == "cancelled" else "Archive outcome uncertain; reconcile without retry")
            self.ledger.put(db, "workers", worker_id, worker); self.ledger.put(db, "commands", command["id"], command)
            validate_projection(db, worker, runs.document(db, worker["resultReviewHash"], "result_review"))
            self.ledger.event(db, "archive_observed", {"workerId": worker_id, "observationHash": obs_hash})
            return receipt(observed)
