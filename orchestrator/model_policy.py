"""Owner-reviewed native model policy; no model calls, transport or global config.

Capability/application observations are trusted-controller assertions, not host
attestation. Internal owner methods require a separately authenticated caller.
"""
import copy
import contextlib
import re
import time

from . import missions, run_authority as runs, task_contracts
from .admission import exact, identifier, integer, sha, timestamp
from .core import Refusal, canonical, digest, require
from .native_lifecycle import NativeLifecycle

EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
COMPLEXITY = ("routine", "standard", "complex", "critical")
CAP_AGE = 300
SETTING_AGE = 60
REVIEW_FIELDS = {"missionHash", "reviewReceiptHash", "capabilityHash", "profiles", "qualityFloors", "maxEscalations", "confirmed"}


def name(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}", value), "Bounded model/profile identifier required")
    return value


def settings(value):
    exact(value, {"model", "effort", "speed"})
    name(value["model"])
    require(isinstance(value["effort"], str) and value["effort"] in EFFORTS and value["speed"] is None, "Unsupported effort or speed; never fall back")
    return value


def fresh(at, age):
    timestamp(at)
    require(0 <= time.time() - at <= age, "Model evidence is stale or future-dated")


def capability_in(ledger, db, *, current=True):
    meta = ledger.get(db, "meta", 1)
    doc = runs.document(db, meta.get("modelCapabilityHash"), "model_capability")
    require(doc["version"] == db.execute("SELECT count(*) FROM snapshots WHERE kind='model_capability'").fetchone()[0],
            "Model capability pointer is not the latest retained observation")
    require(doc["workspaceId"] == missions.workspace(ledger) and doc["brainId"] == meta["brainId"], "Foreign model capability")
    require(doc["catalogHash"] == digest(doc["catalog"]), "Model catalog changed")
    if current: fresh(doc["observedAt"], CAP_AGE)
    return doc


def record_capability(ledger, token, request):
    request = copy.deepcopy(request)
    with ledger.tx() as db:
        meta, key, fp, prior = runs.request_in(ledger, db, request, "designated_brain", "model_capability",
            {"hostId", "models", "observedAt", "evidenceHash"}, token)
        if prior: return prior
        require(request["hostId"] == "local", "Only the local native task adapter is qualified")
        fresh(request["observedAt"], CAP_AGE); sha(request["evidenceHash"])
        require(isinstance(request["models"], list) and 1 <= len(request["models"]) <= 32, "Bounded native model catalog required")
        models = []
        for row in request["models"]:
            exact(row, {"model", "efforts"}); name(row["model"])
            require(isinstance(row["efforts"], list) and 1 <= len(row["efforts"]) <= len(EFFORTS) and
                    all(isinstance(e, str) and e in EFFORTS for e in row["efforts"]) and
                    len(set(row["efforts"])) == len(row["efforts"]), "Exact supported effort list required")
            models.append({"model": row["model"], "efforts": sorted(row["efforts"])})
        require(len({r["model"] for r in models}) == len(models), "Duplicate model capability")
        catalog = {"hostId": "local", "adapter": "codex_app_model_thinking_v1", "speedSupported": False,
                   "models": sorted(models, key=lambda r: r["model"])}
        previous = meta.get("modelCapabilityHash")
        version = 1
        if previous:
            old = capability_in(ledger, db, current=False)
            require(request["observedAt"] > old["observedAt"], "Capability time must advance")
            if meta.get("modelPolicyHash") and old["catalogHash"] != digest(catalog):
                # A later return to the original catalog is not a new owner review.
                meta["modelPolicyCatalogInvalidated"] = True
            version = old["version"] + 1
        else:
            require(not db.execute("SELECT 1 FROM snapshots WHERE kind='model_capability'").fetchone(), "Capability pointer missing; explicit recovery required")
        require(version <= 1000, "Capability history requires explicit maintenance")
        doc = {"kind": "model_capability", "workspaceId": missions.workspace(ledger), "brainId": meta["brainId"],
               "catalog": catalog, "catalogHash": digest(catalog), "observedAt": request["observedAt"],
               "evidenceHash": request["evidenceHash"], "previousHash": previous, "version": version,
               "trustBoundary": "caller_supplied_native_tool_schema"}
        value = runs.retain(db, "model_capability", doc)
        meta["modelCapabilityHash"] = value; ledger.put(db, "meta", 1, meta)
        return runs.receipt_in(ledger, db, key, fp, "model_capability", capabilityHash=value, catalogHash=doc["catalogHash"])


