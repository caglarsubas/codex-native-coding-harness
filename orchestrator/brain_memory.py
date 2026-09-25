"""Compact durable brain memory and bounded, phase-attributed local telemetry.

No native transport, transcript retention, provider billing or automatic rotation.
"""
import json
from pathlib import Path
import time

from .activity import candidates, open_regular
from .core import Refusal, canonical, digest, require
from .observations import TOKENS, config, stamp, token_vector

MAX_BYTES = 128 * 1024 * 1024
MAX_LINE = 16 * 1024 * 1024
FRESH_SECONDS = 120


def scope(run):
    return digest({"id": run["id"], "brain": run["brainId"], "start": run["startedAt"],
                   "brainSegments": run.get("brainSegments"),
                   "tasks": [(t["id"], t.get("threadId"), t.get("effectIssued"), t["status"])
                             for t in run["tasks"]], "status": run["status"],
                   "checkpoint": run.get("checkpoint")})


def session_usage(paths, identity, start, end, brain=False):
    events, gaps, session_starts = {}, [], []
    for path in paths:
        with open_regular(path) as stream:
            header_line = stream.readline(MAX_LINE + 1)
            require(len(header_line) <= MAX_LINE, "Log header exceeds telemetry bound")
            header = json.loads(header_line)
            require(header.get("type") == "session_meta" and
                    header.get("payload", {}).get("id") == identity, "Log identity mismatch")
            require(not header["payload"].get("forked_from_id"), "Fork usage requires explicit attribution")
            observed_start = stamp(header.get("timestamp"))
            if observed_start is not None:
                session_starts.append(observed_start)
            consumed = len(header_line)
            while True:
                line = stream.readline(MAX_LINE + 1)
                if not line:
                    break
                consumed += len(line)
                require(len(line) <= MAX_LINE and consumed <= MAX_BYTES, "Telemetry read bound exceeded")
                try:
                    row = json.loads(line)
                except ValueError:
                    gaps.append("incomplete_or_malformed_record")
                    continue
                payload = row.get("payload", {})
                if row.get("type") != "event_msg" or payload.get("type") != "token_count":
                    continue
                info = payload.get("info") or {}
                if not info:
                    continue
                at = stamp(row.get("timestamp"))
                total, last = token_vector(info.get("total_token_usage")), token_vector(info.get("last_token_usage"))
                if at is None or total is None or last is None:
                    gaps.append("invalid_token_record")
                    continue
                if at <= end:
                    # Copied archive/continuation observations do not add usage twice.
                    events[(at, canonical(total))] = (at, total, last)
    ordered = sorted(events.values(), key=lambda e: (e[0], e[1]["total_tokens"]))
    require(ordered, "No token samples for registered task")
    for previous, current in zip(ordered, ordered[1:]):
        if any(current[1][k] < previous[1][k] for k in TOKENS):
            gaps.append("counter_reset_or_regression")
    zero = dict.fromkeys(TOKENS, 0)
    if brain:
        before = [e for e in ordered if e[0] < start]
        if before:
            baseline = before[-1][1]
        else:
            require(session_starts and min(session_starts) >= start and ordered[0][1] == ordered[0][2],
                    "Brain baseline missing; lifetime total cannot be charged to this phase")
            baseline = zero
    else:
        require(ordered[0][1] == ordered[0][2], "Worker log prefix missing")
        baseline = zero
    selected = [e for e in ordered if e[0] >= start] if brain else ordered
    require(selected, "No token sample inside the measured interval")
    last = selected[-1]
    values = {k: max(0, last[1][k] - baseline[k]) for k in TOKENS}
    unique = {canonical(e[1]) for e in selected}
    return {"sessionId": identity, "tokens": values, "sampleAt": last[0],
            "calls": len(unique), "lastInputTokens": last[2]["input_tokens"],
            "gaps": sorted(set(gaps))}


