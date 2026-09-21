"""Retained local phase reports and exact owner review; never execution authority."""
import contextlib
import copy
import hashlib
import json
import time

from . import missions, run_authority as runs, task_contracts
from .admission import exact, sha, timestamp
from .core import AXES, Refusal, canonical, digest, require
from .decisions import authorize_brain
from .observations import capture

REPORT = "phase_checkpoint_report"
REVIEW = "phase_checkpoint_review"
WITHDRAWAL = "phase_checkpoint_withdrawal"
REVIEW_FIELDS = {"reportHash", "artifactId", "missionHash", "reviewReceiptHash", "settingsPolicy", "expiresAt", "confirmed"}
BOUND = 256000
BOUNDARY = ("Recorded local claims, not phase acceptance or fresh native activity. "
            "Limits are not measured usage. Shared cumulative accounting and every "
            "admission/effect check remain required. Review never resumes or dispatches work.")


def json_object(raw):
    try: value = json.loads(raw)
    except (ValueError, TypeError, RecursionError): raise Refusal("Invalid checkpoint metadata") from None
    require(isinstance(value, dict), "Invalid checkpoint metadata")
    return value


def document(db, key, kind):
    value = task_contracts.document_in(db, key, kind, BOUND)
    require(value is not None, "Phase checkpoint record is missing, changed or oversized")
    return value


def retain(db, kind, value):
    raw = canonical(value)
    require(len(raw.encode()) <= BOUND, "Phase checkpoint record exceeds its bound")
    key = digest(value)
    db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?)", (key, kind, raw))
    return key


def artifact_bytes(db, key):
    sha(key)
    row = db.execute("SELECT CASE WHEN length(CAST(data AS BLOB))<=16000 THEN data END,"
                     "CASE WHEN length(content)<=8388608 THEN content END FROM artifact_versions WHERE id=?", (key,)).fetchone()
    require(row and row[0] is not None and isinstance(row[1], bytes), "Retained checkpoint artifact unavailable")
    info, raw = json_object(row[0]), row[1]
    require(info.get("id") == key == digest([info.get("key"), info.get("version"), info.get("sha256")]) and
            info.get("sha256") == hashlib.sha256(raw).hexdigest(), "Checkpoint artifact integrity changed")
    return info, raw


def rows_in(ledger, db, table):
    # Closed table names only. Refuse incomplete projections, never truncate them.
    require(table in ("workers", "queue", "repos", "commands"), "Invalid checkpoint source")
    require(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] <= 1000 and
            not db.execute(f"SELECT 1 FROM {table} WHERE length(CAST(data AS BLOB))>256000 LIMIT 1").fetchone(),
            "Checkpoint source exceeds its bound; explicit history migration required")
    return sorted(ledger.all(db, table), key=lambda r: r["id"])


def context_in(ledger, db):
    """Hash relevant local state without observing files, native tasks or tokens."""
    meta = ledger.get(db, "meta", 1); state = runs.current_in(ledger, db)
    control = meta.get("brainControl") or {}
    require(state and state["status"] == "checkpointed" and control.get("phase") == "parked" and
            control.get("desired") == "stopped" and meta["paused"] is True and
            state["checkpointHash"] == (control.get("checkpoint") or {}).get("documentHash") and
            state["stopCommandId"] == control.get("commandId"), "Exact parked run checkpoint required")
    grant = runs.document(db, state["runHash"], "run_authorization")
    require(grant["workspaceId"] == missions.workspace(ledger) and grant["brainId"] == meta["brainId"],
            "Checkpoint workspace or brain changed")
    checkpoint = document(db, state["checkpointHash"], "brain_checkpoint")
    require(checkpoint["commandId"] == state["stopCommandId"], "Checkpoint stop binding changed")
    for key in checkpoint["artifactIds"]: artifact_bytes(db, key)
    queue, workers = rows_in(ledger, db, "queue"), rows_in(ledger, db, "workers")
    commands = [c for c in rows_in(ledger, db, "commands") if c["status"] in ("queued", "processing") or c.get("needsBrainReceipt")]
    source = {"workspaceId": missions.workspace(ledger), "brainId": meta["brainId"],
        "runStateHash": digest(state), "checkpointHash": state["checkpointHash"],
        "workersHash": digest(workers), "queueHash": digest(queue), "repositoriesHash": digest(rows_in(ledger, db, "repos")),
        "pendingControlsHash": digest(commands), "pendingControlCount": len(commands), "runnerHash": digest(meta["runner"])}
    return source, grant, state, checkpoint, queue, workers


