"""Explicit, read-only mission/packet/admission preflight. Never execution authority."""
import contextlib
import fnmatch
import json
import sqlite3
import time
from collections import Counter

from . import missions, reconciliation
from .core import Refusal, digest, eligibility_issues, require, safe_relative, validate_seed

MAX_PACKETS = 100
MAX_SEED_BYTES = 512_000


def contained_path(candidate, scopes):
    """Conservative containment for existing fnmatch paths; never infer glob subsets."""
    def valid(path):
        try:
            safe_relative(path)
            return len(path) <= 1000 and not any(p in ("", ".", "..") for p in path.split("/"))
        except ValueError:
            return False
    if not valid(candidate): return False
    literal = not any(c in candidate for c in "*?[")
    for scope in scopes:
        if not valid(scope): continue
        if candidate == scope or (literal and fnmatch.fnmatchcase(candidate, scope)): return True
        # Only a literal directory prefix with unrestricted recursive suffix is
        # safely comparable without a full glob-language inclusion proof.
        if scope.endswith("/**") and not any(c in scope[:-3] for c in "*?[") and candidate.startswith(scope[:-2]):
            return True
    return False


def selected_source(ledger):
    """One workspace read transaction; no native, filesystem or Git inspection."""
    wid = missions.workspace(ledger)
    with contextlib.closing(ledger.connect()) as db:
        db.execute("BEGIN")
        meta = ledger.get(db, "meta", 1)
        mission = missions.state_in(ledger, db)
        repos = sorted(ledger.all(db, "repos"), key=lambda r: r["id"])
        workers = sorted(ledger.all(db, "workers"), key=lambda w: w["id"])
        queue = sorted(ledger.all(db, "queue"), key=lambda q: q["id"])
        candidates = [q for q in queue if q["status"] in ("proposed", "approved")]
        seeds = {}
        for q in candidates[:MAX_PACKETS]:
            row = db.execute("SELECT data FROM snapshots WHERE id=? AND length(CAST(data AS BLOB))<=?",
                             (q["seedHash"], MAX_SEED_BYTES)).fetchone()
            try: seeds[q["id"]] = json.loads(row[0]) if row else None
            except ValueError: seeds[q["id"]] = None
        receipt = None
        if mission.get("receiptHash"):
            row = db.execute("SELECT data FROM snapshots WHERE id=?", (mission["receiptHash"],)).fetchone()
            if row: receipt = json.loads(row[0])
        # All binding inputs stay private. Only the digest and narrow projections
        # leave this module; never return raw repository paths or controller tokens.
        source_hash = digest({"meta": meta, "mission": mission, "receipt": receipt,
                              "repos": repos, "queue": queue, "workers": workers, "seeds": seeds})
    return {"workspaceId": wid, "meta": meta, "mission": mission, "receipt": receipt,
            "repos": repos, "workers": workers, "queue": candidates[:MAX_PACKETS], "seeds": seeds,
            "candidateCount": len(candidates), "sourceHash": source_hash}


