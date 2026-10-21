"""Actual disposable admission plus synthetic native readiness, never live state."""
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from orchestrator import historical_admission as history, missions, readiness_owned as owned, standard
from orchestrator import worker_phase_admission as admission, worker_admission_source as continuity
from orchestrator.assistant_journey import JourneyProposals, catalog
from orchestrator.app_server_wake import AppServerWake
from orchestrator.core import Ledger, Refusal, canonical, digest
from orchestrator.notification import BrainNotifier
from orchestrator.same_project_lifecycle import source_proof
import test_historical_admission as lineage
import test_readiness_owned as readiness
from test_public_native_tasks import CONTRACT


class AdmittedReadinessTest(unittest.TestCase):
    def setUp(self):
        self.h=lineage.HistoricalAdmissionTest('runTest'); self.addCleanup(self.h.doCleanups)
        with patch.object(lineage.SetupFixture,'checkout_local',True,create=True): self.h.setUp()
        self.registry,self.target=self.h.registry,self.h.target
        if getattr(self,'historical_source',False):
            # A completed admission genuinely crosses an implementation epoch;
            # the inert frozen Python is only hashed, never imported/executed.
            self.frozen=self.h.u.f.f.f.root/'inert-original-readiness-source'
            directory=self.frozen/'orchestrator'; directory.mkdir(parents=True,mode=0o700)
            inert=directory/'fixture.py'; inert.write_text("raise AssertionError('Never execute historical source')\n"); inert.chmod(0o600)
            original_source=admission.source_hash
            self.epoch=source_proof(self.frozen)['sourceHash']
            original_context=history.context
            def historical_context(*args,**kwargs):
                context,result,q=original_context(*args,**kwargs); context['sourceHash']=self.epoch
                return context,result,q
            for p in (patch.object(history,'PR185_SOURCE',self.epoch),
                      patch.object(history,'context',side_effect=historical_context),
                      patch.object(admission,'source_hash',side_effect=lambda:self.epoch)):
                p.start(); self.addCleanup(p.stop)
        self.h.qualify()
        state=missions.read(self.target)
        missions.change(self.target,{'id':'review-admitted-readiness-fixture','operation':'review',
            'expectedRevision':state['revision'],'documentHash':state['documentHash'],'confirmed':True})
        binding=admission.successor._read_binding(self.h.binding)
        binding['brains'][self.h.s.brain]['nativeTaskBackend']=copy.deepcopy(CONTRACT)
        # Schema export is mocked by ReadinessOwnedTest; still pin a complete
        # executable field before this disposable admission is reviewed.
        binding['endpoint']['executable']='/fixture/not-executed'
        self.h.s.write(self.h.binding,binding)
        preview=self.h.prepare()
        admission.backup(self.registry,self.h.source,preview['request'],self.h.backup,writers_stopped=True)
        self.receipt=admission.confirm(self.registry,self.h.source,preview['request'],preview['reviewHash'],
            writers_stopped=True,backup_root=self.h.backup)
        if getattr(self,'historical_source',False):
            self.epoch=original_source()
            continuity.qualify(self.registry,self.target,self.frozen,writers_stopped=True)
            path=self.target.root/continuity.FILE
            os.utime(path,ns=(1792000000000000001,1792000000000000001))
            self.original_continuity_bytes=path.read_bytes()
            self.original_continuity_pin=admission.successor.pin(path)
        self.original_marker=(self.target.root/admission.successor.FENCE).read_bytes()
        self.original_source_claim=admission.successor.source_claim(self.registry.root,self.h.source.workspace_id).read_bytes()
        self.r=readiness.ReadinessOwnedTest('runTest'); self.r.setUp(); self.addCleanup(self.r.doCleanups)
        # Reuse only the labelled fake native server. The ledger/admission and
        # registry above are real, separately created disposable SQLite/Git.
        old_brain=self.r.f.brain; native_record=self.r.binding['brains'][old_brain]
        native_record.clear(); native_record.update(binding['brains'][self.h.s.brain])
        self.r.binding.clear(); self.r.binding.update(copy.deepcopy(binding))
        self.r.registry=self.registry; self.r.ledger=self.target
        self.r.f.registry=self.registry; self.r.f.ledger=self.target
        self.r.f.brain=self.h.s.brain; self.r.f.repo=self.h.s.checkout
        self.r.wake=AppServerWake(self.r.binding,self.target)
        self.r.f.notifier=BrainNotifier(self.target); self.r.f.notifier.app_server=self.r.wake
        for p in (patch.object(self.r.wake,'configured',return_value=True),
                  patch.object(self.r.f.notifier,'status',return_value={'status':'configured','transport':'owned_app_server'})):
            p.start(); self.addCleanup(p.stop)
        self.r.runtime=SimpleNamespace(ledger=self.target,registry=self.registry,notifier=self.r.f.notifier)
        self.r.proposals=JourneyProposals(self.r.runtime)
        self.r.state=self.state

    def state(self):
        value=self.target.snapshot()
        value.update(workspace={'id':'target','name':'Admitted disposable'},standard=standard.read(self.target),
            mission=missions.read(self.target),brainNotification={'publicReadinessSourceAvailable':True})
        return value

    def conserved(self):
        self.h.conserved()
        self.assertEqual((self.target.root/admission.successor.FENCE).read_bytes(),self.original_marker)
        self.assertEqual(admission.successor.source_claim(self.registry.root,self.h.source.workspace_id).read_bytes(),self.original_source_claim)
        self.assertIsNone(self.target.snapshot()['meta'].get('standardRun'))
        if getattr(self,'historical_source',False):
            path=self.target.root/continuity.FILE
            self.assertEqual(path.read_bytes(),self.original_continuity_bytes)
            self.assertEqual(admission.successor.pin(path),self.original_continuity_pin)

    def test_exact_admission_readiness_uses_new_review_and_same_connection_without_play(self):
        before=admission.partial.database_proof(self.target.db)
        actions=catalog(self.state())
        self.assertFalse(actions['codex_check']['available'],'The advisory guide must not offer the unsupported legacy path')
        self.assertTrue(actions[owned.WORKFLOW]['available'])
        self.r.prepare(); review=self.r.review()
        self.assertEqual(review['version'],2)
        self.assertEqual(review['local']['workerAdmission']['recordHash'],self.receipt['recordHash'])
        self.assertEqual(admission.partial.database_proof(self.target.db),before)
        self.assertFalse(any(m in ('thread/resume','turn/start') for m,_ in self.r.calls))
        self.r.confirm(); delivered=self.r.deliver()
        self.assertEqual(delivered['notification']['status'],'accepted',json.dumps(delivered['notification']))
        self.r.receipt()
        command=next(c for c in self.target.snapshot()['commands'] if c['id']==self.r.cid)
        self.assertEqual(command['notification']['status'],'accepted')
        self.assertEqual(standard.read(self.target)['catalogRefresh']['status'],'completed')
        self.assertEqual([m for m,_ in self.r.calls].count('thread/resume'),1)
        self.assertEqual([m for m,_ in self.r.calls].count('turn/start'),1)
        self.assertNotIn('nativeLoadedProfile',command['notification'],'Readiness is not a phase-control profile')
        self.conserved()

    def test_loaded_admitted_target_needs_no_additional_load(self):
        self.r.loaded=True; self.r.prepare(); self.r.confirm(); self.r.deliver(); self.r.receipt()
        self.assertNotIn('thread/resume',[m for m,_ in self.r.calls]); self.conserved()

    def test_existing_or_failed_request_cannot_be_rearmed_as_admitted_startup(self):
        old=standard.request_catalog_refresh(self.target,{'id':str(uuid.uuid4()),'contextHash':standard.read(self.target)['contextHash']})
        self.assertFalse(catalog(self.state())[owned.WORKFLOW]['available'])
        with self.assertRaises(Refusal): owned.prepare(self.registry,self.target,self.r.binding,str(uuid.uuid4()))
        self.assertFalse(owned.claims(self.target)); self.conserved()

    def test_legacy_readiness_remains_no_load_and_cannot_gain_admitted_handoff(self):
        old=standard.request_catalog_refresh(self.target,{'id':str(uuid.uuid4()),'contextHash':standard.read(self.target)['contextHash']})
        self.r.f.notifier.notify(old['id'])
        self.assertFalse(any(m in ('thread/resume','turn/start') for m,_ in self.r.calls))
        self.assertFalse(owned.claims(self.target)); self.conserved()

    def test_lost_load_or_turn_ack_is_one_shot_and_preserves_admission(self):
        self.r.prepare(); self.r.confirm(); self.r.lost_ack=True
        self.r.deliver(); self.r.deliver()
        self.assertEqual([m for m,_ in self.r.calls].count('thread/resume'),1)
        self.assertNotIn('turn/start',[m for m,_ in self.r.calls])
        with self.assertRaises(Refusal): self.r.prepare()
        self.conserved()

    def test_uncertain_turn_never_reloads_or_replays_even_with_same_admission(self):
        self.r.prepare(); self.r.confirm(); self.r.lost_turn=True
        first=self.r.deliver(); self.r.deliver()
        self.assertEqual(first['notification']['status'],'uncertain')
        self.assertEqual([m for m,_ in self.r.calls].count('thread/resume'),1)
        self.assertEqual([m for m,_ in self.r.calls].count('turn/start'),1)
        self.assertTrue(owned.journal(self.target,self.r.cid,'close').exists())
        self.conserved()

    def test_unknown_cross_workspace_ownership_after_load_fences_send(self):
        self.r.prepare(); self.r.confirm()
        original=admission.successor.other_owners; changed=False
        def ownership(*args):
            if changed: raise Refusal('Synthetic newly uncertain foreign repository ownership')
            return original(*args)
        def after_load(method):
            nonlocal changed
            if method=='thread/resume': changed=True
        self.r.callback=after_load
        with patch.object(admission.successor,'other_owners',side_effect=ownership): self.r.deliver()
        self.assertEqual([m for m,_ in self.r.calls].count('thread/resume'),1)
        self.assertNotIn('turn/start',[m for m,_ in self.r.calls]); self.conserved()

    def test_stop_after_claim_prevents_turn_and_keeps_both_admission_claims(self):
        self.r.prepare(); self.r.confirm()
        def stop(method):
            if method=='thread/resume':
                with self.target.tx() as db:
                    meta=Ledger.get(db,'meta',1); meta['brainControl']={'desired':'stopped','phase':'checkpointing'}
                    Ledger.put(db,'meta',1,meta)
        self.r.callback=stop; self.r.deliver()
        self.assertNotIn('turn/start',[m for m,_ in self.r.calls]); self.conserved()

    def test_binding_drift_and_version_one_cannot_authorize_admitted_load(self):
        self.r.prepare(); original=copy.deepcopy(self.r.binding)
        self.r.binding['brains'][self.h.s.brain]['projectId']=str(uuid.uuid4())
        with self.assertRaises(Refusal): self.r.confirm()
        self.r.binding.clear(); self.r.binding.update(original)
        value=self.r.review(); value['version']=1
        with self.assertRaises(Refusal): owned.validate_review(value)
        value=self.r.review(); value['local'].pop('workerAdmission')
        with self.assertRaises(Refusal): owned.validate_review(value)
        self.assertFalse(owned.claims(self.target)); self.conserved()

    def test_private_backup_includes_external_source_claim_and_binding(self):
        self.r.prepare(); self.r.confirm()
        review=self.r.review()
        self.assertIn('admitted-source-claim',review['local']['sidecars'])
        self.assertIn('admitted-binding',review['local']['sidecars'])
        proof=owned.record(owned.fence(self.target))
        archive=owned.record(proof['backup']['path'],1_000_000)
        self.assertEqual(len(archive['files']),2+len(review['local']['sidecars']))
        self.conserved()


