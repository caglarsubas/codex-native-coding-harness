"""Finite synthetic lineage; no live host, model, telemetry or credential read."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from orchestrator import handoff_reconciliation as api, host_transfer_handoff as handoff
from orchestrator.app_server_wake import NativeConnectionLost
from orchestrator.core import Refusal, digest
from orchestrator.host_lifecycle import write_record
import test_host_transfer_handoff as fixtures


class ReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.HostTransferTest('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        original=self.f.Destination._line
        def lost(proxy):
            original(proxy)  # Retain both actual fixture mailbox replies first.
            raise NativeConnectionLost('heartbeat_missing')
        with patch.object(self.f.Destination,'_line',lost):
            self.assertEqual(self.f.apply()['status'],'incomplete_unknown')
        self.q=self.f.q; self.registry=self.f.registry; self.ledger=self.f.ledger
        self.root=Path(self.q['journal']); self.owner=handoff.phase.owner_root(self.q)
        self.turn=handoff.read(self.root/'native-ack.json')['turnId']
        self.target=Path(handoff.read(self.owner/'transfer.json')['destinationPath'])
        with self.target.open('a') as stream:
            for kind in ('task_started','task_complete'):
                stream.write(json.dumps({'type':'event_msg','payload':{'type':kind,'turn_id':self.turn}})+'\n')
        self.old_inventory=handoff.phase.consumer_inventory(self.q)
        self.old_owner=handoff.phase.lifecycle.inventory(self.owner)
        self.before=handoff.planning.original_context(self.registry,self.ledger,self.q['original']['bindingFile'],
            self.q['original']['command']['id'],disposed=True)
        self.file=self.f.directory/'request.json'; self.out=self.f.f.root/'completion-evidence'
        self.calls=[]; self.activity='notLoaded'; self.completed=True; self.foreign=False; self.unstable=False
        self.auth=True; self.samples=0
        owner=self
        class Probe:
            def __init__(self,q): self.initialization={'codexHome':str(owner.f.home)}
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def _rpc(self,method,params):
                owner.calls.append((method,copy.deepcopy(params)))
                if method=='account/read':
                    owner.assertEqual(params,{'refreshToken':False})
                    return {'requiresOpenaiAuth':True,'account':{'type':'chatgpt','planType':'pro'} if owner.auth else None}
                if method=='project/read':
                    value=copy.deepcopy(owner.f.project)
                    if owner.foreign: value['roots']=[{'path':'/foreign'}]
                    return {'project':value}
                if method=='thread/read':
                    owner.samples+=1
                    row=copy.deepcopy(owner.f.thread)
                    row.update(path=str(owner.target),status={'type':owner.activity})
                    row['turns'].append({'id':owner.turn,'status':'completed' if owner.completed else 'inProgress','items':[]})
                    if owner.unstable and owner.samples>1: row['status']={'type':'idle'}
                    return {'thread':row}
                if method=='thread/turns/list':
                    return {'data':[{'id':owner.turn,'status':'completed' if owner.completed else 'inProgress'}],'nextCursor':None}
                raise AssertionError('No write, load, subscription, discovery or other read allowed')
        self.probe=patch.object(api,'Probe',Probe); self.probe.start(); self.addCleanup(self.probe.stop)

    def collect(self): return api.collect(self.registry,self.ledger,self.file,self.out)
    def conserved(self):
        self.assertEqual(handoff.phase.consumer_inventory(self.q),self.old_inventory)
        self.assertEqual(handoff.phase.lifecycle.inventory(self.owner),self.old_owner)
        self.assertEqual(handoff.planning.original_context(self.registry,self.ledger,self.q['original']['bindingFile'],
            self.q['original']['command']['id'],disposed=True),self.before)
        self.assertEqual(handoff.status(self.q)['status'],'incomplete_unknown'); self.f.conserved()

    def test_unloaded_completed_turn_is_evidence_without_reload_or_safety_inference(self):
        value=self.collect(); self.assertEqual(value['status'],'preparation_completion_observed',value)
        self.assertEqual(value,api.status(self.registry,self.ledger,self.out))
        self.assertEqual(value['native']['nativeStatus'],{'type':'notLoaded'})
        self.assertEqual(value['native']['currentTrackedTerminals'],'unknown_not_collected')
        self.assertEqual(value['boundary'],api.BOUNDARY); self.conserved()
        self.assertEqual(set(m for m,_ in self.calls),{'account/read','project/read','thread/read','thread/turns/list'})

    def test_later_binding_review_is_conditional_not_binding_installation(self):
        self.collect(); before=list(self.calls)
        value=api.binding_review(self.registry,self.ledger,self.out)
        self.assertTrue(value['prerequisiteSatisfied']); self.assertFalse(value['installsBinding'])
        self.assertEqual(value['request']['requiredOriginalOutcome'],'incomplete_unknown')
        self.assertNotEqual(value['reviewHash'],handoff.binding_review(self.q)['reviewHash'])
        self.assertFalse(handoff.binding_review(self.q)['prerequisiteSatisfied'])
        self.assertEqual(self.calls,before); self.conserved()

    def test_status_never_collects_reconnects_or_renews_observation(self):
        value=self.collect(); calls=list(self.calls)
        for _ in range(2): self.assertEqual(api.status(self.registry,self.ledger,self.out),value)
        self.assertEqual(self.calls,calls); self.conserved()

    def test_interrupted_or_active_turn_remains_unknown(self):
        self.completed=False
        self.assertEqual(self.collect()['status'],'unknown')
        with self.assertRaises(Refusal): api.binding_review(self.registry,self.ledger,self.out)
        self.conserved()

    def test_active_thread_or_permission_status_is_never_loaded_or_cancelled(self):
        self.activity='active'
        self.assertEqual(self.collect()['status'],'unknown'); self.conserved()

    def test_foreign_native_identity_remains_unknown(self):
        self.foreign=True
        self.assertEqual(self.collect()['status'],'unknown'); self.conserved()

    def test_changing_repeated_metadata_remains_unknown(self):
        self.unstable=True
        self.assertEqual(self.collect()['status'],'unknown'); self.conserved()

    def test_authentication_gap_does_not_login_or_refresh(self):
        self.auth=False
        self.assertEqual(self.collect()['status'],'unknown'); self.conserved()

    def test_native_completion_without_correlated_persisted_boundary_is_unknown(self):
        self.target.write_bytes(self.target.read_bytes().replace(b'task_complete',b'opaque_boundary'))
        self.assertEqual(self.collect()['status'],'unknown'); self.conserved()

    def test_changed_original_history_prefix_is_unknown(self):
        self.target.write_bytes(self.target.read_bytes().replace(b'session_meta',b'changed_meta'))
        self.assertEqual(self.collect()['status'],'unknown'); self.conserved()

    def test_missing_original_receipt_is_not_reconstructed(self):
        (self.root/'receive.json').unlink()
        with self.assertRaises((Refusal,OSError)): self.collect()
        self.assertEqual(self.calls,[]); self.assertFalse(self.out.exists())

    def test_changed_claim_fails_before_any_connection(self):
        (self.owner/'assign.claim.json').write_text('{}')
        with self.assertRaises(Refusal): self.collect()
        self.assertEqual(self.calls,[])

    def test_unknown_original_stage_cannot_become_a_transfer_retry(self):
        (self.root/'failure.json').write_text('{}')
        with self.assertRaises(Refusal): self.collect()
        self.assertEqual(self.calls,[])

    def test_existing_evidence_directory_is_never_overwritten(self):
        self.collect(); calls=list(self.calls)
        with self.assertRaises(Refusal): self.collect()
        self.assertEqual(self.calls,calls); self.conserved()

    def test_native_homes_and_old_journals_cannot_be_evidence_destinations(self):
        for path in (self.f.home/'evidence',self.root/'evidence',self.f.f.repo/'evidence'):
            self.out=path
            with self.assertRaises(Refusal): self.collect()
        self.assertEqual(self.calls,[]); self.conserved()

    def test_unknown_historical_source_cannot_be_executed_or_substituted(self):
        q=copy.deepcopy(self.q); q['sourceHash']='0'*64
        with self.assertRaises(Refusal): api.qualified_source(q,self.f.f.root)
        q['sourceHash']=api.PR181_SOURCE
        with self.assertRaises(Refusal): api.qualified_source(q,None)
        with patch.object(handoff.phase.lifecycle,'source_proof',return_value={'sourceHash':'1'*64}):
            with self.assertRaises(Refusal): api.qualified_source(q,self.f.f.root)

    def test_partial_or_extra_evidence_files_are_not_accepted(self):
        self.collect(); write_record(self.out/'extra.json',{'unlisted':True})
        with self.assertRaises(Refusal): api.status(self.registry,self.ledger,self.out)
        self.conserved()

    def test_changed_observation_cannot_claim_terminal_safety(self):
        value=self.collect(); value['boundary']['currentTerminalSafety']='safe'
        (self.out/'evidence.json').write_text(json.dumps(value))
        with self.assertRaises(Refusal): api.status(self.registry,self.ledger,self.out)
        self.conserved()

    def test_probe_has_a_closed_exact_target_read_allowlist(self):
        self.probe.stop()
        probe=api.Probe(self.q)
        for method,params in [('thread/resume',{'threadId':self.f.f.brain}),('thread/subscribe',{}),
            ('turn/start',{}),('thread/read',{'threadId':'foreign','includeTurns':True}),
            ('account/read',{'refreshToken':True}),('turn/interrupt',{}),('project/list',{})]:
            with self.subTest(method=method),self.assertRaises(Refusal): probe._rpc(method,params)


if __name__=='__main__': unittest.main()
