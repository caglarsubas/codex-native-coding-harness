"""Disposable metadata fixtures; no real host, turn, recovery or pilot claim."""
import copy
import time
import unittest
from unittest.mock import patch

from orchestrator import native_policy_evidence as evidence, standard
from orchestrator.app_server_wake import AppServerWake
from orchestrator.core import Refusal, canonical, digest
from orchestrator.native_read_client import ReadProxy
from orchestrator.workspaces import fingerprint
import test_standard_native_observation as fixtures
from test_app_server_wake import BRAIN, PROJECT, FakeProxy, FakeThread
import test_app_server_wake as wake_fixtures

CONTRACT = {"protocol": evidence.PROTOCOL, "sourceCommit": "a" * 40, "sourceTree": "b" * 40}


def response(brain_id=BRAIN, cwd="/fixture/brain"):
    return {"version": 1, "threadId": brain_id, "policy": {
        "scope": "loadedThreadDefaults", "cwd": cwd, "model": "gpt-6-astra",
        "approvalPolicy": "on-request", "approvalsReviewer": "user",
        "sandbox": {"type": "workspaceWrite", "writableRoots": [], "networkAccess": False,
                    "excludeTmpdirEnvVar": False, "excludeSlashTmp": False},
        "codeModeOffEnforced": True, "effectiveToolMode": "direct"}}


class ContractTest(unittest.TestCase):
    def test_exact_native_response_not_request_echo(self):
        self.assertTrue(evidence.matches(evidence.reported(response(), BRAIN, "/fixture/brain")))
        for key, value in (("codeModeOffEnforced", False), ("effectiveToolMode", None),
                           ("approvalPolicy", "never"), ("approvalsReviewer", "auto_review")):
            item = response(); item["policy"][key] = value
            self.assertFalse(evidence.matches(evidence.reported(item, BRAIN, "/fixture/brain")))

    def test_missing_runtime_stays_unknown(self):
        item = response(); item["policy"] = None
        self.assertIsNone(evidence.reported(item, BRAIN, "/fixture/brain"))
        self.assertFalse(evidence.matches(None))

    def test_foreign_version_scope_identity_and_opaque_fields_refuse(self):
        for edit in (lambda r: r.update(version=True), lambda r: r.update(version=2),
                     lambda r: r.update(threadId="foreign"), lambda r: r.update(private="SECRET"),
                     lambda r: r["policy"].update(scope="activeStep"),
                     lambda r: r["policy"].update(cwd="/elsewhere"),
                     lambda r: r["policy"].update(codeModeOffEnforced=1),
                     lambda r: r["policy"].update(private="SECRET"),
                     lambda r: r["policy"]["sandbox"].update(networkAccess=True),
                     lambda r: r["policy"]["sandbox"].update(writableRoots=["/elsewhere"]),
                     lambda r: r["policy"].pop("codeModeOffEnforced")):
            item = response(); edit(item)
            with self.subTest(item=item), self.assertRaises(Refusal):
                evidence.reported(item, BRAIN, "/fixture/brain")

    def test_contract_is_closed_and_not_a_boolean_attestation_switch(self):
        self.assertEqual(evidence.validate_contract(CONTRACT), CONTRACT)
        for value in (None, {**CONTRACT, "policyVerified": True}, {**CONTRACT, "sourceTree": "bad"},
                      {**CONTRACT, "protocol": "config_echo"}):
            with self.assertRaises(Refusal): evidence.validate_contract(value)

    def test_base_read_client_has_no_mutation_escape(self):
        client = ReadProxy({})
        with patch.object(client, "_rpc", return_value=None) as rpc:
            client.call(evidence.METHOD, {"threadId": BRAIN})
            rpc.assert_called_once_with(evidence.METHOD, {"threadId": BRAIN})
            for method, params in (("thread/resume", {"threadId": BRAIN}),
                                   (evidence.METHOD, {"threadId": BRAIN, "load": True})):
                with self.assertRaises(Refusal): client.call(method, params)
            self.assertEqual(rpc.call_count, 1)

    def test_policy_proxy_refuses_every_foreign_target_or_write_before_rpc(self):
        client = evidence.PolicyReadProxy({}, PROJECT, BRAIN)
        with patch.object(client, "_rpc") as rpc:
            for method, params in ((evidence.METHOD, {"threadId": "foreign"}),
                                   ("thread/resume", {"threadId": BRAIN}),
                                   ("project/read", {"projectId": "foreign"}),
                                   ("thread/list", {"ancestorThreadId": BRAIN}),
                                   ("thread/backgroundTerminals/list", {"threadId": BRAIN})):
                with self.assertRaises(Refusal): client.call(method, params)
            rpc.assert_not_called()


class InspectionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.StandardNativeObservationTest(methodName="runTest")
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.ledger, self.registry = self.fixture.ledger, self.fixture.registry
        self.binding = copy.deepcopy(self.fixture.binding)
        self.brain = self.fixture.brain_id
        self.binding["endpoint"]["sha256"] = "c" * 64
        self.binding["brains"][self.brain]["policyEvidence"] = CONTRACT.copy()
        self.host = AppServerWake(self.binding, self.ledger)
        self.fake = self.fixture.fake
        self.fake.threads[self.brain]["status"]["activeFlags"] = []
        self.raw = response(self.brain, str(self.fixture.repo))
        self.policy_calls = []
        def rpc(method, params):
            self.policy_calls.append((method, params))
            self.assertEqual(method, evidence.METHOD)
            self.assertEqual(params, {"threadId": self.brain})
            return copy.deepcopy(self.raw)
        self.fake._rpc = rpc
        for item in (patch.object(evidence, "PolicyReadProxy", return_value=self.fake),
                     patch("orchestrator.native_read_client.validate_endpoint")):
            item.start(); self.addCleanup(item.stop)

    def fingerprint(self):
        with standard.read_db(self.ledger.db) as db: return fingerprint(db)

    def test_diagnostic_matches_without_writes_or_safety_claim(self):
        before = self.fingerprint()
        result = evidence.inspect(self.registry, self.ledger, self.host)
        self.assertEqual(result["status"], "matching")
        self.assertTrue(result["policyVerified"])
        self.assertEqual(result["boundary"], evidence.BOUNDARY)
        self.assertFalse(any(result["boundary"].values()))
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual([m for m, _ in self.fake.calls], ["project/read", "thread/read"] * 2)
        self.assertEqual(len(self.policy_calls), 2)
        self.assertNotIn(str(self.fixture.repo), canonical(result))
        self.assertNotIn("gpt-6-astra", canonical(result))

    def test_unloaded_never_loads_and_old_binding_never_probes(self):
        self.raw["policy"] = None
        self.fake.threads[self.brain]["status"] = {"type": "notLoaded"}
        result = evidence.inspect(self.registry, self.ledger, self.host)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["policyVerified"])
        self.policy_calls.clear(); self.fake.calls.clear()
        del self.binding["brains"][self.brain]["policyEvidence"]
        self.assertEqual(evidence.inspect(self.registry, self.ledger, self.host)["status"], "unsupported")
        self.assertEqual(self.fake.calls, []); self.assertEqual(self.policy_calls, [])

    def test_raw_mismatch_is_not_verified_and_no_private_error_leaks(self):
        self.raw["policy"]["codeModeOffEnforced"] = False
        self.raw["policy"]["effectiveToolMode"] = None
        self.assertEqual(self.host.check_policy(self.registry)["status"], "mismatch")
        self.fake._rpc = lambda *args: (_ for _ in ()).throw(Refusal("PRIVATE_ERROR_SECRET"))
        result = self.host.check_policy(self.registry)
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("PRIVATE_ERROR_SECRET", canonical(result))

    def test_pause_race_host_drift_or_changed_sample_refuses(self):
        def race(*args):
            self.fake.callback = None
            with self.ledger.tx() as db:
                meta = self.ledger.get(db, "meta", 1)
                meta["standardRun"]["status"] = "stopping"
                self.ledger.put(db, "meta", 1, meta)
        self.fake.callback = race
        with self.assertRaisesRegex(Refusal, "changed"): evidence.inspect(self.registry, self.ledger, self.host)
        samples = iter([self.raw, {**self.raw, "policy": None}])
        self.fake._rpc = lambda *args: copy.deepcopy(next(samples))
        with self.assertRaises(Refusal): evidence.inspect(self.registry, self.ledger, self.host)

    def test_foreign_project_and_closed_host_refuse(self):
        self.fake.threads[self.brain]["projectId"] = "foreign"
        with self.assertRaises(Refusal): evidence.inspect(self.registry, self.ledger, self.host)
        self.assertFalse(self.policy_calls)
        self.host.close()
        with self.assertRaises(Refusal): evidence.inspect(self.registry, self.ledger, self.host)

    def test_polling_reads_only_cached_original_time_and_never_qualifies_resume(self):
        self.assertEqual(self.host.policy_status(self.brain, self.fixture.run_id, 1)["status"], "unchecked")
        before = self.fingerprint()
        result = self.host.check_policy(self.registry)
        count = len(self.policy_calls)
        cached = self.host.policy_status(self.brain, result["runId"], result["revision"])
        self.assertEqual(cached, result)
        with patch("orchestrator.app_server_wake.time.time", return_value=result["checkedAt"] + 301):
            stale = self.host.policy_status(self.brain, result["runId"], result["revision"])
        self.assertEqual(stale["status"], "stale")
        self.assertFalse(stale["policyVerified"])
        self.assertEqual(stale["checkedAt"], result["checkedAt"])
        self.assertEqual(len(self.policy_calls), count)
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(self.host.policy_status(self.brain, "other", result["revision"])["status"], "stale")


