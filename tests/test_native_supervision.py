"""Synthetic tool responses and isolated ledgers only; no live task/usage writes."""
import copy
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import dispatch_admission, native_limits as limits, native_supervision as supervision
from orchestrator.core import Ledger, Refusal, canonical, digest
from test_native_creation import NativeCreationFixture


def wait_result(status="idle", turn="completed", **fields):
    return {"timedOut": False, "polls": [{"schemaVersion": 1, "cursor": "fixture-epoch:2", "revision": 2,
        "changed": True, "thread": {"id": "native-task", "hostId": "local", "status": {"type": status}},
        "latestTurn": {"id": "turn-fixture", "status": turn, "error": None},
        "latestAssistantMessage": {"text": "PRIVATE-CONVERSATION-DO-NOT-RETAIN"},
        "latestToolMarker": {"arguments": "PRIVATE-TOOL-INPUT-DO-NOT-RETAIN"}, **fields}]}


def usage_result(short=10, long=20):
    now = time.time()
    return {"ordinaryUsageAllowed": True, "accountId": "account-fixture-private",
            "rateLimitsByLimitId": {"codex": {"limitId": "codex", "spendControlReached": False,
                "rateLimitReachedType": None, "primary": {"windowDurationMins": 300, "usedPercent": short, "resetsAt": now+18000},
                "secondary": {"windowDurationMins": 10080, "usedPercent": long, "resetsAt": now+604800}}},
            "rateLimitResetCredits": {"availableCount": 100, "secret": "DO-NOT-RETAIN-CREDITS"}}


