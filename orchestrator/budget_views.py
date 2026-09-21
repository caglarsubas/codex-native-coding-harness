"""Explicit bounded accounting inspection, never admission or native telemetry."""
import contextlib
import json
import os
import sqlite3
import time

from . import admission, native_limits, phase_usage
from .core import Refusal, canonical, digest, require
from .workspaces import identity, private_path

MAX_ROWS, MAX_BYTES, MAX_PHASES = 4096, 4_000_000, 128
INVALID = (Refusal, OSError, sqlite3.Error, KeyError, ValueError, TypeError, RecursionError)
BOUNDARY = ("Recorded accounting, not live telemetry, a bill or permission to execute. "
            "Reservations may overlap observed usage until settlement is incorporated. "
            "Account windows are shared; phase allowances are separate, not additive wallets.")


def file_identity(path):
    private_path(path.parent, existing=True)
    require(path.is_file() and not path.is_symlink(), "Private accounting database required")
    stat = path.stat()
    require(stat.st_uid == os.getuid() and stat.st_nlink == 1 and stat.st_mode & 0o077 == 0, "Private regular database required")
    return stat.st_dev, stat.st_ino


@contextlib.contextmanager
def readonly(path):
    before = file_identity(path)
    with contextlib.closing(sqlite3.connect(path.as_uri()+"?mode=ro", uri=True, timeout=1)) as db:
        db.execute("PRAGMA query_only=ON"); db.execute("PRAGMA trusted_schema=OFF")
        deadline = time.monotonic()+5
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        db.execute("BEGIN")
        yield db
        require(before == file_identity(path), "Database identity changed during inspection")


def objects(db, table, where="", params=()):
    require(table in ("meta", "allocations", "claims", "snapshots"), "Unsupported accounting table")
    count, size = db.execute(f"SELECT count(*),coalesce(sum(length(CAST(data AS BLOB))),0) FROM {table} {where}", params).fetchone()
    require(count <= MAX_ROWS and size <= MAX_BYTES, "Accounting inspection bound exceeded")
    rows = db.execute(f"SELECT id,data FROM {table} {where} ORDER BY id", params).fetchall()
    result = []
    for key, raw in rows:
        value = json.loads(raw); require(isinstance(value, dict), "Invalid accounting record")
        canonical(value)  # Reject non-finite JSON, including in otherwise unused fields.
        result.append((key, value))
    return result


class ReadModel:
    """Only read interfaces used by existing journal validators; no writer store."""
    def __init__(self, meta, claims, now): self.meta, self.claims, self.now = meta, claims, now
    def clock(self): return self.now
    def get(self, db, table, key):
        require(table == "meta" and key == 1, "Unsupported accounting read")
        return self.meta
    def rows(self, db, table):
        require(table == "claims", "Unsupported accounting inventory")
        return self.claims


def account_view(model, db):
    native = native_limits.current_in(model, db)
    if native:
        result = native_limits.status(model, db)
        return {k: result[k] for k in ("status", "observedAt", "windows", "issues")} | {"source": "native_limit_record"}
    value = model.meta["account"]
    if value is None: return {"status": "unknown", "observedAt": None, "windows": None, "issues": ["account_not_observed"], "source": "none"}
    admission.exact(value, {"observedAt", "evidenceHash", "windows"}); admission.timestamp(value["observedAt"])
    admission.sha(value["evidenceHash"]); admission.exact(value["windows"], {"short", "long"})
    issues = []; windows = {}
    if not 0 <= model.now-value["observedAt"] <= model.meta["policy"]["maxObservationAgeSeconds"]: issues.append("observation_stale_or_future")
    for name, window in value["windows"].items():
        admission.exact(window, {"usedPercent", "resetsAt"}); admission.timestamp(window["resetsAt"])
        used = window["usedPercent"]
        require(type(used) in (int, float) and 0 <= used <= 100, "Invalid account percentage")
        windows[name] = {**window, "remainingPercent": 100-used}
        if window["resetsAt"] <= model.now: issues.append(name+"_window_reset")
        if 100-used < model.meta["policy"]["minAccountRemainingPercent"]: issues.append(name+"_headroom_low")
    return {"status": "blocked" if issues else "headroom_observed", "observedAt": value["observedAt"],
            "windows": windows, "issues": issues, "source": "supplied_limit_record"}


