"""Opt-in cooperative runs. Native effects belong to the designated Codex brain.

Registry -> ledger serialization protects registered workspace ownership. This is
not host-wide scheduling, an OS sandbox, complete accounting or a native client.
"""
import contextlib
import fnmatch
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import time
import uuid

from .core import ACTIVE, Refusal, canonical, digest, require, safe_relative
from . import missions
from .decisions import authorize_brain
from .enrollment import fence_exists, record_in
from . import standard_worktrees as worktrees

PROTOCOL = "standard_cooperative_v1"
CATALOG_REFRESH_KIND = "standard_catalog_refresh"
CATALOG_REFRESH_MAX_DELIVERY_ATTEMPTS = 3
BOUNDARY = ("Registered tasks only; cooperative checkpoints, not process-tree termination. "
            "Observed tokens may be incomplete; allowance reservations are not measured usage or a hard billing cap.")
TERMINAL = {"completed", "failed", "not_created"}


def controller_file(ledger):
    return ledger.root / "standard-controller.json"


def acquire_private(ledger, owner):
    """Persist the opaque token without exposing it in a tool result or argv."""
    with ledger.tx() as db:
        meta = ledger.get(db, "meta", 1)
        require(owner.startswith(meta["brainId"]+":") and meta["controller"] is None, "Exact designated brain and unowned controller required")
        if meta.get("standardRun"):
            require(meta["standardRun"]["protocol"] == PROTOCOL and meta["standardRun"]["brainId"] == meta["brainId"], "Foreign cooperative run")
        else:
            eligible(ledger, db)
        token = secrets.token_hex(24)
        fd = os.open(controller_file(ledger), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump({"owner": owner, "token": token}, output)
            output.flush(); os.fsync(output.fileno())
        meta["controller"] = {"owner": owner, "token": token, "since": time.time()}
        ledger.put(db, "meta", 1, meta)
        ledger.event(db, "standard_controller_acquired", {"owner": owner})
    return {"acquired": True, "tokenPersistedPrivately": True}


def private_token(ledger):
    fd = os.open(controller_file(ledger), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        stat = os.fstat(stream.fileno())
        require(stat.st_uid == os.getuid() and stat.st_mode & 0o077 == 0 and stat.st_nlink == 1 and stat.st_size < 2048, "Invalid private controller file")
        value = json.load(stream)
    with read_db(ledger.db) as db:
        meta = authorize_brain(ledger, db, value["token"])
        require(meta["controller"]["owner"] == value["owner"], "Stale controller file requires explicit recovery")
    return value["token"]


def release_private(ledger, checkpoint):
    token = private_token(ledger)
    ledger.release(token, checkpoint)
    controller_file(ledger).unlink()
    return {"released": True}


def exact(value, fields):
    require(isinstance(value, dict) and set(value) == set(fields.split()), "Unexpected standard protocol fields")


def read_db(path):
    db = sqlite3.connect(Path(path).as_uri()+"?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN")
    return contextlib.closing(db)


def git_root(path):
    root = Path(path).resolve(strict=True)
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, timeout=5, check=False)
    require(result.returncode == 0, "Standard scope requires an existing Git repository")
    common = Path(result.stdout.strip()).resolve(strict=True)
    stat = common.stat()
    return digest({"path": str(common), "device": stat.st_dev, "inode": stat.st_ino})


def eligible(ledger, db):
    meta = ledger.get(db, "meta", 1)
    require((meta["schemaVersion"] == 1 or (meta["schemaVersion"] == 4 and meta.get("standardRun", {}).get("protocol") == PROTOCOL))
            and "admissionBinding" not in meta and not fence_exists(ledger.root),
            "Strict or enrolled workspaces cannot switch to cooperative mode")
    repos = ledger.all(db, "repos")
    require(repos and all(r["policyProfile"] == "standard" for r in repos), "Only all-standard workspaces qualify; Harness is unchanged")
    require(not any(w["status"] in ACTIVE for w in ledger.all(db, "workers")), "Reconcile existing workers first")
    require(not any(q["status"] == "approved" for q in ledger.all(db, "queue")), "Hold legacy approved packets first")
    require(meta["paused"] is True and meta.get("runner") is None, "Legacy dispatch must stay paused with no owned runner")
    m = missions.state_in(ledger, db)
    require(m["effectiveStatus"] == "reviewed", "Review an exact mission first")
    require(m["document"]["spec"]["authority"]["approvalMode"] == "phase_delegated", "Standard Play needs explicitly reviewed phase-delegated authority")
    require(not any("merge" in s["operations"] for s in m["document"]["spec"]["phase"]["scope"]) or
            m["document"]["spec"]["authority"].get("mergeMode") == "brain_exact_pr_v1",
            "Cooperative merge needs an explicit reviewed phase opt-in")
    return meta, m


def current_blockers(ledger, db, run):
    problems = []
    try:
        _, m = eligible(ledger, db)
        require(m["documentHash"] == run["missionHash"] and m["receiptHash"] == run["reviewHash"], "Mission changed: checkpoint and review a new phase")
        require(time.time() < run["expiresAt"], "Run duration expired: checkpoint required")
    except (Refusal, ValueError) as error:
        problems.append(str(error))
    from .brain_memory import blockers as usage_blockers
    problems.extend(usage_blockers(run))
    return problems


def projection(ledger, db):
    meta = ledger.get(db, "meta", 1)
    run = meta.get("standardRun")
    result = {"protocol": PROTOCOL, "boundary": BOUNDARY, "run": run,
              "catalog": meta.get("standardCatalog"), "catalogRequired": False,
              "available": False, "blocker": None}
    refreshes = sorted((c for c in ledger.all(db, "commands") if c["kind"] == CATALOG_REFRESH_KIND),
                       key=lambda c: (c["createdAt"], c["id"]), reverse=True)
    latest_refresh = refreshes[0] if refreshes else None
    result["catalogRefresh"] = None if not latest_refresh else {
        "id": latest_refresh["id"], "status": latest_refresh["status"],
        "createdAt": latest_refresh["createdAt"], "completedAt": latest_refresh.get("completedAt"),
        "result": latest_refresh.get("result"), "notification": latest_refresh.get("notification"),
        "catalogError": latest_refresh.get("catalogError"),
        "catalogReceipt": latest_refresh.get("catalogReceipt"),
        "deliveryAttempts": len(latest_refresh.get("notificationHistory", [])) +
            (1 if latest_refresh.get("notification") else 0),
        "maxDeliveryAttempts": CATALOG_REFRESH_MAX_DELIVERY_ATTEMPTS,
    }
    try:
        eligible(ledger, db)
        catalog = result["catalog"]
        result["catalogRequired"] = not (catalog and time.time()-catalog["observedAt"] < 86400)
        require(not result["catalogRequired"], "Brain must record the available native model/effort catalog (valid for 24 hours)")
        result["available"] = True
    except (Refusal, ValueError) as error:
        result["blocker"] = str(error)
    if run:
        result["blockers"] = current_blockers(ledger, db, run)
        result["nativeObservation"] = None
        if run.get("nativeObservationHash"):
            from .standard_native_observation import report_in
            try:
                native = report_in(db, run["nativeObservationHash"])
                require(native["runId"] == run["id"] and native["brainId"] == run["brainId"] and
                        native["workspaceId"] == missions.workspace(ledger), "Foreign native task observation")
                result["nativeObservation"] = {"reportHash": run["nativeObservationHash"],
                    "observedAt": native["observedAt"], "issues": native["issues"],
                    "samples": native["samples"], "boundary": native["boundary"]}
            except (Refusal, ValueError, KeyError, TypeError):
                result["nativeObservation"] = {"reportHash": run["nativeObservationHash"],
                    "observedAt": None, "issues": ["retained_native_observation_unavailable"],
                    "samples": [], "boundary": {"executionAuthorized": False}}
        active = [t for t in run["tasks"] if t["status"] not in TERMINAL]
        permitted = run["limits"]["maxParallelTasks"]
        if worktrees.repository_mode(run) != worktrees.MODE:
            eligible_now, reason = min(1, max(0, permitted-len(active))), "Repository-exclusive mode"
        elif any(t.get("taskKind") != "producer" or not t.get("worktree") or
                 time.time()-t["worktree"].get("nativeObservedAt", 0) >= worktrees.NATIVE_AGE for t in active):
            eligible_now, reason = 0, "A pending, unbound, non-producer or stale native task retains the repository lock"
        else:
            mission_phase = (missions.state_in(ledger, db).get("document") or {}).get("spec", {}).get("phase", {})
            outline = mission_phase.get("taskOutline", [])
            candidates = []
            for item in outline:
                if any(t["repository"] == item["repository"] and
                       not worktrees.disjoint(t["paths"], item["exactFiles"]) for t in run["tasks"]):
                    continue
                if all(t["repository"] != item["repository"] or
                       worktrees.disjoint(t["paths"], item["exactFiles"]) for t in active):
                    candidates.append(item)
            chosen = []
            for item in candidates:
                if all(p["repository"] != item["repository"] or
                       worktrees.disjoint(p["exactFiles"], item["exactFiles"]) for p in chosen):
                    chosen.append(item)
            eligible_now = min(len(chosen), max(0, permitted-len(active)),
                               max(0, run["limits"]["maxTasks"]-len(run["tasks"])))
            reason = ("Conservative disjoint candidates from the reviewed task outline; exact native and file checks still apply" if outline
                      else "No reviewed independently scoped next candidate; exact proposed paths are checked at claim")
            if not outline and permitted > 0:
                eligible_now = None
                reason = "Unknown until a reviewed outline identifies independently scoped producer candidates"
        if worktrees.repository_mode(run) != worktrees.MODE and eligible_now and permitted > 0:
            outline = (missions.state_in(ledger, db).get("document") or {}).get("spec", {}).get("phase", {}).get("taskOutline", [])
            if not outline:
                eligible_now = None
                reason = "Unknown until a reviewed outline identifies the next task candidate"
        if run["status"] != "running" or result["blockers"]:
            eligible_now = 0
            reason = "Run is stopped, blocked, expired or awaiting a new exact review"
        integration_ready = False
        integration_reason = "No fully verified producer set awaiting integration"
        if worktrees.repository_mode(run) == worktrees.MODE:
            phase = (missions.state_in(ledger, db).get("document") or {}).get("spec", {}).get("phase", {})
            for scope in phase.get("scope", []):
                same = [t for t in run["tasks"] if t["repository"] == scope["repository"]]
                if (same and "open_pr" in scope["operations"] and
                    all(t.get("taskKind") == "producer" and t["status"] == "completed" and
                        t.get("sourceProof") and t.get("headSHA") for t in same) and
                    run["status"] == "running" and not result["blockers"] and
                    len(run["tasks"]) < run["limits"]["maxTasks"] and
                    charged(run)+run["limits"]["checkpointReserveTokens"] < run["limits"]["tokenBudget"]):
                    integration_ready = True
                    integration_reason = "A separate budgeted integration task can be proposed; exact claim checks still apply"
                    break
        result["parallelEligibility"] = {"permitted": permitted, "currentlyEligible": eligible_now,
                                         "active": len(active), "reason": reason,
                                         "mode": worktrees.repository_mode(run),
                                         "integrationReady": integration_ready,
                                         "integrationReason": integration_reason}
        observations = [t["observedTokens"] for t in run["tasks"] if t.get("observedTokens") is not None]
        if run["brainUsageCoverage"] != "not_observed":
            observations.append(run["brainObservedTokens"])
        result["observedTokens"] = sum(observations) if observations else None
        result["unmeasuredTasks"] = sum(t.get("observedTokens") is None for t in run["tasks"])
        result["chargedAllowance"] = charged(run)
        result["remainingAllowance"] = max(0, run["limits"]["tokenBudget"]-result["chargedAllowance"]-run["limits"]["checkpointReserveTokens"])
        usage = run.get("usageReport")
        result["measuredUsage"] = None if not usage else {
            "tokens": usage["tokens"], "coverage": usage["coverage"], "gaps": usage["gaps"],
            "collectedAt": usage["collectedAt"], "through": usage["through"],
            "highWater": run.get("usageHighWater", 0),
            "remainingMeasured": None if usage["gaps"] else max(0, run["limits"]["tokenBudget"]
                - max(usage["tokens"]["total_tokens"], run.get("usageHighWater", 0))
                - run["limits"]["checkpointReserveTokens"])}
        closeout = run.get("closeoutReport")
        result["closeoutUsage"] = None if not closeout else {
            "tokens": closeout["tokens"], "coverage": closeout["coverage"],
            "gaps": closeout["gaps"], "collectedAt": closeout["collectedAt"],
            "highWater": run.get("closeoutHighWater", 0)}
        if run["status"] in ("completed", "blocked"):
            m = missions.state_in(ledger, db)
            if m.get("document") and m["document"]["spec"]["phase"]["id"] == run["phaseId"]:
                result.update(available=False, blocker="This phase has reached its owner checkpoint. Review a genuinely new phase; Play cannot reset this phase's usage or attempts.")
    result["history"] = []
    for row in db.execute("SELECT id,data FROM snapshots WHERE kind='standard_run' ORDER BY rowid DESC LIMIT 30"):
        doc = json.loads(row["data"])
        result["history"].append({"documentHash": row["id"], "at": doc["at"], "operation": doc["operation"],
            "runId": doc["run"]["id"], "revision": doc["run"]["revision"], "status": doc["run"]["status"]})
    result["contextHash"] = digest({"workspace": missions.workspace(ledger), "brain": meta["brainId"],
        "mission": meta.get("missionConfiguration"), "run": run, "catalog": result["catalog"],
        "database": str(ledger.db), "available": result["available"], "blocker": result["blocker"]})
    return result


def request_catalog_refresh(ledger, request):
    """Retain one exact read-only capability request; retry only proven non-delivery."""
    exact(request, "id contextHash")
    require(isinstance(request["id"], str) and 8 <= len(request["id"]) <= 128, "Refresh request ID required")
    with ledger.tx() as db:
        prior = db.execute("SELECT data FROM commands WHERE id=?", (request["id"],)).fetchone()
        if prior:
            command = json.loads(prior[0])
            require(command["kind"] == CATALOG_REFRESH_KIND and
                    command["payload"]["contextHash"] == request["contextHash"],
                    "Refresh request ID belongs to different content")
            notification = command.get("notification") or {}
            history = command.get("notificationHistory", [])
            if (command["status"] == "queued" and notification.get("status") == "unavailable" and
                    len(history) + 1 < CATALOG_REFRESH_MAX_DELIVERY_ATTEMPTS):
                command["notificationHistory"] = [*history, notification]
                command.pop("notification", None)
                command["result"] = "Retrying automatic delivery after confirmed non-delivery."
                ledger.put(db, "commands", command["id"], command)
                ledger.event(db, "standard_catalog_refresh_retry", {
                    "id": command["id"], "attempt": len(command["notificationHistory"]) + 1})
            return command
        state = projection(ledger, db)
        require(state["contextHash"] == request["contextHash"], "Run readiness changed; refresh before requesting capabilities")
        eligible(ledger, db)
        require(not state["run"] or state["run"]["status"] in ("completed", "blocked"),
                "A running cooperative phase owns its catalog")
        require(not state["available"], "The native model/effort catalog is already current")
        require(not any(c["kind"] == CATALOG_REFRESH_KIND and c["status"] in ("queued", "processing")
                        for c in ledger.all(db, "commands")),
                "A native capability refresh is already pending")
        mission = missions.state_in(ledger, db)
        command = {"id": request["id"], "kind": CATALOG_REFRESH_KIND, "actor": "dashboard",
                   "status": "queued", "createdAt": time.time(),
                   "payload": {"contextHash": request["contextHash"],
                               "missionHash": mission["documentHash"], "brainId": ledger.get(db, "meta", 1)["brainId"]},
                   "result": "Saved; waiting for the designated brain to observe native capabilities."}
        ledger.put(db, "commands", command["id"], command)
        ledger.event(db, "standard_catalog_refresh_requested", {"id": command["id"], "missionHash": mission["documentHash"]})
        return command


def charged(run):
    return max(run["brainAllowance"], run.get("brainObservedTokens", 0)) + sum(
        max(t["allowance"], t.get("observedTokens") or 0) for t in run["tasks"])


def read(ledger):
    with read_db(ledger.db) as db:
        return projection(ledger, db)


def save(ledger, db, meta, run, operation):
    run["revision"] += 1
    run["updatedAt"] = time.time()
    meta["standardRun"] = run
    meta["schemaVersion"] = 4  # Older helpers refuse this explicit, owner-selected protocol.
    ledger.put(db, "meta", 1, meta)
    record = {"operation": operation, "at": time.time(), "run": run}
    key = digest(record)
    db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?)", (key, "standard_run", canonical(record)))
    ledger.event(db, "standard_"+operation, {"runId": run["id"], "revision": run["revision"], "documentHash": key})


