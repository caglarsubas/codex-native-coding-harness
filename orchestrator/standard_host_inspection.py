"""Private owned-host handoff and explicit brain-only metadata inspection.

Never discovers, loads, resumes or starts a native thread. The handoff is an
immutable copy of the operator-reviewed binding, not a new binding or authority.
"""
import copy
import os
import time

from .app_server_wake import _read_binding, load_binding, NATIVE_APPROVAL_POLICY
from .core import canonical, digest, require
from .native_project_assignment import _scope
from .standard_native_observation import _base_in, _brain_identity, TaskReadProxy
from . import standard

VERSION = 1
BOUNDARY = {"nativeMutationMade": False, "executionAuthorized": False,
            "approvalAuthorized": False, "taskTreeComplete": False,
            "tokenUsageMeasured": False, "ownershipReleased": False}


def binding_file(ledger, binding_hash):
    from .admission import sha
    sha(binding_hash)
    return ledger.root / ("owned-host-binding-" + binding_hash + ".json")


def retain_binding(ledger, binding):
    """Called only inside the existing committed notification transaction.

    No collection, endpoint discovery or review renewal occurs here. Private
    bytes are never placed in snapshots, browser projections or inference.
    """
    key = digest(binding)
    path = binding_file(ledger, key)
    require(ledger.root.resolve(strict=True) == ledger.root and
            ledger.root.stat().st_uid == os.getuid() and not ledger.root.stat().st_mode & 0o077,
            "Exact private owner ledger directory required")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        require(_read_binding(path) == binding, "Private owned host handoff changed")
    else:
        with os.fdopen(fd, "w") as stream:
            stream.write(canonical(binding))
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(ledger.root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        require(_read_binding(path) == binding, "Private owned host handoff changed")
    return key


def resume_profile(binding, brain_id, command_id, response):
    """Project only closed metadata from the successful resume response.

    The installed protocol reports sandbox/approval/reviewer, but not Code Mode.
    A successful config override remains an acknowledgement, not attestation.
    """
    response = response if isinstance(response, dict) else {}
    sandbox = response.get("sandbox")
    sandbox_type = sandbox.get("type") if isinstance(sandbox, dict) else None
    approval = response.get("approvalPolicy")
    reviewer = response.get("approvalsReviewer")
    return {"version": VERSION, "bindingHash": digest(binding), "brainId": brain_id, "commandId": command_id,
            "observedAt": time.time(), "requested": copy.deepcopy(binding["brains"][brain_id]["nativePolicy"]),
            "resumeAcknowledged": True,
            "reported": {"sandbox": sandbox_type if sandbox_type in
                         ("workspaceWrite", "readOnly", "dangerFullAccess", "externalSandbox") else None,
                         "approvalPolicy": approval if approval in ("on-request", "never", "untrusted") else None,
                         "approvalsReviewer": reviewer if reviewer in
                         ("user", "auto_review", "guardian_subagent") else None,
                         "codeMode": None}}


def _context(registry, ledger, token, run_id, command_id):
    from .notification import NOTIFY_KINDS
    with registry.tx() as registry_db, standard.read_db(ledger.db) as db:
        meta, run, _ = _base_in(registry, ledger, token, registry_db, db, run_id)
        commands = ledger.all(db, "commands")
        command = next((c for c in commands if c["id"] == command_id), None)
        require(command and command["kind"] in NOTIFY_KINDS, "Exact owned standard control required")
        require(command["status"] in ("processing", "completed"), "Receive this exact control before host inspection")
        note = command.get("notification") or {}
        profile = note.get("nativeResumeProfile")
        stream = note.get("nativeThreadObservation") or {}
        require(note.get("brainId") == meta["brainId"] and note.get("status") == "accepted" and
                note.get("nativeDelivery") == "owned_turn_start" and
                isinstance(note.get("nativeTurnId"), str) and
                stream.get("rootThreadId") == meta["brainId"] and stream.get("streamStatus") == "open" and
                note.get("nativeTurnStatus") not in ("completed", "interrupted", "failed", "unconfirmed"),
                "Current subscribed owned turn required; old delivery is not current evidence")
        require(isinstance(profile, dict) and profile.get("version") == VERSION and
                profile.get("brainId") == meta["brainId"] and
                profile.get("commandId") == command_id and profile.get("nativeTurnId") == note["nativeTurnId"] and
                profile.get("bindingHash") == note.get("hostBindingHash") and
                profile.get("requested") == NATIVE_APPROVAL_POLICY and profile.get("resumeAcknowledged") is True,
                "Current owned resume profile is unavailable or changed")
        owned = [c for c in commands if (c.get("notification") or {}).get("brainId") == meta["brainId"]]
        require(max(owned, key=lambda c: c["notification"].get("attemptedAt", 0))["id"] == command_id,
                "A newer owned control superseded this host handoff")
        # Conversations/decisions do not have runId in their typed payload.
        # The trusted notification transaction pins the current run for both.
        require(note.get("hostRunId") == run["id"] and
                command.get("payload", {}).get("runId", run["id"]) == run["id"],
                "Host handoff belongs to another run")
        return {"revision": meta["revision"], "runHash": digest(run), "runStatus": run["status"],
                "brainId": meta["brainId"], "bindingHash": note["hostBindingHash"],
                "nativeTurnId": note["nativeTurnId"], "profile": copy.deepcopy(profile),
                "approvals": copy.deepcopy(note.get("nativeApprovals", []))}


def inspect(registry, ledger, token, run_id, command_id):
    """Explicit, repeated project/read + exact thread/read; no ledger write."""
    context = _context(registry, ledger, token, run_id, command_id)
    path = binding_file(ledger, context["bindingHash"])
    binding = load_binding(path)
    require(digest(binding) == context["bindingHash"], "Reviewed owned host binding changed")
    scope = _scope(registry, ledger.workspace_id, binding)
    started = time.time()
    with TaskReadProxy(binding["endpoint"], scope["projectId"], [scope["brainId"]]) as proxy:
        before = _brain_identity(proxy, scope, include_flags=True)
        after = _brain_identity(proxy, scope, include_flags=True)
    require(before == after and after["nativeStatus"] == "active",
            "Current native brain activity or membership is unknown or changed")
    require(load_binding(path) == binding and _scope(registry, ledger.workspace_id, binding) == scope and
            _context(registry, ledger, token, run_id, command_id) == context,
            "Host, catalog, Pause, run or approval context changed during inspection")
    reported = context["profile"]["reported"]
    issues = []
    if after["activeFlags"] is None:
        issues.append("native_active_flags_unavailable")
    elif after["activeFlags"]:
        issues.append("native_approval_or_user_input_pending")
    if reported.get("sandbox") != "workspaceWrite":
        issues.append("native_sandbox_unavailable_or_different")
    if reported.get("approvalPolicy") != "on-request":
        issues.append("native_approval_policy_unavailable_or_different")
    if reported.get("approvalsReviewer") != "user":
        issues.append("native_approval_reviewer_unavailable_or_different")
    if any(a.get("status") not in ("resolved", "resolved_without_response") for a in context["approvals"]):
        issues.append("unresolved_recorded_native_approval")
    return {"version": VERSION, "workspaceId": ledger.workspace_id, "runId": run_id,
            "commandId": command_id, "brainId": context["brainId"], "nativeTurnId": context["nativeTurnId"],
            "bindingHash": context["bindingHash"], "endpointHash": scope["endpointHash"],
            "catalogProjectId": scope["catalogProjectId"], "ownedProjectId": scope["projectId"],
            "startedAt": started, "observedAt": time.time(), "brain": after,
            "resumeProfile": context["profile"], "issues": issues,
            "gaps": ["code_mode_not_independently_reported", "native_effect_inventory_not_complete"],
            "boundary": BOUNDARY}