def supported(cap, value):
    settings(value)
    require(any(row["model"] == value["model"] and value["effort"] in row["efforts"] for row in cap["catalog"]["models"]),
            "Requested model/effort is unavailable on the observed host")


def validate_review_in(ledger, db, request):
    """Shared read-only validation for owner preview and atomic review."""
    meta = ledger.get(db, "meta", 1)
    require(request["confirmed"] is True and meta["paused"], "Explicit owner confirmation while paused required")
    source = runs.mission_source(ledger, db); task_contracts.reviewed_phase(source)
    require(request["missionHash"] == source["mission"]["documentHash"] and
            request["reviewReceiptHash"] == source["mission"]["receiptHash"], "Exact reviewed mission required")
    cap = capability_in(ledger, db)
    require(digest(cap) == request["capabilityHash"], "Exact current capability observation required")
    exact(request["qualityFloors"], set(COMPLEXITY))
    floors = [integer(request["qualityFloors"][c], 1, 4) for c in COMPLEXITY]
    require(floors == sorted(floors), "Complexity quality floors must not decrease")
    integer(request["maxEscalations"], 0, 2)
    require(isinstance(request["profiles"], list) and 1 <= len(request["profiles"]) <= 16, "Bounded approved profiles required")
    for profile in request["profiles"]:
        exact(profile, {"id", "settings", "quality", "minimumWorkTokens"}); name(profile["id"])
        supported(cap, profile["settings"]); integer(profile["quality"], 1, 4); integer(profile["minimumWorkTokens"], 1, 1_000_000_000)
        require(profile["settings"]["effort"] != "ultra", "Automatic-delegation effort needs qualified descendant admission")
    require(len({p["id"] for p in request["profiles"]}) == len(request["profiles"]), "Duplicate profile ID")
    require(len({digest(p["settings"]) for p in request["profiles"]}) == len(request["profiles"]), "Duplicate profile settings")
    require(any(p["quality"] >= max(floors) for p in request["profiles"]), "No profile meets the highest quality floor")
    return cap


def review(ledger, request, *, actor, _db=None):
    require(actor == "dashboard_owner", "Only the owner can review model policy")
    request = copy.deepcopy(request)
    with (contextlib.nullcontext(_db) if _db is not None else ledger.tx()) as db:
        require(db.in_transaction, "Model policy review requires a transaction")
        meta, key, fp, prior = runs.request_in(ledger, db, request, actor, "model_policy_review",
            REVIEW_FIELDS)
        if prior: return prior
        cap = validate_review_in(ledger, db, request)
        doc = {"kind": "model_policy", "workspaceId": missions.workspace(ledger), "brainId": meta["brainId"],
               "actor": actor, "missionHash": request["missionHash"], "reviewReceiptHash": request["reviewReceiptHash"],
               "catalogHash": cap["catalogHash"], "profiles": copy.deepcopy(request["profiles"]),
               "qualityFloors": copy.deepcopy(request["qualityFloors"]), "maxEscalations": request["maxEscalations"],
               "previousHash": meta.get("modelPolicyHash"), "at": time.time()}
        value = runs.retain(db, "model_policy", doc)
        meta.update(modelPolicyHash=value, modelPolicyRevoked=False, modelPolicyCatalogInvalidated=False)
        ledger.put(db, "meta", 1, meta)
        runs.fence_in(ledger, db, meta, "model_policy_changed")
        return runs.receipt_in(ledger, db, key, fp, "model_policy_review", policyHash=value)


