"""Disposable ledgers/Git and native-shaped fixtures; no real model or task calls."""
import contextlib
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

from orchestrator import model_policy as models, missions, run_authority as runs
from orchestrator import correction_handoff, native_lifecycle
from orchestrator.core import Refusal, canonical, digest
import test_dispatch_admission
import test_native_creation
import test_run_authority
import test_task_contracts
import test_runner_coordination

LOW = {"model": "fixture-economy", "effort": "medium", "speed": None}
HIGH = {"model": "fixture-reasoner", "effort": "high", "speed": None}


def request(ledger, prefix="settings", **fields):
    revision = ledger.snapshot()["meta"]["revision"]
    return {"id": prefix + "-" + str(revision), "expectedRevision": revision, **fields}


def capability(ledger, token, **fields):
    return models.record_capability(ledger, token, request(ledger, "capability", hostId="local",
        models=[{"model": LOW["model"], "efforts": ["low", "medium"]}, {"model": HIGH["model"], "efforts": ["high", "xhigh", "ultra"]}],
        observedAt=time.time(), evidenceHash="a"*64) | fields)


def policy_request(ledger, cap):
    m = missions.read(ledger)
    return request(ledger, "policy", missionHash=m["documentHash"], reviewReceiptHash=m["receiptHash"],
        capabilityHash=cap["capabilityHash"], confirmed=True, maxEscalations=1,
        qualityFloors={"routine": 1, "standard": 2, "complex": 3, "critical": 4},
        profiles=[{"id": "economy", "settings": LOW, "quality": 2, "minimumWorkTokens": 2000},
                  {"id": "reasoner", "settings": HIGH, "quality": 4, "minimumWorkTokens": 12000}])


def select_request(fx, **fields):
    return request(fx.ledger, "selection", runHash=fx.run["runHash"], queueId=fx.args["queue_id"],
        contractHash=fx.fx.contract["contractHash"], workerId=None, expectedHash=None, profileId="economy",
        complexity="standard", rationale="Bounded fixture task meets the reviewed quality floor.",
        capabilityHash=fx.ledger.snapshot()["meta"]["modelCapabilityHash"]) | fields


def select_approve(fx):
    selection = models.ModelPolicy(fx.bridge).select(fx.token, select_request(fx))
    approval = runs.approve_task(fx.ledger, fx.fx.approval_request(fx.run), actor="dashboard_owner")
    fx.approval = approval; fx.args["approval_hash"] = approval["approvalHash"]
    return selection


@contextlib.contextmanager
def adaptive_setup(*, native=False):
    spec, authorize, reserve = (test_task_contracts.TaskContractTest.spec,
                              test_run_authority.RunAuthorityTest.authorize,
                              test_dispatch_admission.DispatchAdmissionTest.reserve)
    def adaptive_spec(fixture, **fields): return spec(fixture, **fields) | {"requestedSettings": copy.deepcopy(LOW)}
    def adaptive_authorize(fixture, supplied=None):
        cap = capability(fixture.ledger, fixture.token)
        receipt = models.review(fixture.ledger, policy_request(fixture.ledger, cap), actor="dashboard_owner")
        return authorize(fixture, (supplied or fixture.auth_request()) | {
            "settingsPolicy": {"mode": "adaptive", "policyHash": receipt["policyHash"]}})
    def adaptive_reserve(fixture, **fields):
        select_approve(fixture)
        return reserve(fixture, **fields)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(test_task_contracts.TaskContractTest, "spec", adaptive_spec))
        stack.enter_context(patch.object(test_run_authority.RunAuthorityTest, "authorize", adaptive_authorize))
        stack.enter_context(patch.object(test_run_authority.RunAuthorityTest, "approve", return_value={"approvalHash": "a"*64}))
        if native: stack.enter_context(patch.object(test_dispatch_admission.DispatchAdmissionTest, "reserve", adaptive_reserve))
        yield


class ModelPolicyTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_dispatch_admission.DispatchAdmissionTest()
        with adaptive_setup(): self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.ledger, self.token, self.store = self.fx.ledger, self.fx.token, self.fx.store
        self.api = models.ModelPolicy(self.fx.bridge)

    def logical(self): return self.fx.fx.fx.logical(), self.store.snapshot()
    def select(self, **fields): return self.api.select(self.token, select_request(self.fx, **fields))
    def policy(self): return self.ledger.document(self.ledger.snapshot()["meta"]["modelPolicyHash"])
    def pause(self): self.fx.fx.fx.command("brain_stop")

    def test_capability_policy_and_selection_never_send_or_reserve(self):
        before = self.store.snapshot()
        with patch("subprocess.Popen", side_effect=AssertionError("No native call")): selected = self.select()
        doc = self.ledger.document(selected["selectionHash"])
        self.assertEqual(doc["settings"], LOW); self.assertEqual(doc["quality"], 2)
        self.assertEqual(before, self.store.snapshot()); self.assertEqual(self.ledger.snapshot()["workers"], [])
        self.assertFalse(selected["executionAuthorized"])
        self.assertFalse(self.api.state(self.token)["speedSupported"])

    def test_owner_review_and_revoke_cannot_be_called_by_brain(self):
        cap = capability(self.ledger, self.token)
        for actor in ("designated_brain", "unknown"):
            with self.assertRaises(Refusal): models.review(self.ledger, policy_request(self.ledger, cap), actor=actor)
            with self.assertRaises(Refusal): models.revoke(self.ledger, {}, actor=actor)

    def test_quality_floor_and_contract_match_refuse_silent_downgrade_or_fallback(self):
        before = self.logical()
        for fields in ({"complexity": "critical"}, {"profileId": "unavailable"}, {"profileId": "reasoner"},
                       {"capabilityHash": "a"*64}, {"rationale": ""}, {"speed": "fast"}):
            with self.assertRaises(Refusal): self.select(**fields)
        self.assertEqual(before, self.logical())

    def test_budget_unknown_or_exhausted_refuses_selection_without_approval(self):
        self.fx.refresh_usage(total=89000)
        before = self.logical()
        with self.assertRaisesRegex(Refusal, "headroom"): self.select()
        self.assertEqual(before, self.logical())

    def test_same_catalog_refresh_preserves_policy_but_changed_catalog_blocks(self):
        first = capability(self.ledger, self.token)
        self.assertEqual(first["catalogHash"], self.policy()["catalogHash"])
        self.select()
        capability(self.ledger, self.token, models=[{"model": LOW["model"], "efforts": ["low"]}])
        with self.assertRaisesRegex(Refusal, "catalog changed"): self.select()

    def test_catalog_return_does_not_restore_policy_without_fresh_owner_review(self):
        capability(self.ledger, self.token, models=[{"model": LOW["model"], "efforts": ["low"]}])
        cap = capability(self.ledger, self.token)
        self.assertEqual(cap["catalogHash"], self.policy()["catalogHash"])
        with self.assertRaisesRegex(Refusal, "owner policy review"): self.select()
        self.assertEqual(self.api.state(self.token)["policyStatus"], "blocked")
        self.fx.meta(paused=True)
        models.review(self.ledger, policy_request(self.ledger, cap), actor="dashboard_owner")
        self.assertEqual(self.api.state(self.token)["policyStatus"], "current_review_not_activation")
        self.assertEqual(runs.read(self.ledger)["state"]["status"], "fenced")

    def test_capability_expiry_does_not_get_refreshed_by_read_or_replay(self):
        req = request(self.ledger, "explicit-cap", hostId="local", models=self.api.state(self.token)["capability"]["catalog"]["models"],
                      observedAt=time.time(), evidenceHash="a"*64)
        one = models.record_capability(self.ledger, self.token, req)
        with patch.object(models.time, "time", return_value=req["observedAt"] + 301):
            self.assertEqual(models.record_capability(self.ledger, self.token, req), one)
            before = self.logical(); self.api.state(self.token); self.assertEqual(before, self.logical())
            with self.assertRaisesRegex(Refusal, "stale"): self.select()

    def test_capability_shape_future_duplicate_and_remote_refuse(self):
        before = self.logical()
        for fields in ({"models": []}, {"hostId": "remote"}, {"observedAt": time.time()+100},
                       {"models": [{"model": "x", "efforts": ["high", "high"]}]}, {"models": [{"model": "x", "efforts": ["invented"]}]},
                       {"models": [{"model": "x", "efforts": ["high"]}]*2}, {"evidenceHash": "invalid"}):
            with self.assertRaises(Refusal): capability(self.ledger, self.token, **fields)
        self.assertEqual(before, self.logical())

    def test_concurrent_selection_and_historical_replay_after_pause(self):
        req = select_request(self.fx)
        with ThreadPoolExecutor(max_workers=2) as pool: receipts = list(pool.map(lambda _: self.api.select(self.token, req), range(2)))
        self.assertEqual(receipts[0], receipts[1]); self.pause(); before = self.logical()
        self.assertEqual(self.api.select(self.token, req), receipts[0]); self.assertEqual(before, self.logical())
        with self.assertRaises(Refusal): self.select()

    def test_revocation_fences_run_without_resetting_shared_usage_or_owners(self):
        select_approve(self.fx); self.fx.reserve(); before = self.store.snapshot()
        policy_hash = self.ledger.snapshot()["meta"]["modelPolicyHash"]
        req = request(self.ledger, "revoke-policy", policyHash=policy_hash, reason="Owner withdrew model permission")
        receipt = models.revoke(self.ledger, req, actor="dashboard_owner")
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(runs.read(self.ledger)["state"]["status"], "fenced")
        with self.assertRaises(Refusal): self.fx.begin()
        self.assertEqual(models.revoke(self.ledger, req, actor="dashboard_owner"), receipt)

    def test_approval_locks_initial_choice(self):
        select_approve(self.fx)
        with self.assertRaisesRegex(Refusal, "before task approval"): self.select()
        self.assertEqual(self.fx.reserve()["stage"], "reserved")

    def test_transaction_failure_rolls_back_selection_and_pointer(self):
        before = self.logical()
        with patch.object(self.api.ledger, "event", side_effect=RuntimeError("fixture interruption")), self.assertRaises(RuntimeError): self.select()
        self.assertEqual(before, self.logical())

    def test_selection_refuses_wrong_controller_or_contract(self):
        with self.assertRaises(Refusal): self.api.select("wrong", select_request(self.fx))
        with self.assertRaises(Refusal): self.select(contractHash="a"*64)
        with self.assertRaises(Refusal): self.select(queueId="foreign")

    def test_owner_policy_rejects_unsupported_speed_ultra_and_duplicate_quality(self):
        self.fx.meta(paused=True)
        cap = capability(self.ledger, self.token)
        for change in ("speed", "ultra", "duplicate", "quality", "floor", "confirmation"):
            req = policy_request(self.ledger, cap)
            if change == "speed": req["profiles"][1]["settings"] = HIGH | {"speed": "fast"}
            elif change == "ultra": req["profiles"][1]["settings"] = HIGH | {"effort": "ultra"}
            elif change == "duplicate": req["profiles"].append(copy.deepcopy(req["profiles"][0]))
            elif change == "quality": req["profiles"][1]["quality"] = 1
            elif change == "floor": req["qualityFloors"]["routine"] = 4
            else: req["confirmed"] = False
            with self.assertRaises(Refusal): models.review(self.ledger, req, actor="dashboard_owner")

    def test_readonly_cli_and_selection_strict_json_no_owner_route(self):
        argv = [sys.executable, "-m", "orchestrator.cli", "--platform", str(self.fx.registry.root), "--workspace", "a"]
        env = {**os.environ, "ORCHESTRATOR_CONTROLLER_TOKEN": self.token}
        def call(tail): return subprocess.run(argv+tail, env=env, capture_output=True, text=True)
        before = self.logical(); result = call(["model-policy-state"])
        self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(before, self.logical())
        path = self.ledger.root / "model-request.json"; path.write_text(canonical(select_request(self.fx)))
        result = call(["model-policy-select", str(path)]); self.assertEqual(result.returncode, 0, result.stderr)
        path.write_text('{"id":"x","id":"y"}')
        self.assertNotEqual(call(["model-policy-select", str(path)]).returncode, 0)
        self.assertNotEqual(call(["model-policy-review", str(path)]).returncode, 0)

    def test_capability_pointer_rollback_and_missing_pointer_fail_closed(self):
        old = self.ledger.snapshot()["meta"]["modelCapabilityHash"]
        capability(self.ledger, self.token)
        self.fx.meta(modelCapabilityHash=old)
        with self.assertRaisesRegex(Refusal, "latest"): self.api.state(self.token)
        with self.assertRaises(Refusal): self.select()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.pop("modelCapabilityHash"); self.ledger.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "pointer missing"): capability(self.ledger, self.token)

    def test_profile_floor_is_enforced_again_at_actual_reservation(self):
        original = policy_request
        def larger(ledger, cap):
            req = original(ledger, cap); req["profiles"][0]["minimumWorkTokens"] = 20000
            return req
        other = test_dispatch_admission.DispatchAdmissionTest()
        with patch.object(sys.modules[__name__], "policy_request", larger), adaptive_setup(): other.setUp()
        self.addCleanup(other.tearDown)
        select_approve(other)
        with self.assertRaisesRegex(Refusal, "model profile"): other.reserve()
        self.assertEqual(other.store.snapshot()["claims"], [])
        self.assertEqual(other.reserve(estimates={"workTokens": 20000, "reviewTokens": 1000, "handoffTokens": 500})["stage"], "reserved")

    def test_owner_review_replay_does_not_restore_revoked_policy(self):
        self.fx.meta(paused=True)
        cap = capability(self.ledger, self.token); req = policy_request(self.ledger, cap)
        receipt = models.review(self.ledger, req, actor="dashboard_owner")
        models.revoke(self.ledger, request(self.ledger, "revoke-model", policyHash=receipt["policyHash"], reason="Withdraw"), actor="dashboard_owner")
        before = self.logical()
        self.assertEqual(models.review(self.ledger, req, actor="dashboard_owner"), receipt)
        self.assertEqual(before, self.logical()); self.assertTrue(self.api.state(self.token)["policyRevoked"])

    def test_unsupported_effort_is_refused_even_for_a_known_model(self):
        self.fx.meta(paused=True); cap = capability(self.ledger, self.token)
        req = policy_request(self.ledger, cap); req["profiles"][0]["settings"] = LOW | {"effort": "high"}
        with self.assertRaisesRegex(Refusal, "unavailable"): models.review(self.ledger, req, actor="dashboard_owner")

    def test_same_model_higher_effort_uses_the_same_owned_task(self):
        original_capability, original_policy = capability, policy_request
        def one_model(ledger, token, **fields):
            return original_capability(ledger, token,
                **({"models": [{"model": LOW["model"], "efforts": ["medium", "high"]}]} | fields))
        def effort_policy(ledger, cap):
            req = original_policy(ledger, cap)
            req["profiles"][1]["settings"] = LOW | {"effort": "high"}
            return req
        fixture = NativeModelPolicyTest()
        self.addCleanup(fixture.doCleanups)
        with patch.object(sys.modules[__name__], "capability", one_model), patch.object(sys.modules[__name__], "policy_request", effort_policy):
            fixture.setUp()
        fixture.start(); fixture.observe_settings()
        chosen = fixture.models.select(fixture.token, select_request(fixture.fx, workerId=fixture.wid,
            expectedHash=fixture.fx.claim()["nativeLifecycleHash"], profileId="reasoner", complexity="complex"))
        receipt = fixture.correction.prepare(fixture.token, fixture.wid, fixture.correction_request(chosen["selectionHash"]))
        checked = fixture.correction.check(fixture.token, fixture.wid, receipt["handoffHash"])
        self.assertEqual(checked["arguments"]["model"], LOW["model"])
        self.assertEqual(checked["arguments"]["thinking"], "high")
        self.assertEqual(checked["arguments"]["threadId"], "native-task")
        self.assertEqual(len(fixture.store.snapshot()["claims"]), 1)


