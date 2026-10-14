"""Bounded public-host sign-in diagnostics, not model access or authority.

Read on the already owned connection only. Never log in, refresh credentials,
copy an auth store, choose a provider, or infer terminal/usage evidence.
"""
import time

from .core import canonical, digest, require

METHOD = "account/read"
PARAMS = {"refreshToken": False}


def projection(value):
    require(isinstance(value, dict) and {"account", "requiresOpenaiAuth"} <= set(value) and
            set(value) <= {"account", "requiresOpenaiAuth", "workspaceRouting"} and
            type(value["requiresOpenaiAuth"]) is bool and len(canonical(value).encode()) <= 16384,
            "Native authentication report is unsupported")
    account = value["account"]
    require(account is None or isinstance(account, dict) and
            account.get("type") in ("apiKey", "chatgpt", "amazonBedrock"),
            "Native account type is unknown")
    ready = not value["requiresOpenaiAuth"] or account is not None
    return {"status": "ready" if ready else "authentication_required", "ready": ready,
            "requiresOpenaiAuth": value["requiresOpenaiAuth"], "accountPresent": account is not None}


def inspect(proxy):
    """Fixed repeated account reads; raw account/routing data is never retained."""
    first = proxy._rpc(METHOD, PARAMS.copy())
    before = projection(first)
    second = proxy._rpc(METHOD, PARAMS.copy())
    after = projection(second)
    require(first == second and before == after, "Native authentication changed during inspection")
    return {"version": 1, **after, "checkedAt": time.time(), "responseHash": digest(second),
            "modelAccessVerified": False, "executionAuthorized": False,
            "terminalSafetyVerified": False, "usageMeasured": False}


def require_ready(proxy):
    report = inspect(proxy)
    require(report["ready"], "Sign in on the reviewed native host before new work; no login or retry was sent")
    return report