class FutureWakeTest(unittest.TestCase):
    def setUp(self):
        self.fixture = wake_fixtures.WakeTest(methodName="runTest")
        self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        self.wake = self.fixture.wake
        self.fixture.binding["brains"][BRAIN]["policyEvidence"] = CONTRACT.copy()
        self.fixture.binding["endpoint"]["sha256"] = "c" * 64
        self.raw = response()
        outer = self
        class SupportedProxy(FakeProxy):
            def _rpc(self, method, params):
                if method == evidence.METHOD:
                    self.calls.append((method, params))
                    return copy.deepcopy(outer.raw)
                return super()._rpc(method, params)
        for item in (patch("orchestrator.app_server_wake.WakeProxy", SupportedProxy),
                     patch("orchestrator.app_server_wake.validate_endpoint"),
                     patch("orchestrator.app_server_wake.threading.Thread", FakeThread)):
            item.start(); self.addCleanup(item.stop)

    def test_new_owned_delivery_retains_actual_proof_but_not_in_resume_echo(self):
        self.assertEqual(self.wake.send(BRAIN, "pointer", "control")["status"], "accepted")
        note = self.wake.ledger.command["notification"]
        self.assertIsNone(note["nativeResumeProfile"]["reported"]["codeMode"])
        item = note["nativeEffectivePolicy"]
        self.assertTrue(evidence.valid_retained(item, {**note, "status": "accepted", "nativeDelivery": "owned_turn_start", "hostBindingHash": digest(self.fixture.binding),
             "attemptedAt": time.time()}, note["nativeResumeProfile"], "control", BRAIN))
        self.assertEqual([m for m, _ in FakeProxy.instances[-1].calls],
                         ["thread/read", "thread/resume", evidence.METHOD, evidence.METHOD, "turn/start"])

    def test_failed_policy_read_cannot_start_turn_or_add_retry_permission(self):
        for value in (None, False):
            self.raw = response()
            if value is None: self.raw["policy"] = None
            else: self.raw["policy"]["codeModeOffEnforced"] = False
            result = self.wake.send(BRAIN, "pointer", "control")
            self.assertEqual(result["status"], "unavailable")
            self.assertFalse(result["nativeFailure"]["turnStartAttempted"])
            self.assertNotIn("turn/start", [m for m, _ in FakeProxy.instances[-1].calls])
            # A distinct fixture per case; never reissue a live one-shot command.
            self.wake.ledger.command["notification"].pop("nativeResumeProfile", None)

    def test_endpoint_drift_after_policy_read_refuses_before_turn_start(self):
        with patch("orchestrator.app_server_wake.validate_endpoint", side_effect=Refusal("changed")):
            result = self.wake.send(BRAIN, "pointer", "control")
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["nativeFailure"]["turnStartAttempted"])
        self.assertNotIn("turn/start", [m for m, _ in FakeProxy.instances[-1].calls])


if __name__ == "__main__":
    unittest.main()
