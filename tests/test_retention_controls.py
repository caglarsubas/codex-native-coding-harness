"""Owner configuration in disposable fixtures; never a native archival call."""
import copy
import contextlib
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import retention_controls as controls, retention_policy as policy
from orchestrator.core import Refusal, canonical
from orchestrator.workspaces import fingerprint
import test_retention_policy


class RetentionControlsTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_retention_policy.RetentionPolicyTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.ledger = self.fx.ledger; self.api = controls.RetentionControls(); self.session = "fixture-session"
        self.fx.paused_flag(True)  # Isolated setup, not production Pause/release authority.

    def state(self): return controls.inspect(self.ledger)
    def logical(self):
        with contextlib.closing(self.ledger.connect()) as db: return fingerprint(db)
    def request(self, operation="review", **fields):
        state = self.state()
        body = {"operation": operation, "expectedRevision": state["workspaceRevision"], "contextHash": state["contextHash"]}
        body.update({"runHash": state["currentRun"]["runHash"], "expectedPolicyHash": state["policy"]["policyHash"] if state["policy"] else None,
                     "maxArchives": 1, "minimumRetentionSeconds": 3600} if operation == "review" else
                    {"policyHash": state["policy"]["policyHash"], "reason": "Keep local tasks available"})
        return body | fields
    def preview(self, operation="review", **fields): return self.api.preview(self.ledger, self.request(operation, **fields), self.session)
    def confirm(self, proposal, **fields):
        return self.api.confirm(self.ledger, {"proposal": proposal, "confirmed": True,
            "cleanupAcknowledged": proposal["document"]["operation"] == "review", **fields}, self.session)

    def test_inspection_and_preview_are_read_only(self):
        before = self.logical(); shared = self.fx.api.store.snapshot()
        state = self.state(); preview = self.preview()
        self.assertTrue(state["canReview"]); self.assertTrue(state["canRevoke"])
        self.assertFalse(state["executionAuthorized"]); self.assertEqual(state["policy"]["recordedAttempts"], 0)
        self.assertEqual(preview["document"]["request"]["maxArchives"], 1)
        self.assertEqual(before, self.logical()); self.assertEqual(shared, self.fx.api.store.snapshot())

    def test_review_revoke_and_historical_retry_never_restore_authority(self):
        shared = self.fx.api.store.snapshot(); preview = self.preview()
        first = self.confirm(preview); self.assertFalse(first["replayed"])
        self.assertEqual(self.state()["policy"]["version"], 2)
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        revoked = self.preview("revoke"); self.confirm(revoked)
        before = self.logical()
        with patch("orchestrator.retention_controls.time.time", return_value=time.time()+1000):
            replay = self.confirm(preview)
        self.assertTrue(replay["replayed"]); self.assertEqual(replay["receipt"], first["receipt"])
        self.assertEqual(before, self.logical()); self.assertTrue(self.state()["policy"]["revoked"])
        self.assertEqual(self.ledger.snapshot()["commands"], []); self.assertEqual(shared, self.fx.api.store.snapshot())

    def test_confirmation_and_cleanup_must_be_explicit_booleans(self):
        preview = self.preview(); before = self.logical()
        for change in ({"confirmed": False}, {"confirmed": 1}, {"cleanupAcknowledged": False}, {"cleanupAcknowledged": 1}, {"extra": True}):
            with self.subTest(change=change), self.assertRaises(Refusal): self.confirm(preview, **change)
        self.assertEqual(before, self.logical())

    def test_tampering_session_restart_and_workspace_refuse(self):
        preview = self.preview(); changed = copy.deepcopy(preview); changed["document"]["request"]["maxArchives"] = 2
        with self.assertRaises(Refusal): self.confirm(changed)
        body = {"proposal": preview, "confirmed": True, "cleanupAcknowledged": True}
        with self.assertRaises(Refusal): self.api.confirm(self.ledger, body, "other-session")
        with self.assertRaises(Refusal): controls.RetentionControls().confirm(self.ledger, body, self.session)
        foreign = copy.deepcopy(preview); foreign["document"]["workspaceId"] = "b"; foreign["signature"] = self.api.sign(foreign["document"])
        with self.assertRaises(Refusal): self.confirm(foreign)

    def test_expired_unused_preview_refuses(self):
        preview = self.preview(); before = self.logical()
        with patch("orchestrator.retention_controls.time.time", return_value=time.time()+301), self.assertRaisesRegex(Refusal, "expired"):
            self.confirm(preview)
        self.assertEqual(before, self.logical())

    def test_revision_pause_and_policy_changes_invalidate_preview(self):
        preview = self.preview()
        self.fx.paused_flag(False)
        with self.assertRaisesRegex(Refusal, "changed"): self.confirm(preview)
        self.fx.paused_flag(True)
        self.fx.revoke()
        with self.assertRaises(Refusal): self.confirm(preview)

    def test_concurrent_confirm_commits_once(self):
        preview = self.preview()
        with ThreadPoolExecutor(max_workers=2) as pool: receipts = list(pool.map(lambda _: self.confirm(preview), range(2)))
        self.assertEqual(sum(not r["replayed"] for r in receipts), 1)
        self.assertEqual(receipts[0]["receipt"], receipts[1]["receipt"])
        self.assertEqual(self.state()["policy"]["version"], 2)

    def test_event_failure_rolls_back_confirmation(self):
        preview = self.preview(); before = self.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("fixture rollback")), self.assertRaises(RuntimeError): self.confirm(preview)
        self.assertEqual(before, self.logical()); self.assertFalse(self.confirm(preview)["replayed"])

    def test_revoke_remains_available_during_active_or_expired_run(self):
        self.fx.paused_flag(False)
        self.assertFalse(self.state()["canReview"]); self.assertTrue(self.state()["canRevoke"])
        with patch("orchestrator.retention_controls.time.time", return_value=time.time()+7200):
            state = self.state(); self.assertIsNone(state["currentRun"]); self.assertTrue(state["canRevoke"])
            self.confirm(self.preview("revoke")); self.assertFalse(self.state()["canRevoke"])

    def test_attempt_count_survives_owner_policy_revision(self):
        self.fx.paused_flag(False); self.fx.save(); self.fx.paused_flag(True)
        self.confirm(self.preview())
        state = self.state(); self.assertEqual(state["policy"]["recordedAttempts"], 1)
        self.assertEqual([h["version"] for h in state["history"]], [2, 1])

    def test_corrupt_policy_disables_controls(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.pop("retentionPolicyHash"); self.ledger.put(db, "meta", 1, meta)
        state = self.state(); self.assertEqual(state["status"], "unavailable"); self.assertFalse(state["canReview"]); self.assertFalse(state["canRevoke"])

    def test_first_policy_is_explicit_opt_in_for_an_existing_run(self):
        # Construct the isolated no-policy setup, not a production reset/recovery path.
        with self.ledger.tx() as db:
            db.execute("DELETE FROM snapshots WHERE kind=?", (policy.POLICY,))
            meta = self.ledger.get(db, "meta", 1)
            meta.pop("retentionPolicyHash"); meta.pop("retentionPolicyRevoked")
            self.ledger.put(db, "meta", 1, meta)
        state = self.state(); self.assertEqual(state["status"], "not_delegated")
        self.assertTrue(state["canReview"]); self.assertFalse(state["canRevoke"])
        before = self.logical(); preview = self.preview(); self.assertEqual(before, self.logical())
        self.assertIsNone(preview["document"]["request"]["expectedPolicyHash"])
        self.confirm(preview); self.assertEqual(self.state()["policy"]["version"], 1)
        self.assertEqual(self.ledger.snapshot()["commands"], [])

    def test_oversize_history_is_unavailable_before_document_decoding(self):
        with self.ledger.tx() as db:
            db.execute("UPDATE snapshots SET data=? WHERE kind=?", ('x'*2_000_001, policy.POLICY))
        with patch.object(policy, "latest_in", side_effect=AssertionError("Bound before decode")):
            state = self.state()
        self.assertEqual(state["status"], "unavailable"); self.assertFalse(state["canReview"]); self.assertFalse(state["canRevoke"])

    def test_closed_preview_shapes_and_limits(self):
        base = self.request(); before = self.logical()
        for change in ({"operation": "archive"}, {"extra": True}, {"maxArchives": 99}, {"minimumRetentionSeconds": -1},
                       {"minimumRetentionSeconds": True}, {"runHash": "a"*64}, {"expectedPolicyHash": None}, {"contextHash": "b"*64}):
            with self.subTest(change=change), self.assertRaises(Refusal): self.api.preview(self.ledger, base | change, self.session)
        self.assertEqual(before, self.logical())

    def test_summary_omits_bindings_rationale_and_paths_and_labels_stale(self):
        report = self.state(); value = controls.summary(report, report["workspaceRevision"]+1)
        value["secret"] = "SECRET"; value["policy"]["runHash"] = "SECRET"
        summary = controls.assistant_summary(value)
        self.assertTrue(summary["historical"]); self.assertTrue(summary["workspaceChanged"])
        self.assertNotIn("SECRET", canonical(summary)); self.assertNotIn(str(self.ledger.root), canonical(summary))
        self.assertNotIn(report["policy"]["policyHash"], canonical(summary))
        with patch("orchestrator.retention_controls.time.time", return_value=report["inspectedAt"]+61): self.assertTrue(controls.summary(report, 0)["expired"])

    def test_duplicate_and_nonfinite_json_refuse(self):
        for raw in ('{"confirmed":false,"confirmed":true}', '{"value":NaN}', '{"nested":{"x":1,"x":2}}'):
            with self.assertRaises(Refusal): controls.decode(raw)
        self.assertEqual(controls.decode('{"value":1}'), {"value": 1})
