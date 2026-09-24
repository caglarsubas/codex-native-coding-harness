import json
import datetime as dt
import contextlib
import io
import os
from pathlib import Path
import sys
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator.core import Refusal
from orchestrator import brain_handoff, projects
from test_standard import StandardTest


class BrainHandoffTest(unittest.TestCase):
    def setUp(self):
        self.fixture = StandardTest('test_owner_preview_bound_to_session_content_and_stale_state')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.ledger, self.registry = self.fixture.ledger, self.fixture.registry
        catalog = projects.record(self.registry, {'schemaVersion': 2, 'projects': [{
            'projectId': 'native-a', 'projectKind': 'local', 'label': 'Fixture project',
            'hostId': 'local', 'path': str(self.fixture.repo), 'isGitRepository': True}]}, time.time())
        projects.bind(self.registry, 'alpha', 'local', 'native-a', catalog['hash'])
        self.fixture.control()
        self.fixture.call('checkpoint', outcome='paused', summary='Owner checkpoint reached.', brainObservedTokens=500)
        self.ledger.release(self.fixture.token, 'Controller released at saved checkpoint')
        self.controls = brain_handoff.Controls()
        self.new_id = str(uuid.uuid4())

    def prepare(self):
        preview = self.controls.preview(self.registry, self.ledger, 'owner-session')
        return self.controls.confirm(self.registry, self.ledger, {**preview, 'confirmed': True}, 'owner-session')

    def _write_native_log(self, prepared, *, marker=True, phase='final_answer', recorded_at=None):
        codex = self.fixture.root / 'codex'
        log_dir = codex / 'sessions' / '2026' / '09' / '24'
        log_dir.mkdir(parents=True, exist_ok=True)
        receipt = {'handoffId': prepared['id'], 'taskId': self.new_id,
                   'packageHash': prepared['payload']['packageHash'],
                   'summary': 'I read the retained checkpoint and will await owner confirmation.'}
        content = brain_handoff.receipt_marker(receipt) if marker else 'No package acknowledgment in this reply.'
        records = [
            {'type': 'session_meta', 'payload': {'id': self.new_id, 'cwd': str(self.fixture.repo)}},
            {'type': 'response_item', 'timestamp': dt.datetime.fromtimestamp(time.time() if recorded_at is None else recorded_at, dt.timezone.utc).isoformat(),
             'payload': {'type': 'message', 'role': 'assistant', 'phase': phase,
                         'content': [{'type': 'output_text', 'text': 'Checkpoint reviewed.\n' + content}]}}
        ]
        (log_dir / ('rollout-fixture-' + self.new_id + '.jsonl')).write_text(''.join(json.dumps(row) + '\n' for row in records))
        (self.ledger.root / 'observations.json').write_text(json.dumps({'codexHome': str(codex)}))
        return receipt

    def _native_result(self, **changes):
        row = {'id': self.new_id, 'kind': 'codex', 'projectId': 'native-a',
               'hostId': 'local', 'status': 'idle', 'title': 'Replacement task', **changes}
        return {'schemaVersion': 4, 'threads': [row], 'pinnedThreads': [],
                'unavailableHosts': [], 'unavailableSources': []}

    def test_owner_confirmed_handoff_retains_usage_and_binding(self):
        prepared = self.prepare()
        self.assertEqual(prepared['kind'], 'brain_handoff')
        old = self.ledger.snapshot()['meta']['brainId']
        token = self.ledger.acquire(old + ':handoff')
        candidate = {'handoffId': prepared['id'], 'taskId': self.new_id, 'projectId': 'native-a',
                     'hostId': 'local', 'observation': 'Codex native task/project identity observed'}
        brain_handoff.candidate(self.ledger, token, candidate)
        with self.assertRaises(Refusal):
            brain_handoff.candidate(self.ledger, token, {**candidate, 'taskId': str(uuid.uuid4())})
        self.ledger.release(token, 'Candidate recorded; old brain stopped')
        receipt = self._write_native_log(prepared)
        brain_handoff.receipt(self.ledger, receipt)
        token = self.ledger.acquire(old + ':membership')
        brain_handoff.native_observation(self.ledger, token, self._native_result(), time.time())
        self.ledger.release(token, 'Replacement idle after final reply')
        self.assertEqual(self.ledger.snapshot()['meta']['brainHandoff']['receiptEvidence']['source'], 'local_native_final_reply')
        self.assertEqual(len(self.ledger.snapshot()['meta']['brainHandoff']['receiptEvidence']['recordHash']), 64)
        self.assertEqual(self.ledger.snapshot()['meta']['brainHandoff']['nativeMembership']['source'], 'codex.list_threads')
        final = self.controls.finalize_preview(self.registry, self.ledger, 'owner-session')
        with self.registry.tx() as db:
            old_row = db.execute("SELECT data FROM workspaces WHERE id='alpha'").fetchone()[0]
            old_binding = db.execute("SELECT data FROM project_bindings WHERE workspace='alpha'").fetchone()[0]
        with self.assertRaises(Refusal):
            self.controls.finalize(self.registry, self.ledger, {**final, 'confirmed': True}, 'other-session')
        result = self.controls.finalize(self.registry, self.ledger,
                                        {'preview': final['preview'], 'signature': final['signature'], 'confirmed': True},
                                        'owner-session')
        self.assertEqual(result['newBrainId'], self.new_id)
        self.assertEqual(self.registry.ledger('alpha').snapshot()['meta']['brainId'], self.new_id)
        run = self.registry.ledger('alpha').snapshot()['meta']['standardRun']
        self.assertEqual(run['status'], 'paused')
        self.assertEqual(run['brainObservedTokens'], 500)
        self.assertEqual([part['id'] for part in run['brainSegments']], [old, self.new_id])
        self.assertEqual(projects.catalog(self.registry)['projects'][0]['bindingStatus'], 'linked')
        with self.assertRaises(Refusal):
            self.controls.finalize(self.registry, self.ledger,
                                   {'preview': final['preview'], 'signature': final['signature'], 'confirmed': True},
                                   'owner-session')
        # Emulate a process interruption after the ledger commit but before
        # the registry commit. Ordinary project opening must fail closed until
        # an exact owner repair finishes only the second binding.
        with self.registry.tx() as db:
            db.execute("UPDATE workspaces SET brain=?,data=? WHERE id='alpha'", (old, old_row))
            db.execute("UPDATE project_bindings SET data=? WHERE workspace='alpha'", (old_binding,))
        with self.assertRaises(Refusal):
            self.registry.root_for('alpha')
        with self.assertRaises(Refusal):
            brain_handoff.recover_registry(self.registry, 'alpha', prepared['id'], False)
        repaired = brain_handoff.recover_registry(self.registry, 'alpha', prepared['id'], True)
        self.assertEqual(repaired['status'], 'recovered')
        self.assertEqual(self.registry.ledger('alpha').snapshot()['meta']['brainId'], self.new_id)
        self.assertEqual(brain_handoff.recover_registry(self.registry, 'alpha', prepared['id'], True)['status'],
                         'already_consistent')

    def test_wrong_project_and_unobserved_native_checkout_refused(self):
        prepared = self.prepare()
        old = self.ledger.snapshot()['meta']['brainId']
        token = self.ledger.acquire(old + ':handoff')
        wrong = {'handoffId': prepared['id'], 'taskId': self.new_id, 'projectId': 'different',
                 'hostId': 'local', 'observation': 'Native task was seen in another project'}
        with self.assertRaises(Refusal): brain_handoff.candidate(self.ledger, token, wrong)
        brain_handoff.candidate(self.ledger, token, {**wrong, 'projectId': 'native-a'})
        self.ledger.release(token, 'Candidate recorded')
        with self.assertRaises(Refusal):
            brain_handoff.receipt(self.ledger, {'handoffId': prepared['id'], 'taskId': self.new_id,
                'packageHash': prepared['payload']['packageHash'],
                'summary': 'I read the checkpoint and am ready to await owner review.'})
        self.assertEqual(self.ledger.snapshot()['meta']['brainId'], old)

    def test_native_task_membership_is_required_and_cross_project_results_refuse(self):
        prepared = self.prepare()
        old = self.ledger.snapshot()['meta']['brainId']
        token = self.ledger.acquire(old + ':handoff')
        brain_handoff.candidate(self.ledger, token, {'handoffId': prepared['id'], 'taskId': self.new_id,
            'projectId': 'native-a', 'hostId': 'local', 'observation': 'Native project and task observed in Codex'})
        for result in (self._native_result(projectId='other'), self._native_result(hostId='other'),
                       self._native_result(id=str(uuid.uuid4())),
                       self._native_result(status='notLoaded'),
                       {**self._native_result(), 'unavailableHosts': ['local']},
                       {**self._native_result(), 'pinnedThreads': self._native_result()['threads']}):
            with self.assertRaises(Refusal):
                brain_handoff.native_observation(self.ledger, token, result, time.time())
        with self.assertRaises(Refusal):
            brain_handoff.native_observation(self.ledger, token, self._native_result(), prepared['createdAt'] - 1)
        self.ledger.release(token, 'Candidate recorded')
        receipt = self._write_native_log(prepared)
        brain_handoff.receipt(self.ledger, receipt)
        with self.assertRaises(Refusal):
            self.controls.finalize_preview(self.registry, self.ledger, 'owner-session')
        token = self.ledger.acquire(old + ':active-membership')
        brain_handoff.native_observation(self.ledger, token, self._native_result(status='active'), time.time())
        self.ledger.release(token, 'Active replacement observed')
        with self.assertRaises(Refusal):
            self.controls.finalize_preview(self.registry, self.ledger, 'owner-session')

    def test_cli_imports_bounded_native_task_observation(self):
        from orchestrator.cli import main
        prepared = self.prepare()
        old = self.ledger.snapshot()['meta']['brainId']
        token = self.ledger.acquire(old + ':handoff')
        brain_handoff.candidate(self.ledger, token, {'handoffId': prepared['id'], 'taskId': self.new_id,
            'projectId': 'native-a', 'hostId': 'local', 'observation': 'Native project and task observed in Codex'})
        path = self.fixture.root / 'native-task-list.json'
        path.write_text(json.dumps(self._native_result()))
        argv = ['orchestrator', '--platform', str(self.registry.root), '--workspace', 'alpha',
                'brain-handoff-native-observation', str(path), '--observed-at', str(time.time())]
        with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'ORCHESTRATOR_CONTROLLER_TOKEN': token}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            main()
        self.assertEqual(json.loads(output.getvalue())['nativeMembership']['projectId'], 'native-a')
        self.ledger.release(token, 'Native membership retained')
        brain_handoff.receipt(self.ledger, self._write_native_log(prepared))
        with self.assertRaises(Refusal):
            self.controls.finalize_preview(self.registry, self.ledger, 'owner-session')
        token = self.ledger.acquire(old + ':membership')
        observed_at = time.time()
        brain_handoff.native_observation(self.ledger, token, self._native_result(), observed_at)
        brain_handoff.native_observation(self.ledger, token, self._native_result(), observed_at)
        with self.assertRaises(Refusal):
            brain_handoff.native_observation(self.ledger, token, self._native_result(title='Changed result'), observed_at)
        self.ledger.release(token, 'Native membership recorded')
        final = self.controls.finalize_preview(self.registry, self.ledger, 'owner-session')
        self.assertEqual(final['handoff']['status'], 'received')
        token = self.ledger.acquire(old + ':membership-refresh')
        brain_handoff.native_observation(self.ledger, token, self._native_result(title='Refreshed result'), time.time() + 0.01)
        self.ledger.release(token, 'Membership refreshed')
        with self.assertRaises(Refusal):
            self.controls.finalize(self.registry, self.ledger,
                                   {'preview': final['preview'], 'signature': final['signature'], 'confirmed': True},
                                   'owner-session')
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1)
            meta['brainHandoff']['nativeMembership']['observedAt'] -= 7200
            self.ledger.put(db, 'meta', 1, meta)
        with self.assertRaises(Refusal):
            self.controls.finalize_preview(self.registry, self.ledger, 'owner-session')

    def test_receipt_requires_exact_final_reply_after_preparation(self):
        prepared = self.prepare()
        old = self.ledger.snapshot()['meta']['brainId']
        token = self.ledger.acquire(old + ':handoff')
        brain_handoff.candidate(self.ledger, token, {'handoffId': prepared['id'], 'taskId': self.new_id,
            'projectId': 'native-a', 'hostId': 'local', 'observation': 'Native project and task observed in Codex'})
        self.ledger.release(token, 'Candidate recorded')
        for options in ({'marker': False}, {'phase': 'commentary'},
                        {'recorded_at': self.ledger.snapshot()['meta']['brainHandoff']['createdAt'] - 60}):
            receipt = self._write_native_log(prepared, **options)
            with self.assertRaises(Refusal):
                brain_handoff.receipt(self.ledger, receipt)
            self.assertEqual(self.ledger.snapshot()['meta']['brainId'], old)
        receipt = self._write_native_log(prepared)
        with self.assertRaises(Refusal):
            brain_handoff.receipt(self.ledger, {**receipt, 'summary': 'A different summary claiming to have read the package.'})
        self.assertEqual(brain_handoff.receipt(self.ledger, receipt)['status'], 'received')
        self.assertEqual(brain_handoff.receipt(self.ledger, receipt)['status'], 'received')

    def test_active_worker_and_unresolved_creation_block_preview(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1)
            meta['standardRun']['tasks'].append({'id': 'active', 'status': 'running', 'threadId': self.new_id})
            self.ledger.put(db, 'meta', 1, meta)
        with self.assertRaises(Refusal):
            self.controls.preview(self.registry, self.ledger, 'owner-session')
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1)
            meta['standardRun']['tasks'][-1] = {'id': 'uncertain', 'status': 'not_created',
                                                   'threadId': None, 'effectIssued': True}
            self.ledger.put(db, 'meta', 1, meta)
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1)
            meta['standardRun']['tasks'][-1]['status'] = 'uncertain'
            self.ledger.put(db, 'meta', 1, meta)
        with self.assertRaises(Refusal):
            self.controls.preview(self.registry, self.ledger, 'owner-session')

    def test_stale_owner_preview_does_not_change_binding(self):
        preview = self.controls.preview(self.registry, self.ledger, 'owner-session')
        old = self.ledger.snapshot()['meta']['brainId']
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1)
            meta['standardRun']['revision'] += 1
            self.ledger.put(db, 'meta', 1, meta)
        with self.assertRaises(Refusal):
            self.controls.confirm(self.registry, self.ledger, {**preview, 'confirmed': True}, 'owner-session')
        self.assertEqual(self.ledger.snapshot()['meta']['brainId'], old)


if __name__ == '__main__':
    unittest.main()
