"""Operator-pinned, historical-only host chain. No old endpoint is contacted.

Launch provenance establishes which dead host owned a saved request; it is not
native effect/child-process cleanup evidence. Native recovery never uses this
configuration. Reading a manifest cannot launch, bind, load or notify anything.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

from .admission import exact, sha
from .core import digest, require, Refusal
from .host_lifecycle import private_file, review_hash
from . import turn_host_continuity as continuity


def artifact(pin):
    exact(pin, {"path", "sha256"})
    sha(pin["sha256"])
    path = private_file(pin["path"])
    before = path.stat()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        require((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino), "Historical launch artifact was replaced")
        content = stream.read(65537)
        require(len(content) <= 65536, "Historical launch artifact grew beyond its bound")
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) and
            hashlib.sha256(content).hexdigest() == pin["sha256"], "Historical launch artifact changed")
    return content


def validate_launch(entry):
    """Pin intent + same-attempt process record, not an arbitrary PID assertion."""
    launch, retired = entry["launch"], entry["retiredHost"]
    exact(launch, {"intent", "process", "execClaim"})
    try:
        intent = json.loads(artifact(launch["intent"]))
        process = json.loads(artifact(launch["process"]))
    except (ValueError, UnicodeError) as error:
        raise Refusal("Malformed historical launch metadata") from error
    require(isinstance(intent, dict) and isinstance(process, dict) and
            isinstance(intent.get("spec"), dict) and digest(intent) == retired["launchClaimHash"] and
            intent.get("reviewHash") == review_hash(intent.get("spec"), intent.get("mode")) and
            intent.get("manifestHash") == digest(intent["spec"]) and
            process.get("pid") == retired["processId"] and type(process.get("pid")) is int and
            process.get("mode") == intent["mode"] and
            Path(launch["intent"]["path"]).parent == Path(launch["process"]["path"]).parent,
            "Original PID must match its preserved, separately reviewed launch attempt")
    brain = next(iter(entry["binding"]["brains"].values()))
    require(intent["spec"].get("cwd") == brain.get("cwd"), "Historical launch checkout changed")
    if intent["mode"] == "exec":
        require(launch["execClaim"] is not None and
                Path(launch["execClaim"]["path"]).parent == Path(launch["intent"]["path"]).parent and
                artifact(launch["execClaim"]) == b"" and
                process.get("status") == "exec_boundary_issued",
                "Exact retained one-shot exec claim and process record required")
    else:
        require(launch["execClaim"] is None and process.get("status") in ("process_running", "process_exited"),
                "Exact retained supervised launch record required")


def validate(value, *, artifacts=True):
    exact(value, {"version", "workspaceId", "brainId", "candidateBindingHash", "hosts"})
    require(type(value["version"]) is int and value["version"] == 1 and
            isinstance(value["workspaceId"], str) and isinstance(value["brainId"], str) and
            isinstance(value["hosts"], list) and 1 <= len(value["hosts"]) <= 8,
            "Bounded historical host chain required")
    sha(value["candidateBindingHash"])
    ids, pids = set(), set()
    for entry in value["hosts"]:
        exact(entry, {"binding", "retiredHost", "launch"})
        binding = entry["binding"]
        require(isinstance(binding, dict) and set(binding) == {"endpoint", "brains"} and
                isinstance(binding["endpoint"], dict) and isinstance(binding["brains"], dict) and
                set(binding["brains"]) == {value["brainId"]}, "One exact historical brain binding required")
        continuity.validate_retired(entry["retiredHost"])
        key, pid = digest(binding), entry["retiredHost"]["processId"]
        require(key == entry["retiredHost"]["bindingHash"] and key != value["candidateBindingHash"] and
                key not in ids and pid not in pids, "Historical host identity is duplicated or substituted")
        ids.add(key); pids.add(pid)
        if artifacts: validate_launch(entry)
    return value


def load(path):
    from .native_read_client import decode
    return copy.deepcopy(validate(decode(private_file(path).read_bytes())))


def inspect(value, binding, scope, commands, workspace_id):
    validate(value)
    require(value["workspaceId"] == workspace_id and value["brainId"] == scope["brainId"] and
            value["candidateBindingHash"] == digest(binding), "Historical chain belongs to another project or host")
    required = {c["notification"]["hostBindingHash"] for c in commands} - {digest(binding)}
    require({digest(e["binding"]) for e in value["hosts"]} == required,
            "Pin every historical request host, with no unrelated or missing host")
    proofs = []
    for entry in value["hosts"]:
        command = next(c for c in commands if c["notification"]["hostBindingHash"] == digest(entry["binding"]))
        proof = continuity.proof(entry["binding"], binding, command, scope)
        continuity.retirement(entry["retiredHost"], entry["binding"])
        proofs.append({"binding": continuity.for_browser(proof)["previousBinding"], "retiredHost": copy.deepcopy(entry["retiredHost"]),
                       "launch": copy.deepcopy(entry["launch"])})
    return {"version": 1, "manifestHash": digest(value), "hosts": proofs}


def check_retained(chain, proof, commands, ledger):
    """Revalidate signed private artifacts and fixed PIDs under confirmation locks."""
    exact(chain, {"version", "manifestHash", "hosts"})
    require(type(chain["version"]) is int and chain["version"] == 1 and
            isinstance(chain["hosts"], list) and 1 <= len(chain["hosts"]) <= 8, "Exact historical chain required")
    entries = []
    from .pause_host_continuity import check_catalog
    for host in chain["hosts"]:
        exact(host, {"binding", "retiredHost", "launch"})
        p = continuity.from_browser({**continuity.for_browser(proof), "previousBinding":host["binding"]})
        check_catalog(ledger, p)
        require(p["candidateBinding"] == proof["candidateBinding"] and
                all(p[k] == proof[k] for k in ("ledgerIdentity", "catalogHash", "projectLocationHash", "hostId")),
                "Historical chain continuity changed")
        entries.append({"binding": p["previousBinding"], "retiredHost": host["retiredHost"], "launch": host["launch"]})
    value = {"version": 1, "workspaceId": ledger.workspace_id,
             "brainId": commands[0]["notification"]["brainId"],
             "candidateBindingHash": digest(proof["candidateBinding"]), "hosts": entries}
    validate(value)
    require(digest(value) == chain["manifestHash"], "Historical chain signature changed")
    required = {c["notification"]["hostBindingHash"] for c in commands} - {value["candidateBindingHash"]}
    require({digest(e["binding"]) for e in entries} == required, "Historical chain request coverage changed")
    for entry in entries:
        require(entry["binding"]["brains"] == proof["candidateBinding"]["brains"], "Historical brain identity changed")
        continuity.retirement(entry["retiredHost"], entry["binding"])

