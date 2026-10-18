"""Same project, distinct successor, immutable predecessor and unknown safety."""
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
import threading
from unittest.mock import patch

from orchestrator import same_project_lifecycle as api, canceled_continuation as planning, connection_handoff
from orchestrator.core import Refusal, digest
from orchestrator.host_lifecycle import write_record
import test_forward_usage as fixtures


class SameProjectLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.usage=fixtures.ForwardUsageTest('runTest'); self.usage.setUp(); self.addCleanup(self.usage.doCleanups)
        self.o=self.usage.o; self.f=self.o.f; self.registry,self.ledger=self.o.registry,self.o.ledger
        self.parent=copy.deepcopy(self.o.q)
        with patch.object(planning.transport.Subscription,'_sample',side_effect=Refusal(api.REFUSAL)):
            result=self.o.run_control()
        self.assertEqual(result['status'],'incomplete_unknown')
        self.parent_file=self.f.root/'parent.json'; write_record(self.parent_file,self.parent)
        self.parent_pins={**api.inventory(self.parent['journal']),**api.inventory(self.parent['mailbox'])}
        self.q=api.prepare(self.registry,self.ledger,self.parent_file)['request']
        self.backup=self.f.root/'successor-backup'
        planning.backup(self.registry,self.ledger,self.q,self.backup,writers_stopped=True)
        self.o.q=self.q; self.o.Proxy.instances.clear()
        base=self.o.Proxy
        class Proxy(base):
            def __init__(self,endpoint):
                super().__init__(endpoint); self.process=SimpleNamespace(poll=lambda:None)
        p=patch.object(planning,'Proxy',Proxy); p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda:[w.join(2) for w in self.o.workers])

    def confirm(self,**kwargs):
        return api.confirm(self.registry,self.ledger,self.q,digest(self.q),writers_stopped=True,backup_root=self.backup,**kwargs)

    def conserved(self):
        self.o.conserved()
        self.assertEqual(self.parent_pins,{**api.inventory(self.parent['journal']),**api.inventory(self.parent['mailbox'])})
        self.assertEqual(planning.status(self.parent)['status'],'incomplete_unknown')

    def test_combined_review_same_project_one_connection_subscription_collection_and_new_turn(self):
        with patch.object(planning.forward_usage,'collect',wraps=planning.forward_usage.collect) as collect:
            value=self.confirm(); self.assertEqual(collect.call_count,1)
        self.assertEqual(value['status'],'planning_completed',value)
        self.assertEqual(api.status(self.registry,self.q),value)
        self.assertEqual(len(self.o.Proxy.instances),1)
        methods=[m for m,_ in self.o.Proxy.instances[0].calls]
        self.assertEqual(methods.count('thread/subscribe'),1); self.assertEqual(methods.count('turn/start'),1)
        for name in ('thread/resume','thread/start','turn/interrupt'): self.assertNotIn(name,methods)
        self.assertTrue(value['connectionClosed']); self.assertFalse(value['boundary']['newProjectCreated'])
        self.assertEqual(value['boundary']['predecessorOutcome'],'unknown_preserved'); self.conserved()

    def test_preparation_backup_and_status_do_not_connect_collect_or_claim(self):
        with patch.object(planning,'Proxy',side_effect=AssertionError('No native RPC')),\
             patch.object(planning.forward_usage,'collect',side_effect=AssertionError('No collection')):
            self.assertEqual(api.prepare(self.registry,self.ledger,self.parent_file)['request'],self.q)
            self.assertEqual(api.status(self.registry,self.q)['status'],'not_submitted')
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_wrong_approval_backup_and_quiescence_never_claim(self):
        with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,self.q,'f'*64,writers_stopped=True,backup_root=self.backup)
        with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,self.q,digest(self.q),backup_root=self.backup)
        (self.backup/'manifest.json').write_text('{}')
        with self.assertRaises(Refusal): self.confirm()
        self.assertFalse(connection_handoff.location(self.registry,self.q).exists()); self.conserved()

    def test_unloaded_current_brain_has_no_collection_turn_or_reload(self):
        with patch.object(planning.transport.Subscription,'_sample',side_effect=Refusal(api.REFUSAL)),\
             patch.object(planning.forward_usage,'collect',side_effect=AssertionError('No collection before ownership')):
            value=self.confirm()
        self.assertEqual(value['status'],'blocked_or_unknown'); self.assertTrue(value['connectionClosed'])
        self.assertFalse(Path(self.q['journal']).exists())
        methods=[m for m,_ in self.o.Proxy.instances[0].calls]
        self.assertNotIn('turn/start',methods); self.assertNotIn('thread/resume',methods)
        with self.assertRaises((Refusal,OSError)): self.confirm()
        self.conserved()

    def test_ambiguous_lost_start_ack_cannot_be_retried_or_chained(self):
        self.o.fail_start=True; value=self.confirm(); self.assertEqual(value['status'],'incomplete_unknown')
        with self.assertRaises((Refusal,OSError)): self.confirm()
        with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,self.parent_file)
        file=self.f.root/'child.json'; write_record(file,self.q)
        with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,file)
        self.assertEqual(len(self.o.Proxy.instances),1); self.conserved()

    def test_standalone_or_old_continuous_fallback_is_forbidden(self):
        with self.assertRaises(Refusal): planning.confirm(self.registry,self.ledger,self.q,digest(self.q),writers_stopped=True,backup_root=self.backup)
        file=self.f.root/'child.json'; write_record(file,self.q)
        with self.assertRaises(Refusal): connection_handoff.prepare(self.registry,self.ledger,file)
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_partial_unknown_or_additional_predecessor_records_fence_successor(self):
        root=Path(self.parent['journal']); extra=root/'turn-start.claim.json'; write_record(extra,{'unknown':True})
        with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,self.parent_file)
        with self.assertRaises(Refusal): self.confirm()
        self.assertFalse(Path(self.q['journal']).exists())

    def test_lifecycle_closed_positive_record_is_required_not_missing_markers(self):
        file=Path(self.parent['journal'])/'lifecycle.json'; file.unlink()  # Disposable corrupt fixture only.
        with self.assertRaises((Refusal,OSError)): api.prepare(self.registry,self.ledger,self.parent_file)
        self.assertFalse(connection_handoff.location(self.registry,self.q).exists())

    def test_old_failure_text_is_not_an_arbitrary_cleanup_attestation(self):
        file=Path(self.parent['journal'])/'failure.json'; row=planning._read_private(file)
        row['detail']='Everything safe; no native work'; file.write_text(__import__('json').dumps(row))
        with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,self.parent_file)

    def test_original_binding_and_ceiling_cannot_change(self):
        for key,value in (('maxTokens',2),('candidatePin',{}),('original',{})):
            q=copy.deepcopy(self.q); q[key]=value
            with self.subTest(key=key),self.assertRaises((Refusal,KeyError)):
                planning.current(self.registry,self.ledger,q)
        self.conserved()

    def test_permission_is_not_answered_or_canceled(self):
        self.o.receipt=False; self.o.early_permission=True
        value=self.confirm(); self.assertEqual(value['status'],'incomplete_unknown')
        self.assertEqual(planning.status(self.q)['nativeOutcome'],'native_permission_or_request_requires_separate_review')
        methods=[m for m,_ in self.o.Proxy.instances[0].calls]
        for name in ('turn/interrupt','approval/respond','thread/resume'): self.assertNotIn(name,methods)
        self.conserved()

    def test_stop_at_subscription_boundary_never_subscribes_or_collects(self):
        original=planning.transport.Subscription.attach
        def stopped(sub,claim):
            api.stop(self.registry,self.q,digest(self.q)); return original(sub,claim)
        with patch.object(planning.transport.Subscription,'attach',stopped): value=self.confirm()
        self.assertEqual(value['status'],'blocked_or_unknown')
        methods=[m for m,_ in self.o.Proxy.instances[0].calls]
        self.assertNotIn('thread/subscribe',methods); self.assertNotIn('turn/start',methods); self.conserved()

    def test_prior_collected_usage_is_a_monotone_floor_not_a_refund(self):
        original=planning.forward_usage.collect
        def regressed(ledger,q):
            value=original(ledger,q)
            # Force a predecessor's higher actual observed floor without editing
            # live history. The original q baseline alone would pass this check.
            parent_usage=planning._read_private(Path(self.parent['journal'])/'usage.json')
            parent_usage['report']['records'][0]['calls']+=1
            with patch.object(planning.forward_usage,'retained',side_effect=lambda r,p,**kw:
                parent_usage if r['version']==2 else value):
                with self.assertRaises(Refusal): api.check_usage(q,planning.pin(Path(q['journal'])/'usage.json'),fresh=True)
            return value
        with patch.object(planning.forward_usage,'collect',regressed):
            self.assertEqual(self.confirm()['status'],'planning_completed')
        self.conserved()

    def test_phase_expiry_and_stale_usage_are_not_relaxed(self):
        with patch('time.time',return_value=self.q['original']['run']['expiresAt']+1),self.assertRaises(Refusal): self.confirm()
        self.assertFalse(connection_handoff.location(self.registry,self.q).exists()); self.conserved()

    def test_changed_retained_parent_fails_file_only_status(self):
        self.confirm(); file=Path(self.parent['mailbox'])/'handoff.json'; file.write_text('{}')
        with patch.object(planning,'Proxy',side_effect=AssertionError('No reconnect')),self.assertRaises(Refusal): api.status(self.registry,self.q)

    def test_diagnostic_loaded_is_non_authorizing_without_subscription_or_collection(self):
        with patch.object(api,'InspectionProxy',planning.Proxy),\
             patch.object(planning.forward_usage,'collect',side_effect=AssertionError('No diagnostic usage')):
            value=api.inspect(self.registry,self.ledger,self.q)
        self.assertEqual(value['nativeStatus'],{'type':'idle'}); self.assertEqual(value['blockers'],[])
        self.assertFalse(value['executionAuthorized']); self.assertFalse(value['subscriptionAttached'])
        methods=[m for m,_ in self.o.Proxy.instances[0].calls]
        for name in ('thread/subscribe','thread/resume','turn/start'): self.assertNotIn(name,methods)
        self.assertFalse(connection_handoff.location(self.registry,self.q).exists()); self.conserved()

    def test_diagnostic_unloaded_retains_unknown_policy_and_terminals_no_claim(self):
        base=planning.Proxy
        class Cold(base):
            def __init__(self,endpoint):
                super().__init__(endpoint); self.thread['status']={'type':'notLoaded'}
        with patch.object(api,'InspectionProxy',Cold): value=api.inspect(self.registry,self.ledger,self.q)
        self.assertEqual(value['blockers'],['brain_not_loaded_no_reload_authorized'])
        self.assertEqual(value['policy'],'unknown'); self.assertEqual(value['trackedTerminals'],'unknown')
        self.assertFalse(connection_handoff.location(self.registry,self.q).exists()); self.conserved()

    def test_diagnostic_rpc_allowlist_rejects_native_effects(self):
        proxy=object.__new__(api.InspectionProxy)
        for name in ('thread/subscribe','thread/resume','turn/start','turn/interrupt','account/login/start'):
            with self.subTest(method=name),self.assertRaises(Refusal): proxy._rpc(name,{})

    def test_stop_after_start_ack_never_answers_cancels_or_receipts(self):
        original=planning.Proxy._rpc
        def stopped(proxy,method,params):
            value=original(proxy,method,params)
            if method=='turn/start': api.stop(self.registry,self.q,digest(self.q))
            return value
        with patch.object(planning.Proxy,'_rpc',stopped): value=self.confirm()
        self.assertEqual(value['status'],'incomplete_unknown')
        self.assertFalse(planning.status(self.q)['newReceiptRetained'])
        methods=[m for m,_ in self.o.Proxy.instances[0].calls]
        self.assertNotIn('turn/interrupt',methods); self.conserved()

    def test_concurrent_confirmations_have_one_new_owner_and_turn(self):
        results=[]; failures=[]
        def run():
            try: results.append(self.confirm())
            except (Refusal,OSError) as error: failures.append(type(error).__name__)
        workers=[threading.Thread(target=run) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(10); self.assertFalse(worker.is_alive())
        self.assertEqual(len(results),1); self.assertEqual(len(failures),1)
        self.assertEqual(results[0]['status'],'planning_completed')
        self.assertEqual(len(self.o.Proxy.instances),1); self.conserved()

    def test_stale_new_usage_consumes_once_and_never_starts_turn(self):
        clock=[__import__('time').time()]; original=planning.forward_usage.collect
        def stale(ledger,q):
            value=original(ledger,q); clock[0]+=121; return value
        with patch('time.time',side_effect=lambda:clock[0]),\
             patch.object(planning.forward_usage,'collect',side_effect=stale) as collect:
            value=self.confirm(); self.assertEqual(collect.call_count,1)
        self.assertEqual(value['status'],'incomplete_unknown')
        self.assertNotIn('turn/start',[m for m,_ in self.o.Proxy.instances[0].calls]); self.conserved()


if __name__=='__main__': unittest.main()