class ProjectionTest(unittest.TestCase):
    def wait(self, result): return supervision.normalize_wait(result, time.time(), "local", "native-task")
    def usage(self, result): return limits.normalize(result, time.time())

    def test_activity_is_current_status_not_last_turn_outcome(self):
        for native, turn, expected in (("idle", "completed", "idle"), ("active", "completed", "running"),
                ("active", "failed", "running"), ("notLoaded", "completed", "unknown"),
                ("systemError", "completed", "unknown"), ("idle", "inProgress", "unknown")):
            with self.subTest(native=native, turn=turn): self.assertEqual(self.wait(wait_result(native, turn))["activity"], expected)

    def test_error_missing_unsupported_and_conflicting_status_never_become_idle(self):
        for result in ({"polls": []}, {"error": "private error"}, {**wait_result(), "errors": [{"error": "private"}]},
                       wait_result(schemaVersion=2), wait_result("futureStatus"),
                       wait_result(thread={"id": "native-task", "hostId": "local", "status": {"type": "idle", "activeFlags": ["waitingOnUserInput"]}})):
            self.assertEqual(self.wait(result)["activity"], "unknown")

    def test_exact_task_scope_and_single_poll(self):
        for result in (wait_result(thread={"id": "other", "hostId": "local"}),
                wait_result(thread={"id": "native-task", "hostId": "remote"}), {"polls": [*wait_result()["polls"], *wait_result()["polls"]]}):
            with self.assertRaises(Refusal): self.wait(result)

    def test_unchanged_cursor_still_retains_actual_observed_status_not_final_text(self):
        result = self.wait(wait_result(changed=False))
        self.assertEqual(result["activity"], "idle"); self.assertEqual(result["cursor"], "fixture-epoch:2")
        self.assertNotIn("PRIVATE", canonical(result))
        self.assertFalse(result["descendantsComplete"]); self.assertFalse(result["taskUsageAvailable"])

    def test_window_duration_not_slot_controls_mapping(self):
        result = usage_result(); bucket = result["rateLimitsByLimitId"]["codex"]
        bucket["primary"], bucket["secondary"] = bucket["secondary"], bucket["primary"]
        normalized = self.usage(result)
        self.assertTrue(normalized["complete"])
        self.assertEqual(normalized["windows"]["short"]["usedPercent"], 10)
        self.assertEqual(normalized["windows"]["long"]["usedPercent"], 20)

    def test_actual_weekly_only_shape_is_unknown_short_not_full_headroom(self):
        result = usage_result(); bucket = result["rateLimitsByLimitId"]["codex"]
        bucket["primary"] = bucket["secondary"]; bucket["secondary"] = None
        normalized = self.usage(result)
        self.assertFalse(normalized["complete"]); self.assertIsNone(normalized["windows"]["short"])
        self.assertEqual(normalized["windows"]["long"]["usedPercent"], 20)
        self.assertIn("short_window_unavailable", normalized["issues"])

    def test_explicit_map_prevents_legacy_or_other_model_fallback(self):
        result = usage_result(); result["rateLimits"] = copy.deepcopy(result["rateLimitsByLimitId"]["codex"])
        result["rateLimitsByLimitId"] = {"other-model": result["rateLimits"]}
        self.assertFalse(self.usage(result)["complete"])
        result["rateLimitsByLimitId"] = {"codex": None}
        self.assertFalse(self.usage(result)["complete"])
        for value in (None, {}):
            result["rateLimitsByLimitId"] = value
            self.assertTrue(self.usage(result)["complete"])

    def test_missing_values_permissions_and_exhaustion_are_not_zero(self):
        for mutate in (lambda r: r.update(ordinaryUsageAllowed=False), lambda r: r.pop("ordinaryUsageAllowed"),
                       lambda r: r.update(isError=True), lambda r: r.update(error="private error"),
                       lambda r: r.update(errors=[{"message": "private error"}]),
                       lambda r: r.pop("accountId"),
                       lambda r: r["rateLimitsByLimitId"]["codex"].update(spendControlReached=True),
                       lambda r: r["rateLimitsByLimitId"]["codex"].update(rateLimitReachedType="weekly"),
                       lambda r: r["rateLimitsByLimitId"]["codex"]["primary"].update(usedPercent=None),
                       lambda r: r["rateLimitsByLimitId"]["codex"]["primary"].update(resetsAt=1),
                       lambda r: r["rateLimitsByLimitId"]["codex"]["primary"].update(usedPercent=True)):
            result = usage_result(); mutate(result)
            self.assertFalse(self.usage(result)["complete"])

    def test_duplicate_or_unsupported_durations_are_explicit(self):
        for duration in (10080, 120, True, "300"):
            result = usage_result(); result["rateLimitsByLimitId"]["codex"]["primary"]["windowDurationMins"] = duration
            normalized = self.usage(result)
            self.assertFalse(normalized["complete"]); self.assertIsNone(normalized["windows"]["short"])

    def test_overrun_is_zero_remaining_but_negative_or_nonfinite_refuses(self):
        self.assertEqual(self.usage(usage_result(short=101))["windows"]["short"]["usedPercent"], 100)
        self.assertFalse(self.usage(usage_result(short=-1))["complete"])
        for value in (float("inf"), float("nan")):
            with self.assertRaises(Refusal): self.usage(usage_result(short=value))

    def test_no_credits_identity_or_transcripts_retained_and_input_bounded(self):
        normalized = self.usage(usage_result())
        self.assertNotIn("account-fixture-private", canonical(normalized))
        self.assertNotIn("DO-NOT-RETAIN", canonical(normalized)); self.assertFalse(normalized["tokenCountersAvailable"])
        with self.assertRaises(Refusal): self.usage({"padding": "x"*128001})
        with self.assertRaises(Refusal): self.wait({"padding": "x"*128001})