def review_record_in(db, key, workspace_id):
    from . import result_review
    record = runs.document(db, key, "result_review")
    result_review.validate(record["request"])
    intent = runs.document(db, record["intentHash"], "dispatch_intent")
    settlement = runs.document(db, record["request"]["settlementHash"], "ownership_settlement")
    require(intent["workspaceId"] == workspace_id and record["workerId"] == intent["workerId"] == settlement["workerId"] and
            settlement["intentHash"] == record["intentHash"], "Phase result source binding changed")
    result_review.history_in(db, key, intent, settlement)
    return record


def task_rows(db, grant, queue, workers):
    out, references = [], []
    for q in queue:
        owned = [w for w in workers if w["queueId"] == q["id"]]
        contracts, phase_owned = [], []
        for w in owned:
            pointer = w.get("dispatchAdmission")
            if pointer:
                intent = runs.document(db, pointer["intentHash"], "dispatch_intent")
                require(intent["workerId"] == w["id"] and intent["queueId"] == q["id"] and
                        intent["workspaceId"] == grant["workspaceId"], "Worker report binding changed")
                old = runs.document(db, intent["runHash"], "run_authorization")
                if old["phaseId"] == grant["phaseId"]:
                    phase_owned.append(w)
                    contracts.append(intent["contractHash"])
                    references.extend(((pointer["intentHash"], "dispatch_intent"), (intent["runHash"], "run_authorization")))
        if q.get("taskContract"): contracts.append(q["taskContract"]["hash"])
        phase_contracts = []
        for key in sorted(set(contracts)):
            contract = runs.document(db, key, "task_contract")
            require(contract["spec"]["queueId"] == q["id"], "Phase task contract queue binding changed")
            if contract["workspaceId"] == grant["workspaceId"] and contract["phaseId"] == grant["phaseId"]:
                phase_contracts.append(key); references.append((key, "task_contract"))
        if not phase_contracts: continue
        require(len(out) < 64, "Phase report task limit exceeded; no truncated report")
        worker_rows = []
        for w in phase_owned:
            review = None
            if w.get("resultReviewHash"):
                record = review_record_in(db, w["resultReviewHash"], grant["workspaceId"])
                require(record["workerId"] == w["id"], "Result report belongs to a different worker")
                references.append((w["resultReviewHash"], "result_review"))
                result = record["request"]["result"]
                review = {"hash": w["resultReviewHash"], "outcome": record["request"]["outcome"],
                          "recordedAt": record["at"], "commit": result["commit"],
                          "axes": {axis: result["evidence"][axis]["status"] for axis in AXES},
                          "criteria": [r["proof"]["status"] for r in result["criteria"]],
                          "preservation": result["preservation"]["status"]}
            worker_rows.append({"id": w["id"], "status": w["status"], "review": review,
                "settlementHash": w.get("ownershipSettlementHash"), "archived": w.get("archived") is True})
        out.append({"queueId": q["id"], "repository": q["repository"], "status": q["status"],
                    "held": q["held"], "contractHashes": phase_contracts, "workers": worker_rows})
    return out, sorted(set(references))


def markdown(report):
    # Free text is JSON-quoted: no model-authored HTML, links or executable controls.
    lines = ["# Phase checkpoint report", "", BOUNDARY, "", "```json", json.dumps({
        k: report[k] for k in ("workspaceId", "runHash", "phaseId", "generation", "checkpointHash",
            "checkpointAt", "checkpointArtifacts", "retainedAt", "phase", "stopReasons", "limits", "summary", "tasks", "note")}, indent=2, ensure_ascii=False, sort_keys=True), "```", ""]
    return "\n".join(lines).encode()


