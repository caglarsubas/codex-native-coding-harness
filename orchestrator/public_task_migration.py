"""Read-only same-run public-backend migration assessment, never a permit.

Old endpoints are immutable bytes only. A current policy or empty replacement
tracker cannot qualify historical effects or override an original Play guard.
"""
import time

from . import standard
from .app_server_wake import _read_binding, load_binding
from .core import ACTIVE, Refusal, digest, require
from .enrollment import fence_exists, record_in
from .native_policy_evidence import collect, matches
from .native_project_assignment import _scope
from .public_native_tasks import validate_contract
from .standard_native_observation import TaskReadProxy, _brain_identity, _terminals


def assess(registry, ledger, run_id, current_path, original_path):
    """Explicit metadata reads on the already separately reviewed current host.

    The supplied current binding is not installed and no source result can be
    submitted to Resume. All history remains subject to its original contract.
    """
    original = _read_binding(original_path)  # No old endpoint validation/connection.
    current = load_binding(current_path)
    with registry.tx() as registry_db, standard.read_db(ledger.db) as db:
        require(record_in(registry_db) is None and not fence_exists(ledger.root), "Strict enrollment refuses migration")
        meta = ledger.get(db, "meta", 1)
        run = meta.get("standardRun")
        require(meta.get("schemaVersion") == 4 and run and run["id"] == run_id and run["protocol"] == standard.PROTOCOL and
                run["brainId"] == meta["brainId"] and run["status"] == "paused" and
                meta.get("paused") is True and not meta.get("controller") and not meta.get("runner") and
                not meta.get("admissionBinding"), "Exact unowned paused standard run required")
        repos = ledger.all(db, "repos")
        require(repos and all(r["policyProfile"] == "standard" for r in repos) and not run["tasks"] and
                not any(w["status"] in ACTIVE for w in ledger.all(db, "workers")) and
                not any(q["status"] == "approved" for q in ledger.all(db, "queue")),
                "Unresolved registered work cannot migrate")
        require(not any(m.get("status") in ("prepared", "issued", "uncertain") for m in run.get("merges", [])),
                "Unresolved merge retains ownership")
        commands = ledger.all(db, "commands")
        require(not any(c["status"] in ("queued", "processing") for c in commands), "Pending control retains ownership")
        play = [c for c in commands if c["kind"] == "standard_play" and c.get("payload", {}).get("runId") == run_id]
        require(len(play) == 1 and play[0]["status"] == "completed" and
                (play[0].get("notification") or {}).get("hostBindingHash") == digest(original),
                "Exact immutable original Play and binding required")
        brain_id = meta["brainId"]
        before = original["brains"].get(brain_id)
        after = current["brains"].get(brain_id)
        require(before and after and all(before.get(k) == after.get(k) for k in
                ("workspaceId", "cwd", "projectId", "catalogProjectId", "nativePolicy")) and
                after["workspaceId"] == ledger.workspace_id,
                "Brain, checkout, both project identities or native policy changed")
        require(len(current["brains"]) == 1, "Public migration is scoped to exactly one brain")
        validate_contract(after.get("nativeTaskBackend"), after.get("policyEvidence"))
        context_hash = digest(meta)
        original_hash = digest(play[0])
    scope = _scope(registry, ledger.workspace_id, current)
    issues = ["separate_same_run_transition_not_reviewed", "original_native_policy_unverified",
              "historical_terminal_and_effect_coverage_unknown"]
    if time.time() >= run["expiresAt"]:
        issues.append("original_phase_duration_expired")
    policy, native, terminals = None, None, None
    try:
        with TaskReadProxy(current["endpoint"], scope["projectId"], [brain_id]) as proxy:
            first = _brain_identity(proxy, scope, include_flags=True)
            policy = collect(proxy, current, brain_id, None)
            second = _brain_identity(proxy, scope, include_flags=True)
            require(first == second, "Brain activity changed during migration assessment")
            native = second["nativeStatus"]
            if native == "idle" and second["activeFlags"] == []:
                samples = [_terminals(proxy, brain_id) for _ in range(2)]
                last = _brain_identity(proxy, scope, include_flags=True)
                require(samples[0] == samples[1] and last == second, "Current terminal view changed")
                terminals = "running" if samples[1] else "none"
            else:
                issues.append("current_loaded_idle_and_terminal_evidence_unknown")
    except (OSError, Refusal, ValueError, KeyError, TypeError):
        issues.append("current_native_read_unavailable")
    with standard.read_db(ledger.db) as db:
        require(digest(ledger.get(db, "meta", 1)) == context_hash, "Pilot changed during migration assessment")
    require(_read_binding(original_path) == original and load_binding(current_path) == current and
            _scope(registry, ledger.workspace_id, current) == scope, "Binding or catalog changed")
    with registry.tx() as registry_db:
        require(record_in(registry_db) is None and not fence_exists(ledger.root), "Enrollment changed during assessment")
    return {"version": 1, "runId": run_id, "status": "blocked", "migrationQualified": False,
            "checkedAt": time.time(), "contextHash": context_hash, "originalPlayHash": original_hash,
            "originalBindingHash": digest(original), "candidateBindingHash": digest(current),
            "candidatePolicyMatches": bool(policy and matches(policy["reported"])),
            "currentNativeStatus": native or "unknown", "currentTrackedTerminals": terminals or "unknown",
            "issues": issues, "preservedRunHash": digest(run),
            "boundary": {"nativeMutationMade": False, "bindingInstalled": False, "originalPlayChanged": False,
                         "usageReset": False, "historicalCleanupVerified": False, "resumeAuthorized": False,
                         "pilotAccepted": False}}
