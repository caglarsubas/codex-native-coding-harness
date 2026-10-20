"""Disposable setup completion only. No native host, credentials or model calls."""
import contextlib
import copy
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator import empty_setup_transition as api, missions, projects, standard
from orchestrator.core import Ledger, Refusal, canonical, digest
from orchestrator.public_host_lifecycle import CONFIG
from orchestrator.workspaces import Registry, fingerprint
from test_native_policy_evidence import response


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.registry = Registry(self.root/'platform', create=True)
        self.checkout = self.root/'checkout'; self.checkout.mkdir(mode=0o700)
        self.home = self.root/'native-home'; self.home.mkdir(mode=0o700)
        self.records = self.root/'records'; self.records.mkdir(mode=0o700)
        self.old, self.brain, self.native, self.catalog = [str(uuid.uuid4()) for _ in range(4)]
        self.ledger = Ledger(self.root/'target')
        self.ledger.initialize({'schemaVersion': 1, 'brainId': self.old, 'repositories': [
            {'id': 'repo', 'path': str(self.checkout), 'projectId': 'old-catalog', 'ref': 'main',
             'mergePolicy': 'manual', 'policyProfile': 'standard'}]})
        self.registry.register('target', 'Target', self.ledger.root)
        self.ledger = self.registry.ledger('target')
        spec = {'goal': 'Offline function', 'successCriteria': ['Tests pass'], 'exclusions': ['No network'],
            'phase': {'id': 'one', 'title': 'One', 'objective': 'One function', 'checkpoint': 'Stop',
                'stopConditions': ['Pause'], 'durationHours': 24,
                'scope': [{'repository': 'repo', 'allowedPaths': ['summary.py'], 'operations': ['edit', 'test']}]},
            'authority': {'approvalMode': 'phase_delegated', 'tokenBudget': 120000,
                'checkpointReserveTokens': 10000, 'maxTasks': 1, 'maxParallelTasks': 1}}
        self.draft = missions.change(self.ledger, {'id': str(uuid.uuid4()), 'operation': 'save',
            'expectedRevision': 0, 'spec': spec})['current']
        self.other = Ledger(self.root/'old')
        self.other.initialize({'schemaVersion': 1, 'brainId': 'old-held-brain', 'repositories': []})
        with self.other.tx() as db:
            meta = Ledger.get(db, 'meta', 1)
            meta.update(oldUsage={'tokens': 101877, 'gaps': ['preserved']}, oldClaims=['consumed'])
            Ledger.put(db, 'meta', 1, meta)
        self.registry.register('old', 'Old held fixture', self.other.root)
        old_catalog = projects.record(self.registry, self.catalog_result('old-catalog'), 1)
        projects.bind(self.registry, 'target', 'local', 'old-catalog', old_catalog['hash'])
        self.config = self.home/'config.toml'
        self.write(self.config, CONFIG+'\n[projects.'+canonical(str(self.checkout))+']\ntrust_level = "trusted"\n', raw=True)
        self.endpoint = {'executable': '/fixture/bin/codex', 'sha256': 'a'*64,
            'socket': '/fixture/socket', 'socketIdentity': {}, 'serverIdentityHash': 'b'*64}
        self.spec = {'version': 1, 'kind': api.KIND, 'workspaceId': 'target', 'oldBrainId': self.old,
            'brainId': self.brain, 'nativeProjectId': self.native, 'catalogProjectId': self.catalog,
            'checkout': str(self.checkout), 'endpoint': self.endpoint, 'configFile': str(self.config),
            'originalConfigPin': {'sha256': hashlib.sha256(CONFIG.encode()).hexdigest(),
                'bytes': len(CONFIG.encode()), 'mode': 0o600}, 'setupRecords': {},
            'catalogObservation': str(self.records/'catalog.json')}
        self.write(self.spec['catalogObservation'], {'source': 'codex_app.list_projects',
            'observedAt': time.time(), 'completeResult': self.catalog_result(self.catalog)})
        operator = self.records/'original-operator.py'; self.write(operator, 'consumed fixture', raw=True)
        manifest = self.records/'launch-manifest.exact.json'
        self.write(manifest, {'configPin': self.spec['originalConfigPin'], 'runtimePackage': {'root': '/fixture'},
            'cwd': str(self.checkout), 'codexHome': str(self.home)})
        start = {'cwd': str(self.checkout), 'ephemeral': False, 'sandbox': 'workspace-write',
            'approvalPolicy': 'on-request', 'approvalsReviewer': 'user',
            'config': {'features': {'code_mode': {'enabled': False}}}}
        request = {'version': 1, 'kind': 'prospective_disjoint_v1_native_identity_setup_v1',
            'immutableInputs': [{'path': str(operator), 'sha256': api.pin(operator)['sha256'],
                'identity': list(api.file_identity(operator.lstat()))}, api.input_pin(manifest)],
            'target': {'workspaceId': 'target', 'root': str(self.checkout)},
            'predecessor': {'brainId': self.old},
            'reviewedHost': {'endpoint': self.endpoint, 'runtimePackage': {'root': '/fixture'}},
            'prospectiveNativeSetup': {'projectCreate': {'name': 'New empty project', 'roots': [{'path': str(self.checkout)}]},
                'threadStartParameters': start}}
        approval = digest(request)
        values = {'setupRequest': request, 'ownerApproval': {'reviewHash': approval,
            'exactHumanApproval': 'Approve prospective v1 native setup '+approval},
            'projectResult': self.project(), 'brainResult': self.thread(),
            'creatorObservations': {'samples': [self.sample(), self.sample()]}}
        for key, value in values.items():
            path = self.records/(key+'.json'); self.write(path, value); self.spec['setupRecords'][key] = str(path)
        intent = {'reviewHash': approval, 'maximumProjectCreates': 1, 'maximumBrainCreates': 1,
            'maximumLoads': 0, 'maximumTurns': 0, 'operatorSource': api.pin(operator),
            'requestPin': api.pin(self.spec['setupRecords']['setupRequest'])}
        path = self.records/'intent.json'; self.write(path, intent); self.spec['setupRecords']['applicationIntent'] = str(path)
        for key, method, params in (('projectClaim', 'project/create', request['prospectiveNativeSetup']['projectCreate']),
            ('brainClaim', 'thread/start', {**start, 'projectId': self.native})):
            path = self.records/(key+'.json')
            self.write(path, {'reviewHash': approval, 'method': method, 'params': params,
                'maximumAttempts': 1, 'retryPermitted': False, 'operatorSource': api.pin(operator),
                'endpointHash': digest(self.endpoint)})
            self.spec['setupRecords'][key] = str(path)
        self.status = 'notLoaded'; self.calls = []
        self.history = {'data': [], 'nextCursor': None, 'backwardsCursor': None}
        fixture = self
        class FakeProxy:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def _rpc(self, method, params):
                fixture.calls.append((method, copy.deepcopy(params)))
                if method == 'project/read': return fixture.project()
                if method == 'thread/read': return fixture.thread(fixture.status)
                if method == 'thread/effectivePolicy/read':
                    return ({'version': 1, 'threadId': fixture.brain, 'policy': None}
                        if fixture.status == 'notLoaded' else response(fixture.brain, str(fixture.checkout)))
                if method == 'thread/turns/list': return copy.deepcopy(fixture.history)
                raise AssertionError('Unexpected native operation '+method)
        for mock in (patch.object(api, 'validate_endpoint'), patch('orchestrator.public_host_runtime.validate_pin'),
            patch.object(api, 'SetupReadProxy', return_value=FakeProxy())):
            mock.start(); self.addCleanup(mock.stop)

    def write(self, path, value, raw=False):
        path = Path(path); path.write_text(value if raw else canonical(value)); path.chmod(0o600)

    def catalog_result(self, pid):
        return {'schemaVersion': 2, 'projects': [{'projectKind': 'local', 'projectId': pid,
            'hostId': 'local', 'label': 'Target', 'path': str(self.checkout), 'isGitRepository': True}]}

    def project(self): return {'project': {'id': self.native, 'roots': [{'path': str(self.checkout)}]}}

    def thread(self, status='idle'):
        return {'thread': {'id': self.brain, 'projectId': self.native, 'cwd': str(self.checkout),
            'ephemeral': False, 'turns': [], 'status': {'type': status}}}

    def sample(self): return {'project': self.project(), 'thread': self.thread(),
        'policy': response(self.brain, str(self.checkout))}

    def preview(self): return api.preview(self.registry, 'target', self.spec)

    def confirm(self, preview=None, **kw):
        preview = preview or self.preview()
        return api.confirm(self.registry, 'target', preview['request'], preview['reviewHash'],
            confirmed=True, writers_stopped=True, fresh_catalog=self.spec['catalogObservation'], **kw)

    def contents(self, path):
        with standard.read_db(path) as db: return fingerprint(db)


