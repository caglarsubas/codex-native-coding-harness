"""Synthetic designated-brain handoffs; never send messages or execute acceptance."""
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

from orchestrator import runner_handoff, run_authority as runs, native_supervision, phase_usage
from orchestrator.core import Refusal, canonical, digest
import test_runner_coordination
from test_native_supervision import usage_result


class RunnerHandoffTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_runner_coordination.RunnerCoordinationTest(); self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.r = self.fx.r
        self.api = runner_handoff.RunnerHandoff(self.r.api.bridge); self.r.api = self.api
        self.ledger, self.store, self.token, self.wid = self.r.ledger, self.r.store, self.r.token, self.r.wid
        self.dispatch = self.fx.fx.fx

    def prepare(self):
        self.r.acquire()
        return self.api.prepare(self.token, self.wid, self.r.launch())

    def check(self, handoff): return self.api.check(self.token, self.wid, handoff["handoffHash"])
    def state(self): return self.api.state(self.token, self.wid)
    def pause(self): self.dispatch.fx.fx.command("brain_stop")
    def logical(self): return self.dispatch.fx.fx.logical(), self.store.snapshot()

    def delivery(self, handoff, **fields):
        return self.r.request(handoffHash=handoff["handoffHash"], hostId="local", threadId=self.r.thread,
            outcome="acknowledged", observedAt=time.time(), evidenceHash="b"*64) | fields

    def cli(self, operation, *args, request=None, token=None, select=True, workspace="a"):
        argv = [sys.executable, "-m", "orchestrator.cli"]
        if select: argv += ["--platform", str(self.dispatch.registry.root), "--workspace", workspace]
        argv += ["runner-handoff-"+operation, self.wid, *args]
        if request is not None:
            path = self.ledger.root / "fixture-request.json"; path.write_text(canonical(request)); argv.append(str(path))
        return subprocess.run(argv, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
            env={**os.environ, "ORCHESTRATOR_CONTROLLER_TOKEN": token or self.token})

    def between_launch(self, change):
        locked, calls = self.api.bridge.locked, 0
        def boundary(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3: change()  # check read, local launch marker, shared launch
            return locked(*args, **kwargs)
        return patch.object(self.api.bridge, "locked", side_effect=boundary)

    def test_prepare_emits_exact_target_contract_and_no_other_authority(self):
        self.r.acquire(); before = self.store.snapshot()
        handoff = self.api.prepare(self.token, self.wid, self.r.launch())
        args = handoff["arguments"]
        self.assertEqual(set(args), {"hostId", "threadId", "prompt"})
        self.assertEqual(args["threadId"], self.r.thread); self.assertEqual(args["hostId"], "local")
        self.assertIn(canonical(self.dispatch.fx.fx.seed["execution"]), args["prompt"])
        self.assertIn(self.r.artifact["id"], args["prompt"])
        self.assertIn("No edits, retries, new tasks, merge, archive", args["prompt"])
        self.assertNotIn("Observe the pinned fixture", args["prompt"])
        self.assertEqual(handoff["tool"], "send_message_to_thread")
        self.assertTrue(handoff["mustCheckBeforeSend"]); self.assertFalse(handoff["nativeCallMade"])
        self.assertEqual(before, self.store.snapshot()); self.assertFalse(self.state()["sendCheckConsumed"])

    def test_one_shot_check_and_separate_delivery_process_cleanup(self):
        handoff = self.prepare(); checked = self.check(handoff)
        self.assertTrue(checked["sendNow"]); self.assertFalse(checked["reusablePermit"])
        self.assertEqual(checked["runnerStatus"], "launch_intent")
        self.assertFalse(checked["nativeCallMade"])
        saved = self.api.delivery(self.token, self.wid, self.delivery(handoff))
        self.assertEqual(saved["runnerStatus"], "launch_intent")
        self.assertEqual(self.r.state()["creation"]["activity"], "unknown")
        self.assertEqual(self.state()["runner"]["delivery"]["outcome"], "acknowledged")
        self.assertEqual(len(self.store.snapshot()["resources"]), 2)
        self.r.observe("running"); self.r.observe("exited", exitCode=4)
        self.assertEqual(len(self.store.snapshot()["resources"]), 2)
        self.r.release()
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)
        self.assertEqual(self.r.claim()["estimatedTokens"], 12650)
        self.assertFalse(self.ledger.snapshot()["meta"]["pilotPassed"])
        self.assertNotIn("arguments", self.state())
        # The new delivery field must remain compatible with terminal settlement;
        # even a settled nonzero-exit attempt is not an accepted packet.
        settled = self.fx.settlement_helper().settle()
        self.assertTrue(settled["ownershipReleased"]); self.assertFalse(settled["packetAccepted"])
        self.assertEqual(self.store.snapshot()["resources"], [])

    def test_prepare_and_check_never_replay_send(self):
        handoff = self.prepare(); request = self.ledger.document(handoff["handoffHash"])["request"]
        self.check(handoff); before = self.logical()
        for call in (lambda: self.check(handoff), lambda: self.api.prepare(self.token, self.wid, request)):
            with self.assertRaises(Refusal): call()
            self.assertEqual(before, self.logical())
        self.api.recover(self.token, self.wid)
        with self.assertRaises(Refusal): self.check(handoff)

    def test_concurrent_prepares_emit_only_one_handoff(self):
        self.r.acquire(); request = self.r.launch()
        def prepare(_):
            try: return self.api.prepare(self.token, self.wid, request)
            except Refusal: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(prepare, range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_concurrent_checks_emit_only_one_send_permission(self):
        handoff = self.prepare()
        def check(_):
            try: return self.check(handoff)
            except Refusal: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(check, range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.r.claim()["estimatedTokens"], 12650)

    def test_stale_handoff_and_budget_refuse_without_marker(self):
        handoff = self.prepare()
        with patch.object(runner_handoff.time, "time", return_value=time.time()+61):
            with self.assertRaisesRegex(Refusal, "expired"): self.check(handoff)
        self.dispatch.refresh_usage(total=79000)
        with self.assertRaisesRegex(Refusal, "headroom"): self.check(handoff)
        self.assertFalse(self.state()["sendCheckConsumed"])

    def test_exhausted_native_account_blocks_send(self):
        handoff = self.prepare()
        native_supervision.NativeSupervision(self.api.bridge).account_record(self.token,
            {"id": "exhausted", "expectedHash": None, "observedAt": time.time(), "result": usage_result(short=100)})
        with self.assertRaisesRegex(Refusal, "headroom"): self.check(handoff)
        self.assertFalse(self.state()["sendCheckConsumed"])

    def test_phase_counter_gaps_block_send(self):
        handoff = self.prepare()
        native_supervision.NativeSupervision(self.api.bridge).account_record(self.token,
            {"id": "healthy", "expectedHash": None, "observedAt": time.time(), "result": usage_result()})
        usage = phase_usage.PhaseUsage(self.api.bridge); aid = self.dispatch.binding["id"]
        current = usage.state(self.token, aid)
        usage.record(self.token, aid, {"id": "missing", "expectedHash": None, "contextHash": current["contextHash"],
            "observedAt": time.time(), "evidence": {"accountIdentityHash": current["accountIdentityHash"],
                "complete": False, "includesDescendants": False, "evidenceHash": "d"*64, "sessions": []}})
        with self.assertRaises(Refusal): self.check(handoff)
        self.assertFalse(self.state()["sendCheckConsumed"])

    def test_pause_before_check_is_not_a_send_or_cancellation(self):
        handoff = self.prepare(); self.pause()
        with self.assertRaises(Refusal): self.check(handoff)
        self.assertFalse(self.state()["sendCheckConsumed"])
        self.assertEqual(self.state()["runner"]["status"], "reserved")
        self.r.release("unlaunched")
        self.assertEqual(self.state()["runner"]["status"], "released")

    def test_pause_between_launch_commits_retains_unmatched_intent(self):
        handoff = self.prepare()
        with self.between_launch(self.pause):
            with self.assertRaises(Refusal): self.check(handoff)
        self.assertTrue(self.state()["sendCheckConsumed"])
        self.assertEqual(self.r.worker()["dispatchAdmission"]["stage"], "runner_launch_pending")
        self.api.recover(self.token, self.wid)
        with self.assertRaises(Refusal): self.r.release("unlaunched")
        with self.assertRaises(Refusal): self.check(handoff)

    def test_shared_commit_receipt_crash_recovers_without_send_permission(self):
        handoff = self.prepare(); attach = self.api.attach_in
        def crash(db, worker, claim, record):
            if worker.get("nativeLifecycleHash") != digest(record): raise RuntimeError("fixture receipt crash")
            return attach(db, worker, claim, record)
        with patch.object(self.api, "attach_in", side_effect=crash):
            with self.assertRaises(RuntimeError): self.check(handoff)
        self.assertEqual(self.state()["runner"]["status"], "launch_intent")
        self.api.recover(self.token, self.wid)
        with self.assertRaises(Refusal): self.check(handoff)
        self.assertTrue(self.state()["sendCheckConsumed"])

    def test_artifact_tampering_before_and_between_send_gates_refuses(self):
        handoff = self.prepare()
        def change():
            with self.ledger.tx() as db:
                db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"run something else", self.r.artifact["id"]))
        with self.between_launch(change):
            with self.assertRaisesRegex(Refusal, "instruction binding"): self.check(handoff)
        self.assertTrue(self.state()["sendCheckConsumed"])
        with self.assertRaises(Refusal): self.check(handoff)

    def test_handoff_pointer_loss_and_tampered_document_refuse(self):
        handoff = self.prepare()
        with self.ledger.tx() as db:
            worker = self.ledger.get(db, "workers", self.wid); worker.pop("runnerHandoffHash")
            self.ledger.put(db, "workers", self.wid, worker)
        with self.assertRaisesRegex(Refusal, "pointer changed"): self.state()
        with self.assertRaises(Refusal): self.api.prepare(self.token, self.wid, self.r.launch())
        with self.ledger.tx() as db:
            worker["runnerHandoffHash"] = handoff["handoffHash"]; self.ledger.put(db, "workers", self.wid, worker)
            db.execute("UPDATE snapshots SET data='{}' WHERE id=?", (handoff["handoffHash"],))
        with self.assertRaises(Refusal): self.check(handoff)

    def test_uncertain_delivery_never_retries_or_releases(self):
        handoff = self.prepare(); self.check(handoff)
        request = self.delivery(handoff, outcome="uncertain")
        self.api.delivery(self.token, self.wid, request)
        with self.assertRaises(Refusal): self.check(handoff)
        with self.assertRaises(Refusal): self.r.release("unlaunched")
        with self.assertRaises(Refusal): self.r.release()
        self.api.delivery(self.token, self.wid, self.delivery(handoff))
        self.assertEqual(self.state()["runner"]["status"], "launch_intent")

    def test_delivery_replay_preserves_newer_process_state_and_timestamp(self):
        handoff = self.prepare(); self.check(handoff); request = self.delivery(handoff, outcome="uncertain")
        first = self.api.delivery(self.token, self.wid, request)
        self.r.observe("running"); before = self.logical()
        replay = self.api.delivery(self.token, self.wid, request)
        self.assertEqual(first["recordHash"], replay["recordHash"])
        self.assertEqual(replay["runnerStatus"], "running"); self.assertEqual(before, self.logical())
        with self.assertRaises(Refusal): self.api.delivery(self.token, self.wid, request | {"outcome": "acknowledged"})

    def test_acknowledgment_cannot_be_downgraded_or_retimestamped(self):
        handoff = self.prepare(); self.check(handoff)
        self.api.delivery(self.token, self.wid, self.delivery(handoff))
        before = self.logical()
        for outcome in ("acknowledged", "uncertain"):
            with self.assertRaises(Refusal): self.api.delivery(self.token, self.wid, self.delivery(handoff, outcome=outcome))
        self.assertEqual(before, self.logical())

    def test_delivery_requires_consumed_check_exact_task_and_closed_shape(self):
        handoff = self.prepare()
        with self.assertRaisesRegex(Refusal, "not been consumed"): self.api.delivery(self.token, self.wid, self.delivery(handoff))
        self.check(handoff); before = self.logical()
        for fields in ({"threadId": "another"}, {"hostId": "another"}, {"outcome": "finished"},
                       {"handoffHash": "c"*64}, {"observedAt": 0}, {"observedAt": float("nan")},
                       {"observedAt": time.time()+61}, {"extra": True}, {"expectedHash": "d"*64}):
            with self.subTest(fields=fields), self.assertRaises(Refusal):
                self.api.delivery(self.token, self.wid, self.delivery(handoff, **fields))
        self.assertEqual(before, self.logical())

    def test_late_delivery_after_pause_and_process_exit_is_not_acceptance(self):
        handoff = self.prepare(); self.check(handoff); self.pause(); self.r.observe("exited")
        saved = self.api.delivery(self.token, self.wid, self.delivery(handoff))
        self.assertEqual(saved["runnerStatus"], "exited")
        self.assertFalse(saved["ownershipReleased"]); self.assertFalse(saved["executionAuthorized"])
        self.r.release(); self.assertEqual(self.state()["runner"]["status"], "released")

    def test_delivery_shared_commit_crash_has_receipt_only_recovery(self):
        handoff = self.prepare(); self.check(handoff); request = self.delivery(handoff)
        attach = self.api.attach_in
        def crash(db, worker, claim, record):
            if worker.get("nativeLifecycleHash") != digest(record): raise RuntimeError("fixture receipt crash")
            return attach(db, worker, claim, record)
        with patch.object(self.api, "attach_in", side_effect=crash):
            with self.assertRaises(RuntimeError): self.api.delivery(self.token, self.wid, request)
        self.api.recover(self.token, self.wid); before = self.logical()
        self.api.delivery(self.token, self.wid, request)
        self.assertEqual(before, self.logical())
        with self.assertRaises(Refusal): self.check(handoff)

    def test_revoked_authority_and_current_controls_block_send(self):
        handoff = self.prepare()
        runs.revoke_task(self.ledger, self.dispatch.fx.request(queueId=self.dispatch.args["queue_id"],
            approvalHash=self.dispatch.approval["approvalHash"], reason="Fixture withdrawal"), actor="dashboard_owner")
        with self.assertRaises(Refusal): self.check(handoff)
        self.assertFalse(self.state()["sendCheckConsumed"])

    def test_read_and_recover_do_not_refresh_or_emit_arguments(self):
        handoff = self.prepare(); self.check(handoff); before = self.logical()
        self.state(); receipt = self.api.recover(self.token, self.wid)
        self.assertEqual(before, self.logical()); self.assertNotIn("sendNow", receipt)
        self.assertNotIn("arguments", receipt)

    def test_harness_and_nonlocal_targets_are_not_handoff_capabilities(self):
        self.r.acquire(); original = runs.document
        def changed(db, key, kind):
            doc = original(db, key, kind)
            if kind == "seed": doc = {**doc, "policyProfile": "harness"}
            return doc
        with patch.object(runs, "document", side_effect=changed):
            with self.assertRaises(Refusal): self.api.prepare(self.token, self.wid, self.r.launch())
        with self.ledger.tx() as db:
            worker, intent = self.api.bridge.intent_in(db, self.wid)
        state = copy.deepcopy(self.r.state()); state["creation"]["hostId"] = "remote"
        with self.assertRaises(Refusal): runner_handoff.arguments(worker, intent, self.dispatch.fx.fx.seed, state)

    def test_wrong_controller_workspace_and_foreign_handoff_refuse(self):
        handoff = self.prepare(); other = self.fx.other()
        foreign = runner_handoff.RunnerHandoff(other.api.bridge)
        for call in (lambda: self.api.check("wrong", self.wid, handoff["handoffHash"]),
                     lambda: foreign.check(other.token, other.wid, handoff["handoffHash"]),
                     lambda: self.api.check(self.token, other.wid, handoff["handoffHash"])):
            with self.assertRaises(Refusal): call()
        self.assertFalse(self.state()["sendCheckConsumed"])

    def test_cli_full_workflow_and_workspace_required(self):
        for operation in ("state", "recover"):
            result = self.cli(operation, select=False)
            self.assertNotEqual(result.returncode, 0); self.assertIn("explicit registered workspace", result.stderr)
        result = self.cli("acquire", request=self.r.reservation())
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("prepare", request=self.r.launch())
        self.assertEqual(result.returncode, 0, result.stderr); handoff = json.loads(result.stdout)
        result = self.cli("check", handoff["handoffHash"])
        self.assertEqual(result.returncode, 0, result.stderr); self.assertTrue(json.loads(result.stdout)["sendNow"])
        self.assertNotEqual(self.cli("check", handoff["handoffHash"]).returncode, 0)
        result = self.cli("delivery", request=self.delivery(handoff))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("observe-process", request=self.r.process("exited"))
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("release", request=self.r.cleanup())
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("state"); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["runner"]["status"], "released")
        self.assertEqual(self.cli("recover").returncode, 0)

    def test_cli_rejects_symlink_oversize_and_wrong_token(self):
        path = self.ledger.root / "bad.json"; path.write_text(" "*16001)
        self.assertNotEqual(self.cli("acquire", str(path)).returncode, 0)
        path.write_text(canonical(self.r.reservation()))
        link = self.ledger.root / "link.json"; link.symlink_to(path)
        self.assertNotEqual(self.cli("acquire", str(link)).returncode, 0)
        self.assertNotEqual(self.cli("acquire", str(path), token="wrong").returncode, 0)
        self.assertIsNone(self.state()["runner"])

    def test_artifact_tampering_before_check_does_not_cross_launch(self):
        handoff = self.prepare()
        with self.ledger.tx() as db:
            db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"different", self.r.artifact["id"]))
        with self.assertRaises(Refusal): self.check(handoff)
        self.assertFalse(self.state()["sendCheckConsumed"])

    def test_canceled_prepared_reservation_cannot_be_sent_or_recreated(self):
        handoff = self.prepare(); self.r.release("unlaunched"); before = self.logical()
        with self.assertRaises(Refusal): self.check(handoff)
        with self.assertRaises(Refusal): self.api.prepare(self.token, self.wid, self.r.launch())
        with self.assertRaises(Refusal): self.r.acquire()
        self.assertEqual(before, self.logical())

    def test_closed_prepare_shape_and_reused_request_id_fail_before_launch(self):
        self.r.acquire(); request = self.r.launch()
        for fields in ({"prompt": "run a different command"}, {"model": "override"}, {"expectedHash": "c"*64},
                       {"runnerKey": "runner:"+"f"*64}, {"reservationId": "other"}):
            with self.subTest(fields=fields), self.assertRaises(Refusal):
                self.api.prepare(self.token, self.wid, request | fields)
        # A launch request cannot reuse the runner acquisition request ID.
        handoff = self.api.prepare(self.token, self.wid, request | {"id": self.r.state()["runner"]["reservationId"]})
        with self.assertRaisesRegex(Refusal, "ID reused"): self.check(handoff)
        self.assertFalse(self.state()["sendCheckConsumed"])

    def test_maintenance_and_inbox_checkpoint_fence_new_send(self):
        handoff = self.prepare()
        self.dispatch.meta(admissionBinding={"fixture": True})
        with self.assertRaises(Refusal): self.check(handoff)
        self.dispatch.meta(admissionBinding=None)
        self.dispatch.fx.fx.command("checkpoint", {"workerId": self.wid})
        with self.assertRaises(Refusal): self.check(handoff)
        self.assertFalse(self.state()["sendCheckConsumed"])

    def test_stale_and_nonidle_runner_observation_refuse_preparation(self):
        self.r.acquire()
        for fields in ({"state": "unknown"}, {"complete": False}, {"cleanupObserved": False},
                       {"observedAt": time.time()-61}, {"observedAt": time.time()+1}):
            request = self.r.launch(); request["observation"].update(fields)
            with self.subTest(fields=fields), self.assertRaises(Refusal): self.api.prepare(self.token, self.wid, request)
        self.assertIsNone(self.state()["handoffHash"])

    def test_stale_native_idle_blocks_new_handoff(self):
        self.r.acquire()
        with patch.object(self.store, "clock", return_value=time.time()+61):
            with self.assertRaises(Refusal): self.api.prepare(self.token, self.wid, self.r.launch())
        self.assertFalse(self.state()["sendCheckConsumed"])

    def test_no_command_or_transport_called_by_the_handoff(self):
        with patch("subprocess.run", side_effect=AssertionError("No process allowed")), \
                patch("subprocess.Popen", side_effect=AssertionError("No process allowed")):
            handoff = self.prepare(); self.check(handoff)
            self.api.delivery(self.token, self.wid, self.delivery(handoff))
        self.assertEqual(self.state()["runner"]["status"], "launch_intent")

    def test_foreign_instruction_repository_refuses_preparation(self):
        self.r.acquire()
        with self.ledger.tx() as db:
            row = db.execute("SELECT data FROM artifact_versions WHERE id=?", (self.r.artifact["id"],)).fetchone()
            artifact = json.loads(row[0]); artifact["repository"] = "b"
            db.execute("UPDATE artifact_versions SET data=? WHERE id=?", (canonical(artifact), self.r.artifact["id"]))
        with self.assertRaises(Refusal): self.api.prepare(self.token, self.wid, self.r.launch())
        self.assertIsNone(self.state()["handoffHash"])

    def test_changed_preflight_between_check_commits_keeps_ownership(self):
        handoff = self.prepare()
        def change():
            with self.ledger.tx() as db:
                q = self.ledger.get(db, "queue", self.dispatch.args["queue_id"])
                q["preflight"]["checks"]["locksVerified"] = False
                self.ledger.put(db, "queue", q["id"], q)
        with self.between_launch(change):
            with self.assertRaises(Refusal): self.check(handoff)
        self.assertTrue(self.state()["sendCheckConsumed"])
        self.assertEqual(len(self.store.snapshot()["resources"]), 2)

    def test_internal_receipt_replay_does_not_expose_send_now(self):
        handoff = self.prepare(); self.check(handoff)
        request = self.ledger.document(handoff["handoffHash"])["request"]
        receipt = self.api.begin(self.token, self.wid, request)
        self.assertNotIn("sendNow", receipt); self.assertNotIn("arguments", receipt)
        self.assertFalse(receipt["nativeCallMade"])


if __name__ == "__main__": unittest.main()
