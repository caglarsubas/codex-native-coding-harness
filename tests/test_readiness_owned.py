"""Disposable forward-only readiness lifecycle; never a live brain or host."""
import copy
import json
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from orchestrator import readiness_owned as owned, standard, standard_preplay as preplay
from orchestrator import public_readiness as public
from orchestrator.app_server_wake import AppServerWake, NATIVE_APPROVAL_POLICY
from orchestrator.assistant_journey import JourneyProposals, catalog
from orchestrator.core import Refusal, digest
from orchestrator.public_pilot_inspection import exclusive
import test_standard_preplay as fixtures
from test_public_readiness import schemas
from test_native_policy_evidence import response, CONTRACT as POLICY
from test_public_native_tasks import CONTRACT
from test_app_server_wake import FakeThread


class ReadinessOwnedTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PreplayTest('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.registry,self.ledger = self.f.registry,self.f.ledger
        # The fixture constructor queues a synthetic legacy request. Start a
        # separate empty fixture before any send; this is never live cleanup.
        with self.ledger.tx() as db: db.execute('DELETE FROM commands')
        self.binding = self.f.binding
        r = self.binding['brains'][self.f.brain]
        r.update(nativeTaskBackend=copy.deepcopy(CONTRACT),policyEvidence=POLICY.copy(),
                 nativePolicy=NATIVE_APPROVAL_POLICY.copy())
        self.binding['endpoint'].update(executable='/fixture/not-executed',sha256='c'*64)
        self.loaded=False; self.lost_ack=False; self.lost_turn=False; self.callback=None; self.calls=[]; self.proxies=[]
        self.terminals=[]; self.policy_bad=False; self.active=False; self.mcp=[]; self.auth=True
        self.latest=None; self.turn=str(uuid.uuid4())
        outer=self
        class Proxy:
            def __init__(self,*_,**__): self.closed=False; self.deadline=0; outer.proxies.append(self)
            def begin_readiness(self,seconds): self._readiness_owned_deadline=time.monotonic()+seconds
            def __enter__(self): return self
            def __exit__(self,*_): self.closed=True
            def call(self,method,params): return self._rpc(method,params)
            def _rpc(self,method,params):
                outer.calls.append((method,copy.deepcopy(params)))
                if outer.callback: outer.callback(method)
                if method=='project/read': return {'project':{'id':r['projectId'],'roots':[{'path':r['cwd']}]}}
                if method=='thread/read': return {'thread':{'id':outer.f.brain,'projectId':r['projectId'],
                    'cwd':r['cwd'],'status':{'type':'active' if outer.active else 'idle' if outer.loaded else 'notLoaded'}}}
                if method=='thread/turns/list': return {'data':[] if outer.latest is None else [outer.latest],'nextCursor':None}
                if method=='thread/effectivePolicy/read':
                    value=response(outer.f.brain,r['cwd']) if outer.loaded else {'version':1,'threadId':outer.f.brain,'policy':None}
                    if outer.policy_bad and outer.loaded: value['policy']['codeModeOffEnforced']=False
                    return value
                if method=='thread/backgroundTerminals/list': return {'data':outer.terminals,'nextCursor':None}
                if method=='account/read': return {'account':{'type':'apiKey'} if outer.auth else None,'requiresOpenaiAuth':True}
                if method=='mcpServerStatus/list': return {'data':outer.mcp,'nextCursor':None}
                if method=='model/list': return {'data':[{'model':'observed-fixture','hidden':False,
                    'supportedReasoningEfforts':[{'reasoningEffort':'high'}]}],'nextCursor':None}
                if method=='thread/resume':
                    outer.loaded=True
                    if outer.lost_ack: raise Refusal('Synthetic lost load acknowledgment')
                    return {'thread':{'id':outer.f.brain,'projectId':r['projectId'],'cwd':r['cwd'],'turns':[]}}
                if method=='turn/start':
                    if outer.lost_turn: raise Refusal('Synthetic uncertain turn start')
                    return {'turn':{'id':outer.turn,'status':'inProgress'}}
                raise AssertionError('Unexpected native operation '+method)
        self.Proxy=Proxy
        self.wake=AppServerWake(self.binding,self.ledger)
        self.f.notifier.app_server=self.wake
        for item in (patch.object(owned,'ReadProxy',Proxy),patch.object(owned,'validate_endpoint'),
                     patch.object(public,'validate_endpoint'),patch.object(public,'export_schemas',return_value=public.schema_contract(schemas())),
                     patch('orchestrator.app_server_wake.WakeProxy',Proxy),patch.object(self.wake,'configured',return_value=True),
                     patch('orchestrator.app_server_wake.validate_endpoint'),patch('orchestrator.app_server_wake.threading.Thread',FakeThread)):
            item.start(); self.addCleanup(item.stop)
        self.runtime=SimpleNamespace(ledger=self.ledger,registry=self.registry,notifier=self.f.notifier)
        self.proposals=JourneyProposals(self.runtime)

    def state(self):
        from orchestrator import missions
        s=self.ledger.snapshot()
        s.update(workspace={'id':'v3','name':'Fixture'},standard=standard.read(self.ledger),mission=missions.read(self.ledger),
                 brainNotification={'publicReadinessSourceAvailable':True})
        return s

    def prepare(self):
        s=self.state(); p=self.proposals.prepare(catalog(s)[owned.WORKFLOW],s,'owner-session')
        self.preview=p; self.cid=p['document']['id']; return p

    def confirm(self,p=None):
        return self.proposals.confirm(self.ledger,{'proposal':p or self.preview,'confirmed':True},'owner-session')

    def review(self,p=None):
        return owned.browser_review((p or self.preview)['document']['request'])

    def deliver(self): return self.f.notifier.notify(self.cid)

    def receipt(self):
        self.f.cid=self.cid; self.f.handoff=preplay.path(self.ledger.root,self.cid,'handoff')
        evidence=preplay.state(self.f.handoff)['publicReadiness']['evidenceHash']
        self.f.publish({'operation':'public_catalog_ack','requestId':self.cid,'evidenceHash':evidence})
        preplay.service(self.ledger,self.binding,self.cid,self.f.brain,self.turn)

    def test_review_never_loads_claims_or_starts_and_has_no_timer_expiry(self):
        before=owned.partial.database_proof(self.ledger.db); p=self.prepare()
        self.assertIsNone(p['document']['expiresAt']); self.assertEqual(p['document']['validity'],'until_scope_changes')
        self.assertEqual(owned.partial.database_proof(self.ledger.db),before); self.assertFalse(owned.claims(self.ledger))
        self.assertFalse(any(m in ('thread/resume','turn/start') for m,_ in self.calls))
        with patch('orchestrator.assistant_journey.time.time',return_value=time.time()+86400):
            self.confirm()
        self.assertFalse(any(m in ('thread/resume','turn/start') for m,_ in self.calls))

    def test_one_request_owns_load_capture_and_receipt_without_inspection_reuse(self):
        inspection=self.ledger.root/'public-preplay-load-consumed.claim'; exclusive(inspection,{'old':'consumed'})
        old=inspection.read_bytes(); self.prepare(); self.confirm(); result=self.deliver()
        self.assertEqual(result['notification']['status'],'accepted')
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1)
        self.assertEqual([m for m,_ in self.calls].count('turn/start'),1)
        self.assertEqual(inspection.read_bytes(),old)
        self.assertFalse(self.proxies[-1].closed,'Original readiness proxy is owned by the existing turn observer')
        params=next(p for m,p in self.calls if m=='thread/resume')
        self.assertEqual(params['approvalPolicy'],'on-request'); self.assertTrue(params['excludeTurns'])
        self.assertEqual(params['config']['features']['code_mode'],{'enabled':False})
        self.assertNotIn('model',params); self.assertNotIn('input',params)
        self.receipt(); current=standard.read(self.ledger)
        self.assertEqual(current['catalogRefresh']['status'],'completed')
        self.assertIsNone(current['run']); self.assertTrue(self.ledger.snapshot()['meta']['paused'])
        command=next(c for c in self.ledger.snapshot()['commands'] if c['id']==self.cid)
        public.retained_catalog(current['catalog'],command,self.binding)
        self.assertTrue(command['notification']['nativePublicReadinessProfile']['nativeLoadMade'])
        self.assertEqual(command['notification']['preplayCatalog']['version'],3)

    def test_loaded_start_observes_without_another_load(self):
        self.loaded=True; self.prepare(); self.confirm(); self.deliver()
        self.assertNotIn('thread/resume',[m for m,_ in self.calls]); self.receipt()
        self.assertEqual(standard.read(self.ledger)['catalogRefresh']['status'],'completed')

    def test_lost_load_ack_is_consumed_and_never_turns_or_reloads(self):
        self.prepare(); self.confirm(); self.lost_ack=True; self.deliver(); self.deliver()
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1)
        self.assertNotIn('turn/start',[m for m,_ in self.calls])
        self.assertTrue(owned.journal(self.ledger,self.cid,'load-claim').exists())
        self.assertFalse(owned.journal(self.ledger,self.cid,'load-ack').exists())
        with self.assertRaises(Refusal): self.prepare()
        with self.assertRaises(Refusal): standard.request_catalog_refresh(self.ledger,{'id':str(uuid.uuid4()),'contextHash':standard.read(self.ledger)['contextHash']})

    def test_duplicate_confirmation_and_delivery_never_rearm(self):
        self.prepare(); first,_=self.confirm(); self.deliver()
        for _ in range(2):
            _,changed=self.confirm(); self.assertFalse(changed); self.deliver()
            standard.request_catalog_refresh(self.ledger,{'id':self.cid,'contextHash':first['result']['payload']['contextHash']})
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1)
        self.assertEqual([m for m,_ in self.calls].count('turn/start'),1)

    def test_scope_source_binding_session_and_native_drift_refuse_before_claim(self):
        self.prepare(); bad=copy.deepcopy(self.preview); changed=self.review(bad); changed['maximumSeconds']=901
        bad['document']['request']['readinessStartJson']=owned.canonical(changed)
        with self.assertRaises(Refusal): self.confirm(bad)
        with self.assertRaises(Refusal): self.proposals.confirm(self.ledger,{'proposal':self.preview,'confirmed':True},'foreign')
        self.active=True
        with self.assertRaises(Refusal): self.confirm()
        self.assertFalse(owned.claims(self.ledger))

    def test_unloaded_is_unknown_and_wrong_current_policy_or_trackers_block(self):
        p=self.prepare(); before=self.review(p)['before']
        self.assertIsNone(before['policy']); self.assertIsNone(before['trackedTerminals'])
        self.confirm(); self.policy_bad=True; self.deliver()
        self.assertNotIn('turn/start',[m for m,_ in self.calls])
        self.assertTrue(owned.journal(self.ledger,self.cid,'load-claim').exists())

    def test_pause_or_stop_after_load_claim_fences_turn_without_reset(self):
        self.prepare(); self.confirm()
        def stop(method):
            if method=='thread/resume':
                with self.ledger.tx() as db:
                    meta=self.ledger.get(db,'meta',1); meta['brainControl']={'desired':'stopped','phase':'checkpointing'}
                    self.ledger.put(db,'meta',1,meta)
        self.callback=stop; self.deliver()
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1)
        self.assertNotIn('turn/start',[m for m,_ in self.calls]); self.assertTrue(owned.claims(self.ledger))

    def test_partial_canonical_claim_is_not_a_new_request_allowance(self):
        self.prepare(); review=self.review()
        exclusive(owned.fence(self.ledger),{'protocol':owned.PROTOCOL,'commandId':self.cid,
            'reviewHash':digest(review),'bindingHash':digest(self.binding),'backup':{}})
        with self.assertRaises(Refusal): self.confirm()
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass
        self.assertFalse(any(m=='thread/resume' for m,_ in self.calls))

    def test_version_two_keeps_its_loaded_only_no_reload_contract(self):
        command=standard.request_catalog_refresh(self.ledger,{'id':str(uuid.uuid4()),'contextHash':standard.read(self.ledger)['contextHash']})
        self.f.notifier.notify(command['id'])
        self.assertFalse(any(m in ('thread/resume','turn/start') for m,_ in self.calls))
        self.assertEqual(self.ledger.snapshot()['commands'][0]['notification']['preplayCatalog']['version'],2)

    def test_missing_auth_or_nonempty_mcp_cannot_prepare(self):
        self.auth=False
        with self.assertRaises(Refusal): self.prepare()
        self.auth=True; self.mcp=[{'foreign':'tool'}]
        with self.assertRaises(Refusal): self.prepare()

    def test_private_backups_preserve_exact_rows_and_original_sidecars(self):
        file=self.ledger.root/'old-immutable.claim'; exclusive(file,{'usageGap':'unknown','tokens':1049625})
        self.prepare(); self.confirm()
        claim=owned.record(owned.fence(self.ledger)); archive=owned.record(claim['backup']['path'],1000000)
        self.assertEqual(archive['reviewHash'],digest(self.review()))
        self.assertEqual(len(archive['files']),3)
        for p in archive['files'].values(): self.assertEqual(Path(p['path']).stat().st_mode&0o777,0o600)
        self.assertEqual(owned.record(file),{'usageGap':'unknown','tokens':1049625})

    def test_uncertain_turn_start_keeps_load_and_send_claims_without_another_turn(self):
        self.prepare(); self.confirm(); self.lost_turn=True; self.deliver(); self.deliver()
        command=self.ledger.snapshot()['commands'][0]
        self.assertEqual(command['notification']['status'],'uncertain')
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1)
        self.assertEqual([m for m,_ in self.calls].count('turn/start'),1)
        self.assertTrue(owned.journal(self.ledger,self.cid,'close').exists())

    def test_stop_during_capability_capture_fences_turn_on_same_connection(self):
        self.prepare(); self.confirm()
        def stop(method):
            if method=='model/list':
                with self.ledger.tx() as db:
                    meta=self.ledger.get(db,'meta',1); meta['brainControl']={'desired':'stopped'}
                    self.ledger.put(db,'meta',1,meta)
        self.callback=stop; self.deliver()
        self.assertNotIn('turn/start',[m for m,_ in self.calls])
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1)

    def test_backup_corruption_and_original_claim_drift_fence_before_load(self):
        old=self.ledger.root/'inspection-existing.claim'; exclusive(old,{'consumed':True})
        self.prepare(); self.confirm()
        manifest=owned.record(owned.record(owned.fence(self.ledger))['backup']['path'],1000000)
        Path(manifest['files']['ledger']['path']).write_bytes(b'corrupt disposable backup')
        self.deliver()
        self.assertNotIn('thread/resume',[m for m,_ in self.calls])
        self.assertTrue(owned.claims(self.ledger))

    def test_other_project_binding_and_source_change_invalidate_review(self):
        self.prepare(); original=copy.deepcopy(self.binding)
        self.binding['brains'][self.f.brain]['projectId']=str(uuid.uuid4())
        with self.assertRaises(Refusal): self.confirm()
        self.binding.clear(); self.binding.update(original)
        with patch.object(preplay,'source_hash',return_value='0'*64):
            with self.assertRaises(Refusal): self.confirm()
        self.assertFalse(owned.claims(self.ledger))

    def test_failed_status_alone_cannot_dispose_unknown_historical_delivery(self):
        with self.ledger.tx() as db:
            c=copy.deepcopy(self.f.command); c['status']='failed'; self.ledger.put(db,'commands',c['id'],c)
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(owned.claims(self.ledger))

    def test_harness_repository_cannot_use_readiness_owned_loading(self):
        with self.ledger.tx() as db:
            r=self.ledger.get(db,'repos','a'); r['policyProfile']='harness'; self.ledger.put(db,'repos','a',r)
        with self.assertRaises((Refusal,KeyError)): self.prepare()

    def test_missing_original_load_ack_cannot_be_reconstructed_from_catalog_proof(self):
        self.prepare(); self.confirm(); self.deliver()
        c=self.ledger.snapshot()['commands'][0]
        owned.journal(self.ledger,self.cid,'load-ack').unlink()
        with self.assertRaises(OSError): owned.catalog_proof(c)

    def test_real_original_catalog_error_receipt_is_preserved_not_replayed(self):
        # Complete the fixture's original v1 request through its original
        # mailbox, not an owner-authored status or receipt backfill.
        old = self.f.command
        self.binding['brains'][self.f.brain].pop('nativeTaskBackend')
        with self.ledger.tx() as db: self.ledger.put(db,'commands',old['id'],old)
        self.f.notifier.app_server=SimpleNamespace(binding=self.binding,send=self.f.send)
        self.f.deliver()
        self.f.publish({'operation':'catalog_error','requestId':old['id'],
            'code':'native_schema_unavailable','detail':'Not exposed by this fixture','retryable':False})
        self.f.service()
        with self.ledger.tx() as db:
            c=self.ledger.get(db,'commands',old['id'])
            c['notification'].update(nativeTurnStatus='completed',nativeThreadObservation={'streamStatus':'closed'})
            self.ledger.put(db,'commands',old['id'],c)
        original=self.ledger.snapshot()['commands'][0]
        self.binding['brains'][self.f.brain]['nativeTaskBackend']=copy.deepcopy(CONTRACT)
        self.f.notifier.app_server=self.wake
        self.prepare(); self.confirm(); self.deliver(); self.receipt()
        self.assertEqual(next(c for c in self.ledger.snapshot()['commands'] if c['id']==old['id']),original)
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1)

    def test_completed_foreign_turn_during_capture_cannot_be_ignored(self):
        self.prepare(); self.confirm()
        def drift(method):
            if method=='model/list': self.latest={'id':str(uuid.uuid4()),'status':'completed'}
        self.callback=drift; self.deliver()
        self.assertNotIn('turn/start',[m for m,_ in self.calls])
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1)

    def test_original_canonical_claim_and_handoff_are_required_for_catalog_proof(self):
        self.prepare(); self.confirm(); self.deliver()
        c=self.ledger.snapshot()['commands'][0]
        claim=owned.record(owned.fence(self.ledger)); claim['bindingHash']='0'*64
        owned.fence(self.ledger).write_text(__import__('json').dumps(claim))
        with self.assertRaises(Refusal): owned.catalog_proof(c)

    @staticmethod
    def browser_roundtrip(value):
        result=subprocess.run(['node','-e',
            'let s="";process.stdin.on("data",d=>s+=d);process.stdin.on("end",()=>process.stdout.write(JSON.stringify(JSON.parse(s))));'],
            input=json.dumps(value),text=True,capture_output=True,check=True,timeout=10)
        return json.loads(result.stdout)

    def test_real_javascript_roundtrip_preserves_exact_nanosecond_pins_and_receipt(self):
        old=self.ledger.root/'public-preplay-load-consumed.claim'
        exclusive(old,{'old':'consumed','usageGap':'unknown'})
        os.utime(old,ns=(1792000000000000001,1792000000000000001))
        original=old.read_bytes(); proposal=self.prepare(); review=self.review()
        pin=review['local']['sidecars'][old.name]
        self.assertIn(1792000000000000001,pin['identity'])
        rounded=self.browser_roundtrip(review)
        self.assertNotEqual(rounded['local']['sidecars'][old.name],pin,'Fixture must reproduce the old unsafe-number boundary')
        wire=self.browser_roundtrip(proposal)
        self.assertEqual(wire,proposal)
        self.assertEqual(self.review(wire),review)
        self.confirm(wire); self.deliver(); self.receipt()
        command=self.ledger.snapshot()['commands'][0]
        self.assertEqual(command['payload']['readinessStart'],review)
        self.assertEqual(command['payload']['readinessStart']['local']['sidecars'][old.name],pin)
        self.assertEqual(old.read_bytes(),original)
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1)
        self.assertEqual([m for m,_ in self.calls].count('turn/start'),1)
        self.assertIsNone(standard.read(self.ledger)['run'])

    def test_browser_wire_rejects_unencoded_noncanonical_and_malformed_reviews(self):
        self.prepare(); request=self.preview['document']['request']; review=self.review()
        cases=[{'id':self.cid,'contextHash':review['contextHash'],'readinessStart':review},
               {**request,'readinessStartJson':' '+request['readinessStartJson']},
               {**request,'readinessStartJson':'[]'},
               {**request,'readinessStartJson':request['readinessStartJson'].replace('"version":1','"version":1,"version":1',1)},
               {**request,'readinessStartJson':request['readinessStartJson'].replace('"maximumSeconds":900','"maximumSeconds":NaN',1)},
               {**request,'readinessStartJson':'x'*30001},
               {**request,'unexpected':'ignored?'}]
        for value in cases:
            with self.subTest(value=str(value)[:100]), self.assertRaises(Refusal): owned.browser_review(value)
        self.assertFalse(owned.claims(self.ledger))
        self.assertFalse(any(m in ('thread/resume','turn/start') for m,_ in self.calls))

    def test_canonical_browser_review_must_match_outer_command_and_context(self):
        self.prepare(); request=self.preview['document']['request']
        for key,value in (('id',str(uuid.uuid4())),('contextHash','0'*64)):
            with self.subTest(key=key), self.assertRaises(Refusal): owned.browser_review({**request,key:value})
        self.assertFalse(owned.claims(self.ledger))

    def test_resigned_rounded_pin_still_fails_scope_validation_before_claim(self):
        old=self.ledger.root/'old-inspection.claim'; exclusive(old,{'consumed':True})
        os.utime(old,ns=(1792000000000000001,1792000000000000001))
        self.prepare(); bad=copy.deepcopy(self.preview); rounded=self.browser_roundtrip(self.review())
        bad['document']['request']=owned.browser_request(rounded)
        bad['signature']=self.proposals.sign(bad['document'])
        with self.assertRaises(Refusal): self.confirm(bad)
        self.assertFalse(owned.claims(self.ledger))
        self.assertEqual(self.ledger.snapshot()['commands'],[])

    def test_unicode_claim_name_and_large_epoch_survive_browser_encoding(self):
        old=self.ledger.root/'inspection-\u00e9-\u6d4b\u8bd5.claim'; exclusive(old,{'consumed':True})
        self.prepare(); review=self.review(); wire=self.browser_roundtrip(self.preview)
        self.assertEqual(self.review(wire),review)
        self.confirm(wire)
        self.assertEqual(self.ledger.snapshot()['commands'][0]['payload']['readinessStart'],review)

    def test_browser_roundtrip_keeps_foreign_session_and_tampering_refused(self):
        self.prepare(); wire=self.browser_roundtrip(self.preview)
        with self.assertRaises(Refusal):
            self.proposals.confirm(self.ledger,{'proposal':wire,'confirmed':True},'other-browser')
        changed=self.review(wire); changed['before']['latestTurn']={'id':'foreign','status':'completed'}
        wire['document']['request']=owned.browser_request(changed)
        with self.assertRaises(Refusal): self.confirm(wire)
        self.assertFalse(owned.claims(self.ledger))
