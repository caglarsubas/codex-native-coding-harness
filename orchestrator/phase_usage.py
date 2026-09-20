"""Phase-scoped cumulative accounting of supplied evidence, not a token collector."""
import copy
import json
import sqlite3

from .admission import COUNTERS, COVERAGE, counters, exact, identifier, sha, timestamp
from .core import Refusal, canonical, digest, require
from .native_limits import bounded
from .ownership_settlement import OwnershipSettlement

KIND = "phase_usage"
ZERO = {k: 0 for k in COUNTERS}
BOUNDARY = {"executionAuthorized": False, "nativeCallMade": False, "ownershipReleased": False,
            "trustBoundary": "caller_supplied_cumulative_evidence_not_native_attestation"}


def pair(row): return (row["hostId"], row["threadId"])


def exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE name='phase_usage_records'").fetchone() is not None


def record_in(db, key, allocation_id):
    sha(key)
    row = db.execute("SELECT data FROM phase_usage_records WHERE hash=? AND allocation=? AND length(CAST(data AS BLOB))<=256000",
                     (key, allocation_id)).fetchone() if exists(db) else None
    require(row is not None, "Phase usage record missing or oversized")
    doc = json.loads(row[0])
    require(digest(doc) == key and doc["kind"] == KIND, "Phase usage journal integrity changed")
    return doc


def current_in(db, allocation):
    count = db.execute("SELECT count(*) FROM phase_usage_records WHERE allocation=?", (allocation["id"],)).fetchone()[0] if exists(db) else 0
    key = allocation.get("phaseUsageHash")
    if not key:
        require(not count, "Phase usage pointer missing; no legacy fallback")
        return None
    doc = record_in(db, key, allocation["id"])
    require(doc["version"] == count and doc["allocationFingerprint"] == allocation["fingerprint"],
            "Phase usage history or allocation binding changed")
    if doc["previousHash"]:
        require(record_in(db, doc["previousHash"], allocation["id"])["version"]+1 == count, "Phase usage history incomplete")
    return doc


def membership(store, db, allocation):
    """Shared facts whose changes invalidate coverage, not transient idle/running."""
    members = []
    for claim in store.rows(db, "claims"):
        if claim["allocationId"] != allocation["id"]: continue
        members.append({"id": claim["id"], "role": claim["role"], "native": claim["native"],
                        "unresolved": not claim["native"] and bool(claim.get("clientNative") or claim["status"] == "uncertain"),
                        "settlementHash": claim.get("settlementHash"), "settled": claim["status"] == "settled"})
    require(len(members) <= 64, "Phase membership needs explicit archival migration")
    return members


def projection(doc):
    # A newer envelope cannot renew the oldest constituent sample's clock.
    observed_at = min([doc["observedAt"]]+[s["observedAt"] for s in doc["sessions"].values() if s["highWater"] is not None])
    return {"observedAt": observed_at, "evidenceHash": digest(doc), "counters": doc["counters"],
            "coverage": sorted(COVERAGE) if not doc["issues"] else [], "settledClaimIds": doc["settledClaimIds"]}


def enforce(store, db, allocation):
    doc = current_in(db, allocation)
    if doc is None: return
    store.fresh(doc["observedAt"], store.get(db, "meta", 1)["policy"])
    require(not doc["issues"], "Phase usage evidence incomplete; new work remains fenced")
    require(doc["membership"] == membership(store, db, allocation), "Phase membership changed; refresh complete usage")
    require(store.get(db, "meta", 1).get("nativeAccountIdentity") == doc["accountIdentityHash"], "Phase usage account binding changed")
    require(allocation["usage"] == projection(doc), "Phase usage projection diverged; no legacy fallback")


def enforce_context(bridge, db, kernel, allocation):
    doc = current_in(kernel, allocation)
    if doc is None: return
    _, context, _ = PhaseUsage(bridge).context(db, bridge.ledger.get(db, "meta", 1), kernel, allocation["id"])
    require(doc["contextHash"] == digest(context), "Phase usage context changed; refresh complete evidence before effects")


