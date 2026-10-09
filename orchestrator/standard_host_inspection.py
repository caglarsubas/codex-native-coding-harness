"""Private owned-host handoff and explicit brain-only metadata inspection.

Never discovers, loads, resumes or starts a native thread. The handoff is an
immutable copy of the operator-reviewed binding, not a new binding or authority.
"""
import copy
import os
import stat
import tempfile
import time

from .app_server_wake import _read_binding, load_binding, NATIVE_APPROVAL_POLICY
from .core import canonical, digest, require
from .native_project_assignment import _scope
from .standard_native_observation import _base_in, _brain_identity, TaskReadProxy
from . import standard

VERSION = 1
BROKER = "owned_observer_v1"
REQUEST_SECONDS = 30
REPORT_FIELDS = set("version workspaceId runId commandId brainId nativeTurnId bindingHash endpointHash "
                    "catalogProjectId ownedProjectId startedAt observedAt brain resumeProfile issues gaps boundary".split())
ISSUES = {"native_active_flags_unavailable", "native_approval_or_user_input_pending",
          "native_sandbox_unavailable_or_different", "native_approval_policy_unavailable_or_different",
          "native_approval_reviewer_unavailable_or_different", "unresolved_recorded_native_approval"}
GAPS = ["code_mode_not_independently_reported", "native_effect_inventory_not_complete"]
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
                "transport": note.get("hostInspectionTransport", "direct_v1"),
                "approvals": copy.deepcopy(note.get("nativeApprovals", []))}


def inspect(registry, ledger, token, run_id, command_id):
    """Explicit fixed metadata query, never a sandbox escape or native effect."""
    context = _context(registry, ledger, token, run_id, command_id)
    if context["transport"] == BROKER:
        return _request_inspection(registry, ledger, token, run_id, command_id, context)
    require(context["transport"] == "direct_v1", "Unsupported host inspection transport")
    return _collect(registry, ledger, token, run_id, command_id, context)


def _collect(registry, ledger, token, run_id, command_id, context, binding=None):
    path = binding_file(ledger, context["bindingHash"])
    retained = load_binding(path)
    require(binding is None or retained == binding, "Owned observer binding changed")
    binding = retained
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
            "gaps": GAPS.copy(), "boundary": BOUNDARY.copy()}


def _mailbox(ledger, command_id, suffix):
    from .admission import identifier
    identifier(command_id)
    require(ledger.root.resolve(strict=True) == ledger.root and
            ledger.root.stat().st_uid == os.getuid() and not ledger.root.stat().st_mode & 0o077,
            "Exact private owner ledger directory required")
    return ledger.root / ("host-inspection-" + digest(command_id) + suffix + ".json")


def _read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                not info.st_mode & 0o077 and info.st_nlink == 1 and info.st_size <= 65536,
                "Invalid private host inspection mailbox")
        from .native_read_client import decode
        return decode(stream.read())


