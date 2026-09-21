"""Later-generation review of the same bytes; no native calls or live state."""
import copy
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from orchestrator import brain_control, missions, result_reauthorization as auth, workspace_pause
from orchestrator.core import Refusal, digest
from orchestrator.observations import capture
import test_missions
import test_result_review
import test_result_handoff


class GenerationFixture:
    def setup_review(self):
        self.fx = test_result_review.ResultReviewTest(); self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.bind()

    def bind(self):
        self.ledger, self.token, self.wid = self.fx.ledger, self.fx.token, self.fx.wid
        self.store, self.intent = self.fx.store, self.fx.intent
        self.runfx = self.fx.fx.fx.fx.fx
        self.dispatch = self.fx.fx.fx.fx

    def next_generation(self, scope=None):
        stop = self.runfx.stop({"runHash": self.runfx.state()["runHash"]})
        self.ledger.process(self.token)
        worker = self.fx.worker()
        with self.ledger.tx() as db:
            artifact = capture(db, "generation-stop-"+str(time.time()), b"Synthetic safe checkpoint.", {
                "repository": "a", "name": "checkpoint.md", "orderAt": time.time(),
                "references": [{"session": "brain-a", "at": time.time()}, {"session": worker["threadId"], "at": time.time()}]})
        observed = time.time()
        proof = workspace_pause.observe(self.ledger, self.token, stop["commandId"], {
            "workspaceId": "a", "commandId": stop["commandId"], "observedAt": observed, "evidenceHash": "a"*64,
            "complete": True, "includesDescendants": True, "brain": {"hostId": "local", "threadId": "brain-a"},
            "tasks": [{"hostId": worker["hostId"], "threadId": worker["threadId"], "workerId": self.wid,
                       "parent": None, "status": "idle", "observedAt": observed, "checkpointArtifactId": artifact["id"]}]})
        checkpoint = brain_control.park(self.ledger, self.token, stop["commandId"], {
            "summary": "Fixture safe checkpoint", "artifactIds": [artifact["id"]], "pauseEvidenceHash": proof["documentHash"]})
        current = missions.read(self.ledger); spec = copy.deepcopy(current["document"]["spec"])
        spec["phase"]["id"] = "phase-"+str(self.runfx.state()["generation"]+1)
        if scope is not None: spec["phase"]["scope"] = scope
        saved = missions.change(self.ledger, test_missions.request(revision=current["revision"], spec=spec))["current"]
        missions.change(self.ledger, test_missions.request("review", saved["revision"], documentHash=saved["documentHash"], confirmed=True))
        self.run = self.runfx.authorize(self.runfx.release_request(checkpoint["documentHash"]))
        self.runfx.fx.command("brain_resume"); self.ledger.process(self.token)
        # Deliberate isolated activation, matching the dispatch fixture. No public Play route.
        self.dispatch.meta(paused=False)
        return self.run

    def request(self, **changes):
        return self.runfx.request(runHash=self.run["runHash"], workerId=self.wid, intentHash=digest(self.intent),
            settlementHash=self.fx.worker()["ownershipSettlementHash"], previousReviewHash=self.fx.worker().get("resultReviewHash"),
            commit="f"*40, reason="Reconsider unchanged result bytes under the reviewed next phase", confirmed=True) | changes

    def authorize(self, request=None):
        return auth.authorize(self.ledger, request or self.request(), actor="dashboard_owner")

    def revoke(self, receipt):
        return auth.revoke(self.ledger, self.runfx.request(workerId=self.wid, authorityHash=receipt["authorityHash"],
            reason="Owner withdrew review-only scope", confirmed=True), actor="dashboard_owner")

    def review(self, receipt, outcome="accepted"):
        return self.fx.review(self.fx.evidence(outcome) | {"reviewAuthorityHash": receipt["authorityHash"]})