class NativeSupervisionTest(NativeCreationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        handoff = self.begin(); self.check(handoff); self.record(handoff)
        self.observer = supervision.NativeSupervision(self.fx.bridge)

    def observation(self, result=None, **fields):
        return {"id": "wait-fixture", "expectedHash": self.fx.claim()["nativeLifecycleHash"],
                "observedAt": time.time(), "result": result if result is not None else wait_result(), **fields}

    def observe(self, request=None): return self.observer.record(self.token, self.wid, request or self.observation())

    def account_request(self, result=None, **fields):
        return {"id": "limits-fixture", "expectedHash": self.observer.account_state(self.token)["currentHash"],
                "observedAt": time.time(), "result": result if result is not None else usage_result(), **fields}

    def account(self, request=None): return self.observer.account_record(self.token, request or self.account_request())

    def budget_check(self):
        with self.store.tx() as db:
            self.store.check_budget(db, self.store.get(db, "allocations", self.fx.binding["id"]))

    def test_read_only_plan_uses_exact_confirmed_task_and_scoped_cursor(self):
        before = self.logical(); plan = self.observer.plan(self.token, self.wid)
        self.assertEqual(before, self.logical()); self.assertEqual(plan["tool"], "wait_threads")
        self.assertEqual(plan["arguments"], {"targets": [{"hostId": "local", "threadId": "native-task"}], "timeoutMs": 0})
        self.observe(); plan = self.observer.plan(self.token, self.wid)
        self.assertEqual(plan["arguments"]["targets"][0]["afterCursor"], "fixture-epoch:2")
        self.assertFalse(plan["executionAuthorized"])

    def test_cli_task_and_account_roundtrip(self):
        plan = self.cli("native-task-plan", self.wid)
        self.assertEqual(plan.returncode, 0, plan.stderr)
        observation = self.observation(); observation["expectedHash"] = json.loads(plan.stdout)["expectedHash"]
        record = self.cli("native-task-record", self.wid, request=observation)
        self.assertEqual(record.returncode, 0, record.stderr)
        state = self.cli("native-task-state", self.wid)
        self.assertEqual(state.returncode, 0, state.stderr); self.assertEqual(json.loads(state.stdout)["activity"], "idle")
        result = self.cli("native-account-record", request=self.account_request())
        self.assertEqual(result.returncode, 0, result.stderr)
        limits_state = self.cli("native-account-state")
        self.assertEqual(limits_state.returncode, 0, limits_state.stderr)
        self.assertEqual(json.loads(limits_state.stdout)["status"], "headroom_observed")

    def test_idle_observation_keeps_all_capacity_and_evidence_axes(self):
        before = self.fx.worker(); resources = self.store.snapshot()["resources"]
        receipt = self.observe(); worker = self.fx.worker()
        self.assertEqual(worker["status"], "running"); self.assertEqual(worker["nativeActivity"]["activity"], "idle")
        self.assertEqual(worker["evidence"], before["evidence"])
        self.assertEqual(self.store.snapshot()["resources"], resources)
        self.assertFalse(receipt["ownershipReleased"]); self.assertFalse(receipt["executionAuthorized"])
        retained = self.ledger.document(receipt["recordHash"])
        self.assertEqual(retained["request"]["evidenceHash"], digest(retained["source"]))
        self.assertNotIn("PRIVATE", canonical(retained))

    def test_not_loaded_and_latest_completed_remain_unknown_and_keep_ownership(self):
        self.observe(self.observation(wait_result("notLoaded")))
        self.assertEqual(self.observer.state(self.token, self.wid)["activity"], "unknown")
        self.assertEqual(self.fx.claim()["status"], "running")  # Owned, not active.
        self.assertFalse(self.observer.state(self.token, self.wid)["descendantsComplete"])

    def test_late_observation_after_pause_never_resumes(self):
        request = self.observation(wait_result("active")); self.fx.fx.fx.command("pause")
        self.observe(request)
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(self.fx.worker()["nativeActivity"]["activity"], "running")

    def test_interrupted_local_attachment_replays_shared_result(self):
        request = self.observation()
        with patch.object(self.observer.lifecycle, "attach_in", side_effect=RuntimeError("fixture interruption")):
            with self.assertRaises(RuntimeError): self.observe(request)
        self.assertNotEqual(self.fx.worker()["nativeLifecycleHash"], self.fx.claim()["nativeLifecycleHash"])
        self.fx.fx.fx.command("pause")
        self.observe(request)
        self.assertEqual(self.fx.worker()["nativeLifecycleHash"], self.fx.claim()["nativeLifecycleHash"])
        before = self.logical(); self.observe(request); self.assertEqual(before, self.logical())

    def test_historical_replay_does_not_overwrite_newer_activity(self):
        one = self.observation(); first = self.observe(one)
        self.observe(self.observation(wait_result("active"), id="newer"))
        before = self.logical(); replay = self.observe(one)
        self.assertEqual(replay["recordHash"], first["recordHash"])
        self.assertNotEqual(replay["currentHash"], first["recordHash"])
        self.assertEqual(before, self.logical())
        with self.assertRaises(Refusal): self.observe({**one, "result": wait_result("notLoaded")})

    def test_stale_future_foreign_and_conflicting_results_refuse(self):
        before = self.logical()
        for request in (self.observation(observedAt=time.time()-100), self.observation(observedAt=time.time()+60),
                        self.observation(expectedHash="a"*64), self.observation(wait_result(thread={"id": "other", "hostId": "local"})),
                        {**self.observation(), "activity": "idle"}):
            with self.assertRaises(Refusal): self.observe(request)
            self.assertEqual(before, self.logical())

    def test_concurrent_observers_only_one_new_version(self):
        requests = [self.observation(id="one"), self.observation(id="two")]
        def record(request):
            try: return self.observe(request)
            except Refusal: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(record, requests))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_state_expiry_changes_display_not_retained_time_or_identity(self):
        self.observe(); before = self.logical()
        with patch.object(self.store, "clock", return_value=time.time()+61):
            state = self.observer.state(self.token, self.wid)
            self.assertFalse(state["fresh"]); self.assertEqual(state["activity"], "unknown")
        self.assertEqual(before, self.logical())

    def test_pending_binding_is_never_a_task_poll_target(self):
        with self.store.tx() as db:
            claim = self.store.get(db, "claims", self.wid)
            native = self.observer.lifecycle.record_in(db, claim["nativeLifecycleHash"], self.ledger.document(self.fx.worker()["dispatchAdmission"]["intentHash"]))
        # Exercise the adapter's pending guard before any call is emitted.
        state = copy.deepcopy(native["state"]); state["creation"].update(outcome="pending", threadId=None, clientThreadId="pending")
        with patch.object(self.observer.lifecycle, "state_in", return_value=(claim, native, state)):
            with self.assertRaisesRegex(Refusal, "pending client IDs"): self.observer.plan(self.token, self.wid)

    def test_native_account_updates_limits_but_not_phase_tokens_or_claims(self):
        before = self.store.snapshot(); receipt = self.account(); after = self.store.snapshot()
        self.assertEqual(before["claims"], after["claims"]); self.assertEqual(before["resources"], after["resources"])
        self.assertEqual(before["allocations"], after["allocations"])
        self.assertEqual(receipt["current"]["windows"]["short"]["remainingPercent"], 90)
        self.assertFalse(receipt["current"]["phaseTokenUsageUpdated"])
        self.budget_check()
        with self.store.tx() as db: serialized = canonical(limits.current_in(self.store, db))
        self.assertNotIn("account-fixture-private", serialized); self.assertNotIn("DO-NOT-RETAIN", serialized)

    def test_new_incomplete_native_limits_override_older_healthy_evidence(self):
        self.account(); self.budget_check()
        result = usage_result(); result["rateLimitsByLimitId"]["codex"]["primary"] = None
        receipt = self.account(self.account_request(result, id="missing-window"))
        self.assertEqual(receipt["current"]["status"], "blocked")
        with self.assertRaisesRegex(Refusal, "incomplete or changed"): self.budget_check()
        # Even the pre-journal budget read must not see older healthy limits.
        with patch.object(limits, "enforce"):
            with self.assertRaisesRegex(Refusal, "Account usage is unknown"): self.budget_check()
        self.account(self.account_request(id="healthy-again")); self.budget_check()

    def test_exhaustion_permissions_and_changed_identity_block_without_resetting_phase(self):
        before = self.store.snapshot()["allocations"]
        self.account(self.account_request(usage_result(short=99)))
        with self.assertRaisesRegex(Refusal, "headroom"): self.budget_check()
        changed = usage_result(); changed["accountId"] = "different-account"
        receipt = self.account(self.account_request(changed, id="changed-account"))
        self.assertIn("account_identity_changed", receipt["current"]["issues"])
        with self.assertRaises(Refusal): self.budget_check()
        self.assertEqual(self.store.snapshot()["allocations"], before)

    def test_account_replay_is_historical_without_refresh_or_restoring_old_health(self):
        one = self.account_request(); first = self.account(one)
        failed = {"ordinaryUsageAllowed": False}
        self.account(self.account_request(failed, id="unavailable")); before = self.logical()
        replay = self.account(one)
        self.assertTrue(replay["historical"]); self.assertEqual(replay["recordHash"], first["recordHash"])
        self.assertEqual(replay["current"]["status"], "blocked"); self.assertEqual(before, self.logical())
        with self.assertRaises(Refusal): self.account({**one, "result": usage_result(short=40)})

    def test_account_legacy_update_or_pointer_loss_cannot_bypass_native_fence(self):
        self.account()
        now = time.time()
        with self.assertRaisesRegex(Refusal, "legacy updates"):
            self.store.observe_account({"observedAt": now, "evidenceHash": "a"*64,
                "windows": {k: {"usedPercent": 0, "resetsAt": now+3600} for k in ("short", "long")}})
        with self.store.tx() as db:
            meta = self.store.get(db, "meta", 1); meta.pop("nativeAccountHash"); self.store.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "pointer missing"): self.budget_check()
        with self.assertRaises(Refusal): self.observer.account_state(self.token)

    def test_native_account_expiry_and_reset_stay_visible_without_refresh(self):
        self.account(); before = self.logical()
        with patch.object(self.store, "clock", return_value=time.time()+61):
            self.assertIn("observation_stale_or_future", self.observer.account_state(self.token)["issues"])
            with self.assertRaises(Refusal): self.budget_check()
        self.assertEqual(before, self.logical())

    def test_stale_or_foreign_expected_account_hash_does_not_write(self):
        before = self.logical()
        for request in (self.account_request(observedAt=time.time()-61), self.account_request(observedAt=time.time()+1),
                        self.account_request(expectedHash="a"*64), {**self.account_request(), "confirmed": True}):
            with self.assertRaises(Refusal): self.account(request)
            self.assertEqual(before, self.logical())

    def test_account_observation_after_pause_preserves_stop_and_all_owners(self):
        self.fx.fx.fx.command("pause"); workers = self.ledger.snapshot()["workers"]
        self.account(); self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(self.ledger.snapshot()["workers"], workers)

    def test_account_atomic_failure_and_retry(self):
        request = self.account_request(); before = self.logical()
        with patch.object(self.store, "event", side_effect=RuntimeError("fixture commit failure")):
            with self.assertRaises(RuntimeError): self.account(request)
        self.assertEqual(before, self.logical()); self.account(request); self.budget_check()

    def test_concurrent_account_updates_have_one_winner(self):
        requests = [self.account_request(id="one"), self.account_request(id="two")]
        def record(request):
            try: return self.account(request)
            except Refusal: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(record, requests))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_wrong_controller_and_no_selected_workspace_have_no_side_effects(self):
        before = self.logical()
        with self.assertRaises(Refusal): self.observer.plan("wrong", self.wid)
        with self.assertRaises(Refusal): self.observer.record("wrong", self.wid, self.observation())
        with self.assertRaises(Refusal): self.observer.account_record("wrong", self.account_request())
        with self.assertRaises(Refusal): self.observer.account_state("wrong")
        for command in ("native-task-plan", "native-task-state", "native-account-state"):
            result = self.cli(command, *([self.wid] if command.startswith("native-task-") else []), select=False)
            self.assertNotEqual(result.returncode, 0); self.assertIn("explicit registered workspace", result.stderr)
        self.assertEqual(before, self.logical())

    def test_account_projection_drift_is_blocked_in_status_and_admission(self):
        self.account()
        with self.store.tx() as db:
            meta = self.store.get(db, "meta", 1); meta["account"]["windows"]["short"]["usedPercent"] = 0
            self.store.put(db, "meta", 1, meta)
        self.assertIn("account_projection_diverged", self.observer.account_state(self.token)["issues"])
        with self.assertRaisesRegex(Refusal, "diverged"): self.budget_check()

    def test_native_account_never_supplies_missing_phase_counters(self):
        with self.store.tx() as db:
            allocation = self.store.get(db, "allocations", self.fx.binding["id"])
            allocation["usage"] = None; self.store.put(db, "allocations", allocation["id"], allocation)
        self.account()
        with self.assertRaisesRegex(Refusal, "usage coverage"): self.budget_check()

    def test_account_pointer_and_record_tampering_refuse(self):
        self.account()
        with self.store.tx() as db:
            current = limits.current_in(self.store, db); key = digest(current)
            current["projection"]["complete"] = False
            db.execute("UPDATE native_account_records SET data=? WHERE hash=?", (canonical(current), key))
        with self.assertRaisesRegex(Refusal, "integrity changed"): self.observer.account_state(self.token)
        with self.assertRaises(Refusal): self.budget_check()

    def test_native_source_binding_cannot_claim_another_activity(self):
        source = supervision.normalize_wait(wait_result("notLoaded"), time.time(), "local", "native-task")
        observation = {"id": "bad-source", "expectedHash": self.fx.claim()["nativeLifecycleHash"],
            "outcome": "confirmed", "hostId": "local", "threadId": "native-task", "clientThreadId": None,
            "observedAt": source["observedAt"], "activity": "idle", "evidenceHash": digest(source)}
        before = self.logical()
        with self.assertRaisesRegex(Refusal, "provenance"):
            self.observer.lifecycle.observe(self.token, self.wid, observation, source=source)
        self.assertEqual(before, self.logical())

    def test_account_limits_are_shared_across_workspaces_but_requests_are_scoped(self):
        one = self.account()
        ledger = Ledger(self.fx.registry.root.parent / "second-observer")
        ledger.initialize({"schemaVersion": 1, "brainId": "brain-b", "repositories": [
            {"id": "a", "path": str(self.repo), "projectId": "project-b", "ref": "origin/main",
             "mergePolicy": "manual", "policyProfile": "standard"}]})
        self.fx.registry.register("b", "Project B", ledger.root)
        token = ledger.acquire("brain-b:fixture")
        other = dispatch_admission.DispatchAdmission(self.fx.registry, "b", self.store)
        second = supervision.NativeSupervision(other)
        self.assertEqual(second.account_state(token)["currentHash"], one["recordHash"])
        request = self.account_request(usage_result(long=99))
        two = second.account_record(token, request)  # Same textual request ID in a different workspace.
        self.assertNotEqual(two["recordHash"], one["recordHash"])
        self.assertEqual(self.observer.account_state(self.token)["status"], "blocked")
        with self.assertRaises(Refusal): self.budget_check()
        with self.assertRaises(Refusal): second.account_state(self.token)


class NativeSupervisionCreationGateTest(NativeCreationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp(); self.observer = supervision.NativeSupervision(self.fx.bridge)

    def observe_limits(self, result, key=None):
        return self.observer.account_record(self.token, {"id": "limits-"+str(time.time_ns()),
            "expectedHash": key, "observedAt": time.time(), "result": result})

    def test_missing_limits_fence_the_existing_creation_boundary(self):
        self.observe_limits({"ordinaryUsageAllowed": False})
        with self.assertRaisesRegex(Refusal, "incomplete or changed"): self.begin()
        self.assertEqual(self.fx.worker()["status"], "reserved")
        self.assertEqual(self.fx.claim()["status"], "reserved")

    def test_exhaustion_between_handoff_and_send_check_preserves_inflight_owner(self):
        healthy = self.observe_limits(usage_result())
        handoff = self.begin()
        self.observe_limits(usage_result(short=100), healthy["recordHash"])
        with self.assertRaisesRegex(Refusal, "headroom"): self.check(handoff)
        self.assertEqual(self.fx.claim()["status"], "starting")
        self.assertIsNone(self.fx.worker().get("nativeHandoffCheckHash"))


if __name__ == "__main__": unittest.main()
