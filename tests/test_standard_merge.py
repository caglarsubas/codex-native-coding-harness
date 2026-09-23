"""Temporary local Git fixtures and closed fake GitHub GETs; no live effects."""
import base64
import copy
import json
import subprocess
import tempfile
from pathlib import Path
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator import standard_merge as merge
from orchestrator.core import Ledger, Refusal
from orchestrator.standard import brain, read
from orchestrator.missions import change
from test_missions import specification, request
import test_standard as fixtures


class StandardMergeTest(unittest.TestCase):
    control = fixtures.StandardTest.control
    call = fixtures.StandardTest.call
    claim = fixtures.StandardTest.claim
    activate = fixtures.StandardTest.activate
    observe = fixtures.StandardTest.observe
    tearDown = fixtures.StandardTest.tearDown

    def workspace(self, wid):
        ledger = Ledger(self.root/wid)
        ledger.initialize({'schemaVersion': 1, 'brainId': str(uuid.uuid4()), 'repositories': [
            {'id': 'a', 'path': str(self.repo), 'projectId': 'projectless', 'ref': 'HEAD',
             'policyProfile': 'standard', 'mergePolicy': 'required_checks'}]})
        self.registry.register(wid, wid, ledger.root)
        ledger = self.registry.ledger(wid)
        spec = specification(mode='phase_delegated')
        spec['authority']['mergeMode'] = merge.MODE
        spec['phase']['scope'][0]['operations'].append('merge')
        saved = change(ledger, request(spec=spec))['current']
        change(ledger, request('review', saved['revision'], documentHash=saved['documentHash'], confirmed=True))
        token = ledger.acquire(ledger.snapshot()['meta']['brainId']+':merge-test')
        brain(self.registry, ledger, token, {'operation': 'catalog', 'models': [{'model': 'fixture', 'efforts': ['low']}], 'source': 'Fixture schema'})
        return ledger, token

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True).strip()

    def setUp(self):
        fixtures.StandardTest.setUp(self)
        self.git('config', 'user.name', 'Fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('remote', 'add', 'origin', 'git@github.com:fixture/project.git')
        (self.repo/'tests').mkdir(); (self.repo/'web').mkdir()
        (self.repo/'tests/test_fixture.py').write_text('x = 1\n')
        (self.repo/'tests/test_fixture_ui.js').write_text('"use strict";\n')
        (self.repo/'web/app.js').write_text('"use strict";\n')
        self.git('add', '.'); self.git('commit', '-qm', 'Base')
        self.base = self.git('rev-parse', 'HEAD')
        self.git('checkout', '-qb', 'codex/fixture')
        (self.repo/'tests/test_fixture.py').write_text('x = 2\n')
        self.git('add', '.'); self.git('commit', '-qm', 'Result')
        self.head = self.git('rev-parse', 'HEAD')
        self.activate(); self.observe()
        self.call('finish', taskId='task-1', outcome='completed', evidence={
            'source': 'Independently inspected exact commit', 'tests': 'Local fixture checks',
            'artifacts': [], 'preservation': 'Git retained; merge preparation retains exact patch',
            'summary': 'Independent fixture review', 'headSHA': self.head})
        run = read(self.ledger)['run']; task = run['tasks'][0]
        self.binding = {'prUrl': 'https://github.com/fixture/project/pull/7', 'number': 7,
                        'baseBranch': 'main', 'headBranch': 'codex/fixture', 'baseSHA': self.base, 'headSHA': self.head}
        def checks(commands): return [{'argv': c, 'exitCode': 0, 'output': 'Complete fixture output: passed'} for c in commands]
        self.evidence = {'headSHA': self.head, 'resultHash': task['result'], 'reviewer': run['brainId'],
            'verdict': 'passed', 'summary': 'Brain independently reviewed diff, result and local checks',
            'native': {'observedAt': time.time(), 'tasks': [{'threadId': task['threadId'], 'status': 'completed', 'trackedTerminals': 'none'}]},
            'local': {'observedAt': time.time(), 'headSHA': self.head, 'complete': True,
                'python': checks([['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-v']]),
                'javascript': checks([['node', 'tests/test_fixture_ui.js']]),
                'syntax': checks([['python3', '-m', 'compileall', '-q', 'orchestrator', 'tests'], ['node', '--check', 'tests/test_fixture_ui.js'], ['node', '--check', 'web/app.js']]),
                'diff': checks([['git', 'diff', '--check', self.base, self.head]])}}
        self.pull = {'number': 7, 'html_url': self.binding['prUrl'], 'head': {'sha': self.head, 'ref': 'codex/fixture', 'repo': {'full_name': 'fixture/project'}},
                     'base': {'sha': self.base, 'ref': 'main', 'repo': {'full_name': 'fixture/project'}},
                     'state': 'open', 'merged': False, 'draft': False, 'mergeable': True, 'mergeable_state': 'clean'}
        self.responses = {
            'pulls/7': self.pull, 'branches/main': {'commit': {'sha': self.base}, 'protected': False},
            'rules/branches/main?per_page=100&page=1': [],
            'commits/'+self.head+'/check-suites?per_page=100&page=1': {'total_count': 0, 'check_suites': []},
            'commits/'+self.head+'/check-runs?filter=all&per_page=100&page=1': {'total_count': 0, 'check_runs': []},
            'commits/'+self.head+'/status?per_page=100&page=1': {'sha': self.head, 'repository': {'full_name': 'fixture/project'}, 'total_count': 0, 'statuses': []},
            'commits/'+self.head+'/statuses?per_page=100&page=1': [],
            'actions/workflows?per_page=100&page=1': {'total_count': 0, 'workflows': []}}
        self.reader = patch.object(merge, 'api_read', side_effect=lambda endpoint, deadline: copy.deepcopy(self.responses[endpoint.removeprefix('repos/fixture/project/')]))
        self.reader.start(); self.addCleanup(self.reader.stop)
        self.queue = {'data': {'repository': {'nameWithOwner': 'fixture/project', 'pullRequest': {
            'number': 7, 'url': self.binding['prUrl'], 'baseRefName': 'main', 'baseRefOid': self.base,
            'headRefName': 'codex/fixture', 'headRefOid': self.head, 'isMergeQueueEnabled': False,
            'isInMergeQueue': False, 'autoMergeRequest': None}}}}
        queue_reader = patch.object(merge, 'queue_read', side_effect=lambda *a: copy.deepcopy(self.queue))
        queue_reader.start(); self.addCleanup(queue_reader.stop)
        self.request_id = str(uuid.uuid4())

    def op(self, operation, **changes):
        values = {'taskId': 'task-1', 'requestId': self.request_id}
        if operation == 'merge_prepare': values.update(binding=self.binding, evidence=self.evidence)
        if operation == 'merge_check': values.update(evidence=self.evidence)
        return self.call(operation, **{**values, **changes})

    def merged(self):
        self.pull.update(state='closed', merged=True, merged_at='2026-09-23T00:00:00Z', merge_commit_sha='f'*40)
        self.pull['base']['sha'] = 'f'*40

    def test_one_shot_no_workflow_source_retention_and_replay(self):
        prepared = self.op('merge_prepare')
        self.assertEqual(prepared['merge']['status'], 'prepared')
        report = self.ledger.document(prepared['merge']['observationHash'])
        self.assertTrue(report['noWorkflowObservation'])
        self.assertFalse(report['report']['ci']['complete'])  # Absence is not CI success.
        original = self.ledger.document(prepared['merge']['bindingHash'])
        preserved = self.ledger.document(original['sourceHash'])
        self.assertEqual(preserved['headSHA'], self.head)
        self.assertTrue(preserved['patchBase64'])
        self.assertEqual([base64.b64decode(value) for value in preserved['blobsBase64'].values()], [b'x = 2\n'])
        with patch.object(merge, 'remote', side_effect=AssertionError('Replay must not collect')):
            self.assertTrue(self.op('merge_prepare')['replay'])
        issued = self.op('merge_check')
        self.assertEqual(issued['argv'], ['gh', 'api', '--hostname', 'github.com', '--method', 'PUT',
            '-H', 'Accept: application/vnd.github+json', '-H', 'X-GitHub-Api-Version: '+merge.API_VERSION,
            'repos/fixture/project/pulls/7/merge', '-f', 'sha='+self.head, '-f', 'merge_method=merge'])
        self.assertNotIn('argv', self.op('merge_check'))
        receipt = self.op('merge_receipt', delivery='unknown')
        self.assertEqual(receipt['merge']['status'], 'uncertain')
        self.assertTrue(self.op('merge_receipt', delivery='unknown')['replay'])
        self.assertEqual(self.op('merge_reconcile')['merge']['status'], 'uncertain')
        self.assertNotIn('argv', self.op('merge_check'))
        self.merged()
        self.assertEqual(self.op('merge_reconcile')['merge']['status'], 'merged')
        self.assertNotIn('argv', self.op('merge_check'))
        self.assertTrue(self.op('merge_reconcile')['replay'])

    def test_pause_and_review_races_recheck_after_io(self):
        self.op('merge_prepare')
        real = merge.remote
        def pause(*a, **kw):
            result = real(*a, **kw); self.control('pause'); return result
        with patch.object(merge, 'remote', side_effect=pause), self.assertRaisesRegex(Refusal, 'Context changed'):
            self.op('merge_check')
        self.assertEqual(read(self.ledger)['run']['merges'][0]['status'], 'prepared')
        with self.assertRaises(Refusal): self.op('merge_check')

    def test_review_race_and_historical_replay_never_restore_authority(self):
        self.op('merge_prepare')
        real = merge.remote
        def revoke(*a, **kw):
            result = real(*a, **kw)
            m = self.ledger.snapshot()['mission']
            change(self.ledger, request('revoke', m['revision'], documentHash=m['documentHash'], confirmed=True))
            return result
        with patch.object(merge, 'remote', side_effect=revoke), self.assertRaises(Refusal): self.op('merge_check')
        self.assertNotIn('argv', self.op('merge_prepare'))
        with self.assertRaises(Refusal): self.op('merge_check')

    def test_stale_head_base_and_branch_refused(self):
        self.op('merge_prepare')
        for side, field, value in [('head', 'sha', 'a'*40), ('base', 'sha', 'b'*40), ('base', 'ref', 'other'), ('head', 'ref', 'codex/other')]:
            old = self.pull[side][field]; self.pull[side][field] = value
            with self.subTest(side=side, field=field), self.assertRaises(Refusal): self.op('merge_check')
            self.pull[side][field] = old
        self.git('update-ref', 'refs/heads/codex/fixture', self.base)
        with self.assertRaises(Refusal): self.op('merge_check')

    def test_checks_missing_pending_failed_truncated_ambiguous(self):
        self.responses['rules/branches/main?per_page=100&page=1'] = [{'type': 'required_status_checks', 'parameters': {'required_status_checks': [{'context': 'unit', 'integration_id': 1}]}}]
        suites = self.responses['commits/'+self.head+'/check-suites?per_page=100&page=1']
        runs = self.responses['commits/'+self.head+'/check-runs?filter=all&per_page=100&page=1']
        with self.assertRaises(Refusal): self.op('merge_prepare')
        suites.update(total_count=1, check_suites=[{'id': 2, 'head_sha': self.head, 'status': 'completed', 'conclusion': 'success'}])
        row = {'id': 3, 'head_sha': self.head, 'app': {'id': 1}, 'check_suite': {'id': 2}, 'name': 'unit', 'status': 'completed', 'conclusion': 'success'}
        for status, conclusion in [('in_progress', None), ('completed', 'failure')]:
            runs.update(total_count=1, check_runs=[{**row, 'status': status, 'conclusion': conclusion}])
            with self.assertRaises(Refusal): self.op('merge_prepare')
        runs.update(total_count=2, check_runs=[row])
        with self.assertRaises(Refusal): self.op('merge_prepare')
        runs.update(total_count=2, check_runs=[row, {**row, 'id': 4}])
        with self.assertRaises(Refusal): self.op('merge_prepare')
        runs.update(total_count=1, check_runs=[row])
        self.assertEqual(self.op('merge_prepare')['merge']['status'], 'prepared')

    def test_no_workflow_does_not_waive_local_evidence(self):
        for field in ('python', 'javascript', 'syntax', 'diff'):
            evidence = copy.deepcopy(self.evidence); evidence['local'][field] = []
            with self.subTest(field=field), self.assertRaises(Refusal): self.op('merge_prepare', evidence=evidence)
        for field, value in [('observedAt', time.time()-301), ('headSHA', 'a'*40), ('complete', False)]:
            evidence = copy.deepcopy(self.evidence); evidence['local'][field] = value
            with self.assertRaises(Refusal): self.op('merge_prepare', evidence=evidence)
        evidence = copy.deepcopy(self.evidence); evidence['local']['python'][0]['exitCode'] = 1
        with self.assertRaises(Refusal): self.op('merge_prepare', evidence=evidence)
        self.responses['actions/workflows?per_page=100&page=1'] = {'total_count': 1, 'workflows': [{'id': 1}]}
        with self.assertRaises(Refusal): self.op('merge_prepare')

    def test_duplicate_pr_and_immutable_request(self):
        self.op('merge_prepare')
        with self.assertRaises(Refusal): self.op('merge_prepare', requestId=str(uuid.uuid4()))
        with self.assertRaises(Refusal): self.op('merge_prepare', binding={**self.binding, 'number': 8})
        with self.assertRaises(Refusal): self.op('merge_check', taskId='foreign')

    def test_already_merged_or_closed_observation_never_emits_arguments(self):
        self.merged()
        result = self.op('merge_prepare')
        self.assertEqual(result['merge']['status'], 'merged')
        self.assertNotIn('argv', self.op('merge_check'))

    def test_closed_pr_reconciliation_after_pause(self):
        self.op('merge_prepare'); self.op('merge_check'); self.control('pause')
        self.pull['state'] = 'closed'
        self.assertEqual(self.op('merge_reconcile')['merge']['status'], 'not-merged')
        self.assertNotIn('argv', self.op('merge_check'))

    def test_harness_manual_and_unreviewed_refuse_before_io(self):
        for field, value in [('policyProfile', 'harness'), ('mergePolicy', 'manual'), ('projectId', 'changed')]:
            with self.ledger.tx() as db:
                original = self.ledger.get(db, 'repos', 'a'); changed = {**original, field: value}; self.ledger.put(db, 'repos', 'a', changed)
            with patch.object(merge, 'source', side_effect=AssertionError('No I/O')), self.assertRaises(Refusal): self.op('merge_prepare')
            with self.ledger.tx() as db: self.ledger.put(db, 'repos', 'a', original)
        m = self.ledger.snapshot()['mission']
        change(self.ledger, request('revoke', m['revision'], documentHash=m['documentHash'], confirmed=True))
        with self.assertRaises(Refusal): self.op('merge_prepare')

    def test_independent_review_native_and_result_binding_required(self):
        for field, value in [('reviewer', read(self.ledger)['run']['tasks'][0]['threadId']), ('verdict', 'failed'), ('resultHash', 'a'*64)]:
            with self.assertRaises(Refusal): self.op('merge_prepare', evidence={**self.evidence, field: value})
        evidence = copy.deepcopy(self.evidence); evidence['native']['tasks'] = []
        with self.assertRaises(Refusal): self.op('merge_prepare', evidence=evidence)
        evidence = copy.deepcopy(self.evidence); evidence['native']['tasks'][0]['trackedTerminals'] = 'unknown'
        with self.assertRaises(Refusal): self.op('merge_prepare', evidence=evidence)

    def test_expired_completed_brain_stop_and_unresolved_tasks_refused(self):
        with self.ledger.tx() as db: original = self.ledger.get(db, 'meta', 1)
        mutations = [lambda m: m['standardRun'].update(status='completed'),
                     lambda m: m['standardRun'].update(expiresAt=time.time()-1),
                     lambda m: m.update(brainControl={'phase': 'stop_requested', 'desired': 'stopped'}),
                     lambda m: m['standardRun']['tasks'].append({'id': 'pending', 'status': 'pending', 'allowance': 10000}),
                     lambda m: m['standardRun']['limits'].pop('mergeMode')]
        for mutate in mutations:
            m = copy.deepcopy(original); mutate(m)
            with self.ledger.tx() as db: self.ledger.put(db, 'meta', 1, m)
            with self.assertRaises(Refusal): self.op('merge_prepare')
        with self.ledger.tx() as db: self.ledger.put(db, 'meta', 1, original)

    def test_unknown_merge_blocks_phase_close_and_claim(self):
        self.op('merge_prepare'); self.op('merge_check')
        with self.assertRaises(Refusal): self.claim('task-2')
        for outcome in ('completed', 'blocked'):
            with self.assertRaises(Refusal): self.call('checkpoint', outcome=outcome, summary='Cannot abandon unknown send', brainObservedTokens=None)
        self.control('pause')
        self.call('checkpoint', outcome='paused', summary='Retain unknown delivery', brainObservedTokens=None)
        with self.assertRaises(Refusal): self.control('resume')

    def test_other_workspace_task_and_merge_ownership_refused(self):
        other, token = self.workspace('beta')
        self.control(ledger=other)
        self.call('claim', ledger=other, token=token, id='other-task', repository='a', title='Other task',
                  paths=['tests/test_fixture.py'], instructions='Fixture', acceptance=['Pass'],
                  model='fixture', effort='low', rationale='Fixture', allowance=10000)
        with self.assertRaisesRegex(Refusal, 'Another registered task'): self.op('merge_prepare')
        self.call('cancel_unissued', ledger=other, token=token, taskId='other-task')
        self.op('merge_prepare')
        with self.assertRaisesRegex(Refusal, 'unresolved merge'):
            self.call('claim', ledger=other, token=token, id='other-task-2', repository='a', title='Other task',
                      paths=['tests/test_fixture.py'], instructions='Fixture', acceptance=['Pass'],
                      model='fixture', effort='low', rationale='Fixture', allowance=10000)

    def test_duplicate_pr_cannot_be_rebound_in_a_new_run(self):
        self.merged(); self.op('merge_prepare')
        self.call('checkpoint', outcome='completed', summary='Fixture owner checkpoint', brainObservedTokens=None)
        spec = specification(mode='phase_delegated')
        spec['authority']['mergeMode'] = merge.MODE
        spec['phase']['id'] = 'phase-two'
        spec['phase']['scope'][0]['operations'].append('merge')
        m = self.ledger.snapshot()['mission']
        saved = change(self.ledger, request('save', m['revision'], spec=spec))['current']
        change(self.ledger, request('review', saved['revision'], documentHash=saved['documentHash'], confirmed=True))
        self.activate(); self.observe()
        self.call('finish', taskId='task-1', outcome='completed', evidence={
            'source': 'Fixture result', 'tests': 'Passed', 'artifacts': [],
            'preservation': 'Retained', 'summary': 'Reviewed', 'headSHA': self.head})
        self.request_id = str(uuid.uuid4())
        with patch.object(merge, 'source', side_effect=AssertionError('No recollection')), self.assertRaisesRegex(Refusal, 'Duplicate PR'):
            self.op('merge_prepare')

    def test_check_transaction_rollback_never_returns_arguments(self):
        self.op('merge_prepare')
        original = self.ledger.event
        def fail(db, kind, data):
            if kind == 'standard_merge_check': raise RuntimeError('Fixture commit failure')
            return original(db, kind, data)
        with patch.object(self.ledger, 'event', side_effect=fail), self.assertRaises(RuntimeError): self.op('merge_check')
        self.assertEqual(read(self.ledger)['run']['merges'][0]['status'], 'prepared')
        self.assertIn('argv', self.op('merge_check'))

    def test_source_and_remote_drift_during_collection_refused(self):
        original = merge.api_read
        calls = 0
        def drift(endpoint, deadline):
            nonlocal calls
            result = original(endpoint, deadline)
            if endpoint.endswith('pulls/7'):
                calls += 1
                if calls == 2: result['draft'] = True
            return result
        with patch.object(merge, 'api_read', side_effect=drift), self.assertRaises(Refusal): self.op('merge_prepare')
        self.git('update-ref', 'refs/heads/codex/fixture', self.base)
        with self.assertRaises(Refusal): self.op('merge_prepare')

    def test_post_remote_head_origin_and_layout_drift_refuse_issuance(self):
        self.op('merge_prepare')
        real = merge.remote
        mutations = [
            (lambda: self.git('update-ref', 'refs/heads/codex/fixture', self.base),
             lambda: self.git('update-ref', 'refs/heads/codex/fixture', self.head)),
            (lambda: self.git('remote', 'set-url', 'origin', 'git@github.com:foreign/project.git'),
             lambda: self.git('remote', 'set-url', 'origin', 'git@github.com:fixture/project.git')),
            # Replacing object storage preserves standard.git_root's identity.
            (lambda: (self.repo/'.git/objects').rename(self.repo/'.git/objects-old'),
             lambda: (self.repo/'.git/objects-old').rename(self.repo/'.git/objects')),
        ]
        for mutate, restore in mutations:
            def drift(*a, **kw):
                result = real(*a, **kw)
                mutate()
                if not (self.repo/'.git/objects').exists():
                    (self.repo/'.git/objects').mkdir()
                return result
            try:
                with patch.object(merge, 'remote', side_effect=drift), self.assertRaises(Refusal):
                    self.op('merge_check')
                self.assertEqual(read(self.ledger)['run']['merges'][0]['status'], 'prepared')
            finally:
                if (self.repo/'.git/objects-old').exists(): (self.repo/'.git/objects').rmdir()
                restore()
        self.assertIn('argv', self.op('merge_check'))

    def test_policy_metadata_drift_beyond_required_names_refuses(self):
        self.responses['branches/main']['protected'] = True
        classic = {'required_status_checks': None, 'enforce_admins': {'enabled': True},
                   'required_pull_request_reviews': {'required_approving_review_count': 1},
                   'restrictions': {'users': [], 'teams': [], 'apps': []}}
        self.responses['branches/main/protection'] = classic
        rules_key = 'rules/branches/main?per_page=100&page=1'
        self.responses[rules_key] = [{'type': 'pull_request', 'ruleset_id': 1,
                                     'parameters': {'required_approving_review_count': 1}}]
        self.op('merge_prepare')
        original = merge.api_read
        changes = [
            ('branches/main/protection', lambda r: r['enforce_admins'].update(enabled=False)),
            ('branches/main/protection', lambda r: r['required_pull_request_reviews'].update(required_approving_review_count=2)),
            ('branches/main/protection', lambda r: r['restrictions']['teams'].append({'id': 8})),
            ('branches/main/protection', lambda r: r.update(future_policy={'enabled': True})),
            (rules_key, lambda r: r[0]['parameters'].update(required_approving_review_count=2)),
            (rules_key, lambda r: r[0].update(ruleset_id=2)),
            (rules_key, lambda r: r.append({'type': 'future_rule'})),
        ]
        for suffix, mutate in changes:
            calls = 0
            def drift(endpoint, deadline):
                nonlocal calls
                result = original(endpoint, deadline)
                if endpoint.endswith(suffix):
                    calls += 1
                    if calls == 2: mutate(result)
                return result
            with self.subTest(suffix=suffix), patch.object(merge, 'api_read', side_effect=drift):
                with self.assertRaisesRegex(Refusal, 'changed during verification'): self.op('merge_check')
            self.assertEqual(read(self.ledger)['run']['merges'][0]['status'], 'prepared')

    def test_policy_unavailable_or_unsupported_is_not_absence(self):
        self.op('merge_prepare')
        original = merge.api_read
        for missing in ('rules/branches/main?per_page=100&page=1', 'branches/main/protection'):
            self.responses['branches/main']['protected'] = missing.endswith('protection')
            def unavailable(endpoint, deadline):
                if endpoint.endswith(missing): raise Refusal('Fixture endpoint unavailable')
                return original(endpoint, deadline)
            with patch.object(merge, 'api_read', side_effect=unavailable), self.assertRaises(Refusal):
                self.op('merge_check')
        self.responses['branches/main']['protected'] = False
        key = 'rules/branches/main?per_page=100&page=1'
        for value in (None, [{'type': 'unsupported_rule'}]):
            self.responses[key] = value
            with self.assertRaises(Refusal): self.op('merge_check')
        self.assertEqual(read(self.ledger)['run']['merges'][0]['status'], 'prepared')

    def test_effective_queue_classic_ruleset_unknown_and_auto_merge_refuse(self):
        self.op('merge_prepare')
        pr = self.queue['data']['repository']['pullRequest']
        for field in ('isMergeQueueEnabled', 'isInMergeQueue', 'autoMergeRequest'):
            original = pr[field]
            for value in (True, None, 'unknown', {'enabledAt': 'fixture'}):
                if value is None and field == 'autoMergeRequest': continue
                pr[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(Refusal): self.op('merge_check')
            del pr[field]
            with self.assertRaises(Refusal): self.op('merge_check')
            pr[field] = original
        # Effective queue enabled even though REST classic response has no queue field.
        self.responses['branches/main']['protected'] = True
        self.responses['branches/main/protection'] = {'required_status_checks': None}
        pr['isMergeQueueEnabled'] = True
        with self.assertRaises(Refusal): self.op('merge_check')
        pr['isMergeQueueEnabled'] = False
        self.responses['rules/branches/main?per_page=100&page=1'] = [{'type': 'merge_queue', 'parameters': {}}]
        with self.assertRaises(Refusal): self.op('merge_check')
        self.responses['rules/branches/main?per_page=100&page=1'] = []
        for value in (None, {}, {'errors': [{'message': 'Unsupported field'}], 'data': self.queue['data']},
                      {'data': {'repository': None}}):
            with patch.object(merge, 'queue_read', return_value=value), self.assertRaises(Refusal): self.op('merge_check')
        self.assertEqual(read(self.ledger)['run']['merges'][0]['status'], 'prepared')

    def test_queue_round_race_and_post_issue_effect_has_no_deferred_fallback(self):
        self.op('merge_prepare')
        first = copy.deepcopy(self.queue); second = copy.deepcopy(first)
        second['data']['repository']['pullRequest']['isMergeQueueEnabled'] = True
        with patch.object(merge, 'queue_read', side_effect=[first, second]), self.assertRaises(Refusal):
            self.op('merge_check')
        issued = self.op('merge_check')
        # Simulate policy changing after issuance. The disposable endpoint model
        # refuses a synchronous PUT; no gh-pr-merge/queue/auto mutation is available.
        calls = []
        def server(argv):
            calls.append(argv)
            self.assertEqual(argv[argv.index('--method')+1], 'PUT')
            self.assertIn('repos/fixture/project/pulls/7/merge', argv)
            self.assertIn('sha='+self.head, argv)
            self.assertEqual(argv[-2:], ['-f', 'merge_method=merge'])
            return {'status': 405, 'merged': False, 'queued': False, 'autoMerge': False}
        result = server(issued['argv'])
        self.assertFalse(result['queued'] or result['autoMerge'])
        self.op('merge_receipt', delivery='failed')
        self.assertNotIn('argv', self.op('merge_check'))
        self.assertEqual(self.op('merge_reconcile')['merge']['status'], 'uncertain')
        self.assertEqual(len(calls), 1)

    def test_optional_successful_reruns_and_provider_collisions_refuse(self):
        suites = self.responses['commits/'+self.head+'/check-suites?per_page=100&page=1']
        runs = self.responses['commits/'+self.head+'/check-runs?filter=all&per_page=100&page=1']
        suites.update(total_count=1, check_suites=[{'id': 2, 'head_sha': self.head, 'status': 'completed', 'conclusion': 'success'}])
        row = {'id': 3, 'head_sha': self.head, 'app': {'id': 1}, 'check_suite': {'id': 2},
               'name': 'optional', 'status': 'completed', 'conclusion': 'success'}
        for app in (1, 9):
            runs.update(total_count=2, check_runs=[row, {**row, 'id': 4, 'app': {'id': app}}])
            with self.assertRaisesRegex(Refusal, 'inventory.*ambiguity'): self.op('merge_prepare')
        runs.update(total_count=1, check_runs=[row])
        status = {'id': 5, 'context': 'optional', 'state': 'success'}
        self.responses['commits/'+self.head+'/status?per_page=100&page=1'].update(total_count=1, statuses=[status])
        self.responses['commits/'+self.head+'/statuses?per_page=100&page=1'] = [status]
        with self.assertRaisesRegex(Refusal, 'inventory.*ambiguity'): self.op('merge_prepare')
        # Combined status hides older reruns, which the history must also reject.
        self.responses['commits/'+self.head+'/statuses?per_page=100&page=1'].append({**status, 'id': 6})
        with self.assertRaisesRegex(Refusal, 'Ambiguous combined'): self.op('merge_prepare')

    def test_full_rule_or_status_history_page_is_not_complete(self):
        key = 'rules/branches/main?per_page=100&page=1'
        self.responses[key] = [{'type': 'pull_request', 'parameters': {}}] * 100
        with self.assertRaises(Refusal): self.op('merge_prepare')
        self.responses[key] = []
        self.responses['commits/'+self.head+'/statuses?per_page=100&page=1'] = [
            {'id': n+1, 'context': str(n), 'state': 'success'} for n in range(100)]
        with self.assertRaises(Refusal): self.op('merge_prepare')

    def test_full_check_metadata_drift_is_compared(self):
        self.op('merge_prepare')
        original = merge.api_read
        calls = 0
        def drift(endpoint, deadline):
            nonlocal calls
            result = original(endpoint, deadline)
            if '/check-runs?' in endpoint:
                calls += 1
                if calls == 2: result['future_coverage'] = 'unknown'
            return result
        with patch.object(merge, 'api_read', side_effect=drift), self.assertRaisesRegex(Refusal, 'changed during verification'):
            self.op('merge_check')

    def test_foreign_origin_and_unsupported_policy_refused(self):
        self.git('remote', 'set-url', 'origin', 'git@github.com:other/project.git')
        with self.assertRaises(Refusal): self.op('merge_prepare')
        self.git('remote', 'set-url', 'origin', 'git@github.com:fixture/project.git')
        self.responses['rules/branches/main?per_page=100&page=1'] = [{'type': 'unknown_rule'}]
        with self.assertRaises(Refusal): self.op('merge_prepare')


class QueueTransportTest(unittest.TestCase):
    def test_fixed_bounded_query_transport_and_failures(self):
        binding = {'prUrl': 'https://github.com/fixture/project/pull/7'}
        # Disposable CLI fixture: exercise the real pipe/JSON reader with no network.
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder)/'gh'
            def fixture(body):
                executable.write_text('#!/usr/bin/env python3\nimport sys\n' + body)
                executable.chmod(0o700)
            fixture("assert sys.argv[1:7] == ['api', '--hostname', 'github.com', '--method', 'POST', 'graphql']\n"
                    "assert sys.argv[7] == '-f'\n"
                    "q = sys.argv[8]\n"
                    "assert q.startswith('query=query { repository(') and 'mutation' not in q\n"
                    "assert all(f in q for f in ['isMergeQueueEnabled', 'isInMergeQueue', 'autoMergeRequest'])\n"
                    "print('{\"data\":{}}')\n")
            with patch.object(merge.shutil, 'which', return_value=str(executable)):
                self.assertEqual(merge.queue_read(binding, time.monotonic()+5), {'data': {}})
                for body in ("print('{bad json}')\n", "print('{\"data\":{},\"data\":null}')\n",
                             "print('x' * 20000)\n", "sys.exit(1)\n"):
                    fixture(body)
                    with self.subTest(body=body), self.assertRaises(Refusal):
                        merge.queue_read(binding, time.monotonic()+5)
                fixture("import time\ntime.sleep(1)\n")
                with self.assertRaises(Refusal):
                    merge.queue_read(binding, time.monotonic()+.05)


if __name__ == '__main__': unittest.main()
