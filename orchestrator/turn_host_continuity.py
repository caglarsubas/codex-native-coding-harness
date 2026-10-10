"""Historical host pins for read-only recovery of an already ended brain turn.

Only operator-supplied, separately reviewed bindings are accepted. This module
never starts a host, reconnects an old endpoint, loads a thread or cancels a turn.
"""
import copy
import subprocess

from .app_server_wake import NATIVE_APPROVAL_POLICY
from .core import digest, require
from .pause_host_continuity import for_browser, from_browser, load_previous
from .admission import exact, sha


def load_retired(path):
    from .host_lifecycle import private_file
    from .native_read_client import decode
    value = decode(private_file(path).read_bytes())
    validate_retired(value)
    return value


def validate_retired(value):
    exact(value, {"version", "bindingHash", "processId", "launchClaimHash"})
    require(type(value["version"]) is int and value["version"] == 1 and
            type(value["processId"]) is int and 1 < value["processId"] <= 2**31 - 1,
            "The separately reviewed original host process is required")
    sha(value["bindingHash"]); sha(value["launchClaimHash"])


def process_absent(pid):
    # Fixed metadata-only argv. Any live/reused PID, failed read or timeout is
    # a refusal. No kill, process discovery, socket probe or old-host fallback.
    try:
        result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "pid="], capture_output=True,
                                timeout=5, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 1 and result.stdout == b"" and result.stderr == b""


def retirement(value, previous):
    validate_retired(value)
    require(value["bindingHash"] == digest(previous), "Retired process must belong to the preserved original binding")
    require(process_absent(value["processId"]),
            "Original host process is live, reused or unknown; replacement recovery cannot release its controller")
    return copy.deepcopy(value)


BOUNDARY = ("Inspect only the original, already-ended turn on the separately reviewed replacement host. "
            "Recover only its abandoned controller after repeated loaded-idle metadata and known-empty tracked terminals. "
            "Preserve every receipt, unknown effect, usage gap and original phase expiry. "
            "No cancellation, thread loading, permission response, checkpoint, wake, Resume, Play or pilot acceptance.")


def proof(previous, candidate, command, scope):
    """Validate historical bytes without inspecting the obsolete endpoint."""
    require(isinstance(previous, dict) and set(previous) == {"endpoint", "brains"} and
            isinstance(candidate, dict) and set(candidate) == {"endpoint", "brains"} and
            isinstance(previous["endpoint"], dict) and isinstance(candidate["endpoint"], dict) and
            digest(previous) == command["notification"]["hostBindingHash"] and
            digest(previous) != digest(candidate), "The exact preserved original host binding is required")
    brain = scope["brainId"]
    require(previous["brains"] == candidate["brains"] and set(candidate["brains"]) == {brain},
            "Replacement recovery requires one unchanged brain, workspace, checkout and both project identities")
    row = candidate["brains"][brain]
    require(row.get("nativePolicy") == NATIVE_APPROVAL_POLICY,
            "The exact restricted native approval profile is required")
    return {"version": 1, "previousBinding": copy.deepcopy(previous), "candidateBinding": copy.deepcopy(candidate),
            **{k: scope[k] for k in ("ledgerIdentity", "catalogHash", "hostId")},
            "projectLocationHash": scope["locationHash"]}


def same_ended(before, after):
    require(before["status"] != "inProgress" and after["status"] != "inProgress" and
            all(before.get(k) == after.get(k) for k in
                ("turnId", "status", "completedAt", "activity", "trackedTerminals")),
            "The exact ended turn changed; no replacement-host cancellation is authorized")
