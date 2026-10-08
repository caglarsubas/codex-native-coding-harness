"""Exact reviewed host continuity for the sole pre-turn Pause replacement.

No host is started, selected, repinned or notified here. The operator supplies
an already separately reviewed candidate binding and the preserved old binding.
The signed checkpoint preview includes both; old bytes are historical evidence,
never a live endpoint. A connection change does not change the brain or run.
"""
import contextlib
import copy
import sqlite3
from types import SimpleNamespace

from .core import digest, require

FIELDS = {"version", "previousBinding", "candidateBinding", "ledgerIdentity",
          "catalogHash", "projectLocationHash", "hostId"}
SOCKET_FIELDS = {"device", "inode", "owner", "mode", "changedNs"}


def _browser_proof(proof, *, decode):
    """Lossless browser envelope only; retained pins and their hashes stay integers."""
    require(isinstance(proof, dict) and set(proof) == FIELDS and
            type(proof["version"]) is int and proof["version"] == 1,
            "Exact replacement-host continuity review required")
    result = copy.deepcopy(proof)

    def identity(value):
        if decode:
            # Reject coercion, mixed representations and unbounded digit strings.
            require(isinstance(value, str) and 0 < len(value) <= 20 and
                    all("0" <= c <= "9" for c in value) and
                    (value == "0" or value[0] != "0"),
                    "Canonical decimal continuity identity required")
            return int(value)
        require(type(value) is int and value >= 0 and len(str(value)) <= 20,
                "Exact integer continuity identity required")
        return str(value)

    require(isinstance(result["ledgerIdentity"], list) and len(result["ledgerIdentity"]) == 2,
            "Retained ledger identity required")
    result["ledgerIdentity"] = [identity(v) for v in result["ledgerIdentity"]]
    for key in ("previousBinding", "candidateBinding"):
        binding = result[key]
        require(isinstance(binding, dict) and set(binding) == {"endpoint", "brains"} and
                isinstance(binding["endpoint"], dict), "Exact reviewed host binding required")
        endpoint = binding["endpoint"]
        if "socketIdentity" in endpoint:
            pins = endpoint["socketIdentity"]
            require(isinstance(pins, dict) and set(pins) == SOCKET_FIELDS,
                    "Exact reviewed socket identity required")
            endpoint["socketIdentity"] = {k: identity(v) for k, v in pins.items()}
    return result


def for_browser(proof):
    return _browser_proof(proof, decode=False)


def from_browser(proof):
    return _browser_proof(proof, decode=True)


def registry_view(ledger):
    # Registry.__init__ acquires a write transaction. These checks must work
    # under the existing registry -> ledger lock and must remain read-only.
    return SimpleNamespace(root=ledger.platform_root, db=ledger.platform_root / "platform.sqlite3")


def load_previous(path):
    from .app_server_wake import _read_binding
    # Unlike load_binding, never validate or connect to the obsolete endpoint.
    # Its exact full hash must match the failed command before any use.
    return _read_binding(path)


def validate(proof, context, binding_hash, observation):
    from .app_server_wake import NATIVE_APPROVAL_POLICY
    from .pause_recovery import same_turn
    require(context and isinstance(proof, dict) and set(proof) == FIELDS and
            type(proof["version"]) is int and proof["version"] == 1,
            "Exact replacement-host continuity review required")
    p = context["command"]["payload"]
    old, new = proof["previousBinding"], proof["candidateBinding"]
    require(all(isinstance(b, dict) and set(b) == {"endpoint", "brains"} and
                isinstance(b["endpoint"], dict) and isinstance(b["brains"], dict) for b in (old, new)) and
            digest(old) == p["bindingHash"] and digest(new) == binding_hash and
            digest(old) != digest(new) and old["brains"] == new["brains"] and
            set(new["brains"]) == {p["brainId"]},
            "Continuity requires the exact old binding and one unchanged brain mapping")
    row = new["brains"][p["brainId"]]
    require(isinstance(row, dict) and row.get("nativePolicy") == NATIVE_APPROVAL_POLICY and
            row.get("projectId") == p["observation"]["projectId"] and
            same_turn({**p["observation"], "bindingHash": binding_hash}, observation),
            "Native brain, project, approval policy or latest completed turn changed")
    from .admission import sha
    for key in ("catalogHash", "projectLocationHash"):
        sha(proof[key])
    require(isinstance(proof["ledgerIdentity"], list) and len(proof["ledgerIdentity"]) == 2 and
            all(type(v) is int and v >= 0 for v in proof["ledgerIdentity"]) and
            isinstance(proof["hostId"], str) and 0 < len(proof["hostId"]) <= 200,
            "Retained ledger and catalog identity required")


def check_catalog(ledger, proof):
    """Read-only recheck, including at receipt; never discover or refresh a catalog."""
    from .native_project_assignment import _catalog_still_bound, _registered
    new = proof["candidateBinding"]
    brain, row = next(iter(new["brains"].items()))
    root, inspected, _, _ = _registered(registry_view(ledger), ledger.workspace_id)
    require(root == ledger.root and inspected["brainId"] == brain and
            inspected["databaseIdentity"] == proof["ledgerIdentity"], "Registered continuity identity changed")
    scope = {"root": ledger.root, "brainId": brain, "ledgerIdentity": proof["ledgerIdentity"],
             "hostId": proof["hostId"], "catalogProjectId": row.get("catalogProjectId", row["projectId"])}
    with contextlib.closing(sqlite3.connect((ledger.platform_root / "platform.sqlite3").as_uri()+"?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        _catalog_still_bound(db, ledger.workspace_id, scope, proof)


def inspect(registry, workspace_id, state, context, previous_binding, binding, proxy):
    from . import native_project_assignment as project, pause_recovery
    require(context is not None, "Host continuity is only for the first proved pre-turn recovery failure")
    # Scope validates the currently pinned endpoint, separate native/app catalog
    # IDs, registered database and the catalog's exact Git repository root.
    scope = project._scope(registry, workspace_id, binding)
    require(scope["brainId"] == state["meta"]["brainId"] and
            scope["ledgerRevision"] == state["meta"]["revision"], "Project changed during continuity inspection")
    proof = {"version": 1, "previousBinding": copy.deepcopy(previous_binding),
             "candidateBinding": copy.deepcopy(binding),
             **{k: scope[k] for k in ("ledgerIdentity", "catalogHash", "hostId")},
             "projectLocationHash": scope["locationHash"]}
    # Reject changed historical bytes/mapping before native I/O. Only the host
    # endpoint may differ; a name or matching checkout is never identity proof.
    validate(proof, context, digest(binding), {**context["command"]["payload"]["observation"],
                                            "bindingHash": digest(binding)})
    first, roots = project._native_identity(proxy, scope)
    require(first["projectId"] == scope["projectId"], "Candidate host must already observe the exact assigned project")
    original = pause_recovery.eligible(state, state["meta"]["standardRun"]["pauseRecovery"]["id"]
                                       if state["meta"]["standardRun"]["pauseRecovery"].get("priorAttempt") else None)
    observation = pause_recovery.observe(proxy, binding, original)
    last, last_roots = project._native_identity(proxy, scope)
    require(first == last and roots == last_roots and project._scope(registry, workspace_id, binding) == scope,
            "Candidate host, native project or catalog changed during inspection")
    validate(proof, context, digest(binding), observation)
    return observation, proof
