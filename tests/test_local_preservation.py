"""Private fixture Git/ledger only. No live native tools or remote requests."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import local_preservation as preservation, source_observation as source
from orchestrator.core import Refusal, canonical
from orchestrator.observations import artifact
from test_source_observation import GitFixture
import test_result_handoff
import test_result_review


class LocalGitPreservationTest(GitFixture, unittest.TestCase):
    def setUp(self): self.make_git()

    def collect(self):
        return preservation.preserve_git(str(self.repo), self.key, self.base, self.result, "codex/test-001")

    def test_bundle_restores_without_source_and_does_not_read_working_files(self):
        (self.repo / "src/example.py").write_text("PRIVATE UNCOMMITTED SECRET\n")
        before = self.disk(); bundle, report = self.collect()
        self.assertEqual(before, self.disk()); self.assertNotIn(b"PRIVATE UNCOMMITTED SECRET", bundle)
        self.assertTrue(report["restoredWithoutSource"]); self.assertTrue(report["gitIntegrityVerified"])
        self.assertFalse(report["offDeviceBackup"]); self.assertFalse(report["remoteObserved"])
        saved = self.root / "restorable.bundle"; saved.write_bytes(bundle)
        self.repo.rename(self.root / "inaccessible-original")
        restored = self.root / "restored.git"
        subprocess.run(["/usr/bin/git", "-c", "protocol.file.allow=always", "clone", "--bare", str(saved), str(restored)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        self.assertEqual(source.commit_tree(restored, self.base), report["baseTree"])
        self.assertEqual(source.commit_tree(restored, self.result), report["resultTree"])
        self.assertEqual(source.git_read(restored, ["show", self.result + ":src/example.py"]), b"result\n")

    def test_config_hooks_replacements_and_inherited_environment_are_ignored(self):
        trap = self.root / "no-hook"
        config = self.repo / ".git/config"
        config.write_text(config.read_text() + '\n[core]\n fsmonitor = touch ' + str(trap) +
                          '\n[remote "origin"]\n url = ext::bad\n promisor = true\n')
        replacements = self.repo / ".git/refs/replace"; replacements.mkdir()
        (replacements / self.result).write_text(self.base + "\n")
        with patch.dict(os.environ, {"GIT_DIR": "/missing", "GIT_OBJECT_DIRECTORY": "/missing",
                                    "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "include.path", "GIT_CONFIG_VALUE_0": "/missing"}):
            _, report = self.collect()
        self.assertEqual(report["commit"], self.result); self.assertFalse(trap.exists())

    def test_linked_worktree_and_packed_objects(self):
        linked = self.root / "linked"
        self.git("switch", "main"); self.git("worktree", "add", str(linked), "codex/test-001")
        self.git("repack", "-ad"); self.git("pack-refs", "--all", "--prune")
        self.repo = linked
        self.assertTrue(self.collect()[1]["gitIntegrityVerified"])

    def test_missing_blob_refuses_instead_of_retaining_structure_only(self):
        blob = self.git("rev-parse", self.result + ":src/example.py")
        (self.repo / ".git/objects" / blob[:2] / blob[2:]).rename(self.root / "missing-blob")
        with self.assertRaises(Refusal): self.collect()

    def test_oversized_bundle_refuses(self):
        with patch.object(preservation, "MAX_ARTIFACT", 128), self.assertRaisesRegex(Refusal, "bound"):
            self.collect()

    def test_corrupt_pack_is_rejected_by_independent_restore(self):
        read = source.git_read
        def corrupt(view, args, **kwargs):
            raw = read(view, args, **kwargs)
            return raw[:-1] + bytes([raw[-1] ^ 1]) if args[:2] == ["bundle", "create"] else raw
        with patch.object(source, "git_read", corrupt), self.assertRaises(Refusal): self.collect()

    def test_branch_drift_during_restore_refuses(self):
        read = source.git_read
        def drift(view, args, **kwargs):
            raw = read(view, args, **kwargs)
            if args[0] == "fsck": (self.repo / ".git/refs/heads/codex/test-001").write_text(self.base + "\n")
            return raw
        with patch.object(source, "git_read", drift), self.assertRaisesRegex(Refusal, "branch changed"):
            self.collect()

    def test_alternates_shallow_and_symlink_storage_refuse(self):
        for name in ("shallow", "objects/info/alternates"):
            file = self.repo / ".git" / name; file.parent.mkdir(exist_ok=True, parents=True); file.write_text("unsupported\n")
            try:
                with self.assertRaisesRegex(Refusal, "separate adapter"): self.collect()
            finally: file.unlink()
        (self.repo / ".git/objects/trap").symlink_to(self.root)
        with self.assertRaisesRegex(Refusal, "indirection"): self.collect()


class PreservationHandoffTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_result_handoff.ResultHandoffTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.ledger = self.fx.ledger

    def prepare(self, cli=False):
        result = self.fx.review_request(cli=cli)["result"]
        rows = [{"subject": axis, "artifactId": p["artifactId"]} for axis, p in result["evidence"].items() if p["artifactId"]]
        rows += [{"subject": "criterion:" + str(row["index"]), "artifactId": row["proof"]["artifactId"]} for row in result["criteria"]]
        request = self.fx.request(evidence=sorted(rows, key=lambda r: r["subject"]))
        return result, request

    def collect(self, request, cli=False): return self.fx.call("collect_preservation", request, cli)

    def read(self, receipt):
        return self.fx.call("proof_read", {"artifactId": receipt["artifactId"], "subject": "preservation", "commit": self.fx.result})

    def review_request(self, result, receipt):
        result["preservation"] = {"status": "verified", "artifactId": receipt["artifactId"], "observedAt": time.time()}
        return self.fx.with_review(result)

    def test_cli_collect_read_review_and_historical_state(self):
        shared = self.fx.store.snapshot(); result, request = self.prepare(cli=True)
        receipt = self.collect(request, cli=True)
        self.assertFalse(receipt["packetAccepted"]); self.assertFalse(receipt["archiveAuthorized"])
        self.assertEqual(self.fx.fx.worker()["status"], "settled")
        read = self.read(receipt); report = json.loads(read["content"])
        self.assertEqual(read["provenance"], preservation.PROVENANCE)
        self.assertEqual(report["bundle"]["id"], receipt["bundleArtifactId"])
        self.assertEqual(len(report["inventory"]["handoffs"]), 1)
        metadata, bundle = artifact(self.ledger, receipt["bundleArtifactId"])
        self.assertEqual(metadata["sha256"], hashlib.sha256(bundle).hexdigest())
        accepted = self.fx.call("review", self.review_request(result, receipt), cli=True)
        self.assertTrue(accepted["packetAccepted"]); self.assertFalse(accepted["archiveAuthorized"])
        self.fx.pause(); before = self.fx.logical()
        with patch("subprocess.Popen", side_effect=AssertionError("Historical reads must not run Git")):
            self.assertEqual(self.collect(request), receipt)
            self.assertEqual(self.read(receipt), read)
            self.assertEqual(self.fx.call("state")["review"], accepted)
        self.assertEqual(before, self.fx.logical()); self.assertEqual(shared, self.fx.store.snapshot())

    def test_pause_and_revision_fence_before_git(self):
        _, request = self.prepare(); before = self.fx.logical()
        with patch.object(preservation, "preserve_git", side_effect=AssertionError("No Git before authority")):
            with self.assertRaises(Refusal): self.collect(request | {"expectedRevision": 0})
        self.assertEqual(before, self.fx.logical()); self.fx.pause()
        with patch.object(preservation, "preserve_git", side_effect=AssertionError("No Git after Pause")):
            with self.assertRaises(Refusal): self.collect(request)

    def test_maintenance_blocks_new_collection_but_expired_replay_is_historical(self):
        _, request = self.prepare(); receipt = self.collect(request)
        self.fx.pause(); (self.ledger.root / "admission-fence.json").touch(mode=0o600)
        before = self.fx.logical()
        with patch.object(self.fx.store, "clock", return_value=time.time() + 1000), \
             patch.object(preservation, "preserve_git", side_effect=AssertionError("No I/O behind fence")):
            self.assertEqual(self.collect(request), receipt); self.read(receipt)
            with self.assertRaises(Refusal): self.collect(request | {"id": "new"})
        self.assertEqual(before, self.fx.logical())

    def test_pause_during_collection_leaves_no_bundle_or_manifest(self):
        _, request = self.prepare(); collect = preservation.preserve_git
        def pause(*args):
            measured = collect(*args); self.fx.pause(); return measured
        with patch.object(preservation, "preserve_git", pause), self.assertRaises(Refusal): self.collect(request)
        with self.ledger.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM artifact_versions WHERE json_extract(data,'$.provenance')=?", (preservation.PROVENANCE,)).fetchone()[0], 0)

    def test_atomic_event_failure_rolls_back_bundle_manifest_and_receipt(self):
        _, request = self.prepare(); before = self.fx.logical()
        with patch.object(self.fx.api.ledger, "event", side_effect=RuntimeError("fixture crash")), self.assertRaises(RuntimeError):
            self.collect(request)
        self.assertEqual(before, self.fx.logical())

    def test_concurrent_identical_requests_retain_one_bundle_and_manifest(self):
        _, request = self.prepare()
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(lambda _: self.collect(request), range(2)))
        self.assertEqual(receipts[0], receipts[1])
        with self.ledger.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM artifact_versions WHERE json_extract(data,'$.provenance')=?", (preservation.PROVENANCE,)).fetchone()[0], 2)

    def test_replay_ignores_missing_source_but_checks_original_bytes(self):
        _, request = self.prepare(); receipt = self.collect(request)
        self.fx.repo.rename(self.fx.root / "removed-source")
        with patch("subprocess.Popen", side_effect=AssertionError("No recollection")):
            self.assertEqual(self.collect(request), receipt); self.read(receipt)
        with self.ledger.tx() as db:
            db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"bad bundle", receipt["bundleArtifactId"]))
        with self.assertRaisesRegex(Refusal, "bundle bytes"): self.read(receipt)
        with self.assertRaises(Refusal): self.collect(request)

    def test_missing_bundle_and_missing_receipt_invalidate_historical_review(self):
        result, request = self.prepare(); receipt = self.collect(request)
        self.fx.call("review", self.review_request(result, receipt))
        with self.ledger.tx() as db:
            db.execute("DELETE FROM snapshots WHERE kind=?", (preservation.REQUEST,))
        with self.assertRaisesRegex(Refusal, "receipt changed or missing"): self.fx.call("state")
        with self.ledger.tx() as db:
            db.execute("DELETE FROM artifact_versions WHERE id=?", (receipt["bundleArtifactId"],))
        with self.assertRaisesRegex(Refusal, "bundle is missing"): self.read(receipt)

    def test_malformed_receipt_is_a_closed_refusal_not_a_recollection(self):
        _, request = self.prepare(); self.collect(request)
        with self.ledger.tx() as db:
            db.execute("UPDATE snapshots SET data=? WHERE kind=?", (canonical({"artifactId": "a" * 64}), preservation.REQUEST))
        with patch.object(preservation, "preserve_git", side_effect=AssertionError("No repair by recollection")):
            with self.assertRaises(Refusal): self.collect(request)

    def test_tampered_evidence_or_handoff_bytes_invalidate_manifest(self):
        _, request = self.prepare(); receipt = self.collect(request)
        report = json.loads(self.read(receipt)["content"])
        for key in (request["evidence"][0]["artifactId"], report["inventory"]["handoffs"][0]["id"]):
            with self.ledger.tx() as db:
                original = db.execute("SELECT content FROM artifact_versions WHERE id=?", (key,)).fetchone()[0]
                db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"tampered", key))
            with self.assertRaises(Refusal): self.read(receipt)
            with self.ledger.tx() as db: db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (original, key))
        self.read(receipt)

    def test_different_proof_versions_cannot_reuse_preservation(self):
        result, request = self.prepare(); receipt = self.collect(request)
        result["criteria"][0]["proof"] = self.fx.proof("criterion:0", content="New version")
        with self.assertRaisesRegex(Refusal, "differs from preserved versions"):
            self.fx.call("review", self.review_request(result, receipt))

    def test_missing_inventory_version_cannot_verify_a_larger_result(self):
        result, request = self.prepare(); request["evidence"] = request["evidence"][:1]
        receipt = self.collect(request)
        with self.assertRaisesRegex(Refusal, "differs from preserved versions"):
            self.fx.call("review", self.review_request(result, receipt))

    def test_old_collection_cannot_be_freshened_by_new_proof_timestamp(self):
        result, request = self.prepare(); receipt = self.collect(request)
        later = time.time() + 61
        with patch("time.time", return_value=later), patch.object(self.fx.store, "clock", return_value=later):
            with self.assertRaisesRegex(Refusal, "Fresh non-future"):
                self.fx.call("review", self.review_request(result, receipt))

    def test_closed_input_cycle_duplicate_subject_and_wrong_commit_refuse(self):
        _, request = self.prepare(); before = self.fx.logical()
        cases = [{"commit": "HEAD"}, {"commit": "d" * 40}, {"settlementHash": "e" * 64}, {"evidence": []},
                 {"evidence": request["evidence"] * 2}, {"evidence": [{"subject": "preservation", "artifactId": "a" * 64}]},
                 {"evidence": [{"subject": "independent_review", "artifactId": "a" * 64}]},
                 {"evidence": [{"subject": "criterion:999", "artifactId": "a" * 64}]}, {"path": "/arbitrary"}]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(Refusal): self.collect(request | change)
        self.assertEqual(before, self.fx.logical())

    def test_changed_replay_and_removed_provenance_refuse(self):
        _, request = self.prepare(); receipt = self.collect(request)
        with self.assertRaisesRegex(Refusal, "different content"):
            self.collect(request | {"expectedRevision": self.fx.revision()})
        with self.ledger.tx() as db:
            row = json.loads(db.execute("SELECT data FROM artifact_versions WHERE id=?", (receipt["artifactId"],)).fetchone()[0])
            row.pop("provenance")
            db.execute("UPDATE artifact_versions SET data=? WHERE id=?", (canonical(row), receipt["artifactId"]))
        with self.assertRaisesRegex(Refusal, "provenance"): self.read(receipt)

    def test_wrong_controller_workspace_and_cli_defaults_refuse(self):
        _, request = self.prepare()
        for kwargs in ({"token": "wrong"}, {"workspace": "missing"}, {"worker": "other"}, {"select": False}):
            self.assertNotEqual(self.fx.cli("collect-preservation", request=request, **kwargs).returncode, 0)

    def test_harness_refuses_before_any_source_access(self):
        self.fx.harness = True
        other = test_result_review.ResultReviewTest(); other.setUp(); self.addCleanup(other.tearDown)
        from orchestrator.result_handoff import ResultHandoff
        api = ResultHandoff(other.fx.bridge)
        request = self.fx.request(expectedRevision=other.ledger.snapshot()["meta"]["revision"],
                                 settlementHash=other.worker()["ownershipSettlementHash"],
                                 evidence=[{"subject": "source", "artifactId": "a" * 64}])
        with patch.object(preservation, "preserve_git", side_effect=AssertionError("No Harness access")):
            with self.assertRaisesRegex(Refusal, "Harness"): api.collect_preservation(other.token, other.wid, request)

    def test_brain_approval_without_owner_delegation_refuses_before_source_access(self):
        from orchestrator import run_authority as runs
        _, request = self.prepare()
        read = runs.document
        def forged(db, key, kind):
            value = read(db, key, kind)
            return value | {"actor": "designated_brain"} if kind == "run_task_approval" else value
        with patch.object(runs, "document", forged), \
             patch.object(preservation, "preserve_git", side_effect=AssertionError("No unauthorized source access")):
            with self.assertRaisesRegex(Refusal, "exact owner"): self.collect(request)

    def test_settled_acceptance_does_not_allow_new_preservation_or_archive(self):
        result, request = self.prepare(); receipt = self.collect(request)
        self.fx.call("review", self.review_request(result, receipt))
        with self.assertRaises(Refusal): self.collect(request | {"id": "new", "expectedRevision": self.fx.revision()})
        self.assertFalse(self.fx.fx.worker()["archived"])


class DelegatedPreservationTest(unittest.TestCase):
    def test_delegated_scope_preserves_local_bytes_without_archive_authority(self):
        import test_missions
        import test_run_authority
        specification, approve = test_missions.specification, test_run_authority.RunAuthorityTest.approve
        def delegated_spec(*args, **kwargs): return specification(*args, **{**kwargs, "mode": "phase_delegated"})
        def delegated_approval(fixture, run, **kwargs): return approve(fixture, run, **{**kwargs, "actor": "designated_brain"})
        other = PreservationHandoffTest()
        with patch.object(test_missions, "specification", delegated_spec), \
             patch.object(test_run_authority.RunAuthorityTest, "approve", delegated_approval): other.setUp()
        self.addCleanup(other.doCleanups)
        result, request = other.prepare(); receipt = other.collect(request)
        self.assertEqual(other.read(receipt)["provenance"], preservation.PROVENANCE)
        accepted = other.fx.call("review", other.review_request(result, receipt))
        self.assertTrue(accepted["packetAccepted"]); self.assertFalse(accepted["archiveAuthorized"])
        with patch.object(preservation, "preserve_git", side_effect=AssertionError("No replay I/O")):
            self.assertEqual(other.collect(request), receipt)


class LocalOnlyVerificationPolicyTest(unittest.TestCase):
    def test_repository_does_not_enable_actions_workflows(self):
        root = Path(__file__).resolve().parents[1] / ".github/workflows"
        self.assertFalse(list(root.glob("*.yml")) + list(root.glob("*.yaml")),
                         "Owner requires local verification and no extra GitHub Actions billing")


if __name__ == "__main__": unittest.main()