def assess(source, platform, now):
    """Pure diagnostic projection. A pass is one local check, never activation."""
    meta, mission = source["meta"], source["mission"]
    checks = []
    def check(code, group, ok, detail, next_action, view, owner="owner", status=None):
        checks.append({"code": code, "group": group, "status": status or ("satisfied" if ok else "blocked"),
                       "detail": detail, "nextAction": next_action, "view": view, "owner": owner})
    doc = mission["document"]
    valid = bool(doc) and digest(doc) == mission["documentHash"]
    if valid:
        try:
            spec, bindings = missions.validate(doc["spec"], source["repos"])
            valid = spec == doc["spec"] and bindings == doc["repositoryBindings"] and not mission["bindingIssues"]
        except (ValueError, TypeError, KeyError): valid = False
    check("mission_binding", "setup", valid, "Mission hash, identity and repository policies match." if valid else "The mission must match this workspace, brain and current repository policies.",
          "Save a current mission version with explicit scope and limits.", "mission")
    receipt = source["receipt"] or {}
    reviewed = valid and mission["effectiveStatus"] == "reviewed" and digest(receipt) == mission.get("receiptHash") and \
        receipt.get("operation") == "review" and receipt.get("actor") == "dashboard_owner" and \
        receipt.get("documentHash") == mission["documentHash"] and receipt.get("revision") == mission["revision"]
    check("owner_review", "setup", reviewed, "The exact current owner review is retained; it is not execution authority." if reviewed else "Only the exact current owner-review receipt counts; old reviews grant no run authority.",
          "Review the current mission configuration in Mission & authority.", "mission")
    spec = doc["spec"] if valid else None
    phase = spec["phase"] if spec else None
    limits = spec["authority"] if spec else None
    check("brain_identity", "setup", bool(meta.get("brainId")), "A designated brain is recorded; activity is not observed by this check." if meta.get("brainId") else "A designated brain must be configured.",
          "Connect the intended existing brain through workspace setup.", "readiness")
    check("execution_mode", "setup", bool(limits) and limits["approvalMode"] != "prepare_only",
          "Configured mode: " + limits["approvalMode"] + ". This mode is not activated." if limits else "No approval mode is configured.", "Choose and review the intended approval mode if development is desired.", "mission")
    scope_ids = {r["repository"] for r in phase["scope"]} if phase else set()
    scoped_repos = [r for r in source["repos"] if r["id"] in scope_ids]
    check("project_mappings", "setup", bool(scope_ids) and all(r.get("projectId") for r in scoped_repos),
          "Every scoped repository needs a recorded native project mapping; native validity is checked separately.",
          "Inspect repository registration and native mappings.", "readiness", "brain_operator")
    control = meta.get("brainControl") or {}
    stopping = control.get("desired") == "stopped" and control.get("phase") != "parked"
    check("pause_checkpoint", "evidence", not stopping, "An unfinished workspace Pause must reach its safe checkpoint first." if stopping else "No unfinished Pause is recorded; this is not native inactivity evidence.",
          "Inspect Pause progress; preserve worker and runner ownership.", "overview", "brain_operator")
    check("controller_idle", "evidence", not meta.get("controller"), "An owned controller means coordination is still recorded; age does not release it." if meta.get("controller") else "No controller owner is recorded; this does not prove the native brain is idle.",
          "Let the current bounded cycle finish or reconcile its exact owner.", "workers", "brain_operator")
    evaluation = platform.get("currentEvaluation") or {}
    consistent = platform.get("sourceMatchesReview") is True and evaluation.get("evidenceConsistent") is True and \
        evaluation.get("status") == "consistent" and not evaluation.get("issues") and bool(platform.get("baselineRecordHash")) and \
        type(evaluation.get("validUntil")) in (int, float) and evaluation["validUntil"] >= now
    check("platform_baseline", "evidence", consistent,
          "Platform inventory, resource mappings, account headroom and cumulative usage need a fresh, consistent retained review.",
          "Use the documented platform reconciliation procedure; do not reset owners or assume missing usage is zero.",
          "readiness", "brain_operator")
    check("packet_coverage", "evidence", source["candidateCount"] <= MAX_PACKETS,
          "This inspection covers at most 100 prepared packets; omitted packets are not assessed.",
          "Reduce or explicitly partition the candidate set before activation integration.", "queue", "brain_operator")
    packets = [assess_packet(q, source, phase, now) for q in source["queue"]]
    for code, detail, action, view in (
        ("run_activation", "Owner-bound run generations and effect/continuation fences are not implemented.", "Implement exact run activation and recovery without reusing configuration review as permission.", "mission"),
        ("phase_release", "Delegated packet authorization and mandatory phase release are not implemented.", "Implement phase-scoped approval and owner-bound checkpoint release.", "mission"),
        ("native_admission", "Capacity/token reservations and reconciled legacy ownership are not connected to native effects.", "Integrate transactional claims, cumulative usage, ownership recovery and native receipts.", "workers"),
        ("task_policy", "Version-bound operation declarations and requested/applied/observed model, effort and speed policies are not implemented.", "Bind task effects and supported execution settings to the reviewed phase before launch.", "queue"),
        ("native_pilot", "A real supervised two-workspace Play/Pause pilot has not been accepted by this feature.", "Qualify live behavior only after the preceding controls are implemented and separately authorized.", "readiness")):
        check(code, "implementation", False, detail, action, view, "platform_development", "not_implemented")
    candidate = None
    if reviewed:
        candidate = {"kind": "diagnostic_run_binding", "workspaceId": source["workspaceId"], "brainId": meta["brainId"],
                     "missionHash": mission["documentHash"], "reviewReceiptHash": mission["receiptHash"],
                     "missionRevision": mission["revision"], "phaseId": phase["id"],
                     "scopeHash": digest(phase["scope"]), "repositoryBindingsHash": digest(doc["repositoryBindings"]),
                     "authorityHash": digest(limits), "baselineRecordHash": platform.get("baselineRecordHash"),
                     "platformReviewHash": (platform.get("receipt") or {}).get("recordHash"),
                     "workspaceSourceHash": source["sourceHash"]}
    return {"schemaVersion": 1, "workspaceId": source["workspaceId"], "generatedAt": now,
            "workspaceRevision": meta["revision"], "workspaceSourceHash": source["sourceHash"],
            "status": "blocked", "executionAuthorized": False, "activationAvailable": False,
            "atomicReservation": False, "nativeStateCollected": False, "ownershipReleased": False,
            "candidate": candidate, "candidateHash": digest(candidate) if candidate else None,
            "mission": {"version": mission["version"], "status": mission["effectiveStatus"],
                        "phaseTitle": phase["title"] if phase else None, "limits": limits,
                        "checkpoint": phase["checkpoint"] if phase else None},
            "checks": checks, "packets": packets,
            "coverage": {"candidatePackets": source["candidateCount"], "inspectedPackets": len(packets),
                         "omittedPackets": source["candidateCount"] - len(packets)},
            "platformEvidence": {"reviewVersion": platform.get("version"), "consistentAtInspection": consistent,
                "evidenceValidUntil": evaluation.get("validUntil"),
                "baselineRetained": bool(platform.get("baselineRecordHash")),
                "issueCounts": dict(Counter(str(i.get("code", "unknown"))[:100] for i in evaluation.get("issues", []))),
                "trustBoundary": "caller_supplied_external_evidence_not_native_attestation"},
            "boundary": "Read-only diagnostic, not approval, a run, reserved capacity or a token allowance. Evidence may change immediately; inspect again before any future activation."}