class SetupTransitionTest(Fixture):
    def test_preview_is_non_mutating_unloaded_is_unknown_and_reads_are_exact(self):
        before = {p: self.contents(p) for p in (self.ledger.db, self.registry.db, self.other.db)}
        result = self.preview()
        self.assertEqual(result['native']['status'], 'notLoaded')
        self.assertFalse(result['native']['currentPolicyQualified'])
        self.assertEqual(result['native']['currentTerminalSafety'], 'unknown')
        self.assertEqual(result['request']['boundary'], api.BOUNDARY)
        self.assertEqual(before, {p: self.contents(p) for p in before})
        self.assertEqual([method for method, _ in self.calls],
            ['project/read', 'thread/read', 'thread/effectivePolicy/read', 'thread/turns/list']*2)
        self.assertFalse((self.ledger.root/api.FENCE).exists())

    def test_confirm_preserves_old_records_other_ledgers_and_creates_only_new_draft(self):
        other = self.contents(self.other.db); before = self.contents(self.ledger.db)
        immutable = {path: Path(path).read_bytes() for path in self.spec['setupRecords'].values()}
        with standard.read_db(self.ledger.db) as db:
            original_draft = Ledger.get(db, 'snapshots', self.draft['documentHash'])
        receipt = self.confirm()
        self.assertFalse(any(receipt['boundary'].values()))
        selected = self.registry.ledger('target'); meta = selected.snapshot()['meta']
        self.assertEqual(meta['brainId'], self.brain); self.assertTrue(meta['paused'])
        self.assertNotIn('standardRun', meta)
        current = missions.read(selected)
        self.assertEqual(current['effectiveStatus'], 'draft')
        self.assertEqual(current['document']['previousHash'], self.draft['documentHash'])
        self.assertEqual(current['document']['brainId'], self.brain)
        with standard.read_db(selected.db) as db:
            self.assertEqual(Ledger.get(db, 'snapshots', self.draft['documentHash']), original_draft)
        after = self.contents(selected.db)
        for table in before:
            if table not in ('meta', 'repos', 'snapshots'): self.assertEqual(after[table], before[table])
        self.assertEqual(self.contents(self.other.db), other)
        self.assertEqual(immutable, {path: Path(path).read_bytes() for path in immutable})
        self.assertTrue(projects.catalog(self.registry)['projects'][0]['managed'])
        backups = self.registry.root/'backups'/receipt['backupId']
        self.assertEqual(backups.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in backups.iterdir()))

    def test_identical_confirmation_is_receipt_only_no_rebind_or_native_read(self):
        proposal = self.preview(); receipt = self.confirm(proposal)
        self.calls.clear(); before = self.contents(self.registry.db)
        self.assertEqual(self.confirm(proposal), receipt)
        self.assertEqual(self.calls, []); self.assertEqual(before, self.contents(self.registry.db))
        with self.registry.tx() as db:
            db.execute("UPDATE workspaces SET name='Later' WHERE id='target'")
        self.assertEqual(self.confirm(proposal), receipt)
        with self.registry.tx() as db:
            self.assertEqual(db.execute("SELECT name FROM workspaces WHERE id='target'").fetchone()[0], 'Later')

    def test_approval_and_stopped_writers_are_not_inferred(self):
        q = self.preview()
        for confirmed, stopped, hash_value in ((False, True, q['reviewHash']),
            (True, False, q['reviewHash']), (True, True, '0'*64)):
            with self.assertRaises(Refusal):
                api.confirm(self.registry, 'target', q['request'], hash_value, confirmed=confirmed,
                    writers_stopped=stopped, fresh_catalog=self.spec['catalogObservation'])
        self.assertFalse((self.ledger.root/api.FENCE).exists())

    def test_review_has_no_timer_expiry_but_actual_catalog_recheck_is_fresh(self):
        proposal = self.preview(); path = self.records/'fresh-catalog.json'
        later = time.time()+86400
        self.write(path, {'source': 'codex_app.list_projects', 'observedAt': later,
            'completeResult': self.catalog_result(self.catalog)})
        with patch.object(api.time, 'time', return_value=later):
            with self.assertRaisesRegex(Refusal, 'stale'):
                self.confirm(proposal)
            api.confirm(self.registry, 'target', proposal['request'], proposal['reviewHash'],
                confirmed=True, writers_stopped=True, fresh_catalog=path)

    def test_catalog_host_project_or_mapping_drift_refuses(self):
        q = self.preview()
        self.spec['catalogProjectId'] = str(uuid.uuid4())
        with self.assertRaises(Refusal): self.preview()
        self.spec = copy.deepcopy(q['request']['spec'])
        changed = self.catalog_result(self.catalog); changed['projects'][0]['hostId'] = 'foreign'
        path = self.records/'changed-catalog.json'
        self.write(path, {'source': 'codex_app.list_projects', 'observedAt': time.time(), 'completeResult': changed})
        with self.assertRaises(Refusal):
            api.confirm(self.registry, 'target', q['request'], q['reviewHash'], confirmed=True,
                writers_stopped=True, fresh_catalog=path)

    def test_original_claim_uncertainty_or_changed_result_never_retries(self):
        path = self.spec['setupRecords']['brainClaim']; value = api.read(path)
        value['retryPermitted'] = True; self.write(path, value)
        with self.assertRaises(Refusal): self.preview()
        self.assertEqual(self.calls, [])

    def test_native_active_missing_turn_or_nonempty_history_refuses_without_load(self):
        self.status = 'active'
        with self.assertRaises(Refusal): self.preview()
        self.status = 'notLoaded'; self.history['data'] = [{'id': 'unexpected-turn'}]
        with self.assertRaisesRegex(Refusal, 'empty native turn'): self.preview()
        self.assertTrue(all(method not in ('thread/resume', 'thread/start', 'turn/start') for method, _ in self.calls))

    def test_pinned_native_empty_history_schema_keeps_both_cursor_bounds(self):
        for history in ({'data': [], 'nextCursor': None},
            {'data': [], 'nextCursor': None, 'backwardsCursor': 'unseen'},
            {'data': [], 'nextCursor': 'unseen', 'backwardsCursor': None},
            {'data': [], 'nextCursor': None, 'backwardsCursor': None, 'unqualified': True}):
            with self.subTest(history=history):
                self.history = history
                with self.assertRaisesRegex(Refusal, 'empty native turn history'): self.preview()

    def test_reviewed_mission_and_any_request_or_ownership_history_refuse(self):
        missions.change(self.ledger, {'id': str(uuid.uuid4()), 'operation': 'review',
            'expectedRevision': self.draft['revision'], 'documentHash': self.draft['documentHash'], 'confirmed': True})
        with self.assertRaisesRegex(Refusal, 'Reviewed mission'): self.preview()

    def test_changed_source_scope_or_consumed_inputs_invalidate_review_before_claim(self):
        q = self.preview()
        with patch.object(api, 'source_hash', return_value='different'):
            with self.assertRaisesRegex(Refusal, 'context changed'): self.confirm(q)
        self.assertFalse((self.ledger.root/api.FENCE).exists())
        self.write(self.records/'original-operator.py', 'changed', raw=True)
        with self.assertRaisesRegex(Refusal, 'file epoch'): self.confirm(q)

    def test_dashboard_lock_and_foreign_database_change_refuse(self):
        from orchestrator.workspace_identity_recovery import dashboard_lock
        q = self.preview()
        with dashboard_lock(self.other.root), self.assertRaisesRegex(Refusal, 'Stop the dashboard'):
            self.confirm(q)
        with self.other.tx() as db:
            meta = Ledger.get(db, 'meta', 1); meta['oldClaims'].append('another')
            Ledger.put(db, 'meta', 1, meta)
        with self.assertRaisesRegex(Refusal, 'context changed'): self.confirm(q)

    def test_partial_commit_blocks_direct_and_registered_writes_and_never_retries(self):
        q = self.preview(); original = api.exclusive
        def fail_final(path, value):
            if path.name == api.RECEIPT: raise OSError('fixture flush failure')
            return original(path, value)
        with patch.object(api, 'exclusive', side_effect=fail_final), self.assertRaises(OSError): self.confirm(q)
        self.assertTrue((self.ledger.root/api.FENCE).exists())
        with self.assertRaises(Refusal): self.registry.ledger('target')
        with self.assertRaises(Refusal), self.ledger.tx(): pass
        self.calls.clear()
        with self.assertRaises(Refusal): self.confirm(q)
        self.assertEqual(self.calls, [])

    def test_only_exact_config_append_is_supported_never_policy_relaxation(self):
        old = self.config.read_text()
        for raw in (CONFIG, old+'\nmodel = "foreign"\n', old.replace('on-request', 'never'),
            old.replace(str(self.checkout), '/foreign'), old+'\n[features.extra]\nenabled = true\n'):
            with self.subTest(raw=raw):
                self.write(self.config, raw, raw=True)
                with self.assertRaises(Refusal): self.preview()
        self.write(self.config, old, raw=True)
        (self.checkout/'.codex').mkdir()
        self.write(self.checkout/'.codex/config.toml', 'model="foreign"', raw=True)
        with self.assertRaisesRegex(Refusal, 'Additional'): self.preview()

    def test_known_config_epoch_changes_invalidate_exact_review(self):
        q = self.preview(); raw = self.config.read_text()
        self.write(self.config, raw, raw=True)
        with self.assertRaisesRegex(Refusal, 'context changed'): self.confirm(q)

    def test_nonprivate_source_input_is_preserved_but_runtime_records_stay_private(self):
        source = self.records/'source.md'; self.write(source, 'original reviewed source', raw=True); source.chmod(0o644)
        path = self.spec['setupRecords']['setupRequest']; request = api.read(path)
        request['immutableInputs'].append(api.input_pin(source)); self.write(path, request)
        review = digest(request)
        for key in ('ownerApproval', 'applicationIntent', 'projectClaim', 'brainClaim'):
            file = self.spec['setupRecords'][key]; value = api.read(file); value['reviewHash'] = review
            if key == 'ownerApproval': value['exactHumanApproval'] = 'Approve prospective v1 native setup '+review
            if key == 'applicationIntent': value['requestPin'] = api.pin(path)
            self.write(file, value)
        self.confirm()
        self.assertEqual(source.read_text(), 'original reviewed source')
        self.assertEqual(source.stat().st_mode & 0o777, 0o644)

    def test_claim_added_during_normal_write_fences_commit(self):
        before = self.contents(self.ledger.db)
        with self.assertRaises(Refusal), self.ledger.tx() as db:
            meta = Ledger.get(db, 'meta', 1); meta['unsafe'] = 'must rollback'; Ledger.put(db, 'meta', 1, meta)
            api.exclusive(self.ledger.root/api.FENCE, {'kind': api.KIND, 'reviewHash': '0'*64})
        self.assertEqual(self.contents(self.ledger.db), before)

    def test_failure_after_local_commit_before_registry_commit_stays_fenced(self):
        proposal = self.preview(); original_tx = self.registry.tx
        @contextlib.contextmanager
        def fail_commit():
            with original_tx() as db:
                yield db
                raise RuntimeError('fixture failure before registry commit')
        with patch.object(self.registry, 'tx', fail_commit), self.assertRaises(RuntimeError): self.confirm(proposal)
        self.assertEqual(self.ledger.snapshot()['meta']['brainId'], self.brain)
        with api.read_database(self.registry.db) as db:
            self.assertEqual(db.execute("SELECT brain FROM workspaces WHERE id='target'").fetchone()[0], self.old)
        with self.assertRaises(Refusal): self.registry.root_for('target')
        with self.assertRaises(Refusal), self.ledger.tx(): pass
        self.calls.clear()
        with self.assertRaises(Refusal): self.confirm(proposal)
        self.assertEqual(self.calls, [])

    def test_any_existing_history_or_control_prevents_setup_adoption(self):
        for table in ('commands', 'decisions', 'continuations'):
            with self.subTest(table=table):
                with self.ledger.tx() as db: Ledger.put(db, table, 'history', {'id': 'history', 'status': 'completed'})
                with self.assertRaisesRegex(Refusal, 'history must remain empty'): self.preview()
                with self.ledger.tx() as db: db.execute('DELETE FROM '+table)
        for field, value in (('standardRun', {}), ('controller', {'owner': 'old'}), ('paused', False)):
            with self.subTest(field=field):
                with self.ledger.tx() as db:
                    old = Ledger.get(db, 'meta', 1); current = {**old, field: value}; Ledger.put(db, 'meta', 1, current)
                with self.assertRaises(Refusal): self.preview()
                with self.ledger.tx() as db: Ledger.put(db, 'meta', 1, old)

    def test_historical_hold_drift_invalidates_review_and_keeps_usage(self):
        hold = self.other.root/'standard-canceled-play.json'
        self.write(hold, {'kind': 'fixture-old-hold', 'terminalSafety': 'unknown'})
        proposal = self.preview(); before = self.contents(self.other.db)
        self.write(hold, {'kind': 'changed'})
        with self.assertRaisesRegex(Refusal, 'context changed'): self.confirm(proposal)
        self.assertEqual(self.contents(self.other.db), before)
        self.assertFalse((self.ledger.root/api.FENCE).exists())