def report_in(ledger, db, key):
    report = document(db, key, REPORT)
    require(report["workspaceId"] == missions.workspace(ledger), "Foreign phase checkpoint report")
    for ref, kind in report["references"]:
        document(db, ref, kind)
        if kind == "result_review": review_record_in(db, ref, report["workspaceId"])
    checkpoint = document(db, report["checkpointHash"], "brain_checkpoint")
    for artifact_id in checkpoint["artifactIds"]: artifact_bytes(db, artifact_id)
    receipt = receipt_for(db, report)
    require(receipt.get("operation") == "phase_report" and receipt.get("reportHash") == key, "Phase report receipt changed")
    return report


def receipt_for(db, record):
    row = db.execute("SELECT data FROM snapshots WHERE id=? AND kind='run_request' AND length(CAST(data AS BLOB))<=32768", (record["requestKey"],)).fetchone()
    require(row is not None, "Checkpoint request receipt missing")
    lookup = json_object(row[0]); exact(lookup, {"fingerprint", "receiptHash"})
    require(lookup["fingerprint"] == record["fingerprint"], "Checkpoint request binding changed")
    return runs.document(db, lookup["receiptHash"], "run_receipt")


def prepare(ledger, token, request):
    with ledger.tx() as db:
        meta, key, fingerprint, prior = runs.request_in(ledger, db, request, "designated_brain", "phase_report",
            {"runHash", "checkpointHash", "note"}, token)
        if prior:
            read_in(ledger, db, prior["reportHash"], prior["artifactId"])
            return prior
        note = missions.text(request["note"], "Checkpoint report note")
        source, grant, state, checkpoint, queue, workers = context_in(ledger, db)
        require(request["runHash"] == state["runHash"] and request["checkpointHash"] == state["checkpointHash"],
                "Exact run and checkpoint required")
        mission = runs.document(db, grant["missionHash"], "mission_configuration")
        tasks, references = task_rows(db, grant, queue, workers)
        reviewed = [w for q in tasks for w in q["workers"] if w["review"]]
        report = {"kind": REPORT, "workspaceId": grant["workspaceId"], "runHash": state["runHash"],
            "generation": grant["generation"], "phaseId": grant["phaseId"], "checkpointHash": state["checkpointHash"],
            "checkpointAt": checkpoint["at"], "retainedAt": time.time(), "source": source, "requestKey": key, "fingerprint": fingerprint,
            "checkpointArtifacts": checkpoint["artifactIds"],
            "phase": mission["spec"]["phase"], "stopReasons": state["stopReasons"], "limits": grant["authority"],
            "tasks": tasks, "summary": {"declaredTasks": len(tasks), "recordedAcceptedResults": sum(w["review"]["outcome"] == "accepted" for w in reviewed),
                "recordedChangesRequired": sum(w["review"]["outcome"] == "changes_required" for w in reviewed),
                "unreviewedWorkers": sum(w["review"] is None for q in tasks for w in q["workers"]),
                "otherRetainedWorkers": len(workers)-sum(len(q["workers"]) for q in tasks),
                "unfinishedDeclaredTasks": sum(q["status"] != "complete" for q in tasks),
                "pendingControlCount": source["pendingControlCount"],
                "phaseAcceptance": "not_established", "measuredPhaseTokens": None, "usageStatus": "requires_shared_phase_usage_check"},
            "note": note, "references": sorted(set(references + [(state["runHash"], "run_authorization"),
                (grant["missionHash"], "mission_configuration")])), "executionAuthorized": False}
        report_hash = retain(db, REPORT, report)
        artifact = capture(db, "phase-checkpoint:" + state["runHash"], markdown(report), {
            "repository": grant["repositoryBindings"][0]["repository"], "name": "phase-checkpoint-report.md",
            "orderAt": report["retainedAt"], "provenance": REPORT, "phaseReportHash": report_hash,
            "references": [{"session": meta["brainId"], "at": report["retainedAt"], "runHash": state["runHash"]}]})
        meta["phaseCheckpointReport"] = {"reportHash": report_hash, "artifactId": artifact["id"]}
        ledger.put(db, "meta", 1, meta)
        return runs.receipt_in(ledger, db, key, fingerprint, "phase_report", reportHash=report_hash, artifactId=artifact["id"])


