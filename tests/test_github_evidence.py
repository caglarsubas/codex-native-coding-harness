"""Exact remote evidence fixtures. No test makes an external network request."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import github_evidence as github, result_review
from orchestrator.core import Refusal, canonical, digest
from orchestrator.resources import remote_key
import test_dispatch_admission
import test_ownership_settlement
import test_result_review

URL = "https://github.com/example/repo/pull/1"
COMMIT = "f"*40
BASE = "c"*40
BRANCH = "codex/test-001"
SLUG = "example/repo"


def payloads():
    return {
        "pull": {"number": 1, "html_url": URL, "head": {"sha": COMMIT, "ref": BRANCH, "repo": {"full_name": SLUG}},
                 "base": {"sha": BASE, "ref": "main", "repo": {"full_name": SLUG}}, "state": "open",
                 "merged": False, "merged_at": None, "merge_commit_sha": "d"*40, "draft": False,
                 "body": "PRIVATE PR BODY MUST NOT BE RETAINED"},
        "classic": {"required_status_checks": {"contexts": ["tests"], "checks": [{"context": "tests", "app_id": 7}], "strict": True}},
        "rules": [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "tests", "integration_id": 7}]}}],
        "suites": {"total_count": 1, "check_suites": [{"id": 11, "head_sha": COMMIT}]},
        "runs": {"total_count": 1, "check_runs": [{"id": 12, "head_sha": COMMIT, "name": "tests", "app": {"id": 7},
                  "check_suite": {"id": 11}, "status": "completed", "conclusion": "success", "output": {"text": "PRIVATE CHECK OUTPUT"}}]},
        "statuses": {"sha": COMMIT, "total_count": 0, "statuses": [], "repository": {"full_name": SLUG}},
    }


class Reader:
    def __init__(self, data=None):
        self.data = copy.deepcopy(data or payloads()); self.calls = []

    def __call__(self, endpoint, deadline):
        self.calls.append(endpoint)
        key = ("pull" if "/pulls/" in endpoint else "classic" if endpoint.endswith("/protection") else
               "rules" if "/rules/branches/" in endpoint else "suites" if "/check-suites?" in endpoint else
               "runs" if "/check-runs?" in endpoint else "statuses" if "/status?" in endpoint else None)
        if key is None: raise AssertionError("Unexpected endpoint")
        result = self.data[key]
        if isinstance(result, Exception): raise result
        return copy.deepcopy(result)


class GitHubProjectionTest(unittest.TestCase):
    def inspect(self, reader=None):
        return github.inspect_github(URL, COMMIT, BASE, BRANCH, reader=reader or Reader())

    def test_exact_projection_redacts_bodies_and_merely_observes(self):
        reader = Reader(); report = self.inspect(reader)
        self.assertEqual(report["ciStatus"], "verified")
        self.assertEqual(report["ci"]["requiredChecks"], ["tests [app:7]"])
        self.assertEqual(report["pr"]["mergeCommit"], None)  # Open PR's test-merge SHA is not a merge.
        self.assertEqual(report["pr"]["headSHA"], COMMIT)
        self.assertNotIn("PRIVATE", canonical(report)); self.assertEqual(len(reader.calls), 12)
        self.assertFalse(report["atomicSnapshot"]); self.assertFalse(report["mergeAuthorized"])
        self.assertFalse(report["runtimeObserved"])
        self.assertEqual(report["observedAt"], report["startedAt"])

    def test_pending_failed_and_skipped_are_not_passing(self):
        for status, conclusion, expected in (("queued", None, "unverified"), ("in_progress", None, "unverified"),
            ("completed", "failure", "failed"), ("completed", "neutral", "unverified"),
            ("completed", "skipped", "unverified"), ("completed", "cancelled", "failed")):
            reader = Reader(); reader.data["runs"]["check_runs"][0].update(status=status, conclusion=conclusion)
            with self.subTest(conclusion=conclusion): self.assertEqual(self.inspect(reader)["ciStatus"], expected)

    def test_unavailable_policy_checks_or_suites_remain_unknown(self):
        for key in ("classic", "rules", "suites", "runs", "statuses"):
            reader = Reader(); reader.data[key] = Refusal("secret error must not leak")
            report = self.inspect(reader)
            self.assertEqual(report["ciStatus"], "unverified"); self.assertFalse(report["ci"]["complete"])
            self.assertNotIn("secret error", canonical(report))

    def test_empty_requirements_are_not_green_ci(self):
        reader = Reader(); reader.data["classic"] = {"required_status_checks": None}; reader.data["rules"] = []
        report = self.inspect(reader)
        self.assertEqual(report["ciStatus"], "unverified"); self.assertIn("no_required_checks", report["issues"])

    def test_effective_rules_union_classic_policy_and_provider_bindings(self):
        reader = Reader()
        reader.data["rules"][0]["parameters"]["required_status_checks"].append({"context": "security", "integration_id": 9})
        report = self.inspect(reader)
        self.assertEqual(len(report["ci"]["requiredChecks"]), 2)
        self.assertEqual(report["ciStatus"], "unverified"); self.assertIn("required_check_missing", report["issues"])

    def test_unpinned_provider_checks_cannot_satisfy_pinned_requirement(self):
        reader = Reader(); reader.data["runs"]["check_runs"][0]["app"]["id"] = 8
        report = self.inspect(reader)
        self.assertIn("required_check_missing", report["issues"]); self.assertEqual(report["ciStatus"], "unverified")

    def test_legacy_status_provider_is_not_guessed(self):
        reader = Reader(); reader.data["statuses"].update(total_count=1, statuses=[{"id": 20, "context": "tests", "state": "success"}])
        report = self.inspect(reader)
        self.assertIn("legacy_status_provider_unverified", report["issues"])
        reader.data["classic"]["required_status_checks"]["checks"][0]["app_id"] = -1
        reader.data["rules"] = []
        self.assertEqual(self.inspect(reader)["ciStatus"], "verified")
        reader.data["statuses"]["statuses"][0]["state"] = "failure"
        self.assertEqual(self.inspect(reader)["ciStatus"], "failed")

    def test_same_name_ambiguous_reruns_refuse_green_ci(self):
        reader = Reader(); duplicate = copy.deepcopy(reader.data["runs"]["check_runs"][0]); duplicate["id"] = 13
        reader.data["runs"]["check_runs"].append(duplicate); reader.data["runs"]["total_count"] = 2
        report = self.inspect(reader)
        self.assertIn("ambiguous_check_runs", report["issues"]); self.assertEqual(report["ciStatus"], "unverified")

    def test_unsupported_required_workflows_merge_queue_and_new_rules_are_unknown(self):
        for kind in ("workflows", "required_code_scanning", "merge_queue", "future_rule"):
            reader = Reader(); reader.data["rules"].append({"type": kind})
            report = self.inspect(reader)
            self.assertIn("unsupported_effective_rule", report["issues"]); self.assertFalse(report["ci"]["complete"])

    def test_incomplete_overflow_and_duplicate_inventories_refuse(self):
        for key in ("suites", "runs", "statuses"):
            for count in (True, -1, 2, 101):
                reader = Reader(); reader.data[key]["total_count"] = count
                with self.subTest(key=key, count=count), self.assertRaises(Refusal): self.inspect(reader)
        reader = Reader(); reader.data["rules"] *= 100
        with self.assertRaises(Refusal): self.inspect(reader)

    def test_malformed_policy_is_a_bounded_refusal(self):
        for parameters in (None, [], "invalid", {"required_status_checks": None}):
            reader = Reader(); reader.data["rules"][0]["parameters"] = parameters
            with self.subTest(parameters=parameters), self.assertRaises(Refusal): self.inspect(reader)

    def test_duplicate_remote_identities_are_not_complete_coverage(self):
        for key, field in (("suites", "check_suites"), ("runs", "check_runs"), ("statuses", "statuses")):
            reader = Reader()
            if key == "statuses": reader.data[key][field] = [{"id": 20, "context": "tests", "state": "success"}]
            reader.data[key][field] *= 2; reader.data[key]["total_count"] = 2
            with self.subTest(key=key), self.assertRaises(Refusal): self.inspect(reader)

    def test_total_deadline_refuses_before_network(self):
        reader = Reader()
        with patch.object(github.time, "monotonic", side_effect=[0, 31]), self.assertRaisesRegex(Refusal, "deadline"):
            self.inspect(reader)
        self.assertEqual(reader.calls, [])

    def test_head_base_branch_fork_and_url_identity_must_match(self):
        for side, field, value in (("head", "sha", "a"*40), ("base", "sha", "a"*40), ("head", "ref", "codex/other"),
                                    ("head", "repo", {"full_name": "other/repo"}), ("base", "repo", None)):
            reader = Reader(); reader.data["pull"][side][field] = value
            with self.subTest(field=field), self.assertRaises(Refusal): self.inspect(reader)
        reader = Reader(); reader.data["pull"]["html_url"] = "https://github.com/other/repo/pull/1"
        with self.assertRaises(Refusal): self.inspect(reader)

    def test_check_and_status_commit_or_repository_mismatch_refuses(self):
        for key, field in (("suites", "check_suites"), ("runs", "check_runs")):
            reader = Reader(); reader.data[key][field][0]["head_sha"] = "e"*40
            with self.assertRaises(Refusal): self.inspect(reader)
        reader = Reader(); reader.data["statuses"]["sha"] = "e"*40
        with self.assertRaises(Refusal): self.inspect(reader)
        reader = Reader(); reader.data["statuses"]["repository"]["full_name"] = "other/repo"
        with self.assertRaises(Refusal): self.inspect(reader)

    def test_policy_and_check_drift_between_rounds_refuse(self):
        for key in ("classic", "runs", "pull"):
            reader = Reader()
            def changed(endpoint, deadline):
                if len(reader.calls) == 6:
                    if key == "classic": reader.data[key]["required_status_checks"]["strict"] = False
                    elif key == "runs": reader.data[key]["check_runs"][0]["conclusion"] = "failure"
                    else: reader.data[key]["head"]["sha"] = "e"*40
                return reader(endpoint, deadline)
            with self.subTest(key=key), self.assertRaises(Refusal): self.inspect(changed)

    def test_merged_state_is_observed_not_merge_permission(self):
        reader = Reader(); reader.data["pull"].update(merged=True, state="closed", merged_at="2026-01-01T01:01:01Z")
        report = self.inspect(reader)
        self.assertEqual(report["pr"]["state"], "merged"); self.assertEqual(report["pr"]["mergeCommit"], "d"*40)
        self.assertFalse(report["mergeAuthorized"])
        reader.data["pull"]["state"] = "open"
        with self.assertRaises(Refusal): self.inspect(reader)

    def test_noncanonical_or_untrusted_targets_refuse_before_io(self):
        for url in ("http://github.com/example/repo/pull/1", URL+"?token=secret", URL+"#fragment",
                    "https://token@github.com/example/repo/pull/1", "https://other.test/example/repo/pull/1",
                    "https://github.com/example/../pull/1", "https://github.com/example/repo/pull/01"):
            with self.subTest(url=url), self.assertRaises(Refusal), patch.object(github, "api_read", side_effect=AssertionError("No request")):
                github.inspect_github(url, COMMIT, BASE, BRANCH)

    def test_transport_uses_only_explicit_get_and_bounded_private_environment(self):
        original = subprocess.Popen; observed = []
        def process(argv, **kwargs):
            observed.append((argv, kwargs))
            return original([sys.executable, "-c", "print('{}')"], **kwargs)
        with patch.object(github.shutil, "which", return_value="/trusted/gh"), patch.object(github.subprocess, "Popen", side_effect=process), \
             patch.dict(os.environ, {"GH_HOST": "evil.test", "GH_DEBUG": "api", "INFERENCE_API_KEY": "fixture-secret"}):
            self.assertEqual(github.api_read("repos/example/repo/pulls/1", time.monotonic()+10), {})
        argv, kwargs = observed[0]
        self.assertEqual(argv[1:7], ["api", "--hostname", "github.com", "--method", "GET", "-H"])
        self.assertNotIn("GH_HOST", kwargs["env"]); self.assertNotIn("GH_DEBUG", kwargs["env"])
        self.assertNotIn("INFERENCE_API_KEY", kwargs["env"]); self.assertNotIn("shell", kwargs)
        self.assertIn("X-GitHub-Api-Version: "+github.API_VERSION, argv)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)

    def test_transport_limits_errors_duplicate_json_and_output(self):
        original = subprocess.Popen
        for code in ("import sys; sys.exit(1)", "print('{\"a\":1,\"a\":2}')", "print('x'*512001)", "print('NaN')"):
            def process(argv, **kwargs): return original([sys.executable, "-c", code], **kwargs)
            with self.subTest(code=code), patch.object(github.shutil, "which", return_value="/trusted/gh"), \
                 patch.object(github.subprocess, "Popen", side_effect=process), self.assertRaises(Refusal):
                github.api_read("repos/example/repo/pulls/1", time.monotonic()+5)

    def test_transport_timeout_is_not_a_retry(self):
        original = subprocess.Popen
        def process(argv, **kwargs): return original([sys.executable, "-c", "import time; time.sleep(5)"], **kwargs)
        with patch.object(github.shutil, "which", return_value="/trusted/gh"), \
             patch.object(github.subprocess, "Popen", side_effect=process) as proc, self.assertRaises(Refusal):
            github.api_read("repos/example/repo/pulls/1", time.monotonic()+.05)
        self.assertEqual(proc.call_count, 1)


class GitHubRetentionTest(unittest.TestCase):
    def setUp(self):
        key = remote_key("https://github.com/"+SLUG)
        for target in (test_dispatch_admission, test_ownership_settlement):
            mock = patch.object(target, "KEY", key); mock.start(); self.addCleanup(mock.stop)
        self.fx = test_result_review.ResultReviewTest(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.api = github.GitHubObserver(self.fx.fx.bridge)
        self.ledger, self.store, self.token, self.wid = self.fx.ledger, self.fx.store, self.fx.token, self.fx.wid
        self.reader = Reader()
        mock = patch.object(github, "api_read", self.reader); mock.start(); self.addCleanup(mock.stop)

    def request(self, **fields):
        return {"id": "github-1", "expectedRevision": self.ledger.snapshot()["meta"]["revision"],
                "settlementHash": self.fx.worker()["ownershipSettlementHash"], "commit": COMMIT, "prUrl": URL, **fields}

    def observe(self, request=None): return self.api.observe(self.token, self.wid, request or self.request())
    def report(self, receipt): return self.ledger.document(receipt["observationHash"])
    def pause(self): self.fx.fx.fx.fx.fx.fx.command("pause")

    def review_request(self, receipt, outcome="accepted", subject="ci", **changes):
        report = self.report(receipt); result = self.fx.evidence()["result"]
        result.update(pr=report["pr"], ci=report["ci"])
        result["evidence"][subject] = {"status": "verified", "artifactId": receipt["artifactId"], "observedAt": time.time()}
        result.update(changes); result["observedAt"] = time.time()
        return self.fx.request(result, outcome)

    def test_provenance_artifact_is_atomic_without_shared_or_worker_mutation(self):
        before = self.store.snapshot(); worker = self.fx.worker(); receipt = self.observe()
        self.assertEqual(before, self.store.snapshot()); self.assertEqual(worker, self.fx.worker())
        self.assertEqual(receipt["ciStatus"], "verified"); self.assertFalse(receipt["packetAccepted"])
        with self.ledger.tx() as db:
            info, raw = result_review.artifact_in(db, receipt["artifactId"], self.fx.intent, "ci", COMMIT)
        self.assertEqual(info["provenance"], github.PROVENANCE)
        self.assertNotIn(b"PRIVATE", raw)
        self.assertEqual(json.loads(raw), self.report(receipt))

    def test_collected_ci_supports_separate_review_not_runtime(self):
        receipt = self.observe(); request = self.review_request(receipt)
        self.assertTrue(self.fx.review(request)["packetAccepted"])
        self.assertEqual(self.fx.worker()["evidence"]["runtime"]["status"], "unverified")
        self.assertFalse(self.ledger.snapshot()["meta"]["pilotPassed"])

    def test_replay_after_pause_expiry_and_fence_never_recollects(self):
        request = self.request(); first = self.observe(request); calls = len(self.reader.calls)
        self.pause(); (self.ledger.root / "admission-fence.json").touch(mode=0o600)
        before = self.fx.logical()
        with patch.object(self.store, "clock", return_value=time.time()+10000):
            self.assertEqual(self.observe(request), first)
        self.assertEqual(before, self.fx.logical()); self.assertEqual(calls, len(self.reader.calls))
        with self.assertRaises(Refusal): self.observe(request | {"prUrl": URL.replace("/1", "/2")})

    def test_wrong_controller_revision_and_remote_refuse_before_network(self):
        for fields in ({"prUrl": "https://github.com/other/repo/pull/1"}, {"expectedRevision": 0},
                       {"settlementHash": "e"*64}, {"commit": "HEAD"}, {"endpoint": "/arbitrary"}):
            with self.subTest(fields=fields), self.assertRaises(Refusal): self.observe(self.request(**fields))
        with self.assertRaises(Refusal): self.api.observe("wrong", self.wid, self.request())
        self.assertEqual(self.reader.calls, [])

    def test_pause_during_collection_discards_retention(self):
        original = github.inspect_github
        def inspect(*args, **kwargs):
            report = original(*args, **kwargs); self.pause(); return report
        with patch.object(github, "inspect_github", side_effect=inspect), self.assertRaises(Refusal): self.observe()
        with self.ledger.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (github.KIND,)).fetchone()[0], 0)
        with self.assertRaises(Refusal): self.observe()
        self.assertEqual(len(self.reader.calls), 12)

    def test_event_failure_rolls_back_all_local_evidence(self):
        before = self.fx.logical(); shared = self.store.snapshot()
        with patch.object(self.api.ledger, "event", side_effect=RuntimeError("retention crash")), self.assertRaises(RuntimeError):
            self.observe()
        self.assertEqual(before, self.fx.logical()); self.assertEqual(shared, self.store.snapshot())
        self.assertEqual(self.observe()["ciStatus"], "verified")

    def test_concurrent_identical_observations_retain_one_receipt(self):
        request = self.request()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.observe(request), range(2)))
        self.assertEqual(results[0], results[1])
        with self.ledger.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (github.KIND,)).fetchone()[0], 1)

    def test_changed_ci_or_pr_projection_is_not_accepted(self):
        receipt = self.observe()
        for section, field, value in (("ci", "requiredChecks", ["different"]), ("pr", "mergeCommit", "d"*40),
                                      ("pr", "url", "https://github.com/other/repo/pull/1")):
            request = self.review_request(receipt); result = request["result"]; result[section][field] = value
            request = self.fx.request(result)
            with self.subTest(field=field), self.assertRaises(Refusal): self.fx.review(request)

    def test_missing_journal_receipt_or_provenance_never_falls_back(self):
        receipt = self.observe(); request = self.review_request(receipt)
        with self.ledger.tx() as db:
            db.execute("DELETE FROM snapshots WHERE id=?", (receipt["observationHash"],))
        with self.assertRaises(Refusal): self.fx.review(request)
        with self.assertRaises(Refusal): self.observe(self.report_request(receipt))

    def report_request(self, receipt):
        # No extra read of a deliberately deleted journal: request was initially revision-bound.
        with self.ledger.tx() as db:
            _, raw = result_review.artifact_in(db, receipt["artifactId"], self.fx.intent, "ci", COMMIT)
        return json.loads(raw)["request"]

    def test_removed_provenance_still_requires_collector_binding(self):
        receipt = self.observe(); request = self.review_request(receipt)
        with self.ledger.tx() as db:
            info = json.loads(db.execute("SELECT data FROM artifact_versions WHERE id=?", (receipt["artifactId"],)).fetchone()[0])
            info.pop("provenance")
            db.execute("UPDATE artifact_versions SET data=? WHERE id=?", (canonical(info), receipt["artifactId"]))
        with self.assertRaisesRegex(Refusal, "provenance"): self.fx.review(request)

    def test_missing_request_receipt_never_becomes_generic_evidence(self):
        receipt = self.observe(); request = self.review_request(receipt)
        key = self.report(receipt)["requestKey"]
        with self.ledger.tx() as db:
            db.execute("DELETE FROM snapshots WHERE id=?", (key,))
        with self.assertRaisesRegex(Refusal, "receipt changed or missing"): self.fx.review(request)

    def test_corrupt_request_receipt_is_a_refusal_not_a_crash(self):
        request = self.request(); receipt = self.observe(request); key = self.report(receipt)["requestKey"]
        for data in ("not JSON", "[]", "null"):
            with self.ledger.tx() as db: db.execute("UPDATE snapshots SET data=? WHERE id=?", (data, key))
            with self.subTest(data=data), self.assertRaisesRegex(Refusal, "Invalid retained GitHub receipt"):
                self.observe(request)

    def test_unavailable_policy_cannot_be_promoted_to_verified(self):
        self.reader.data["classic"] = Refusal("unavailable")
        receipt = self.observe(); self.assertEqual(receipt["ciStatus"], "unverified")
        request = self.review_request(receipt)
        with self.assertRaisesRegex(Refusal, "cannot be promoted"): self.fx.review(request)

    def test_failed_ci_can_support_rejection_but_never_acceptance(self):
        self.reader.data["runs"]["check_runs"][0]["conclusion"] = "failure"
        receipt = self.observe(); self.assertEqual(receipt["ciStatus"], "failed")
        request = self.review_request(receipt)
        with self.assertRaisesRegex(Refusal, "cannot be promoted"): self.fx.review(request)
        result = request["result"]; result["evidence"]["ci"]["status"] = "failed"
        request = self.fx.request(result, "changes_required")
        self.assertFalse(self.fx.review(request)["packetAccepted"])
        self.assertEqual(self.fx.worker()["status"], "settled")

    def test_collector_cannot_be_reused_for_unrelated_axis(self):
        receipt = self.observe(); report = self.report(receipt)
        with self.ledger.tx() as db:
            info, raw = result_review.artifact_in(db, receipt["artifactId"], self.fx.intent, "ci", COMMIT)
            with self.assertRaisesRegex(Refusal, "cannot prove"):
                github.validate_github_proof(db, info, raw, self.fx.intent, {}, {}, "runtime")
        self.assertFalse(report["runtimeObserved"])

    def test_original_collection_time_is_not_renewed_by_review(self):
        receipt = self.observe(); later = time.time()+61
        # Every supplied review/proof time is new; only the collector's original
        # observation is stale. Repackaging it must not renew that observation.
        with patch("time.time", return_value=later), patch.object(self.store, "clock", return_value=later):
            request = self.review_request(receipt)
            with self.assertRaisesRegex(Refusal, "Fresh non-future observation required"): self.fx.review(request)

    def test_separate_merged_proof_does_not_authorize_merge(self):
        self.reader.data["pull"].update(merged=True, state="closed", merged_at="2026-01-01T00:00:00Z")
        receipt = self.observe(); request = self.review_request(receipt, subject="merge")
        # Use the same collector's CI projection for its CI proof too.
        request["result"]["evidence"]["ci"] = {"status": "verified", "artifactId": receipt["artifactId"], "observedAt": time.time()}
        request["result"]["observedAt"] = time.time(); request = self.fx.request(request["result"])
        self.assertTrue(self.fx.review(request)["packetAccepted"]); self.assertFalse(receipt["mergeAuthorized"])

    def test_harness_policy_refuses_before_any_network(self):
        import test_core
        initialize, make_seed = test_core.Ledger.initialize, test_core.seed
        def harness_initialize(ledger, config):
            config = copy.deepcopy(config)
            for repo in config["repositories"]:
                if repo["id"] == "a": repo.update(policyProfile="harness")
            return initialize(ledger, config)
        def harness_seed(*args, **kwargs):
            kwargs["profile"] = "harness"
            return make_seed(*args, **kwargs)
        other = test_ownership_settlement.OwnershipSettlementTest()
        with patch.object(test_core.Ledger, "initialize", harness_initialize), patch.object(test_core, "seed", harness_seed):
            other.setUp()
        try:
            other.settle(); api = github.GitHubObserver(other.bridge)
            request = self.request(expectedRevision=other.ledger.snapshot()["meta"]["revision"],
                                   settlementHash=other.worker()["ownershipSettlementHash"])
            with self.assertRaisesRegex(Refusal, "Harness result acceptance needs its trusted adapter"):
                api.observe(other.token, other.wid, request)
        finally: other.tearDown()
        self.assertEqual(self.reader.calls, [])


if __name__ == "__main__": unittest.main()
