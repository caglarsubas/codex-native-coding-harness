"""Sign-in is separate from transport, policy, model access and phase authority."""
import copy
import json
import unittest
from unittest.mock import patch

from orchestrator import native_auth_readiness as auth, native_policy_evidence as policy
from orchestrator.app_server_wake import AppServerWake
from orchestrator.core import Refusal, canonical
from orchestrator.native_read_client import ReadProxy
import test_app_server_wake as wakes
import test_native_policy_evidence as policies
import test_public_native_tasks as tasks


class ReportTest(unittest.TestCase):
    def test_authenticated_or_auth_not_required_are_not_model_entitlement(self):
        for account, required in (({'type': 'apiKey'}, True),
                                  ({'type': 'chatgpt', 'email': 'PRIVATE', 'planType': 'pro'}, True),
                                  (None, False)):
            with self.subTest(account=account):
                raw = {'account': account, 'requiresOpenaiAuth': required}
                proxy = unittest.mock.Mock()
                proxy._rpc.return_value = raw
                report = auth.require_ready(proxy)
                self.assertTrue(report['ready'])
                self.assertFalse(report['modelAccessVerified'])
                self.assertFalse(report['executionAuthorized'])
                self.assertFalse(report['terminalSafetyVerified'])
                self.assertFalse(report['usageMeasured'])
                self.assertNotIn('PRIVATE', canonical(report))
                self.assertEqual(proxy._rpc.call_args_list,
                                 [unittest.mock.call('account/read', {'refreshToken': False})] * 2)

    def test_missing_auth_is_observed_and_refuses_without_login(self):
        proxy = unittest.mock.Mock()
        proxy._rpc.return_value = {'account': None, 'requiresOpenaiAuth': True}
        self.assertEqual(auth.inspect(proxy)['status'], 'authentication_required')
        with self.assertRaisesRegex(Refusal, 'Sign in'): auth.require_ready(proxy)
        self.assertTrue(all(call.args[0] == 'account/read' for call in proxy._rpc.call_args_list))

    def test_missing_malformed_new_protocol_or_oversized_response_is_unknown(self):
        for value in (None, {}, {'account': None}, {'requiresOpenaiAuth': True},
                      {'account': None, 'requiresOpenaiAuth': 1},
                      {'account': {}, 'requiresOpenaiAuth': True},
                      {'account': False, 'requiresOpenaiAuth': True},
                      {'account': {'type': 'unrecognized'}, 'requiresOpenaiAuth': True},
                      {'account': None, 'requiresOpenaiAuth': False, 'ready': True},
                      {'account': {'type': 'chatgpt', 'email': 'x' * 17000}, 'requiresOpenaiAuth': True}):
            with self.subTest(value=value), self.assertRaises(Refusal): auth.projection(value)

    def test_drift_including_account_identity_refuses_even_if_still_signed_in(self):
        for second in ({'account': None, 'requiresOpenaiAuth': True},
                       {'account': {'type': 'chatgpt', 'email': 'different'}, 'requiresOpenaiAuth': True}):
            proxy = unittest.mock.Mock()
            proxy._rpc.side_effect = [{'account': {'type': 'chatgpt', 'email': 'original'},
                                      'requiresOpenaiAuth': True}, second]
            with self.assertRaisesRegex(Refusal, 'changed'): auth.inspect(proxy)

    def test_base_read_proxy_remains_closed_and_policy_proxy_allows_only_no_refresh(self):
        base = ReadProxy({})
        proxy = policy.PolicyReadProxy({}, 'project', 'brain')
        with patch.object(base, '_rpc') as rpc:
            with self.assertRaises(Refusal): base.call('account/read', {'refreshToken': False})
            rpc.assert_not_called()
        with patch.object(proxy, '_rpc') as rpc:
            proxy.call('account/read', {'refreshToken': False})
            for method, args in (('account/read', {'refreshToken': True}), ('account/login/start', {}),
                                 ('account/read', {'refreshToken': False, 'login': True})):
                with self.assertRaises(Refusal): proxy.call(method, args)
            rpc.assert_called_once_with('account/read', {'refreshToken': False})


