"""Explicit local source-structure observations, not acceptance or native work.

Only standard-policy tasks with pinned local Git identity. Git sees a temporary
bare view, not repository configuration, worktree files, replacement refs or
credentials. This is a bounded read against a trusted local filesystem, not an
OS sandbox or an attestation of remote state/semantic correctness.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time

from . import run_authority as runs
from .admission import exact, identifier, integer, sha
from .core import Refusal, canonical, digest, require
from .observations import capture, read_regular
from .phase_scope import contained_path
from .result_review import ResultReview, artifact_in, unaccepted_worker

PROVENANCE = "local_source_observer_v1"
KIND = "local_source_observation"
OID = re.compile(r"[a-f0-9]{40}")
MAX_BYTES = 16000


def oid(value):
    require(isinstance(value, str) and OID.fullmatch(value), "Local source observer supports exact SHA-1 commits only")
    return value


def branch_ref(branch):
    require(isinstance(branch, str) and branch.startswith("codex/") and len(branch) <= 200 and
            all(re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", p) and not p.endswith((".", ".lock")) and
                ".." not in p for p in branch.split("/")), "Unsupported source branch name")
    return "refs/heads/" + branch


def regular(path, root, bound=8192):
    return read_regular(path, root, bound)


def directory(path):
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and path == path.resolve(strict=True), "Canonical non-symlink Git directory required")
    return {"device": info.st_dev, "inode": info.st_ino}


def layout(path, expected_key):
    root = Path(path)
    require(root.is_absolute(), "Registered absolute repository required")
    root_id = directory(root)
    marker = root / ".git"; info = marker.lstat()
    if stat.S_ISDIR(info.st_mode):
        gitdir = marker; marker_hash = None
    else:
        require(stat.S_ISREG(info.st_mode), "Unsupported Git marker")
        raw = regular(marker, root, 4096)
        text = raw.decode("utf-8").strip()
        require(text.startswith("gitdir: ") and "\n" not in text and "\x00" not in text, "Invalid linked-worktree Git marker")
        gitdir = (root / text[8:]).resolve(strict=True); marker_hash = hashlib.sha256(raw).hexdigest()
    git_id = directory(gitdir)
    common_file = gitdir / "commondir"
    if common_file.exists() or common_file.is_symlink():
        raw = regular(common_file, gitdir, 4096); text = raw.decode("utf-8").strip()
        require(text and "\n" not in text and "\x00" not in text, "Invalid Git common directory")
        common = (gitdir / text).resolve(strict=True); common_hash = hashlib.sha256(raw).hexdigest()
    else:
        common = gitdir; common_hash = None
    common_id = directory(common)
    require("repo-local:" + digest(common_id) == expected_key, "Registered Git common-directory identity changed")
    objects = common / "objects"; objects_id = directory(objects)
    for name in ("shallow", "info/grafts", "objects/info/alternates", "objects/info/http-alternates"):
        candidate = common / name
        require(not candidate.exists() and not candidate.is_symlink(), "Shallow, grafted or alternate object storage needs a separate adapter")
    return common, objects, digest({"root": root_id, "git": git_id, "common": common_id,
                                    "objects": objects_id, "marker": marker_hash, "commondir": common_hash})


def ref_value(common, ref):
    path = common / ref
    if path.exists() or path.is_symlink():
        return oid(regular(path, common, 128).decode("ascii").strip())
    packed = common / "packed-refs"
    require(packed.exists() or packed.is_symlink(), "Exact local result branch is unavailable")
    matches = []
    for line in regular(packed, common, 1_000_000).decode("utf-8").splitlines():
        if line.startswith(("#", "^")) or not line: continue
        fields = line.split(" ")
        require(len(fields) == 2, "Invalid packed reference inventory")
        if fields[1] == ref: matches.append(oid(fields[0]))
    require(len(matches) == 1, "Exact local result branch is absent or ambiguous")
    return matches[0]


def check_objects(objects):
    """Refuse filesystem indirection; do not open source blobs or pack contents."""
    start = time.monotonic(); count = 0; pending = [objects]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                count += 1
                require(count <= 50000 and time.monotonic() - start < 3, "Git object inventory exceeds its bound")
                info = entry.stat(follow_symlinks=False)
                require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), "Git object storage contains unsupported indirection")
                if stat.S_ISDIR(info.st_mode): pending.append(entry.path)


def git_read(view, args, bound=65536, timeout=4):
    """Closed callers only. No inherited Git targeting/configuration/credentials."""
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_ALLOW_PROTOCOL": "",
           "GIT_TERMINAL_PROMPT": "0", "GIT_NO_LAZY_FETCH": "1", "GIT_ATTR_NOSYSTEM": "1"}
    argv = ["/usr/bin/git", "--no-optional-locks", "--git-dir="+str(view),
            "-c", "protocol.allow=never", "-c", "core.hooksPath="+os.devnull,
            "-c", "core.fsmonitor=false", "-c", "core.attributesFile="+os.devnull,
            "-c", "core.commitGraph=false", "-c", "core.multiPackIndex=false", *args]
    data = bytearray(); deadline = time.monotonic() + timeout
    with subprocess.Popen(argv, cwd=view, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, start_new_session=True) as proc:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    require(remaining > 0, "Local Git observation timed out")
                    ready = selector.select(remaining)
                    require(ready, "Local Git observation timed out")
                    chunk = os.read(proc.stdout.fileno(), min(65536, bound + 1 - len(data)))
                    if not chunk: break
                    data.extend(chunk)
                    require(len(data) <= bound, "Local Git output exceeds its bound")
            proc.wait(timeout=max(0.01, deadline-time.monotonic()))
            require(proc.returncode == 0, "Required local Git evidence is unavailable")
        except BaseException:
            if proc.poll() is None:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                except PermissionError:
                    # Some hosts deny process-group signals. This closed Git
                    # view cannot launch configured helpers; stop our child only.
                    proc.kill()
            proc.wait()
            raise
    return bytes(data)


def commit_tree(view, key):
    raw = git_read(view, ["cat-file", "commit", key])
    require(hashlib.sha1(b"commit "+str(len(raw)).encode()+b"\0"+raw).hexdigest() == key,
            "Local commit object does not match its identity")
    first = raw.split(b"\n", 1)[0]
    require(first.startswith(b"tree "), "Commit tree is unavailable")
    return oid(first[5:].decode("ascii"))


@contextlib.contextmanager
def object_view(objects):
    """Configuration-isolated view shared by closed, read-only Git probes."""
    with tempfile.TemporaryDirectory(prefix="codex-source-view-") as folder:
        view = Path(folder)
        (view / "refs").mkdir(); (view / "HEAD").write_text("ref: refs/heads/observer\n")
        (view / "config").write_text("[core]\nrepositoryformatversion = 0\nbare = true\n")
        (view / "objects").symlink_to(objects, target_is_directory=True)
        yield view


def inspect_base(path, key, base):
    """Exact local commit availability/identity only; never checkout or fetch."""
    oid(base)
    try:
        common, objects, pin = layout(path, key)
        check_objects(objects)
        with object_view(objects) as view: tree = commit_tree(view, base)
        common_after, objects_after, after = layout(path, key)
        check_objects(objects_after)
        require(after == pin and common_after == common, "Repository identity changed during base observation")
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        raise Refusal("Local base metadata unavailable or unsupported") from error
    return {"baseSHA": base, "baseTree": tree, "resourceKey": key, "layoutHash": pin,
            "observedAt": time.time(), "worktreeInspected": False, "remoteObserved": False}


def changes(raw):
    require(raw.endswith(b"\0"), "Complete nonempty source diff required")
    fields = raw[:-1].split(b"\0")
    require(len(fields) % 2 == 0 and 0 < len(fields) <= 400, "Source diff exceeds 200 changed paths")
    result = []
    for header, raw_path in zip(fields[::2], fields[1::2]):
        parts = header.decode("ascii").split(" ")
        require(len(parts) == 5 and parts[0].startswith(":"), "Invalid raw source diff")
        old_mode, new_mode, old_object, new_object, action = parts[0][1:], *parts[1:]
        require(old_mode in ("000000", "100644", "100755") and new_mode in ("000000", "100644", "100755"),
                "Changed symlinks or submodules require a separate source adapter")
        oid(old_object); oid(new_object)
        require(action in ("A", "M", "D", "T"), "Unsupported source change")
        path = raw_path.decode("utf-8", errors="strict")
        require(len(path) <= 500 and contained_path(path, [path]) and not any(c in path for c in "*?[]"),
                "Unsupported changed path")
        result.append({"path": path, "oldMode": old_mode, "newMode": new_mode,
                       "oldObject": old_object, "newObject": new_object, "change": action})
    require(len({r["path"] for r in result}) == len(result), "Duplicate source change")
    return sorted(result, key=lambda r: r["path"])


def inspect_source(path, key, base, result, branch, allowed):
    """Measure local committed structure. No ledger changes or remote claims."""
    oid(base); oid(result); ref = branch_ref(branch)
    require(base != result, "Distinct base and result commits required")
    started = time.time()
    try:
        common, objects, pin = layout(path, key)
        require(ref_value(common, ref) == result, "Result branch tip does not match the requested commit")
        check_objects(objects)
        with object_view(objects) as view:
            base_tree, result_tree = commit_tree(view, base), commit_tree(view, result)
            git_read(view, ["merge-base", "--is-ancestor", base, result], bound=0)
            raw = git_read(view, ["diff-tree", "--no-ext-diff", "--no-textconv", "--no-renames", "--no-commit-id",
                                  "--no-abbrev", "-r", "--raw", "-z", base, result, "--"])
            delta = changes(raw)
        common_after, objects_after, after = layout(path, key)
        check_objects(objects_after)
        require(after == pin and common_after == common and ref_value(common_after, ref) == result,
                "Repository identity or result branch changed during observation")
    except (OSError, UnicodeError, subprocess.SubprocessError) as error:
        raise Refusal("Local source metadata unavailable or unsupported") from error
    paths = [row["path"] for row in delta]
    report = {"baseSHA": base, "commit": result, "branch": branch, "resourceKey": key, "layoutHash": pin,
              "baseTree": base_tree, "resultTree": result_tree, "baseAncestor": True, "diffComplete": True,
              "changes": delta, "changedPaths": paths, "outOfScope": [p for p in paths if not contained_path(p, allowed)],
              "startedAt": started, "observedAt": time.time(), "worktreeInspected": False,
              "remoteObserved": False, "semanticReviewPerformed": False}
    require(report["observedAt"] >= started, "Source observation clock moved backwards")
    require(len(canonical(report).encode()) <= 13000, "Source report exceeds its retained proof bound")
    return report


def request_shape(request):
    exact(request, {"id", "expectedRevision", "settlementHash", "commit"})
    identifier(request["id"]); integer(request["expectedRevision"]); sha(request["settlementHash"]); oid(request["commit"])


def request_key(intent, request):
    return digest({"kind": "source_observation_request", "workspaceId": intent["workspaceId"],
                   "workerId": intent["workerId"], "id": request["id"]})


def receipt_for(report, artifact):
    return {"fingerprint": digest({"workerId": report["workerId"], "request": report["request"]}),
            "observationHash": digest(report), "artifactId": artifact["id"],
            "observedAt": report["observedAt"], "retainedAt": artifact["observedAt"], "workerId": report["workerId"],
            "sourceWithinScope": not report["outOfScope"], "packetAccepted": False,
            "executionAuthorized": False, "nativeCallMade": False, "remoteObserved": False}


def request_receipt_in(db, key):
    row = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=32768 THEN data END FROM snapshots WHERE id=?", (key,)).fetchone()
    if not row: return None
    require(row[0] == "source_observation_request" and row[1] is not None, "Invalid retained source request")
    try: receipt = json.loads(row[1])
    except (ValueError, TypeError, RecursionError): raise Refusal("Invalid retained source request") from None
    require(isinstance(receipt, dict), "Invalid retained source request")
    return receipt


def collector_binding_in(db, info, raw, intent):
    try: report = json.loads(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError): report = None
    require(isinstance(report, dict) and report.get("kind") == KIND and report.get("schemaVersion") == 1 and
            info.get("provenance") == PROVENANCE and info.get("sourceObservationHash") == digest(report) and
            canonical(report).encode() == raw, "Collector source artifact provenance changed")
    require(runs.document(db, digest(report), KIND) == report, "Retained collector observation changed")
    request_shape(report.get("request"))
    require(report["workerId"] == intent["workerId"] and report["intentHash"] == digest(intent) and
            report["repository"] == intent["repository"] and report["resourceKey"] in intent["resourceKeys"] and
            report["requestKey"] == request_key(intent, report["request"]) and
            report["settlementHash"] == report["request"]["settlementHash"] and
            report["commit"] == report["request"]["commit"], "Collector source task binding changed")
    require(request_receipt_in(db, report["requestKey"]) == receipt_for(report, info), "Collector request receipt changed or missing")
    return report


def validate_source_proof(db, info, raw, intent, settlement, result):
    """Collector-labelled bytes cannot fall back to an untyped proof on drift."""
    try: report = json.loads(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError): report = None
    tagged = (info.get("provenance") == PROVENANCE or "sourceObservationHash" in info or
              str(info.get("key", "")).startswith("source-observation:") or
              isinstance(report, dict) and report.get("kind") == KIND)
    if not tagged: return None
    report = collector_binding_in(db, info, raw, intent)
    require(report["settlementHash"] == digest(settlement) and report["baseSHA"] == result["baseSHA"] and
            report["commit"] == result["commit"] and report["branch"] == result["branch"] and
            report["changedPaths"] == sorted(result["changedPaths"]) and report["diffComplete"] is True,
            "Result differs from collected source evidence")
    require(result["evidence"]["source"]["status"] != "verified" or not report["outOfScope"],
            "Collected out-of-scope changes cannot verify source")
    require(settlement["at"] <= report["startedAt"] <= report["observedAt"] <= info["observedAt"],
            "Collected source observation timing changed")
    return report["observedAt"]


class SourceObserver:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.review = ResultReview(bridge)

    def source_in(self, db, meta, kernel, worker, intent, request):
        claim, terminal = self.review.settlement.record_in(kernel, intent)
        require(terminal and digest(terminal) == request["settlementHash"] and
                worker.get("ownershipSettlementHash") == request["settlementHash"] and worker["status"] == "settled",
                "Exact attached confirmed-terminal settlement required")
        self.review.settlement.attach_in(db, worker, claim, terminal)
        self.review.settlement.maintenance_check(kernel)
        unaccepted_worker(worker)
        self.review.authority_in(db, meta, worker, intent)  # Includes standard policy before filesystem I/O.
        require(meta["revision"] == request["expectedRevision"], "Workspace changed before source observation")
        allocation = self.store.get(kernel, "allocations", intent["allocationId"])
        require(allocation["fingerprint"] == intent["allocationFingerprint"] == digest(allocation["spec"]), "Phase allocation binding changed")
        keys = [key for key in intent["resourceKeys"] if key.startswith("repo-local:")]
        require(len(keys) == 1, "One pinned local common-directory resource is required")
        repo = self.ledger.get(db, "repos", intent["repository"])
        seed = runs.document(db, intent["seedHash"], "seed")
        source = {"repo": repo, "seed": seed, "claimHash": digest(claim), "worker": worker,
                  "runState": meta["runAuthority"], "revision": meta["revision"], "resourceKey": keys[0]}
        return source

    def retained_in(self, db, key, fingerprint, intent, request):
        receipt = request_receipt_in(db, key)
        if receipt is None: return None
        require(receipt.get("fingerprint") == fingerprint, "Source observation request ID reused with different content")
        info, raw = artifact_in(db, receipt["artifactId"], intent, "source", request["commit"])
        report = collector_binding_in(db, info, raw, intent)
        require(report["request"] == request and report["requestKey"] == key, "Retained source request changed")
        return receipt

    def observe(self, token, worker_id, request):
        request_shape(request)
        request = dict(request)  # All four fields are scalars; detach across I/O.
        fingerprint = digest({"workerId": worker_id, "request": request})
        key = digest({"kind": "source_observation_request", "workspaceId": self.bridge.workspace_id,
                      "workerId": worker_id, "id": request["id"]})
        with self.bridge.locked(token) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            prior = self.retained_in(db, key, fingerprint, intent, request)
            if prior: return prior  # Historical observation; never repeat Git or refresh clocks.
        with self.bridge.locked(token, ownership_change=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            # Another identical request may have retained its result after the first lookup.
            prior = self.retained_in(db, key, fingerprint, intent, request)
            if prior: return prior
            with self.store.tx() as kernel: source = self.source_in(db, meta, kernel, worker, intent, request)
        measured = inspect_source(source["repo"]["path"], source["resourceKey"], source["seed"]["baseSHA"],
                                  request["commit"], source["seed"]["branch"], source["seed"]["allowedPaths"])
        with self.bridge.locked(token, ownership_change=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            prior = self.retained_in(db, key, fingerprint, intent, request)
            if prior: return prior
            with self.store.tx() as kernel:
                current = self.source_in(db, meta, kernel, worker, intent, request)
                require(current == source, "Source task binding changed during observation")
                self.store.fresh(measured["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
            report = {"kind": KIND, "schemaVersion": 1, "workerId": worker_id, "intentHash": digest(intent),
                      "repository": intent["repository"], "settlementHash": request["settlementHash"],
                      "request": request, "requestKey": key, **measured}
            require(len(canonical(report).encode()) <= MAX_BYTES, "Source artifact exceeds its bound")
            observation_hash = runs.retain(db, KIND, report)
            artifact = capture(db, "source-observation:"+key, canonical(report).encode(), {
                "repository": intent["repository"], "name": "source-observation.json", "orderAt": report["observedAt"],
                "provenance": PROVENANCE, "sourceObservationHash": observation_hash, "references": [{
                    "workerId": worker_id, "intentHash": digest(intent), "commit": request["commit"], "subject": "source", "at": report["observedAt"]}]})
            receipt = receipt_for(report, artifact)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, "source_observation_request", canonical(receipt)))
            self.ledger.event(db, "source_observed", {"workerId": worker_id, "observationHash": observation_hash, "artifactId": artifact["id"]})
            return receipt