def collect_closeout(ledger, run):
    """Observe registered sessions after a terminal checkpoint, without rewriting phase totals."""
    checkpoint = run.get("checkpoint")
    if not checkpoint or run["status"] not in ("completed", "blocked"):
        return None
    home = config(ledger).get("codexHome")
    at, now = checkpoint["at"], time.time()
    identities = [segment["id"] for segment in run.get("brainSegments", [])
                  if segment.get("end") is None or segment["end"] > at]
    if not identities:
        identities = [run["brainId"]]
    identities.extend(task["threadId"] for task in run["tasks"] if task.get("threadId"))
    records, gaps = [], []
    try:
        require(home and Path(home).is_absolute() and len(identities) <= 32
                and len(set(identities)) == len(identities), "Closeout log discovery unavailable")
        paths = candidates(Path(home), identities)
        for identity in identities:
            try:
                record = session_usage([path for path in paths if identity in path.name], identity, at, now, brain=True)
                records.append(record)
                gaps.extend(record["gaps"])
            except (OSError, ValueError, Refusal, TypeError, KeyError):
                gaps.append("closeout_baseline_or_session_unavailable:" + identity)
    except (OSError, ValueError, Refusal, TypeError):
        gaps.append("closeout_log_discovery_unavailable")
    totals = {key: sum(record["tokens"][key] for record in records) for key in TOKENS}
    return {"runId": run["id"], "checkpointAt": at, "collectedAt": now,
            "records": records, "tokens": totals, "gaps": sorted(set(gaps)),
            "coverage": "gapped" if gaps else "observed_local",
            "boundary": "Post-checkpoint local closeout, separately observed; not phase usage or provider billing"}


def collect(ledger, run):
    """Explicit collection only. Existing configured local log roots; exact IDs."""
    home = config(ledger).get("codexHome")
    records, gaps = [], []
    segments = run.get("brainSegments") or [{"id": run["brainId"], "start": run["startedAt"], "end": None}]
    wanted = [(item["id"], True, item["start"], item["end"]) for item in segments]
    for task in run["tasks"]:
        if task.get("threadId"):
            wanted.append((task["threadId"], False, run["startedAt"], None))
        elif task.get("effectIssued"):
            gaps.append("unresolved_native_identity")
    now = time.time()
    # Completed runs remain historical; never attribute a later brain turn to them.
    end = (run.get("checkpoint") or {}).get("at", now) if run["status"] in ("completed", "blocked") else now
    try:
        require(home and Path(home).is_absolute(), "Configured Codex log root unavailable")
        require(len(wanted) <= 32 and len({w[0] for w in wanted}) == len(wanted), "Ambiguous or oversized session set")
        paths = candidates(Path(home), [w[0] for w in wanted])
        for identity, is_brain, start, segment_end in wanted:
            selected = [p for p in paths if identity in p.name]
            try:
                result = session_usage(selected, identity, start, min(end, segment_end) if segment_end else end, is_brain)
                result["role"] = "brain" if is_brain else "worker"
                records.append(result)
                gaps.extend(result["gaps"])
            except (OSError, ValueError, Refusal, TypeError, KeyError):
                gaps.append("session_usage_unavailable:" + identity)
    except (OSError, ValueError, Refusal, TypeError):
        gaps.append("configured_log_discovery_unavailable")
    totals = {k: sum(r["tokens"][k] for r in records) for k in TOKENS}
    return {"scopeHash": scope(run), "runId": run["id"], "collectedAt": now,
            "through": end, "records": records, "tokens": totals, "gaps": sorted(set(gaps)),
            "coverage": "gapped" if gaps else "observed_local",
            "boundary": "Local registered-session telemetry, not billing, full descendants or a hard cap. Cached input is included; reasoning is already in output. Completed-run totals end at the saved checkpoint and exclude later closeout."}


def blockers(run):
    if not run.get("usageGuardVersion"):
        return []  # Existing runs are not silently enrolled on source upgrade.
    report = run.get("usageReport")
    if not report or report["scopeHash"] != scope(run):
        return ["Measure exact run usage before another effect"]
    if time.time() - report["collectedAt"] > FRESH_SECONDS:
        return ["Usage observation expired; measure before another effect"]
    problems = []
    if report["gaps"]:
        problems.append("Usage coverage has gaps; checkpoint for reconciliation")
    known = max(report["tokens"]["total_tokens"], run.get("usageHighWater", 0))
    if known + run["limits"]["checkpointReserveTokens"] >= run["limits"]["tokenBudget"]:
        problems.append("Observed phase usage reached its checkpoint budget")
    return problems


