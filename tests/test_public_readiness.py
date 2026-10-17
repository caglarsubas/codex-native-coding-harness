"""Backend-specific evidence in disposable ledgers; no live native connection."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from orchestrator import public_readiness as public, standard_preplay as preplay, standard
from orchestrator.core import Refusal, digest
import test_standard_preplay as fixtures
import test_native_policy_evidence as policy_fixtures
import test_app_server_wake as wake_fixtures
from test_public_native_tasks import CONTRACT


def schemas():
    def schema(fields):
        return {'type': 'object', 'properties': {k: {} for k in fields}}
    return {'ThreadStartParams': schema(('cwd', 'projectId', 'model', 'approvalPolicy', 'approvalsReviewer', 'sandbox', 'config', 'ephemeral')),
            'TurnStartParams': schema(('threadId', 'input', 'model', 'effort', 'approvalPolicy', 'approvalsReviewer')),
            'ModelListParams': schema(('cursor', 'limit', 'includeHidden')),
            'ModelListResponse': schema(('data', 'nextCursor'))}


class PublicReadinessTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PreplayTest('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.ledger, self.registry = self.f.ledger, self.f.registry
        self.binding, self.brain, self.cid = self.f.binding, self.f.brain, self.f.cid
        record = self.binding['brains'][self.brain]
        record.update(nativeTaskBackend=copy.deepcopy(CONTRACT), policyEvidence=policy_fixtures.CONTRACT.copy())
        self.binding['endpoint'].update(executable='/fixture/never-executed', sha256='c'*64)
        self.calls = []
        self.page = {'data': [{'model': 'actual-fixture-model', 'hidden': False,
            'supportedReasoningEfforts': [{'reasoningEffort': 'low'}, {'reasoningEffort': 'high'}]}], 'nextCursor': None}
        self.policy = policy_fixtures.response(self.brain, record['cwd'])
        self.thread_status = 'idle'; self.mcp = {'data': [], 'nextCursor': None}
        self.callback = None
        outer = self
        class Proxy:
            def _rpc(self, method, params):
                outer.calls.append((method, copy.deepcopy(params)))
                if outer.callback:
                    outer.callback(method)
                if method == 'model/list': return copy.deepcopy(outer.page)
                if method == 'thread/effectivePolicy/read': return copy.deepcopy(outer.policy)
                if method == 'account/read': return {'account': {'type': 'apiKey'}, 'requiresOpenaiAuth': True}
                if method == 'project/read': return {'project': {'id': record['projectId'], 'roots': [{'path': record['cwd']}]}}
                if method == 'thread/read': return {'thread': {'id': outer.brain, 'cwd': record['cwd'],
                    'projectId': record['projectId'], 'status': {'type': outer.thread_status}}}
                if method == 'mcpServerStatus/list': return copy.deepcopy(outer.mcp)
                raise AssertionError('Forbidden native method: '+method)
        self.proxy = Proxy()
        self.export = patch.object(public, 'export_schemas', return_value=public.schema_contract(schemas())).start()
        self.addCleanup(patch.stopall)
        patch.object(public, 'validate_endpoint').start()
        self.f.notifier.app_server.send = self.send

    def send(self, brain, message, command):
        with self.ledger.tx() as db:
            c = self.ledger.get(db, 'commands', self.cid)
            c['notification'].update(nativeTaskContract=copy.deepcopy(CONTRACT),
                nativePublicReadinessProfile={'bindingHash': digest(self.binding), 'brainId': self.brain,
                    'commandId': self.cid, 'nativeLoadMade': False})
            self.ledger.put(db, 'commands', self.cid, c)
        preplay.capture_public(self.ledger, self.binding, self.cid, self.brain, self.proxy)
        preplay.public_send_check(self.ledger, self.binding, self.cid, self.brain)
        with self.ledger.tx() as db:
            c = self.ledger.get(db, 'commands', self.cid)
            c['notification']['nativePublicReadinessProfile']['nativeTurnId'] = 'original-turn'
            self.ledger.put(db, 'commands', self.cid, c)
        return self.f.send(brain, message, command)

    def deliver(self): return self.f.deliver()

    def acknowledge(self):
        state = preplay.state(self.f.handoff)
        result = {'operation': 'public_catalog_ack', 'requestId': self.cid,
                  'evidenceHash': state['publicReadiness']['evidenceHash']}
        self.f.publish(result); self.f.service()
        return standard.read(self.ledger)

    def test_public_receipt_uses_exact_observed_evidence_without_desktop_schemas_or_load(self):
        self.deliver(); before = self.ledger.snapshot()['meta']
        state = self.acknowledge()
        self.assertEqual(state['catalogRefresh']['status'], 'completed')
        self.assertEqual(state['catalog']['models'], [{'model': 'actual-fixture-model', 'efforts': ['low', 'high']}])
        self.assertTrue(state['available'])
        self.assertEqual(preplay.status(self.f.handoff)['status'], 'completed')
        self.assertFalse(state['catalog']['publicReadiness']['boundary']['modelEntitlementVerified'])
        self.assertEqual(state['catalog']['observedAt'], state['catalog']['publicReadiness']['observedAt'],
                         'Acknowledgement must not refresh the original native capture time')
        self.assertIsNone(self.ledger.snapshot()['meta'].get('standardRun'))
        self.assertEqual(before['checkpoint'], self.ledger.snapshot()['meta']['checkpoint'])
        public.retained_catalog(state['catalog'], self.ledger.snapshot()['commands'][0], self.binding)
        self.assertTrue(all(m in {'model/list', 'account/read', 'project/read', 'thread/read',
            'thread/effectivePolicy/read', 'mcpServerStatus/list'} for m,_ in self.calls))
        self.assertIn('public_catalog_ack', self.f.sent[0]); self.assertNotIn('Inspect only current native creation', self.f.sent[0])

    def test_model_list_alone_cannot_be_a_public_catalog(self):
        self.deliver()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1)
            with self.assertRaisesRegex(Refusal, 'original backend evidence'):
                standard.catalog_in(self.ledger, db, meta, self.f.result)
        self.assertIsNone(standard.read(self.ledger)['catalog'])

    def test_brain_cannot_supply_a_catalog_or_rewrite_model_choices(self):
        self.deliver()
        file = self.ledger.root/'brain-result.json'; preplay._write_once(file, self.f.result)
        with self.assertRaisesRegex(Refusal, 'exact pre-Play'):
            preplay.submit(self.f.handoff, file)
        self.assertFalse(preplay.path(self.ledger.root, self.cid, 'request').exists())

    def test_forged_ack_cannot_create_a_catalog(self):
        self.deliver(); self.f.publish({'operation': 'public_catalog_ack', 'requestId': self.cid, 'evidenceHash': '0'*64})
        self.f.service()
        self.assertEqual(preplay.status(self.f.handoff)['status'], 'unavailable')
        self.assertIsNone(standard.read(self.ledger)['catalog'])

    def test_tampered_capture_is_not_brain_evidence(self):
        self.deliver()
        path = preplay.path(self.ledger.root, self.cid, 'capabilities')
        value = preplay._read_private(path); value['models'][0]['model'] = 'invented'
        path.write_text(__import__('json').dumps(value))
        self.acknowledge()
        self.assertIsNone(standard.read(self.ledger)['catalog'])
        self.assertEqual(preplay.status(self.f.handoff)['status'], 'unavailable')

    def test_claimed_capture_never_reexecutes_even_after_failure(self):
        self.page['nextCursor'] = 'repeat'
        with self.assertRaises(Refusal): self.deliver()
        self.assertTrue(preplay.path(self.ledger.root, self.cid, 'capabilities-claim').exists())
        self.assertEqual(self.export.call_count, 1)
        self.page['nextCursor'] = None
        with self.assertRaises(FileExistsError):
            preplay.capture_public(self.ledger, self.binding, self.cid, self.brain, self.proxy)
        self.assertEqual(self.export.call_count, 1)

    def test_not_loaded_or_active_brain_never_counts_as_idle(self):
        for status in ('notLoaded', 'active'):
            self.thread_status = status
            with self.assertRaises(Refusal):
                public.collect(self.proxy, self.binding, self.brain, self.cid, '0'*64)
        self.assertNotIn('thread/resume', [m for m,_ in self.calls])

    def test_missing_or_unenforced_policy_is_not_readiness(self):
        for value in (None, False):
            self.policy = policy_fixtures.response(self.brain, self.binding['brains'][self.brain]['cwd'])
            if value is None: self.policy['policy'] = None
            else: self.policy['policy']['codeModeOffEnforced'] = False
            with self.assertRaises(Refusal): public.collect(self.proxy, self.binding, self.brain, self.cid, '0'*64)

    def test_nonempty_or_incomplete_mcp_inventory_refuses(self):
        for value in ({'data': [{}], 'nextCursor': None}, {'data': [], 'nextCursor': 'next'}):
            self.mcp = value
            with self.assertRaises(Refusal): public.collect(self.proxy, self.binding, self.brain, self.cid, '0'*64)

    def test_changed_model_observation_refuses(self):
        n = []
        def change(method):
            if method == 'model/list':
                n.append(1)
                if len(n) == 2: self.page['data'][0]['model'] = 'changed'
        self.callback = change
        with self.assertRaisesRegex(Refusal, 'observations changed'):
            public.collect(self.proxy, self.binding, self.brain, self.cid, '0'*64)

    def test_schema_must_cover_exact_adapter_parameters(self):
        for name, field in [('ThreadStartParams', 'projectId'), ('TurnStartParams', 'effort'), ('ModelListParams', 'cursor')]:
            value = schemas(); del value[name]['properties'][field]
            with self.assertRaises(Refusal): public.schema_contract(value)
        value = schemas(); value['ThreadStartParams']['properties']['sandbox'] = {'enum': ['danger-full-access']}
        with self.assertRaises(Refusal): public.schema_contract(value)

    def test_schema_constraints_are_never_silently_ignored(self):
        self.assertFalse(public.accepts({'minimum': 50, 'type': 'integer'}, 30, {}))
        self.assertFalse(public.accepts({'oneOf': [{}, {}]}, 'ambiguous', {}))
        self.assertFalse(public.accepts({'allOf': [{'type': 'string'}, {'minLength': 3}]}, 'x', {}))
        for constraint in ('not', 'const', 'if', 'patternProperties'):
            with self.assertRaises(Refusal): public.accepts({constraint: {}}, 'x', {})

    def test_changed_receipt_and_policy_shapes_cannot_qualify_cached_evidence(self):
        self.deliver(); state = self.acknowledge()
        command = self.ledger.snapshot()['commands'][0]
        for key in ('brainId', 'handoffHash', 'requestHash'):
            changed = copy.deepcopy(command); changed['preplayReceipt'][key] = 'foreign'
            with self.assertRaises(Refusal): public.retained_catalog(state['catalog'], changed, self.binding)
        value = copy.deepcopy(state['catalog']['publicReadiness']); value['policy']['extra'] = True
        with self.assertRaises(Refusal): public.validate(value, value['bindingHash'], self.brain, self.cid, value['handoffHash'])

    def test_foreign_schema_refs_and_unsupported_models_refuse(self):
        with self.assertRaises(Refusal): public.accepts({'$ref': 'https://not-a-schema'}, 'x', {})
        self.page['data'][0]['supportedReasoningEfforts'] = [{'reasoningEffort': 'unknown-new-effort'}]
        with self.assertRaisesRegex(Refusal, 'No supported'): public.models(self.proxy)

    def test_duplicate_models_efforts_and_pagination_are_not_complete(self):
        original = copy.deepcopy(self.page)
        for mode in ('model', 'effort', 'cursor'):
            self.page = copy.deepcopy(original)
            if mode == 'model': self.page['data'] *= 2
            if mode == 'effort': self.page['data'][0]['supportedReasoningEfforts'] *= 2
            if mode == 'cursor': self.page['nextCursor'] = 'cycle'
            with self.assertRaises(Refusal): public.models(self.proxy)

    def test_closed_observer_cannot_accept_a_late_public_receipt(self):
        self.deliver()
        self.f.mutate('commands', self.cid, lambda c: c['notification']['nativeThreadObservation'].update(streamStatus='closed'))
        self.acknowledge()
        self.assertEqual(preplay.status(self.f.handoff)['status'], 'unavailable')
        self.assertIsNone(standard.read(self.ledger)['catalog'])

    def test_status_and_state_never_recollect_or_connect(self):
        self.deliver(); count = len(self.calls)
        with patch.object(public, 'collect', side_effect=AssertionError('No collection')):
            preplay.state(self.f.handoff); preplay.status(self.f.handoff)
        self.assertEqual(len(self.calls), count)

    def test_public_sandbox_ack_has_no_sqlite_registry_or_native_access(self):
        self.deliver(); evidence = preplay.state(self.f.handoff)['publicReadiness']['evidenceHash']
        file = self.ledger.root/'ack.json'
        preplay._write_once(file, {'operation': 'public_catalog_ack', 'requestId': self.cid, 'evidenceHash': evidence})
        with patch('sqlite3.connect', side_effect=AssertionError('SQLite forbidden')), \
             patch('socket.socket', side_effect=AssertionError('Native connection forbidden')), \
             patch('orchestrator.workspaces.Registry', side_effect=AssertionError('Registry forbidden')), \
             patch.object(preplay.time, 'monotonic', side_effect=[0, 31]):
            self.assertEqual(preplay.state(self.f.handoff)['publicReadiness']['evidenceHash'], evidence)
            self.assertEqual(preplay.submit(self.f.handoff, file)['status'], 'waiting_for_original_observer')

    def test_foreign_binding_cannot_reuse_a_retained_catalog(self):
        self.deliver(); state = self.acknowledge()
        wrong = copy.deepcopy(self.binding); wrong['endpoint']['sha256'] = 'd'*64
        with self.assertRaises(Refusal): public.retained_catalog(state['catalog'], self.ledger.snapshot()['commands'][0], wrong)

    def test_no_automatic_retry_can_clear_an_unavailable_original_public_send(self):
        self.deliver()
        self.f.mutate('commands', self.cid, lambda c: c['notification'].update(status='unavailable'))
        saved = self.ledger.snapshot()['commands'][0]
        again = standard.request_catalog_refresh(self.ledger, {'id': self.cid, 'contextHash': saved['payload']['contextHash']})
        self.assertEqual(again, saved)
        self.assertNotIn('notificationHistory', again)

    def test_stop_race_during_capture_fences_receipt_and_send(self):
        def stop(method):
            if method == 'model/list':
                self.f.mutate('meta', 1, lambda m: m.update(brainControl={'desired': 'stopped', 'status': 'checkpointing'}))
        self.callback = stop
        with self.assertRaises(Refusal): self.deliver()
        self.assertFalse(preplay.path(self.ledger.root, self.cid, 'capabilities').exists())

    def test_late_capture_cannot_backfill_an_accepted_original(self):
        self.deliver(); count = len(self.calls)
        with self.assertRaises(Refusal): preplay.capture_public(self.ledger, self.binding, self.cid, self.brain, self.proxy)
        self.assertEqual(len(self.calls), count)

    def test_lost_reply_does_not_reapply_public_receipt(self):
        self.deliver(); value = preplay.state(self.f.handoff)['publicReadiness']
        self.f.publish({'operation': 'public_catalog_ack', 'requestId': self.cid, 'evidenceHash': value['evidenceHash']})
        original = preplay._write_once
        def lost(file, value):
            if file.name.endswith('-reply.json'): raise OSError('Fixture lost reply')
            original(file, value)
        with patch.object(preplay, '_write_once', side_effect=lost), self.assertRaises(OSError): self.f.service()
        proof = self.f.proof(); self.f.service()
        self.assertEqual(self.f.proof(), proof)
        self.assertEqual(preplay.status(self.f.handoff)['status'], 'claimed_outcome_unknown')
        self.assertEqual(standard.read(self.ledger)['catalogRefresh']['status'], 'completed')


class PublicWakeTest(unittest.TestCase):
    def setUp(self):
        self.f = wake_fixtures.WakeTest('runTest'); self.f.setUp(); self.addCleanup(self.f.tearDown)
        self.wake = self.f.wake
        brain = wake_fixtures.BRAIN
        self.f.binding['brains'][brain].update(nativeTaskBackend=copy.deepcopy(CONTRACT),
            policyEvidence=policy_fixtures.CONTRACT.copy())
        self.f.binding['endpoint']['sha256'] = 'c'*64
        self.wake.ledger.command.update(kind='standard_catalog_refresh')
        self.wake.ledger.command['notification']['preplayCatalog'] = {'version': 2}
        outer = self
        class Proxy(wake_fixtures.FakeProxy):
            status = 'idle'
            def _rpc(self, method, params):
                if method == 'account/read':
                    self.calls.append((method, params)); return {'account': {'type': 'apiKey'}, 'requiresOpenaiAuth': True}
                if method == 'thread/effectivePolicy/read':
                    self.calls.append((method, params)); return policy_fixtures.response()
                return super()._rpc(method, params)
        self.proxy = Proxy
        for item in (patch('orchestrator.app_server_wake.WakeProxy', Proxy),
                     patch('orchestrator.app_server_wake.validate_endpoint'),
                     patch('orchestrator.app_server_wake.threading.Thread', wake_fixtures.FakeThread)):
            item.start(); self.addCleanup(item.stop)
        self.capture = patch.object(preplay, 'capture_public', return_value={}).start()
        self.check = patch.object(preplay, 'public_send_check').start()
        self.addCleanup(patch.stopall)

    def test_loaded_public_readiness_never_resumes_the_brain(self):
        result = self.wake.send(wake_fixtures.BRAIN, 'fixed pointer', 'control')
        self.assertEqual(result['status'], 'accepted')
        calls = [m for m,_ in wake_fixtures.FakeProxy.instances[-1].calls]
        self.assertNotIn('thread/resume', calls); self.assertEqual(calls.count('turn/start'), 1)
        self.assertEqual(self.capture.call_count, 1); self.assertEqual(self.check.call_count, 1)
        note = self.wake.ledger.command['notification']
        self.assertNotIn('nativeResumeProfile', note)
        self.assertFalse(note['nativePublicReadinessProfile']['nativeLoadMade'])
        self.assertEqual(note['nativePublicReadinessProfile']['nativeTurnId'], wake_fixtures.TURN)

    def test_not_loaded_public_brain_is_fenced_without_reload(self):
        self.proxy.status = 'notLoaded'
        result = self.wake.send(wake_fixtures.BRAIN, 'fixed pointer', 'control')
        self.assertEqual(result['status'], 'unavailable')
        self.assertFalse(result['nativeFailure']['resumeAttempted'])
        self.assertFalse(result['nativeFailure']['turnStartAttempted'])
        self.capture.assert_not_called()

    def test_capture_failure_never_starts_a_turn_or_reloads(self):
        self.capture.side_effect = Refusal('fixture schema unavailable')
        result = self.wake.send(wake_fixtures.BRAIN, 'fixed pointer', 'control')
        self.assertEqual(result['status'], 'unavailable')
        self.assertFalse(result['nativeFailure']['resumeAttempted'])
        self.assertFalse(result['nativeFailure']['turnStartAttempted'])

    def test_send_check_race_never_starts_a_turn(self):
        self.check.side_effect = Refusal('fixture Pause race')
        result = self.wake.send(wake_fixtures.BRAIN, 'fixed pointer', 'control')
        self.assertEqual(result['status'], 'unavailable')
        self.assertFalse(result['nativeFailure']['turnStartAttempted'])

    def test_public_play_cannot_substitute_a_bare_model_catalog(self):
        self.wake.ledger.command['kind'] = 'standard_play'
        self.wake.ledger.command['standardRun'] = {'catalog': {'models': [{'model': 'invented', 'efforts': ['high']}]}}
        result = self.wake.send(wake_fixtures.BRAIN, 'pointer', 'control')
        self.assertEqual(result['status'], 'unavailable')
        self.assertFalse(result['nativeFailure']['turnStartAttempted'])
        self.assertFalse(result['nativeFailure']['resumeAttempted'])


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name).resolve()/'fixture-executable'
        self.file.write_bytes(b'no executable fixture code is run'); self.file.chmod(0o700)
        self.sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.mode = 'good'

    def export(self, argv, **kwargs):
        self.assertEqual(argv[:5], [str(self.file), 'app-server', 'generate-json-schema', '--experimental', '--out'])
        self.assertEqual(set(kwargs['env']), {'PATH', 'HOME', 'CODEX_HOME', 'TMPDIR'})
        self.assertEqual(kwargs['env']['HOME'], kwargs['env']['CODEX_HOME'])
        self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
        output = Path(argv[5]); (output/'v2').mkdir(parents=True)
        for name, value in schemas().items():
            file = output/'v2'/(name+'.json')
            file.write_text(json.dumps(value))
            if self.mode == 'symlink' and name == 'TurnStartParams':
                file.unlink(); file.symlink_to(self.file)
            if self.mode == 'duplicate' and name == 'TurnStartParams':
                file.write_text('{"type":"object","type":"object"}')
        return subprocess.CompletedProcess(argv, 0)

    def test_fixed_schema_export_uses_empty_home_and_actual_argument_validator(self):
        with patch.object(public.subprocess, 'run', side_effect=self.export):
            self.assertEqual(public.export_schemas(str(self.file), self.sha), public.schema_contract(schemas()))

    def test_changed_binary_refuses_before_execution(self):
        with patch.object(public.subprocess, 'run') as run, self.assertRaises(Refusal):
            public.export_schemas(str(self.file), '0'*64)
        run.assert_not_called()

    def test_symlink_and_duplicate_schema_outputs_refuse(self):
        for mode in ('symlink', 'duplicate'):
            self.mode = mode
            with patch.object(public.subprocess, 'run', side_effect=self.export), self.assertRaises(Refusal):
                public.export_schemas(str(self.file), self.sha)

    def test_export_timeout_is_closed_failure_without_fallback(self):
        with patch.object(public.subprocess, 'run', side_effect=subprocess.TimeoutExpired('fixture', 20)) as run:
            with self.assertRaisesRegex(Refusal, 'no fallback or retry'): public.export_schemas(str(self.file), self.sha)
        self.assertEqual(run.call_count, 1)


if __name__ == '__main__':
    unittest.main()