class ReaderFenceTest(unittest.TestCase):
    def test_mutations_foreign_ids_discovery_and_broadened_history_never_forward(self):
        client = api.SetupReadProxy({'endpoint': {}, 'nativeProjectId': 'new-project',
            'brainId': 'new-brain', 'configFile': '/isolated/config.toml'})
        with patch.object(api.ReadProxy, '_rpc') as rpc:
            for method, params in (('thread/resume', {'threadId': 'new-brain'}),
                ('thread/start', {}), ('turn/start', {'threadId': 'new-brain'}),
                ('project/read', {'projectId': 'old-project'}), ('thread/list', {}),
                ('account/read', {'refreshToken': True}), ('thread/read', {'threadId': 'old-brain', 'includeTurns': False}),
                ('thread/read', {'threadId': 'new-brain', 'includeTurns': True}),
                ('thread/turns/list', {'threadId': 'new-brain', 'limit': 100}),
                ('thread/turns/list', {'threadId': 'new-brain', 'cursor': None, 'limit': True,
                    'sortDirection': 'desc', 'itemsView': 'notLoaded'}),
                ('thread/backgroundTerminals/list', {'threadId': 'new-brain'})):
                with self.subTest(method=method), self.assertRaises(Refusal): client._rpc(method, params)
            rpc.assert_not_called()


if __name__ == '__main__': unittest.main()
