"""Explicit loaded-thread policy reads; never loading, waking or authorizing.

Only an operator-reviewed binding opting into the repaired native contract can
use this adapter. Old resume acknowledgements remain unknown. The public report
describes loaded defaults, not active-step grants, OS enforcement or terminals.
"""
import copy
import re
import time

from .core import Refusal, digest, require
from .native_read_client import ReadProxy

PROTOCOL = "loaded_thread_policy_v1"
METHOD = "thread/effectivePolicy/read"
BOUNDARY = {"nativeMutationMade": False, "executionAuthorized": False,
            "terminalSafetyVerified": False, "historicalCleanupVerified": False,
            "usageMeasured": False, "ownershipReleased": False}
POLICY_FIELDS = {"scope", "cwd", "model", "approvalPolicy", "approvalsReviewer",
                 "sandbox", "codeModeOffEnforced", "effectiveToolMode"}
SANDBOX_FIELDS = {"type", "writableRoots", "networkAccess", "excludeTmpdirEnvVar", "excludeSlashTmp"}
EVIDENCE_FIELDS = {"version", "protocol", "bindingHash", "executableHash", "sourceCommit", "sourceTree",
                   "brainId", "commandId", "observedAt", "responseHash", "reported"}
REPORTED_FIELDS = {"scope", "sandbox", "approvalPolicy", "approvalsReviewer",
                   "codeModeOffEnforced", "effectiveToolMode"}


def validate_contract(value):
    require(isinstance(value, dict) and set(value) == {"protocol", "sourceCommit", "sourceTree"} and
            value["protocol"] == PROTOCOL and all(isinstance(value[k], str) and
            re.fullmatch(r"[0-9a-f]{40}", value[k]) for k in ("sourceCommit", "sourceTree")),
            "Exact reviewed native policy protocol and source pins required")
    return value


def reported(response, brain_id, cwd):
    """Validate the actual native versioned response, not a request/config echo."""
    require(isinstance(response, dict) and set(response) == {"version", "threadId", "policy"} and
            type(response["version"]) is int and response["version"] == 1 and
            response["threadId"] == brain_id, "Native policy response identity or version differs")
    policy = response["policy"]
    if policy is None:
        return None  # Unloaded or missing runtime: never load to make it known.
    require(isinstance(policy, dict) and set(policy) == POLICY_FIELDS and
            policy["scope"] == "loadedThreadDefaults" and policy["cwd"] == cwd and
            isinstance(policy["model"], str) and 0 < len(policy["model"]) <= 256 and
            type(policy["codeModeOffEnforced"]) is bool and
            policy["effectiveToolMode"] in (None, "direct"), "Unsupported loaded-thread policy response")
    sandbox = policy["sandbox"]
    require(isinstance(sandbox, dict) and set(sandbox) == SANDBOX_FIELDS and
            sandbox["type"] == "workspaceWrite" and isinstance(sandbox["writableRoots"], list) and
            len(sandbox["writableRoots"]) <= 32 and
            all(isinstance(root, str) and root == cwd for root in sandbox["writableRoots"]) and
            all(type(sandbox[k]) is bool for k in
                ("networkAccess", "excludeTmpdirEnvVar", "excludeSlashTmp")),
            "Native sandbox defaults are unsupported or exceed the reviewed checkout")
    require(sandbox["networkAccess"] is False, "Network access is outside this policy qualification")
    require(policy["approvalPolicy"] in ("on-request", "never", "untrusted", "on-failure") and
            policy["approvalsReviewer"] in ("user", "auto_review", "guardian_subagent"),
            "Native approval defaults are unsupported")
    return {"scope": policy["scope"], "sandbox": sandbox["type"],
            "approvalPolicy": policy["approvalPolicy"], "approvalsReviewer": policy["approvalsReviewer"],
            "codeModeOffEnforced": policy["codeModeOffEnforced"], "effectiveToolMode": policy["effectiveToolMode"]}


def matches(value):
    return (isinstance(value, dict) and set(value) == REPORTED_FIELDS and
            value["scope"] == "loadedThreadDefaults" and value["sandbox"] == "workspaceWrite" and
            value["approvalPolicy"] == "on-request" and value["approvalsReviewer"] == "user" and
            value["codeModeOffEnforced"] is True and value["effectiveToolMode"] == "direct")


def collect(proxy, binding, brain_id, command_id):
    """Fixed repeated reads on an already reviewed/owned connection only."""
    record = binding["brains"][brain_id]
    contract = validate_contract(record.get("policyEvidence"))
    first = proxy._rpc(METHOD, {"threadId": brain_id})
    first_reported = reported(first, brain_id, record["cwd"])
    second = proxy._rpc(METHOD, {"threadId": brain_id})
    second_reported = reported(second, brain_id, record["cwd"])
    require(first == second and first_reported == second_reported,
            "Native loaded policy changed between samples")
    return {"version": 1, "protocol": PROTOCOL, "bindingHash": digest(binding),
            "executableHash": binding["endpoint"]["sha256"],
            "sourceCommit": contract["sourceCommit"], "sourceTree": contract["sourceTree"],
            "brainId": brain_id, "commandId": command_id, "observedAt": time.time(),
            "responseHash": digest(second), "reported": second_reported}


