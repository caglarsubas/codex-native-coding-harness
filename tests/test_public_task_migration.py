"""Read-only original/candidate assessments, never live migration authority."""
import copy
import time
import unittest
from unittest.mock import patch

from orchestrator import public_task_migration as migration, standard
from orchestrator.core import Refusal, canonical, digest
from orchestrator.workspaces import fingerprint
import test_public_native_tasks as task_fixtures


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.fixture=task_fixtures.AdapterTest(methodName="runTest")
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        f=self.fixture
        self.ledger,self.registry=f.ledger,f.registry
        self.current=copy.deepcopy(f.binding);self.original=copy.deepcopy(f.binding)
        self.original["endpoint"]["sha256"]="d"*64
        self.original["brains"][f.brain].pop("nativeTaskBackend")
        self.original["brains"][f.brain].pop("policyEvidence")
        with self.ledger.tx() as db:
            meta=self.ledger.get(db,"meta",1)
            meta["controller"]=None
            meta["standardRun"].update(status="paused",tasks=[])
            self.ledger.put(db,"meta",1,meta)
            play=self.ledger.get(db,"commands",f.command_id)
            play["notification"]["hostBindingHash"]=digest(self.original)
            self.ledger.put(db,"commands",f.command_id,play)
        self.fake=f.fake
        self.fake.threads[f.brain]["status"]={"type":"idle","activeFlags":[]}
        self.fake._rpc=lambda *_:copy.deepcopy(f.raw)
        self.paths=(f.host.fixture.fixture.root/"candidate",f.host.fixture.fixture.root/"original")
        for item in (patch.object(migration,"_read_binding",side_effect=lambda _:copy.deepcopy(self.original)),
                     patch.object(migration,"load_binding",side_effect=lambda _:copy.deepcopy(self.current)),
                     patch.object(migration,"TaskReadProxy",return_value=self.fake)):
            item.start();self.addCleanup(item.stop)

    def assess(self):
        return migration.assess(self.registry,self.ledger,self.fixture.run_id,*self.paths)

    def test_matching_current_policy_and_empty_tracker_never_prove_historical_cleanup(self):
        with standard.read_db(self.ledger.db) as db:before=fingerprint(db)
        saved=copy.deepcopy(self.ledger.snapshot())
        result=self.assess()
        self.assertEqual(result["status"],"blocked")
        self.assertTrue(result["candidatePolicyMatches"])
        self.assertEqual(result["currentTrackedTerminals"],"none")
        self.assertFalse(result["migrationQualified"])
        self.assertIn("historical_terminal_and_effect_coverage_unknown",result["issues"])
        self.assertIn("separate_same_run_transition_not_reviewed",result["issues"])
        self.assertFalse(any(result["boundary"].values()))
        after=self.ledger.snapshot()
        self.assertEqual(after["meta"],saved["meta"])
        self.assertEqual(after["commands"],saved["commands"])
        with standard.read_db(self.ledger.db) as db:self.assertEqual(fingerprint(db),before)
        for method,_ in self.fake.calls:self.assertIn(method,{"project/read","thread/read","thread/backgroundTerminals/list"})
        self.assertNotIn(str(self.fixture.host.fixture.repo),canonical(result))

    def test_unloaded_remains_unknown_without_loading_or_recovery(self):
        self.fake.threads[self.fixture.brain]["status"]={"type":"notLoaded"}
        self.fixture.raw["policy"]=None
        result=self.assess()
        self.assertEqual(result["currentTrackedTerminals"],"unknown")
        self.assertFalse(result["candidatePolicyMatches"])
        self.assertNotIn("thread/resume",[m for m,_ in self.fake.calls])
        self.assertNotIn("thread/backgroundTerminals/list",[m for m,_ in self.fake.calls])

    def test_both_project_ids_native_policy_and_checkout_are_immutable(self):
        record=self.current["brains"][self.fixture.brain]
        for key,value in (("catalogProjectId","changed"),("projectId","changed"),("cwd","/changed"),
                          ("nativePolicy",{"sandbox":"danger-full-access"})):
            original=copy.deepcopy(record[key]);record[key]=value
            with self.assertRaises(Refusal):self.assess()
            record[key]=original
        self.assertFalse(self.fake.calls)

    def test_original_binding_is_never_a_connect_target(self):
        result=self.assess()
        self.assertEqual(result["originalBindingHash"],digest(self.original))
        self.assertNotEqual(result["candidateBindingHash"],digest(self.original))
        self.assertEqual(self.fake.endpoint["fixture"],"pinned")

    def test_expiry_is_not_extended_or_usage_reset(self):
        with self.ledger.tx() as db:
            meta=self.ledger.get(db,"meta",1)
            meta["standardRun"].update(expiresAt=time.time()-1,brainObservedTokens=123456,brainUsageCoverage="observed_partial")
            self.ledger.put(db,"meta",1,meta)
        before=copy.deepcopy(standard.read(self.ledger)["run"])
        result=self.assess()
        self.assertIn("original_phase_duration_expired",result["issues"])
        self.assertEqual(standard.read(self.ledger)["run"],before)

    def test_concurrent_change_invalidates_assessment(self):
        def race(*_):
            self.fake.callback=None
            with self.ledger.tx() as db:
                meta=self.ledger.get(db,"meta",1);meta["standardRun"]["status"]="stopping"
                self.ledger.put(db,"meta",1,meta)
        self.fake.callback=race
        with self.assertRaises(Refusal):self.assess()

    def test_missing_original_play_receipt_or_pending_owner_refuses(self):
        with self.ledger.tx() as db:
            command=self.ledger.get(db,"commands",self.fixture.command_id)
            command["status"]="queued"
            self.ledger.put(db,"commands",command["id"],command)
        with self.assertRaises(Refusal):self.assess()
        self.assertFalse(self.fake.calls)


if __name__=="__main__":unittest.main()
