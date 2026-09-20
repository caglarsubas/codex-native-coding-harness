"""Bounded private Git/evidence retention; no remote, native or archive effects."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

from . import run_authority as runs, source_observation as source
from .admission import exact, integer, sha, timestamp
from .core import Refusal, canonical, digest, require
from .observations import MAX_ARTIFACT, capture
from .result_review import artifact_in

KIND = "local_result_preservation"
REQUEST = "local_preservation_request"
PROVENANCE = "local_preservation_v1"
REFS = ("refs/heads/preserved-base", "refs/heads/preserved-result")


def preserve_git(path, key, base, commit, branch):
    """Copy Git objects, not working files. Verification has no original objects."""
    source.oid(base); source.oid(commit); ref = source.branch_ref(branch)
    require(base != commit, "Distinct preservation base and result required")
    started = time.time()
    try:
        common, objects, pin = source.layout(path, key)
        require(source.ref_value(common, ref) == commit, "Preservation branch tip changed")
        source.check_objects(objects)
        with source.object_view(objects) as view:
            source.commit_tree(view, base); source.commit_tree(view, commit)
            source.git_read(view, ["merge-base", "--is-ancestor", base, commit], bound=0)
            (view / "refs/heads").mkdir()
            for name, value in zip(REFS, (base, commit)):
                (view / name).write_text(value + "\n")
            bundle = source.git_read(view, ["bundle", "create", "--version=2", "-", *REFS],
                                     bound=MAX_ARTIFACT, timeout=10)
        # Fixed v2 header, no prerequisites and no additional refs/capabilities.
        expected = b"# v2 git bundle\n" + b"".join(
            (value + " " + name + "\n").encode() for name, value in zip(REFS, (base, commit))) + b"\n"
        require(bundle.startswith(expected + b"PACK"), "Self-contained exact-ref Git bundle required")
        with tempfile.TemporaryDirectory(prefix="codex-preservation-restore-") as folder:
            root = Path(folder); view = root / "restore"; view.mkdir()
            (view / "objects").mkdir(); (view / "refs/heads").mkdir(parents=True)
            (view / "HEAD").write_text("ref: " + REFS[1] + "\n")
            (view / "config").write_text("[core]\nrepositoryformatversion = 0\nbare = true\n")
            saved = root / "result.bundle"; saved.write_bytes(bundle)
            source.git_read(view, ["bundle", "verify", str(saved)], timeout=10)
            source.git_read(view, ["bundle", "unbundle", str(saved)], timeout=10)
            for name, value in zip(REFS, (base, commit)):
                (view / name).write_text(value + "\n")
            source.git_read(view, ["fsck", "--full", "--strict", "--no-reflogs", "--no-dangling", *REFS], timeout=10)
            trees = [source.commit_tree(view, value) for value in (base, commit)]
            source.git_read(view, ["merge-base", "--is-ancestor", base, commit], bound=0)
        common_after, objects_after, after = source.layout(path, key)
        source.check_objects(objects_after)
        require(pin == after and common_after == common and source.ref_value(common_after, ref) == commit,
                "Repository identity or branch changed during preservation")
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        raise Refusal("Local preservation unavailable or unsupported") from error
    observed = time.time()
    require(started <= observed, "Preservation clock moved backwards")
    return bundle, {"baseSHA": base, "commit": commit, "branch": branch, "resourceKey": key, "layoutHash": pin,
                    "baseTree": trees[0], "resultTree": trees[1], "startedAt": started, "observedAt": observed,
                    "restoredWithoutSource": True, "gitIntegrityVerified": True, "worktreeInspected": False,
                    "remoteObserved": False, "offDeviceBackup": False, "externalObjectContentsPreserved": False}


def request_shape(request):
    exact(request, {"id", "expectedRevision", "settlementHash", "commit", "evidence"})
    source.request_shape({k: request[k] for k in ("id", "expectedRevision", "settlementHash", "commit")})
    require(isinstance(request["evidence"], list) and 1 <= len(request["evidence"]) <= 40,
            "Preservation requires 1 to 40 exact evidence versions")
    subjects = []
    for row in request["evidence"]:
        exact(row, {"subject", "artifactId"}); sha(row["artifactId"])
        require(isinstance(row["subject"], str) and len(row["subject"]) <= 80 and
                row["subject"] not in ("preservation", "independent_review"),
                "Preservation cannot contain itself or its later independent review")
        subjects.append(row["subject"])
    require(subjects == sorted(set(subjects)), "Preservation evidence must have unique sorted subjects")
    require(len(canonical(request).encode()) <= 8000, "Preservation request exceeds its bound")


def request_key(intent, request):
    return digest({"kind": REQUEST, "workspaceId": intent["workspaceId"], "workerId": intent["workerId"], "id": request["id"]})


def row_binding(info):
    require(isinstance(info, dict) and all(k in info for k in ("id", "sha256", "size", "observedAt")),
            "Preserved artifact metadata is incomplete")
    sha(info["id"]); sha(info["sha256"]); integer(info["size"]); timestamp(info["observedAt"])
    return {k: info[k] for k in ("id", "sha256", "size", "observedAt")}


def inventory_in(db, intent, terminal, request):
    from .result_handoff import handoff_proof
    seed = runs.document(db, intent["seedHash"], "seed")
    from .core import AXES
    allowed = set(AXES) | {"criterion:" + str(i) for i in range(len(seed["acceptance"]))}
    evidence = []
    for row in request["evidence"]:
        require(row["subject"] in allowed, "Preservation evidence subject is outside this task")
        info, raw = handoff_proof(db, row["artifactId"], intent, row["subject"], request["commit"])
        require(info.get("size") == len(raw), "Preservation artifact size changed")
        evidence.append({"subject": row["subject"], **row_binding(info)})
    handoffs = []
    from .ownership_settlement import OwnershipSettlement
    for task in terminal["request"]["inventory"]["tasks"]:
        OwnershipSettlement.artifact_in(db, intent, task, terminal["nativeRecord"]["at"])
        info = json.loads(db.execute("SELECT data FROM artifact_versions WHERE id=?", (task["checkpointArtifactId"],)).fetchone()[0])
        handoffs.append({"hostId": task["hostId"], "threadId": task["threadId"], **row_binding(info)})
    return {"evidence": evidence, "handoffs": handoffs}


def receipt_for(report, info):
    return {"preservationHash": digest(report), "artifactId": info["id"], "bundleArtifactId": report["bundle"]["id"],
            "workerId": report["workerId"], "observedAt": report["observedAt"], "retainedAt": info["observedAt"],
            "packetAccepted": False, "archiveAuthorized": False, "nativeCallMade": False, "remoteObserved": False,
            "trustBoundary": "local_git_and_retained_evidence_not_off_device_backup"}


def receipt_in(db, key):
    row = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=2000 THEN data END FROM snapshots WHERE id=?", (key,)).fetchone()
    if row is None: return None
    require(row[0] == REQUEST and row[1] is not None, "Invalid preservation request receipt")
    try: out = json.loads(row[1])
    except (ValueError, TypeError, RecursionError): raise Refusal("Invalid preservation request receipt") from None
    require(isinstance(out, dict), "Invalid preservation request receipt")
    exact(out, {"preservationHash", "artifactId", "bundleArtifactId", "workerId", "observedAt", "retainedAt",
                "packetAccepted", "archiveAuthorized", "nativeCallMade", "remoteObserved", "trustBoundary"})
    for name in ("preservationHash", "artifactId", "bundleArtifactId"): sha(out[name])
    return out


def validate_proof(db, info, raw, intent, subject, commit):
    """Historical integrity check. No Git/filesystem/native calls or new clocks."""
    tagged = (info.get("provenance") == PROVENANCE or "preservationHash" in info or
              str(info.get("key", "")).startswith(("local-preservation:", "preserved-git:")))
    if not tagged: return None
    require(subject == "preservation" and info.get("provenance") == PROVENANCE,
            "Preservation proof cannot prove a different subject or lose provenance")
    report = runs.document(db, info.get("preservationHash"), KIND)
    require(canonical(report).encode() == raw and report["schemaVersion"] == 1, "Preservation manifest bytes changed")
    request = report["request"]; request_shape(request)
    require(report["workerId"] == intent["workerId"] and report["intentHash"] == digest(intent) and
            report["repository"] == intent["repository"] and request["commit"] == report["commit"] == commit and
            report["requestKey"] == request_key(intent, request) and report["resourceKey"] in intent["resourceKeys"],
            "Preservation task or commit binding changed")
    seed = runs.document(db, intent["seedHash"], "seed")
    terminal = runs.document(db, request["settlementHash"], "ownership_settlement")
    require(terminal["intentHash"] == digest(intent) and report["baseSHA"] == seed["baseSHA"] and
            report["branch"] == seed["branch"] and terminal["at"] <= report["startedAt"] <= report["observedAt"] <= info["observedAt"],
            "Preservation base, settlement or timing changed")
    require(inventory_in(db, intent, terminal, request) == report["inventory"], "Preserved evidence inventory changed")
    b = report["bundle"]
    row = db.execute("SELECT CASE WHEN length(CAST(data AS BLOB))<=4000 THEN data END,"
                     "CASE WHEN length(content)<=? THEN content END FROM artifact_versions WHERE id=?", (MAX_ARTIFACT, b["id"])).fetchone()
    require(row is not None and row[0] is not None and isinstance(row[1], bytes), "Retained preservation bundle is missing or oversized")
    try: bundle_info = json.loads(row[0])
    except (ValueError, TypeError, RecursionError): raise Refusal("Invalid preservation bundle metadata") from None
    require(isinstance(bundle_info, dict), "Invalid preservation bundle metadata")
    integer(bundle_info.get("version"))
    require(isinstance(bundle_info, dict) and bundle_info.get("key") == "preserved-git:" + report["requestKey"] and
            bundle_info.get("provenance") == PROVENANCE and bundle_info.get("repository") == intent["repository"] and
            bundle_info.get("sha256") == hashlib.sha256(row[1]).hexdigest() and bundle_info.get("size") == len(row[1]) and
            row_binding(bundle_info) == b and b["id"] == digest([bundle_info["key"], bundle_info["version"], b["sha256"]]) and
            report["observedAt"] <= b["observedAt"] <= info["observedAt"], "Preserved bundle bytes or metadata changed")
    require(receipt_in(db, report["requestKey"]) == receipt_for(report, info), "Preservation request receipt changed or missing")
    return report


def validate_result(db, info, raw, intent, settlement, result):
    report = validate_proof(db, info, raw, intent, "preservation", result["commit"])
    if report is None: return None
    require(report["request"]["settlementHash"] == digest(settlement), "Preservation belongs to a different settlement")
    expected = [{"subject": subject, "artifactId": proof["artifactId"]} for subject, proof in result["evidence"].items() if proof["artifactId"]]
    expected += [{"subject": "criterion:" + str(row["index"]), "artifactId": row["proof"]["artifactId"]}
                 for row in result["criteria"] if row["proof"]["artifactId"]]
    require(sorted(expected, key=lambda r: r["subject"]) == report["request"]["evidence"],
            "Result evidence differs from preserved versions")
    return report["startedAt"]


class LocalPreservation:
    def __init__(self, handoff):
        self.handoff, self.bridge, self.ledger, self.store = handoff, handoff.bridge, handoff.ledger, handoff.store

    def retained_in(self, db, intent, request):
        prior = receipt_in(db, request_key(intent, request))
        if prior is None: return None
        report = runs.document(db, prior["preservationHash"], KIND)
        require(report["request"] == request, "Preservation request ID reused with different content")
        artifact_in(db, prior["artifactId"], intent, "preservation", request["commit"])
        return prior

    def context_in(self, db, meta, kernel, worker, intent, request):
        context = self.handoff.source.source_in(db, meta, kernel, worker, intent, request)
        _, terminal = self.handoff.reviewer.settlement.record_in(kernel, intent)
        context["inventory"] = inventory_in(db, intent, terminal, request)
        return context

    def collect(self, token, worker_id, request):
        request_shape(request); request = copy.deepcopy(request)
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id)
            with self.store.tx() as kernel: self.handoff.terminal_in(db, kernel, worker, intent)
            prior = self.retained_in(db, intent, request)
            if prior: return prior
        with self.bridge.locked(token, ownership_change=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            # Another identical request may have retained its result after the first lookup.
            prior = self.retained_in(db, intent, request)
            if prior: return prior
            with self.store.tx() as kernel: context = self.context_in(db, meta, kernel, worker, intent, request)
        bundle, measured = preserve_git(context["repo"]["path"], context["resourceKey"], context["seed"]["baseSHA"],
                                         request["commit"], context["seed"]["branch"])
        with self.bridge.locked(token, ownership_change=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            prior = self.retained_in(db, intent, request)
            if prior: return prior
            with self.store.tx() as kernel:
                require(self.context_in(db, meta, kernel, worker, intent, request) == context,
                        "Preservation authority or inventory changed during collection")
                self.store.fresh(measured["startedAt"], self.store.get(kernel, "meta", 1)["policy"])
            key = request_key(intent, request)
            metadata = {"repository": intent["repository"], "orderAt": measured["observedAt"], "provenance": PROVENANCE,
                        "references": [{"workerId": worker_id, "intentHash": digest(intent), "commit": request["commit"],
                                        "subject": "preservation", "at": measured["observedAt"]}]}
            bundle_info = capture(db, "preserved-git:" + key, bundle, {**metadata, "name": "preserved-result.bundle"})
            report = {"kind": KIND, "schemaVersion": 1, "workerId": worker_id, "intentHash": digest(intent),
                      "repository": intent["repository"], "request": request, "requestKey": key,
                      "inventory": context["inventory"], "bundle": row_binding(bundle_info), **measured}
            require(len(canonical(report).encode()) <= 16000, "Preservation manifest exceeds its bound")
            report_hash = runs.retain(db, KIND, report)
            info = capture(db, "local-preservation:" + key, canonical(report).encode(),
                           {**metadata, "name": "local-preservation.json", "preservationHash": report_hash})
            receipt = receipt_for(report, info)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, REQUEST, canonical(receipt)))
            artifact_in(db, info["id"], intent, "preservation", request["commit"])
            self.ledger.event(db, "result_preserved_locally", {"workerId": worker_id, "preservationHash": report_hash, "artifactId": info["id"]})
            return receipt
