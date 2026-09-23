import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import threading

from orchestrator.brain_memory import blockers, session_usage
from orchestrator import brain_memory
from orchestrator.core import Ledger, Refusal


def vector(total, cached=0, output=0, reasoning=0):
    return {'input_tokens': total - output, 'cached_input_tokens': cached,
            'output_tokens': output, 'reasoning_output_tokens': reasoning,
            'total_tokens': total}


class BrainMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name).resolve() / 'rollout.jsonl'
        self.identity = str(uuid.uuid4())

    def write(self, samples, duplicate=False, malformed=False, session_start=None):
        header = {'type': 'session_meta', 'payload': {'id': self.identity}}
        if session_start is not None:
            header['timestamp'] = dt.datetime.fromtimestamp(session_start, dt.timezone.utc).isoformat()
        rows = [header]
        for second, total, last in samples:
            row = {'type': 'event_msg', 'timestamp': dt.datetime.fromtimestamp(second, dt.timezone.utc).isoformat(),
                       'payload': {'type': 'token_count', 'info': {
                       'total_token_usage': vector(total, cached=total // 2),
                       'last_token_usage': vector(last, cached=total // 2 if session_start is not None and last == total else 0)}}}
            rows.append(row)
            if duplicate: rows.append(row)
        self.path.write_text('\n'.join(json.dumps(row) for row in rows) + ('\n{' if malformed else '\n'))

    def test_exact_brain_phase_delta_deduplicates_cache_and_marks_gap(self):
        self.write([(100, 500, 500), (200, 900, 400), (300, 1400, 500)], duplicate=True, malformed=True)
        report = session_usage([self.path], self.identity, 150, 350, True)
        self.assertEqual(report['tokens']['total_tokens'], 900)
        self.assertEqual(report['tokens']['cached_input_tokens'], 450)
        self.assertEqual(report['calls'], 2)
        self.assertIn('incomplete_or_malformed_record', report['gaps'])

    def test_missing_baseline_and_counter_regression_are_not_complete(self):
        self.write([(200, 900, 400)])
        with self.assertRaises(Refusal): session_usage([self.path], self.identity, 150, 350, True)
        self.write([(100, 500, 500), (200, 400, 50)])
        report = session_usage([self.path], self.identity, 150, 350, True)
        self.assertIn('counter_reset_or_regression', report['gaps'])

    def test_worker_prefix_missing(self):
        self.write([(200, 900, 400)])
        with self.assertRaises(Refusal): session_usage([self.path], self.identity, 150, 350)

    def test_delayed_closeout_is_not_charged_to_checkpoint_interval(self):
        self.write([(100, 500, 500), (200, 900, 400), (300, 1000, 100)])
        phase = session_usage([self.path], self.identity, 150, 250, True)
        closeout = session_usage([self.path], self.identity, 250, 350, True)
        self.assertEqual(phase['tokens']['total_tokens'], 400)
        self.assertEqual(closeout['tokens']['total_tokens'], 100)
        with self.assertRaises(Refusal):
            session_usage([self.path], self.identity, 350, 400, True)

    def test_new_replacement_brain_can_start_at_zero_without_old_prefix(self):
        self.write([(210, 100, 100), (220, 180, 80)], session_start=200)
        report = session_usage([self.path], self.identity, 190, 250, True)
        self.assertEqual(report['tokens']['total_tokens'], 180)
        self.write([(210, 180, 80)], session_start=200)
        with self.assertRaises(Refusal):
            session_usage([self.path], self.identity, 190, 250, True)

    def test_fresh_complete_usage_required_for_new_effect(self):
        run = {'usageGuardVersion': 1, 'id': 'run', 'brainId': self.identity, 'startedAt': 1,
               'tasks': [], 'status': 'running', 'checkpoint': None, 'limits': {
                   'tokenBudget': 1000, 'checkpointReserveTokens': 100}}
        self.assertTrue(blockers(run))
        from orchestrator.brain_memory import scope
        import time
        run['usageReport'] = {'scopeHash': scope(run), 'collectedAt': time.time(),
                              'gaps': [], 'tokens': vector(800), 'records': []}
        self.assertEqual(blockers(run), [])
        run['usageReport']['gaps'] = ['counter_reset']
        self.assertTrue(blockers(run))
        run['usageReport']['gaps'] = []
        run['usageReport']['tokens'] = vector(900)
        self.assertTrue(blockers(run))

    def test_concurrent_refresh_never_refunds_retained_high_water(self):
        ledger = Ledger(self.path.parent / 'ledger')
        ledger.initialize({'schemaVersion': 1, 'brainId': self.identity, 'repositories': [
            {'id': 'app', 'path': str(self.path.parent), 'projectId': 'fixture', 'ref': 'HEAD',
             'policyProfile': 'standard', 'mergePolicy': 'manual'}]})
        run_id = str(uuid.uuid4())
        run = {'id': run_id, 'protocol': 'standard_cooperative_v1', 'revision': 0,
               'brainId': self.identity, 'startedAt': 100, 'status': 'running',
               'checkpoint': None, 'tasks': [], 'brainObservedTokens': 0,
               'brainUsageCoverage': 'not_observed', 'limits': {'tokenBudget': 2000,
                                                                'checkpointReserveTokens': 100}}
        with ledger.tx() as db:
            meta = ledger.get(db, 'meta', 1)
            meta['standardRun'] = run
            ledger.put(db, 'meta', 1, meta)
        def report(_ledger, snapshot, total):
            return {'scopeHash': brain_memory.scope(snapshot), 'runId': run_id,
                    'collectedAt': 1000, 'through': 1000, 'records': [{
                        'role': 'brain', 'sessionId': self.identity, 'tokens': vector(total),
                        'sampleAt': 1000, 'calls': 1, 'lastInputTokens': total, 'gaps': []}],
                    'tokens': vector(total), 'gaps': [], 'coverage': 'observed_local'}
        with patch.object(brain_memory, 'collect', side_effect=lambda l, r: report(l, r, 800)):
            brain_memory.refresh(ledger, run_id)
        barrier = threading.Barrier(2)
        def collect_lower(l, r):
            barrier.wait(timeout=5)
            return report(l, r, 300)
        with patch.object(brain_memory, 'collect', side_effect=collect_lower):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = [future.exception() for future in
                           [executor.submit(brain_memory.refresh, ledger, run_id) for _ in range(2)]]
        self.assertEqual(sum(error is None for error in results), 1)
        self.assertTrue(any(isinstance(error, Refusal) for error in results if error))
        retained = ledger.snapshot()['meta']['standardRun']
        self.assertEqual(retained['usageHighWater'], 800)
        self.assertEqual(retained['brainObservedTokens'], 800)


if __name__ == '__main__':
    unittest.main()