class NativeModelPolicyTest(test_native_creation.NativeCreationFixture, unittest.TestCase):
    def setUp(self):
        with adaptive_setup(native=True), patch.object(test_dispatch_admission.DispatchAdmissionTest, "runners", [test_runner_coordination.RUNNER], create=True): super().setUp()
        self.models = models.ModelPolicy(self.fx.bridge)
        self.correction = correction_handoff.CorrectionHandoff(self.fx.bridge)

    def selection(self):
        return self.ledger.snapshot()["queue"][0]["modelSelectionHash"]

    def start(self):
        handoff = self.begin(); self.check(handoff); self.record(handoff)
        self.correction.observe(self.token, self.wid, {"id": "idle-observation", "expectedHash": self.fx.claim()["nativeLifecycleHash"],
            "outcome": "confirmed", "hostId": "local", "threadId": "native-task", "clientThreadId": None,
            "activity": "idle", "observedAt": time.time(), "evidenceHash": "b"*64})
        return handoff

    def observe_settings(self, **fields):
        worker = self.fx.worker()
        with self.ledger.tx() as db, self.store.tx() as kernel:
            _, intent = self.fx.bridge.intent_in(db, self.wid)
            _, _, state = self.correction.state_in(kernel, intent)
            selected, boundary, _ = models.active_selection(self.ledger, db, worker, intent, state)
        req = request(self.ledger, "model-observed", selectionHash=digest(selected), boundaryHash=boundary,
            hostId="local", threadId="native-task", applied=None, observed=selected["settings"], observedAt=time.time(), evidenceHash="c"*64) | fields
        return self.models.observe(self.token, self.wid, req)

    def correction_request(self, selection=None):
        return {"id": "correct-"+str(self.ledger.snapshot()["meta"]["revision"]),
                "expectedRevision": self.ledger.snapshot()["meta"]["revision"], "expectedHash": self.fx.claim()["nativeLifecycleHash"],
                "operation": "edit", "findings": "A fixture edge case needs correction.", "rationale": "Fix within the same packet.",
                "reuseReason": "Retain task knowledge.", "estimates": {"workTokens": 12000, "reviewTokens": 500, "handoffTokens": 500},
                "modelSelectionHash": selection or self.selection()}

    def test_creation_emits_exact_authorized_settings_without_speed_or_global_change(self):
        handoff = self.begin()
        self.assertEqual(handoff["arguments"]["model"], LOW["model"])
        self.assertEqual(handoff["arguments"]["thinking"], LOW["effort"])
        self.assertNotIn("speed", handoff["arguments"])
        self.assertTrue(self.check(handoff)["sendNow"])
        with self.assertRaises(Refusal): self.check(handoff)

    def test_acknowledgment_does_not_prove_applied_or_observed_settings(self):
        self.start()
        self.assertIsNone(self.models.state(self.token, self.wid)["observation"])
        with self.assertRaisesRegex(Refusal, "observation required"):
            self.correction.prepare(self.token, self.wid, self.correction_request())
        self.observe_settings()
        state = self.models.state(self.token, self.wid)["observation"]
        self.assertIsNone(state["applied"]); self.assertEqual(state["observed"], LOW)
        receipt = self.correction.prepare(self.token, self.wid, self.correction_request())
        checked = self.correction.check(self.token, self.wid, receipt["handoffHash"])
        self.assertEqual(checked["arguments"]["model"], LOW["model"])

    def test_mismatch_and_unknown_are_retained_but_block_further_work(self):
        self.start()
        for value in (HIGH, None):
            self.observe_settings(observed=value)
            self.assertEqual(self.models.state(self.token, self.wid)["observation"]["observed"], value)
            with self.assertRaises(Refusal): self.correction.prepare(self.token, self.wid, self.correction_request())
        self.observe_settings(applied=HIGH, observed=LOW)
        with self.assertRaises(Refusal): self.correction.prepare(self.token, self.wid, self.correction_request())

    def test_escalation_is_explicit_budgeted_one_shot_and_needs_new_observation(self):
        self.start(); self.observe_settings()
        req = select_request(self.fx, workerId=self.wid, expectedHash=self.fx.claim()["nativeLifecycleHash"],
                             profileId="reasoner", complexity="complex")
        chosen = self.models.select(self.token, req)
        receipt = self.correction.prepare(self.token, self.wid, self.correction_request(chosen["selectionHash"]))
        checked = self.correction.check(self.token, self.wid, receipt["handoffHash"])
        self.assertEqual(checked["arguments"]["model"], HIGH["model"])
        self.assertEqual(checked["arguments"]["thinking"], HIGH["effort"])
        with self.assertRaises(Refusal): self.correction.check(self.token, self.wid, receipt["handoffHash"])
        self.correction.record(self.token, self.wid, {"id": "correction-ack", "handoffHash": receipt["handoffHash"],
            "continuationHash": checked["continuationHash"], "expectedHash": self.fx.claim()["nativeLifecycleHash"],
            "hostId": "local", "threadId": "native-task", "outcome": "acknowledged", "observedAt": time.time(),
            "evidenceHash": "b"*64, "progress": None, "activity": "unknown"})
        self.correction.record(self.token, self.wid, {"id": "correction-finished", "handoffHash": receipt["handoffHash"],
            "continuationHash": checked["continuationHash"], "expectedHash": self.fx.claim()["nativeLifecycleHash"],
            "hostId": "local", "threadId": "native-task", "outcome": "finished", "observedAt": time.time(),
            "evidenceHash": "b"*64, "progress": True, "activity": "idle"})
        with self.assertRaises(Refusal): self.correction.prepare(self.token, self.wid, self.correction_request(chosen["selectionHash"]))
        self.observe_settings()
        with self.assertRaisesRegex(Refusal, "Escalation limit"):
            self.models.select(self.token, select_request(self.fx, workerId=self.wid, expectedHash=self.fx.claim()["nativeLifecycleHash"], profileId="reasoner", complexity="critical"))
        self.assertEqual(self.fx.claim()["continuationReservedTokens"], 13000)

    def test_policy_or_capability_drift_blocks_already_prepared_send(self):
        self.start(); self.observe_settings()
        receipt = self.correction.prepare(self.token, self.wid, self.correction_request())
        capability(self.ledger, self.token, models=[{"model": LOW["model"], "efforts": ["low"]}])
        with self.assertRaisesRegex(Refusal, "catalog changed"): self.correction.check(self.token, self.wid, receipt["handoffHash"])

    def test_late_matching_observation_after_pause_does_not_resume(self):
        self.start(); self.fx.fx.fx.command("brain_stop")
        observed = self.observe_settings()
        self.assertFalse(observed["executionAuthorized"]); self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        with self.assertRaises(Refusal): self.correction.prepare(self.token, self.wid, self.correction_request())

    def test_foreign_settings_target_and_unconsumed_selection_refuse(self):
        self.start()
        for fields in ({"threadId": "foreign"}, {"selectionHash": "a"*64}, {"boundaryHash": "b"*64}, {"hostId": "other"}):
            with self.assertRaises(Refusal): self.observe_settings(**fields)

    def test_runner_requires_observed_settings_and_inherits_without_override(self):
        from orchestrator.runner_handoff import RunnerHandoff
        self.start()
        rig = test_runner_coordination.Rig(self.fx.bridge, self.token, self.wid, "native-task")
        rig.api = RunnerHandoff(self.fx.bridge)
        with self.assertRaisesRegex(Refusal, "observation required"): rig.acquire()
        self.observe_settings(); rig.acquire()
        handoff = rig.api.prepare(self.token, self.wid, rig.launch())
        self.assertNotIn("model", handoff["arguments"]); self.assertNotIn("thinking", handoff["arguments"])
        self.assertTrue(rig.api.check(self.token, self.wid, handoff["handoffHash"])["sendNow"])

    def test_settings_observation_pointer_rollback_cannot_hide_mismatch(self):
        self.start(); first = self.observe_settings(); self.observe_settings(observed=HIGH)
        with self.ledger.tx() as db:
            worker = self.ledger.get(db, "workers", self.wid); worker["modelObservationHash"] = first["observationHash"]
            self.ledger.put(db, "workers", self.wid, worker)
        with self.assertRaisesRegex(Refusal, "pointer"): self.models.state(self.token, self.wid)
        with self.assertRaises(Refusal): self.correction.prepare(self.token, self.wid, self.correction_request())

    def test_settings_observation_expiry_blocks_correction_without_refreshing_evidence(self):
        self.start(); self.observe_settings(); now = time.time()
        before = self.models.state(self.token, self.wid)
        with patch.object(models.time, "time", return_value=now + 61):
            state = self.models.state(self.token, self.wid)
            self.assertFalse(state["observationFresh"]); self.assertEqual(state["observation"], before["observation"])
            with self.assertRaisesRegex(Refusal, "stale"): self.correction.prepare(self.token, self.wid, self.correction_request())

    def test_prepared_escalation_cannot_supply_observed_settings_before_send(self):
        self.start(); self.observe_settings()
        chosen = self.models.select(self.token, select_request(self.fx, workerId=self.wid,
            expectedHash=self.fx.claim()["nativeLifecycleHash"], profileId="reasoner", complexity="complex"))
        with self.assertRaises(Refusal): self.observe_settings(selectionHash=chosen["selectionHash"], observed=HIGH)

    def test_pause_between_correction_transactions_preserves_uncertainty(self):
        self.start(); self.observe_settings()
        handoff = self.correction.prepare(self.token, self.wid, self.correction_request())
        locked, count = self.correction.bridge.locked, 0
        def pause_gap(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 4: self.fx.fx.fx.command("brain_stop")
            return locked(*args, **kwargs)
        with patch.object(self.correction.bridge, "locked", side_effect=pause_gap), self.assertRaises(Refusal):
            self.correction.check(self.token, self.wid, handoff["handoffHash"])
        self.assertIsNotNone(self.fx.worker().get("nativeContinuationIntentHash"))
        self.assertEqual(self.fx.claim()["status"], "running")
        with self.assertRaises(Refusal): self.correction.check(self.token, self.wid, handoff["handoffHash"])

    def test_undercut_escalation_estimates_and_budget_stop_without_new_send(self):
        self.start(); self.observe_settings()
        chosen = self.models.select(self.token, select_request(self.fx, workerId=self.wid,
            expectedHash=self.fx.claim()["nativeLifecycleHash"], profileId="reasoner", complexity="complex"))
        req = self.correction_request(chosen["selectionHash"]); req["estimates"]["workTokens"] = 100
        with self.assertRaisesRegex(Refusal, "undercuts"): self.correction.prepare(self.token, self.wid, req)
        self.fx.refresh_usage(total=80000)
        with self.assertRaises(Refusal): self.correction.prepare(self.token, self.wid, self.correction_request(chosen["selectionHash"]))

    def test_creation_capability_drift_refuses_pre_send_without_second_attempt(self):
        handoff = self.begin()
        capability(self.ledger, self.token, models=[{"model": LOW["model"], "efforts": ["low"]}])
        with self.assertRaisesRegex(Refusal, "catalog changed"): self.check(handoff)
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        self.assertTrue(self.api.state(self.token, self.wid)["creationBoundaryCrossed"])


if __name__ == "__main__": unittest.main()
