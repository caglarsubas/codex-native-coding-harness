"""Recorded event comparison, not a scheduler, native poll or effect permission."""
from . import brain_control, run_authority as runs
from .admission import exact, sha
from .core import digest, require

PROTOCOL = "brain_event_wait_v1"
CATEGORIES = {"policy", "eligibility", "shared_admission", "queue", "workers",
              "commands", "decisions", "continuations", "repos", "quarantined_ownership",
              "artifact_metadata", "recorded_observations"}
# These writes happen while ending/receiving the same idle turn. They are not a
# new development event. New/unknown metadata is conservatively significant.
BOOKKEEPING = {"revision", "controller", "checkpoint", "lastReconciled",
               "inboxCheckedAt", "brainCycleHash", "heartbeat"}


def capture(coordinator, db, meta, kernel, context):
    tables = ("queue", "workers", "commands", "decisions", "continuations", "repos")
    coordinator.bounded_in(db, tables)
    rows = {table: sorted(coordinator.ledger.all(db, table), key=lambda r: r["id"]) for table in tables}
    policy = {k: v for k, v in meta.items() if k not in BOOKKEEPING}
    # Ignore only observation time, not native schedule identity/status changes.
    policy["heartbeat"] = {k: v for k, v in meta["heartbeat"].items() if k != "observedAt"}
    sources = {table: digest(value) for table, value in rows.items()}
    # SELECT data only: never load artifact BLOBs, inspect proofs or read files.
    for table, category in (("artifact_versions", "artifact_metadata"), ("observation_records", "recorded_observations")):
        coordinator.bounded_in(db, (table,))
        sources[category] = digest([list(row) for row in db.execute(f"SELECT id,data FROM {table} ORDER BY id")])
    legacy = []
    if kernel.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_claims'").fetchone():
        coordinator.bounded_in(kernel, ("legacy_claims",))
        legacy = [c for c in coordinator.store.rows(kernel, "legacy_claims")
                  if c["workspaceId"] == coordinator.bridge.workspace_id]
    sources["quarantined_ownership"] = digest(legacy)
    sources.update(policy=digest(policy), shared_admission=context["sharedStateHash"],
                   eligibility=digest({k: context[k] for k in
                       ("runHash", "runStatus", "blockers", "candidates", "workers", "budget")}))
    reasons = []
    if brain_control.stopped(meta): reasons.append("brain_stop")
    elif brain_control.control(meta).get("phase") == "resume_requested": reasons.append("resume_receipt")
    if meta.get("decisionListener", {}).get("enabled"): reasons.append("idle_listener_enabled")
    if meta.get("runner"): reasons.append("runner_owned")
    if any(c["status"] in ("queued", "processing") or c.get("needsBrainReceipt") for c in rows["commands"]):
        reasons.append("pending_receipts")
    if any(d["status"] in ("answered", "received") for d in rows["decisions"]):
        reasons.append("unresolved_answers")
    if any(c["status"] in ("needs_proposal", "needs_revision") for c in rows["continuations"]):
        reasons.append("follow_up_planning")
    if any(q["canCreate"] for q in context["candidates"]): reasons.append("eligible_work")
    # Check all retained phases, not just the current run. A missing local receipt
    # or worker row must never turn a retained shared owner into an empty inbox.
    allocation_rows = coordinator.store.rows(kernel, "allocations")
    all_allocations = {a["id"] for a in allocation_rows}
    allocations = {a["id"] for a in allocation_rows if a["spec"]["workspaceId"] == coordinator.bridge.workspace_id}
    claim_rows = coordinator.store.rows(kernel, "claims")
    claims = [c for c in claim_rows if c["allocationId"] in allocations]
    claim_ids = {c["id"] for c in claim_rows}
    worker_ids = {w["id"] for w in rows["workers"]}
    if (any(c["allocationId"] not in all_allocations for c in claim_rows) or
            any(r[0] not in claim_ids for r in kernel.execute("SELECT claim FROM resources")) or
            any(c["id"] not in worker_ids for c in claims)):
        reasons.append("unresolved_shared_ownership")
    if legacy or any(c["status"] != "settled" for c in claims) or any(
            not w.get("ownershipSettlementHash") and
            (w.get("dispatchAdmission") or w["status"] != "complete") for w in rows["workers"]):
        reasons.append("retained_ownership")
    not_created = set()
    for claim in claims:
        if claim.get("creationOutcome") == "not_created" and claim["id"] in worker_ids:
            from .creation_recovery import CreationRecovery
            worker, intent = coordinator.bridge.intent_in(db, claim["id"])
            _, terminal = CreationRecovery(coordinator.bridge).record_in(kernel, intent)
            require(terminal and worker.get("ownershipSettlementHash") == digest(terminal) and
                    worker["dispatchAdmission"].get("claimHash") == digest(claim) and not worker.get("threadId") and
                    runs.document(db, digest(terminal), CreationRecovery.kind) == terminal,
                    "Non-creation receipt requires reconciliation before quiet waiting")
            not_created.add(worker["id"])
    if any(w.get("ownershipSettlementHash") and not w.get("resultReviewHash") and w["id"] not in not_created
           for w in rows["workers"]):
        reasons.append("result_review_pending")
    return {"protocol": PROTOCOL, "sources": sources, "supervisionReasons": sorted(reasons)}


def validate(boundary):
    exact(boundary, {"protocol", "sources", "supervisionReasons"})
    require(boundary["protocol"] == PROTOCOL, "Unknown brain wait protocol")
    exact(boundary["sources"], CATEGORIES)
    for value in boundary["sources"].values(): sha(value)
    reasons = boundary["supervisionReasons"]
    require(isinstance(reasons, list) and all(isinstance(r, str) for r in reasons)
            and reasons == sorted(set(reasons)), "Invalid wait supervision record")


def state(coordinator, token, key):
    sha(key)
    with coordinator.bridge.locked(token) as (db, meta), coordinator.store.tx() as kernel:
        doc = coordinator.document_in(db, key)
        require(doc["request"]["choice"] == "wait", "A retained wait decision is required")
        require(coordinator.prior_in(db, doc["request"]["id"]) == doc, "Brain wait receipt changed")
        latest = coordinator.latest_in(db, meta)
        stopped = brain_control.stopped(meta)
        out = {"decisionHash": key, "recordedAt": doc["at"], "resumeEvent": doc["request"]["resumeEvent"],
               "state": "stopped" if stopped else "superseded", "changedCategories": [],
               "supervisionReasons": ["brain_stop"] if stopped else [],
               "quietEligible": False, "executionAuthorized": False, "nativeCallMade": False,
               "scheduleChangeAuthorized": False, "currentNativeActivity": "not_observed",
               "next": "follow_safe_stop" if stopped else "inspect_current_lifecycle"}
        if not latest or digest(latest) != key: return out
        if "waitBoundary" not in doc:
            return out if stopped else {**out, "state": "unbound", "next": "inspect_and_record_bound_wait"}
        boundary = doc["waitBoundary"]; validate(boundary)
        context = coordinator.context_in(db, meta, kernel)
        current = capture(coordinator, db, meta, kernel, context)
        changed = sorted(k for k in CATEGORIES if current["sources"][k] != boundary["sources"][k])
        reasons = current["supervisionReasons"]
        status = "stopped" if stopped else "supervision_required" if reasons else "changed" if changed else "unchanged"
        return {**out, "state": status, "changedCategories": changed, "supervisionReasons": reasons,
                "quietEligible": status == "unchanged",
                "next": "follow_safe_stop" if stopped else "end_turn_without_new_decision" if status == "unchanged"
                        else "inspect_current_lifecycle"}
