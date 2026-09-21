"""Disposable terminal CLI fixtures; no native effects or host qualification."""
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

from orchestrator import terminal_handoff as terminal, run_authority as runs
from orchestrator.core import Refusal, canonical
import test_creation_recovery
import test_ownership_settlement


def cli(api, token, worker, operation, request=None, *, select=True, outcome=None):
    argv = [sys.executable, "-m", "orchestrator.cli"]
    if select: argv += ["--platform", str(api.bridge.registry.root), "--workspace", api.bridge.workspace_id]
    argv += ["terminal-handoff-"+operation, worker, "--outcome", outcome or api.outcome]
    if request is not None:
        path = api.ledger.root / "terminal-request.json"; path.write_text(canonical(request)); argv.append(str(path))
    return subprocess.run(argv, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
                          env={**os.environ, "ORCHESTRATOR_CONTROLLER_TOKEN": token})


def checked_cli(api, token, worker, operation, request=None):
    result = cli(api, token, worker, operation, request)
    if result.returncode: raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def proof_request(api, token, worker, thread_id, id="proof"):
    state = api.state(token, worker)
    return {"id": id, "expectedRevision": state["revision"], "expectedHash": state["expectedHash"],
            "threadId": thread_id, "observedAt": time.time(), "content": "Independent fixture handoff; not live evidence."}


def bind_proofs(api, token, worker, request, through_cli=False):
    request = copy.deepcopy(request)
    rows = request["inventory"]["tasks"] if api.outcome == "confirmed" else [{"threadId": None}]
    for index, row in enumerate(rows):
        proof = proof_request(api, token, worker, row["threadId"], request["id"]+"-proof-"+str(index))
        result = checked_cli(api, token, worker, "proof-add", proof) if through_cli else api.proof_add(token, worker, proof)
        if api.outcome == "confirmed": row.update(checkpointArtifactId=result["artifactId"], observedAt=time.time())
        else: request["reconciliationArtifactId"] = result["artifactId"]
    request["inventory"]["observedAt"] = time.time()
    for row in request["resources"]: row["observedAt"] = time.time()
    for row in request["usage"].get("sessions", []): row["observedAt"] = time.time()
    request["usage"]["observedAt"] = time.time()
    return request


def logical(api):
    with api.ledger.tx() as db:
        local = {r[0]: list(db.execute('SELECT * FROM "'+r[0]+'"')) for r in
                 db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}
        local = {k: [tuple(r) for r in v] for k, v in local.items()}
    return local, api.store.snapshot()


class TerminalHandoffTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_ownership_settlement.OwnershipSettlementTest(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.api = terminal.TerminalHandoff(self.fx.bridge, "confirmed")
        self.token, self.wid = self.fx.token, self.fx.wid

    def request(self, descendants=()): return bind_proofs(self.api, self.token, self.wid, self.fx.evidence(descendants))
    def settle(self, request): return self.api.settle(self.token, self.wid, request)

    def test_cli_round_trip_requires_all_proofs_and_leaves_acceptance_held(self):
        request = bind_proofs(self.api, self.token, self.wid, self.fx.evidence(("child",)), True)
        before = logical(self.api); state = checked_cli(self.api, self.token, self.wid, "state")
        self.assertEqual(before, logical(self.api)); self.assertIsNone(state["settlement"])
        result = checked_cli(self.api, self.token, self.wid, "settle", request)
        self.assertEqual(result["actualTokens"], 2000); self.assertFalse(result["packetAccepted"])
        self.assertTrue(self.api.state(self.token, self.wid)["receiptAttached"])
        self.assertTrue(self.fx.ledger.snapshot()["queue"][0]["held"])
        self.assertEqual(result, checked_cli(self.api, self.token, self.wid, "recover"))
        self.assertEqual(result, checked_cli(self.api, self.token, self.wid, "settle", request))

    def test_state_is_read_only_and_not_native_truth(self):
        before = logical(self.api); result = self.api.state(self.token, self.wid)
        self.assertEqual(before, logical(self.api)); self.assertFalse(result["nativeCallMade"])
        self.assertEqual(result["currentNativeActivity"], "not_observed")
        self.assertFalse(result["executionAuthorized"])

    def test_wrong_brain_workspace_outcome_or_missing_selection_refuses(self):
        for result in (cli(self.api, "wrong", self.wid, "state"), cli(self.api, self.token, "other", "state"),
                       cli(self.api, self.token, self.wid, "state", select=False),
                       cli(self.api, self.token, self.wid, "state", outcome="not_created")):
            self.assertNotEqual(result.returncode, 0)

    def test_proof_replay_is_exact_and_does_not_refresh_or_write(self):
        request = proof_request(self.api, self.token, self.wid, "worker-fixture")
        receipt = self.api.proof_add(self.token, self.wid, request); before = logical(self.api)
        self.assertEqual(receipt, self.api.proof_add(self.token, self.wid, request))
        self.assertEqual(before, logical(self.api))
        with self.assertRaises(Refusal): self.api.proof_add(self.token, self.wid, request | {"content": "Changed"})

    def test_concurrent_proof_replay_retains_one_artifact(self):
        request = proof_request(self.api, self.token, self.wid, "worker-fixture")
        with ThreadPoolExecutor(2) as pool:
            receipts = list(pool.map(lambda _: self.api.proof_add(self.token, self.wid, request), range(2)))
        self.assertEqual(receipts[0], receipts[1])
        with self.fx.ledger.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (terminal.KIND,)).fetchone()[0], 1)

    def test_unbound_artifact_and_wrong_task_proofs_cannot_release(self):
        with self.assertRaises(Refusal): self.settle(self.fx.evidence())
        request = self.request(("child",)); request["inventory"]["tasks"][0]["checkpointArtifactId"] = request["inventory"]["tasks"][1]["checkpointArtifactId"]
        with self.assertRaises(Refusal): self.settle(request)
        self.assertEqual(self.fx.claim()["status"], "running")

    def test_partial_cleanup_counters_and_remote_descendant_refuse(self):
        original = self.request()
        changes = [("inventory", "complete", False), ("inventory", "includesDescendants", False),
                   ("inventory", "pendingResolved", False), ("inventory", "effectsComplete", False), ("usage", "complete", False)]
        for group, key, value in changes:
            request = copy.deepcopy(original); request[group][key] = value
            with self.subTest(group=group, key=key), self.assertRaises(Refusal): self.settle(request)
        request = copy.deepcopy(original); request["resources"][0]["cleanupObserved"] = False
        with self.assertRaises(Refusal): self.settle(request)
        request = copy.deepcopy(original); request["inventory"]["tasks"][0]["hostId"] = "remote"
        with self.assertRaises(Refusal): self.settle(request)
        self.assertEqual(len(self.api.store.snapshot()["resources"]), 1)

    def test_retained_descendant_cannot_be_omitted(self):
        self.fx.pause_inventory(("child",))
        with self.assertRaisesRegex(Refusal, "descendant missing"): self.settle(self.request())

    def test_attempt_drift_and_stale_revision_or_time_refuse_proof(self):
        request = proof_request(self.api, self.token, self.wid, "worker-fixture")
        for changes in ({"expectedRevision": 0}, {"expectedHash": "f"*64}, {"observedAt": 0},
                        {"observedAt": time.time()+60}, {"content": "x"*8001}, {"threadId": None}, {"extra": True}):
            with self.subTest(changes=list(changes)), self.assertRaises(Refusal):
                self.api.proof_add(self.token, self.wid, request | changes)
        self.fx.fx.observe()
        with self.assertRaises(Refusal): self.api.proof_add(self.token, self.wid, request)

    def test_pause_expiry_and_revocation_allow_only_safety_settlement(self):
        self.fx.fx.fx.fx.fx.command("pause")
        runs.revoke_task(self.fx.ledger, self.fx.fx.fx.fx.request(queueId=self.fx.worker()["queueId"],
            approvalHash=self.fx.fx.fx.approval["approvalHash"], reason="fixture revoked"), actor="dashboard_owner")
        with patch("orchestrator.run_authority.require_current", side_effect=AssertionError("not new work")):
            receipt = self.settle(self.request())
        self.assertTrue(receipt["ownershipReleased"]); self.assertFalse(receipt["executionAuthorized"])
        self.assertTrue(self.fx.ledger.snapshot()["meta"]["paused"])

    def test_maintenance_blocks_new_proof_and_settlement_but_allows_historical_recovery(self):
        request = self.request(); path = self.fx.ledger.root / "admission-fence.json"
        path.touch()
        with self.assertRaises(Refusal): self.settle(request)
        with self.assertRaises(Refusal): self.api.proof_add(self.token, self.wid, proof_request(self.api, self.token, self.wid, "worker-fixture", "new"))
        path.unlink(); receipt = self.settle(request); path.touch()
        self.assertEqual(receipt, self.api.recover(self.token, self.wid))

    def test_interrupted_attachment_inspection_does_not_recover_and_new_owner_survives(self):
        request = self.request()
        with patch.object(terminal.ConfirmedSettlement, "attach_in", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError): self.settle(request)
        before = logical(self.api); state = self.api.state(self.token, self.wid)
        self.assertTrue(state["recoveryRequired"]); self.assertFalse(state["receiptAttached"])
        self.assertEqual(before, logical(self.api))
        bridge, token, args = self.fx.fx.fx.second_workspace(request["resources"][0]["key"])
        newer = bridge.reserve(token, **args)
        receipt = self.api.recover(self.token, self.wid)
        self.assertTrue(receipt["ownershipReleased"])
        self.assertEqual(self.api.store.snapshot()["resources"][0]["claimId"], newer["workerId"])

    def test_corrupt_proof_blocks_recovery_without_reattaching(self):
        request = self.request()
        with patch.object(terminal.ConfirmedSettlement, "attach_in", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError): self.settle(request)
        with self.fx.ledger.tx() as db:
            db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"changed", request["inventory"]["tasks"][0]["checkpointArtifactId"]))
        with self.assertRaises(Refusal): self.api.recover(self.token, self.wid)
        self.assertNotIn("ownershipSettlementHash", self.fx.worker())

    def test_strict_request_reader_duplicate_nonfinite_oversized_symlink(self):
        from orchestrator.result_handoff import read_request
        path = self.fx.ledger.root / "bad.json"
        for raw in ('{"id":"a","id":"b"}', '{"x":NaN}', "x"*16001):
            path.write_text(raw)
            with self.assertRaises(Refusal): read_request(path)
        link = self.fx.ledger.root / "link.json"; link.symlink_to(path)
        with self.assertRaises((Refusal, OSError)): read_request(link)

    def test_harness_scope_and_nonlocal_worker_refuse_before_writes(self):
        original = runs.document
        def changed(db, key, kind):
            doc = original(db, key, kind)
            return doc | {"policyProfile": "harness"} if kind == "seed" else doc
        before = logical(self.api)
        with patch.object(runs, "document", side_effect=changed), self.assertRaisesRegex(Refusal, "Harness"):
            self.api.state(self.token, self.wid)
        self.assertEqual(before, logical(self.api))
        self.fx.mutate_worker(hostId="remote")
        with self.assertRaisesRegex(Refusal, "local"): self.api.state(self.token, self.wid)

    def test_proof_metadata_or_receipt_corruption_refuses(self):
        receipt = self.api.proof_add(self.token, self.wid, proof_request(self.api, self.token, self.wid, "worker-fixture"))
        with self.fx.ledger.tx() as db:
            original = json.loads(db.execute("SELECT data FROM artifact_versions WHERE id=?", (receipt["artifactId"],)).fetchone()[0])
        for change in ({"observedAt": time.time()+1}, {"references": []}, {"provenance": "generic"}, {"terminalProofHash": "f"*64}):
            with self.fx.ledger.tx() as db:
                db.execute("UPDATE artifact_versions SET data=? WHERE id=?", (canonical(original | change), receipt["artifactId"]))
            with self.fx.ledger.tx() as db, self.assertRaises(Refusal):
                _, intent = self.api.bridge.intent_in(db, self.wid)
                terminal.proof_in(db, receipt["artifactId"], intent, self.fx.claim()["nativeLifecycleHash"], "confirmed", "worker-fixture")

    def test_proof_retention_rollback_does_not_leave_dangling_artifact(self):
        request = proof_request(self.api, self.token, self.wid, "worker-fixture"); before = logical(self.api)
        with patch.object(self.api.ledger, "event", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError): self.api.proof_add(self.token, self.wid, request)
        self.assertEqual(before, logical(self.api))

    def test_concurrent_settlement_is_one_release_and_no_usage_reset(self):
        request = self.request()
        with ThreadPoolExecutor(2) as pool:
            receipts = list(pool.map(lambda _: self.settle(request), range(2)))
        self.assertEqual(receipts[0], receipts[1]); self.assertEqual(self.fx.budget()["unincorporatedSettledTokens"], 1000)
        with self.api.store.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM ownership_settlements").fetchone()[0], 1)

    def test_settlement_without_commit_cannot_be_recovered(self):
        before = logical(self.api)
        with self.assertRaisesRegex(Refusal, "No committed"): self.api.recover(self.token, self.wid)
        self.assertEqual(before, logical(self.api))


class AbsentHandoffTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_creation_recovery.CreationRecoveryTest(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.fx.begin(); self.fx.observe()
        self.api = terminal.TerminalHandoff(self.fx.fx.bridge, "not_created")
        self.token, self.wid = self.fx.token, self.fx.wid

    def request(self): return bind_proofs(self.api, self.token, self.wid, self.fx.evidence(), True)

    def test_cli_not_created_retains_attempt_no_retry_and_zero_actual(self):
        request = self.request(); result = checked_cli(self.api, self.token, self.wid, "settle", request)
        self.assertEqual(result["creationOutcome"], "not_created"); self.assertEqual(result["actualTokens"], 0)
        self.assertFalse(result["retryAuthorized"]); self.assertFalse(result["packetAccepted"])
        self.assertEqual(len(self.fx.store.snapshot()["claims"]), 1)
        self.assertEqual(self.fx.worker()["clientThreadId"], "client-fixture")
        self.assertEqual(result, checked_cli(self.api, self.token, self.wid, "recover"))
        before = logical(self.api); self.assertTrue(self.api.state(self.token, self.wid)["receiptAttached"])
        self.assertEqual(before, logical(self.api))

    def test_partial_absence_or_nonzero_usage_cannot_release(self):
        original = self.request()
        for field in ("requestFinal", "complete", "includesDescendants", "pendingResolved", "effectsComplete"):
            request = copy.deepcopy(original); request["inventory"][field] = False
            with self.assertRaises(Refusal): self.api.settle(self.token, self.wid, request)
        request = copy.deepcopy(original); request["usage"]["counters"]["inputTokens"] = 1
        with self.assertRaises(Refusal): self.api.settle(self.token, self.wid, request)
        self.assertEqual(len(self.api.store.snapshot()["resources"]), 1)

    def test_confirmed_outcome_cannot_be_inferred_from_pending_creation(self):
        before = logical(self.api)
        with self.assertRaises(Refusal): terminal.TerminalHandoff(self.fx.fx.bridge, "confirmed").state(self.token, self.wid)
        self.assertEqual(before, logical(self.api))

    def test_interrupted_absence_receipt_is_recovered_without_second_release(self):
        request = self.request()
        with patch.object(terminal.AbsentSettlement, "attach_in", side_effect=RuntimeError("interrupted")):
            with self.assertRaises(RuntimeError): self.api.settle(self.token, self.wid, request)
        before = logical(self.api); self.assertTrue(self.api.state(self.token, self.wid)["recoveryRequired"])
        self.assertEqual(before, logical(self.api)); shared = self.api.store.snapshot()
        self.api.recover(self.token, self.wid); self.assertEqual(shared, self.api.store.snapshot())


class TerminalCompositionTest(unittest.TestCase):
    @staticmethod
    def settle_via_cli(fixture, request=None):
        api = terminal.TerminalHandoff(fixture.bridge, "confirmed")
        bound = bind_proofs(api, fixture.token, fixture.wid, request or fixture.evidence(), True)
        return checked_cli(api, fixture.token, fixture.wid, "settle", bound)

    def test_terminal_cli_composes_with_measured_result_cli(self):
        import test_result_handoff
        fixture = test_result_handoff.ResultHandoffTest()
        with patch.object(test_ownership_settlement.OwnershipSettlementTest, "settle", self.settle_via_cli):
            fixture.setUp()
        try:
            request = fixture.review_request(cli=True)
            self.assertTrue(fixture.call("review", request, cli=True)["packetAccepted"])
            api = terminal.TerminalHandoff(fixture.api.bridge, "confirmed")
            before = logical(api); state = api.state(fixture.token, fixture.wid)
            self.assertEqual(before, logical(api)); self.assertFalse(state["settlement"]["packetAccepted"])
        finally: fixture.doCleanups()

    def test_terminal_cli_allows_delegated_next_packet_without_owner_continue(self):
        import test_brain_coordinator
        fixture = test_brain_coordinator.BrainCoordinatorTest(); fixture.setUp()
        try:
            with patch.object(test_ownership_settlement.OwnershipSettlementTest, "settle", self.settle_via_cli):
                fixture.test_reviewed_first_packet_exposes_next_delegated_packet_without_owner_continue()
        finally: fixture.tearDown(); fixture.doCleanups()


if __name__ == "__main__": unittest.main()
