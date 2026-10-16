"""Disposable cross-project successor admission; no live binding or native turn."""
import copy
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator import core, projects, standard, standard_successor as successor
from orchestrator.core import Refusal, canonical, digest
from orchestrator.app_server_wake import AppServerWake
from orchestrator.workspaces import fingerprint
import test_standard_quarantine as fixtures
from test_native_policy_evidence import response, CONTRACT
from test_app_server_wake import FakeThread


class SuccessorTest(unittest.TestCase):
    def setUp(self):
        self.q = fixtures.QuarantineTest(methodName='runTest'); self.q.setUp(); self.addCleanup(self.q.doCleanups)
        self.source, self.registry = self.q.ledger, self.q.registry
        base = self.q.f.fixture.fixture
        self.old_repo = base.repo
        self.git(self.old_repo, 'remote', 'add', 'origin', 'https://github.com/fixture/old.git')
        self.new_repo = base.root/'separate-repo'; self.new_repo.mkdir()
        self.git(self.new_repo, 'init', '-q')
        self.git(self.new_repo, 'remote', 'add', 'origin', 'https://github.com/fixture/new.git')
        base.repo = self.new_repo
        self.target, self.token = base.workspace('beta'); base.repo = self.old_repo
        self.target.release(self.token, 'Disposable pre-phase setup complete')
        self.brain = self.target.snapshot()['meta']['brainId']
        self.project, self.catalog = str(uuid.uuid4()), str(uuid.uuid4())
        entries = [{'projectId': self.q.f.fixture.catalog_project_id, 'projectKind': 'local', 'label': 'Source',
                    'hostId': 'local', 'path': str(self.old_repo), 'isGitRepository': True},
                   {'projectId': self.catalog, 'projectKind': 'local', 'label': 'Target', 'hostId': 'local',
                    'path': str(self.new_repo), 'isGitRepository': True}]
        projects.record(self.registry, {'schemaVersion': 2, 'projects': entries}, time.time())
        projects.bind(self.registry, 'beta', 'local', self.catalog, projects.catalog(self.registry)['hash'])
        self.binding = {'endpoint': {'fixture': 'pinned', 'sha256': 'a'*64}, 'brains': {self.brain: {
            'workspaceId': 'beta', 'cwd': str(self.new_repo), 'projectId': self.project,
            'catalogProjectId': self.catalog, 'policyEvidence': CONTRACT,
            'nativePolicy': {'sandbox': 'workspace-write', 'approvalPolicy': 'on-request', 'codeMode': False}}}}
        self.binding_path = base.root/'target-binding.json'
        self.binding_path.write_text(canonical(self.binding)); self.binding_path.chmod(0o600)
        self.q.confirm()
        with standard.read_db(self.source.db) as db: self.old = fingerprint(db)
        self.controls = standard.Controls()

    @staticmethod
    def git(path, *args): subprocess.run(['git', '-C', str(path), *args], check=True, capture_output=True)

    def assert_source_unchanged(self):
        with standard.read_db(self.source.db) as db: self.assertEqual(fingerprint(db), self.old)

    def prepare(self): return successor.prepare(self.registry, self.source, 'beta', self.binding_path)
    def confirm(self, preview=None):
        p = preview or self.prepare(); return successor.confirm(self.registry, self.source, p['request'], p['reviewHash'])
    def play(self):
        p = self.controls.preview(self.target, {'operation': 'play', 'contextHash': standard.read(self.target)['contextHash'],
                                 'brainAllowance': 10000, 'durationHours': 8}, 'owner')
        return self.controls.confirm(self.registry, self.target, {**p, 'confirmed': True}, 'owner')

    def test_preview_is_local_nonwaking_and_preserves_both_ledgers(self):
        with standard.read_db(self.target.db) as db: before = fingerprint(db)
        p = self.prepare()
        self.assertEqual(p['validUntil'], 'scope_changes'); self.assertFalse(any(p['request']['boundary'].values()))
        self.assert_source_unchanged()
        with standard.read_db(self.target.db) as db: self.assertEqual(fingerprint(db), before)
        self.assertFalse(self.q.f.fixture.fake.calls)

    def test_admission_preserves_old_run_and_requires_separate_play(self):
        receipt = self.confirm(); meta = self.target.snapshot()['meta']
        self.assertEqual(meta['schemaVersion'], 7); self.assertIsNone(meta.get('standardRun'))
        self.assert_source_unchanged()
        self.assertEqual(receipt['priorObservedTokens'], 1049625)
        self.assertEqual(receipt['priorTerminalSafety'], 'unknown')
        self.assertFalse(receipt['boundary']['playAuthorized'])
        self.assertEqual(standard.read(self.target)['successor']['recordHash'], receipt['recordHash'])
        command = self.play(); run = standard.read(self.target)['run']
        self.assertEqual(command['payload']['successorHash'], receipt['recordHash'])
        self.assertEqual(run['ownerReceipt']['successorHash'], receipt['recordHash'])
        self.assertEqual(run['successorHash'], receipt['recordHash'])
        self.assert_source_unchanged()
        with patch.object(core, 'LEDGER_VERSIONS', (1, 2, 3, 4, 5, 6)):
            with self.assertRaises(Refusal): core.Ledger(self.target.root)

    def test_exact_confirmation_replay_returns_original_without_new_play(self):
        p = self.prepare(); first = self.confirm(p)
        with standard.read_db(self.target.db) as db: before = fingerprint(db)
        self.assertEqual(self.confirm(p), first)
        with standard.read_db(self.target.db) as db: self.assertEqual(fingerprint(db), before)
        self.assertEqual(self.target.snapshot()['commands'], [])

    def test_same_workspace_or_shared_remote_or_nested_checkout_refuses(self):
        with self.assertRaises(Refusal): successor.prepare(self.registry, self.source, 'alpha', self.binding_path)
        with self.assertRaisesRegex(Refusal, 'must not share'):
            successor.disjoint([{'root': str(self.old_repo), 'keys': ['a']}],
                               [{'root': str(self.old_repo/'nested'), 'keys': ['b']}])
        with self.assertRaisesRegex(Refusal, 'must not share'):
            successor.disjoint([{'root': str(self.old_repo), 'keys': ['common']}],
                               [{'root': str(self.new_repo), 'keys': ['common']}])
        self.git(self.new_repo, 'remote', 'set-url', 'origin', 'git@github.com:fixture/old.git')
        with self.assertRaisesRegex(Refusal, 'must not share'): self.prepare()

    def test_unknown_repository_identity_never_means_disjoint(self):
        self.git(self.new_repo, 'remote', 'remove', 'origin')
        with self.assertRaisesRegex(Refusal, 'Complete local'): self.prepare()

    def localize(self):
        for repo in (self.old_repo, self.new_repo):
            self.git(repo, 'remote', 'remove', 'origin')
            self.git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=f@example.invalid',
                     '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'independent genesis '+repo.name)

    def test_explicit_local_identity_review_admits_without_releasing_old_scope(self):
        self.localize()
        with self.assertRaises(Refusal): self.prepare()
        p = successor.prepare(self.registry, self.source, 'beta', self.binding_path, local_only=True)
        self.assertEqual(p['request']['identityPolicy'], successor.LOCAL_POLICY)
        self.assertEqual(p['request']['target']['repositories'][0]['localIdentity']['remotes'], 'observed_absent')
        receipt = self.confirm(p)
        self.assertEqual(receipt['priorObservedTokens'], 1049625)
        self.assertFalse(receipt['boundary']['repositoryReleased'])
        self.assert_source_unchanged()
        self.git(self.new_repo, '-c', 'user.name=Fixture', '-c', 'user.email=f@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'permitted later commit')
        with standard.read_db(self.target.db) as db:
            self.assertEqual(successor.retained_in(self.target, db)['reviewHash'], p['reviewHash'])
        command = self.play()
        with self.target.tx() as db:
            command = self.target.get(db, 'commands', command['id'])
            command['notification'] = {'status': 'sending', 'brainId': self.brain,
                'hostRunId': command['payload']['runId'], 'hostBindingHash': digest(self.binding),
                'successorHash': command['payload']['successorHash'], 'attemptedAt': time.time(),
                'hostInspectionTransport': 'owned_observer_v1'}
            self.target.put(db, 'commands', command['id'], command)
        native = self.fake(); host = AppServerWake(self.binding, self.target)
        with patch.object(host, 'configured', return_value=True), patch('orchestrator.app_server_wake.validate_endpoint'), \
             patch('orchestrator.app_server_wake.WakeProxy', return_value=native), \
             patch('orchestrator.app_server_wake.threading.Thread', FakeThread):
            delivered = host.send(self.brain, 'Fixture local-only fixed pointer', command['id'])
        self.assertEqual(delivered['status'], 'accepted', delivered)
        self.assertEqual(native.calls.count('turn/start'), 1)
        self.assertNotIn('thread/resume', native.calls)
        self.assert_source_unchanged()

    def test_local_identity_config_drift_refuses_before_permanent_claim(self):
        self.localize()
        p = successor.prepare(self.registry, self.source, 'beta', self.binding_path, local_only=True)
        self.git(self.new_repo, 'remote', 'add', 'origin', 'https://github.com/fixture/new')
        with self.assertRaises(Refusal): self.confirm(p)
        self.assertFalse((self.target.root/successor.FENCE).exists())
        self.assert_source_unchanged()

    def test_local_identity_clone_and_foreign_hold_conflict(self):
        self.localize()
        p = successor.prepare(self.registry, self.source, 'beta', self.binding_path, local_only=True)
        self.git(self.new_repo, 'fetch', '-q', str(self.old_repo), 'HEAD:refs/heads/old-copy')
        with self.assertRaises(Refusal): self.confirm(p)
        with self.assertRaisesRegex(Refusal, 'must not share'):
            successor.prepare(self.registry, self.source, 'beta', self.binding_path, local_only=True)
        self.assert_source_unchanged()

    def test_changed_target_or_binding_invalidates_exact_review(self):
        p = self.prepare()
        with self.target.tx() as db:
            meta = self.target.get(db, 'meta', 1); meta['revision'] += 1; self.target.put(db, 'meta', 1, meta)
        with self.assertRaisesRegex(Refusal, 'scope changed'): self.confirm(p)
        self.assertFalse((self.target.root/successor.FENCE).exists())
        p = self.prepare(); self.binding_path.write_text(canonical({**self.binding, 'extra': True}))
        with self.assertRaises(Refusal): self.confirm(p)

    def test_pending_control_and_owned_target_refuse(self):
        with self.target.tx() as db:
            meta = self.target.get(db, 'meta', 1); meta['controller'] = {'owner': 'fixture'}
            self.target.put(db, 'meta', 1, meta)
        with self.assertRaisesRegex(Refusal, 'empty unowned'): self.prepare()

    def test_interrupted_admission_is_permanently_fenced_not_retried(self):
        p = self.prepare()
        original = core.Ledger.put
        def fail_meta(db, table, key, value):
            if table == 'meta' and value.get('schemaVersion') == 7: raise OSError('Synthetic interruption')
            return original(db, table, key, value)
        with patch.object(core.Ledger, 'put', side_effect=fail_meta):
            with self.assertRaises(OSError): self.confirm(p)
        with self.assertRaises(Refusal): self.confirm(p)
        with self.assertRaises(Refusal):
            with self.target.tx(): pass
        self.assert_source_unchanged()

    def test_damaged_or_deleted_marker_cannot_downgrade_or_hide_old_usage(self):
        self.confirm(); (self.target.root/successor.FENCE).unlink()
        with self.assertRaises(Refusal):
            with self.target.tx(): pass
        self.assertFalse(standard.read(self.target)['available'])
        self.assertEqual(self.source.snapshot()['meta']['standardRun']['brainObservedTokens'], 1049625)

    def test_post_admission_scope_change_rolls_back(self):
        self.confirm()
        with self.assertRaises(Refusal):
            with self.target.tx() as db:
                meta = self.target.get(db, 'meta', 1); meta['schemaVersion'] = 1
                self.target.put(db, 'meta', 1, meta)
        self.assertEqual(self.target.snapshot()['meta']['schemaVersion'], 7)

    def test_post_admission_binding_drift_fences_writes(self):
        self.confirm()
        self.binding_path.write_text(canonical({**self.binding, 'extra': True}))
        with self.assertRaises(Refusal): self.target.acquire(self.brain+':fixture')
        self.assertFalse(standard.read(self.target)['available']); self.assert_source_unchanged()

    def test_hardlinked_binding_cannot_be_admitted(self):
        os.link(self.binding_path, self.binding_path.parent/'binding-alias')
        with self.assertRaises(Refusal): self.prepare()

    def test_late_foreign_owner_blocks_effects_but_not_local_pause(self):
        self.confirm(); self.play()
        base = self.q.f.fixture.fixture
        old = base.repo; base.repo = self.new_repo
        foreign, token = base.workspace('gamma'); base.repo = old
        foreign.release(token, 'Fixture setup complete')
        with foreign.tx() as db:
            meta = foreign.get(db, 'meta', 1); meta['runner'] = {'owner': 'foreign-fixture'}
            foreign.put(db, 'meta', 1, meta)
        with standard.read_db(self.target.db) as db: scopes = successor.repositories(self.target.all(db, 'repos'))
        with self.assertRaisesRegex(Refusal, 'must not share'):
            successor.other_owners(self.registry, self.target, scopes)
        p = self.controls.preview(self.target, {'operation': 'pause',
            'contextHash': standard.read(self.target)['contextHash'], 'brainAllowance': 10000, 'durationHours': 8}, 'owner')
        self.controls.confirm(self.registry, self.target, {**p, 'confirmed': True}, 'owner')
        self.assertEqual(standard.read(self.target)['run']['status'], 'stopping'); self.assert_source_unchanged()

    def sending(self):
        self.confirm(); command = self.play()
        with self.target.tx() as db:
            command = self.target.get(db, 'commands', command['id'])
            command['notification'] = {'status': 'sending', 'brainId': self.brain, 'hostRunId': command['payload']['runId'],
                'hostBindingHash': digest(self.binding), 'successorHash': command['payload']['successorHash'],
                'attemptedAt': time.time(), 'hostInspectionTransport': 'owned_observer_v1'}
            self.target.put(db, 'commands', command['id'], command)
        return command

    def fake(self, *, loaded=True, terminals=None, callback=None):
        owner = self
        class Native:
            calls = []
            active = False
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def call(self, method, params): return self._rpc(method, params)
            def _rpc(self, method, params):
                self.calls.append(method)
                if callback: callback(method)
                if method == 'thread/read': return {'thread': {'id': owner.brain, 'projectId': owner.project,
                    'cwd': str(owner.new_repo), 'status': {'type': 'active' if self.active else 'idle' if loaded else 'notLoaded', 'activeFlags': []}}}
                if method == 'project/read': return {'project': {'id': owner.project, 'roots': [{'path': str(owner.new_repo)}]}}
                if method == 'thread/backgroundTerminals/list': return {'data': terminals or [], 'nextCursor': None}
                if method == 'thread/effectivePolicy/read': return response(owner.brain, str(owner.new_repo))
                if method == 'turn/start':
                    self.active = True
                    return {'turn': {'id': 'new-owned-turn'}}
                raise AssertionError('Forbidden native call: '+method)
        return Native()

    def test_loaded_only_send_uses_new_control_and_never_resumes(self):
        command = self.sending(); native = self.fake(); host = AppServerWake(self.binding, self.target)
        with patch.object(host, 'configured', return_value=True), patch('orchestrator.app_server_wake.validate_endpoint'), \
             patch('orchestrator.app_server_wake.WakeProxy', return_value=native), \
             patch('orchestrator.app_server_wake.threading.Thread', FakeThread):
            result = host.send(self.brain, 'Fixture fixed pointer', command['id'])
        self.assertEqual(result['status'], 'accepted', result)
        self.assertEqual(native.calls.count('turn/start'), 1); self.assertNotIn('thread/resume', native.calls)
        with self.target.tx() as db:
            command = self.target.get(db, 'commands', command['id']); command['notification'].update(result)
            self.target.put(db, 'commands', command['id'], command)
        policy = standard.read(self.target)['nativePolicyVerification']
        self.assertTrue(policy['policyVerified']); self.assertTrue(policy['loadedWithoutResume'])
        self.assertFalse(policy['resumeAcknowledged'])
        self.assert_source_unchanged()

    def test_unloaded_or_unknown_terminal_target_never_loads_or_starts(self):
        command = self.sending(); native = self.fake(loaded=False); host = AppServerWake(self.binding, self.target)
        with patch.object(host, 'configured', return_value=True), patch('orchestrator.app_server_wake.WakeProxy', return_value=native):
            result = host.send(self.brain, 'Fixture', command['id'])
        self.assertEqual(result['status'], 'unavailable'); self.assertFalse(result['nativeFailure']['resumeAttempted'])
        self.assertNotIn('thread/resume', native.calls); self.assertNotIn('turn/start', native.calls)
        self.assert_source_unchanged()

    def test_public_idle_enum_is_explicitly_supported_without_reload(self):
        command = self.sending(); native = self.fake(); call = native._rpc
        def native_idle(method, params):
            value = call(method, params)
            if method == 'thread/read': value['thread']['status'] = {'type': 'idle'}
            return value
        native._rpc = native_idle
        profile, evidence = successor.loaded_profile(AppServerWake(self.binding, self.target), native, command['id'], self.brain)
        self.assertEqual(profile['protocol'], successor.PROFILE)
        self.assertTrue(evidence['reported']['codeModeOffEnforced']); self.assertNotIn('thread/resume', native.calls)

    def test_malformed_idle_flags_and_unknown_terminal_page_never_start(self):
        command = self.sending(); host = AppServerWake(self.binding, self.target)
        for status in ({'type': 'idle', 'activeFlags': None}, {'type': 'idle', 'activeFlags': ['waitingOnApproval']},
                       {'type': 'active', 'activeFlags': []}):
            native = self.fake(); call = native._rpc
            def changed(method, params):
                value = call(method, params)
                if method == 'thread/read': value['thread']['status'] = status
                return value
            native._rpc = changed
            with self.assertRaises(Refusal): successor.loaded_profile(host, native, command['id'], self.brain)
            self.assertNotIn('turn/start', native.calls)
        native = self.fake(); call = native._rpc
        def incomplete(method, params):
            return {'data': []} if method == 'thread/backgroundTerminals/list' else call(method, params)
        native._rpc = incomplete
        with self.assertRaises(Refusal): successor.loaded_profile(host, native, command['id'], self.brain)
        self.assertNotIn('turn/start', native.calls)

    def test_expired_successor_never_starts_or_renews_clock(self):
        command = self.sending(); host = AppServerWake(self.binding, self.target)
        expires = standard.read(self.target)['run']['expiresAt']
        with patch.object(successor.time, 'time', return_value=expires+1):
            native = self.fake()
            with self.assertRaisesRegex(Refusal, 'expired'): successor.loaded_profile(host, native, command['id'], self.brain)
        self.assertEqual(standard.read(self.target)['run']['expiresAt'], expires)
        self.assertEqual(native.calls, []); self.assert_source_unchanged()

    def test_private_review_rejects_extra_safety_or_authority_fields(self):
        p = self.prepare(); path = self.binding_path.parent/'review.json'
        path.write_text(canonical(p['request'])); path.chmod(0o600)
        self.assertEqual(successor.read_request(path), p['request'])
        changed = copy.deepcopy(p['request']); changed['terminalSafe'] = True
        path.write_text(canonical(changed))
        with self.assertRaises(Refusal): successor.read_request(path)

    def test_tracker_unknown_or_running_blocks_without_native_effect(self):
        command = self.sending(); host = AppServerWake(self.binding, self.target)
        native = self.fake(terminals=[{'itemId': 'item', 'processId': 'handle'}])
        with self.assertRaises(Refusal): successor.loaded_profile(host, native, command['id'], self.brain)
        self.assertNotIn('thread/resume', native.calls); self.assertNotIn('turn/start', native.calls)

    def test_pause_race_does_not_start_or_renew(self):
        command = self.sending(); host = AppServerWake(self.binding, self.target)
        fired = False
        def pause(method):
            nonlocal fired
            if method == 'thread/effectivePolicy/read' and not fired:
                fired = True
                with self.target.tx() as db:
                    meta = self.target.get(db, 'meta', 1); meta['standardRun']['status'] = 'stopping'
                    self.target.put(db, 'meta', 1, meta)
        native = self.fake(callback=pause)
        with self.assertRaisesRegex(Refusal, 'Pause or successor state changed'):
            successor.loaded_profile(host, native, command['id'], self.brain)
        with self.assertRaises(Refusal): successor.loaded_profile(host, self.fake(), command['id'], self.brain)
        self.assertNotIn('turn/start', native.calls)

    def test_wrong_loaded_policy_never_becomes_configuration_acknowledgement(self):
        command = self.sending(); native = self.fake(); call = native._rpc
        def wrong(method, params):
            value = call(method, params)
            if method == 'thread/effectivePolicy/read': value['policy']['codeModeOffEnforced'] = False
            return value
        native._rpc = wrong
        with self.assertRaisesRegex(Refusal, 'loaded policy'):
            successor.loaded_profile(AppServerWake(self.binding, self.target), native, command['id'], self.brain)
        self.assertNotIn('thread/resume', native.calls)

    def test_new_phase_journal_can_reach_its_checkpoint_without_reusing_old_run(self):
        command = self.sending(); native = self.fake(); host = AppServerWake(self.binding, self.target)
        with patch.object(host, 'configured', return_value=True), patch('orchestrator.app_server_wake.validate_endpoint'), \
             patch('orchestrator.app_server_wake.WakeProxy', return_value=native), \
             patch('orchestrator.app_server_wake.threading.Thread', FakeThread):
            delivered = host.send(self.brain, 'Fixture pointer', command['id'])
        self.assertEqual(delivered['status'], 'accepted')
        with self.target.tx() as db:
            saved = self.target.get(db, 'commands', command['id']); saved['notification'].update(delivered)
            self.target.put(db, 'commands', command['id'], saved)
        token = self.target.acquire(self.brain+':disposable')
        run_id = command['payload']['runId']
        def action(operation, **values):
            return standard.brain(self.registry, self.target, token, {'operation': operation, 'runId': run_id, **values})
        action('receive')
        from orchestrator import standard_host_inspection as inspection
        from orchestrator import native_policy_evidence
        context = inspection._context(self.registry, self.target, token, run_id, command['id'])
        with patch.object(inspection, 'load_binding', return_value=self.binding), \
             patch.object(native_policy_evidence, 'PolicyReadProxy', return_value=native):
            report = inspection._collect(self.registry, self.target, token, run_id, command['id'], context)
        self.assertEqual(report['version'], 2); self.assertIn('loadedProfile', report)
        self.assertNotIn('resumeProfile', report); self.assertEqual(report['issues'], [])
        # Exercise the real observer-mailbox validator, not a sandbox socket
        # fallback or a synthetic policy receipt authored by the brain.
        def service(_):
            inspection.service_request(self.target, self.binding, command['id'], self.brain, delivered['nativeTurnId'])
        with patch.object(inspection, 'load_binding', return_value=self.binding), \
             patch.object(native_policy_evidence, 'PolicyReadProxy', return_value=native), \
             patch.object(inspection.time, 'sleep', side_effect=service):
            broker_report = inspection.inspect(self.registry, self.target, token, run_id, command['id'])
        self.assertEqual(broker_report['version'], 2); self.assertNotIn('resumeProfile', broker_report)
        action('claim', id='worker', repository='a', title='Disposable task', paths=['tests/test_fixture.py'],
               instructions='Fixture only', acceptance=['Local fixture'], model='fixture', effort='low',
               rationale='Disposable contract exercise', allowance=10000)
        action('issue', taskId='worker')
        action('bind', taskId='worker', threadId=str(uuid.uuid4()), clientThreadId=None, hostId='local')
        action('observe', taskId='worker', nativeStatus='completed', trackedTerminals='none', observedTokens=100,
               observedAt=time.time(), source='Synthetic disposable task metadata')
        action('finish', taskId='worker', outcome='completed', evidence={'source': 'Synthetic fixture',
            'tests': 'Synthetic local result', 'artifacts': [], 'preservation': 'Disposable fixture', 'summary': 'Not a live pilot'})
        action('checkpoint', outcome='completed', summary='Disposable successor checkpoint only', brainObservedTokens=200)
        self.assertEqual(standard.read(self.target)['run']['status'], 'completed')
        self.assertNotEqual(run_id, self.source.snapshot()['meta']['standardRun']['id'])
        self.assert_source_unchanged(); self.assertNotIn('thread/resume', native.calls)


if __name__ == '__main__': unittest.main()