def refresh(ledger, run_id, request_id=None):
    """Optimistic snapshot; collection cannot silently follow a switched run."""
    from .standard import read_db, save, PROTOCOL
    receipt_key = digest({"kind": "standard_usage_request", "id": request_id, "runId": run_id}) if request_id else None
    with read_db(ledger.db) as db:
        if receipt_key:
            receipt = db.execute("SELECT data FROM snapshots WHERE id=? AND kind='standard_usage_request'", (receipt_key,)).fetchone()
            if receipt:
                return json.loads(receipt[0])
        meta = ledger.get(db, "meta", 1)
        run = meta.get("standardRun")
        require(run and run["id"] == run_id and run["protocol"] == PROTOCOL, "Exact standard run required")
        require(all(r["policyProfile"] == "standard" for r in ledger.all(db, "repos")), "Harness telemetry is separate")
        captured = digest(run)
    report = collect(ledger, run)
    closeout = collect_closeout(ledger, run)
    with ledger.tx() as db:
        if receipt_key:
            receipt = db.execute("SELECT data FROM snapshots WHERE id=? AND kind='standard_usage_request'", (receipt_key,)).fetchone()
            if receipt:
                return json.loads(receipt[0])
        meta = ledger.get(db, "meta", 1); current = meta.get("standardRun")
        require(current and digest(current) == captured, "Run changed during measurement; refresh explicitly")
        key = digest(report)
        db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?)", (key, "standard_usage", canonical(report)))
        if closeout is not None:
            db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?)",
                       (digest(closeout), "standard_closeout_usage", canonical(closeout)))
            current["closeoutReport"] = closeout
            current["closeoutHighWater"] = max(current.get("closeoutHighWater", 0),
                                               closeout["tokens"]["total_tokens"])
        current["usageReport"] = report
        current["usageHighWater"] = max(current.get("usageHighWater", 0), report["tokens"]["total_tokens"])
        # Retain per-session high water; missing/regressed telemetry never refunds usage.
        brain_total = sum(r["tokens"]["total_tokens"] for r in report["records"] if r["role"] == "brain")
        if any(r["role"] == "brain" for r in report["records"]):
            current["brainObservedTokens"] = max(current["brainObservedTokens"], brain_total)
            current["brainUsageCoverage"] = "observed_partial"
        for record in report["records"]:
            count = record["tokens"]["total_tokens"]
            if record["role"] == "brain":
                continue
            else:
                task = next(t for t in current["tasks"] if t.get("threadId") == record["sessionId"])
                task["observedTokens"] = max(task.get("observedTokens") or 0, count)
        save(ledger, db, meta, current, "usage_refresh")
        result = {"documentHash": key, **report, "closeout": closeout}
        if receipt_key:
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (receipt_key, "standard_usage_request", canonical(result)))
    return result


def capsule(ledger, db, run, note):
    """Inert memory with exact evidence pointers, not a transcript or run grant."""
    require(isinstance(note, str) and 0 < len(note) <= 4000, "Bounded continuation note required")
    doc = {"kind": "brain_memory_v1", "runId": run["id"], "brainId": run["brainId"],
           "phaseId": run["phaseId"], "missionHash": run["missionHash"], "reviewHash": run["reviewHash"],
           "status": run["status"], "limits": run["limits"], "checkpoint": run.get("checkpoint"),
           "usageHighWater": run.get("usageHighWater"), "usageCoverage": (run.get("usageReport") or {}).get("coverage", "unknown"),
           "tasks": [{k: t.get(k) for k in ("id", "title", "threadId", "status", "seedHash", "result")}
                     for t in run["tasks"]],
           "merges": [{k: m.get(k) for k in ("requestId", "status", "bindingHash")} for m in run.get("merges", [])],
           "note": note, "at": time.time(),
           "boundary": "Memory only. Verify current ledger, source and native state. No copied controller, credential, approval, resume, budget reset or permission to replace the designated brain."}
    require(len(canonical(doc).encode()) <= 32000, "Brain memory too large; retain smaller evidence pointers")
    key = digest(doc)
    db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, "brain_memory", canonical(doc)))
    run["memoryHash"] = key
    return key
