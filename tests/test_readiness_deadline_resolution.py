"""Disposable deadlines and real SQLite admission resolution; no live calls."""
import copy
import json
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from orchestrator import readiness_prestart_resolution as resolution, readiness_owned as owned
from orchestrator import standard, standard_preplay as preplay, partial_admission as partial
from orchestrator import projects
from orchestrator.app_server_wake import WakeProxy
from orchestrator.core import Refusal, canonical, digest
from orchestrator.native_read_client import NativeReadFailure, ReadProxy
from orchestrator.standard_quarantine import exclusive
import test_admitted_readiness as admitted
import test_readiness_owned as fixtures


class ReadinessDeadlineTest(unittest.TestCase):
    def test_rpc_budgets_exclude_local_work_but_never_renew_connection_window(self):
        proxy=WakeProxy({}); now=[100.0]; calls=[]
        def watched(): proxy._watching=True
        def rpc(_self,method,params):
            calls.append((method,proxy.deadline)); return {'fixture':True}
        with patch('time.monotonic',side_effect=lambda:now[0]),patch.object(proxy,'watch_connection',side_effect=watched), \
                patch.object(ReadProxy,'_rpc',autospec=True,side_effect=rpc):
            proxy.begin_readiness(900); end=proxy._readiness_owned_deadline
            self.assertTrue(proxy._watching)
            now[0]+=60  # slow foreground ledger/source validation, no native I/O
            proxy._rpc('account/read',{'refreshToken':False})
            self.assertEqual(calls[-1],('account/read',175))
            now[0]=995; proxy._rpc('thread/read',{})
            self.assertEqual(calls[-1][1],end)
            now[0]=end
            with self.assertRaises(Refusal): proxy._rpc('turn/start',{})
            self.assertEqual(len(calls),2,'Expired window refuses before even entering RPC')
            with self.assertRaises(Refusal): proxy.begin_readiness(900)
            self.assertEqual(proxy._readiness_owned_deadline,end)

    def test_legacy_proxy_does_not_acquire_readiness_deadline(self):
        proxy=WakeProxy({}); proxy.deadline=123
        with patch.object(ReadProxy,'_rpc',return_value={}): proxy._rpc('thread/read',{})
        self.assertEqual(proxy.deadline,123); self.assertFalse(hasattr(proxy,'_readiness_owned_deadline'))

    def test_real_deadline_guard_still_refuses_slow_native_io(self):
        proxy=WakeProxy({}); proxy.deadline=10
        with patch('time.monotonic',return_value=11):
            with self.assertRaises(NativeReadFailure): ReadProxy._ready(proxy,None,1)

    def test_short_io_budget_never_renews_native_scope_freshness(self):
        proxy=WakeProxy({}); proxy._readiness_owned_deadline=1000
        with patch('time.monotonic',return_value=500),patch.object(ReadProxy,'_rpc') as rpc:
            with self.assertRaises(Refusal): proxy._rpc('turn/start',{})
            proxy._readiness_scope_checked_at=379
            with self.assertRaises(Refusal): proxy._rpc('turn/start',{})
            rpc.assert_not_called()
            proxy._readiness_scope_checked_at=380
            proxy._rpc('turn/start',{}); rpc.assert_called_once()
            self.assertEqual(proxy._readiness_owned_deadline,1000)