class PublicWakeTest(unittest.TestCase):
    def setUp(self):
        self.fixture = wakes.WakeTest(methodName='runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.tearDown)
        self.wake = self.fixture.wake
        self.fixture.binding['endpoint']['sha256'] = 'c' * 64
        self.fixture.binding['brains'][wakes.BRAIN].update(
            policyEvidence=policies.CONTRACT.copy(), nativeTaskBackend=tasks.CONTRACT.copy())
        self.account = {'account': {'type': 'apiKey'}, 'requiresOpenaiAuth': True}
        self.auth_calls = 0
        outer = self
        class Proxy(wakes.FakeProxy):
            def _rpc(self, method, params):
                if method in ('account/read', policy.METHOD):
                    self.calls.append((method, copy.deepcopy(params)))
                    if method == 'account/read':
                        outer.auth_calls += 1
                        return outer.account_response()
                    return policies.response()
                return super()._rpc(method, params)
        self.account_response = lambda: copy.deepcopy(self.account)
        for item in (patch('orchestrator.app_server_wake.WakeProxy', Proxy),
                     patch('orchestrator.app_server_wake.validate_endpoint'),
                     patch('orchestrator.app_server_wake.threading.Thread', wakes.FakeThread)):
            item.start(); self.addCleanup(item.stop)

    def send(self): return self.wake.send(wakes.BRAIN, 'fixed pointer', 'control')

    def methods(self): return [m for m, _ in wakes.FakeProxy.instances[-1].calls]

    def test_missing_auth_refuses_before_any_load_turn_or_observer_marker(self):
        self.account['account'] = None
        result = self.send()
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['nativeFailure']['stage'], 'authentication_check')
        self.assertFalse(result['nativeFailure']['resumeAttempted'])
        self.assertFalse(result['nativeFailure']['turnStartAttempted'])
        self.assertNotIn('thread/resume', self.methods())
        self.assertNotIn('turn/start', self.methods())
        self.assertNotIn('nativeThreadObservation', self.wake.ledger.command['notification'])

    def test_auth_loss_after_load_cannot_start_turn_or_erase_resume_fact(self):
        self.account_response = lambda: ({'account': None, 'requiresOpenaiAuth': True}
                                         if self.auth_calls > 2 else copy.deepcopy(self.account))
        result = self.send()
        self.assertEqual(result['status'], 'unavailable')
        self.assertTrue(result['nativeFailure']['resumeAttempted'])
        self.assertFalse(result['nativeFailure']['turnStartAttempted'])
        self.assertIn('nativeResumeProfile', self.wake.ledger.command['notification'])
        self.assertNotIn('turn/start', self.methods())

    def test_unknown_auth_error_is_sanitized_and_has_no_fallback(self):
        self.account_response = lambda: (_ for _ in ()).throw(Refusal('PRIVATE_TOKEN'))
        result = self.send()
        self.assertNotIn('PRIVATE_TOKEN', canonical(result))
        self.assertFalse(result['nativeFailure']['resumeAttempted'])
        self.assertNotIn('account/login/start', self.methods())

    def test_ready_auth_is_rechecked_without_copying_old_play_profile(self):
        result = self.send()
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(self.auth_calls, 4)
        self.assertEqual(self.methods().count('thread/resume'), 1)
        self.assertEqual(self.methods().count('turn/start'), 1)
        self.assertIsNone(self.wake.ledger.command['notification']['nativeResumeProfile']['reported']['codeMode'])