def assess_packet(q, source, phase, now):
    result = {k: q[k] for k in ("id", "repository", "packetId", "seedHash", "packetDigest", "status", "held")}
    issues = []
    seed = source["seeds"].get(q["id"])
    repo = next((r for r in source["repos"] if r["id"] == q["repository"]), None)
    try:
        require(seed is not None and digest(seed) == q["seedHash"], "Seed integrity")
        validate_seed(seed)
        require(seed["repository"] == q["repository"] and seed["packetId"] == q["packetId"] and
                seed["packetDigest"] == q["packetDigest"] and repo and seed["policyProfile"] == repo["policyProfile"], "Seed binding")
        require(len(seed["allowedPaths"]) <= 80, "Path count")
    except (ValueError, TypeError, KeyError):
        return {**result, "pathScope": "not_assessed", "legacyEligibility": "not_assessed", "executionAuthorized": False,
                "issues": [{"code": "seed_integrity", "detail": "Seed is missing, oversized, invalid or no longer bound to this packet and policy."}]}
    row = next((r for r in phase["scope"] if r["repository"] == q["repository"]), None) if phase else None
    covered = bool(row) and all(contained_path(p, row["allowedPaths"]) for p in seed["allowedPaths"])
    if not covered: issues.append({"code": "phase_scope", "detail": "Packet paths are outside the phase, ambiguous, or cannot be conservatively proven contained."})
    try: legacy = eligibility_issues(q, repo, seed, source["workers"], now)
    except (ValueError, TypeError, KeyError, AttributeError):
        legacy = [{"code": "invalid_record", "detail": "Recorded packet preflight or worker evidence is invalid; reconcile it explicitly."}]
    issues.extend({"code": "legacy_" + i["code"], "detail": i["detail"]} for i in legacy)
    issues.append({"code": "operation_contract_missing", "detail": "The v1 seed does not bind requested operations/settings to a phase; path containment alone is not permission."})
    return {**result, "pathScope": "contained" if covered else "not_proven", "legacyEligibility": "recorded_checks_satisfied" if not legacy else "blocked",
            "executionAuthorized": False, "issues": issues}


def inspect(registry, ledger):
    try: return _inspect(registry, ledger)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        raise Refusal("Run inspection is unavailable: verify workspace identity and retained records. No activation or state change occurred.") from None


def _inspect(registry, ledger):
    require(registry.root_for(missions.workspace(ledger)) == ledger.root, "Workspace does not belong to this platform")
    source = selected_source(ledger)
    try: platform = reconciliation.status(registry)
    except (OSError, ValueError, KeyError, sqlite3.Error):
        platform = {"currentEvaluation": {"issues": [{"code": "platform_source_unavailable"}]}}
    result = assess(source, platform, time.time())
    if selected_source(ledger)["sourceHash"] != source["sourceHash"]:
        result["checks"].append({"code": "workspace_changed", "group": "evidence", "status": "blocked", "owner": "brain_operator",
            "detail": "Workspace state changed during this non-atomic inspection.", "nextAction": "Inspect again; do not use this candidate binding.", "view": "runReadiness"})
        result["candidate"] = result["candidateHash"] = None
    result["reportHash"] = digest(result)
    return result


def assistant_summary(report):
    if not report: return {"status": "not_inspected", "executionAuthorized": False}
    blockers = [c for c in report["checks"] if c["status"] != "satisfied"]
    return {"status": "historical_inspection", "generatedAt": report["generatedAt"], "workspaceRevision": report["workspaceRevision"],
            "executionAuthorized": False, "activationAvailable": False, "blockerCount": len(blockers),
            "blockers": [{k: c[k] for k in ("code", "group", "owner", "view")} for c in blockers[:16]],
            "coverage": report["coverage"]}