class Controls:
    """Session-bound previews, exact replay receipts, no native calls."""
    def __init__(self):
        self.key = secrets.token_bytes(32)

    def sign(self, value):
        return hmac.new(self.key, canonical(value).encode(), hashlib.sha256).hexdigest()

    def preview(self, ledger, request, session):
        require(set(request) in ({"operation", "contextHash", "brainAllowance", "durationHours"},
                                 {"operation", "contextHash", "brainAllowance", "durationHours", "measureUsage"}),
                "Unexpected standard control fields")
        require(request["operation"] in ("play", "pause", "resume"), "Unknown run control")
        require("measureUsage" not in request or type(request["measureUsage"]) is bool,
                "Measured usage choice must be explicit")
        state = read(ledger)
        require(state["contextHash"] == request["contextHash"], "Run changed; refresh before reviewing")
        missions.integer(request["brainAllowance"], "Brain allowance", 1, 1_000_000_000)
        missions.integer(request["durationHours"], "Run hours", 1, 24)
        doc = {**request, "workspaceId": missions.workspace(ledger), "session": digest(session),
               "id": str(uuid.uuid4()), "runId": state["run"]["id"] if state["run"] else None,
               "expiresAt": time.time()+300, "boundary": BOUNDARY}
        return {"preview": doc, "signature": self.sign(doc)}

    def confirm(self, registry, ledger, body, session):
        exact(body, "preview signature confirmed")
        require(body["confirmed"] is True and isinstance(body["signature"], str), "Explicit owner confirmation required")
        doc = body["preview"]
        require(hmac.compare_digest(self.sign(doc), body["signature"]), "Invalid preview signature")
        require(doc["session"] == digest(session) and doc["workspaceId"] == missions.workspace(ledger), "Foreign preview")
        with registry.tx() as registry_db, ledger.tx() as db:
            # A lost HTTP response returns the original command, never a second effect.
            prior = db.execute("SELECT data FROM commands WHERE id=?", (doc["id"],)).fetchone()
            if prior:
                return json.loads(prior[0])
            require(time.time() < doc["expiresAt"], "Preview expired")
            require(record_in(registry_db) is None, "Strict platform enrollment blocks cooperative control")
            meta = ledger.get(db, "meta", 1)
            run = meta.get("standardRun")
            op = doc["operation"]
            if op != "pause":
                from .reply_recovery import fence_development
                fence_development(ledger, db)
            if op == "pause":
                require(run and run["id"] == doc["runId"], "Pause belongs to another run")
            else:
                require(projection(ledger, db)["contextHash"] == doc["contextHash"], "Run changed; inspect and confirm again")
            if op == "pause":
                require(run and run["status"] in ("running", "stopping"), "No active cooperative run")
                run["status"] = "stopping"
            elif op == "resume":
                require(not run or not run.get("recovery") or run["recovery"].get("status") == "replied",
                        "Recovery preparation still needs its exact reply")
                require(run and run["status"] == "paused" and not any(t["status"] not in TERMINAL for t in run["tasks"]), "Retain a safe checkpoint before resuming")
                require(not current_blockers(ledger, db, run), "Run expired or mission changed; review a new phase")
                require(not any(m["status"] in ("issued", "uncertain") for m in run.get("merges", [])), "Reconcile the unresolved merge before Resume")
                run["status"] = "running"
            else:
                require(projection(ledger, db)["available"], "Standard Play prerequisites are missing")
                require(not run or not run.get("recovery") or run["recovery"].get("status") == "replied",
                        "Recovery preparation still needs its exact reply")
                if doc.get("measureUsage"):
                    from .observations import config as observation_config
                    require(observation_config(ledger).get("codexHome"),
                            "Configure the local Codex log root before activating measured usage")
                require(run is None or run["status"] in ("completed", "blocked"), "Existing run needs its checkpoint or Resume")
                require(run is None or not any(t["status"] not in TERMINAL for t in run["tasks"]), "Unresolved native tasks retain ownership")
                require(run is None or not any(m["status"] in ("issued", "uncertain") for m in run.get("merges", [])), "Unresolved merge retains its run")
                meta, m = eligible(ledger, db)
                spec = m["document"]["spec"]
                require(run is None or run["phaseId"] != spec["phase"]["id"], "Same-phase usage/attempts cannot be reset; use Resume or review a genuinely new phase")
                require(doc["brainAllowance"]+spec["authority"]["checkpointReserveTokens"] < spec["authority"]["tokenBudget"], "Reserve leaves no worker allowance")
                identities = {s["repository"]: git_root(ledger.get(db, "repos", s["repository"])["path"]) for s in spec["phase"]["scope"]}
                run = {"id": str(uuid.uuid4()), "protocol": PROTOCOL, "revision": 0, "status": "running",
                       "missionHash": m["documentHash"], "reviewHash": m["receiptHash"], "phaseId": spec["phase"]["id"],
                       "brainId": meta["brainId"], "startedAt": time.time(), "expiresAt": time.time()+doc["durationHours"]*3600,
                       "limits": spec["authority"], "catalog": meta["standardCatalog"], "identities": identities,
                       "brainAllowance": doc["brainAllowance"], "brainObservedTokens": 0, "brainUsageCoverage": "not_observed",
                       "usageGuardVersion": 1 if doc.get("measureUsage") else None,
                       "tasks": [], "checkpoint": None, "ownerReceipt": doc}
            save(ledger, db, meta, run, op)
            command = {"id": doc["id"], "kind": "standard_"+op, "actor": "dashboard", "status": "queued",
                       "createdAt": time.time(), "payload": {"runId": run["id"]}, "result": "Saved; waiting for native brain receipt"}
            ledger.put(db, "commands", command["id"], command)
            return command