class PublicWorkerTest(unittest.TestCase):
    def setUp(self):
        self.fixture = tasks.AdapterTest(methodName='runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture

    def test_missing_auth_consumes_explicit_query_without_creation_or_schema_bump(self):
        self.f.account['account'] = None
        before = self.f.ledger.snapshot()['meta']['standardRun']
        self.f.request(); self.f.service()
        self.assertEqual(self.f.request()['stage'], 'refused')
        self.assertFalse(self.f.task()['effectIssued'])
        self.assertEqual(self.f.ledger.snapshot()['meta']['schemaVersion'], 4)
        self.assertNotIn('thread/start', [m for m, _ in self.f.calls])
        self.assertEqual(self.f.ledger.snapshot()['meta']['standardRun'], before)
        calls = copy.deepcopy(self.f.calls)
        self.f.account['account'] = {'type': 'apiKey'}
        self.f.service(); self.f.request()
        self.assertEqual(self.f.calls, calls)  # Repair does not replay this old query.

    def test_signout_after_creation_retains_identity_without_first_turn_or_retry(self):
        self.f.request()
        def signout(method):
            if method == 'thread/start': self.f.account['account'] = None
        self.f.callback = signout; self.f.service()
        self.assertEqual(self.f.task()['threadId'], self.f.thread_id)
        self.assertEqual(self.f.task()['publicNative']['stage'], 'pre_turn_blocked')
        self.assertEqual(self.f.task()['trackedTerminals'], 'unknown')
        self.assertNotIn('turn/start', [m for m, _ in self.f.calls])
        calls = copy.deepcopy(self.f.calls)
        self.f.service(); self.assertEqual(self.f.calls, calls)

    def test_pause_race_during_auth_read_still_prevents_creation(self):
        self.f.request()
        self.f.callback = lambda method: self.f.pause() if method == 'account/read' else None
        self.f.service()
        self.assertNotIn('thread/start', [m for m, _ in self.f.calls])
        self.assertFalse(self.f.task()['effectIssued'])


class DiagnosticTest(unittest.TestCase):
    def setUp(self):
        self.fixture = policies.InspectionTest(methodName='runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture
        self.f.binding['brains'][self.f.brain]['nativeTaskBackend'] = tasks.CONTRACT.copy()
        self.account = {'account': None, 'requiresOpenaiAuth': True}
        self.calls = []
        def rpc(method, params):
            self.calls.append(method)
            return copy.deepcopy(self.account if method == 'account/read' else self.f.raw)
        self.f.fake._rpc = rpc

    def test_auth_missing_is_visible_separate_from_matching_loaded_policy(self):
        before = self.f.fingerprint()
        result = self.f.host.check_policy(self.f.registry)
        self.assertTrue(result['policyVerified'])
        self.assertEqual(result['authentication']['status'], 'authentication_required')
        self.assertIn('needs sign-in', result['detail'])
        self.assertFalse(result['authentication']['modelAccessVerified'])
        self.assertEqual(before, self.f.fingerprint())

    def test_unloaded_and_missing_auth_stay_unknown_without_loading(self):
        self.f.raw['policy'] = None
        self.f.fake.threads[self.f.brain]['status'] = {'type': 'notLoaded'}
        result = self.f.host.check_policy(self.f.registry)
        self.assertEqual(result['status'], 'unknown')
        self.assertEqual(result['authentication']['status'], 'authentication_required')
        self.assertNotIn('thread/resume', self.calls)

    def test_cached_auth_ages_without_recollection_or_timestamp_renewal(self):
        self.account['account'] = {'type': 'apiKey'}
        result = self.f.host.check_policy(self.f.registry)
        count = len(self.calls)
        with patch('orchestrator.app_server_wake.time.time', return_value=result['checkedAt'] + 301):
            cached = self.f.host.policy_status(self.f.brain, result['runId'], result['revision'])
        self.assertEqual(cached['authentication']['status'], 'stale')
        self.assertFalse(cached['authentication']['ready'])
        self.assertEqual(cached['authentication']['checkedAt'], result['authentication']['checkedAt'])
        self.assertEqual(len(self.calls), count)


if __name__ == '__main__': unittest.main()