def revoke(ledger, request, *, actor, _db=None):
    require(actor == "dashboard_owner", "Only the owner can revoke model policy")
    request = copy.deepcopy(request)
    with (contextlib.nullcontext(_db) if _db is not None else ledger.tx()) as db:
        require(db.in_transaction, "Model policy revocation requires a transaction")
        meta, key, fp, prior = runs.request_in(ledger, db, request, actor, "model_policy_revoke", {"policyHash", "reason"})
        if prior: return prior
        sha(request["policyHash"]); missions.text(request["reason"], "Revocation reason")
        require(meta.get("modelPolicyHash") == request["policyHash"], "Exact current model policy required")
        runs.document(db, request["policyHash"], "model_policy")
        meta["modelPolicyRevoked"] = True; ledger.put(db, "meta", 1, meta)
        runs.fence_in(ledger, db, meta, "model_policy_revoked")
        return runs.receipt_in(ledger, db, key, fp, "model_policy_revoke", policyHash=request["policyHash"])


def policy_in(ledger, db, value, *, current=True):
    if value == "native_defaults": return None
    exact(value, {"mode", "policyHash"}); require(value["mode"] == "adaptive", "Unsupported settings policy")
    doc = runs.document(db, value["policyHash"], "model_policy")
    meta = ledger.get(db, "meta", 1)
    require(doc["actor"] == "dashboard_owner" and doc["workspaceId"] == missions.workspace(ledger) and
            doc["brainId"] == meta["brainId"], "Model policy identity changed")
    if current:
        require(meta.get("modelPolicyHash") == value["policyHash"] and meta.get("modelPolicyRevoked") is False,
                "Model policy revoked or superseded")
        require(not meta.get("modelPolicyCatalogInvalidated"), "Host catalog changed; owner policy review required")
        source = runs.mission_source(ledger, db); task_contracts.reviewed_phase(source)
        require(doc["missionHash"] == source["mission"]["documentHash"] and
                doc["reviewReceiptHash"] == source["mission"]["receiptHash"], "Model policy mission changed")
        require(capability_in(ledger, db)["catalogHash"] == doc["catalogHash"], "Host catalog changed; owner policy review required")
    return doc


def selection_in(db, key, *, run_hash, contract_hash):
    doc = runs.document(db, key, "model_selection")
    require(doc["runHash"] == run_hash and doc["contractHash"] == contract_hash, "Foreign model selection")
    return doc


def initial_in(ledger, db, grant, q, contract):
    value = grant["settingsPolicy"]
    policy = policy_in(ledger, db, value)
    if policy is None:
        require(all(v is None for v in contract["spec"]["requestedSettings"].values()), "Task settings exceed the authorized native-defaults policy")
        return None
    require(contract["repositoryBinding"]["policyProfile"] == "standard", "Harness adaptive settings require its trusted adapter")
    require(q.get("modelSelectionHash"), "Select an approved model profile before task approval/admission")
    doc = selection_in(db, q.get("modelSelectionHash"), run_hash=digest(grant), contract_hash=digest(contract))
    require(doc["workerId"] is None and doc["queueId"] == q["id"] and doc["policyHash"] == value["policyHash"] and
            doc["settings"] == contract["spec"]["requestedSettings"], "Initial settings selection changed")
    return doc


def initial_arguments(ledger, db, intent):
    grant = runs.document(db, intent["runHash"], "run_authorization")
    q = ledger.get(db, "queue", intent["queueId"]); contract = runs.document(db, intent["contractHash"], "task_contract")
    doc = initial_in(ledger, db, grant, q, contract)
    return {"model": doc["settings"]["model"], "thinking": doc["settings"]["effort"]} if doc else {}