class HistoricalAdmittedReadinessWireTest(unittest.TestCase):
    def setUp(self):
        self.f=AdmittedReadinessTest('runTest'); self.f.historical_source=True
        self.addCleanup(self.f.doCleanups); self.f.setUp()

    def test_signed_display_and_integer_authority_pins_survive_real_javascript(self):
        f=self.f; p=f.r.prepare(); review=f.r.review()
        original=review['local']['workerAdmission']['sourceContinuityPin']
        self.assertEqual(original,f.original_continuity_pin)
        self.assertIn(1792000000000000001,original['identity'])
        display=p['document']['preview']['details']['workerAdmission']['sourceContinuityPin']
        self.assertEqual(display,{'sha256':original['sha256'],'identity':[str(n) for n in original['identity']]})
        wire=f.r.browser_roundtrip(p)
        self.assertEqual(wire,p,'The complete signed envelope, not just its inner request, must survive JavaScript')
        self.assertEqual(f.r.review(wire),review)
        f.r.confirm(wire); delivered=f.r.deliver(); f.r.receipt()
        self.assertEqual(delivered['notification']['status'],'accepted')
        saved=next(c for c in f.target.snapshot()['commands'] if c['id']==f.r.cid)
        self.assertEqual(saved['payload']['readinessStart'],review)
        f.r.confirm(wire); f.r.deliver()
        self.assertEqual([m for m,_ in f.r.calls].count('thread/resume'),1)
        self.assertEqual([m for m,_ in f.r.calls].count('turn/start'),1)
        self.assertEqual(standard.read(f.target)['catalogRefresh']['status'],'completed')
        f.conserved()

    def test_display_or_authority_tampering_cannot_create_a_claim(self):
        f=self.f; p=f.r.prepare()
        for value in ('1792000000000000002',1792000000000000001):
            bad=f.r.browser_roundtrip(p)
            bad['document']['preview']['details']['workerAdmission']['sourceContinuityPin']['identity'][-1]=value
            with self.subTest(display=value), self.assertRaises(Refusal): f.r.confirm(bad)
        review=f.r.review(); rounded=f.r.browser_roundtrip(review)
        self.assertNotEqual(rounded['local']['workerAdmission']['sourceContinuityPin'],f.original_continuity_pin)
        bad=copy.deepcopy(p); bad['document']['request']=owned.browser_request(rounded)
        bad['signature']=f.r.proposals.sign(bad['document'])
        with self.assertRaises(Refusal): f.r.confirm(bad)
        review['local']['workerAdmission']['sourceContinuityPin']['identity']=[str(n) for n in f.original_continuity_pin['identity']]
        with self.assertRaises(Refusal): owned.validate_review(review)
        self.assertFalse(owned.claims(f.target)); self.assertEqual(f.target.snapshot()['commands'],[])
        self.assertFalse(any(m in ('thread/resume','turn/start') for m,_ in f.r.calls))
        f.conserved()


