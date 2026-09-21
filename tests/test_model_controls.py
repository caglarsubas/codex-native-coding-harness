import contextlib
import copy
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import model_controls as controls, model_policy as models, missions, run_authority as runs
from orchestrator.core import Refusal, canonical
from orchestrator.workspaces import fingerprint
import test_model_policy
import test_missions
import test_task_contracts


class ModelControlsTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_task_contracts.TaskContractTest(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.ledger, self.registry, self.token = self.fx.ledger, self.fx.registry, self.fx.token
        self.cap = test_model_policy.capability(self.ledger, self.token)
        self.api = controls.ModelControls(); self.session = "model-owner-fixture"

    def state(self): return controls.inspect(self.ledger)
    def logical(self):
        with contextlib.closing(self.ledger.connect()) as db: return fingerprint(db)
    def request(self, operation="review", **changes):
        r = self.state(); fields = test_model_policy.policy_request(self.ledger, self.cap)
        return {"operation": operation, "expectedRevision": r["workspaceRevision"], "contextHash": r["contextHash"],
            **({k: fields[k] for k in controls.CHOICES} if operation == "review" else
               {"policyHash": r["policy"]["policyHash"], "reason": "Owner withdraws fixture policy"}), **changes}
    def preview(self, operation="review", **changes): return self.api.preview(self.ledger, self.request(operation, **changes), self.session)
    def confirm(self, p, **changes): return self.api.confirm(self.ledger, {"proposal": p, "confirmed": True, **changes}, self.session)

    def test_inspect_preview_and_cached_summary_are_read_only(self):
        before = self.logical()
        with patch("subprocess.Popen", side_effect=AssertionError("No native or provider call")):
            r = self.state(); self.preview(); controls.summary(r, r["workspaceRevision"])
        self.assertTrue(r["canReview"], r["reviewBlocker"]); self.assertEqual(r["capabilityStatus"], "fresh_recorded")
        self.assertEqual(before, self.logical()); self.assertFalse(r["executionAuthorized"])

    def test_review_revoke_and_historical_retry_never_restore_permission(self):
        p = self.preview(); before = self.ledger.snapshot(); saved = self.confirm(p)
        self.assertFalse(saved["nativeCallMade"]); self.assertFalse(saved["executionAuthorized"])
        after = self.ledger.snapshot()
        for name in ("workers", "queue", "commands"): self.assertEqual(before[name], after[name])
        revoke = self.preview("revoke"); self.confirm(revoke); fingerprint_before = self.logical()
        with patch("orchestrator.model_controls.time.time", return_value=time.time()+301):
            self.assertTrue(self.confirm(p)["replayed"]); self.assertTrue(self.confirm(revoke)["replayed"])
        self.assertEqual(fingerprint_before, self.logical()); self.assertTrue(self.state()["policy"]["revoked"])

    def test_review_fences_existing_run_without_start_stop_or_counter_reset(self):
        m = missions.read(self.ledger)
        runs.authorize(self.ledger, test_model_policy.request(self.ledger, missionHash=m["documentHash"], reviewReceiptHash=m["receiptHash"],
            checkpointHash=None, expiresAt=time.time()+3600, settingsPolicy="native_defaults", confirmed=True), actor="dashboard_owner")
        before = self.ledger.snapshot(); self.confirm(self.preview()); after = self.ledger.snapshot()
        self.assertEqual(runs.read(self.ledger)["state"]["status"], "fenced")
        for name in ("queue", "workers", "commands"): self.assertEqual(before[name], after[name])
        for name in ("paused", "brainControl", "heartbeat", "runner"): self.assertEqual(before["meta"].get(name), after["meta"].get(name))

    def test_invalid_choices_refuse_before_any_write(self):
        request = self.request(); before = self.logical()
        bad = [{"maxEscalations": 3}, {"maxEscalations": True}, {"qualityFloors": {"routine":4,"standard":1,"complex":3,"critical":4}},
               {"profiles": []}, {"actor": "dashboard_owner"}, {"capabilityHash": "a"*64}, {"operation": "activate"}]
        for settings in ({"model": "not-observed", "effort": "high", "speed": None},
                         {"model": "fixture-reasoner", "effort": "ultra", "speed": None},
                         {"model": "fixture-reasoner", "effort": "high", "speed": "fast"}):
            profiles = copy.deepcopy(request["profiles"]); profiles[1]["settings"] = settings; bad.append({"profiles": profiles})
        for change in bad:
            with self.subTest(change=change), self.assertRaises(Refusal): self.api.preview(self.ledger, request | change, self.session)
        self.assertEqual(before, self.logical())

    def test_missing_stale_capability_blocks_review_but_not_intact_revocation(self):
        self.confirm(self.preview())
        with patch("orchestrator.model_controls.time.time", return_value=time.time()+301):
            r = self.state(); self.assertFalse(r["canReview"]); self.assertTrue(r["canRevoke"])
            self.assertEqual(r["capabilityStatus"], "stale"); self.confirm(self.preview("revoke"))
        self.assertTrue(self.state()["policy"]["revoked"])

    def test_corrupt_capability_does_not_prevent_revocation(self):
        self.confirm(self.preview())
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (self.cap["capabilityHash"],))
        r = self.state(); self.assertFalse(r["canReview"]); self.assertEqual(r["capabilityStatus"], "unavailable")
        self.assertTrue(r["canRevoke"]); self.confirm(self.preview("revoke"))

    def test_pointer_history_and_missing_revocation_marker_fail_closed(self):
        first = self.confirm(self.preview())["receipt"]["policyHash"]; self.confirm(self.preview())
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["modelPolicyHash"] = first; self.ledger.put(db, "meta", 1, meta)
        self.assertEqual(self.state()["status"], "unavailable")
        with self.assertRaises(Refusal): self.preview()

    def test_history_bounds_checked_before_document_reads(self):
        with self.ledger.tx() as db:
            for i in range(129): db.execute("INSERT INTO snapshots VALUES(?,?,?)", (str(i), "model_policy", "{}"))
        with patch.object(models, "policy_in", side_effect=AssertionError("Bound first")):
            self.assertEqual(self.state()["status"], "unavailable")

    def test_missing_revocation_marker_does_not_look_like_new_setup(self):
        self.confirm(self.preview())
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); del meta["modelPolicyRevoked"]; self.ledger.put(db, "meta", 1, meta)
        self.assertEqual(self.state()["status"], "unavailable"); self.assertFalse(self.state()["canRevoke"])

    def test_session_signature_identity_restart_and_confirmation_are_bound(self):
        p = self.preview(); changed = copy.deepcopy(p); changed["document"]["request"]["maxEscalations"] = 2
        with self.assertRaises(Refusal): self.confirm(changed)
        for fields in ({"confirmed": False}, {"confirmed": 1}, {"execute": True}):
            with self.assertRaises(Refusal): self.confirm(p, **fields)
        body = {"proposal": p, "confirmed": True}
        with self.assertRaises(Refusal): self.api.confirm(self.ledger, body, "other-session")
        with self.assertRaises(Refusal): controls.ModelControls().confirm(self.ledger, body, self.session)
        with patch.object(controls, "identity", return_value="other-inode"), self.assertRaises(Refusal): self.confirm(p)

    def test_expiry_pause_catalog_and_mission_changes_refuse_stale_previews(self):
        p = self.preview()
        with patch("orchestrator.model_controls.time.time", return_value=time.time()+301), self.assertRaisesRegex(Refusal, "expired"):
            self.confirm(p)
        self.cap = test_model_policy.capability(self.ledger, self.token)
        with self.assertRaises(Refusal): self.confirm(p)
        p = self.preview(); m = missions.read(self.ledger); spec = copy.deepcopy(m["document"]["spec"]); spec["goal"] = "Changed mission"
        missions.change(self.ledger, test_missions.request(revision=m["revision"], spec=spec))
        with self.assertRaises(Refusal): self.confirm(p)
        self.assertFalse(self.state()["canReview"])

    def test_unpaused_setup_and_unversioned_drift_refuse(self):
        p = self.preview()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["paused"] = False; self.ledger.put(db, "meta", 1, meta)
        self.assertFalse(self.state()["canReview"])
        with self.assertRaises(Refusal): self.confirm(p)

    def test_concurrent_confirm_and_event_rollback_are_atomic(self):
        p = self.preview(); before = self.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("rollback")), self.assertRaises(RuntimeError): self.confirm(p)
        self.assertEqual(before, self.logical())
        with ThreadPoolExecutor(2) as pool: saved = list(pool.map(lambda _: self.confirm(p), range(2)))
        self.assertEqual(sum(not r["replayed"] for r in saved), 1); self.assertEqual(len(self.state()["history"]), 1)

    def test_review_revoke_race_has_one_winner(self):
        self.confirm(self.preview()); a, b = self.preview(), self.preview("revoke")
        def confirm(p):
            try: return self.confirm(p)
            except Refusal: return None
        with ThreadPoolExecutor(2) as pool: result = list(pool.map(confirm, (a,b)))
        self.assertEqual(sum(r is not None for r in result), 1)

    def test_cached_summary_is_closed_historical_and_not_current_settings(self):
        self.confirm(self.preview()); r = self.state(); result = controls.summary(r, r["workspaceRevision"]+1)
        self.assertTrue(result["workspaceChanged"]); self.assertEqual(result["recordedProfiles"], 2)
        for private in ("fixture-reasoner", "policyHash", "missionHash", "reason"): self.assertNotIn(private, canonical(result))
        with patch("orchestrator.model_controls.time.time", return_value=time.time()+61): self.assertTrue(controls.summary(r, 0)["expired"])

    def test_borrowed_transaction_must_be_active(self):
        req = self.preview()["document"]["request"]
        with contextlib.closing(self.ledger.connect()) as db:
            with self.assertRaisesRegex(Refusal, "transaction"): models.review(self.ledger, req, actor="dashboard_owner", _db=db)


if __name__ == "__main__": unittest.main()