def active_selection(ledger, db, worker, intent, state):
    """Historical last consumed selection, never an unconsumed preparation."""
    grant = runs.document(db, intent["runHash"], "run_authorization")
    if grant["settingsPolicy"] == "native_defaults": return None, None, None
    continuation = state["continuation"]
    if continuation:
        effect = runs.document(db, continuation["intentHash"], "native_continuation_intent")
        require(effect["workerId"] == worker["id"] and effect["intentHash"] == digest(intent), "Model continuation scope changed")
        key, boundary, at = effect["request"].get("modelSelectionHash"), continuation["intentHash"], continuation["at"]
    else:
        check = runs.document(db, worker.get("nativeHandoffCheckHash"), "native_creation_check")
        require(check["workerId"] == worker["id"] and check["intentHash"] == digest(intent) and
                check["handoffHash"] == worker.get("nativeHandoffHash"), "Settings need the consumed creation handoff")
        key = ledger.get(db, "queue", intent["queueId"]).get("modelSelectionHash")
        boundary, at = digest(check), check["at"]
    doc = selection_in(db, key, run_hash=intent["runHash"], contract_hash=intent["contractHash"])
    return doc, boundary, at


def observation_in(db, worker, intent):
    key = worker.get("modelObservationHash")
    slot = digest({"kind": "model_observation_latest", "intentHash": digest(intent)})
    row = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=100 THEN data END FROM snapshots WHERE id=?", (slot,)).fetchone()
    if not key and not row: return None
    require(key and row and row[0] == "model_observation_latest" and row[1] == canonical({"observationHash": key}),
            "Settings observation pointer changed or missing")
    doc = runs.document(db, key, "model_observation")
    require(doc["workerId"] == worker["id"] and doc["intentHash"] == digest(intent), "Foreign model observation")
    return doc


def require_observed(ledger, db, worker, intent, state):
    selected, boundary, _ = active_selection(ledger, db, worker, intent, state)
    if not selected: return None
    doc = observation_in(db, worker, intent)
    require(doc and doc["selectionHash"] == digest(selected) and doc["boundaryHash"] == boundary and
            doc["observed"] == selected["settings"] and doc["applied"] in (None, selected["settings"]),
            "Current matching native settings observation required")
    fresh(doc["observedAt"], SETTING_AGE)
    return selected


def correction_arguments(ledger, db, worker, intent, state, request):
    grant = runs.document(db, intent["runHash"], "run_authorization")
    policy = policy_in(ledger, db, grant["settingsPolicy"])
    if not policy:
        require("modelSelectionHash" not in request, "Native-default task cannot override settings")
        return {}
    old = require_observed(ledger, db, worker, intent, state)
    new = selection_in(db, request.get("modelSelectionHash"), run_hash=intent["runHash"], contract_hash=intent["contractHash"])
    require(new["policyHash"] == grant["settingsPolicy"]["policyHash"] and
            (new == old or (new["workerId"] == worker["id"] and new["previousHash"] == digest(old) and
             new["step"] == old["step"] + 1 <= policy["maxEscalations"] and new["quality"] > old["quality"])),
            "Correction settings must retain or strictly escalate the current approved selection")
    require(request["estimates"]["workTokens"] >= new["minimumWorkTokens"], "Correction estimate undercuts the selected model profile")
    return {"model": new["settings"]["model"], "thinking": new["settings"]["effort"]}


