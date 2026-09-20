"""Bounded GitHub metadata evidence, never merge authority or CI execution."""
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from urllib.parse import quote

from . import run_authority as runs
from .admission import exact, identifier, integer, sha
from .core import Refusal, canonical, digest, require
from .observations import capture
from .resources import remote_key
from .result_review import ResultReview, artifact_in, unaccepted_worker
from .source_observation import oid

KIND = "github_result_observation"
PROVENANCE = "github_result_observer_v1"
REQUEST = "github_observation_request"
LIMIT = 40
API_VERSION = "2022-11-28"


def pr_target(url):
    require(isinstance(url, str), "Exact GitHub PR URL required")
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_-]{1,100})/([A-Za-z0-9_.-]{1,100})/pull/([1-9][0-9]{0,8})", url)
    require(match is not None and match[2] not in (".", "..") and not match[2].endswith(".git"),
            "Only canonical credential-free github.com PR URLs are supported")
    slug = f"{match[1]}/{match[2]}".lower()
    return slug, int(match[3]), remote_key("https://github.com/"+slug)


def name(value):
    require(isinstance(value, str) and value.strip() == value and 0 < len(value) <= 160 and
            not any(ord(c) < 32 or ord(c) == 127 for c in value), "Unsupported GitHub check or branch name")
    return value


