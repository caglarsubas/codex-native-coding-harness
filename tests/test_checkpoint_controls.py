import contextlib
import copy
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import checkpoint_controls as controls, phase_checkpoints as phases, run_authority as runs
from orchestrator.core import Refusal, canonical
from orchestrator.workspaces import fingerprint
import test_phase_checkpoints


class CheckpointControlsTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_phase_checkpoints.PhaseCheckpointTest(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.ledger = self.fx.ledger; self.registry = self.fx.fx.fx.registry
        self.report = self.fx.prepare(); self.api = controls.CheckpointControls(); self.session = "fixture-session"

    def state(self): return controls.inspect(self.ledger)
    def logical(self):
        with contextlib.closing(self.ledger.connect()) as db: return fingerprint(db)
    def request(self, operation="review", **changes):
        state = self.state(); candidate = state["candidate"]
        body = {"operation": operation, "expectedRevision": state["workspaceRevision"], "contextHash": state["contextHash"]}
        if operation == "review":
            body.update({k: candidate[k] for k in ("reportHash", "artifactId", "missionHash", "reviewReceiptHash")},
                        settingsPolicy="native_defaults", expiresInSeconds=3600)
        else: body.update(checkpointReviewHash=state["reviews"][0]["checkpointReviewHash"], reason="Keep this phase parked")
        return body | changes
    def preview(self, operation="review", **changes): return self.api.preview(self.ledger, self.request(operation, **changes), self.session)
    def confirm(self, preview, **changes):
        return self.api.confirm(self.ledger, {"proposal": preview, "confirmed": True, **changes}, self.session)
    def authorize(self, proposal, receipt):
        return self.fx.fx.authorize(self.fx.authorize_request(proposal["document"]["request"], receipt["receipt"]))

    def test_inspection_and_preview_are_read_only(self):
        before = self.logical(); report = self.state(); self.preview()
        self.assertTrue(report["canReview"]); self.assertEqual(report["candidate"]["summary"]["measuredPhaseTokens"], None)
        self.assertFalse(report["executionAuthorized"]); self.assertEqual(before, self.logical())
        self.assertFalse((self.registry.root / "admission.sqlite3").exists())

    def test_review_is_not_run_authorization_or_resume(self):
        before = self.ledger.snapshot(); p = self.preview(); result = self.confirm(p)
        after = self.ledger.snapshot(); self.assertFalse(result["executionAuthorized"])
        for key in ("paused", "brainControl", "runAuthority", "runner", "heartbeat"):
            self.assertEqual(before["meta"][key], after["meta"][key])
        for key in ("queue", "workers", "commands"): self.assertEqual(before[key], after[key])
        next_run = self.authorize(p, result); self.assertEqual(next_run["generation"], 2)
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])

    def test_withdrawal_blocks_unused_review_and_replay_never_rearms(self):
        p = self.preview(); review = self.confirm(p); withdrawal = self.preview("withdraw")
        saved = self.confirm(withdrawal); before = self.logical()
        with patch("orchestrator.checkpoint_controls.time.time", return_value=time.time()+301):
            self.assertTrue(self.confirm(p)["replayed"]); self.assertEqual(self.confirm(withdrawal)["receipt"], saved["receipt"])
        self.assertEqual(before, self.logical()); self.assertTrue(self.state()["reviews"][0]["withdrawn"])
        with self.assertRaisesRegex(Refusal, "withdrawn"): self.authorize(p, review)

    def test_withdrawal_does_not_stop_already_authorized_run(self):
        p = self.preview(); review = self.confirm(p); next_run = self.authorize(p, review)
        before = self.ledger.snapshot()["meta"]["runAuthority"]
        self.assertFalse(self.state()["canReview"])
        self.confirm(self.preview("withdraw"))
        self.assertEqual(before, self.ledger.snapshot()["meta"]["runAuthority"])
        with contextlib.closing(self.ledger.connect()) as db:
            state = runs.current_in(self.ledger, db)
            self.assertEqual(state["runHash"], next_run["runHash"]); self.assertEqual(state["status"], "authorized_intent")

    def test_explicit_confirmation_and_closed_fields(self):
        p = self.preview(); before = self.logical()
        for change in ({"confirmed": False}, {"confirmed": 1}, {"cleanupAcknowledged": True}):
            with self.assertRaises(Refusal): self.confirm(p, **change)
        for change in ({"expiresInSeconds": 0}, {"expiresInSeconds": 86401}, {"expiresInSeconds": True},
                       {"settingsPolicy": "adaptive"}, {"reportHash": "f"*64}, {"operation": "play"}, {"extra": True}):
            with self.assertRaises(Refusal): self.api.preview(self.ledger, self.request() | change, self.session)
        self.assertEqual(before, self.logical())

    def test_session_tamper_restart_and_workspace_refuse(self):
        p = self.preview(); changed = copy.deepcopy(p); changed["document"]["request"]["expiresAt"] += 1
        with self.assertRaises(Refusal): self.confirm(changed)
        body = {"proposal": p, "confirmed": True}
        with self.assertRaises(Refusal): self.api.confirm(self.ledger, body, "another-session")
        with self.assertRaises(Refusal): controls.CheckpointControls().confirm(self.ledger, body, self.session)
        with patch.object(controls, "identity", return_value="replacement-inode"), self.assertRaises(Refusal): self.confirm(p)

    def test_expired_preview_and_changed_report_refuse(self):
        p = self.preview()
        with patch("orchestrator.checkpoint_controls.time.time", return_value=time.time()+301), self.assertRaisesRegex(Refusal, "expired"):
            self.confirm(p)
        self.fx.prepare()
        with self.assertRaises(Refusal): self.confirm(p)

    def test_source_change_without_revision_change_invalidates_preview(self):
        p = self.preview()
        with self.ledger.tx() as db:
            q = self.ledger.all(db, "queue")[0]; q["held"] = not q["held"]; self.ledger.put(db, "queue", q["id"], q)
        self.assertFalse(self.state()["canReview"])
        with self.assertRaises(Refusal): self.confirm(p)

    def test_concurrent_confirm_commits_once(self):
        p = self.preview()
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: self.confirm(p), range(2)))
        self.assertEqual(sum(not r["replayed"] for r in results), 1); self.assertEqual(len(self.state()["reviews"]), 1)

    def test_confirmation_event_failure_rolls_back(self):
        p = self.preview(); before = self.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("fixture rollback")), self.assertRaises(RuntimeError): self.confirm(p)
        self.assertEqual(before, self.logical()); self.confirm(p)
        p = self.preview("withdraw"); before = self.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("fixture rollback")), self.assertRaises(RuntimeError): self.confirm(p)
        self.assertEqual(before, self.logical())

    def test_withdrawal_owner_only_and_projection_tamper_fails_closed(self):
        p = self.preview(); review = self.confirm(p); w = self.preview("withdraw"); req = w["document"]["request"]
        with self.assertRaises(Refusal): phases.withdraw(self.ledger, req, actor="designated_brain")
        self.confirm(w)
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.pop("phaseReviewWithdrawals"); self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): self.authorize(p, review)
        self.assertEqual(self.state()["status"], "unavailable")

    def test_withdrawal_receipt_tamper_blocks_grant(self):
        p = self.preview(); review = self.confirm(p); w = self.confirm(self.preview("withdraw"))
        record = self.ledger.document(w["receipt"]["withdrawalHash"])
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (record["requestKey"],))
        with self.assertRaises(Refusal): self.authorize(p, review)
        self.assertEqual(self.state()["status"], "unavailable")

    def test_grant_and_withdrawal_same_revision_have_one_winner(self):
        p = self.preview(); review = self.confirm(p); w = self.preview("withdraw")
        grant_request = self.fx.authorize_request(p["document"]["request"], review["receipt"])
        def attempt(operation):
            try:
                if operation == "grant": self.fx.fx.authorize(grant_request)
                else: self.confirm(w)
                return operation
            except Refusal: return "refused"
        with ThreadPoolExecutor(max_workers=2) as pool: result = list(pool.map(attempt, ("grant", "withdraw")))
        self.assertEqual(result.count("refused"), 1)
        if "withdraw" in result:
            with self.assertRaisesRegex(Refusal, "withdrawn"): self.authorize(p, review)
        else:
            self.assertEqual(runs.read(self.ledger)["state"]["status"], "authorized_intent")

    def test_corrupt_report_blocks_review_but_not_withdrawal(self):
        self.confirm(self.preview())
        with self.ledger.tx() as db: db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"corrupt", self.report["artifactId"]))
        self.assertFalse(self.state()["canReview"]); self.confirm(self.preview("withdraw"))
        self.assertTrue(self.state()["reviews"][0]["withdrawn"])

    def test_corrupt_review_and_oversize_history_are_unavailable(self):
        self.confirm(self.preview())
        with self.ledger.tx() as db: db.execute("UPDATE snapshots SET data=? WHERE kind=?", ('x'*2_000_001, phases.REVIEW))
        with patch.object(phases, "owner_review_in", side_effect=AssertionError("Bound first")):
            self.assertEqual(self.state()["status"], "unavailable")

    def test_new_review_does_not_withdraw_other_exact_reviews(self):
        first = self.preview(); one = self.confirm(first); self.confirm(self.preview())
        self.confirm(self.preview("withdraw"))
        self.assertFalse(self.state()["reviews"][1]["withdrawn"])
        self.assertEqual(self.authorize(first, one)["generation"], 2)

    def test_cached_summary_never_exposes_private_bindings(self):
        self.confirm(self.preview()); state = self.state(); summary = controls.summary(state, state["workspaceRevision"]+1)
        self.assertTrue(summary["workspaceChanged"]); self.assertEqual(summary["recordedReviews"], 1)
        self.assertNotIn(state["reviews"][0]["checkpointReviewHash"], canonical(summary))
        self.assertNotIn(str(self.ledger.root), canonical(summary))
        with patch("orchestrator.checkpoint_controls.time.time", return_value=time.time()+61): self.assertTrue(controls.summary(state, 0)["expired"])

    def test_settings_choice_is_explicit_and_current_adaptive_policy_supported(self):
        import test_model_policy as model_fixture
        from orchestrator import model_policy
        cap = model_fixture.capability(self.ledger, self.fx.token)
        saved = model_policy.review(self.ledger, model_fixture.policy_request(self.ledger, cap), actor="dashboard_owner")
        # Existing parked checkpoint remains parked; there is no activation here.
        state = self.state(); self.assertTrue(state["canReview"])
        value = {"mode": "adaptive", "policyHash": saved["policyHash"]}
        self.assertIn(value, [s["value"] for s in state["candidate"]["settings"]])
        p = self.preview(settingsPolicy=value); self.confirm(p)
        self.assertEqual(self.state()["reviews"][0]["settingsPolicy"], value)
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
