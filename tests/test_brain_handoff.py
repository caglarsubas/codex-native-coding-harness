import json
from pathlib import Path
import time
import unittest
import uuid

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
        codex = self.fixture.root / 'codex'
        log_dir = codex / 'sessions' / '2026' / '09' / '24'
        log_dir.mkdir(parents=True)
        (log_dir / ('rollout-fixture-' + self.new_id + '.jsonl')).write_text(json.dumps({
            'type': 'session_meta', 'payload': {'id': self.new_id, 'cwd': str(self.fixture.repo)}}) + '\n')
        (self.ledger.root / 'observations.json').write_text(json.dumps({'codexHome': str(codex)}))
        receipt = {'handoffId': prepared['id'], 'taskId': self.new_id,
                   'packageHash': prepared['payload']['packageHash'],
                   'summary': 'I read the retained checkpoint and will await owner confirmation.'}
        brain_handoff.receipt(self.ledger, receipt)
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