def allocation_view(model, db, allocation, phase):
    admission.identifier(allocation["id"])
    require(allocation["fingerprint"] == digest(allocation["spec"]) and type(allocation["closed"]) is bool, "Allocation binding changed")
    limits = allocation["spec"]["limits"]
    admission.exact(limits, {"maxParallelTasks", "maxTasks", "tokenBudget", "checkpointReserveTokens"})
    for value in limits.values(): admission.integer(value)
    claims = [c for c in model.claims if c["allocationId"] == allocation["id"]]
    for claim in claims:
        require(claim["status"] in (*admission.HELD, "settled"), "Unknown ownership status")
        admission.integer(claim["estimatedTokens"])
        if claim["status"] == "settled": admission.counters(claim["actual"])
    issues = [] if phase else ["phase_binding_unavailable"]
    usage = allocation["usage"]
    if usage is not None:
        admission.counters(usage["counters"]); admission.timestamp(usage["observedAt"])
        require(isinstance(usage["coverage"], list) and set(usage["coverage"]) <= admission.COVERAGE, "Invalid coverage")
        included = usage["settledClaimIds"]
        require(isinstance(included, list) and len(included) == len(set(included)), "Invalid settlement coverage")
        settled = {c["id"]: c for c in claims if c["status"] == "settled"}
        require(set(included) <= set(settled) and sum(admission.counters(settled[k]["actual"]) for k in included) <= admission.counters(usage["counters"]),
                "Settlement accounting changed")
    budget = admission.budget_projection(allocation, model.claims)
    doc = phase_usage.current_in(db, allocation)
    if doc:
        if doc["issues"]: issues.append("usage_evidence_incomplete")
        if doc["membership"] != phase_usage.membership(model, db, allocation): issues.append("membership_changed")
        if doc["accountIdentityHash"] != model.meta.get("nativeAccountIdentity"): issues.append("usage_account_changed")
        require(usage == phase_usage.projection(doc), "Phase usage projection changed; no fallback")
    else: issues.append("phase_journal_not_observed")
    if not budget["usageKnown"]: issues.append("usage_coverage_incomplete")
    observed = usage["observedAt"] if usage else None
    if observed is None: issues.append("usage_not_observed")
    elif not 0 <= model.now-observed <= model.meta["policy"]["maxObservationAgeSeconds"]: issues.append("usage_stale_or_future")
    # Legacy totals remain historical evidence, never fabricated phase coverage.
    balance = budget["remainingForNewWork"] if not issues else None
    return {"allocationId": allocation["id"], "phaseId": phase, "closed": allocation["closed"],
            "limits": limits, "observedAt": observed,
            "expiresAt": observed+model.meta["policy"]["maxObservationAgeSeconds"] if observed else None,
            "status": "needs_evidence" if issues else "recorded", "issues": sorted(set(issues)),
            "usageSource": "phase_journal" if doc else "legacy_supplied" if usage else "none",
            "observedTokens": budget["observedTokens"] if usage else None, "heldTokens": budget["heldTokens"],
            "unincorporatedSettledTokens": budget["unincorporatedSettledTokens"],
            "checkpointReserveTokens": budget["checkpointReserveTokens"], "recordedBalance": balance,
            "recordedClaims": len(claims), "heldClaims": sum(c["status"] in admission.HELD for c in claims),
            "settledClaims": sum(c["status"] == "settled" for c in claims), "effectContextChecked": False}