def validate(evidence):
    bounded(evidence, 128000)
    exact(evidence, {"accountIdentityHash", "complete", "includesDescendants", "evidenceHash", "sessions"})
    sha(evidence["accountIdentityHash"]); sha(evidence["evidenceHash"])
    require(type(evidence["complete"]) is bool and type(evidence["includesDescendants"]) is bool, "Explicit usage coverage required")
    require(isinstance(evidence["sessions"], list) and len(evidence["sessions"]) <= 64, "Bounded session inventory required")
    seen = set()
    for row in evidence["sessions"]:
        exact(row, {"hostId", "threadId", "claimId", "role", "parent", "counterEpoch", "baseline", "observedAt", "evidenceHash", "counters", "complete"})
        identifier(row["hostId"]); identifier(row["threadId"])
        if row["claimId"] is not None: identifier(row["claimId"])
        require(row["role"] in ("brain", "worker", "reviewer", "nested"), "Invalid phase usage role")
        if row["parent"] is not None:
            exact(row["parent"], {"hostId", "threadId"})
            for value in row["parent"].values(): identifier(value)
        sha(row["counterEpoch"]); sha(row["evidenceHash"]); timestamp(row["observedAt"])
        require(type(row["complete"]) is bool, "Explicit session completeness required")
        base = row["baseline"]; exact(base, {"observedAt", "evidenceHash", "counters"})
        timestamp(base["observedAt"]); sha(base["evidenceHash"]); counters(base["counters"])
        require(base["observedAt"] <= row["observedAt"], "Baseline follows current sample")
        if row["counters"] is not None: counters(row["counters"])
        require(pair(row) not in seen, "Duplicate phase usage session")
        seen.add(pair(row))