class GenerationResultReviewTest(GenerationFixture, unittest.TestCase):
    def setUp(self): self.setup_review()

    def test_initial_review_in_later_generation_needs_explicit_owner_permission(self):
        self.next_generation(); before = self.store.snapshot()
        with self.assertRaises(Refusal): self.fx.review()
        permission = self.authorize(); result = self.review(permission)
        self.assertTrue(result["packetAccepted"])
        self.assertEqual(before, self.store.snapshot())
        record = self.ledger.document(result["reviewHash"])
        self.assertEqual(record["schemaVersion"], 2); self.assertIsNone(record["previousReviewHash"])

    def test_new_version_retains_old_result_replay_and_settlement_recovery(self):
        original = self.fx.evidence("changes_required"); first = self.fx.review(original)
        self.next_generation(); before = self.store.snapshot()
        permission = self.authorize(); result = self.review(permission)
        current = self.fx.worker()
        self.assertEqual(self.ledger.document(result["reviewHash"])["previousReviewHash"], first["reviewHash"])
        self.assertEqual(self.fx.review(original), first)
        self.fx.api.settlement.recover(self.token, self.wid)
        self.assertEqual(current, self.fx.worker()); self.assertEqual(before, self.store.snapshot())
        self.next_generation()  # Later phase reports validate the complete result history.
        self.assertEqual(self.fx.api.read(self.token, self.wid), result)

    def test_changed_commit_and_accepted_results_cannot_be_reopened(self):
        self.fx.review(self.fx.evidence("changes_required")); self.next_generation()
        with self.assertRaisesRegex(Refusal, "Changed source"): self.authorize(self.request(commit="e"*40))
        self.review(self.authorize())
        with self.assertRaises(Refusal): self.authorize()

    def test_same_generation_authority_refuses(self):
        self.run = {"runHash": self.intent["runHash"]}
        with self.assertRaisesRegex(Refusal, "later"): self.authorize()

    def test_narrowed_mission_cannot_reapprove_old_scope(self):
        scope = copy.deepcopy(missions.read(self.ledger)["document"]["spec"]["phase"]["scope"])
        scope[0]["allowedPaths"] = ["unrelated/**"]
        self.next_generation(scope)
        with self.assertRaises(Refusal): self.authorize()

    def test_revocation_consumption_and_historical_authorize_replay(self):
        self.next_generation(); request = self.request(); permission = self.authorize(request)
        self.revoke(permission); before = self.fx.logical()
        self.assertEqual(self.authorize(request), permission); self.assertEqual(before, self.fx.logical())
        with self.assertRaises(Refusal): self.review(permission)
        current = self.authorize(); self.review(current, "changes_required")
        with self.assertRaises(Refusal): self.review(current)
        self.review(self.authorize())

    def test_pause_expiry_and_maintenance_fence_consumption(self):
        self.next_generation(); permission = self.authorize(); request = self.fx.evidence() | {"reviewAuthorityHash": permission["authorityHash"]}
        expiry = self.ledger.document(permission["authorityHash"])["expiresAt"]
        with patch("orchestrator.result_reauthorization.time.time", return_value=expiry+1):
            with self.assertRaises(Refusal): self.fx.review(request)
        fence = self.ledger.root / "admission-fence.json"; fence.touch(mode=0o600)
        with self.assertRaises(Refusal): self.fx.review(request)
        fence.unlink()
        self.runfx.fx.command("pause")
        with self.assertRaises(Refusal): self.review(permission)

    def test_newer_generation_does_not_inherit_unconsumed_permission(self):
        self.next_generation(); permission = self.authorize(); self.next_generation()
        with self.assertRaises(Refusal): self.review(permission)
        self.review(self.authorize())

    def test_authority_hash_required_and_exact(self):
        self.next_generation(); permission = self.authorize()
        for field in ({}, {"reviewAuthorityHash": "a"*64}):
            with self.assertRaises(Refusal): self.fx.review(self.fx.evidence() | field)
        self.review(permission)

    def test_wrong_commit_refused_at_review(self):
        self.next_generation(); permission = self.authorize(self.request(commit="e"*40))
        with self.assertRaisesRegex(Refusal, "commit"): self.review(permission)

    def test_independent_review_must_follow_permission(self):
        self.next_generation(); request = self.fx.evidence(); permission = self.authorize()
        request.update(expectedRevision=self.ledger.snapshot()["meta"]["revision"], reviewAuthorityHash=permission["authorityHash"])
        with self.assertRaisesRegex(Refusal, "follow new owner"): self.fx.review(request)

    def test_later_revocation_does_not_undo_consumed_result(self):
        self.next_generation(); permission = self.authorize(); result = self.review(permission)
        self.revoke(permission); before = self.fx.logical()
        self.assertEqual(self.fx.api.read(self.token, self.wid), result)
        self.assertEqual(before, self.fx.logical())

    def test_review_failure_rolls_back_and_concurrent_consumers_have_one_outcome(self):
        self.next_generation(); permission = self.authorize()
        one = self.fx.evidence() | {"reviewAuthorityHash": permission["authorityHash"]}
        two = self.fx.evidence() | {"reviewAuthorityHash": permission["authorityHash"]}
        before = self.fx.logical(); shared = self.store.snapshot()
        with patch.object(self.fx.api.ledger, "event", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.fx.review(one)
        self.assertEqual(before, self.fx.logical()); self.assertEqual(shared, self.store.snapshot())
        def call(request):
            try: return self.fx.review(request)
            except Refusal: return None
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(call, (one, two)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(shared, self.store.snapshot())

    def test_authority_identity_and_revision_fields_fail_closed(self):
        self.next_generation(); before = self.fx.logical()
        for fields in ({"intentHash": "a"*64}, {"settlementHash": "a"*64}, {"previousReviewHash": "a"*64},
                       {"workerId": "missing"}, {"confirmed": False}, {"reason": ""}, {"unexpected": True}, {"expectedRevision": 0}):
            with self.subTest(fields=fields), self.assertRaises(Refusal): self.authorize(self.request(**fields))
        with self.assertRaises(Refusal): auth.authorize(self.ledger, self.request(), actor="designated_brain")
        self.assertEqual(before, self.fx.logical())

    def test_pointer_rollback_and_deleted_receipt_fail_closed(self):
        self.next_generation(); permission = self.authorize(); self.revoke(permission)
        with self.ledger.tx() as db:
            worker = self.ledger.get(db, "workers", self.wid)
            worker["resultReviewAuthorityHash"] = permission["authorityHash"]; self.ledger.put(db, "workers", self.wid, worker)
        with self.assertRaisesRegex(Refusal, "pointer"): self.review(permission)
        with self.ledger.tx() as db:
            record = self.ledger.document(permission["authorityHash"])
            db.execute("DELETE FROM snapshots WHERE id=?", (record["requestKey"],))
        with self.assertRaisesRegex(Refusal, "receipt missing"): self.authorize()

    def test_old_evidence_corruption_invalidates_new_version(self):
        original = self.fx.evidence("changes_required"); self.fx.review(original)
        self.next_generation(); self.review(self.authorize())
        with self.ledger.tx() as db:
            db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"changed", original["reviewArtifactId"]))
        with self.assertRaises(Refusal): self.fx.api.read(self.token, self.wid)
        with self.assertRaises(Refusal): self.fx.api.settlement.recover(self.token, self.wid)

    def test_history_cannot_be_projected_onto_a_different_worker(self):
        self.next_generation(); self.review(self.authorize())
        from orchestrator.result_review import reviewed_worker_in
        from orchestrator.ownership_settlement import OwnershipSettlement
        worker = self.fx.worker() | {"id": "other-worker"}
        terminal = self.ledger.document(worker["ownershipSettlementHash"])
        with self.ledger.tx() as db:
            with self.assertRaisesRegex(Refusal, "worker identity"):
                reviewed_worker_in(db, worker, OwnershipSettlement.settled_claim(terminal), terminal)

    def test_authorization_rolls_back_and_concurrent_requests_have_one_winner(self):
        self.next_generation(); before = self.fx.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.authorize()
        self.assertEqual(before, self.fx.logical())
        def call(request):
            try: return self.authorize(request)
            except Refusal: return None
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(call, (self.request(), self.request())))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_permission_never_reopens_native_or_reservation(self):
        self.next_generation(); self.authorize(); before = self.store.snapshot()
        with self.assertRaises(Refusal): self.dispatch.reserve()
        with self.assertRaises(Refusal): self.dispatch.begin(self.wid)
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(self.fx.worker()["dispatchAdmission"]["stage"], "settled")
        for file in ("server.py", "cli.py", "assistant_actions.py"):
            self.assertNotIn("result_reauthorization.authorize", (Path("orchestrator") / file).read_text())