class ModelPolicy:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.lifecycle = NativeLifecycle(bridge)

    def select(self, token, request):
        request = copy.deepcopy(request)
        fields = {"runHash", "queueId", "contractHash", "workerId", "expectedHash", "profileId", "complexity", "rationale", "capabilityHash"}
        with self.bridge.locked(token, effects=False) as (db, _):
            _, _, _, prior = runs.request_in(self.ledger, db, request, "designated_brain", "model_select", fields, token)
            if prior: return prior
        with self.bridge.locked(token, effects=True) as (db, _):
            _, key, fp, prior = runs.request_in(self.ledger, db, request, "designated_brain", "model_select", fields, token)
            if prior: return prior
            grant = runs.require_current(self.ledger, db, request["runHash"])
            policy = policy_in(self.ledger, db, grant["settingsPolicy"])
            require(policy is not None, "Owner-reviewed adaptive run required")
            require(request["capabilityHash"] == digest(capability_in(self.ledger, db)), "Capability observation changed")
            q = self.ledger.get(db, "queue", request["queueId"])
            contract = runs.document(db, request["contractHash"], "task_contract")
            require((q.get("taskContract") or {}).get("hash") == request["contractHash"] and
                    task_contracts.evaluate(q, task_contracts.context_in(self.ledger, db, q), contract)["status"] == "bound" and
                    not q["held"] and contract["repositoryBinding"]["policyProfile"] == "standard", "Exact current standard task required")
            require(request["complexity"] in COMPLEXITY, "Unknown task complexity")
            rationale = missions.text(request["rationale"], "Model selection rationale")
            profile = next((p for p in policy["profiles"] if p["id"] == request["profileId"]), None)
            require(profile and profile["quality"] >= policy["qualityFloors"][request["complexity"]], "Profile fails the approved complexity quality floor")
            previous, step = None, 0
            with self.store.tx() as kernel:
                allocation = self.bridge.allocation_in(db, kernel, request["runHash"])
                work = max(contract["spec"]["estimatedTokens"], profile["minimumWorkTokens"])
                self.store.check_budget(kernel, allocation, work + 2)
                if request["workerId"] is None:
                    require(request["expectedHash"] is None and q.get("phaseApprovalHash") is None and
                            not db.execute("SELECT 1 FROM workers WHERE queue_id=?", (q["id"],)).fetchone(), "Select initial settings before task approval or ownership")
                    require(profile["settings"] == contract["spec"]["requestedSettings"], "Profile must match exact requested task settings")
                else:
                    worker, intent = self.bridge.intent_in(db, request["workerId"])
                    require(intent["runHash"] == request["runHash"] and intent["queueId"] == q["id"] and
                            intent["contractHash"] == request["contractHash"], "Foreign escalation target")
                    self.bridge.task_in(db, self.ledger.get(db, "meta", 1), intent["runHash"], q["id"], intent["approvalHash"], worker["id"])
                    _, record, state = self.lifecycle.state_in(kernel, intent)
                    require(record and request["expectedHash"] == digest(record) == worker.get("nativeLifecycleHash"), "Exact attached native state required")
                    self.lifecycle.no_unmatched_intent(worker, state)
                    require(state["creation"]["activity"] == "idle" and state["creation"]["outcome"] == "confirmed" and
                            (not state["continuation"] or state["continuation"]["status"] == "finished") and
                            (not state.get("runner") or state["runner"]["status"] == "released") and state["noProgress"] < 2,
                            "Escalation needs a fresh idle task without unresolved work")
                    self.store.fresh(state["creation"]["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
                    old = require_observed(self.ledger, db, worker, intent, state)
                    previous, step = digest(old), old["step"] + 1
                    require(step <= policy["maxEscalations"] and profile["quality"] > old["quality"] and
                            COMPLEXITY.index(request["complexity"]) >= COMPLEXITY.index(old["complexity"]),
                            "Escalation limit, quality or complexity boundary exceeded")
            doc = {"kind": "model_selection", "workspaceId": self.bridge.workspace_id, "brainId": grant["brainId"],
                   "runHash": request["runHash"], "queueId": q["id"], "contractHash": request["contractHash"],
                   "workerId": request["workerId"], "policyHash": grant["settingsPolicy"]["policyHash"],
                   "capabilityHash": request["capabilityHash"], "profileId": profile["id"], "settings": profile["settings"],
                   "quality": profile["quality"], "minimumWorkTokens": profile["minimumWorkTokens"],
                   "complexity": request["complexity"], "rationale": rationale, "previousHash": previous, "step": step, "at": time.time()}
            value = runs.retain(db, "model_selection", doc)
            if request["workerId"] is None:
                q["modelSelectionHash"] = value; self.ledger.put(db, "queue", q["id"], q)
            return runs.receipt_in(self.ledger, db, key, fp, "model_select", selectionHash=value)

    def observe(self, token, worker_id, request):
        request = copy.deepcopy(request)
        with self.bridge.locked(token) as (db, _):
            _, key, fp, prior = runs.request_in(self.ledger, db, request, "designated_brain", "model_observe",
                {"selectionHash", "boundaryHash", "hostId", "threadId", "applied", "observed", "observedAt", "evidenceHash"}, token)
            if prior:
                require(prior["workerId"] == worker_id, "Foreign settings observation replay")
                return prior
            fresh(request["observedAt"], SETTING_AGE); sha(request["evidenceHash"])
            for field in ("applied", "observed"):
                if request[field] is not None: settings(request[field])
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel:
                _, record, state = self.lifecycle.state_in(kernel, intent)
                require(record and worker.get("nativeLifecycleHash") == digest(record), "Attach native receipt before observing settings")
                selected, boundary, at = active_selection(self.ledger, db, worker, intent, state)
                require(selected and digest(selected) == request["selectionHash"] and boundary == request["boundaryHash"] and
                        request["observedAt"] > at and state["creation"]["outcome"] == "confirmed" and
                        request["hostId"] == state["creation"]["hostId"] == "local" and request["threadId"] == state["creation"]["threadId"],
                        "Settings observation must follow the exact consumed native handoff")
            previous = observation_in(db, worker, intent)
            require(not previous or request["observedAt"] > previous["observedAt"], "Settings observation time must advance")
            doc = {"kind": "model_observation", "workerId": worker_id, "intentHash": digest(intent),
                   **{k: v for k, v in request.items() if k not in ("id", "expectedRevision")},
                   "requested": selected["settings"], "previousHash": digest(previous) if previous else None,
                   "trustBoundary": "caller_supplied_native_settings_not_attestation"}
            value = runs.retain(db, "model_observation", doc)
            slot = digest({"kind": "model_observation_latest", "intentHash": digest(intent)})
            db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?)", (slot, "model_observation_latest", canonical({"observationHash": value})))
            worker["modelObservationHash"] = value; self.ledger.put(db, "workers", worker_id, worker)
            return runs.receipt_in(self.ledger, db, key, fp, "model_observe", workerId=worker_id, observationHash=value)

    def state(self, token, worker_id=None):
        with self.bridge.locked(token) as (db, meta):
            cap = capability_in(self.ledger, db, current=False) if meta.get("modelCapabilityHash") else None
            policy = runs.document(db, meta["modelPolicyHash"], "model_policy") if meta.get("modelPolicyHash") else None
            result = {"capability": cap, "policy": policy, "policyRevoked": meta.get("modelPolicyRevoked"),
                      "capabilityHash": digest(cap) if cap else None, "policyHash": digest(policy) if policy else None,
                      "capabilityFresh": bool(cap and 0 <= time.time() - cap["observedAt"] <= CAP_AGE),
                      "speedSupported": False, "executionAuthorized": False, "nativeCallMade": False}
            result.update(policyStatus="not_reviewed", policyIssue=None)
            if policy:
                try:
                    policy_in(self.ledger, db, {"mode": "adaptive", "policyHash": digest(policy)})
                    result["policyStatus"] = "current_review_not_activation"
                except Refusal as error:
                    result.update(policyStatus="blocked", policyIssue=str(error))
            if worker_id:
                worker, intent = self.bridge.intent_in(db, worker_id)
                result["observation"] = observation_in(db, worker, intent)
                observed = result["observation"]
                result["observationFresh"] = bool(observed and 0 <= time.time() - observed["observedAt"] <= SETTING_AGE)
                q = self.ledger.get(db, "queue", intent["queueId"])
                result["initialSelection"] = (selection_in(db, q["modelSelectionHash"], run_hash=intent["runHash"], contract_hash=intent["contractHash"])
                                              if q.get("modelSelectionHash") else None)
            return result
