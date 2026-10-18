"""Real local numeric fixtures; no live home, native connection or model service."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from orchestrator import brain_memory, canceled_continuation as api, forward_usage as usage
from orchestrator.core import Refusal, canonical, digest
import test_canceled_continuation as fixtures


class ForwardUsageTest(unittest.TestCase):
    def setUp(self):
        def measured(owner,run):
            for file in owner.f.home.rglob('*.jsonl'): file.chmod(0o600)
            return brain_memory.collect(owner.ledger,run)
        self.o=fixtures.ContinuationTest('runTest')
        with patch.object(fixtures.ContinuationTest,'usage_baseline',measured): self.o.setUp()
        self.addCleanup(self.o.doCleanups)
        self.f=self.o.f; self.ledger=self.o.ledger; self.registry=self.o.registry
        self.original=copy.deepcopy(self.o.q['original'])
        self.now=time.time()+181
        self.q=self.prepare()['request']; self.o.q=self.q
        self.backup=self.f.root/'usage-backup'; self.o.backup=self.backup
        with self.clock(): api.backup(self.registry,self.ledger,self.q,self.backup,writers_stopped=True)
        self.log=next(self.f.home.rglob('*.jsonl'))

    def clock(self): return patch('time.time',return_value=self.now)

    def prepare(self):
        with self.clock():
            return api.prepare(self.registry,self.ledger,self.o.old.binding_file,self.o.old.cid,
                self.o.candidate,self.o.contract,1,forward_usage_evidence=True)

    def run_control(self):
        with self.clock(): return self.o.run_control()

    def append(self,total=450,at=None):
        # Numeric fixture append only. Production never edits a native log.
        at=self.now-1 if at is None else at
        vector=lambda n:{'input_tokens':n,'cached_input_tokens':0,'output_tokens':0,
            'reasoning_output_tokens':0,'total_tokens':n}
        row={'type':'event_msg','timestamp':dt.datetime.fromtimestamp(at,dt.timezone.utc).isoformat(),
            'payload':{'type':'token_count','info':{'total_token_usage':vector(total),
                'last_token_usage':vector(max(0,total-300))}}}
        with self.log.open('a') as stream: stream.write(canonical(row)+'\n')

    def record(self): return json.loads((Path(self.q['journal'])/'usage.json').read_bytes())

    def no_native(self): self.assertEqual(self.o.Proxy.instances,[])

    def test_stale_baseline_new_collection_is_monotone_without_changing_old_rows(self):
        old=copy.deepcopy(self.q['original']['run']['usageReport']); self.append()
        result=self.run_control()
        for worker in self.o.workers: worker.join(2)
        self.assertEqual(result['status'],'planning_completed')
        record=self.record(); report=record['report']
        self.assertGreater(report['collectedAt']-old['collectedAt'],120)
        self.assertEqual(report['tokens']['total_tokens'],350)
        self.assertAlmostEqual(report['records'][0]['sampleAt'],self.now-1,places=5)
        self.assertEqual(record['baselineHash'],digest(old))
        self.assertEqual(self.q['original']['run']['usageReport'],old)
        with self.clock(): self.assertEqual(api.status(self.q),result)
        self.o.conserved()
        with patch('time.time',return_value=self.q['original']['run']['expiresAt']+1):
            self.assertEqual(api.status(self.q),result)  # Historical reads do not renew evidence.

    def test_default_v1_still_refuses_stale_usage_and_never_silently_upgrades(self):
        with self.clock(),self.assertRaisesRegex(Refusal,'Fresh'):
            api.prepare(self.registry,self.ledger,self.o.old.binding_file,self.o.old.cid,
                self.o.candidate,self.o.contract,1)
        self.no_native(); self.o.conserved()

    def test_prepare_backup_status_never_collect_or_claim(self):
        with patch.object(usage,'collect',side_effect=AssertionError('No read collection')):
            self.assertEqual(self.prepare()['request'],self.q)
            with self.clock(): api.backup(self.registry,self.ledger,self.q,self.f.root/'another-backup',writers_stopped=True)
            self.assertEqual(api.status(self.q)['status'],'not_submitted')
        self.assertFalse(Path(self.q['journal']).exists()); self.no_native(); self.o.conserved()

    def test_unknown_or_incomplete_baseline_cannot_acquire_freshness(self):
        for field,value in [('records',[]),('gaps',['old_gap']),('tokens',{'total_tokens':200})]:
            o=copy.deepcopy(self.original); o['run']['usageReport'][field]=value
            o['usageReceiptHash']=digest(o['run']['usageReport'])
            with self.subTest(field=field),self.assertRaises(Refusal): usage.baseline(o)
        o=copy.deepcopy(self.original); o['run']['brainUsageCoverage']=None
        with self.assertRaises(Refusal): usage.baseline(o)
        self.no_native()

    def test_missing_and_gapped_logs_consume_collection_without_native_connection(self):
        self.log.write_text(self.log.read_text()+'{\n')
        result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown'); self.assertTrue(self.record()['report']['gaps'])
        with self.assertRaises((Refusal,OSError)): self.run_control()
        with self.assertRaises(Refusal): self.prepare()
        self.no_native(); self.o.conserved()

    def test_missing_log_never_becomes_zero_or_retries(self):
        self.log.unlink(); result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown')
        self.assertTrue((Path(self.q['journal'])/'usage.claim.json').exists())
        self.assertFalse((Path(self.q['journal'])/'usage.json').exists())
        self.no_native(); self.o.conserved()

    def test_regression_is_retained_and_cannot_refund_old_usage(self):
        self.append(250); result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown')
        self.assertIn('counter_reset_or_regression',self.record()['report']['gaps'])
        self.no_native(); self.o.conserved()

    def test_higher_actual_usage_cannot_overrun_brain_allowance(self):
        self.append(100000); result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown')
        self.assertEqual(self.record()['report']['tokens']['total_tokens'],99900)
        self.no_native(); self.o.conserved()

    def test_old_high_water_is_not_refunded_even_with_valid_new_counters(self):
        o=copy.deepcopy(self.original); o['run']['usageHighWater']=1000
        with self.assertRaisesRegex(Refusal,'high-water'):
            usage.budget(o,1,o['run']['usageReport'])

    def test_per_session_vector_and_sample_regressions_are_not_hidden_by_aggregate(self):
        original=copy.deepcopy(self.original); baseline=original['run']['usageReport']
        baseline['records'][0]['tokens'].update(cached_input_tokens=100)
        baseline['tokens'].update(cached_input_tokens=100); original['usageReceiptHash']=digest(baseline)
        for change in ('cache','calls','time'):
            report=copy.deepcopy(baseline)
            if change=='cache':
                report['tokens']['cached_input_tokens']=0; report['records'][0]['tokens']['cached_input_tokens']=0
            elif change=='calls': report['records'][0]['calls']=0
            else: report['records'][0]['sampleAt']-=1
            with self.subTest(change=change),self.assertRaises(Refusal): usage.budget(original,1,report)

    def test_aggregate_foreign_identity_future_and_nonfinite_observations_refuse(self):
        for change in ('sum','identity','future','nan'):
            report=copy.deepcopy(self.original['run']['usageReport'])
            if change=='sum': report['tokens']['total_tokens']+=1
            if change=='identity': report['records'][0]['sessionId']='foreign'
            if change=='future': report['collectedAt']=time.time()+1000
            if change=='nan': report['collectedAt']=float('nan')
            with self.subTest(change=change),self.assertRaises(Refusal): usage.budget(self.original,1,report)

    def test_expiry_is_not_extended_by_new_report(self):
        self.now=self.q['original']['run']['expiresAt']+1
        with self.assertRaisesRegex(Refusal,'expired'): self.run_control()
        self.assertFalse(Path(self.q['journal']).exists()); self.no_native(); self.o.conserved()

    def test_collection_stale_during_subscribe_cannot_start_or_resample(self):
        original=api.transport.Subscription.attach
        def delayed(sub,claim):
            result=original(sub,claim); self.now+=121
            return result
        with patch.object(api.transport.Subscription,'attach',delayed):
            # Use a callable clock, so the simulated I/O delay advances time.
            with patch('time.time',side_effect=lambda:self.now): result=self.o.run_control()
        self.assertEqual(result['status'],'incomplete_unknown')
        self.assertFalse(any(m=='turn/start' for m,_ in self.o.Proxy.instances[-1].calls))
        self.assertEqual(api.status(self.q),result); self.o.conserved()

    def test_expiry_during_collection_prevents_any_native_connection(self):
        original=usage.collect
        def delayed(ledger,q):
            result=original(ledger,q); self.now=q['original']['run']['expiresAt']+1; return result
        with patch.object(usage,'collect',delayed),patch('time.time',side_effect=lambda:self.now):
            result=self.o.run_control()
        self.assertEqual(result['status'],'incomplete_unknown'); self.no_native(); self.o.conserved()

    def test_collection_failure_remains_canonical_across_review_versions(self):
        with patch.object(usage.brain_memory,'session_usage',side_effect=OSError('Fixture interrupted read')):
            result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown')
        q=copy.deepcopy(self.o.q); q.pop('usageSource'); q.update(version=1,kind=api.KIND)
        with self.assertRaises((Refusal,OSError)),patch('time.time',return_value=self.original['run']['usageReport']['collectedAt']):
            api.confirm(self.registry,self.ledger,q,digest(q),writers_stopped=True,backup_root=self.backup)
        self.no_native(); self.o.conserved()

    def test_directory_replacement_refuses_before_claim(self):
        root=self.f.home/'sessions'; root.rename(self.f.home/'old-sessions'); root.mkdir()
        with self.assertRaisesRegex(Refusal,'source/configuration'): self.run_control()
        self.assertFalse(Path(self.q['journal']).exists()); self.no_native()

    def test_hardlinked_telemetry_refuses_before_native_io(self):
        os.link(self.log,self.log.with_suffix('.alias'))
        self.assertEqual(self.run_control()['status'],'incomplete_unknown'); self.no_native(); self.o.conserved()

    def test_symlink_telemetry_refuses_before_native_io(self):
        original=self.log.with_suffix('.original'); self.log.rename(original); self.log.symlink_to(original)
        self.assertEqual(self.run_control()['status'],'incomplete_unknown'); self.no_native(); self.o.conserved()

    def test_changed_configuration_refuses_before_collection(self):
        file=self.ledger.root/'observations.json'; file.write_text('{}')
        with self.assertRaises((Refusal,KeyError)): self.run_control()
        self.assertFalse(Path(self.q['journal']).exists()); self.no_native()

    def test_changed_usage_journal_is_not_completion_or_refresh(self):
        result=self.run_control(); self.assertEqual(result['status'],'planning_completed')
        (Path(self.q['journal'])/'usage.json').write_text('{}')
        with self.assertRaisesRegex(Refusal,'changed'): api.status(self.q)
        self.o.conserved()

    def test_owner_stop_after_collection_wins_before_connect(self):
        original=usage.collect
        def stopped(ledger,q):
            result=original(ledger,q); api.stop(q,digest(q)); return result
        with patch.object(usage,'collect',stopped): result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown'); self.no_native(); self.o.conserved()

    def test_telemetry_append_during_collection_consumes_attempt_without_resample(self):
        original=usage.brain_memory.session_usage
        def changed(*args,**kw):
            value=original(*args,**kw); self.append(); return value
        with patch.object(usage.brain_memory,'session_usage',changed): result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown'); self.no_native(); self.o.conserved()

    def test_source_change_during_collection_fences_send(self):
        original=usage.collect
        def changed(ledger,q):
            result=original(ledger,q); os.utime(ledger.root/'observations.json',None); return result
        with patch.object(usage,'collect',changed): result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown'); self.no_native()

    def test_interrupted_collection_claim_cannot_be_read_as_qualified_evidence(self):
        root=Path(self.q['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        api.exclusive(root/'intent.json',{'kind':self.q['kind'],'reviewHash':digest(self.q)})
        api.exclusive(root/'usage.claim.json',{'kind':usage.KIND,'reviewHash':digest(self.q),
            'sourceHash':digest(self.q['usageSource']),'baselineHash':self.q['original']['usageReceiptHash']})
        self.assertEqual(api.status(self.q)['status'],'claimed_outcome_unknown')
        with self.assertRaises((Refusal,OSError)): self.run_control()
        self.no_native(); self.o.conserved()

    def test_phase_reserve_brain_and_invalid_allowance_checks_stay_independent(self):
        baseline=self.original['run']['usageReport']
        for change in ('phase','reserve','brain','allowance'):
            o=copy.deepcopy(self.original); maximum=1
            if change=='phase': o['run']['limits']['tokenBudget']=baseline['tokens']['total_tokens']
            if change=='reserve': o['run']['limits']['checkpointReserveTokens']=o['run']['limits']['tokenBudget']
            if change=='brain': o['run']['brainAllowance']=baseline['tokens']['total_tokens']
            if change=='allowance': maximum=True
            with self.subTest(change=change),self.assertRaises(Refusal): usage.budget(o,maximum,baseline)

    def test_duplicate_archive_does_not_double_count_or_renew_sample_timestamp(self):
        nested=self.f.home/'sessions'/'archive'; nested.mkdir()
        duplicate=nested/self.log.name; duplicate.write_bytes(self.log.read_bytes()); duplicate.chmod(0o600)
        result=self.run_control(); self.assertEqual(result['status'],'planning_completed')
        report=self.record()['report']; old=self.original['run']['usageReport']
        self.assertEqual(report['tokens'],old['tokens'])
        self.assertEqual(report['records'][0]['sampleAt'],old['records'][0]['sampleAt'])
        self.assertEqual(report['records'][0]['calls'],old['records'][0]['calls']); self.o.conserved()

    def test_exact_concurrent_confirmation_has_one_collection_and_one_native_turn(self):
        import threading
        results=[]; collection=usage.collect
        def run():
            try: results.append(self.o.run_control()['status'])
            except (Refusal,OSError): results.append('refused')
        with self.clock(),patch.object(usage,'collect',wraps=collection) as measured:
            threads=[threading.Thread(target=run) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(10); self.assertFalse(thread.is_alive())
        self.assertCountEqual(results,['planning_completed','refused']); self.assertEqual(measured.call_count,1)
        self.assertEqual(len(self.o.Proxy.instances),1); self.o.conserved()


if __name__=='__main__': unittest.main()