def valid_retained(evidence, note, profile, command_id, brain_id):
    """Only future bound owned-turn evidence; no old-profile backfill or fallback."""
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS | {"nativeTurnId"}:
        return False
    contract = note.get("nativePolicyContract")
    try:
        validate_contract(contract)
    except Refusal:
        return False
    return (type(evidence["version"]) is int and evidence["version"] == 1 and
            note.get("status") == "accepted" and note.get("nativeDelivery") == "owned_turn_start" and
            evidence["protocol"] == PROTOCOL and evidence["sourceCommit"] == contract["sourceCommit"] and
            evidence["sourceTree"] == contract["sourceTree"] and
            evidence["bindingHash"] == note.get("hostBindingHash") == profile.get("bindingHash") and
            evidence["brainId"] == brain_id and evidence["commandId"] == command_id and
            evidence["nativeTurnId"] == note.get("nativeTurnId") == profile.get("nativeTurnId") and
            type(evidence["observedAt"]) in (int, float) and
            type(profile.get("observedAt")) in (int, float) and type(note.get("attemptedAt")) in (int, float) and
            profile["observedAt"] <= evidence["observedAt"] <= note["attemptedAt"] + 30 and
            all(isinstance(evidence[k], str) and re.fullmatch(r"[0-9a-f]{64}", evidence[k])
                for k in ("bindingHash", "executableHash", "responseHash")) and
            evidence["executableHash"] == note.get("nativePolicyExecutableHash") and
            matches(evidence["reported"]))


class PolicyReadProxy(ReadProxy):
    """No caller-authored targets or native writes, including inspection load."""
    def __init__(self, endpoint, project_id, brain_id):
        super().__init__(endpoint)
        self.project_id, self.brain_id = project_id, brain_id

    def call(self, method, params):
        if method == "account/read":
            require(params == {"refreshToken": False}, "Non-refreshing native account read only")
            return self._rpc(method, params)
        if method == "project/read":
            require(params == {"projectId": self.project_id}, "Exact bound project required")
            return self._rpc(method, params)
        require(method in ("thread/read", METHOD) and isinstance(params, dict) and
                params.get("threadId") == self.brain_id, "Exact bound brain policy reads only")
        return super().call(method, params)


def inspect(registry, ledger, host):
    """Owner-requested diagnostic. No ledger writes and no admission authority."""
    from .native_project_assignment import _scope
    from .standard_native_observation import _brain_identity
    from .standard import PROTOCOL as STANDARD_PROTOCOL, read_db
    from .native_read_client import validate_endpoint
    from .enrollment import fence_exists, record_in
    require(host is not None and not host._closed, "Reviewed owned host is unavailable")
    with registry.tx() as registry_db:
        require(record_in(registry_db) is None and not fence_exists(ledger.root),
                "Enrolled projects cannot use standard policy inspection")
    with read_db(ledger.db) as db:
        meta = ledger.get(db, "meta", 1)
        run = meta.get("standardRun")
        require(run and run.get("protocol") == STANDARD_PROTOCOL and run["brainId"] == meta["brainId"] and
                not meta.get("admissionBinding"), "Exact standard run required for policy inspection")
        repos = ledger.all(db, "repos")
        require(repos and all(r.get("policyProfile") == "standard" for r in repos), "Strict projects are not supported")
        context_hash = digest(meta)
    binding = copy.deepcopy(host.binding)
    scope = _scope(registry, ledger.workspace_id, binding)
    require(scope["root"] == ledger.root and scope["brainId"] == meta["brainId"] and
            scope["ledgerRevision"] == meta["revision"], "Registered policy scope changed")
    contract = binding["brains"][scope["brainId"]].get("policyEvidence")
    base = {"runId": run["id"], "revision": meta["revision"], "checkedAt": time.time(),
            "policyVerified": False, "boundary": copy.deepcopy(BOUNDARY)}
    if contract is None:
        return {**base, "status": "unsupported", "detail": "This reviewed host has no effective-policy contract. A newly reviewed repaired host is required; no native request was sent."}
    validate_contract(contract)
    authentication = None
    with PolicyReadProxy(binding["endpoint"], scope["projectId"], scope["brainId"]) as proxy:
        before = _brain_identity(proxy, scope, include_flags=True)
        evidence = collect(proxy, binding, scope["brainId"], None)
        if binding["brains"][scope["brainId"]].get("nativeTaskBackend"):
            from .native_auth_readiness import inspect as inspect_authentication
            authentication = inspect_authentication(proxy)
        after = _brain_identity(proxy, scope, include_flags=True)
    with read_db(ledger.db) as db:
        require(digest(ledger.get(db, "meta", 1)) == context_hash, "Run, Pause or controller changed during policy inspection")
    with registry.tx() as registry_db:
        require(record_in(registry_db) is None and not fence_exists(ledger.root), "Enrollment changed during inspection")
    validate_endpoint(binding["endpoint"])
    require(host.binding == binding and not host._closed and
            _scope(registry, ledger.workspace_id, binding) == scope and before == after,
            "Host, catalog or native brain changed during policy inspection")
    value = evidence["reported"]
    # A loaded report must not coexist with an unloaded/unknown activity read.
    verified = matches(value) and after["nativeStatus"] in ("active", "idle")
    result = {**base, "checkedAt": evidence["observedAt"],
            "status": "matching" if verified else "unknown" if value is None else "mismatch",
            "policyVerified": verified, "reported": value, "sourceCommit": contract["sourceCommit"],
            "sourceTree": contract["sourceTree"], "executableHash": evidence["executableHash"],
            "detail": ("Loaded-thread defaults match the reviewed policy. Terminal safety, historical effects and Resume remain separate." if verified else
                       "Loaded native policy is unknown or differs from review. No load, turn, replay or Resume was sent.")}
    if authentication is not None:
        result["authentication"] = authentication
        if not authentication["ready"]:
            result["detail"] += " The native host also needs sign-in before new work. No login, credential copy or token refresh was sent."
    return result
