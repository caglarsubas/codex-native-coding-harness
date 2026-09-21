"""Explicit owner inspection of retained reports; no controller or mutation seams."""
import contextlib
import time

from . import missions, phase_checkpoints as phases
from .admission import exact, sha, timestamp
from .core import Refusal, digest, require

MAX_REPORTS = 128
INVALID = (Refusal, KeyError, TypeError, ValueError, RecursionError)
BOUNDARY = ("Saved local evidence only. Inspection does not establish phase acceptance, "
            "measure tokens, approve a release or resume work. Native activity is not inspected.")


def metadata_in(ledger, db, key):
    report = phases.document(db, key, phases.REPORT)
    require(report["workspaceId"] == missions.workspace(ledger), "Foreign report")
    receipt = phases.receipt_for(db, report)
    require(receipt.get("operation") == "phase_report" and receipt.get("reportHash") == key, "Report receipt changed")
    artifact_id = receipt["artifactId"]; sha(artifact_id)
    row = db.execute("SELECT data FROM artifact_versions WHERE id=? AND length(CAST(data AS BLOB))<=16000", (artifact_id,)).fetchone()
    require(row is not None, "Report artifact metadata missing")
    info = phases.json_object(row[0])
    require(info.get("id") == artifact_id == digest([info.get("key"), info.get("version"), info.get("sha256")]) and
            info.get("provenance") == phases.REPORT and info.get("phaseReportHash") == key, "Report artifact metadata changed")
    for field in ("retainedAt", "checkpointAt"): timestamp(report[field])
    require(type(info["version"]) is int and info["version"] > 0 and type(report["generation"]) is int and report["generation"] > 0,
            "Invalid report version")
    require(all(isinstance(value, str) and 0 < len(value) <= 2000 for value in (report["phaseId"], report["phase"]["title"])),
            "Invalid report title")
    return {"reportHash": key, "artifactId": artifact_id, "version": info["version"],
            "retainedAt": report["retainedAt"], "checkpointAt": report["checkpointAt"],
            "phaseId": report["phaseId"], "phaseTitle": report["phase"]["title"],
            "generation": report["generation"], "status": "not_inspected"}


def base(ledger, db):
    return {"workspaceId": missions.workspace(ledger), "workspaceRevision": ledger.get(db, "meta", 1)["revision"],
            "inspectedAt": time.time(), "executionAuthorized": False, "nativeCallMade": False, "boundary": BOUNDARY}


def history(ledger):
    """Metadata only. Full proof bytes are checked only for an explicit inspection."""
    with contextlib.closing(ledger.connect()) as db:
        db.execute("BEGIN")
        result = base(ledger, db)
        total = db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (phases.REPORT,)).fetchone()[0]
        latest = ledger.get(db, "meta", 1).get("phaseCheckpointReport")
        try:
            exact(latest, {"reportHash", "artifactId"}); sha(latest["reportHash"]); sha(latest["artifactId"])
        except INVALID: latest = None
        result.update(kind="history", total=total, reports=[], unavailable=0, latest=latest)
        if total > MAX_REPORTS:
            return {**result, "status": "history_limit", "limit": MAX_REPORTS}
        for row in db.execute("SELECT id FROM snapshots WHERE kind=? ORDER BY rowid", (phases.REPORT,)).fetchall():
            try: item = metadata_in(ledger, db, row[0])
            except INVALID:
                result["unavailable"] += 1
                continue  # No invented timestamps, versions or links for corrupt metadata.
            result["reports"].append(item)
        # Stable insertion-order tie break when two saves share one clock tick.
        result["reports"].sort(key=lambda r: r["retainedAt"])
        latest = result["latest"]
        result["latestAvailable"] = any(latest == {k: r[k] for k in ("reportHash", "artifactId")} for r in result["reports"])
        result["status"] = "available" if total else "empty"
        return result


def inspect(ledger, request):
    exact(request, {"reportHash", "artifactId"})
    sha(request["reportHash"]); sha(request["artifactId"])
    with contextlib.closing(ledger.connect()) as db:
        db.execute("BEGIN")
        result = {**base(ledger, db), **request, "kind": "report"}
        try:
            detail = phases.read_in(ledger, db, request["reportHash"], request["artifactId"])
            metadata = metadata_in(ledger, db, request["reportHash"])
        except INVALID:
            return {**result, "status": "unavailable", "contextStatus": "not_checked",
                    "detail": "The saved report or required retained evidence is missing, changed or invalid. No result is shown; restore evidence through the brain/operator before inspecting again."}
        if ledger.get(db, "meta", 1).get("phaseCheckpointReport") != request:
            context_status = "superseded"
        else:
            try:
                source, *_ = phases.context_in(ledger, db)
                context_status = "matches_recorded_checkpoint" if source == detail["report"]["source"] else "workspace_changed"
            except INVALID:
                context_status = "checkpoint_unavailable"
        return {**result, "status": "intact", "contextStatus": context_status,
                "version": metadata["version"], "report": detail["report"]}


def summary(result):
    """Closed projection: no free text, hashes, notes, proof bodies or local paths."""
    if not result: return {"status": "not_inspected", "executionAuthorized": False}
    out = {k: result[k] for k in ("kind", "status", "workspaceRevision", "inspectedAt", "executionAuthorized")}
    if result["kind"] == "history":
        out.update(total=result["total"], unavailable=result["unavailable"], latestAvailable=result.get("latestAvailable", False))
    else:
        out["contextStatus"] = result["contextStatus"]
        if result["status"] == "intact":
            report = result["report"]
            out.update(generation=report["generation"], version=result["version"], checkpointAt=report["checkpointAt"], retainedAt=report["retainedAt"])
            out["counts"] = {k: report["summary"][k] for k in ("declaredTasks", "recordedAcceptedResults", "recordedChangesRequired",
                            "unreviewedWorkers", "unfinishedDeclaredTasks", "pendingControlCount")}
            out.update(phaseAcceptance="not_established", measuredPhaseTokens=None)
    return out


def cached_summary(cached, revision):
    if cached is None: return summary(None)
    return {**cached, "historical": True,
            "workspaceChanged": cached["workspaceRevision"] != revision,
            "expired": not 0 <= time.time()-cached["inspectedAt"] <= 60,
            "boundary": BOUNDARY}
