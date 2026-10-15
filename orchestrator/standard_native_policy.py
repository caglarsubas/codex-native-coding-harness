"""Closed, non-collecting policy diagnostics for an owned standard turn.

The v1 resume acknowledgement cannot attest Code Mode off. Only a separate
supported future native observation bound to its exact owned command and turn
can satisfy the policy prerequisite. Legacy and unsolicited fields stay unknown.
"""
import math


BLOCKER = "Native Code Mode-off policy is unverified; repair and qualify the runtime before new effects or Resume"


def projection(ledger, db, run):
    """Read retained command metadata only; never connect, renew or backfill."""
    candidates = [c for c in ledger.all(db, "commands")
                  if (c.get("notification") or {}).get("hostRunId") == run["id"]]
    if not candidates:
        return None  # Non-owned transports keep their existing separate contract.
    def timestamp(command):
        value = (command.get("notification") or {}).get("attemptedAt")
        return value if type(value) in (int, float) and math.isfinite(value) else -1
    command = max(candidates, key=lambda c: (timestamp(c), c["id"]))
    note = command.get("notification") or {}
    profile = note.get("nativeResumeProfile")
    loaded = False
    if run.get('successorHash'):
        from .standard_successor import valid_profile
        loaded = valid_profile(note.get('nativeLoadedProfile'), note, run, command['id'])
        profile = note.get('nativeLoadedProfile') if loaded else None
    bound = (isinstance(profile, dict) and profile.get("version") == 1 and
             note.get("brainId") == run["brainId"] and
             profile.get("brainId") == run["brainId"] and
             profile.get("commandId") == command["id"] and
             isinstance(note.get("hostBindingHash"), str) and
             profile.get("bindingHash") == note["hostBindingHash"] and
             isinstance(note.get("nativeTurnId"), str) and
             profile.get("nativeTurnId") == note["nativeTurnId"] and
             (profile.get("resumeAcknowledged") is True or loaded))
    reported = profile.get("reported") if bound else None
    reported = reported if isinstance(reported, dict) else {}
    requested = profile.get("requested") if bound else None
    expected = {"sandbox": "workspace-write", "approvalPolicy": "on-request", "codeMode": False}
    if loaded:
        reported = (note.get('nativeEffectivePolicy') or {}).get('reported') or {}
        requested = expected  # Binding policy was checked, never applied or acknowledged by resume.
    # False compares equal to zero in Python: policy values must be exact types.
    configured = (isinstance(requested, dict) and requested == expected and
                  type(requested.get("codeMode")) is bool)
    observed_at = profile.get("observedAt") if bound else None
    if type(observed_at) not in (int, float) or not math.isfinite(observed_at) or observed_at <= 0:
        observed_at = None
    from .native_policy_evidence import valid_retained
    effective = note.get("nativeEffectivePolicy")
    verified = bool(bound and configured and observed_at and
                    valid_retained(effective, note, profile, command["id"], run["brainId"]))
    return {"commandId": command["id"], "observedAt": observed_at,
            "resumeAcknowledged": bool(bound and not loaded), "loadedWithoutResume": loaded, "configurationMatches": configured,
            "sandbox": "reported_matching" if reported.get("sandbox") == "workspaceWrite" else "unverified",
            "approvalPolicy": "reported_matching" if reported.get("approvalPolicy") == "on-request" else "unverified",
            "approvalsReviewer": "reported_matching" if reported.get("approvalsReviewer") == "user" else "unverified",
            "codeMode": "native_reported_off" if verified else "unverified", "policyVerified": verified,
            "blocker": None if verified else BLOCKER,
            "boundary": "Saved policy metadata, not current activity, terminal safety or execution authority."}


def blockers(ledger, db, run):
    result = projection(ledger, db, run)
    return [BLOCKER] if result and not result["policyVerified"] else []