def api_read(endpoint, deadline):
    """Closed generated GET endpoints, bounded stdout, no raw errors or auth retained."""
    executable = shutil.which("gh")
    require(executable and Path(executable).is_absolute(), "Installed GitHub CLI unavailable")
    require(endpoint.startswith("repos/") and not any(c in endpoint for c in "{}\r\n"),
            "Invalid generated GitHub endpoint")
    env = {k: v for k, v in os.environ.items() if k in (
        "HOME", "PATH", "GH_TOKEN", "GITHUB_TOKEN", "GH_CONFIG_DIR", "XDG_CONFIG_HOME",
        "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")}
    env.update(GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1", GH_PAGER="cat", LC_ALL="C")
    argv = [executable, "api", "--hostname", "github.com", "--method", "GET",
            "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: "+API_VERSION, endpoint]
    data = bytearray(); stop = min(deadline, time.monotonic()+5)
    try:
        with tempfile.TemporaryDirectory(prefix="codex-github-read-") as folder:
            with subprocess.Popen(argv, cwd=folder, env=env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
                try:
                    with selectors.DefaultSelector() as selector:
                        selector.register(proc.stdout, selectors.EVENT_READ)
                        while True:
                            remaining = stop-time.monotonic()
                            require(remaining > 0 and selector.select(remaining), "GitHub observation timed out")
                            chunk = os.read(proc.stdout.fileno(), min(65536, 512001-len(data)))
                            if not chunk: break
                            data.extend(chunk)
                            require(len(data) <= 512000, "GitHub response exceeds its bound")
                    proc.wait(timeout=max(.01, stop-time.monotonic()))
                    require(proc.returncode == 0, "GitHub endpoint unavailable")
                except BaseException:
                    if proc.poll() is None: proc.kill()
                    proc.wait()
                    raise
        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, "Duplicate GitHub response field")
                result[key] = value
            return result
        result = json.loads(data, object_pairs_hook=unique)
        canonical(result)  # Reject non-finite JSON; raw bodies never enter reports.
        return result
    except (OSError, ValueError, RecursionError, subprocess.SubprocessError) as error:
        raise Refusal("GitHub response unavailable or unsupported") from error


def pull_projection(raw, slug, number, commit, base, branch):
    require(isinstance(raw, dict) and type(raw.get("number")) is int and raw["number"] == number,
            "GitHub PR identity changed")
    for side in ("head", "base"):
        row = raw.get(side)
        require(isinstance(row, dict) and isinstance(row.get("repo"), dict) and
                isinstance(row["repo"].get("full_name"), str) and row["repo"]["full_name"].lower() == slug,
                "Foreign, renamed or fork PR requires a separate adapter")
    require(raw["head"].get("sha") == commit and raw["base"].get("sha") == base and
            raw["head"].get("ref") == branch, "GitHub PR head, base or branch differs from the approved result")
    base_branch = name(raw["base"].get("ref"))
    require(raw.get("state") in ("open", "closed") and type(raw.get("merged")) is bool and
            type(raw.get("draft")) is bool, "Explicit GitHub PR state required")
    url = f"https://github.com/{slug}/pull/{number}"
    require(isinstance(raw.get("html_url"), str) and raw["html_url"].lower() == url,
            "GitHub PR URL changed")
    merged = raw["merged"]
    require(not merged or raw["state"] == "closed" and bool(raw.get("merged_at")), "Inconsistent GitHub merge state")
    merge = oid(raw.get("merge_commit_sha")) if merged else None
    return {"pr": {"url": url, "headSHA": commit, "baseSHA": base,
                   "state": "merged" if merged else raw["state"], "mergeCommit": merge},
            "baseBranch": base_branch, "headBranch": branch, "draft": raw["draft"]}


def policy_projection(classic, rules):
    required = set(); issues = []
    def add(context, app):
        name(context)
        if app in (None, -1): app = None
        else: integer(app, 1, 2**53-1)
        required.add((context, app))
    if classic is None: issues.append("classic_policy_unavailable")
    else:
        require(isinstance(classic, dict) and "required_status_checks" in classic, "Unsupported classic policy response")
        row = classic["required_status_checks"]
        if row is not None:
            require(isinstance(row, dict) and isinstance(row.get("checks"), list) and
                    isinstance(row.get("contexts"), list), "Explicit classic status-check policy required")
            require(len(row["checks"]) <= LIMIT and len(row["contexts"]) <= LIMIT, "Classic policy exceeds its bound")
            contexts = set()
            for check in row["checks"]:
                require(isinstance(check, dict) and "app_id" in check, "Classic check provider missing")
                add(check.get("context"), check["app_id"]); contexts.add(check["context"])
            for context in row["contexts"]:
                name(context)
                if context not in contexts: add(context, None)
    ignored = {"creation", "update", "deletion", "required_linear_history", "required_signatures", "pull_request",
               "required_deployments", "non_fast_forward", "commit_message_pattern", "commit_author_email_pattern",
               "committer_email_pattern", "branch_name_pattern"}
    if rules is None: issues.append("effective_rules_unavailable")
    else:
        require(isinstance(rules, list) and len(rules) <= LIMIT, "Effective branch rules exceed their bound")
        for row in rules:
            require(isinstance(row, dict), "Invalid effective branch rule")
            kind = row.get("type")
            require(isinstance(kind, str), "Invalid effective branch rule type")
            if kind == "required_status_checks":
                parameters = row.get("parameters")
                require(isinstance(parameters, dict), "Explicit effective status-check parameters required")
                checks = parameters.get("required_status_checks")
                require(isinstance(checks, list) and len(checks) <= LIMIT, "Bounded effective status-check policy required")
                for check in checks:
                    require(isinstance(check, dict), "Invalid required status check")
                    add(check.get("context"), check.get("integration_id"))
            elif kind not in ignored: issues.append("unsupported_effective_rule")
    require(len(required) <= LIMIT, "Required status-check union exceeds its bound")
    if not required: issues.append("no_required_checks")
    return {"required": [{"context": c, "appId": a} for c, a in sorted(required, key=lambda x: (x[0], x[1] or 0))],
            "issues": sorted(set(issues))}


def inventory(raw, field):
    require(isinstance(raw, dict) and type(raw.get("total_count")) is int and
            isinstance(raw.get(field), list) and 0 <= raw["total_count"] <= LIMIT and
            len(raw[field]) == raw["total_count"], "GitHub inventory incomplete or exceeds its bound")
    return raw[field]


def checks_projection(suites, runs_data, statuses, commit, slug):
    issues = []; suites_out = []; runs_out = []; statuses_out = []
    if suites is None: issues.append("check_suites_unavailable")
    else:
        for row in inventory(suites, "check_suites"):
            require(isinstance(row, dict) and row.get("head_sha") == commit, "Check suite commit mismatch")
            integer(row.get("id"), 1, 2**53-1); suites_out.append(row["id"])
        require(len(set(suites_out)) == len(suites_out), "Duplicate check suite")
    if runs_data is None: issues.append("check_runs_unavailable")
    else:
        for row in inventory(runs_data, "check_runs"):
            require(isinstance(row, dict) and row.get("head_sha") == commit and
                    isinstance(row.get("app"), dict) and isinstance(row.get("check_suite"), dict), "Check run identity mismatch")
            integer(row.get("id"), 1, 2**53-1); integer(row["app"].get("id"), 1, 2**53-1)
            integer(row["check_suite"].get("id"), 1, 2**53-1)
            if row["check_suite"]["id"] not in suites_out: issues.append("check_suite_coverage_missing")
            status, conclusion = row.get("status"), row.get("conclusion")
            require(status in ("queued", "in_progress", "completed", "waiting", "requested", "pending") and
                    conclusion in (None, "success", "failure", "neutral", "cancelled", "skipped", "timed_out",
                                   "action_required", "stale", "startup_failure"), "Unsupported check run state")
            state = ("passed" if conclusion == "success" else "failed" if conclusion in (
                "failure", "cancelled", "timed_out", "action_required", "stale", "startup_failure") else "pending") if status == "completed" else "pending"
            runs_out.append({"id": row["id"], "name": name(row.get("name")), "appId": row["app"]["id"],
                             "suiteId": row["check_suite"]["id"], "status": state})
        require(len({r["id"] for r in runs_out}) == len(runs_out), "Duplicate check run")
    if statuses is None: issues.append("commit_statuses_unavailable")
    else:
        require(isinstance(statuses, dict) and statuses.get("sha") == commit and
                isinstance(statuses.get("repository"), dict) and
                isinstance(statuses["repository"].get("full_name"), str) and
                statuses["repository"]["full_name"].lower() == slug, "Commit status repository or SHA mismatch")
        for row in inventory(statuses, "statuses"):
            require(isinstance(row, dict) and row.get("state") in ("success", "failure", "error", "pending"),
                    "Unsupported commit status")
            integer(row.get("id"), 1, 2**53-1)
            statuses_out.append({"id": row["id"], "name": name(row.get("context")), "status":
                {"success": "passed", "failure": "failed", "error": "failed", "pending": "pending"}[row["state"]]})
        require(len({r["id"] for r in statuses_out}) == len(statuses_out) and
                len({r["name"] for r in statuses_out}) == len(statuses_out), "Ambiguous combined commit statuses")
    return {"suiteIds": sorted(suites_out), "runs": sorted(runs_out, key=lambda r: r["id"]),
            "statuses": sorted(statuses_out, key=lambda r: r["id"]), "issues": sorted(set(issues))}


def ci_projection(policy, checks, commit):
    issues = list(policy["issues"])+checks["issues"]; names = []; observed = []
    for required in policy["required"]:
        context, app = required["context"], required["appId"]
        label = context+" [app:"+str(app if app is not None else "any")+"]"; names.append(label)
        candidates = [r for r in checks["runs"] if r["name"] == context and (app is None or r["appId"] == app)]
        legacy = [r for r in checks["statuses"] if r["name"] == context]
        if app is not None and legacy: issues.append("legacy_status_provider_unverified")
        if len({r["appId"] for r in candidates}) != len(candidates): issues.append("ambiguous_check_runs")
        if app is None: candidates += legacy
        if not candidates: issues.append("required_check_missing")
        state = "failed" if any(r["status"] == "failed" for r in candidates) else (
            "passed" if candidates and all(r["status"] == "passed" for r in candidates) else "pending")
        observed.append({"name": label, "headSHA": commit, "status": state})
    ci = {"headSHA": commit, "complete": not issues, "requiredChecks": names, "checks": observed}
    status = "verified" if not issues and all(r["status"] == "passed" for r in observed) else (
        "failed" if not issues and any(r["status"] == "failed" for r in observed) else "unverified")
    return ci, status, sorted(set(issues))


def inspect_github(url, commit, base, branch, *, reader=None):
    slug, number, key = pr_target(url); oid(commit); oid(base); name(branch)
    reader = reader or api_read; deadline = time.monotonic()+30; started = time.time()
    root = "repos/"+slug+"/"
    def get(suffix, optional=False):
        require(time.monotonic() < deadline, "GitHub observation exceeded total deadline")
        try: return reader(root+suffix, deadline)
        except Refusal:
            if optional: return None
            raise
    rounds = []; hashes = []
    for _ in range(2):
        pull = get("pulls/"+str(number)); pr = pull_projection(pull, slug, number, commit, base, branch)
        target = quote(pr["baseBranch"], safe="")
        classic = get("branches/"+target+"/protection", True)
        rules = get("rules/branches/"+target+"?per_page=100&page=1", True)
        suites = get("commits/"+commit+"/check-suites?per_page=100&page=1", True)
        runs_data = get("commits/"+commit+"/check-runs?filter=all&per_page=100&page=1", True)
        statuses = get("commits/"+commit+"/status?per_page=100&page=1", True)
        policy = policy_projection(classic, rules)
        checks = checks_projection(suites, runs_data, statuses, commit, slug)
        rounds.append({**pr, "policy": policy, "observedChecks": checks})
        # Preserve hashes of responses, never PR text, output, auth or details URLs.
        hashes.append({k: digest(v) if v is not None else None for k, v in (
            ("pr", pull), ("classic", classic), ("rules", rules), ("suites", suites), ("runs", runs_data), ("statuses", statuses))})
    require(rounds[0] == rounds[1] and hashes[0] == hashes[1], "GitHub evidence changed during observation; collect again explicitly")
    ci, status, issues = ci_projection(rounds[0]["policy"], rounds[0]["observedChecks"], commit)
    finished = time.time()
    require(started <= finished and time.monotonic() <= deadline, "GitHub observation interval invalid or expired")
    return {**rounds[0], "commit": commit, "baseSHA": base, "branch": branch, "resourceKey": key,
            "ci": ci, "ciStatus": status, "issues": issues, "responseHashes": hashes[0],
            "startedAt": started, "observedAt": started, "finishedAt": finished,
            "remoteObserved": True, "atomicSnapshot": False, "mergeAuthorized": False,
            "runtimeObserved": False, "semanticReviewPerformed": False}


def request_shape(request):
    exact(request, {"id", "expectedRevision", "settlementHash", "commit", "prUrl"})
    identifier(request["id"]); integer(request["expectedRevision"]); sha(request["settlementHash"])
    oid(request["commit"]); pr_target(request["prUrl"])


def request_key(intent, request):
    return digest({"kind": REQUEST, "workspaceId": intent["workspaceId"], "workerId": intent["workerId"], "id": request["id"]})


def receipt_for(report, artifact):
    return {"fingerprint": digest({"workerId": report["workerId"], "request": report["request"]}),
            "observationHash": digest(report), "artifactId": artifact["id"], "workerId": report["workerId"],
            "observedAt": report["observedAt"], "retainedAt": artifact["observedAt"], "ciStatus": report["ciStatus"],
            "packetAccepted": False, "executionAuthorized": False, "nativeCallMade": False, "mergeAuthorized": False}


def receipt_in(db, key):
    row = db.execute("SELECT kind,CASE WHEN length(CAST(data AS BLOB))<=32768 THEN data END FROM snapshots WHERE id=?", (key,)).fetchone()
    if not row: return None
    require(row[0] == REQUEST and row[1] is not None, "Invalid retained GitHub request")
    try: receipt = json.loads(row[1])
    except (ValueError, TypeError, RecursionError): raise Refusal("Invalid retained GitHub receipt") from None
    require(isinstance(receipt, dict), "Invalid retained GitHub receipt")
    return receipt


def collector_binding(db, info, raw, intent):
    try: report = json.loads(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError): report = None
    require(isinstance(report, dict) and report.get("kind") == KIND and report.get("schemaVersion") == 1 and
            info.get("provenance") == PROVENANCE and info.get("githubObservationHash") == digest(report) and
            canonical(report).encode() == raw, "GitHub collector provenance changed")
    require(runs.document(db, digest(report), KIND) == report, "GitHub observation journal changed")
    request_shape(report.get("request"))
    require(report["workerId"] == intent["workerId"] and report["intentHash"] == digest(intent) and
            report["repository"] == intent["repository"] and report["resourceKey"] in intent["resourceKeys"] and
            report["resourceKey"] == pr_target(report["request"]["prUrl"])[2] and
            report["requestKey"] == request_key(intent, report["request"]) and
            report["settlementHash"] == report["request"]["settlementHash"] and report["commit"] == report["request"]["commit"],
            "GitHub observation task binding changed")
    require(receipt_in(db, report["requestKey"]) == receipt_for(report, info), "GitHub request receipt changed or missing")
    return report


def validate_github_proof(db, info, raw, intent, settlement, result, subject):
    try: report = json.loads(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError): report = None
    tagged = (info.get("provenance") == PROVENANCE or "githubObservationHash" in info or
              str(info.get("key", "")).startswith("github-observation:") or isinstance(report, dict) and report.get("kind") == KIND)
    if not tagged: return None
    require(subject in ("ci", "merge"), "GitHub metadata cannot prove this evidence axis")
    report = collector_binding(db, info, raw, intent)
    require(report["settlementHash"] == digest(settlement) and report["pr"] == result["pr"] and
            report["ci"] == result["ci"] and report["commit"] == result["commit"] and
            report["baseSHA"] == result["baseSHA"] and report["branch"] == result["branch"],
            "Result differs from collected GitHub evidence")
    status = result["evidence"][subject]["status"]
    if subject == "ci":
        require(status == "unverified" or status == report["ciStatus"], "Collected GitHub CI status cannot be promoted")
    else:
        require(status == "unverified" or status == "verified" and report["pr"]["state"] == "merged",
                "Collected GitHub PR is not verified merged")
    require(settlement["at"] <= report["startedAt"] == report["observedAt"] <= report["finishedAt"] <= info["observedAt"],
            "GitHub observation timing changed")
    return report["observedAt"]


class GitHubObserver:
    def __init__(self, bridge):
        self.bridge, self.ledger, self.store = bridge, bridge.ledger, bridge.store
        self.review = ResultReview(bridge)

    def context_in(self, db, meta, kernel, worker, intent, request):
        claim, terminal = self.review.settlement.record_in(kernel, intent)
        require(terminal and digest(terminal) == request["settlementHash"] and
                worker.get("ownershipSettlementHash") == request["settlementHash"] and worker["status"] == "settled",
                "Exact attached confirmed-terminal settlement required")
        self.review.settlement.attach_in(db, worker, claim, terminal)
        self.review.settlement.maintenance_check(kernel); unaccepted_worker(worker)
        self.review.authority_in(db, meta, worker, intent)
        require(meta["revision"] == request["expectedRevision"], "Workspace changed before GitHub observation")
        allocation = self.store.get(kernel, "allocations", intent["allocationId"])
        require(allocation["fingerprint"] == intent["allocationFingerprint"] == digest(allocation["spec"]), "Phase allocation binding changed")
        key = pr_target(request["prUrl"])[2]
        require(key in intent["resourceKeys"], "GitHub PR is outside the pinned repository identity")
        return {"seed": runs.document(db, intent["seedHash"], "seed"), "claimHash": digest(claim),
                "worker": worker, "runState": meta["runAuthority"], "resourceKey": key}

    def retained_in(self, db, key, fingerprint, intent, request):
        receipt = receipt_in(db, key)
        if receipt is None: return None
        require(receipt.get("fingerprint") == fingerprint, "GitHub request ID reused with different content")
        info, raw = artifact_in(db, receipt["artifactId"], intent, "ci", request["commit"])
        report = collector_binding(db, info, raw, intent)
        require(report["request"] == request and report["requestKey"] == key, "Retained GitHub request changed")
        return receipt

    def observe(self, token, worker_id, request):
        request_shape(request); request = dict(request)
        fingerprint = digest({"workerId": worker_id, "request": request})
        with self.bridge.locked(token) as (db, _):
            worker, intent = self.bridge.intent_in(db, worker_id); key = request_key(intent, request)
            prior = self.retained_in(db, key, fingerprint, intent, request)
            if prior: return prior
        with self.bridge.locked(token, ownership_change=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            # Another identical request may have retained its result after the first lookup.
            prior = self.retained_in(db, key, fingerprint, intent, request)
            if prior: return prior
            with self.store.tx() as kernel: context = self.context_in(db, meta, kernel, worker, intent, request)
        measured = inspect_github(request["prUrl"], request["commit"], context["seed"]["baseSHA"], context["seed"]["branch"])
        with self.bridge.locked(token, ownership_change=True) as (db, meta):
            worker, intent = self.bridge.intent_in(db, worker_id)
            prior = self.retained_in(db, key, fingerprint, intent, request)
            if prior: return prior
            with self.store.tx() as kernel:
                require(context == self.context_in(db, meta, kernel, worker, intent, request), "GitHub task binding changed during collection")
                self.store.fresh(measured["observedAt"], self.store.get(kernel, "meta", 1)["policy"])
            report = {"kind": KIND, "schemaVersion": 1, "workerId": worker_id, "intentHash": digest(intent),
                      "repository": intent["repository"], "settlementHash": request["settlementHash"],
                      "request": request, "requestKey": key, **measured}
            require(len(canonical(report).encode()) <= 16000, "GitHub proof exceeds its retained bound")
            key_hash = runs.retain(db, KIND, report)
            artifact = capture(db, "github-observation:"+key, canonical(report).encode(), {
                "repository": intent["repository"], "name": "github-observation.json", "orderAt": report["observedAt"],
                "provenance": PROVENANCE, "githubObservationHash": key_hash, "references": [{
                    "workerId": worker_id, "intentHash": digest(intent), "commit": request["commit"], "subject": subject,
                    "at": report["observedAt"]} for subject in ("ci", "merge")]})
            receipt = receipt_for(report, artifact)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, REQUEST, canonical(receipt)))
            self.ledger.event(db, "github_observed", {"workerId": worker_id, "observationHash": key_hash, "artifactId": artifact["id"]})
            return receipt