class PhaseUsage:
    def __init__(self, bridge):
        self.bridge, self.store, self.ledger = bridge, bridge.store, bridge.ledger
        self.terminal = OwnershipSettlement(bridge)

    def context(self, db, meta, kernel, allocation_id):
        identifier(allocation_id)
        allocation = self.store.get(kernel, "allocations", allocation_id)
        require(allocation["spec"]["workspaceId"] == self.bridge.workspace_id and
                allocation["fingerprint"] == digest(allocation["spec"]), "Foreign or changed phase allocation")
        members = membership(self.store, kernel, allocation)
        required = [{"hostId": "local", "threadId": meta["brainId"], "claimId": None, "role": "brain"}]
        finals = {}; issues = []; pending = []
        for member in members:
            worker, intent = self.bridge.intent_in(db, member["id"])
            claim = self.bridge.bound_claim_in(kernel, intent)
            require(claim["allocationId"] == allocation_id, "Claim phase changed")
            terminal_record = None
            if member["settled"]:
                from .creation_recovery import CreationRecovery
                terminal = self.terminal if member["native"] else CreationRecovery(self.bridge)
                _, terminal_record = terminal.record_in(kernel, intent)
                require(terminal_record is not None, "Exact terminal accounting required")
                _, _, state = terminal.history_in(kernel, intent, terminal_record["priorClaim"])
            elif claim["status"] == "reserved" and not claim.get("nativeLifecycleHash"):
                require(claim["native"] is None and not claim.get("clientNative"), "Reserved task has unexpected native identity")
                state = {"creation": None}
            else:
                _, _, state = self.terminal.lifecycle.journal_in(kernel, intent, claim)
            creation = state["creation"] if state else None
            if creation and creation.get("clientThreadId"): pending.append(creation["clientThreadId"])
            if member["native"]:
                root = pair(member["native"])
                for key in sorted(self.terminal.known_descendants(db, root)):
                    required.append({"hostId": key[0], "threadId": key[1], "claimId": member["id"],
                                     "role": member["role"] if key == root else "descendant"})
            elif creation or worker["status"] == "settled":
                if not member["settled"]: issues.append("unresolved_native_creation:"+member["id"])
            elif worker.get("nativeHandoffCheckHash"):
                # The one-use send check is already consumed. The tool may have
                # executed; do not treat the still-unbound claim as uncreated.
                issues.append("unobserved_native_send:"+member["id"])
            if member["settled"]:
                record = terminal_record
                finals[member["id"]] = record
                for row in record["request"]["usage"].get("sessions", []):
                    if not any(pair(r) == pair(row) for r in required):
                        required.append({"hostId": row["hostId"], "threadId": row["threadId"], "claimId": member["id"], "role": "descendant"})
        # Reject known other roots/brains, including those outside this phase.
        # The outer bridge lock already holds the registry transaction. A
        # read-only connection avoids a nested writer/lock while retaining that
        # exclusion; no native inventory or private Codex database is accessed.
        registry_db = sqlite3.connect(self.bridge.registry.db.as_uri()+"?mode=ro", uri=True)
        try: brains = [r[0] for r in registry_db.execute("SELECT brain FROM workspaces")]
        finally: registry_db.close()
        foreign = []
        for claim in self.store.rows(kernel, "claims"):
            if claim["allocationId"] != allocation_id:
                if claim["native"]: foreign.append(claim["native"])
                foreign.extend(claim.get("settledNativeIdentities", []))
        for other in self.store.rows(kernel, "allocations"):
            if other["id"] == allocation_id: continue
            previous = current_in(kernel, other)
            if previous:
                foreign.extend({k: s["binding"][k] for k in ("hostId", "threadId")} for s in previous["sessions"].values() if s["binding"]["role"] != "brain")
        foreign = [{"hostId": h, "threadId": t} for h, t in sorted({pair(r) for r in foreign})]
        value = {"allocationId": allocation_id, "allocationFingerprint": allocation["fingerprint"],
                 "ledgerIdentity": self.bridge.ledger_id, "brainId": meta["brainId"], "membership": members,
                 "required": required, "pendingClientIds": sorted(set(pending)), "foreignRoots": foreign,
                 "otherBrains": sorted(b for b in brains if b != meta["brainId"]),
                 "accountIdentityHash": self.store.get(kernel, "meta", 1).get("nativeAccountIdentity"), "issues": issues}
        return allocation, value, finals

    def assess(self, allocation, context, finals, prior, evidence, observed_at, policy):
        validate(evidence)
        issues = list(context["issues"]); sessions = {pair(s): s for s in evidence["sessions"]}
        def fresh(at): return 0 <= self.store.clock()-at <= policy["maxObservationAgeSeconds"] and at <= observed_at
        if not evidence["complete"] or not evidence["includesDescendants"]: issues.append("inventory_incomplete")
        if evidence["accountIdentityHash"] != context["accountIdentityHash"]: issues.append("account_identity_unconfirmed")
        if prior and evidence["accountIdentityHash"] != prior["accountIdentityHash"]: issues.append("account_identity_changed")
        required = {pair(r): r for r in context["required"]}
        if not set(required) <= set(sessions): issues.append("required_session_missing")
        roots = {m["id"]: pair(m["native"]) for m in context["membership"] if m["native"]}
        pinned = copy.deepcopy(prior["sessions"] if prior else {})
        supplied = set()
        for key, row in sessions.items():
            sid = digest(key); supplied.add(sid)
            binding = {k: row[k] for k in ("hostId", "threadId", "claimId", "role", "parent", "counterEpoch", "baseline")}
            require(row["hostId"] == "local" and row["threadId"] not in context["pendingClientIds"] and
                    row["threadId"] not in context["otherBrains"] and key not in {pair(r) for r in context["foreignRoots"]}, "Foreign or pending native identity")
            if key == ("local", context["brainId"]):
                require(row["role"] == "brain" and row["claimId"] is None and row["parent"] is None, "Exact brain usage binding required")
                require(row["baseline"]["observedAt"] <= allocation["createdAt"], "Brain baseline must precede allocation; no retroactive reset")
            else:
                root = roots.get(row["claimId"])
                require(root is not None and row["role"] != "brain", "Usage has no owned native root")
                require(row["baseline"]["counters"] == ZERO, "Worker usage covers its full task lifetime")
                if key == root:
                    require(row["parent"] is None and row["role"] == required[key]["role"], "Root role or parent changed")
                else:
                    require(row["role"] in ("nested", "reviewer"), "Invalid descendant role")
                    cursor, seen = key, set()
                    while cursor != root:
                        require(cursor in sessions and cursor not in seen and sessions[cursor]["claimId"] == row["claimId"] and sessions[cursor]["parent"] is not None,
                                "Foreign or cyclic phase usage ancestry")
                        seen.add(cursor); cursor = pair(sessions[cursor]["parent"])
            if key in required: require(required[key]["claimId"] == row["claimId"], "Retained task ownership changed")
            old = pinned.get(sid)
            if old and old["binding"] != binding:
                issues.append("session_binding_or_epoch_changed:"+sid); continue
            old = old or {"binding": binding, "highWater": None, "observedAt": 0}
            pinned[sid] = old
            value = row["counters"]
            if not row["complete"] or value is None or not fresh(row["observedAt"]) or row["observedAt"] < allocation["createdAt"]:
                issues.append("session_usage_unavailable:"+sid); continue
            base = row["baseline"]["counters"]
            floor = old["highWater"] or base
            if row["observedAt"] < old["observedAt"] or any(value[k] < floor[k] or value[k] < base[k] for k in COUNTERS):
                issues.append("counter_regressed:"+sid); continue
            delta = {k: value[k]-base[k] for k in COUNTERS}
            try: counters(delta)
            except Refusal:
                issues.append("counter_delta_invalid:"+sid); continue
            old.update(highWater=value, observedAt=row["observedAt"], evidenceHash=row["evidenceHash"])
        if not set(pinned) <= supplied: issues.append("previous_session_missing")
        total = dict(ZERO)
        for row in pinned.values():
            if row["highWater"]:
                for k in COUNTERS: total[k] += row["highWater"][k]-row["binding"]["baseline"]["counters"][k]
        floor = prior["counters"] if prior else (allocation["usage"] or {}).get("counters", ZERO)
        if any(total[k] < floor[k] for k in COUNTERS): issues.append("phase_counter_regressed")
        total = {k: max(total[k], floor[k]) for k in COUNTERS}; counters(total)
        included = set(prior["settledClaimIds"] if prior else (allocation["usage"] or {}).get("settledClaimIds", []))
        for cid, record in finals.items():
            final_rows = {pair(s): s for s in record["request"]["usage"].get("sessions", [])}
            owned = {k: s for k, s in sessions.items() if s["claimId"] == cid}
            valid = set(owned) == set(final_rows) and record["at"] <= observed_at
            for key, row in owned.items():
                final = final_rows.get(key)
                valid = valid and final is not None and row["counterEpoch"] == final["counterEpoch"] and row["counters"] == final["counters"] and row["observedAt"] >= record["at"]
            if valid and not issues: included.add(cid)
            elif not valid: issues.append("settled_usage_mismatch:"+cid)
        return {"sessions": pinned, "counters": total, "issues": sorted(set(issues)), "settledClaimIds": sorted(included)}

    def state(self, token, allocation_id):
        with self.bridge.locked(token) as (db, meta):
            with self.store.tx() as kernel:
                allocation, context, _ = self.context(db, meta, kernel, allocation_id)
                doc = current_in(kernel, allocation)
                issues = list(doc["issues"]) if doc else ["phase_usage_not_observed"]
                if doc:
                    if doc["contextHash"] != digest(context): issues.append("phase_context_changed")
                    if allocation["usage"] != projection(doc): issues.append("phase_projection_diverged")
                    try:
                        policy = self.store.get(kernel, "meta", 1)["policy"]
                        self.store.fresh(doc["observedAt"], policy)
                        self.store.fresh(projection(doc)["observedAt"], policy)
                    except Refusal: issues.append("phase_usage_stale")
                known = []; by_role = {}
                for session in (doc["sessions"] if doc else {}).values():
                    binding, high = session["binding"], session["highWater"]
                    delta = {k: high[k]-binding["baseline"]["counters"][k] for k in COUNTERS} if high is not None else None
                    known.append({**binding, "cumulativeCounters": high, "phaseCounters": delta,
                                  "observedAt": session["observedAt"], "evidenceHash": session.get("evidenceHash")})
                    if delta is not None:
                        role = binding["role"]; by_role[role] = by_role.get(role, 0)+counters(delta)
                return {"allocationId": allocation_id, "expectedHash": digest(doc) if doc else None, "contextHash": digest(context),
                        "requiredSessions": context["required"], "accountIdentityHash": context["accountIdentityHash"],
                        "knownSessions": sorted(known, key=pair), "knownRawTokensByRole": by_role,
                        "observedAt": doc["observedAt"] if doc else None,
                        "oldestSampleAt": projection(doc)["observedAt"] if doc else None,
                        "status": "needs_evidence" if issues else "usage_observed",
                        "issues": sorted(set(issues)), "budget": self.store.budget(kernel, allocation),
                        **BOUNDARY}

    def record(self, token, allocation_id, request):
        bounded(request, 128000)
        exact(request, {"id", "expectedHash", "contextHash", "observedAt", "evidence"})
        identifier(request["id"]); sha(request["contextHash"]); timestamp(request["observedAt"])
        if request["expectedHash"] is not None: sha(request["expectedHash"])
        validate(request["evidence"])
        fingerprint = digest(request)
        with self.bridge.locked(token) as (db, meta):
            with self.store.tx() as kernel:
                allocation, context, finals = self.context(db, meta, kernel, allocation_id)
                prior = current_in(kernel, allocation)
                row = kernel.execute("SELECT hash FROM phase_usage_records WHERE allocation=? AND request=?", (allocation_id, request["id"])).fetchone() if exists(kernel) else None
                if row:
                    old = record_in(kernel, row[0], allocation_id)
                    require(old["fingerprint"] == fingerprint, "Phase usage request ID reused with different content")
                    return {"recordHash": row[0], "currentHash": digest(prior), "historical": row[0] != digest(prior), **BOUNDARY}
                require(request["expectedHash"] == allocation.get("phaseUsageHash") and request["contextHash"] == digest(context), "Phase usage source changed; inspect again")
                require(not allocation["closed"], "Phase allocation is closed")
                self.store.fresh(request["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
                lower = max(allocation["createdAt"], (allocation["usage"] or {}).get("observedAt", 0), prior["observedAt"] if prior else 0)
                require(request["observedAt"] > lower, "Phase observation moved backwards")
                result = self.assess(allocation, context, finals, prior, request["evidence"], request["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
                doc = {"kind": KIND, "schemaVersion": 1, "allocationId": allocation_id, "allocationFingerprint": allocation["fingerprint"],
                       "accountIdentityHash": prior["accountIdentityHash"] if prior else request["evidence"]["accountIdentityHash"],
                       "contextHash": digest(context), "membership": context["membership"], "observedAt": request["observedAt"],
                       "evidenceHash": digest(request["evidence"]), "sourceEvidenceHash": request["evidence"]["evidenceHash"],
                       "fingerprint": fingerprint, "version": prior["version"]+1 if prior else 1,
                       "previousHash": allocation.get("phaseUsageHash"), **result}
                require(doc["version"] <= 10000 and len(doc["sessions"]) <= 64, "Phase usage history needs explicit archival migration")
                bounded(doc, 256000)
                kernel.execute("CREATE TABLE IF NOT EXISTS phase_usage_records(hash TEXT PRIMARY KEY, allocation TEXT NOT NULL, request TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(allocation,request))")
                kernel.execute("INSERT INTO phase_usage_records VALUES(?,?,?,?)", (digest(doc), allocation_id, request["id"], canonical(doc)))
                allocation.update(phaseUsageHash=digest(doc), usage=projection(doc))
                self.store.put(kernel, "allocations", allocation_id, allocation)
                self.store.event(kernel, "phase_usage_observed", allocationId=allocation_id, recordHash=digest(doc))
                return {"recordHash": digest(doc), "currentHash": digest(doc), "historical": False, "issues": doc["issues"],
                        **BOUNDARY}
