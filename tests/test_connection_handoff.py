"""One continuous foreground connection, synthetic private fixtures only."""
import copy
import os
from pathlib import Path
import runpy
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orchestrator import connection_handoff as api, canceled_continuation as planning
from orchestrator.core import Refusal, digest
from orchestrator.host_lifecycle import write_record
import test_forward_usage as fixtures


class ConnectionHandoffTest(unittest.TestCase):
    def setUp(self):
        self.usage=fixtures.ForwardUsageTest('runTest'); self.usage.setUp(); self.addCleanup(self.usage.doCleanups)
        self.o=self.usage.o; self.f=self.o.f; self.registry,self.ledger=self.o.registry,self.o.ledger
        self.q=self.usage.q; self.file=self.f.root/'planning-review.json'; write_record(self.file,self.q)
        self.h=api.prepare(self.registry,self.ledger,self.file,60)['request']
        self.backup=self.f.root/'continuous-backup'
        api.backup(self.registry,self.ledger,self.h,self.backup,writers_stopped=True)
        self.failures=[]; self.results=[]; self.thread=None
        base=self.o.Proxy
        class Proxy(base):
            def __init__(self,endpoint):
                super().__init__(endpoint); r,w=os.pipe(); self.writer=w
                self.process=SimpleNamespace(stdout=os.fdopen(r,'rb',buffering=0),poll=lambda:None)
                self.buffer=b''; self.deadline=time.monotonic()+15
            def __exit__(self,*args):
                if self.process:
                    self.process.stdout.close(); os.close(self.writer)
                return super().__exit__(*args)
        p=patch.object(planning,'Proxy',Proxy); p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.thread and self.thread.is_alive():
            try: api.stop(self.h,digest(self.h))
            except (Refusal,OSError): pass
            self.thread.join(5)
        for worker in self.o.workers: worker.join(2)

    def start(self,cli=False):
        def run():
            try:
                if cli:
                    file=self.f.root/'continuous-review.json'; write_record(file,self.h)
                    args=['connection_handoff','--platform',str(self.registry.root),'--workspace',self.ledger.workspace_id,
                        'serve',str(file),'--confirm-hash',digest(self.h),'--writers-stopped','--backup',str(self.backup)]
                    with patch.object(sys,'argv',args): runpy.run_module('orchestrator.connection_handoff',run_name='__main__')
                    self.results.append(api.status(self.h))
                else:
                    self.results.append(api.serve(self.registry,self.ledger,self.h,digest(self.h),
                        writers_stopped=True,backup_root=self.backup))
            except BaseException as error: self.failures.append(error)
        self.thread=threading.Thread(target=run); self.thread.start()
        until=time.monotonic()+5
        while not (Path(self.h['journal'])/'ready-pin.json').exists():
            if not self.thread.is_alive(): self.fail(str(self.failures or self.results))
            self.assertLess(time.monotonic(),until); time.sleep(.01)

    def approve(self):
        preview=api.planning_review(self.registry,self.ledger,self.h)
        return api.authorize(self.registry,self.ledger,self.h,preview['request'],preview['reviewHash'])

    def finish(self):
        self.thread.join(10); self.assertFalse(self.thread.is_alive()); self.assertEqual(self.failures,[])
        return self.results[0]

    def test_separate_approval_same_connection_no_resubscribe_and_explicit_receipt(self):
        with patch.object(planning.forward_usage,'collect',wraps=planning.forward_usage.collect) as collect:
            self.start(); time.sleep(.2)
            self.assertEqual(collect.call_count,0)
            proxy=self.o.Proxy.instances[-1]
            self.assertEqual([m for m,_ in proxy.calls].count('thread/subscribe'),1)
            self.assertNotIn('turn/start',[m for m,_ in proxy.calls])
            self.assertEqual(api.status(self.h)['status'],'claimed_current_connection_unknown')
            self.approve(); result=self.finish(); self.assertEqual(collect.call_count,1)
        self.assertEqual(result['status'],'planning_completed'); self.assertTrue(result['connectionClosed'])
        self.assertEqual(len(self.o.Proxy.instances),1)
        methods=[m for m,_ in proxy.calls]
        self.assertEqual(methods.count('thread/subscribe'),1); self.assertEqual(methods.count('turn/start'),1)
        self.assertNotIn('thread/resume',methods); self.assertNotIn('turn/interrupt',methods)
        self.assertEqual(api.status(self.h),result); self.o.conserved()

    def test_module_cli_keeps_canonical_process_local_owner(self):
        self.start(cli=True); self.approve(); self.assertEqual(self.finish()['status'],'planning_completed')
        self.assertEqual(len(self.o.Proxy.instances),1); self.o.conserved()

    def test_consumed_planning_cannot_prepare_or_rearm_handoff(self):
        self.o.run_control()
        with self.assertRaisesRegex(Refusal,'Consumed/partial'): api.prepare(self.registry,self.ledger,self.file)
        report=api.assess(self.registry,self.ledger,self.file)
        self.assertIn('original_planning_attempt_consumed_no_rearm',report['blockers'])
        self.assertFalse(report['executableReviewAvailable']); self.assertFalse(report['authorityGranted'])
        self.o.conserved()

    def test_standalone_planning_refuses_existing_or_partial_owner(self):
        root=Path(self.h['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        with self.assertRaisesRegex(Refusal,'Continuous ownership'): self.o.run_control()
        self.assertEqual(self.o.Proxy.instances,[]); self.assertFalse(Path(self.q['journal']).exists())

    def test_wrong_approval_or_source_drift_cannot_start(self):
        self.start(); preview=api.planning_review(self.registry,self.ledger,self.h)
        with self.assertRaises(Refusal): api.authorize(self.registry,self.ledger,self.h,preview['request'],'f'*64)
        changed=copy.deepcopy(preview['request']); changed['ownerNonce']='f'*64
        with self.assertRaises(Refusal): api.authorize(self.registry,self.ledger,self.h,changed,digest(changed))
        api.stop(self.h,digest(self.h)); self.assertEqual(self.finish()['status'],'unknown')
        self.assertFalse(Path(self.q['journal']).exists()); self.o.conserved()

    def test_stop_never_cancels_or_reloads(self):
        self.start(); api.stop(self.h,digest(self.h)); result=self.finish()
        self.assertEqual(result['status'],'unknown')
        methods=[m for m,_ in self.o.Proxy.instances[-1].calls]
        self.assertNotIn('turn/start',methods); self.assertNotIn('turn/interrupt',methods)
        self.assertNotIn('thread/resume',methods); self.o.conserved()

    def test_closed_owner_cannot_be_adopted_or_confirmed(self):
        self.start(); preview=api.planning_review(self.registry,self.ledger,self.h)
        api.stop(self.h,digest(self.h)); self.finish()
        with self.assertRaises(Refusal): api.authorize(self.registry,self.ledger,self.h,preview['request'],preview['reviewHash'])
        with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,self.file)
        with self.assertRaises((Refusal,OSError)):
            api.serve(self.registry,self.ledger,self.h,digest(self.h),writers_stopped=True,backup_root=self.backup)
        self.assertEqual(len(self.o.Proxy.instances),1); self.o.conserved()

    def test_native_permission_during_planning_is_not_answered(self):
        self.o.receipt=False; self.o.early_permission=True
        self.start(); self.approve(); result=self.finish()
        self.assertEqual(result['status'],'incomplete_unknown')
        self.assertEqual(planning.status(self.q)['nativeOutcome'],'native_permission_or_request_requires_separate_review')
        self.o.conserved()

    def test_unchanged_hold_window_is_not_native_evidence_freshness(self):
        self.start(); r=api.ready(self.h)
        with patch.object(api,'process_identity',return_value=r['processIdentity']),\
                patch('time.time',return_value=r['openedAt']+61):
            with self.assertRaisesRegex(Refusal,'window/phase|closed/stopped'): api.planning_review(self.registry,self.ledger,self.h)
        api.stop(self.h,digest(self.h)); self.finish(); self.o.conserved()
        self.assertFalse(Path(self.q['journal']).exists())
        self.assertNotIn('turn/start',[m for m,_ in self.o.Proxy.instances[-1].calls])

    def test_status_and_preparation_make_no_connection_or_usage_collection(self):
        with patch.object(planning,'Proxy',side_effect=AssertionError('No native read')),\
                patch.object(planning.forward_usage,'collect',side_effect=AssertionError('No telemetry')):
            self.assertEqual(api.prepare(self.registry,self.ledger,self.file,60)['request'],self.h)
            self.assertEqual(api.status(self.h)['status'],'not_submitted')
        self.o.conserved()

    def test_backup_change_wrong_hash_or_missing_quiescence_prevents_claim(self):
        for args in ({'confirmation_hash':'f'*64,'writers_stopped':True,'backup_root':self.backup},
                     {'confirmation_hash':digest(self.h),'writers_stopped':False,'backup_root':self.backup}):
            with self.assertRaises(Refusal): api.serve(self.registry,self.ledger,self.h,**args)
        (self.backup/'review.json').write_text('{}')
        with self.assertRaises(Refusal):
            api.serve(self.registry,self.ledger,self.h,digest(self.h),writers_stopped=True,backup_root=self.backup)
        self.assertFalse(Path(self.h['journal']).exists()); self.o.conserved()

    def test_unloaded_preflight_consumes_owner_without_load_or_planning(self):
        with patch.object(planning.transport.Subscription,'_sample',side_effect=Refusal('Not loaded')):
            result=api.serve(self.registry,self.ledger,self.h,digest(self.h),writers_stopped=True,backup_root=self.backup)
        self.assertEqual(result['status'],'unknown')
        self.assertFalse((Path(self.h['journal'])/'subscription.claim.json').exists())
        self.assertFalse(Path(self.q['journal']).exists())
        with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,self.file)
        self.assertNotIn('thread/resume',[m for m,_ in self.o.Proxy.instances[-1].calls]); self.o.conserved()

    def test_concurrent_open_cannot_adopt_original_connection(self):
        self.start()
        with self.assertRaises((Refusal,OSError)):
            api.serve(self.registry,self.ledger,self.h,digest(self.h),writers_stopped=True,backup_root=self.backup)
        self.approve(); self.assertEqual(self.finish()['status'],'planning_completed')
        self.assertEqual(len(self.o.Proxy.instances),1); self.o.conserved()

    def test_stop_after_native_ack_fences_receipt_without_cancel(self):
        self.o.receipt=False; original=self.o.Proxy._rpc
        def stopped(proxy,method,params):
            reply=original(proxy,method,params)
            if method=='turn/start': api.stop(self.h,digest(self.h))
            return reply
        with patch.object(self.o.Proxy,'_rpc',stopped):
            self.start(); self.approve(); result=self.finish()
        self.assertEqual(result['status'],'incomplete_unknown')
        status=planning.status(self.q); self.assertIsNotNone(status['nativeTurnId'])
        self.assertFalse(status['newReceiptRetained']); self.assertFalse(status['proposalRetained'])
        methods=[m for m,_ in self.o.Proxy.instances[-1].calls]
        self.assertNotIn('turn/interrupt',methods); self.assertNotIn('thread/resume',methods); self.o.conserved()

    def test_one_collection_does_not_gain_freshness_from_a_long_ownership_window(self):
        self.h=api.prepare(self.registry,self.ledger,self.file,1000)['request']
        self.backup=self.f.root/'long-window-backup'; api.backup(self.registry,self.ledger,self.h,self.backup,writers_stopped=True)
        clock=[time.time()]; collect=planning.forward_usage.collect
        def stale(ledger,q):
            value=collect(ledger,q); clock[0]+=121; return value
        with patch('time.time',side_effect=lambda:clock[0]),patch.object(planning.forward_usage,'collect',side_effect=stale) as count:
            self.start(); self.approve(); result=self.finish()
        self.assertEqual(result['status'],'incomplete_unknown'); self.assertEqual(count.call_count,1)
        self.assertTrue((Path(self.q['journal'])/'usage.json').exists())
        self.assertNotIn('turn/start',[m for m,_ in self.o.Proxy.instances[-1].calls]); self.o.conserved()

    def test_collection_failure_closes_original_owner_without_reconnect(self):
        with patch.object(planning.forward_usage,'collect',side_effect=OSError('Interrupted fixture read')):
            self.start(); self.approve(); result=self.finish()
        self.assertEqual(result['status'],'incomplete_unknown'); self.assertEqual(len(self.o.Proxy.instances),1)
        self.assertNotIn('turn/start',[m for m,_ in self.o.Proxy.instances[-1].calls]); self.o.conserved()

    def test_changed_ready_record_cannot_be_renewed_or_used_for_approval(self):
        self.start(); file=Path(self.h['journal'])/'ready.json'; r=planning._read_private(file)
        file.write_text('{}')
        with self.assertRaises((Refusal,OSError)): api.planning_review(self.registry,self.ledger,self.h)
        self.assertEqual(self.finish()['status'],'unknown'); self.assertFalse(Path(self.q['journal']).exists())
        self.o.conserved()

    def test_source_change_during_wait_fences_planning(self):
        self.start()
        with patch.object(api,'source_hash',return_value='f'*64): self.assertEqual(self.finish()['status'],'unknown')
        self.assertFalse(Path(self.q['journal']).exists()); self.o.conserved()

    def test_missing_close_record_status_remains_unknown_and_never_connects(self):
        self.start()
        with patch.object(planning,'Proxy',side_effect=AssertionError('No status connection')):
            self.assertEqual(api.status(self.h)['status'],'claimed_current_connection_unknown')
        api.stop(self.h,digest(self.h)); self.finish(); self.o.conserved()


if __name__=='__main__': unittest.main()