def brain(registry, ledger, token, request):
    """Strictly typed journal operations; supplied observations remain observations."""
    require(isinstance(request, dict) and len(canonical(request).encode()) <= 65536, "Bounded JSON request required")
    operation = request.get("operation")
    if isinstance(operation, str) and operation.startswith("merge_"):
        from .standard_merge import brain as merge_brain
        return merge_brain(registry, ledger, token, request)
    with registry.tx() as registry_db, ledger.tx() as db:
        meta = authorize_brain(ledger, db, token)
        require(record_in(registry_db) is None, "Strict platform enrollment blocks cooperative effects")
        if operation == "catalog":
            require(set(request) in ({"operation", "models", "source"},
                                     {"operation", "models", "source", "requestId"}),
                    "Unexpected standard protocol fields")
            eligible(ledger, db)
            require(not meta.get("standardRun") or meta["standardRun"]["status"] in ("completed", "blocked"), "Do not change a running catalog")
            pending_refreshes = [c for c in ledger.all(db, "commands")
                                 if c["kind"] == CATALOG_REFRESH_KIND and c["status"] in ("queued", "processing")]
            request_id = request.get("requestId")
            require(request_id or not pending_refreshes, "Pending automatic catalog refresh requires its exact request ID")
            command = None
            if request_id:
                command = ledger.get(db, "commands", request_id)
                require(command["kind"] == CATALOG_REFRESH_KIND and command["status"] in ("queued", "processing"),
                        "Exact pending catalog refresh required")
                require(command["payload"]["brainId"] == meta["brainId"], "Catalog refresh belongs to another brain")
                require(projection(ledger, db)["contextHash"] == command["payload"]["contextHash"],
                        "Catalog refresh scope changed; record an error instead of stale capabilities")
            require(isinstance(request["models"], list) and 1 <= len(request["models"]) <= 30, "Native catalog required")
            for row in request["models"]:
                exact(row, "model efforts")
                missions.text(row["model"], "Model", 100)
                require(set(missions.strings(row["efforts"], "Efforts")) <= {"low", "medium", "high", "xhigh", "max", "ultra"}, "Unsupported effort")
            meta["standardCatalog"] = {"models": request["models"], "source": missions.text(request["source"], "Catalog source", 500), "observedAt": time.time()}
            ledger.put(db, "meta", 1, meta)
            catalog_hash = digest(meta["standardCatalog"])
            ledger.event(db, "standard_catalog", {"catalogHash": catalog_hash})
            if command:
                command.update(status="completed", completedAt=time.time(),
                               result="Native model/effort catalog recorded by the designated brain.",
                               catalogReceipt={"catalogHash": catalog_hash, "observedAt": meta["standardCatalog"]["observedAt"]})
                ledger.put(db, "commands", command["id"], command)
                ledger.event(db, "standard_catalog_refresh_completed", {"id": command["id"], "catalogHash": catalog_hash})
            return meta["standardCatalog"]
        if operation == "catalog_error":
            exact(request, "operation requestId code detail retryable")
            command = ledger.get(db, "commands", request["requestId"])
            require(command["kind"] == CATALOG_REFRESH_KIND and command["status"] in ("queued", "processing"),
                    "Exact pending catalog refresh required")
            require(command["payload"]["brainId"] == meta["brainId"], "Catalog refresh belongs to another brain")
            missions.text(request["code"], "Catalog error code", 80)
            missions.text(request["detail"], "Catalog error detail", 1000)
            require(type(request["retryable"]) is bool, "retryable must be boolean")
            command.update(status="failed", completedAt=time.time(), result=request["detail"],
                           catalogError={"code": request["code"], "retryable": request["retryable"]})
            ledger.put(db, "commands", command["id"], command)
            ledger.event(db, "standard_catalog_refresh_failed", {
                "id": command["id"], "code": request["code"], "retryable": request["retryable"]})
            return command
        run = meta.get("standardRun")
        require(run and request.get("runId") == run["id"], "Exact cooperative run required")
        if operation == "recovery_receive":
            exact(request, "operation runId requestId")
            from .checkpoint_recovery import receive as receive_recovery
            receive_recovery(ledger, db, meta, run, request["requestId"])
            meta["inboxCheckedAt"] = time.time()
            # Conversation receipt events may advance the ledger revision inside
            # this transaction. Do not overwrite that counter with the earlier
            # controller snapshot when the run receipt is saved below.
            meta["revision"] = ledger.get(db, "meta", 1)["revision"]
        elif operation == "receive":
            exact(request, "operation runId")
            meta["inboxCheckedAt"] = time.time()
            from .conversation import pending, receive_in
            for command in ledger.all(db, "commands"):
                if command["kind"].startswith("standard_") and command["kind"] != "standard_recovery" and command["status"] == "queued":
                    command.update(status="completed", result="Received by designated brain; latest run state governs", completedAt=time.time())
                    ledger.put(db, "commands", command["id"], command)
                elif command["kind"] == "decision_response" and command["status"] == "queued" and run["status"] not in ("stopping", "paused"):
                    from .decisions import receive
                    receive(ledger, db, command)
                    ledger.put(db, "commands", command["id"], command)
                elif pending(command) and run["status"] not in ("stopping", "paused"):
                    receive_in(ledger, db, command, meta)
        elif operation == "claim":
            mode = worktrees.repository_mode(run)
            exact(request, "operation runId id repository title paths instructions acceptance model effort rationale allowance" +
                  (" taskKind" if mode == worktrees.MODE else ""))
            require(run["status"] == "running" and not current_blockers(ledger, db, run), "Run is stopped, expired or stale")
            require(not any(m["status"] in ("prepared", "issued", "uncertain") for m in run.get("merges", [])), "Merge handoff owns the phase checkpoint")
            require(not any(t["id"] == request["id"] for t in run["tasks"]), "Task intent already exists; reconcile, never recreate")
            missions.text(request["id"], "Task ID", 80)
            require(len(run["tasks"]) < run["limits"]["maxTasks"], "Phase task limit reached")
            active = [t for t in run["tasks"] if t["status"] not in TERMINAL]
            require(len(active) < run["limits"]["maxParallelTasks"], "Workspace capacity occupied")
            amount = missions.integer(request["allowance"], "Task allowance", 1, 1_000_000_000)
            require(amount <= projection(ledger, db)["remainingAllowance"], "Insufficient conservative allowance; checkpoint and ask for budget review")
            require(any(r["model"] == request["model"] and request["effort"] in r["efforts"] for r in run["catalog"]["models"]), "Select an owner-reviewed catalog combination")
            m = missions.state_in(ledger, db)
            scope = next((s for s in m["document"]["spec"]["phase"]["scope"] if s["repository"] == request["repository"]), None)
            require(scope is not None, "Repository outside reviewed scope")
            paths = missions.strings(request["paths"], "Task paths", maximum=40)
            for p in paths:
                safe_relative(p)
                require(p in scope["allowedPaths"] or any(fnmatch.fnmatchcase(p, pattern) for pattern in scope["allowedPaths"]), "Task path outside phase")
            repo = ledger.get(db, "repos", request["repository"])
            identity = git_root(repo["path"])
            require(identity == run["identities"][repo["id"]], "Repository identity changed")
            task_kind = None
            start_commit = None
            producer_sources = []
            if mode == worktrees.MODE:
                task_kind = request["taskKind"]
                require(task_kind in ("producer", "integration"), "Isolated worktree task kind required")
                require(repo["policyProfile"] == "standard" and repo.get("projectId") not in (None, "projectless"),
                        "Isolated worktrees require a registered native Git project")
                start_commit = worktrees.start_commit(repo["path"])
                pinned_base = run.setdefault("repositoryBases", {}).setdefault(repo["id"], start_commit)
                require(start_commit == pinned_base, "Repository base moved during the phase")
                same_repo = [t for t in run["tasks"] if t["repositoryIdentity"] == identity]
                if task_kind == "producer":
                    worktrees.exact_files(repo["path"], paths)
                    require(not any(t.get("taskKind") == "integration" for t in same_repo),
                            "Integration already owns this repository")
                    require(all(t.get("taskKind") == "producer" and worktrees.disjoint(paths, t["paths"])
                                for t in same_repo), "Producer file scopes overlap or are ambiguous")
                    producer_repos = {t["repository"] for t in run["tasks"] if t.get("taskKind") == "producer"}
                    integrated_repos = {t["repository"] for t in run["tasks"] if t.get("taskKind") == "integration"}
                    pending_integration_slots = len((producer_repos | {repo["id"]}) - integrated_repos)
                    require(len(run["tasks"])+1+pending_integration_slots <= run["limits"]["maxTasks"],
                            "Reserve one integration task slot per producer repository; review a larger total task limit")
                else:
                    require(not any(t.get("taskKind") == "integration" for t in same_repo),
                            "Integration is one-shot for the repository")
                    require("open_pr" in scope["operations"], "Reviewed integration scope must permit one PR")
                    worktrees.exact_files(repo["path"], paths)
                    require(same_repo and all(t.get("taskKind") == "producer" and t["status"] == "completed" and
                                              t.get("sourceProof") and t.get("headSHA") for t in same_repo),
                            "All producers must settle with verified committed source before integration")
                    producer_sources = [{"taskId": t["id"], "headSHA": t["headSHA"],
                                         "sourceProof": t["sourceProof"], "paths": t["paths"]} for t in same_repo]
                    for source in producer_sources:
                        retained = ledger.get(db, "snapshots", source["sourceProof"])
                        require(digest(retained) == source["sourceProof"] and
                                retained["commit"] == source["headSHA"] and
                                set(retained["changedPaths"]) <= set(source["paths"]) and
                                retained.get("historyScope", {}).get("bounded") is True,
                                "Pinned producer source proof is unavailable or changed")
            owners = active[:]
            for row in registry_db.execute("SELECT id,root FROM workspaces WHERE id<>?", (missions.workspace(ledger),)):
                with read_db(Path(row["root"])/"ledger.sqlite3") as other:
                    other_meta = ledger.get(other, "meta", 1)
                    require(not any(w["status"] in ACTIVE for w in ledger.all(other, "workers")), "Another workspace has legacy/strict owners; use a separate standard registry")
                    foreign = [t for t in (other_meta.get("standardRun") or {}).get("tasks", []) if t["status"] not in TERMINAL]
                    require(not any(t["repositoryIdentity"] == identity for t in foreign),
                            "Repository is owned by a registered task in another workspace")
                    owners.extend(foreign)
                    require(not any(m["repositoryIdentity"] == identity and m["status"] in ("prepared", "issued", "uncertain") for m in (other_meta.get("standardRun") or {}).get("merges", [])), "Repository has an unresolved merge handoff")
            require(len(owners) < 16, "Registered platform task capacity occupied (16)")
            same_active = [t for t in active if t["repositoryIdentity"] == identity]
            if mode != worktrees.MODE or task_kind == "integration":
                require(not same_active, "Repository is owned by a registered task")
            else:
                for owner in same_active:
                    binding = owner.get("worktree")
                    require(owner.get("taskKind") == "producer" and owner.get("threadId") and binding and
                            time.time()-binding.get("nativeObservedAt", 0) < worktrees.NATIVE_AGE,
                            "Pending or unverified native creation retains the whole-repository lock")
                    require(worktrees.disjoint(paths, owner["paths"]), "Producer file scopes overlap")
                    checked = worktrees.verify_worktree(repo["path"], owner, {
                        "root": binding["root"], "branch": binding["branch"],
                        "startCommit": binding["startCommit"],
                        "nativeCreation": binding["nativeCreation"],
                        "nativeObservation": {"threadId": owner["threadId"], "hostId": owner["hostId"],
                                              "cwd": binding["root"], "observedAt": binding["nativeObservedAt"],
                                              "sourceHash": binding["nativeSourceHash"]}}, fresh_native=True)
                    require(checked["layoutHash"] == binding["layoutHash"], "Existing worktree identity changed")
            task = {k: request[k] for k in ("id", "repository", "title", "paths", "model", "effort", "rationale", "allowance")}
            if mode == worktrees.MODE:
                task.update(taskKind=task_kind, startCommit=start_commit,
                            producerSources=producer_sources, nativeProjectId=repo["projectId"])
            for key in ("title", "rationale"):
                task[key] = missions.text(task[key], key, 2000)
            seed = {"runId": run["id"], "taskId": task["id"], "mission": m["document"], "repository": repo,
                    "instructions": missions.text(request["instructions"], "Instructions", 16000),
                    "acceptance": missions.strings(request["acceptance"], "Acceptance"), "task": task,
                    "checkpoint": run["checkpoint"], "boundary": BOUNDARY}
            if mode == worktrees.MODE:
                seed["nativeWorktreeRequired"] = True
                seed["nativeCreation"] = {"projectId": repo["projectId"], "environment": "worktree",
                                          "startingState": {"type": "branch", "branchName": start_commit},
                                          "boundary": "Use the exact pinned commit as the worktree start ref; a default-ref checkout is not accepted."}
                seed["producerCommits"] = producer_sources
                seed["roleBoundary"] = ("Producer: edit, test and commit only in this task's native worktree; "
                                        "do not open or merge a PR." if task_kind == "producer" else
                                        "Integration: combine each pinned producer commit, run combined checks, "
                                        "and open one PR. Conflicts or drift stop for owner review; never retry an uncertain native effect.")
            from .project_knowledge import seed_references
            try:
                seed["sourceReferences"] = seed_references(ledger, repo["id"], repo["path"], paths)
            except (Refusal, OSError, ValueError):
                seed["sourceReferences"] = {"status": "unavailable", "items": [],
                                            "boundary": "Knowledge is optional; inspect authorized source directly"}
            key = digest(seed)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, "standard_seed", canonical(seed)))
            task.update(status="claimed", seedHash=key, repositoryIdentity=identity, createdAt=time.time(), observedTokens=None,
                        threadId=None, clientThreadId=None, nativeStatus="not_created", effectIssued=False, result=None)
            run["tasks"].append(task)
        elif operation == "issue":
            exact(request, "operation runId taskId")
            require(run["status"] == "running" and not current_blockers(ledger, db, run), "Run fenced before native effect")
            task = find_task(run, request)
            require(task["status"] == "claimed" and not task["effectIssued"], "Effect already issued; no resend")
            task.update(effectIssued=True, status="creating", issuedAt=time.time())
        elif operation == "bind":
            exact(request, "operation runId taskId threadId clientThreadId hostId")
            task = find_task(run, request)
            require(task["effectIssued"] and task["status"] in ("creating", "pending"), "No unresolved native creation")
            require(bool(request["threadId"]) != bool(request["clientThreadId"]), "Record confirmed task OR pending client ID")
            for field in ("threadId", "clientThreadId"):
                if request[field]:
                    require(str(uuid.UUID(request[field])) == request[field], "Native UUID required")
            require(request["threadId"] != run["brainId"], "Brain cannot be its own worker")
            require(not any(t["id"] != task["id"] and t["threadId"] == request["threadId"] for t in run["tasks"]) if request["threadId"] else True, "Duplicate native task")
            task.update(threadId=request["threadId"], clientThreadId=request["clientThreadId"] or task["clientThreadId"],
                        hostId=missions.text(request["hostId"], "Host", 100), status="active" if request["threadId"] else "pending")
        elif operation == "worktree_bind":
            exact(request, "operation runId taskId threadId root branch startCommit nativeObservation nativeCreation")
            require(worktrees.repository_mode(run) == worktrees.MODE, "Worktree binding is only for reviewed isolated phases")
            task = find_task(run, request)
            require(task.get("threadId") and task["threadId"] == request["threadId"] and task["status"] == "active",
                    "Confirmed active native task required")
            repo = ledger.get(db, "repos", task["repository"])
            value = {k: request[k] for k in ("root", "branch", "startCommit", "nativeObservation", "nativeCreation")}
            prior = task.get("worktree")
            if prior:
                native = value["nativeObservation"]
                if (value["root"] == prior["root"] and value["branch"] == prior["branch"] and
                    value["startCommit"] == prior["startCommit"] and value["nativeCreation"] == prior["nativeCreation"] and
                    isinstance(native, dict) and
                    native == {"threadId": task["threadId"], "hostId": task["hostId"],
                               "cwd": prior["root"], "observedAt": prior["nativeObservedAt"],
                               "sourceHash": prior["nativeSourceHash"]}):
                    return projection(ledger, db)  # Exact historical replay; no I/O or refreshed clock.
            checked = worktrees.verify_worktree(repo["path"], task, value, fresh_native=True)
            if prior:
                require({k: checked[k] for k in ("root", "branch", "startCommit", "layoutHash")} ==
                        {k: prior[k] for k in ("root", "branch", "startCommit", "layoutHash")} and
                        checked["nativeObservedAt"] > prior["nativeObservedAt"],
                        "Worktree binding is immutable; refresh needs newer native evidence")
            require(not any(t["id"] != task["id"] and t.get("worktree") and
                            (t["worktree"]["root"] == checked["root"] or
                             t["worktree"]["layoutHash"] == checked["layoutHash"] or
                             t["worktree"]["branch"].casefold() == checked["branch"].casefold())
                            for t in run["tasks"] if t["repositoryIdentity"] == task["repositoryIdentity"]),
                    "Native worktree or branch is already bound to another task")
            task["worktree"] = checked
        elif operation == "observe":
            exact(request, "operation runId taskId nativeStatus observedTokens trackedTerminals observedAt source")
            task = find_task(run, request)
            require(task["threadId"] and task["status"] not in TERMINAL, "Confirmed non-terminal task required")
            require(request["nativeStatus"] in ("active", "idle", "completed", "failed", "unknown"), "Unknown native status")
            require(type(request["observedAt"]) in (int, float) and 0 <= time.time()-request["observedAt"] < 300, "Fresh native observation required")
            count = request["observedTokens"]
            if count is not None:
                missions.integer(count, "Observed cumulative tokens", task["observedTokens"] or 0, 10**12)
                task["observedTokens"] = count
            require(request["trackedTerminals"] in ("running", "none", "unknown"), "Tracked terminal state required")
            task.update(nativeStatus=request["nativeStatus"], trackedTerminals=request["trackedTerminals"], observedAt=request["observedAt"],
                        observationSource=missions.text(request["source"], "Observation source", 1000))
            # Supplied observations remain supported, but must not inherit a
            # measured owned-host proof from a previous observation.
            task.pop("nativeObservationHash", None)
            if charged(run)+run["limits"]["checkpointReserveTokens"] >= run["limits"]["tokenBudget"]:
                run["status"] = "stopping"
        elif operation == "preserve":
            exact(request, "operation runId taskId path createdAt")
            task = find_task(run, request)
            require(task["threadId"], "Artifact must belong to a confirmed registered task")
            path = Path(missions.text(request["path"], "Artifact path", 4096)).absolute()
            require(path == path.resolve(strict=True), "Artifact path must be canonical without symlinks")
            root_text = subprocess.run(["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
                                       capture_output=True, text=True, timeout=5, check=False)
            require(root_text.returncode == 0, "Artifact must be inside the registered repository or its worktree")
            root = Path(root_text.stdout.strip()).resolve(strict=True)
            require(git_root(root) == task["repositoryIdentity"], "Artifact belongs to a different Git repository")
            if worktrees.repository_mode(run) == worktrees.MODE:
                binding = task.get("worktree")
                require(binding and root == Path(binding["root"]),
                        "Preserve only from this task's verified native worktree")
                repo = ledger.get(db, "repos", task["repository"])
                checked = worktrees.verify_worktree(repo["path"], task, {
                    "root": binding["root"], "branch": binding["branch"],
                    "startCommit": binding["startCommit"],
                    "nativeCreation": binding["nativeCreation"],
                    "nativeObservation": {"threadId": task["threadId"], "hostId": task["hostId"],
                                          "cwd": binding["root"], "observedAt": binding["nativeObservedAt"],
                                          "sourceHash": binding["nativeSourceHash"]}}, fresh_native=True)
                require(checked["layoutHash"] == binding["layoutHash"], "Worktree identity changed")
            relative = path.relative_to(root).as_posix()
            require(any(fnmatch.fnmatchcase(relative, pattern) for pattern in task["paths"]), "Artifact is outside the approved task paths")
            from .observations import EXTENSIONS, MAX_ARTIFACT, read_regular, capture
            require(path.suffix.lower() in EXTENSIONS, "Unsupported artifact format")
            created = request["createdAt"]
            require(created is None or (type(created) in (int, float) and 0 < created <= time.time()), "Use observed creation time or null")
            artifact = capture(db, str(path), read_regular(path, root, MAX_ARTIFACT), {
                "name": path.name, "path": str(path), "repository": task["repository"],
                "references": [{"session": task["threadId"], "at": created or time.time()}],
                "createdAt": created, "orderAt": created or time.time(), "provenance": "standard_task_preservation"})
            task.setdefault("artifacts", [])
            if artifact["id"] not in task["artifacts"]:
                task["artifacts"].append(artifact["id"])
        elif operation == "finish":
            exact(request, "operation runId taskId outcome evidence")
            task = find_task(run, request)
            require(task["status"] not in TERMINAL, "Task already terminal")
            require(request["outcome"] in ("completed", "failed"), "Invalid terminal result")
            require(task.get("nativeStatus") in ("idle", "completed", "failed") and task.get("trackedTerminals") == "none"
                    and 0 <= time.time()-task.get("observedAt", 0) < 300, "Fresh finished-task and tracked-terminal observation required; not whole-tree proof")
            if task.get("nativeObservationHash"):
                from .standard_native_observation import report_in
                observed = report_in(db, task["nativeObservationHash"])
                sample = next((s for s in observed["samples"] if s["taskId"] == task["id"]), None)
                require(observed["runId"] == run["id"] and observed["brainId"] == run["brainId"] and
                        observed["workspaceId"] == missions.workspace(ledger) and sample and
                        sample["threadId"] == task["threadId"] and not sample["issues"] and
                        sample["nativeStatus"] == task["nativeStatus"] and
                        sample["trackedTerminals"] == task["trackedTerminals"] and
                        observed["observedAt"] == task["observedAt"], "Native task observation proof changed")
            evidence = request["evidence"]
            require(isinstance(evidence, dict), "Result evidence must be an object")
            required = {"source", "tests", "artifacts", "preservation", "summary"}
            mode = worktrees.repository_mode(run)
            if mode == worktrees.MODE:
                required |= {"headSHA"}
                if task.get("taskKind") == "integration":
                    required |= {"prUrl", "prHeadBranch"}
                require(request["outcome"] == "failed" or set(evidence) == required,
                        "Isolated completed result needs exact commit and integration PR evidence")
                require(request["outcome"] != "failed" or set(evidence) in (required, required-{"headSHA"},
                        required-{"headSHA", "prUrl", "prHeadBranch"}), "Unexpected isolated failure evidence fields")
            else:
                require(isinstance(evidence, dict) and set(evidence) in (required, required | {"headSHA"}),
                        "Unexpected result evidence fields")
            if "headSHA" in evidence:
                from .source_observation import oid
                oid(evidence["headSHA"])
            require(isinstance(evidence["artifacts"], list) and len(evidence["artifacts"]) <= 30, "Bounded artifact hashes required")
            for key in evidence["artifacts"]:
                require(isinstance(key, str) and (db.execute("SELECT 1 FROM snapshots WHERE id=?", (key,)).fetchone()
                        or db.execute("SELECT 1 FROM artifact_versions WHERE id=?", (key,)).fetchone()), "Preserve referenced artifact first")
                if mode == worktrees.MODE:
                    require(key in task.get("artifacts", []),
                            "Isolated result artifact must be preserved by this exact native task")
            for key in ("source", "tests", "preservation", "summary"):
                missions.text(evidence[key], key, 8000)
            if mode == worktrees.MODE and request["outcome"] == "completed":
                repo = ledger.get(db, "repos", task["repository"])
                report = worktrees.source_proof(repo["path"], task, evidence["headSHA"])
                if task["taskKind"] == "integration":
                    from .github_evidence import pr_target
                    from .standard_merge import remote_identity
                    from .resources import git_metadata
                    slug, number, _ = pr_target(evidence["prUrl"])
                    require(evidence["prUrl"] == f"https://github.com/{slug}/pull/{number}",
                            "Canonical integration PR URL required")
                    require(evidence["prHeadBranch"] == task["worktree"]["branch"],
                            "Integration PR claim must name its pinned native worktree branch")
                    common = Path(git_metadata(repo["path"], "rev-parse", "--path-format=absolute", "--git-common-dir"))
                    require(remote_identity(common) == slug, "Integration PR belongs to another repository origin")
                    producers = task["producerSources"]
                    require(all(next((t for t in run["tasks"] if t["id"] == p["taskId"]), {}).get("sourceProof") == p["sourceProof"]
                                for p in producers), "Producer evidence changed before integration")
                    worktrees.integrated(repo["path"], task, report, [p["headSHA"] for p in producers])
                source_key = digest(report)
                db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?)", (source_key, "standard_worktree_source", canonical(report)))
                task.update(sourceProof=source_key, headSHA=evidence["headSHA"])
            doc = {"taskId": task["id"], "runId": run["id"], "outcome": request["outcome"], "evidence": evidence, "at": time.time(), "boundary": BOUNDARY}
            key = digest(doc)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, "standard_result", canonical(doc)))
            task.update(status=request["outcome"], result=key, finishedAt=time.time())
            if request["outcome"] == "failed":
                run["status"] = "stopping"
        elif operation == "cancel_unissued":
            exact(request, "operation runId taskId")
            task = find_task(run, request)
            require(not task["effectIssued"], "Uncertain creation cannot be cancelled or retried")
            task["status"] = "not_created"
        elif operation == "checkpoint":
            require(not run.get("ownerCloseout"), "Owner-closed phase cannot be reopened or relabelled; prepare a successor")
            required = {"operation", "runId", "outcome", "summary", "brainObservedTokens"}
            require(set(request) in (required, required | {"reasonCodes"}), "Unexpected checkpoint fields")
            require(request["outcome"] in ("paused", "completed", "blocked"), "Checkpoint outcome required")
            reasons = request.get("reasonCodes", [])
            from .recovery import CHECKPOINT_REASONS
            require(isinstance(reasons, list) and len(reasons) <= 8 and len(reasons) == len(set(map(str, reasons)))
                    and all(isinstance(code, str) and code in CHECKPOINT_REASONS for code in reasons),
                    "Use only supported bounded checkpoint reason codes")
            require(request["outcome"] != "completed" or not reasons,
                    "Completed checkpoint cannot retain safety-stop reasons")
            require(not any(t["status"] not in TERMINAL for t in run["tasks"]), "Unresolved registered tasks retain ownership")
            if request["outcome"] in ("completed", "blocked"):
                require(not any(m["status"] in ("prepared", "issued", "uncertain") for m in run.get("merges", [])), "Reconcile merge before closing the phase")
            if request["outcome"] == "completed":
                require(run["tasks"] and all(t["status"] == "completed" for t in run["tasks"]), "A completed phase needs verified tasks")
            observed = request["brainObservedTokens"]
            if observed is not None:
                missions.integer(observed, "Brain observed tokens", run["brainObservedTokens"], 10**12)
                run.update(brainObservedTokens=observed, brainUsageCoverage="observed_partial", brainAllowance=max(observed, run["brainAllowance"]))
            run.update(status=request["outcome"], checkpoint={"summary": missions.text(request["summary"], "Checkpoint", 8000),
                "reasonCodes": reasons, "at": time.time()})
            from .brain_memory import capsule
            capsule(ledger, db, run, request["summary"])
        else:
            raise Refusal("Unknown standard brain operation")
        save(ledger, db, meta, run, operation)
        return projection(ledger, db)


def find_task(run, request):
    task = next((t for t in run["tasks"] if t["id"] == request.get("taskId")), None)
    require(task is not None, "Unknown registered task")
    return task
