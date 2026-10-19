"""Synthetic numeric history and native metadata only; no live home/model."""
import copy
import datetime as dt
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from orchestrator import post_preparation_usage as api, handoff_reconciliation as completion
from orchestrator.core import Refusal, canonical, digest
import test_handoff_reconciliation as fixtures


def stamp(at): return dt.datetime.fromtimestamp(at,dt.timezone.utc).isoformat()
def vector(n): return {'input_tokens':n,'cached_input_tokens':0,'output_tokens':0,'reasoning_output_tokens':0,'total_tokens':n}
def token(at,total,last):
    return {'timestamp':stamp(at),'type':'event_msg','payload':{'type':'token_count',
        'info':{'total_token_usage':vector(total),'last_token_usage':vector(last)}}}


def native_token(at,brain,turn,response,total,last,turn_total):
    return {'timestamp':stamp(at),'type':'token_usage_record','payload':{'thread_id':brain,'session_id':brain,
        'turn_id':turn,'root_turn_id':turn,'response_id':response,'thread_token_usage':vector(total),
        'usage':vector(last),'turn_token_usage':vector(turn_total)}}


class UsageTest(unittest.TestCase):
    def setUp(self):
        def history(f):
            start=f.m.parent['original']['run']['startedAt']
            return [{'timestamp':stamp(start-3),'type':'session_meta','payload':{'id':f.f.brain,'cwd':str(f.f.repo)}},
                *( [native_token(start-2,f.f.brain,f.f.turn,'old-baseline',100,100,100),
                    native_token(start+.01,f.f.brain,f.f.turn,'old-in-phase',300,200,300)] if getattr(self,'native',False)
                    else [token(start-2,100,100),token(start+.01,300,200)] ),
                {'timestamp':stamp(start+0.02),'type':'event_msg','payload':{'type':'task_complete','turn_id':f.f.turn}}]
        self.f=fixtures.ReconciliationTest('runTest')
        self.addCleanup(self.f.doCleanups)
        with patch.object(fixtures.fixtures.HostTransferTest,'history_rows',history): self.f.setUp()
        self.q=self.f.q; self.registry=self.f.registry; self.ledger=self.f.ledger
        now=self.f.f.now; self.f.f.now+=2
        rows=[json.loads(line) for line in self.f.target.read_text().splitlines()][-2:]
        rows[0]['timestamp']=stamp(now+.25); rows[-1]['timestamp']=stamp(now+1.5)
        rows.insert(-1,native_token(now+1,self.q['original']['brainId'],rows[0]['payload']['turn_id'],
            'new-preparation',500,200,200) if getattr(self,'native',False) else token(now+1,500,200))
        transfer=completion.handoff.transfer_record(self.q)
        prefix=completion.handoff.transfer.read_archive(transfer['archivePath'])
        self.f.target.write_bytes(prefix+''.join(canonical(row)+'\n' for row in rows).encode())
        self.assertEqual(self.f.collect()['status'],'preparation_completion_observed')
        self.out=self.f.f.f.root/'post-usage'
        self.completed=self.f.out

    def collect(self): return api.collect(self.registry,self.ledger,self.completed,self.out)
    def conserved(self): self.f.conserved()

    def test_positive_counts_inherited_prefix_once_and_carries_both_baselines(self):
        result=self.collect(); self.assertEqual(result['status'],'usage_observed',result)
        self.assertEqual(result['report']['tokens']['total_tokens'],400)
        self.assertEqual(result['report']['records'][0]['calls'],2)
        self.assertEqual(result,api.status(self.registry,self.ledger,self.out))
        self.assertEqual(result['newTurnInterval']['completedAt'],result['report']['through'])
        self.assertAlmostEqual(result['report']['records'][0]['sampleAt'],self.f.f.now-1,places=5)
        self.assertFalse(result['boundary']['executionAuthorized']); self.conserved()

    def test_reads_status_without_recollecting_or_refreshing_after_expiry(self):
        result=self.collect(); calls=list(self.f.calls); self.f.f.now+=86400*2
        with patch.object(api,'observation',side_effect=AssertionError('No numeric reread')):
            self.assertEqual(api.status(self.registry,self.ledger,self.out),result)
        self.assertEqual(self.f.calls,calls)
        with self.assertRaises(Refusal): api.status(self.registry,self.ledger,self.out,fresh=True)
        self.conserved()

    def test_missing_new_turn_numeric_sample_stays_unknown_without_retry(self):
        with patch.object(api.brain_memory,'session_usage',side_effect=Refusal('Missing numeric prefix')):
            result=self.collect()
        self.assertEqual(result['status'],'unknown')
        with self.assertRaises(Refusal): api.status(self.registry,self.ledger,self.out,fresh=True)
        calls=list(self.f.calls)
        with self.assertRaises(Refusal): self.collect()
        self.assertEqual(calls,self.f.calls); self.conserved()

    def test_regression_is_retained_gapped_not_refunded(self):
        actual=api.brain_memory.session_usage
        def regressed(*args,**kw):
            row=actual(*args,**kw); row['tokens']=vector(1); row['gaps']=['counter_reset_or_regression']; return row
        with patch.object(api.brain_memory,'session_usage',regressed): result=self.collect()
        self.assertEqual(result['status'],'usage_gapped')
        self.assertIn('incomplete_or_regressed_post_turn_usage',result['issues'])
        with self.assertRaises(Refusal): api.status(self.registry,self.ledger,self.out,fresh=True)
        self.conserved()

    def test_higher_consumption_exhaustion_is_not_hidden(self):
        actual=api.brain_memory.session_usage
        def overrun(*args,**kw):
            row=actual(*args,**kw); row['tokens']=vector(1_000_000); return row
        with patch.object(api.brain_memory,'session_usage',overrun): result=self.collect()
        self.assertEqual(result['status'],'usage_gapped')
        self.assertIn('unchanged_budget_or_reserve_exhausted',result['issues']); self.conserved()

    def test_retained_counter_tamper_cannot_refund_a_baseline(self):
        result=self.collect(); result['report']['tokens']=vector(1); result['report']['records'][0]['tokens']=vector(1)
        (self.out/'evidence.json').write_text(canonical(result))
        with self.assertRaises(Refusal): api.status(self.registry,self.ledger,self.out)
        self.conserved()

    def test_native_file_growth_invalidates_old_accounting_without_read_or_collection(self):
        self.collect()
        with self.f.target.open('a') as stream: stream.write(canonical(token(self.f.f.now+1,600,100))+'\n')
        calls=list(self.f.calls)
        with self.assertRaises(Refusal): api.status(self.registry,self.ledger,self.out)
        self.assertEqual(self.f.calls,calls)

    def test_native_authentication_gap_has_no_refresh_load_or_turn(self):
        self.f.auth=False; result=self.collect(); self.assertEqual(result['status'],'unknown')
        self.assertTrue(all(method in {'account/read','project/read','thread/read','thread/turns/list'} for method,_ in self.f.calls))
        self.conserved()

    def test_foreign_native_or_old_claim_change_fails_closed(self):
        self.f.foreign=True; self.assertEqual(self.collect()['status'],'unknown'); self.conserved()

    def test_no_collection_inside_old_journals_repository_native_or_evidence(self):
        for root in (Path(self.q['journal'])/'usage-evidence',self.f.f.home/'extra',self.f.f.f.repo/'extra',self.completed/'extra'):
            with self.subTest(root=root),self.assertRaises(Refusal):
                api.collect(self.registry,self.ledger,self.completed,root)
        self.conserved()

    def test_extra_or_partial_evidence_files_cannot_be_used(self):
        self.collect(); (self.out/'extra.json').write_text('{}')
        with self.assertRaises(Refusal): api.status(self.registry,self.ledger,self.out)

    def test_historical_completion_source_is_hash_read_only_and_allowlisted(self):
        original=completion.context
        intent=json.loads((self.completed/'intent.json').read_text()); result=json.loads((self.completed/'evidence.json').read_text())
        intent['currentSourceHash']=completion.PR182_SOURCE; result['context']=intent
        (self.completed/'intent.json').write_text(canonical(intent)); (self.completed/'evidence.json').write_text(canonical(result))
        with self.assertRaises(Refusal): completion.status(self.registry,self.ledger,self.completed)
        with patch.object(completion.handoff.phase.lifecycle,'source_proof',return_value={'sourceHash':'0'*64}):
            with self.assertRaises(Refusal): completion.status(self.registry,self.ledger,self.completed,completion_source=self.out)
        with patch.object(completion.handoff.phase.lifecycle,'source_proof',return_value={'sourceHash':completion.PR182_SOURCE}):
            self.assertEqual(completion.status(self.registry,self.ledger,self.completed,completion_source=self.out),result)
        self.assertIs(completion.context,original)


class NativeUsageTest(unittest.TestCase):
    def test_native_response_journal_counts_prefix_once_without_legacy_fallback(self):
        f=UsageTest('runTest'); f.native=True; self.addCleanup(f.doCleanups); f.setUp()
        result=f.collect(); self.assertEqual(result['status'],'usage_observed',result)
        row=result['report']['records'][0]
        self.assertEqual(row['counterSource'],'native_response_usage_v1')
        self.assertEqual(row['tokens']['total_tokens'],400); self.assertEqual(row['calls'],2)
        self.assertEqual(result,api.status(f.registry,f.ledger,f.out)); f.conserved()


if __name__=='__main__': unittest.main()
