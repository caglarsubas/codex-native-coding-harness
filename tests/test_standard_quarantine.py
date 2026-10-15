"""Disposable disposition only; no live host, load, wake or cleanup assertion."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import time
import io
import sys

from orchestrator import standard_quarantine as quarantine, standard, core
from orchestrator.core import Ledger, Refusal, canonical, digest
from orchestrator.workspaces import fingerprint
import test_standard_host_inspection as fixtures


class QuarantineTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.HostInspectionTest(methodName='runTest'); self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.ledger, self.registry = self.f.ledger, self.f.registry
        self.f.update(nativeTurnStatus='completed', nativeThreadObservation={
            'rootThreadId': self.f.fixture.brain_id, 'nativeTurnId': 'owned-turn-1',
            'streamStatus': 'closed', 'events': []})
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1)
            meta.update(controller=None, paused=True)
            meta['standardRun'].update(status='paused', tasks=[], expiresAt=time.time()-1,
                                       brainObservedTokens=1049625, usageHighWater=1049625,
                                       brainUsageCoverage='observed_partial')
            self.ledger.put(db, 'meta', 1, meta)
        self.old = self.ledger.snapshot()

    def prepare(self): return quarantine.prepare(self.registry, self.ledger)

    def confirm(self, proposal=None):
        proposal = proposal or self.prepare()
        return quarantine.confirm(self.registry, self.ledger, proposal['request'], proposal['reviewHash'])

    def test_preview_is_read_only_has_no_timer_and_grants_no_continuation(self):
        with standard.read_db(self.ledger.db) as db: before = fingerprint(db)
        files = set(self.ledger.root.iterdir()); p = self.prepare()
        self.assertEqual(p['validUntil'], 'scope_changes')
        self.assertFalse(any(v is True for v in p['request']['boundary'].values()))
        self.assertEqual(p['request']['state']['meta']['standardRun'], self.old['meta']['standardRun'])
        with standard.read_db(self.ledger.db) as db: self.assertEqual(before, fingerprint(db))
        self.assertEqual(files, set(self.ledger.root.iterdir()))
        self.assertEqual(self.f.fixture.fake.calls, [])

    def test_disposition_preserves_originals_and_is_not_a_terminal_settlement(self):
        result = self.confirm(); current = self.ledger.snapshot()
        self.assertEqual(result['outcome'], 'quarantined_unqualified')
        self.assertEqual(current['meta']['standardRun'], self.old['meta']['standardRun'])
        self.assertEqual(current['commands'], self.old['commands'])
        self.assertEqual(current['meta']['schemaVersion'], 6)
        self.assertFalse(current['meta']['pilotPassed'])
        self.assertEqual(current['meta']['standardRun']['usageHighWater'], 1049625)
        self.assertEqual(quarantine.status(self.ledger)['status'], 'quarantined_unqualified')
        self.assertEqual((self.ledger.root/quarantine.FENCE).stat().st_mode & 0o777, 0o600)

    def test_exact_repeated_confirmation_returns_original_receipt_without_write(self):
        p = self.prepare(); first = self.confirm(p)
        with standard.read_db(self.ledger.db) as db: before = fingerprint(db)
        self.assertEqual(first, self.confirm(p))
        with standard.read_db(self.ledger.db) as db: self.assertEqual(before, fingerprint(db))
        changed = copy.deepcopy(p); changed['request']['captureHash'] = 'a'*64
        changed['reviewHash'] = digest(changed['request'])
        with self.assertRaises(Refusal): self.confirm(changed)

    def test_all_normal_transactions_and_old_helpers_are_fenced(self):
        self.confirm()
        for operation in (lambda: self.ledger.acquire('owner'),
                          lambda: self.ledger.submit({'id': 'new-resume', 'kind': 'resume',
                              'expectedRevision': self.old['meta']['revision'], 'payload': {}}),
                          lambda: self.ledger.initialize({}),
                          lambda: standard.acquire_private(self.ledger, self.old['meta']['brainId']+':new')):
            with self.assertRaises(Refusal): operation()
        with patch.object(core, 'LEDGER_VERSIONS', (1, 2, 3, 4, 5)):
            with self.assertRaises(Refusal): Ledger(self.ledger.root)
        reopened = Ledger(self.ledger.root)
        with self.assertRaises(Refusal):
            with reopened.tx(): pass

    def test_partial_claim_never_retries_or_releases_ownership(self):
        p = self.prepare()
        with patch.object(self.ledger, 'put', side_effect=OSError('Synthetic commit failure')):
            with self.assertRaises(OSError): self.confirm(p)
        self.assertEqual(self.ledger.snapshot()['meta'], self.old['meta'])
        self.assertEqual(quarantine.status(self.ledger)['status'], 'quarantine_incomplete_or_changed')
        with self.assertRaises(Refusal): self.confirm(p)
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass

    def test_damaged_or_deleted_file_does_not_reopen_schema_marker(self):
        self.confirm(); path = self.ledger.root/quarantine.FENCE
        path.write_text('{}')
        self.assertTrue(quarantine.status(self.ledger)['writesBlocked'])
        path.unlink()
        self.assertTrue(quarantine.status(self.ledger)['writesBlocked'])
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass

    def test_scope_usage_or_revision_drift_invalidates_review(self):
        p = self.prepare()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1); meta['standardRun']['brainObservedTokens'] += 1
            self.ledger.put(db, 'meta', 1, meta)
        with self.assertRaisesRegex(Refusal, 'scope changed'): self.confirm(p)
        self.assertFalse((self.ledger.root/quarantine.FENCE).exists())

    def test_unknown_delivery_approval_or_descendant_never_qualifies(self):
        for changes in ({'status': 'uncertain'}, {'nativeApprovals': [{}]},
                        {'nativeThreadObservation': {'streamStatus': 'unconfirmed'}},
                        {'nativeTurnStatus': 'unconfirmed'}):
            old = copy.deepcopy(self.f.note); self.f.update(**changes)
            with self.assertRaises(Refusal): self.prepare()
            self.f.note = old; self.f.update()

    def test_nonexpired_nonempty_or_owned_runs_refuse(self):
        for edit in (lambda m: m['standardRun'].update(expiresAt=time.time()+3600),
                     lambda m: m['standardRun'].update(tasks=[{'id': 'task'}]),
                     lambda m: m.update(controller={'owner': 'native'}),
                     lambda m: m.update(runner={'workerId': 'worker'}),
                     lambda m: m.update(schemaVersion=3)):
            with self.ledger.tx() as db:
                meta = copy.deepcopy(self.old['meta']); edit(meta); self.ledger.put(db, 'meta', 1, meta)
            with self.assertRaises(Refusal): self.prepare()
        self.assertFalse((self.ledger.root/quarantine.FENCE).exists())

    def test_private_review_shape_hash_and_aliases_refuse(self):
        p = self.prepare(); path = self.ledger.root.parent/'review.json'
        path.write_text(canonical(p['request'])); path.chmod(0o600)
        self.assertEqual(quarantine.read_request(path), p['request'])
        altered = copy.deepcopy(p['request']); altered['terminalSafe'] = True
        path.write_text(canonical(altered))
        with self.assertRaises(Refusal): quarantine.read_request(path)
        with self.assertRaises(Refusal): quarantine.confirm(self.registry, self.ledger, p['request'], 'x'*64)

    def test_cross_workspace_repository_hold_is_retained(self):
        self.confirm()
        base = self.f.fixture.fixture
        other, token = base.workspace('beta')
        base.control(ledger=other); base.call('receive', ledger=other, token=token)
        with self.assertRaisesRegex(Refusal, 'quarantined attempt'):
            base.call('claim', ledger=other, token=token, id='task', repository='a', title='Fixture',
                      paths=['tests/test_fixture.py'], instructions='Fixture only', acceptance=['Test'],
                      model='fixture', effort='low', rationale='Fixture', allowance=10000)

    def test_saved_projection_never_offers_eligible_workers_or_resume(self):
        self.confirm(); value = standard.read(self.ledger)
        self.assertFalse(value['available'])
        self.assertEqual(value['parallelEligibility']['currentlyEligible'], 0)
        self.assertEqual(value['observedTokens'], 1049625)
        self.assertEqual(value['quarantine']['boundary']['currentTerminalSafety'], 'unknown')

    def test_foreign_owner_before_disposition_prevents_overlapping_hold(self):
        base = self.f.fixture.fixture
        other, token = base.workspace('beta')
        base.control(ledger=other); base.call('receive', ledger=other, token=token)
        base.call('claim', ledger=other, token=token, id='task', repository='a', title='Fixture',
                  paths=['tests/test_fixture.py'], instructions='Fixture', acceptance=['Test'],
                  model='fixture', effort='low', rationale='Fixture', allowance=10000)
        with self.assertRaisesRegex(Refusal, 'Conflicting foreign ownership'): self.prepare()

    def test_public_creation_capacity_rechecks_quarantine_hold(self):
        self.confirm(); base = self.f.fixture.fixture
        other, token = base.workspace('beta')
        base.control(ledger=other); base.call('receive', ledger=other, token=token)
        from orchestrator.public_native_tasks import _capacity_in
        with self.registry.tx() as registry_db, standard.read_db(other.db) as db:
            run = other.get(db, 'meta', 1)['standardRun']
            task = {'repositoryIdentity': next(iter(self.old['meta']['standardRun']['identities'].values()))}
            with self.assertRaisesRegex(Refusal, 'before native creation/turn'):
                _capacity_in(registry_db, other, db, run, task)

    def test_corrupt_foreign_claim_cannot_appear_as_free_capacity(self):
        self.confirm(); (self.ledger.root/quarantine.FENCE).write_text('{}')
        with standard.read_db(self.ledger.db) as db:
            with self.assertRaises(Refusal): quarantine.repository_holds(self.ledger.root, db, self.ledger.get(db, 'meta', 1))

    def test_original_binding_is_bytes_only_and_drift_refuses(self):
        from orchestrator.standard_host_inspection import binding_file
        from orchestrator.native_read_client import ReadProxy
        with patch.object(ReadProxy, '__enter__', side_effect=AssertionError('No native connection')):
            p = self.prepare()
        path = binding_file(self.ledger, self.f.key)
        value = json.loads(path.read_bytes()); value['brains'][self.f.fixture.brain_id]['projectId'] = 'changed'
        path.write_text(canonical(value))
        with self.assertRaisesRegex(Refusal, 'Original binding changed'): self.confirm(p)

    def test_cli_routes_require_exact_workspace_and_lifecycle_is_file_only(self):
        from orchestrator.cli import main
        argv = ['cli', '--platform', str(self.registry.root), '--workspace', 'alpha', 'standard-quarantine-preview']
        with patch.object(sys, 'argv', argv), patch('sys.stdout', new_callable=io.StringIO) as output:
            main(); result = json.loads(output.getvalue())
        self.assertEqual(result['reviewHash'], self.prepare()['reviewHash'])
        argv[-1] = 'standard-lifecycle-capture'; argv.append(self.f.command_id)
        with patch.object(sys, 'argv', argv), patch('sys.stdout', new_callable=io.StringIO) as output:
            main(); result = json.loads(output.getvalue())
        self.assertEqual(result['status'], 'not_enabled_at_original_boundary')


if __name__ == '__main__': unittest.main()
