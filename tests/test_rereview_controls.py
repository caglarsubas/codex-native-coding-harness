import contextlib
import copy
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import rereview_controls as controls, result_reauthorization as authority
from orchestrator.core import Refusal, canonical
from orchestrator.workspaces import fingerprint
import test_result_reauthorization


class RereviewControlsTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_result_reauthorization.GenerationResultReviewTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.ledger, self.wid, self.store = self.fx.ledger, self.fx.wid, self.fx.store
        self.registry = self.fx.runfx.fx.registry
        self.original = self.fx.fx.evidence("changes_required"); self.fx.fx.review(self.original)
        self.fx.next_generation(); self.api = controls.RereviewControls(); self.session = "owner-fixture"

    def state(self): return controls.inspect(self.ledger, self.wid)
    def logical(self):
        with contextlib.closing(self.ledger.connect()) as db: return fingerprint(db)
    def request(self, operation="authorize", **changes):
        report = self.state()
        return {"operation": operation, "workerId": self.wid, "expectedRevision": report["workspaceRevision"],
            "contextHash": report["contextHash"], "reason": "Review unchanged fixture bytes",
            **({"commit": "f"*40} if operation == "authorize" else {"authorityHash": report["authority"]["authorityHash"]}), **changes}
    def preview(self, operation="authorize", **changes): return self.api.preview(self.ledger, self.request(operation, **changes), self.session)
    def confirm(self, p, **changes): return self.api.confirm(self.ledger, {"proposal": p, "confirmed": True, **changes}, self.session)

    def test_inspection_preview_and_render_metadata_never_collect_or_mutate(self):
        before, shared = self.logical(), self.store.snapshot()
        with patch("subprocess.Popen", side_effect=AssertionError("No collection")):
            report = self.state(); self.preview()
        self.assertTrue(report["canAuthorize"], report["blocker"]); self.assertEqual(report["task"]["commit"], "f"*40)
        self.assertEqual(len(report["reviews"]), 1); self.assertEqual(report["candidate"]["generation"], 2)
        self.assertEqual(before, self.logical()); self.assertEqual(shared, self.store.snapshot())

    def test_authorization_is_not_acceptance_or_native_resume(self):
        before, shared = self.ledger.snapshot(), self.store.snapshot(); receipt = self.confirm(self.preview())
        self.assertFalse(receipt["nativeCallMade"]); self.assertFalse(receipt["executionAuthorized"])
        self.assertEqual(self.fx.fx.worker()["status"], "settled")
        after = self.ledger.snapshot()
        for name in ("queue", "commands"): self.assertEqual(before[name], after[name])
        for key in ("paused", "runAuthority", "brainControl", "runner", "heartbeat"): self.assertEqual(before["meta"][key], after["meta"][key])
        self.assertEqual(shared, self.store.snapshot())
        result = self.fx.review(receipt["receipt"])
        self.assertTrue(result["packetAccepted"]); report = self.state()
        self.assertFalse(report["canAuthorize"]); self.assertTrue(report["authority"]["consumed"])
        self.assertEqual(len(report["reviews"]), 2)

    def test_unreviewed_result_needs_owner_supplied_nonbase_full_commit(self):
        fx = test_result_reauthorization.GenerationResultReviewTest(); fx.setUp(); self.addCleanup(fx.doCleanups)
        fx.next_generation(); report = controls.inspect(fx.ledger, fx.wid)
        self.assertTrue(report["canAuthorize"], report["blocker"])
        self.assertIsNone(report["task"]["commit"]); self.assertEqual(report["reviews"], [])
        request = {"operation": "authorize", "workerId": fx.wid, "expectedRevision": report["workspaceRevision"],
            "contextHash": report["contextHash"], "reason": "First review of settled fixture", "commit": report["task"]["baseSHA"]}
        with self.assertRaises(Refusal): self.api.preview(fx.ledger, request, self.session)
        p = self.api.preview(fx.ledger, request | {"commit": "e"*40}, self.session)
        self.assertIsNone(p["document"]["request"]["previousReviewHash"])
        receipt = self.api.confirm(fx.ledger, {"proposal": p, "confirmed": True}, self.session)
        self.assertFalse(receipt["executionAuthorized"]); self.assertEqual(fx.fx.worker()["status"], "settled")

    def test_later_run_and_narrowed_scope_never_inherit_preview_authority(self):
        p = self.preview(); report = self.state()
        scope = copy.deepcopy(report["candidate"]["scope"]); scope[0]["allowedPaths"] = ["unrelated/**"]
        self.fx.next_generation(scope)
        with self.assertRaises(Refusal): self.confirm(p)
        self.assertFalse(self.state()["canAuthorize"])
        with self.assertRaises(Refusal): self.preview()

    def test_revocation_and_expired_historical_replay_cannot_rearm(self):
        p = self.preview(); self.confirm(p); revoke = self.preview("revoke"); saved = self.confirm(revoke)
        before = self.logical()
        with patch("orchestrator.rereview_controls.time.time", return_value=time.time()+301):
            self.assertTrue(self.confirm(p)["replayed"]); self.assertEqual(self.confirm(revoke)["receipt"], saved["receipt"])
        self.assertEqual(before, self.logical()); self.assertEqual(self.state()["authority"]["status"], "revoked")

    def test_revocation_survives_pause_and_bad_result_proof(self):
        self.confirm(self.preview()); self.fx.runfx.fx.command("pause")
        with self.ledger.tx() as db: db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"bad", self.original["reviewArtifactId"]))
        report = self.state(); self.assertFalse(report["canAuthorize"]); self.assertTrue(report["canRevoke"])
        self.confirm(self.preview("revoke")); self.assertEqual(self.state()["authority"]["status"], "revoked")

    def test_corrupt_permission_blocks_all_controls(self):
        receipt = self.confirm(self.preview())["receipt"]; doc = self.ledger.document(receipt["authorityHash"])
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (doc["requestKey"],))
        report = self.state(); self.assertEqual(report["status"], "unavailable"); self.assertFalse(report["canRevoke"])

    def test_signature_session_identity_restart_and_foreign_task_refuse(self):
        p = self.preview(); changed = copy.deepcopy(p); changed["document"]["request"]["commit"] = "e"*40
        for value in (changed,):
            with self.assertRaises(Refusal): self.confirm(value)
        body = {"proposal": p, "confirmed": True}
        with self.assertRaises(Refusal): self.api.confirm(self.ledger, body, "another-session")
        with self.assertRaises(Refusal): controls.RereviewControls().confirm(self.ledger, body, self.session)
        with patch.object(controls, "identity", return_value="other-inode"), self.assertRaises(Refusal): self.confirm(p)
        self.assertEqual(controls.inspect(self.ledger, "foreign-worker")["status"], "unavailable")
        with self.assertRaises(Refusal): self.preview(workerId="foreign-worker")

    def test_explicit_closed_fields_and_exact_unchanged_commit(self):
        p = self.preview(); before = self.logical()
        for fields in ({"confirmed": False}, {"confirmed": 1}, {"execute": True}):
            with self.assertRaises(Refusal): self.confirm(p, **fields)
        for fields in ({"commit": "e"*40}, {"commit": "main"}, {"reason": ""}, {"operation": "play"},
                       {"runHash": "a"*64}, {"contextHash": "a"*64}, {"expectedRevision": 0}):
            with self.assertRaises(Refusal): self.api.preview(self.ledger, self.request() | fields, self.session)
        self.assertEqual(before, self.logical())

    def test_pause_run_supersession_and_expiry_block_new_confirmation(self):
        p = self.preview()
        with patch("orchestrator.rereview_controls.time.time", return_value=time.time()+301), self.assertRaisesRegex(Refusal, "expired"):
            self.confirm(p)
        self.fx.runfx.fx.command("pause")
        with self.assertRaises(Refusal): self.confirm(p)
        self.assertFalse(self.state()["canAuthorize"])

    def test_source_change_without_revision_fails_context_binding(self):
        p = self.preview()
        with self.ledger.tx() as db:
            q = self.ledger.all(db, "queue")[0]; q["reason"] = "Owner hold"; self.ledger.put(db, "queue", q["id"], q)
        with self.assertRaises(Refusal): self.confirm(p)

    def test_concurrent_confirm_and_rollback_are_atomic(self):
        p = self.preview(); before = self.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("rollback")), self.assertRaises(RuntimeError): self.confirm(p)
        self.assertEqual(before, self.logical())
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(lambda _: self.confirm(p), range(2)))
        self.assertEqual(sum(not r["replayed"] for r in results), 1); self.assertEqual(len(self.state()["permissions"]), 1)

    def test_revocation_and_new_permission_have_one_winner(self):
        self.confirm(self.preview()); revoke, grant = self.preview("revoke"), self.preview()
        def confirm(p):
            try: return self.confirm(p)
            except Refusal: return None
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(confirm, (revoke, grant)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_missing_history_and_bounds_never_hide_as_empty(self):
        self.confirm(self.preview())
        with self.ledger.tx() as db: db.execute("UPDATE snapshots SET data=? WHERE kind=?", ('x'*2_000_001, authority.KIND))
        with patch.object(authority, "record_in", side_effect=AssertionError("Bound first")):
            self.assertEqual(self.state()["status"], "unavailable")

    def test_summary_omits_ids_reasons_proofs_and_marks_staleness(self):
        self.confirm(self.preview()); r = self.state(); out = controls.summary(r, r["workspaceRevision"]+1)
        self.assertTrue(out["workspaceChanged"]); self.assertNotIn(self.wid, canonical(out))
        self.assertNotIn("Review unchanged", canonical(out)); self.assertNotIn("commit", canonical(out))
        with patch("orchestrator.rereview_controls.time.time", return_value=time.time()+61):
            self.assertTrue(controls.summary(r, 0)["expired"])

    def test_supplied_transaction_must_be_active(self):
        request = self.preview()["document"]["request"]
        with contextlib.closing(self.ledger.connect()) as db:
            with self.assertRaisesRegex(Refusal, "transaction"): authority.authorize(self.ledger, request, actor="dashboard_owner", _db=db)


if __name__ == "__main__": unittest.main()