def inspect(registry, ledger, workspace_id):
    identity(workspace_id); now = time.time()
    result = {"workspaceId": workspace_id, "inspectedAt": now, "workspaceRevision": None, "status": "unavailable",
              "allocations": [], "account": None, "sharedCapacity": None, "executionAuthorized": False,
              "nativeCallMade": False, "atomicAcrossStores": False, "boundary": BOUNDARY}
    try:
        with readonly(registry.db) as reg, readonly(ledger.db) as local:
            row = reg.execute("SELECT root,brain,data FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
            require(row and row[0] == str(ledger.root), "Workspace scope changed")
            require(json.loads(row[2])["databaseIdentity"] == list(file_identity(ledger.db)), "Workspace identity changed")
            meta = dict(objects(local, "meta"))[1]
            require(meta["brainId"] == row[1], "Workspace brain changed")
            result["workspaceRevision"] = meta["revision"]
            phases = {}
            for key, grant in objects(local, "snapshots", "WHERE kind=?", ("run_authorization",)):
                require(digest(grant) == key and grant["workspaceId"] == workspace_id, "Run binding changed")
                phase = grant["phaseId"]; require(isinstance(phase, str) and 0 < len(phase) <= 200, "Invalid phase ID")
                phases["phase-"+digest({"workspaceId": workspace_id, "phaseId": phase})] = phase
            path = registry.root / "admission.sqlite3"
            if not path.exists() and not path.is_symlink(): return result | {"status": "not_initialized"}
            with readonly(path) as shared:
                shared_meta = dict(objects(shared, "meta"))[1]
                require(shared_meta["schemaVersion"] == 1, "Unsupported admission schema")
                admission.AdmissionStore.validate_policy(shared_meta["policy"])
                claims = []
                columns = dict(shared.execute("SELECT id,allocation FROM claims LIMIT ?", (MAX_ROWS+1,)))
                for key, claim in objects(shared, "claims"):
                    require(claim["id"] == key and columns[key] == claim["allocationId"] and claim["status"] in (*admission.HELD, "settled"), "Invalid shared claim")
                    claims.append(claim)
                model = ReadModel(shared_meta, claims, now)
                allocations = []; all_ids = set()
                for key, allocation in objects(shared, "allocations"):
                    require(allocation["id"] == key, "Allocation identity changed")
                    all_ids.add(key)
                    if allocation["spec"]["workspaceId"] == workspace_id: allocations.append(allocation)
                require(all(c["allocationId"] in all_ids for c in claims), "Unbound shared claim")
                require(len(allocations) <= MAX_PHASES, "Phase inspection bound exceeded")
                rows = [allocation_view(model, shared, a, phases.get(a["id"])) for a in allocations]
                account = account_view(model, shared)
                policy = shared_meta["policy"]
                account["expiresAt"] = account["observedAt"]+policy["maxObservationAgeSeconds"] if account["observedAt"] else None
                # No foreign task, workspace, repository or native identity leaves this reader.
                capacity = {"recordedHeldClaims": sum(c["status"] in admission.HELD for c in claims),
                            "maximumParallelTasks": policy["maxParallelTasks"],
                            "legacyInventoryIncluded": False, "unmanagedActivityIncluded": False}
            return result | {"status": "available" if rows else "empty", "allocations": rows,
                             "account": account, "sharedCapacity": capacity}
    except INVALID:
        # Do not leak filesystem/SQL errors or silently reuse an older good report.
        return result | {"status": "unavailable", "detail": "Accounting could not be inspected within its integrity and size bounds. No partial balance is shown; ask the brain/operator to reconcile the saved records."}


def cached_summary(result, revision, now=None):
    if not result: return {"status": "not_inspected", "executionAuthorized": False}
    now = time.time() if now is None else now
    out = {k: result[k] for k in ("status", "inspectedAt", "workspaceRevision", "executionAuthorized")}
    expired = not 0 <= now-result["inspectedAt"] <= 60
    rows = []
    for allocation in result["allocations"][:8]:
        old = allocation["expiresAt"] is None or now > allocation["expiresAt"] or now < allocation["observedAt"]
        row = {k: allocation[k] for k in ("status", "closed", "observedAt", "expiresAt", "observedTokens", "heldTokens",
                  "unincorporatedSettledTokens", "checkpointReserveTokens", "recordedBalance", "recordedClaims", "heldClaims", "settledClaims", "issues")}
        row["tokenBudget"] = allocation["limits"]["tokenBudget"]
        row["expired"] = old
        if old or expired or revision != result["workspaceRevision"]: row["recordedBalance"] = None
        rows.append(row)
    out.update(historical=True, workspaceChanged=revision != result["workspaceRevision"], expired=expired,
               sharedStateRechecked=False, effectContextChecked=False, rows=rows, included=len(rows),
               omitted=len(result["allocations"])-len(rows), total=len(result["allocations"]), boundary=BOUNDARY)
    if result["account"]:
        account = result["account"]
        out["sharedAccount"] = {k: account[k] for k in ("status", "observedAt", "expiresAt", "windows", "source")}
        out["sharedAccount"]["expired"] = expired or account["expiresAt"] is None or now > account["expiresAt"]
    if result["sharedCapacity"]: out["sharedCapacity"] = result["sharedCapacity"].copy()
    return out


def assistant_summary(cached):
    """Closed numeric/status projection; no allocation/session identities or text."""
    allowed = ("status", "inspectedAt", "workspaceRevision", "executionAuthorized", "historical", "workspaceChanged", "expired",
               "sharedStateRechecked", "effectContextChecked", "included", "omitted", "total")
    out = {k: cached[k] for k in allowed if k in cached}
    out["rows"] = [{k: row[k] for k in ("status", "closed", "observedAt", "expiresAt", "observedTokens", "heldTokens",
                   "unincorporatedSettledTokens", "checkpointReserveTokens", "recordedBalance", "recordedClaims", "heldClaims",
                   "settledClaims", "tokenBudget", "expired") if k in row} for row in cached.get("rows", [])[:8]]
    if cached.get("sharedAccount"):
        account = cached["sharedAccount"]
        out["sharedAccount"] = {k: account.get(k) for k in ("status", "observedAt", "expiresAt", "source", "expired")}
        out["sharedAccount"]["windows"] = {k: ({f: value.get(f) for f in ("usedPercent", "remainingPercent", "resetsAt")} if value else None)
            for k, value in (account.get("windows") or {}).items() if k in ("short", "long")}
    if cached.get("sharedCapacity"):
        out["sharedCapacity"] = {k: cached["sharedCapacity"].get(k) for k in
            ("recordedHeldClaims", "maximumParallelTasks", "legacyInventoryIncluded", "unmanagedActivityIncluded")}
    return out
