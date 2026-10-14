"""Policy verification uses retained metadata, never synthetic runtime proof."""
import copy
import math
import time
import unittest

from orchestrator import standard, standard_native_policy as policy
from orchestrator.core import Refusal, canonical, digest
from orchestrator.workspaces import fingerprint
import test_standard as fixtures


class NativePolicyTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.StandardTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.control()
        self.fixture.call("receive")
        self.ledger = self.fixture.ledger
        self.run = standard.read(self.ledger)["run"]
        self.command = next(c for c in self.ledger.snapshot()["commands"] if c["kind"] == "standard_play")

    def bind(self, **changes):
        profile = {"version": 1, "commandId": self.command["id"], "brainId": self.run["brainId"],
            "nativeTurnId": "turn", "bindingHash": "a" * 64, "observedAt": time.time() - 10,
            "resumeAcknowledged": True,
            "requested": {"sandbox": "workspace-write", "approvalPolicy": "on-request", "codeMode": False},
            "reported": {"sandbox": "workspaceWrite", "approvalPolicy": "on-request", "approvalsReviewer": "user", "codeMode": None}}
        profile.update(changes)
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.command["id"])
            command["notification"] = {"brainId": self.run["brainId"], "hostRunId": self.run["id"],
                "hostBindingHash": "a" * 64, "nativeTurnId": "turn", "attemptedAt": time.time(),
                "status": "accepted", "nativeDelivery": "owned_turn_start", "nativeResumeProfile": profile,
                "nativeTurnStatus": "completed", "nativeThreadObservation": {"streamStatus": "closed"}}
            self.ledger.put(db, "commands", command["id"], command)
        return profile

    def state_hash(self):
        with standard.read_db(self.ledger.db) as db:
            return fingerprint(db)

    def test_missing_effective_code_mode_blocks_claim_without_changing_authority_or_counters(self):
        profile = self.bind()
        with standard.read_db(self.ledger.db) as db: before = fingerprint(db)
        result = standard.read(self.ledger)["nativePolicyVerification"]
        self.assertEqual(result["observedAt"], profile["observedAt"])
        self.assertEqual(result["sandbox"], "reported_matching")
        self.assertTrue(result["configurationMatches"])
        self.assertFalse(result["policyVerified"])
        self.assertEqual(result["codeMode"], "unverified")
        self.assertIn(policy.BLOCKER, standard.read(self.ledger)["blockers"])
        with self.assertRaises(Refusal): self.fixture.claim()
        with standard.read_db(self.ledger.db) as db: self.assertEqual(fingerprint(db), before)
        self.assertEqual(standard.read(self.ledger)["run"], self.run)

    def test_prepared_task_cannot_issue_after_policy_gap_appears(self):
        self.fixture.claim()
        self.bind()
        before = self.state_hash()
        with self.assertRaises(Refusal): self.fixture.call("issue", taskId="task-1")
        self.assertEqual(self.state_hash(), before)
        task = standard.read(self.ledger)["run"]["tasks"][0]
        self.assertFalse(task["effectIssued"])

    def test_resume_is_fenced_but_receipt_checkpoint_and_reads_remain_available(self):
        self.bind()
        self.fixture.call("receive")
        self.fixture.call("checkpoint", outcome="paused", summary="Policy is unverified; preserve unknown terminals",
                          brainObservedTokens=None, reasonCodes=["other_policy"])
        run = standard.read(self.ledger)["run"]
        before = self.state_hash()
        with self.assertRaises(Refusal): self.fixture.control("resume")
        self.assertEqual(self.state_hash(), before)
        self.assertEqual(run["expiresAt"], self.run["expiresAt"])
        self.assertEqual(run["brainObservedTokens"], self.run["brainObservedTokens"])
        self.assertEqual(run["tasks"], [])
        self.assertEqual(self.ledger.snapshot()["commands"][0]["status"], "completed")

    def test_acknowledgement_unsolicited_fields_and_config_false_never_attest_off(self):
        for code_mode in (False, True, None, 0, "false", {}):
            with self.subTest(value=code_mode):
                self.bind(reported={"sandbox": "workspaceWrite", "approvalPolicy": "on-request",
                                   "approvalsReviewer": "user", "codeMode": code_mode},
                          effectiveToolMode="direct", effectiveConfig={"features": {"code_mode": False}},
                          policyVerified=True, toolNames=["exec_command"])
                view = standard.read(self.ledger)["nativePolicyVerification"]
                self.assertEqual(view["codeMode"], "unverified")
                self.assertFalse(view["policyVerified"])
                self.assertNotIn("toolNames", view)

    def test_foreign_incomplete_or_malformed_profile_cannot_clear_gap_or_leak_private_fields(self):
        for changes in ({"brainId": "foreign"}, {"commandId": "other"}, {"nativeTurnId": "other"},
                        {"bindingHash": "b" * 64}, {"version": 2}, {"resumeAcknowledged": False},
                        {"reported": "PRIVATE"}, {"observedAt": "not-a-time"},
                        {"requested": {"sandbox": "workspace-write", "approvalPolicy": "on-request", "codeMode": 0}}):
            with self.subTest(changes=changes):
                self.bind(**changes)
                view = standard.read(self.ledger)["nativePolicyVerification"]
                self.assertFalse(view["policyVerified"])
                self.assertNotIn("PRIVATE", canonical(view))

    def test_foreign_run_and_non_owned_transport_keep_existing_contract(self):
        self.assertIsNone(standard.read(self.ledger).get("nativePolicyVerification"))
        self.bind()
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.command["id"])
            command["notification"]["hostRunId"] = "other-run"
            self.ledger.put(db, "commands", command["id"], command)
        self.assertIsNone(standard.read(self.ledger)["nativePolicyVerification"])
        self.fixture.claim()

    def test_later_unavailable_handoff_cannot_fall_back_to_older_profile(self):
        self.bind()
        with self.ledger.tx() as db:
            command = copy.deepcopy(self.ledger.get(db, "commands", self.command["id"]))
            command["id"] = "newer-command"
            command["notification"]["attemptedAt"] += 1
            command["notification"].pop("nativeResumeProfile")
            self.ledger.put(db, "commands", command["id"], command)
        view = standard.read(self.ledger)["nativePolicyVerification"]
        self.assertEqual(view["commandId"], "newer-command")
        self.assertFalse(view["resumeAcknowledged"])
        self.assertIsNone(view["observedAt"])
        self.assertFalse(view["policyVerified"])

    def bind_supported(self):
        from orchestrator.native_policy_evidence import collect
        import test_native_policy_evidence as fixtures
        from types import SimpleNamespace
        self.bind()
        binding = {"endpoint": {"sha256": "c" * 64}, "brains": {self.run["brainId"]: {
            "cwd": "/fixture/brain", "policyEvidence": fixtures.CONTRACT}}}
        binding_hash = digest(binding)
        item = collect(SimpleNamespace(_rpc=lambda *args: fixtures.response(self.run["brainId"])),
                       binding, self.run["brainId"], self.command["id"])
        item["nativeTurnId"] = "turn"
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.command["id"])
            note = command["notification"]
            note["hostBindingHash"] = binding_hash
            note["nativeResumeProfile"]["bindingHash"] = binding_hash
            note["nativePolicyContract"] = fixtures.CONTRACT.copy()
            note["nativePolicyExecutableHash"] = "c" * 64
            note["nativeEffectivePolicy"] = item
            self.ledger.put(db, "commands", command["id"], command)
        return item

    def test_future_supported_capture_qualifies_only_policy_prerequisite(self):
        self.bind_supported()
        result = standard.read(self.ledger)["nativePolicyVerification"]
        self.assertTrue(result["policyVerified"])
        self.assertEqual(result["codeMode"], "native_reported_off")
        self.assertIsNone(result["blocker"])
        self.assertNotIn(policy.BLOCKER, standard.read(self.ledger)["blockers"])
        self.assertEqual(standard.read(self.ledger)["run"], self.run)
        self.assertNotIn("terminalSafetyVerified", result)

    def test_changed_or_unbound_supported_capture_cannot_clear_gate(self):
        for edit in (lambda e: e.update(version=True), lambda e: e.update(sourceTree="d" * 40),
                     lambda e: e.update(executableHash="d" * 64), lambda e: e.update(brainId="other"),
                     lambda e: e.update(commandId="other"), lambda e: e.update(nativeTurnId="other"),
                     lambda e: e.update(bindingHash="d" * 64), lambda e: e.update(observedAt=float("nan")),
                     lambda e: e["reported"].update(codeModeOffEnforced=1),
                     lambda e: e["reported"].update(scope="activeStep"),
                     lambda e: e["reported"].update(effectiveToolMode=None),
                     lambda e: e.update(policyVerified=True)):
            self.bind_supported()
            with self.ledger.tx() as db:
                command = self.ledger.get(db, "commands", self.command["id"])
                edit(command["notification"]["nativeEffectivePolicy"])
                # JSON serialization rejects non-finite values, so test its
                # projection directly rather than inserting invalid JSON.
                if not math.isfinite(command["notification"]["nativeEffectivePolicy"]["observedAt"]):
                    from orchestrator.native_policy_evidence import valid_retained
                    self.assertFalse(valid_retained(command["notification"]["nativeEffectivePolicy"],
                         command["notification"], command["notification"]["nativeResumeProfile"],
                         command["id"], self.run["brainId"]))
                    continue
                self.ledger.put(db, "commands", command["id"], command)
            self.assertFalse(standard.read(self.ledger)["nativePolicyVerification"]["policyVerified"])
