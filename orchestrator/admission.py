"""Atomic capacity accounting, NOT execution authority (WSP-04A).

This kernel has no native tools, scheduler, HTTP write route or automatic
activation. A future run controller must validate owner authority and adopt all
legacy owners before using it. All evidence here is a caller assertion, not an
independent observation. See docs/ADMISSION.md for the integration boundary.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import re
import sqlite3
import time

from .core import canonical, digest, require
from .workspaces import private_path, identity

HELD = ("reserved", "starting", "running", "uncertain", "blocked")
COUNTERS = {"inputTokens", "cachedInputTokens", "outputTokens", "reasoningOutputTokens"}
COVERAGE = {"brain", "workers", "reviews"}


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value), "Invalid admission identifier")
    return value


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value), "Evidence or binding SHA-256 required")
    return value


def integer(value, minimum=0, maximum=1_000_000_000_000):
    require(type(value) is int and minimum <= value <= maximum, "Invalid admission integer")
    return value


def exact(value, fields):
    require(isinstance(value, dict) and set(value) == set(fields), "Admission fields do not match contract")


def timestamp(value):
    require(type(value) in (int, float) and math.isfinite(value) and value > 0, "Invalid observation time")
    return value


def counters(value):
    exact(value, COUNTERS)
    for amount in value.values():
        integer(amount)
    require(value["cachedInputTokens"] <= value["inputTokens"] and
            value["reasoningOutputTokens"] <= value["outputTokens"], "Token subset exceeds its parent counter")
    # Cached input and reasoning are subsets, not additional tokens or dollars.
    return value["inputTokens"] + value["outputTokens"]


def resource(value, prefix="repo"):
    pattern = r"repo-(?:local|remote):[a-f0-9]{64}" if prefix == "repo" else r"runner:[a-f0-9]{64}"
    require(isinstance(value, str) and re.fullmatch(pattern, value), "Invalid canonical resource key")
    return value


class AdmissionStore:
    """One private SQLite transaction covers all workspaces and resource claims.

    No cross-database transaction with existing workspace ledgers is claimed.
    Construction with create=False never seeds policy or creates a database.
    Policy and allocation bindings are immutable; no silent budget revision.
    """

    def __init__(self, root, *, policy=None, clock=time.time, legacy_bundle=None, expected_identity=None):
        self.root = private_path(root, existing=True)
        self.db = self.root / "admission.sqlite3"
        self.clock = clock
        if legacy_bundle is not None:
            from .admission_legacy import require_import_fences, validate
            validate(legacy_bundle)
            require(policy == legacy_bundle["policy"], "Exact reviewed adoption policy required")
            require_import_fences(self.root, legacy_bundle, expected_identity)
        require(not self.db.is_symlink(), "Admission database symlink refused")
        if not self.db.exists():
            require(expected_identity is None, "Pinned admission database is missing; explicit recovery required")
            require(policy is not None, "Admission store is not initialized")
            self.validate_policy(policy)
            os.close(os.open(self.db, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        stat = self.db.stat()
        require(self.db.is_file() and stat.st_uid == os.getuid() and stat.st_mode & 0o077 == 0 and stat.st_nlink == 1,
                "Admission database must be private and regular")
        self.database_identity = (stat.st_dev, stat.st_ino)
        require(expected_identity is None or tuple(expected_identity) == self.database_identity,
                "Expected admission database identity changed")
        with self.tx() as db:
            if policy is not None:
                self.validate_policy(policy)
                # No executescript: its implicit commit would break atomic initialization.
                for statement in (
                    "CREATE TABLE IF NOT EXISTS meta(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)",
                    "CREATE TABLE IF NOT EXISTS allocations(id TEXT PRIMARY KEY, data TEXT NOT NULL)",
                    "CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY, allocation TEXT NOT NULL, data TEXT NOT NULL)",
                    "CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY, claim TEXT NOT NULL, since REAL NOT NULL)",
                    "CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, data TEXT NOT NULL)",
                ):
                    db.execute(statement)
                db.execute("INSERT OR IGNORE INTO meta VALUES(1,?)", (canonical({"schemaVersion": 1, "policy": policy, "account": None}),))
            meta = self.get(db, "meta", 1)
            require(meta["schemaVersion"] == 1, "Unsupported admission schema")
            if policy is not None:
                require(meta["policy"] == policy, "Admission policy is immutable; explicit migration required")
            if legacy_bundle is not None:
                from .admission_legacy import install
                install(self, db, legacy_bundle)

    @staticmethod
    def validate_policy(policy):
        exact(policy, {"maxParallelTasks", "maxObservationAgeSeconds", "minAccountRemainingPercent"})
        integer(policy["maxParallelTasks"], 1, 64)
        integer(policy["maxObservationAgeSeconds"], 1, 300)
        integer(policy["minAccountRemainingPercent"], 1, 99)

    @contextlib.contextmanager
    def tx(self):
        stat = self.db.stat()
        private_path(self.root, existing=True)
        require(not self.db.is_symlink() and (stat.st_dev, stat.st_ino) == self.database_identity
                and stat.st_uid == os.getuid() and stat.st_mode & 0o077 == 0 and stat.st_nlink == 1,
                "Admission database identity or permissions changed")
        db = sqlite3.connect(self.db, isolation_level=None, timeout=10)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get(db, table, key):
        row = db.execute(f"SELECT data FROM {table} WHERE id=?", (key,)).fetchone()
        require(row is not None, "Unknown admission record")
        return json.loads(row[0])

    @staticmethod
    def put(db, table, key, value):
        db.execute(f"UPDATE {table} SET data=? WHERE id=?", (canonical(value), key))

    @staticmethod
    def rows(db, table):
        return [json.loads(row[0]) for row in db.execute(f"SELECT data FROM {table} ORDER BY id")]

    def event(self, db, kind, **fields):
        db.execute("INSERT INTO events(data) VALUES(?)", (canonical({"at": self.clock(), "kind": kind, **fields}),))

    def fresh(self, observed_at, policy):
        timestamp(observed_at)
        require(0 <= self.clock() - observed_at <= policy["maxObservationAgeSeconds"], "Fresh non-future observation required")

    def open_allocation(self, allocation_id, *, workspace_id, binding_hash, limits, repositories, runners=()):
        """Pin a capacity envelope. This does not validate or grant run authority."""
        identifier(allocation_id); identity(workspace_id); sha(binding_hash)
        exact(limits, {"maxParallelTasks", "maxTasks", "tokenBudget", "checkpointReserveTokens"})
        integer(limits["maxParallelTasks"], 1, 16); integer(limits["maxTasks"], 1, 1000)
        integer(limits["tokenBudget"], 1, 1_000_000_000)
        integer(limits["checkpointReserveTokens"], 1, limits["tokenBudget"] - 1)
        require(limits["maxParallelTasks"] <= limits["maxTasks"], "Parallel limit exceeds total tasks")
        require(isinstance(repositories, dict) and 1 <= len(repositories) <= 20, "Pin 1–20 repository identities")
        clean_repos = {}
        for repo, keys in repositories.items():
            identifier(repo)
            require(isinstance(keys, list) and 1 <= len(keys) <= 4, "Canonical repository keys required")
            clean_repos[repo] = sorted({resource(key) for key in keys})
        require(isinstance(runners, (list, tuple)) and len(runners) <= 10, "Invalid runner identities")
        spec = {"workspaceId": workspace_id, "bindingHash": binding_hash, "limits": limits,
                "repositories": clean_repos, "runners": sorted({resource(key, "runner") for key in runners})}
        fingerprint = digest(spec)
        with self.tx() as db:
            from .admission_legacy import require_open
            require_open(self.root, self.get(db, "meta", 1))
            prior = db.execute("SELECT data FROM allocations WHERE id=?", (allocation_id,)).fetchone()
            if prior:
                value = json.loads(prior[0])
                require(value["fingerprint"] == fingerprint, "Allocation ID reused with different content")
                return value
            require(not any(a["spec"]["workspaceId"] == workspace_id and not a["closed"] for a in self.rows(db, "allocations")),
                    "Workspace already has an open allocation")
            value = {"id": allocation_id, "fingerprint": fingerprint, "spec": spec,
                     "createdAt": self.clock(), "closed": False, "usage": None}
            db.execute("INSERT INTO allocations VALUES(?,?)", (allocation_id, canonical(value)))
            self.event(db, "allocation_opened", id=allocation_id)
            return value

    def observe_account(self, observation):
        exact(observation, {"observedAt", "evidenceHash", "windows"})
        sha(observation["evidenceHash"])
        exact(observation["windows"], {"short", "long"})
        for window in observation["windows"].values():
            exact(window, {"usedPercent", "resetsAt"})
            used = window["usedPercent"]
            require(type(used) in (int, float) and math.isfinite(used) and 0 <= used <= 100, "Unknown or invalid account usage")
            timestamp(window["resetsAt"])
            require(window["resetsAt"] > observation["observedAt"], "Account window already reset")
        with self.tx() as db:
            meta = self.get(db, "meta", 1)
            if meta["account"] == observation:
                return
            self.fresh(observation["observedAt"], meta["policy"])
            require(not meta["account"] or observation["observedAt"] > meta["account"]["observedAt"], "Account observation moved backwards")
            meta["account"] = observation
            self.put(db, "meta", 1, meta)
            self.event(db, "account_observed", evidenceHash=observation["evidenceHash"])

    def observe_usage(self, allocation_id, observation):
        exact(observation, {"observedAt", "evidenceHash", "counters", "coverage", "settledClaimIds"})
        sha(observation["evidenceHash"]); total = counters(observation["counters"])
        coverage, included = observation["coverage"], observation["settledClaimIds"]
        require(isinstance(coverage, list) and all(isinstance(v, str) for v in coverage)
                and len(coverage) == len(set(coverage)) and set(coverage) <= COVERAGE, "Invalid usage coverage")
        require(isinstance(included, list) and len(included) <= 1000, "Invalid settled-claim coverage")
        for cid in included:
            identifier(cid)
        require(len(included) == len(set(included)), "Duplicate settled-claim coverage")
        with self.tx() as db:
            allocation = self.get(db, "allocations", allocation_id)
            prior = allocation["usage"]
            if prior == observation:
                return
            self.fresh(observation["observedAt"], self.get(db, "meta", 1)["policy"])
            require(observation["observedAt"] >= allocation["createdAt"], "Usage predates allocation")
            if prior:
                require(observation["observedAt"] > prior["observedAt"] and
                        all(observation["counters"][k] >= prior["counters"][k] for k in COUNTERS) and
                        set(prior["settledClaimIds"]) <= set(included), "Cumulative usage moved backwards")
            included_total = 0
            for cid in included:
                claim = self.get(db, "claims", cid)
                require(claim["allocationId"] == allocation_id and claim["status"] == "settled"
                        and claim["settledAt"] <= observation["observedAt"], "Usage includes an unsettled or foreign claim")
                included_total += counters(claim["actual"])
            require(included_total <= total, "Usage does not cover included settlements")
            allocation["usage"] = observation
            self.put(db, "allocations", allocation_id, allocation)
            self.event(db, "usage_observed", id=allocation_id, evidenceHash=observation["evidenceHash"])

    def budget(self, db, allocation):
        usage = allocation["usage"]
        spent = counters(usage["counters"]) if usage else 0
        included = set(usage["settledClaimIds"]) if usage else set()
        claims = [c for c in self.rows(db, "claims") if c["allocationId"] == allocation["id"]]
        # Active estimates may overlap partial observed usage. Keep the conservative
        # over-count until an explicit settled-claim coverage observation replaces it.
        held = sum(c["estimatedTokens"] for c in claims if c["status"] in HELD)
        unsettled_usage = sum(counters(c["actual"]) for c in claims if c["status"] == "settled" and c["id"] not in included)
        limits = allocation["spec"]["limits"]
        return {"observedTokens": spent, "heldTokens": held, "unincorporatedSettledTokens": unsettled_usage,
                "checkpointReserveTokens": limits["checkpointReserveTokens"],
                "remainingForNewWork": limits["tokenBudget"] - spent - held - unsettled_usage - limits["checkpointReserveTokens"],
                "usageKnown": usage is not None and set(usage["coverage"]) == COVERAGE}

    def check_budget(self, db, allocation, extra=0):
        from .admission_legacy import require_open
        require_open(self.root, self.get(db, "meta", 1))
        require(not allocation["closed"], "Allocation is closed")
        meta = self.get(db, "meta", 1)
        account, policy = meta["account"], meta["policy"]
        require(account is not None, "Account usage is unknown")
        self.fresh(account["observedAt"], policy)
        for window in account["windows"].values():
            require(window["resetsAt"] > self.clock(), "Account window reset; refresh observation")
            require(100 - window["usedPercent"] >= policy["minAccountRemainingPercent"], "Account headroom below policy")
        budget = self.budget(db, allocation)
        require(budget["usageKnown"], "Complete brain, worker and review usage coverage required")
        self.fresh(allocation["usage"]["observedAt"], policy)
        require(budget["remainingForNewWork"] >= extra, "Phase token headroom exhausted; checkpoint reserve protected")

    def reserve(self, claim_id, allocation_id, *, repositories, estimates, role="worker"):
        identifier(claim_id)
        require(role in ("worker", "reviewer", "nested"), "Unsupported task role")
        require(isinstance(repositories, list) and 1 <= len(repositories) <= 20, "Repository scope required")
        for repo in repositories:
            identifier(repo)
        require(len(repositories) == len(set(repositories)), "Duplicate repository scope")
        exact(estimates, {"workTokens", "reviewTokens", "handoffTokens"})
        for amount in estimates.values():
            integer(amount, 1, 1_000_000_000)
        spec = {"allocationId": allocation_id, "repositories": sorted(repositories), "estimates": estimates, "role": role}
        fingerprint = digest(spec)
        with self.tx() as db:
            from .admission_legacy import require_open
            require_open(self.root, self.get(db, "meta", 1))
            prior = db.execute("SELECT data FROM claims WHERE id=?", (claim_id,)).fetchone()
            if prior:
                result = json.loads(prior[0])
                require(result["fingerprint"] == fingerprint, "Claim ID reused with different content")
                return result  # Replay never reacquires resources or permits another native call.
            allocation = self.get(db, "allocations", allocation_id)
            estimated = sum(estimates.values())
            self.check_budget(db, allocation, estimated)
            claims = self.rows(db, "claims")
            held = [c for c in claims if c["status"] in HELD]
            limits = allocation["spec"]["limits"]
            require(len(held) < self.get(db, "meta", 1)["policy"]["maxParallelTasks"], "Global task slots exhausted")
            require(sum(c["allocationId"] == allocation_id for c in held) < limits["maxParallelTasks"], "Workspace task slots exhausted")
            require(sum(c["allocationId"] == allocation_id for c in claims) < limits["maxTasks"], "Phase task-attempt limit exhausted")
            keys = set()
            for repo in repositories:
                require(repo in allocation["spec"]["repositories"], "Repository is outside allocation")
                keys.update(allocation["spec"]["repositories"][repo])
            for key in sorted(keys):
                require(not db.execute("SELECT 1 FROM resources WHERE id=?", (key,)).fetchone(), "Repository resource already owned")
            result = {"id": claim_id, **spec, "fingerprint": fingerprint, "estimatedTokens": estimated,
                      "status": "reserved", "createdAt": self.clock(), "native": None, "actual": None, "settledAt": None}
            db.execute("INSERT INTO claims VALUES(?,?,?)", (claim_id, allocation_id, canonical(result)))
            for key in sorted(keys):
                db.execute("INSERT INTO resources VALUES(?,?,?)", (key, claim_id, self.clock()))
            self.event(db, "capacity_reserved", id=claim_id)
            return result

    def begin(self, claim_id):
        """One-shot durable boundary; caller still needs independent execution authority."""
        with self.tx() as db:
            claim = self.get(db, "claims", claim_id)
            require(claim["status"] == "reserved", "Creation already attempted; reconcile, never blindly retry")
            self.check_budget(db, self.get(db, "allocations", claim["allocationId"]))
            claim.update(status="starting", startedAt=self.clock())
            self.put(db, "claims", claim_id, claim)
            self.event(db, "creation_boundary", id=claim_id)
            return claim

    def bind(self, claim_id, *, host_id, thread_id):
        identifier(host_id); identifier(thread_id)
        native = {"hostId": host_id, "threadId": thread_id}
        with self.tx() as db:
            claim = self.get(db, "claims", claim_id)
            require(claim["status"] in ("starting", "uncertain", "blocked", "running"), "Task is not awaiting binding")
            if claim["native"]:
                require(claim["native"] == native, "Native identity already bound")
                return claim
            require(not any(c["native"] == native for c in self.rows(db, "claims")), "Native task already belongs to a claim")
            claim.update(status="running", native=native)
            self.put(db, "claims", claim_id, claim)
            self.event(db, "native_bound", id=claim_id, **native)
            return claim

    def block(self, claim_id, evidence_hash):
        sha(evidence_hash)
        with self.tx() as db:
            claim = self.get(db, "claims", claim_id)
            require(claim["status"] in ("starting", "running", "uncertain", "blocked"), "Claim has no attempted creation")
            claim["status"] = "blocked" if claim["native"] else "uncertain"
            self.put(db, "claims", claim_id, claim)
            self.event(db, "ownership_retained", id=claim_id, evidenceHash=evidence_hash)

    def runner(self, claim_id, key, operation, *, evidence_hash, observed_at):
        resource(key, "runner"); sha(evidence_hash)
        require(operation in ("acquire", "release"), "Unknown runner operation")
        with self.tx() as db:
            claim = self.get(db, "claims", claim_id)
            self.fresh(observed_at, self.get(db, "meta", 1)["policy"])
            require(observed_at >= claim.get("startedAt", claim["createdAt"]), "Runner observation predates claim")
            allocation = self.get(db, "allocations", claim["allocationId"])
            require(key in allocation["spec"]["runners"], "Runner identity is outside allocation")
            owner = db.execute("SELECT claim,since FROM resources WHERE id=?", (key,)).fetchone()
            if operation == "acquire":
                from .admission_legacy import require_open
                require_open(self.root, self.get(db, "meta", 1))
                require(claim["status"] == "running" and owner is None, "Runner unavailable or task is not running")
                db.execute("INSERT INTO resources VALUES(?,?,?)", (key, claim_id, self.clock()))
            else:
                require(owner is not None and owner[0] == claim_id, "Runner belongs to another claim or is unowned")
                require(observed_at >= owner[1], "Exit observation predates runner acquisition")
                db.execute("DELETE FROM resources WHERE id=?", (key,))
            self.event(db, "runner_" + operation, id=claim_id, resource=key, evidenceHash=evidence_hash, observedAt=observed_at)

    def settle(self, claim_id, *, actual, evidence_hash, observed_at, outcome):
        sha(evidence_hash); counters(actual)
        require(outcome in ("not_created", "terminal"), "Explicit reconciled outcome required")
        proof = {"actual": actual, "evidenceHash": evidence_hash, "observedAt": observed_at, "outcome": outcome}
        with self.tx() as db:
            claim = self.get(db, "claims", claim_id)
            if claim["status"] == "settled":
                require(claim["settlement"] == proof, "Settlement already recorded with different evidence")
                return claim
            self.fresh(observed_at, self.get(db, "meta", 1)["policy"])
            require(observed_at >= claim.get("startedAt", claim["createdAt"]), "Terminal observation predates claim")
            require((outcome == "terminal" and claim["native"] is not None) or
                    (outcome == "not_created" and claim["native"] is None and counters(actual) == 0),
                    "Outcome does not match reconciled native identity")
            require(not db.execute("SELECT 1 FROM resources WHERE claim=? AND id LIKE 'runner:%'", (claim_id,)).fetchone(),
                    "Runner still owned; independently observe exit before release")
            # Overrun is truth, not a reason to reject settlement. It blocks next admission.
            claim.update(status="settled", actual=actual, settledAt=self.clock(), settlement=proof)
            self.put(db, "claims", claim_id, claim)
            db.execute("DELETE FROM resources WHERE claim=?", (claim_id,))
            self.event(db, "claim_settled", id=claim_id, evidenceHash=evidence_hash)
            return claim

    def close_allocation(self, allocation_id, evidence_hash):
        sha(evidence_hash)
        with self.tx() as db:
            allocation = self.get(db, "allocations", allocation_id)
            require(not any(c["allocationId"] == allocation_id and c["status"] in HELD for c in self.rows(db, "claims")),
                    "Allocation retains task ownership")
            if not allocation["closed"]:
                allocation.update(closed=True, closedAt=self.clock(), closeEvidenceHash=evidence_hash)
                self.put(db, "allocations", allocation_id, allocation)
                self.event(db, "allocation_closed", id=allocation_id)

    def snapshot(self):
        with self.tx() as db:
            allocations = self.rows(db, "allocations")
            from .admission_legacy import projection
            return {"schemaVersion": 1, "executionAuthorized": False, "dispatchIntegrated": False,
                    "legacy": projection(self, db),
                    "meta": self.get(db, "meta", 1), "claims": self.rows(db, "claims"),
                    "allocations": [{**a, "budget": self.budget(db, a)} for a in allocations],
                    "resources": [{"key": r[0], "claimId": r[1], "since": r[2]}
                                  for r in db.execute("SELECT id,claim,since FROM resources ORDER BY id")],
                    "eventCount": db.execute("SELECT count(*) FROM events").fetchone()[0]}