def read_in(ledger, db, report_hash, artifact_id):
    report = report_in(ledger, db, report_hash)
    info, raw = artifact_bytes(db, artifact_id)
    require(info.get("provenance") == REPORT and info.get("phaseReportHash") == report_hash and raw == markdown(report),
            "Phase report artifact binding changed")
    require(receipt_for(db, report).get("artifactId") == artifact_id, "Phase report artifact receipt changed")
    return {"reportHash": report_hash, "artifactId": artifact_id, "report": report,
            "historical": True, "executionAuthorized": False, "nativeCallMade": False, "boundary": BOUNDARY}


def read(ledger, token, request):
    exact(request, {"reportHash", "artifactId"}); sha(request["reportHash"]); sha(request["artifactId"])
    with contextlib.closing(ledger.connect()) as db:
        db.execute("BEGIN"); authorize_brain(ledger, db, token)
        return read_in(ledger, db, request["reportHash"], request["artifactId"])


def review(ledger, request, *, actor):
    """Trusted owner seam; the dashboard adapter authenticates signed confirmation."""
    with ledger.tx() as db:
        return review_in(ledger, db, request, actor=actor)


def validate_review_in(ledger, db, request):
    meta = ledger.get(db, "meta", 1)
    require(request["confirmed"] is True, "Explicit checkpoint review confirmation required")
    sha(request["reportHash"]); sha(request["artifactId"]); timestamp(request["expiresAt"])
    report = read_in(ledger, db, request["reportHash"], request["artifactId"])["report"]
    source, grant, state, *_ = context_in(ledger, db)
    require(meta.get("phaseCheckpointReport") == {"reportHash": request["reportHash"], "artifactId": request["artifactId"]} and
            report["source"] == source, "Phase checkpoint report is stale or superseded; prepare it again")
    current = runs.mission_source(ledger, db); spec, _ = task_contracts.reviewed_phase(current)
    m = current["mission"]
    require(request["missionHash"] == m["documentHash"] and request["reviewReceiptHash"] == m["receiptHash"], "Exact next reviewed mission required")
    require(spec["authority"]["approvalMode"] != "prepare_only", "Prepare-only mission cannot release run intent")
    if set(state["stopReasons"]) & runs.STOP_REASONS:
        require(m["documentHash"] != grant["missionHash"], "Brain stop boundary requires a newly reviewed mission or bounded correction scope")
    from .model_policy import policy_in
    policy_in(ledger, db, request["settingsPolicy"])
    require(time.time() < request["expiresAt"] <= time.time()+86400, "Review expiry must be within 24 hours")
    return source


def review_in(ledger, db, request, *, actor):
    require(actor == "dashboard_owner", "Only the authenticated owner may review a phase checkpoint")
    request = copy.deepcopy(request)
    _, key, fingerprint, prior = runs.request_in(ledger, db, request, actor, "phase_review", REVIEW_FIELDS)
    if prior:
        release = owner_review_in(ledger, db, prior["checkpointReviewHash"])
        read_in(ledger, db, release["request"]["reportHash"], release["request"]["artifactId"])
        return prior
    source = validate_review_in(ledger, db, request)
    record = {"kind": REVIEW, "workspaceId": missions.workspace(ledger), "actor": actor, "request": request,
              "source": source, "at": time.time(), "requestKey": key, "fingerprint": fingerprint, "executionAuthorized": False}
    review_hash = retain(db, REVIEW, record)
    return runs.receipt_in(ledger, db, key, fingerprint, "phase_review", checkpointReviewHash=review_hash)


