"""Combined real SQLite/Git lineage with synthetic native metadata only."""
import copy
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from orchestrator import historical_admission as api, worker_phase_admission as admission
from orchestrator import empty_setup_transition as setup, missions, projects, standard
from orchestrator.core import Ledger, Refusal, canonical, digest
from orchestrator.workspaces import fingerprint
from test_empty_setup_transition import Fixture as SetupFixture
from test_native_policy_evidence import CONTRACT
import test_post_preparation_usage as usage_fixtures
import test_standard_run_mailbox as source_fixtures


class HistoricalAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.s=SetupFixture('runTest'); self.s.setUp(); self.addCleanup(self.s.doCleanups)
        original=source_fixtures.RunMailboxTest.setUp; record=projects.record
        fixture=self
        def registered(f):
            original(f)
            # The source's original dashboard lock predates every captured
            # disposition, like the live dashboard. Creating a new sidecar
            # afterward must (and does) invalidate historical provenance.
            lock=f.ledger.root/'dashboard.lock'; lock.write_bytes(b''); lock.chmod(0o600)
            f.registry.register('target','Pre-existing unused fixture target',fixture.s.ledger.root)
            fixture.s.registry=f.registry; fixture.s.ledger=f.registry.ledger('target')
        def catalog(registry,value,at):
            value=copy.deepcopy(value); value['projects'].extend(fixture.s.catalog_result('old-catalog')['projects'])
            result=record(registry,value,at)
            projects.bind(registry,'target','local','old-catalog',projects.catalog(registry)['hash'])
            fixture.catalog=copy.deepcopy(value)
            return result
        self.u=usage_fixtures.UsageTest('runTest'); self.addCleanup(self.u.doCleanups)
        with patch.object(source_fixtures.RunMailboxTest,'setUp',registered),patch.object(projects,'record',catalog): self.u.setUp()
        self.registry=self.u.registry; self.source=self.u.ledger; self.target=self.s.ledger
        actual=copy.deepcopy(self.catalog)
        actual['projects']=[p for p in actual['projects'] if p['path']!=str(self.s.checkout)]
        actual['projects'].extend(self.s.catalog_result(self.s.catalog)['projects'])
        self.s.write(self.s.spec['catalogObservation'],{'source':'codex_app.list_projects','observedAt':time.time(),'completeResult':actual})
        # An unused draft is adjusted BEFORE the separately approved setup capture.
        state=missions.read(self.target); spec=copy.deepcopy(state['document']['spec'])
        spec['authority'].update(tokenBudget=1000,checkpointReserveTokens=100)
        missions.change(self.target,{'id':'bounded-fixture-draft','operation':'save','expectedRevision':state['revision'],'spec':spec})
        self.old_usage=self.u.collect(); self.assertEqual(self.old_usage['status'],'usage_observed')
        self.prepared=self.s.preview(); self.receipt=self.s.confirm(self.prepared)
        self.target=self.registry.ledger('target')
        self.out=self.u.f.f.f.root/'requalification'; self.backup=self.u.f.f.f.root/'admission-backup'
        self.binding=self.u.f.f.f.root/'target-binding.json'
        endpoint=patch('orchestrator.native_project_assignment.validate_endpoint')
        endpoint.start(); self.addCleanup(endpoint.stop)  # Explicit fake endpoint, never a live proxy.
        self.s.write(self.binding,{'endpoint':{'fixture':'target','sha256':'a'*64},'brains':{self.s.brain:{
            'workspaceId':'target','cwd':str(self.s.checkout),'projectId':self.s.native,'catalogProjectId':self.s.catalog,
            'nativePolicy':{'sandbox':'workspace-write','approvalPolicy':'on-request','codeMode':False},'policyEvidence':CONTRACT}}})
        with standard.read_db(self.source.db) as db: self.original_source=fingerprint(db)
        self.native_calls=list(self.u.f.calls); self.setup_calls=list(self.s.calls)

    def qualify(self): return api.qualify(self.registry,self.source,'target',self.u.out,self.out)

    def review_target(self):
        state=missions.read(self.target)
        missions.change(self.target,{'id':'review-new-target','operation':'review','expectedRevision':state['revision'],
            'documentHash':state['documentHash'],'confirmed':True})
        token=self.target.acquire(self.s.brain+':fixture-catalog')
        standard.brain(self.registry,self.target,token,{'operation':'catalog','models':[{'model':'fixture','efforts':['low']}],
            'source':'Synthetic exact metadata fixture'})
        self.target.release(token,'Fixture current catalog retained')

    def prepare(self):
        return admission.prepare(self.registry,self.source,'target',self.binding,self.u.out,
            local_only=True,requalification=self.out)

    def conserved(self):
        with standard.read_db(self.source.db) as db: self.assertEqual(fingerprint(db),self.original_source)
        self.assertEqual(self.u.f.calls,self.native_calls); self.assertEqual(self.s.calls,self.setup_calls)
        self.assertEqual(setup.retained(self.target.root),self.receipt)

    def test_requalification_never_collects_loads_or_renews_usage(self):
        with self.assertRaises(Refusal): api.usage.status(self.registry,self.source,self.u.out)
        value=self.qualify(); self.assertEqual(value,api.status(self.registry,self.source,self.out))
        self.assertEqual(value['postPreparationTokens'],self.old_usage['report']['tokens']['total_tokens'])
        self.assertEqual(value['context']['originalUsageCollectedAt'],self.old_usage['report']['collectedAt'])
        self.assertFalse(value['boundary']['playAuthorized']); self.conserved()

    def test_report_cannot_bypass_mission_review_or_be_implicit_admission(self):
        self.qualify()
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse((self.target.root/admission.successor.FENCE).exists()); self.conserved()

    def test_exact_admission_and_backup_carry_historical_evidence_then_preserve_source(self):
        self.qualify(); self.review_target(); p=self.prepare()
        result=admission.backup(self.registry,self.source,p['request'],self.backup,writers_stopped=True)
        self.assertGreater(result['files'],10)
        result=admission.confirm(self.registry,self.source,p['request'],p['reviewHash'],writers_stopped=True,backup_root=self.backup)
        self.assertEqual(result['outcome'],'lineage_recorded_play_not_started')
        with standard.read_db(self.target.db) as db:
            saved=admission.retained_in(self.target,db)
            self.assertEqual(saved['reviewHash'],p['reviewHash']); self.assertNotIn('standardRun',Ledger.get(db,'meta',1))
        self.assertEqual(api.status(self.registry,self.source,self.out)['status'],'historical_admission_evidence_requalified')
        controls=standard.Controls()
        preview=controls.preview(self.target,{'operation':'play','contextHash':standard.read(self.target)['contextHash'],
            'brainAllowance':100,'durationHours':24},'fixture-owner')
        command=controls.confirm(self.registry,self.target,{**preview,'confirmed':True},'fixture-owner')
        self.assertEqual(command['payload']['successorHash'],result['recordHash'])
        self.assertNotEqual(standard.read(self.target)['run']['id'],self.u.q['original']['run']['id'])
        self.assertEqual(api.status(self.registry,self.source,self.out)['status'],'historical_admission_evidence_requalified')
        self.conserved()

    def test_default_admission_still_refuses_old_registry_even_after_qualified_report(self):
        self.qualify(); self.review_target()
        with self.assertRaises(Refusal): admission.prepare(self.registry,self.source,'target',self.binding,self.u.out,local_only=True)
        self.conserved()

    def test_partial_or_extra_report_cannot_be_used(self):
        self.qualify(); self.s.write(self.out/'extra.json',{'unlisted':True})
        with self.assertRaises(Refusal): api.status(self.registry,self.source,self.out)
        self.conserved()

    def test_numeric_tamper_or_gap_cannot_be_refunded(self):
        self.qualify(); value=setup.read(self.u.out/'evidence.json')
        value['report']['tokens']['total_tokens']=0; self.s.write(self.u.out/'evidence.json',value)
        with self.assertRaises(Refusal): api.status(self.registry,self.source,self.out)
        self.conserved()

    def test_requalification_timestamp_cannot_refresh_accounting(self):
        value=self.qualify(); self.u.f.f.now+=86400*2
        self.assertEqual(api.status(self.registry,self.source,self.out),value)
        with self.assertRaises(Refusal): api.usage.status(self.registry,self.source,self.u.out,fresh=True,
            setup_transition={'targetId':'target','setupSource':None})
        self.conserved()

    def test_no_historical_path_authorizes_live_collection(self):
        with self.assertRaises(Refusal): api.usage.context(self.registry,self.source,self.u.completed,live=True,
            setup_transition={'targetId':'target','setupSource':None})
        self.conserved()

    def test_changed_source_or_original_hold_does_not_rearm_report(self):
        self.qualify()
        with patch.object(api.continuity.setup,'source_hash',return_value='0'*64):
            with self.assertRaises(Refusal): api.status(self.registry,self.source,self.out)
        with self.assertRaises(Refusal): self.qualify()
        self.conserved()


if __name__=='__main__': unittest.main()