class GenerationHandoffTest(GenerationFixture, unittest.TestCase):
    def setUp(self):
        self.handoff = test_result_handoff.ResultHandoffTest(); self.handoff.setUp()
        self.addCleanup(self.handoff.doCleanups)
        self.fx = self.handoff.fx; self.bind()

    def test_cli_collects_fresh_evidence_and_preserves_review_history(self):
        old = self.handoff.review_request("changes_required", cli=True); first = self.handoff.call("review", old, cli=True)
        self.next_generation(); shared = self.store.snapshot()
        permission = self.authorize(self.request(commit=self.handoff.result))
        request = self.handoff.review_request(cli=True) | {"reviewAuthorityHash": permission["authorityHash"]}
        second = self.handoff.call("review", request, cli=True)
        state = self.handoff.call("state", cli=True)
        self.assertEqual(state["reviewHistory"], [second, first]); self.assertTrue(state["reviewAuthority"]["consumed"])
        self.assertEqual(self.handoff.call("review", old, cli=True), first)
        self.assertEqual(shared, self.store.snapshot())

    def test_collectors_refuse_wrong_commit_and_recheck_revocation_after_io(self):
        self.next_generation(); permission = self.authorize(self.request(commit=self.handoff.result))
        for operation, fields in (("collect_source", {}), ("collect_github", {"prUrl": test_result_handoff.test_github_evidence.URL})):
            with self.assertRaises(Refusal): self.handoff.call(operation, self.handoff.request(commit="e"*40, **fields))
        from orchestrator import source_observation
        original = source_observation.inspect_source
        def revoke_after_observation(*args, **kwargs):
            result = original(*args, **kwargs); self.revoke(permission); return result
        with patch.object(source_observation, "inspect_source", side_effect=revoke_after_observation):
            with self.assertRaises(Refusal): self.handoff.call("collect_source", self.handoff.request())
        with self.assertRaises(Refusal): self.handoff.proof("preservation")


if __name__ == "__main__": unittest.main()