def owner_review_in(ledger, db, key):
    record = document(db, key, REVIEW)
    require(record["workspaceId"] == missions.workspace(ledger) and record["actor"] == "dashboard_owner", "Foreign checkpoint review")
    receipt = receipt_for(db, record)
    require(receipt.get("operation") == "phase_review" and receipt.get("checkpointReviewHash") == key, "Checkpoint review receipt changed")
    return record


def withdrawals_in(ledger, db):
    """Durable denial, not a new phase or retroactive stop of an authorized run."""
    mapping = ledger.get(db, "meta", 1).get("phaseReviewWithdrawals", {})
    require(isinstance(mapping, dict) and len(mapping) <= 128, "Invalid checkpoint withdrawal inventory")
    count = db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (WITHDRAWAL,)).fetchone()[0]
    require(count == len(mapping), "Checkpoint withdrawal history changed; explicit recovery required")
    for review_hash, key in mapping.items():
        sha(review_hash); sha(key)
        record = document(db, key, WITHDRAWAL)
        require(record["workspaceId"] == missions.workspace(ledger) and record["actor"] == "dashboard_owner" and
                record["checkpointReviewHash"] == review_hash, "Checkpoint withdrawal identity changed")
        receipt = receipt_for(db, record)
        require(receipt.get("operation") == "phase_withdraw" and receipt.get("withdrawalHash") == key and
                receipt.get("checkpointReviewHash") == review_hash, "Checkpoint withdrawal receipt changed")
    return mapping


def withdraw(ledger, request, *, actor):
    with ledger.tx() as db:
        return withdraw_in(ledger, db, request, actor=actor)


def withdraw_in(ledger, db, request, *, actor):
    require(actor == "dashboard_owner", "Only the owner may withdraw checkpoint review")
    request = copy.deepcopy(request)
    meta, key, fp, prior = runs.request_in(ledger, db, request, actor, "phase_withdraw", {"checkpointReviewHash", "reason", "confirmed"})
    mapping = withdrawals_in(ledger, db)
    if prior:
        require(mapping.get(request["checkpointReviewHash"]) == prior["withdrawalHash"], "Withdrawal projection changed")
        return prior
    require(request["confirmed"] is True, "Explicit withdrawal confirmation required")
    review_hash = sha(request["checkpointReviewHash"]); missions.text(request["reason"], "Withdrawal reason")
    owner_review_in(ledger, db, review_hash)
    require(review_hash not in mapping and len(mapping) < 128, "Review already withdrawn or history requires maintenance")
    record = {"kind": WITHDRAWAL, "workspaceId": missions.workspace(ledger), "actor": actor,
              "checkpointReviewHash": review_hash, "reason": request["reason"], "at": time.time(),
              "requestKey": key, "fingerprint": fp, "executionAuthorized": False}
    value = retain(db, WITHDRAWAL, record)
    meta["phaseReviewWithdrawals"] = {**mapping, review_hash: value}; ledger.put(db, "meta", 1, meta)
    return runs.receipt_in(ledger, db, key, fp, "phase_withdraw", checkpointReviewHash=review_hash, withdrawalHash=value)


def require_release_in(ledger, db, request):
    """Same transaction as the new run grant. An old review cannot re-arm a run."""
    review_hash = request.get("checkpointReviewHash")
    record = owner_review_in(ledger, db, review_hash)
    require(review_hash not in withdrawals_in(ledger, db), "Checkpoint review withdrawn; new owner review required")
    reviewed = record["request"]
    source, *_ = context_in(ledger, db)
    meta = ledger.get(db, "meta", 1)
    report = read_in(ledger, db, reviewed["reportHash"], reviewed["artifactId"])["report"]
    require(record["source"] == report["source"] == source and meta.get("phaseCheckpointReport") ==
            {"reportHash": reviewed["reportHash"], "artifactId": reviewed["artifactId"]}, "Checkpoint review is stale or superseded")
    require(all(request[field] == reviewed[field] for field in ("missionHash", "reviewReceiptHash", "settingsPolicy", "expiresAt")) and
            request["checkpointHash"] == source["checkpointHash"], "Release must match the exact owner-reviewed next scope, settings and expiry")