def _write_once(path, value):
    # One immutable explicit query per owned control. Files are private IPC,
    # not a second notification/dispatcher or new executable permission.
    data = canonical(value)
    require(len(data.encode()) <= 65536, "Host inspection mailbox exceeds its bound")
    fd, temporary = tempfile.mkstemp(prefix=".host-inspection-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        # Publish complete bytes atomically, without replacing an existing name.
        os.link(temporary, path, follow_symlinks=False)
    finally:
        os.unlink(temporary)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _request_inspection(registry, ledger, token, run_id, command_id, context):
    request_path = _mailbox(ledger, command_id, "-request")
    reply_path = _mailbox(ledger, command_id, "-reply")
    request = {"version": VERSION, "runId": run_id, "commandId": command_id,
               "contextHash": digest(context), "controllerHash": digest(token)}
    try:
        _write_once(request_path, {**request, "requestedAt": time.time()})
    except FileExistsError:
        pass  # Read the original result; never renew or resubmit its query.
    saved = _read_private(request_path)
    require(isinstance(saved, dict) and set(saved) == set(request) | {"requestedAt"} and
            all(saved[k] == v for k, v in request.items()), "Host inspection request changed")
    require(type(saved["requestedAt"]) in (int, float) and
            0 <= time.time() - saved["requestedAt"] < REQUEST_SECONDS,
            "Host inspection request expired; no query was replayed")
    while time.time() - saved["requestedAt"] < REQUEST_SECONDS:
        require(_context(registry, ledger, token, run_id, command_id) == context,
                "Host inspection context changed; no continuation is authorized")
        try:
            reply = _read_private(reply_path)
        except FileNotFoundError:
            time.sleep(0.1)
            continue
        require(isinstance(reply, dict) and set(reply) in
                ({"requestHash", "status", "report"}, {"requestHash", "status"}) and
                reply.get("requestHash") == digest(saved),
                "Host inspection reply belongs to another query")
        require(reply.get("status") == "completed", "Owned host inspection unavailable; inspect the retained checkpoint")
        report = reply.get("report")
        require(isinstance(report, dict) and set(report) == REPORT_FIELDS and report.get("version") == VERSION and
                report.get("commandId") == command_id and
                report.get("workspaceId") == ledger.workspace_id and report.get("brainId") == context["brainId"] and
                report.get("runId") == run_id and report.get("nativeTurnId") == context["nativeTurnId"] and
                report.get("bindingHash") == context["bindingHash"] and report.get("boundary") == BOUNDARY and
                type(report.get("observedAt")) in (int, float) and
                saved["requestedAt"] <= report["observedAt"] <= time.time() and
                report.get("resumeProfile") == context["profile"],
                "Host inspection reply is stale or changed")
        brain = report["brain"]
        require(isinstance(brain, dict) and set(brain) == {"nativeStatus", "sourceHash", "activeFlags"} and
                brain["nativeStatus"] == "active" and (brain["activeFlags"] is None or
                isinstance(brain["activeFlags"], list) and len(brain["activeFlags"]) <= 2 and
                all(f in ("waitingOnApproval", "waitingOnUserInput") for f in brain["activeFlags"])) and
                isinstance(report["issues"], list) and len(report["issues"]) <= len(ISSUES) and
                all(isinstance(i, str) and i in ISSUES for i in report["issues"]) and
                report["gaps"] == GAPS and type(report["startedAt"]) in (int, float) and
                saved["requestedAt"] <= report["startedAt"] <= report["observedAt"],
                "Host inspection metadata shape changed")
        from .admission import sha, identifier
        for value in (brain["sourceHash"], report["endpointHash"], report["bindingHash"]):
            sha(value)
        for value in (report["catalogProjectId"], report["ownedProjectId"]):
            identifier(value)
        require(_context(registry, ledger, token, run_id, command_id) == context,
                "Host inspection context changed before returning evidence")
        return report
    require(False, "Owned observer did not return host evidence; no native effect was retried")


def service_request(ledger, binding, command_id, brain_id, turn_id):
    """Existing owned observer services only an explicit, controller-bound query.

    No socket is granted to the sandbox. No native write, notification, automatic
    collection, controller acquisition or independent scheduler exists here.
    """
    request_path = _mailbox(ledger, command_id, "-request")
    reply_path = _mailbox(ledger, command_id, "-reply")
    if not request_path.exists() or reply_path.exists():
        return
    request = _read_private(request_path)
    try:
        _write_once(_mailbox(ledger, command_id, "-claim"), {"requestHash": digest(request)})
    except FileExistsError:
        return  # An interrupted collector is unknown, never automatically recollected.
    from .core import Refusal
    try:
        require(isinstance(request, dict) and set(request) ==
                {"version", "runId", "commandId", "contextHash", "controllerHash", "requestedAt"} and
                request["version"] == VERSION and request["commandId"] == command_id and
                type(request["requestedAt"]) in (int, float) and
                0 <= time.time() - request["requestedAt"] < REQUEST_SECONDS,
                "Invalid or expired host inspection request")
        with standard.read_db(ledger.db) as db:
            controller = ledger.get(db, "meta", 1).get("controller") or {}
        token = controller.get("token")
        require(isinstance(token, str) and digest(token) == request["controllerHash"],
                "Host inspection controller changed")
        from .workspaces import Registry
        registry = Registry(ledger.platform_root)
        context = _context(registry, ledger, token, request["runId"], command_id)
        require(context["brainId"] == brain_id and context["nativeTurnId"] == turn_id and
                context["transport"] == BROKER and digest(context) == request["contextHash"] and
                context["bindingHash"] == digest(binding), "Host inspection owner context changed")
        report = _collect(registry, ledger, token, request["runId"], command_id, context, binding)
        reply = {"requestHash": digest(request), "status": "completed", "report": report}
    except (OSError, Refusal, ValueError, KeyError):
        reply = {"requestHash": digest(request), "status": "unavailable"}
    try:
        _write_once(reply_path, reply)
    except FileExistsError:
        pass