class AdmissionSourceContinuityTest(unittest.TestCase):
    def setUp(self):
        self.h=lineage.HistoricalAdmissionTest('runTest'); self.h.setUp(); self.addCleanup(self.h.doCleanups)
        self.registry,self.target=self.h.registry,self.h.target
        self.frozen=self.h.u.f.f.f.root/'inert-qualified-source'
        directory=self.frozen/'orchestrator'; directory.mkdir(parents=True,mode=0o700)
        file=directory/'fixture.py'; file.write_text("raise AssertionError('Historical source must never execute')\n"); file.chmod(0o600)
        self.old=source_proof(self.frozen)['sourceHash']; self.epoch=self.old
        original=history.context
        def historical_context(*args,**kwargs):
            context,result,q=original(*args,**kwargs); context['sourceHash']=self.epoch
            return context,result,q
        for p in (patch.object(history,'PR185_SOURCE',self.old),patch.object(history,'context',side_effect=historical_context),
                  patch.object(admission,'source_hash',side_effect=lambda:self.epoch)):
            p.start(); self.addCleanup(p.stop)
        self.h.qualify()
        state=missions.read(self.target)
        missions.change(self.target,{'id':'review-source-epoch-fixture','operation':'review','expectedRevision':state['revision'],
            'documentHash':state['documentHash'],'confirmed':True})
        self.preview=self.h.prepare()
        admission.backup(self.registry,self.h.source,self.preview['request'],self.h.backup,writers_stopped=True)
        self.receipt=admission.confirm(self.registry,self.h.source,self.preview['request'],self.preview['reviewHash'],
            writers_stopped=True,backup_root=self.h.backup)
        self.before=admission.partial.database_proof(self.target.db)
        self.epoch='f'*64  # Prospective synthetic installation, never a live source override.

    def retained(self):
        with standard.read_db(self.target.db) as db: return admission.retained_in(self.target,db)

    def test_explicit_frozen_source_qualifies_completed_record_without_rewriting_rows_or_usage(self):
        with self.assertRaises((Refusal,OSError)): self.retained()
        result=continuity.qualify(self.registry,self.target,self.frozen,writers_stopped=True)
        self.assertFalse(result['nativeAction']); self.assertFalse(result['playAuthorized'])
        self.assertEqual(self.retained()['reviewHash'],self.preview['reviewHash'])
        self.assertEqual(admission.partial.database_proof(self.target.db),self.before)
        with self.assertRaises(Refusal): history.status(self.registry,self.h.source,self.h.out)
        self.assertEqual(history.status(self.registry,self.h.source,self.h.out,implementation_source=self.frozen)['qualifiedAt'],
            history.continuity.setup.read(self.h.out/'evidence.json')['qualifiedAt'])
        self.h.conserved()

    def test_unknown_changed_or_missing_frozen_source_refuses(self):
        file=self.frozen/'orchestrator/fixture.py'; file.write_text('changed source\n')
        with self.assertRaises(Refusal): continuity.qualify(self.registry,self.target,self.frozen,writers_stopped=True)
        self.assertFalse((self.target.root/continuity.FILE).exists())
        self.assertEqual(admission.partial.database_proof(self.target.db),self.before)

    def test_writers_must_be_explicitly_quiesced_and_later_source_drift_refuses(self):
        with self.assertRaises(Refusal): continuity.qualify(self.registry,self.target,self.frozen)
        self.assertFalse((self.target.root/continuity.FILE).exists())
        continuity.qualify(self.registry,self.target,self.frozen,writers_stopped=True)
        (self.frozen/'orchestrator/fixture.py').write_text('changed after qualification\n')
        with self.assertRaises(Refusal): self.retained()
        self.assertEqual(admission.partial.database_proof(self.target.db),self.before)

    def test_qualification_does_not_authorize_old_pending_request_or_second_admission(self):
        continuity.qualify(self.registry,self.target,self.frozen,writers_stopped=True)
        file=self.h.u.f.f.f.root/'pending-old-request.json'; self.h.s.write(file,self.preview['request'])
        with self.assertRaises(Refusal): admission.read_request(file)
        with self.assertRaises(Refusal): continuity.qualify(self.registry,self.target,self.frozen,writers_stopped=True)
        self.assertEqual(self.retained()['reviewHash'],self.preview['reviewHash']); self.h.conserved()

    def test_partial_or_changed_source_claim_never_qualifies(self):
        source=admission.successor.source_claim(self.registry.root,self.h.source.workspace_id)
        self.h.s.write(source,{'kind':admission.KIND,'target':'foreign','recordHash':'0'*64})
        with self.assertRaises(Refusal): continuity.qualify(self.registry,self.target,self.frozen,writers_stopped=True)
        self.assertFalse((self.target.root/continuity.FILE).exists())


if __name__=='__main__': unittest.main()
