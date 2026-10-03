"""Synthetic journals only: no private IDs, native prompts or conversation bytes."""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orchestrator import brain_memory
from orchestrator.brain_memory import session_usage
from orchestrator.core import Ledger, Refusal
from tests.test_brain_memory import vector


class TokenRecordsTest(unittest.TestCase):
    identity = 'synthetic-session'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name).resolve() / 'rollout.jsonl'

    def row(self, at, kind, payload):
        return {'timestamp': dt.datetime.fromtimestamp(at, dt.timezone.utc).isoformat(),
                'type': kind, 'payload': payload}

    def native(self, at, total, usage, response, turn='turn-1', turn_total=None):
        return self.row(at, 'token_usage_record', {
            'thread_id': self.identity, 'session_id': self.identity, 'turn_id': turn,
            'root_turn_id': turn, 'response_id': response,
            'thread_token_usage': vector(total, total // 2),
            'usage': vector(usage, usage // 2),
            'turn_token_usage': vector(turn_total if turn_total is not None else total,
                                       (turn_total if turn_total is not None else total) // 2)})

    def legacy(self, at, total, usage):
        return self.row(at, 'event_msg', {'type': 'token_count', 'info': {
            'total_token_usage': vector(total, total // 2),
            'last_token_usage': vector(usage, usage // 2), 'model_context_window': 1000}})

    def compaction(self, at, native):
        return self.row(at, 'compacted', {
            'compaction_response_id': native['payload']['response_id'],
            'latest_token_usage_record': copy.deepcopy(native['payload']),
            'replacement_history': [{'content': 'PRIVATE_CONTENT_MUST_NOT_BE_RETAINED'}]})

    def write(self, rows, start=90, path=None):
        header = self.row(start, 'session_meta', {'id': self.identity})
        (path or self.path).write_text('\n'.join(json.dumps(r) for r in [header, *rows])+'\n')

    def collect(self, start=150, end=350, brain=True, paths=None):
        return session_usage(paths or [self.path], self.identity, start, end, brain)

    def compacted_rows(self):
        compact = self.native(210, 1000, 100, 'compact')
        estimate = self.legacy(212, 900, 0)
        estimate['payload']['info']['last_token_usage']['total_tokens'] = 80
        return [self.native(100, 500, 500, 'first'), self.legacy(101, 500, 500),
                self.native(200, 900, 400, 'second'), self.legacy(201, 900, 400),
                compact, self.compaction(211, compact), estimate,
                self.native(300, 1400, 400, 'third'), self.legacy(301, 1300, 400)]

    def test_compaction_is_charged_once_not_the_context_estimate(self):
        self.write(self.compacted_rows())
        report = self.collect()
        self.assertEqual(report['tokens']['total_tokens'], 900)
        self.assertEqual(report['tokens']['cached_input_tokens'], 450)
        self.assertEqual(report['compactionTokens']['total_tokens'], 100)
        self.assertEqual(report['compactionCalls'], 1)
        self.assertEqual(report['calls'], 3)
        self.assertEqual(report['counterSource'], 'native_response_usage_v1')
        self.assertEqual(report['gaps'], [])
        self.assertEqual(report['sampleAt'], 300)
        self.assertEqual(report['lastInputTokens'], 400)
        self.assertNotIn('PRIVATE_CONTENT', json.dumps(report))

    def test_new_counter_only_and_worker_lifetime(self):
        self.write([self.native(100, 500, 500, 'first'), self.native(200, 900, 400, 'second')])
        self.assertEqual(self.collect()['tokens']['total_tokens'], 400)
        worker = self.collect(brain=False)
        self.assertEqual(worker['tokens']['total_tokens'], 900)
        self.assertEqual(worker['gaps'], [])

    def test_duplicate_archives_and_retimestamped_response_do_not_renew_evidence(self):
        rows = self.compacted_rows()
        later = copy.deepcopy(rows[-2]); later['timestamp'] = self.row(340, '', {})['timestamp']
        self.write([*rows, later])
        archive = self.path.parent / 'archive.jsonl'
        archive.write_bytes(self.path.read_bytes())
        report = self.collect(paths=[archive, self.path])
        self.assertEqual(report['tokens']['total_tokens'], 900)
        self.assertEqual(report['calls'], 3)
        self.assertEqual(report['compactionCalls'], 1)
        self.assertEqual(report['sampleAt'], 300)
        self.assertEqual(report['gaps'], [])

    def test_missing_middle_response_and_unmatched_legacy_tail_are_gaps(self):
        rows = self.compacted_rows()
        self.write([r for r in rows if not (r['type']=='token_usage_record' and r['payload']['response_id']=='second')])
        self.assertIn('response_usage_discontinuity', self.collect()['gaps'])
        self.write([*rows, self.legacy(340, 1500, 200)])
        report = self.collect()
        self.assertIn('unmatched_legacy_token_record', report['gaps'])
        self.assertEqual(report['tokens']['total_tokens'], 1100)

    def test_missing_compaction_proof_cannot_clear_bad_breakdown(self):
        self.write([r for r in self.compacted_rows() if r['type'] != 'compacted'])
        report = self.collect()
        self.assertIn('invalid_token_record', report['gaps'])
        self.assertEqual(report['tokens']['total_tokens'], 900)

    def test_compaction_marker_alone_never_falls_back_to_legacy_counter(self):
        rows = self.compacted_rows()
        self.write([r for r in rows if r['type'] != 'token_usage_record'])
        with self.assertRaises(Refusal): self.collect()
        # Historical compacted records without a response journal keep the old
        # collector, including its normal baseline and vector checks.
        self.write([self.legacy(100, 500, 500), self.row(180, 'compacted', {}),
                    self.legacy(200, 900, 400)])
        self.assertEqual(self.collect()['tokens']['total_tokens'], 400)
        self.assertEqual(self.collect()['gaps'], [])

    def test_malformed_headers_and_nonempty_info_types_are_not_coverage(self):
        for header in ([], {'type': 'session_meta', 'payload': []}):
            self.path.write_text(json.dumps(header)+'\n')
            with self.subTest(header=header), self.assertRaises(Refusal): self.collect()
        for info in (False, 0, [], 'counter'):
            self.write([self.native(100, 500, 500, 'first'), self.native(200, 900, 400, 'second'),
                        self.row(201, 'event_msg', {'type': 'token_count', 'info': info})])
            with self.subTest(info=info):
                self.assertIn('invalid_token_record', self.collect()['gaps'])

    def test_compaction_requires_exact_native_response_and_bytes(self):
        for change in ('response', 'usage', 'identity', 'time'):
            with self.subTest(change=change):
                rows = self.compacted_rows(); marker = rows[5]
                if change == 'response': marker['payload']['compaction_response_id'] = 'different'
                if change == 'usage': marker['payload']['latest_token_usage_record']['usage'] = vector(102, 51)
                if change == 'identity': marker['payload']['latest_token_usage_record']['session_id'] = 'foreign'
                if change == 'time': marker['timestamp'] = self.row(209, '', {})['timestamp']
                self.write(rows)
                self.assertIn('unreconciled_compaction_usage', self.collect()['gaps'])

    def test_arbitrary_invalid_last_breakdown_is_not_a_compaction_exception(self):
        for change in ('positive_input', 'over_window', 'boolean', 'negative_cache_write'):
            with self.subTest(change=change):
                rows = self.compacted_rows(); last = rows[6]['payload']['info']['last_token_usage']
                if change == 'positive_input': last['input_tokens'] = 1
                if change == 'over_window': last['total_tokens'] = 1001
                if change == 'boolean': last['output_tokens'] = False
                if change == 'negative_cache_write': last['cache_write_input_tokens'] = -1
                self.write(rows)
                self.assertIn('invalid_token_record', self.collect()['gaps'])

    def test_bad_new_record_never_uses_good_legacy_as_fallback(self):
        rows = [self.native(100, 500, 500, 'first'), self.native(200, 900, 400, 'second'), self.legacy(201, 900, 400)]
        rows[1]['payload']['usage']['total_tokens'] += 1
        self.write(rows)
        report = self.collect()
        self.assertEqual(report['tokens']['total_tokens'], 400)
        self.assertIn('invalid_response_usage_record', report['gaps'])
        self.assertIsNone(report['lastInputTokens'])

    def test_foreign_session_or_thread_counter_is_not_charged(self):
        for key in ('session_id', 'thread_id'):
            with self.subTest(key=key):
                rows = [self.native(100, 500, 500, 'first'), self.native(200, 900, 400, 'second'), self.native(300, 1900, 1000, 'foreign')]
                rows[-1]['payload'][key] = 'other-project'
                self.write(rows)
                report = self.collect()
                self.assertEqual(report['tokens']['total_tokens'], 400)
                self.assertIn('invalid_response_usage_record', report['gaps'])

    def test_missing_metadata_and_invalid_turn_total_are_gaps(self):
        for key in ('root_turn_id', 'response_id', 'turn_token_usage'):
            with self.subTest(key=key):
                rows = [self.native(100, 500, 500, 'first'), self.native(200, 900, 400, 'second')]
                rows[-1]['payload'].pop(key)
                self.write(rows)
                self.assertIn('invalid_response_usage_record', self.collect()['gaps'])

    def test_conflicting_response_and_regression_keep_high_water(self):
        rows = [self.native(100, 500, 500, 'first'), self.native(200, 900, 400, 'second'), self.native(300, 800, 100, 'third')]
        self.write(rows)
        report = self.collect()
        self.assertEqual(report['tokens']['total_tokens'], 400)
        self.assertIn('counter_reset_or_regression', report['gaps'])
        rows[-1] = self.native(300, 1000, 500, 'second')
        self.write(rows)
        report = self.collect()
        self.assertEqual(report['tokens']['total_tokens'], 500)
        self.assertIn('conflicting_token_response', report['gaps'])

    def test_prefix_and_phase_baseline_cannot_be_invented(self):
        self.write([self.native(200, 900, 400, 'first')])
        for brain in (False, True):
            with self.subTest(brain=brain), self.assertRaises(Refusal): self.collect(brain=brain)
        # Even with a previous legacy counter, there is no modern baseline.
        self.write([self.legacy(100, 500, 500), self.native(200, 900, 400, 'first')])
        with self.assertRaises(Refusal): self.collect()

    def test_cutoff_precedes_new_protocol_and_ignores_future_bad_records(self):
        bad = self.native(300, 1400, 500, 'later'); bad['payload']['usage'] = None
        self.write([self.legacy(100, 500, 500), self.legacy(200, 900, 400), bad])
        report = self.collect(end=250)
        self.assertEqual(report['tokens']['total_tokens'], 400)
        self.assertEqual(report['gaps'], [])
        self.assertNotIn('counterSource', report)
        self.write([self.native(100, 500, 500, 'first'), self.native(200, 900, 400, 'second'), bad])
        self.assertEqual(self.collect(end=250)['gaps'], [])

    def test_compaction_before_phase_is_in_baseline_not_new_consumption(self):
        self.write(self.compacted_rows())
        report = self.collect(start=250)
        self.assertEqual(report['tokens']['total_tokens'], 400)
        self.assertEqual(report['compactionCalls'], 0)
        self.assertEqual(report['compactionTokens']['total_tokens'], 0)
        self.assertEqual(report['gaps'], [])

    def test_closeout_is_separate_from_checkpoint_interval(self):
        self.write(self.compacted_rows())
        phase = self.collect(end=250)
        closeout = self.collect(start=250)
        self.assertEqual(phase['tokens']['total_tokens'], 500)
        self.assertEqual(closeout['tokens']['total_tokens'], 400)
        self.assertEqual(phase['gaps'], [])
        self.assertEqual(closeout['gaps'], [])

    def test_missing_timestamp_and_malformed_tail_remain_unknown(self):
        rows = [self.native(100, 500, 500, 'first'), self.native(200, 900, 400, 'second')]
        rows[-1].pop('timestamp'); self.write(rows)
        with self.assertRaises(Refusal): self.collect()
        self.write(self.compacted_rows())
        with self.path.open('a') as f: f.write('{')
        self.assertIn('incomplete_or_malformed_record', self.collect()['gaps'])

    def test_invalid_modern_baseline_and_legacy_total_remain_gaps(self):
        rows = self.compacted_rows()
        rows[0]['payload']['usage']['total_tokens'] += 1
        self.write(rows)
        self.assertIn('invalid_response_usage_record', self.collect()['gaps'])
        rows = self.compacted_rows()
        rows[-1]['payload']['info']['total_token_usage']['total_tokens'] += 1
        self.write(rows)
        self.assertIn('invalid_token_record', self.collect()['gaps'])

    def test_multiple_compactions_and_nonadditive_cache_write_subset(self):
        rows = self.compacted_rows()
        second = self.native(310, 1500, 100, 'compact-2')
        for name in ('usage', 'turn_token_usage', 'thread_token_usage'):
            second['payload'][name]['cache_write_input_tokens'] = 10
        estimate = self.legacy(312, 1300, 0)
        estimate['payload']['info']['last_token_usage']['total_tokens'] = 80
        rows += [second, self.compaction(311, second), estimate,
                 self.native(320, 1600, 100, 'last'), self.legacy(321, 1400, 100)]
        self.write(rows)
        report = self.collect()
        self.assertEqual(report['tokens']['total_tokens'], 1100)
        self.assertEqual(report['compactionCalls'], 2)
        self.assertEqual(report['compactionTokens']['total_tokens'], 200)
        self.assertEqual(report['gaps'], [])
        # A different marker's cache-write metadata cannot reconcile this response.
        rows[-4]['payload']['latest_token_usage_record']['usage']['cache_write_input_tokens'] = 11
        self.write(rows)
        self.assertIn('unreconciled_compaction_usage', self.collect()['gaps'])

    def test_invalid_turn_continuity_and_scalar_json_remain_gaps(self):
        rows = [self.native(100, 500, 500, 'first'), self.native(200, 900, 400, 'second', turn_total=800)]
        self.write(rows)
        self.assertIn('response_usage_discontinuity', self.collect()['gaps'])
        self.write(self.compacted_rows())
        with self.path.open('a') as f: f.write('[]\n')
        self.assertIn('incomplete_or_malformed_record', self.collect()['gaps'])

    def test_output_reasoning_and_cache_deltas_are_subsets_not_extra_charges(self):
        first = self.native(100, 500, 500, 'first')
        second = self.native(200, 600, 100, 'second')
        baseline = vector(500, cached=200, output=50, reasoning=20)
        delta = vector(100, cached=64, output=12, reasoning=5)
        total = vector(600, cached=264, output=62, reasoning=25)
        for name in ('thread_token_usage', 'usage', 'turn_token_usage'):
            first['payload'][name] = baseline.copy()
        second['payload'].update(thread_token_usage=total, usage=delta, turn_token_usage=total)
        self.write([first, second])
        report = self.collect()
        self.assertEqual(report['tokens'], delta)
        self.assertEqual(report['tokens']['total_tokens'], 100)
        self.assertEqual(report['gaps'], [])

    def test_refresh_and_request_replay_preserve_pause_history_and_high_water(self):
        self.write(self.compacted_rows())
        ledger = Ledger(self.path.parent / 'ledger')
        ledger.initialize({'schemaVersion': 1, 'brainId': self.identity, 'repositories': [
            {'id': 'app', 'path': str(self.path.parent), 'projectId': 'fixture', 'ref': 'HEAD',
             'policyProfile': 'standard', 'mergePolicy': 'manual'}]})
        checkpoint = {'at': 350, 'summary': 'saved safety stop', 'reasonCodes': ['usage_evidence']}
        run = {'id': 'run', 'protocol': 'standard_cooperative_v1', 'revision': 0,
               'brainId': self.identity, 'startedAt': 150, 'status': 'paused',
               'checkpoint': checkpoint, 'tasks': [], 'brainObservedTokens': 400,
               'brainUsageCoverage': 'observed_partial', 'usageHighWater': 400,
               'limits': {'tokenBudget': 2000, 'checkpointReserveTokens': 100}}
        old_report = {'scopeHash': brain_memory.scope(run), 'runId': 'run', 'collectedAt': 250,
                      'gaps': ['invalid_token_record'], 'tokens': vector(400), 'coverage': 'gapped'}
        run['usageReport'] = old_report
        with ledger.tx() as db:
            meta = ledger.get(db, 'meta', 1); meta['standardRun'] = run
            ledger.put(db, 'meta', 1, meta)
            db.execute('INSERT INTO snapshots VALUES(?,?,?)', ('old', 'standard_usage', json.dumps(old_report)))
        def collect(_ledger, snapshot):
            report = self.collect(); report['role'] = 'brain'
            return {'scopeHash': brain_memory.scope(snapshot), 'runId': 'run', 'collectedAt': 350,
                    'through': 350, 'records': [report], 'tokens': report['tokens'],
                    'gaps': report['gaps'], 'coverage': 'observed_local'}
        with patch.object(brain_memory, 'collect', side_effect=collect):
            first = brain_memory.refresh(ledger, 'run', 'explicit-refresh')
        with patch.object(brain_memory, 'collect', side_effect=AssertionError('replay must not recollect')):
            replay = brain_memory.refresh(ledger, 'run', 'explicit-refresh')
        self.assertEqual(first, replay)
        retained = ledger.snapshot()['meta']['standardRun']
        self.assertEqual(retained['status'], 'paused')
        self.assertEqual(retained['checkpoint'], checkpoint)
        self.assertEqual(retained['tasks'], [])
        self.assertEqual(retained['usageHighWater'], 900)
        self.assertEqual(retained['brainObservedTokens'], 900)
        self.assertEqual(ledger.snapshot()['commands'], [])
        with ledger.connect() as db:
            self.assertEqual(json.loads(db.execute("SELECT data FROM snapshots WHERE id='old'").fetchone()[0]), old_report)


if __name__ == '__main__':
    unittest.main()