class PrestartResolutionTest(unittest.TestCase):
    def setUp(self):
        self.a=None
        if 'admitted' in self._testMethodName:
            self.a=admitted.AdmittedReadinessTest('runTest'); self.a.setUp(); self.addCleanup(self.a.doCleanups)
            self.r=self.a.r; self.binding_file=self.a.h.binding
        else:
            self.r=fixtures.ReadinessOwnedTest('runTest'); self.r.setUp(); self.addCleanup(self.r.doCleanups)
            brain=self.r.f.brain; native=self.r.binding['brains'][brain]['projectId']
            projects.record(self.r.registry,{'schemaVersion':2,'projects':[{'projectId':native,'projectKind':'local',
                'hostId':'local','label':'Fixture','path':str(self.r.f.repo),'isGitRepository':True}]},time.time())
            projects.bind(self.r.registry,'v3','local',native,projects.catalog(self.r.registry)['hash'])
            self.binding_file=self.r.f.root/'original-binding.json'
            self.binding_file.write_text(canonical(self.r.binding)); self.binding_file.chmod(0o600)
        self.ledger=self.r.ledger; self.registry=self.r.registry
        self.r.prepare(); self.r.confirm()
        def failed(method):
            if method=='account/read': raise NativeReadFailure('deadline_exceeded','Synthetic local deadline')
        self.r.callback=failed; c=self.r.deliver(); self.cid=self.r.cid
        self.assertEqual(c['notification']['nativeFailure']['stage'],'authentication_check')
        self.original=copy.deepcopy(c); self.before=partial.database_proof(self.ledger.db)
        self.meta=self.ledger.snapshot()['meta']
        self.source=preplay.SOURCE; self.pins={p.name:p.read_bytes() for p in self.ledger.root.iterdir()
            if p.name.startswith(('readiness-owned-','preplay-catalog-'))}
        self.calls=copy.deepcopy(self.r.calls)

    def prepare(self):
        return resolution.prepare(self.registry,self.ledger,self.binding_file,self.cid,self.source)

    def mutate(self,fn):
        with self.ledger.tx() as db:
            c=self.ledger.get(db,'commands',self.cid); fn(c); self.ledger.put(db,'commands',self.cid,c)

    def apply(self):
        p=self.prepare(); b=self.r.f.root/'resolution-backup'
        resolution.backup(self.registry,self.ledger,p['request'],b,writers_stopped=True)
        return p,b,resolution.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],writers_stopped=True,backup_root=b)

    def conserved(self):
        if self.a:self.a.conserved()
        self.assertEqual(self.ledger.snapshot()['meta'],self.meta)
        self.assertEqual(next(c for c in self.ledger.snapshot()['commands'] if c['id']==self.cid),self.original)
        self.assertEqual(self.r.calls,self.calls)
        for name,raw in self.pins.items(): self.assertEqual((self.ledger.root/name).read_bytes(),raw)

    def test_review_is_read_only_scope_bound_no_timer_or_native_client(self):
        p=self.prepare(); self.assertEqual(p['validUntil'],'scope_changes')
        self.assertEqual(partial.database_proof(self.ledger.db),self.before)
        self.assertFalse(p['boundary']['readinessAllowanceRestored'])
        self.assertEqual(resolution.prepare(self.registry,self.ledger,self.binding_file,self.cid,self.source),p)
        self.conserved()

    def test_exact_disposition_preserves_request_claims_and_does_not_enable_play(self):
        p,b,result=self.apply()
        self.assertEqual(result['status'],'disposed_unqualified')
        self.assertEqual(resolution.status(self.ledger),result)
        s=standard.read(self.ledger)
        self.assertFalse(s['available']); self.assertEqual(s['readinessResolution'],result)
        self.assertEqual(s['catalogRefresh']['status'],'queued')
        self.assertEqual(self.ledger.snapshot()['workflow']['pendingRequests'],0)
        self.assertEqual(resolution.confirm(self.registry,self.ledger,p['request'],p['reviewHash']),result)
        with self.assertRaises(Refusal): self.r.deliver()
        with self.assertRaises(Refusal): self.r.prepare()
        with self.assertRaises(Refusal): standard.request_catalog_refresh(self.ledger,{'id':'never-rearmed','contextHash':s['contextHash']})
        self.conserved()

    def test_admitted_resolution_preserves_both_claims_and_original_source_lineage(self):
        self.test_exact_disposition_preserves_request_claims_and_does_not_enable_play()

    def test_old_approval_and_unstopped_or_missing_backup_refuse(self):
        p=self.prepare()
        for kw in ({},{'writers_stopped':True}):
            with self.assertRaises(Refusal): resolution.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],**kw)
        with self.assertRaises(Refusal): resolution.confirm(self.registry,self.ledger,p['request'],'f'*64)
        self.assertFalse((self.ledger.root/resolution.FENCE).exists()); self.conserved()

    def test_partial_intent_never_reapplies_and_fences_normal_writes(self):
        p=self.prepare(); exclusive(self.ledger.root/resolution.FENCE,{'kind':resolution.KIND,'reviewHash':p['reviewHash']})
        self.assertEqual(resolution.status(self.ledger)['status'],'incomplete_or_changed')
        self.assertFalse(standard.read(self.ledger)['available'])
        with self.assertRaises(Refusal): resolution.confirm(self.registry,self.ledger,p['request'],p['reviewHash'])
        with self.assertRaises(Refusal): self.r.deliver()
        self.assertEqual(self.r.calls,self.calls)

    def test_positive_failure_flags_are_required_not_absence_or_status(self):
        for change in (
            lambda c:c['notification']['nativeFailure'].update(resumeAttempted=True),
            lambda c:c['notification']['nativeFailure'].update(turnStartAttempted=True),
            lambda c:c['notification']['nativeFailure'].update(reason='connection_lost'),
            lambda c:c['notification'].update(nativeTurnId='unknown'),
            lambda c:c['notification'].update(status='sending'),
            lambda c:c.update(catalogReceipt={}),
        ):
            self.mutate(change)
            with self.assertRaises(Refusal): self.prepare()
            with self.ledger.tx() as db:self.ledger.put(db,'commands',self.cid,self.original)

    def test_any_load_or_capture_record_refuses_without_discarding_it(self):
        p=owned.journal(self.ledger,self.cid,'load-claim'); exclusive(p,{'unknown':True})
        with self.assertRaises(Refusal): self.prepare()
        self.assertTrue(p.exists()); self.assertEqual(self.r.calls,self.calls)

    def test_binding_and_original_source_changes_are_not_migrated(self):
        value=json.loads(self.binding_file.read_text()); value['brains'][self.r.f.brain]['projectId']='changed'
        self.binding_file.write_text(canonical(value))
        with self.assertRaises(Refusal): self.prepare()
        self.assertEqual(self.r.calls,self.calls)

    def test_unknown_or_changed_historical_implementation_refuses(self):
        with patch.object(resolution,'source_proof',return_value={'root':str(self.source),'sourceHash':'f'*64,'epochHash':'a'*64}):
            with self.assertRaises(Refusal): self.prepare()
        self.conserved()

    def test_backup_corruption_is_not_overwritten_or_applied(self):
        p=self.prepare(); b=self.r.f.root/'resolution-backup'
        resolution.backup(self.registry,self.ledger,p['request'],b,writers_stopped=True)
        (b/'sidecar-0.json').write_text('corrupt')
        with self.assertRaises(Refusal): resolution.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],writers_stopped=True,backup_root=b)
        self.assertFalse((self.ledger.root/resolution.FENCE).exists()); self.conserved()

    def test_missing_claim_cannot_downgrade_or_restore_writes(self):
        self.apply(); (self.ledger.root/resolution.FENCE).unlink()  # disposable corruption only
        self.assertEqual(resolution.status(self.ledger)['status'],'incomplete_or_changed')
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass

    def test_changed_old_snapshot_is_detected_without_repairing_it(self):
        p,b,result=self.apply()
        with sqlite3.connect(self.ledger.db) as db:
            db.execute("UPDATE snapshots SET data='{}' WHERE id<>?",(result['recordHash'],))
        self.assertEqual(resolution.status(self.ledger)['status'],'incomplete_or_changed')
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass
