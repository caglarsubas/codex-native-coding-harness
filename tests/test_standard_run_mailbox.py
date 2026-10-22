"""Disposable standard-run IPC, sandbox, conservation and held-request tests."""
import contextlib
import copy
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from orchestrator import standard, standard_run_mailbox as mailbox
from orchestrator import standard_host_inspection as inspection
from orchestrator.core import Ledger, Refusal, canonical, digest
from orchestrator.notification import BrainNotifier
from orchestrator.workspaces import Registry, fingerprint
from orchestrator.missions import change
from test_missions import specification, request
from test_native_policy_evidence import CONTRACT as POLICY, response
from test_public_native_tasks import CONTRACT as BACKEND


class RunMailboxTest(unittest.TestCase):
    measure_usage = True
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / 'checkout'
        self.repo.mkdir(mode=0o700)
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'Base'], check=True)
        self.registry = Registry(self.root / 'protected-registry', create=True)
        self.brain, self.project = str(uuid.uuid4()), str(uuid.uuid4())
        ledger = Ledger(self.repo / '.state')
        ledger.initialize({'schemaVersion': 1, 'brainId': self.brain, 'repositories': [{
            'id': 'a', 'path': str(self.repo), 'projectId': 'projectless', 'ref': 'HEAD',
            'policyProfile': 'standard', 'mergePolicy': 'manual'}]})
        self.registry.register('v3', 'Disposable V3', ledger.root)
        self.ledger = self.registry.ledger('v3')
        saved = change(self.ledger, request(spec=specification(mode='phase_delegated')))['current']
        change(self.ledger, request('review', saved['revision'], documentHash=saved['documentHash'], confirmed=True))
        token = self.ledger.acquire(self.brain + ':catalog')
        standard.brain(self.registry, self.ledger, token, {'operation': 'catalog',
            'models': [{'model': 'fixture', 'efforts': ['low']}], 'source': 'Disposable actual-tool fixture'})
        self.ledger.release(token, 'Catalog captured')
        self.home = self.root / 'usage-home'
        self.home.mkdir(mode=0o700)
        inspection._write_once(self.ledger.root / 'observations.json',
                               {'codexHome': str(self.home), 'artifactRoots': [], 'roadmaps': []})
        self.controls = standard.Controls()
        preview = self.controls.preview(self.ledger, {'operation': 'play',
            'contextHash': standard.read(self.ledger)['contextHash'], 'brainAllowance': 10000,
            'durationHours': 8, 'measureUsage': self.measure_usage}, 'owner')
        self.command = self.controls.confirm(self.registry, self.ledger, {**preview, 'confirmed': True}, 'owner')
        self.cid = self.command['id']
        self.run = standard.read(self.ledger)['run']
        self.run_id = self.run['id']
        self.turn = str(uuid.uuid4())
        self.binding = {'endpoint': {'sha256': 'c' * 64}, 'brains': {self.brain: {
            'workspaceId': 'v3', 'projectId': self.project, 'cwd': str(self.repo),
            'nativePolicy': {'sandbox': 'workspace-write', 'approvalPolicy': 'on-request', 'codeMode': False},
            'policyEvidence': POLICY.copy(), 'nativeTaskBackend': BACKEND.copy()}}}
        self.host = SimpleNamespace(ledger=self.ledger, binding=self.binding, _closed=False,
            configured=lambda _: True, pending_approval=lambda _: None, send=self.send)
        self.sent = []
        notifier = BrainNotifier(self.ledger)
        notifier.app_server = self.host
        with patch.object(notifier, 'status', return_value={'status': 'configured', 'transport': 'owned_app_server'}):
            notifier.notify(self.cid)
        self.handoff = mailbox.path(self.ledger.root, self.cid, 'handoff')
        self.sequence = 0
        self.calls = {}
        self.write_usage()

    def send(self, brain, message, cid):
        self.sent.append(message)
        self.assertTrue(mailbox.path(self.ledger.root, cid, 'handoff').exists())
        mailbox.bind_turn(self.ledger, cid, brain, self.turn, host=self.host)
        profile = inspection.resume_profile(self.binding, brain, cid,
            {'sandbox': {'type': 'workspaceWrite'}, 'approvalPolicy': 'on-request', 'approvalsReviewer': 'user'})
        profile['nativeTurnId'] = self.turn
        from orchestrator.native_policy_evidence import collect
        proxy = SimpleNamespace(_rpc=lambda *_: response(brain, str(self.repo)))
        effective = collect(proxy, self.binding, brain, cid)
        effective['nativeTurnId'] = self.turn
        with self.ledger.tx() as db:
            c = self.ledger.get(db, 'commands', cid)
            c['notification'].update(nativeResumeProfile=profile, nativeEffectivePolicy=effective,
                nativePolicyContract=POLICY.copy(), nativePolicyExecutableHash='c'*64,
                nativeTaskContract=BACKEND.copy(),
                nativeThreadObservation={'rootThreadId': brain, 'streamStatus': 'open'})
            self.ledger.put(db, 'commands', cid, c)
        return {'status': 'accepted', 'nativeDelivery': 'owned_turn_start', 'nativeTurnId': self.turn}

    def write_usage(self, total=300, worker=None):
        folder = self.home / 'sessions'
        folder.mkdir(exist_ok=True)
        now = time.time() - .001
        start = self.run['startedAt']
        ident = worker or self.brain
        vector = lambda n: {'input_tokens': n, 'cached_input_tokens': 0, 'output_tokens': 0,
                            'reasoning_output_tokens': 0, 'total_tokens': n}
        rows = [{'type': 'session_meta', 'timestamp': dt.datetime.fromtimestamp(start-10, dt.timezone.utc).isoformat(),
                 'payload': {'id': ident, 'cwd': str(self.repo)}}]
        samples = [(now, total, total)] if worker else [(start-1, 100, 100), (now, total, total-100)]
        for at, count, delta in samples:
            rows.append({'type': 'event_msg', 'timestamp': dt.datetime.fromtimestamp(at, dt.timezone.utc).isoformat(),
                'payload': {'type': 'token_count', 'info': {'total_token_usage': vector(count), 'last_token_usage': vector(delta)}}})
        (folder / ('rollout-' + ident + '.jsonl')).write_text('\n'.join(json.dumps(r) for r in rows)+'\n')

    def publish(self, operation, payload=None, sequence=None):
        sequence = sequence or self.sequence + 1
        call = {'sequence': sequence, 'operation': operation, 'payload': payload or {}}
        file = self.ledger.root / ('call-' + str(sequence) + '.json')
        if not file.exists(): inspection._write_once(file, call)
        # Keep the two exact deadline reads local to the mailbox under test;
        # another fixture's observer thread must retain the real process clock.
        with patch.object(mailbox, 'time', wraps=time) as clock:
            clock.monotonic.side_effect = [0, 31]
            result = mailbox.submit(self.handoff, file)
        self.calls[sequence] = file
        return result

    def call(self, operation, payload=None):
        sequence = self.sequence + 1
        self.publish(operation, payload, sequence)
        mailbox.service(self.host, self.cid, self.brain, self.turn, sequence)
        result = mailbox.status(self.handoff, sequence)
        self.assertEqual(result['status'], 'completed', result)
        self.sequence = sequence
        return result['result']

    def proof(self):
        with standard.read_db(self.ledger.db) as db:
            return fingerprint(db)

    def mutate(self, fn):
        with self.ledger.tx() as db:
            m = self.ledger.get(db, 'meta', 1)
            fn(m)
            self.ledger.put(db, 'meta', 1, m)

    def begin(self):
        self.call('acquire')
        self.call('receive')
        self.call('usage')

    def claim(self):
        return self.call('journal', {'operation': 'claim', 'id': 'task-1', 'repository': 'a',
            'title': 'Offline fixture', 'paths': ['tests/test_fixture.py'],
            'instructions': 'Implement only the offline fixture; no network or descendants.',
            'acceptance': ['Offline unit test passes'], 'model': 'fixture', 'effort': 'low',
            'rationale': 'Small independently scoped task', 'allowance': 10000})

    def test_future_notification_is_prospective_and_does_not_grant_shared_access(self):
        value = mailbox.handoff(self.handoff)
        self.assertIn('--run-handoff', self.sent[0])
        self.assertNotIn('platform '+str(self.registry.root), self.sent[0])
        for secret in ('endpoint', 'token', str(self.registry.root)):
            self.assertNotIn(secret, canonical(value))
        with self.assertRaisesRegex(Refusal, 'historical'):
            with self.ledger.tx() as db:
                mailbox.prepare(self.ledger, db, self.ledger.get(db, 'commands', self.cid), self.binding)
        self.assertIsNone(self.ledger.snapshot()['meta']['controller'])

    def test_explicit_control_receipt_usage_claim_seed_checkpoint_release(self):
        original = copy.deepcopy(self.run)
        self.assertEqual(self.call('state')['run']['id'], self.run_id)
        self.begin()
        self.assertEqual(next(c for c in self.ledger.snapshot()['commands'] if c['id']==self.cid)['status'], 'completed')
        result = self.claim()
        self.assertEqual(result['run']['tasks'][0]['status'], 'claimed')
        seed = self.call('seed', {'taskId': 'task-1'})
        self.assertEqual(seed['runId'], self.run_id)
        self.call('journal', {'operation': 'cancel_unissued', 'taskId': 'task-1'})
        self.call('journal', {'operation': 'checkpoint', 'outcome': 'blocked',
            'summary': 'Fixture ends without a native task, explicitly unqualified', 'brainObservedTokens': None})
        self.assertTrue(self.call('release', {'summary': 'Fixture checkpoint retained'})['released'])
        run = standard.read(self.ledger)['run']
        for key in ('id', 'startedAt', 'expiresAt', 'ownerReceipt', 'limits', 'brainAllowance'):
            self.assertEqual(run[key], original[key])
        self.assertEqual(run['usageHighWater'], 200)
        self.assertIsNone(self.ledger.snapshot()['meta']['controller'])
        self.assertFalse((self.ledger.root/'standard-controller.json').exists())
        for seq in range(1, self.sequence+1):
            raw = canonical(mailbox.status(self.handoff, seq))
            self.assertNotIn('"token"', raw)
        self.assertFalse(mailbox.status(self.handoff, self.sequence)['continuationAllowed'])

    def test_no_request_does_not_acquire_collect_or_send(self):
        before = self.proof()
        with patch.object(mailbox, '_context', side_effect=AssertionError('No implicit collection')):
            mailbox.service(self.host, self.cid, self.brain, self.turn, 1)
            mailbox.service_pending(self.host, SimpleNamespace(), self.cid, self.brain, self.turn)
        self.assertEqual(self.proof(), before)

    def test_early_call_waits_for_original_delivery_ack_without_claim(self):
        self.publish('acquire')
        with self.ledger.tx() as db:
            c=self.ledger.get(db,'commands',self.cid)
            c['notification']['status']='sending'
            self.ledger.put(db,'commands',self.cid,c)
        mailbox.service_pending(self.host,SimpleNamespace(),self.cid,self.brain,self.turn)
        self.assertFalse(mailbox.path(self.ledger.root,self.cid,'claim',1).exists())
        self.assertIsNone(self.ledger.snapshot()['meta']['controller'])

    def test_run_receipt_does_not_drain_unrelated_saved_message(self):
        message={'id':str(uuid.uuid4()),'kind':'reconcile','actor':'dashboard','status':'queued',
                 'createdAt':time.time(),'payload':{'message':'Unrelated saved question',
                 'brainId':self.brain,'confirmed':True}}
        with self.ledger.tx() as db:self.ledger.put(db,'commands',message['id'],message)
        self.call('acquire');self.call('receive')
        with standard.read_db(self.ledger.db) as db:
            self.assertEqual(self.ledger.get(db,'commands',message['id']),message)
            self.assertEqual(self.ledger.get(db,'commands',self.cid)['status'],'completed')

    def test_identical_client_repetition_only_reads_the_original_receipt(self):
        self.call('acquire')
        before = self.proof()
        with patch.object(mailbox.time, 'monotonic', side_effect=[0, 31]):
            self.assertEqual(mailbox.submit(self.handoff, self.calls[1]), mailbox.status(self.handoff, 1))
        mailbox.service(self.host, self.cid, self.brain, self.turn, 1)
        self.assertEqual(self.proof(), before)

    def test_interrupted_claim_blocks_every_later_sequence_without_reapply(self):
        self.publish('acquire')
        inspection._write_once(mailbox.path(self.ledger.root, self.cid, 'claim', 1), {'interrupted': True})
        before = self.proof()
        mailbox.service(self.host, self.cid, self.brain, self.turn, 1)
        self.assertEqual(mailbox.status(self.handoff, 1)['status'], 'claimed_outcome_unknown')
        with self.assertRaisesRegex(Refusal, 'never advance'):
            self.publish('state', sequence=2)
        self.assertEqual(self.proof(), before)

    def test_forged_client_reply_cannot_skip_an_unknown_operation(self):
        self.publish('acquire')
        original = inspection._read_private(mailbox.path(self.ledger.root, self.cid, 'request', 1))
        inspection._write_once(mailbox.path(self.ledger.root, self.cid, 'claim', 1), {'requestHash': digest(original)})
        inspection._write_once(mailbox.path(self.ledger.root, self.cid, 'reply', 1), {
            'requestHash': digest(original), 'status': 'completed', 'result': {},
            'continuationAllowed': True, 'boundary': mailbox.BOUNDARY, 'seal': '0'*64})
        self.publish('acquire', sequence=2)
        before=self.proof()
        mailbox.service(self.host,self.cid,self.brain,self.turn,2)
        self.assertEqual(mailbox.status(self.handoff,2)['status'],'unavailable')
        self.assertEqual(self.proof(),before)

    def test_expired_budget_and_ended_observer_do_not_become_new_authority(self):
        self.begin()
        self.mutate(lambda m: m['standardRun'].update(expiresAt=time.time()-1))
        self.publish('journal', {'operation': 'claim', 'id': 'task-1'})
        mailbox.service(self.host,self.cid,self.brain,self.turn,self.sequence+1)
        self.assertEqual(mailbox.status(self.handoff,self.sequence+1)['status'],'unavailable')
        self.assertEqual(standard.read(self.ledger)['run']['tasks'],[])

    def test_new_process_without_original_session_cannot_service_saved_requests(self):
        self.publish('acquire')
        self.host._run_control_keys.clear()
        before=self.proof()
        with self.assertRaises(Refusal):
            mailbox.service(self.host,self.cid,self.brain,self.turn,1)
        self.assertEqual(self.proof(),before)
        self.assertEqual(mailbox.status(self.handoff,1)['status'],'claimed_outcome_unknown')

    def test_changed_source_binding_and_closed_observer_fence_service(self):
        self.publish('acquire')
        self.host.binding=copy.deepcopy(self.binding)
        self.host.binding['endpoint']['sha256']='e'*64
        mailbox.service(self.host,self.cid,self.brain,self.turn,1)
        self.assertEqual(mailbox.status(self.handoff,1)['status'],'unavailable')
        self.assertIsNone(self.ledger.snapshot()['meta']['controller'])

    def test_closed_observer_at_write_boundary_rolls_back_controller(self):
        self.publish('acquire')
        original=mailbox._ObserverLedger._guard
        count=[]
        def close_after_write(scoped, db):
            count.append(1)
            if len(count)==2:
                self.host._closed=True
            return original(scoped,db)
        with patch.object(mailbox._ObserverLedger,'_guard',close_after_write):
            mailbox.service(self.host,self.cid,self.brain,self.turn,1)
        self.assertEqual(mailbox.status(self.handoff,1)['status'],'unavailable')
        self.assertIsNone(self.ledger.snapshot()['meta']['controller'])

    def test_ended_observer_and_changed_source_refuse_before_effect(self):
        for changed in ('ended','source'):
            with self.subTest(changed=changed):
                if changed=='ended':
                    with self.ledger.tx() as db:
                        c=self.ledger.get(db,'commands',self.cid)
                        c['notification']['nativeTurnStatus']='completed'
                        self.ledger.put(db,'commands',self.cid,c)
                    self.publish('acquire')
                    mailbox.service(self.host,self.cid,self.brain,self.turn,1)
                    self.assertEqual(mailbox.status(self.handoff,1)['status'],'unavailable')
                else:
                    with patch.object(mailbox,'source_hash',return_value='0'*64):
                        with self.assertRaises(Refusal):mailbox.handoff(self.handoff)
                self.assertIsNone(self.ledger.snapshot()['meta']['controller'])

    def test_same_sequence_concurrency_has_one_controller_claim(self):
        self.publish('acquire')
        threads=[threading.Thread(target=mailbox.service,args=(self.host,self.cid,self.brain,self.turn,1)) for _ in range(4)]
        for t in threads:t.start()
        for t in threads:t.join(5)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(mailbox.status(self.handoff,1)['status'],'completed')
        events=[e for e in self.ledger.snapshot()['events'] if e['kind']=='standard_controller_acquired']
        self.assertEqual(len(events),1)

    def test_invalid_operation_cannot_expose_arbitrary_commands_permissions_or_bindings(self):
        for op in ('rpc', 'exec', 'approve', 'cancel', 'reload', 'replay', 'play', 'resume', 'merge', 'recover'):
            with self.subTest(op=op):
                file = self.ledger.root / (op+'.json')
                inspection._write_once(file, {'sequence': 1, 'operation': op, 'payload': {}})
                with self.assertRaises(Refusal): mailbox.submit(self.handoff, file)
        self.call('acquire')
        self.publish('journal', {'operation': 'issue', 'taskId': 'task-1'})
        mailbox.service(self.host, self.cid, self.brain, self.turn, 2)
        self.assertEqual(mailbox.status(self.handoff, 2)['status'], 'unavailable')

    def test_pending_permission_cannot_be_accepted_cancelled_or_bypassed(self):
        self.host.pending_approval = lambda _: {'held': True}
        self.call('state')
        self.publish('acquire')
        before = self.proof()
        mailbox.service(self.host, self.cid, self.brain, self.turn, 2)
        self.assertEqual(mailbox.status(self.handoff, 2)['status'], 'unavailable')
        self.assertEqual(self.proof(), before)

    def test_queued_owner_response_stays_fenced_until_original_observer_consumes_it(self):
        from orchestrator.app_server_wake import AppServerWake
        host=AppServerWake(self.binding,self.ledger)
        host._pending_approvals[self.brain]={'decision':'cancel'}
        with patch.object(host,'pending_approval',side_effect=AssertionError('No DB-backed UI projection in a write')):
            self.assertTrue(mailbox._permission_held(host,self.brain))
        del host._pending_approvals[self.brain]
        self.assertFalse(mailbox._permission_held(host,self.brain))

    def test_changed_turn_binding_owner_source_and_ended_observer_fail_closed(self):
        self.publish('acquire')
        self.mutate(lambda m: m.update(brainId=str(uuid.uuid4())))
        mailbox.service(self.host, self.cid, self.brain, self.turn, 1)
        self.assertEqual(mailbox.status(self.handoff, 1)['status'], 'unavailable')
        self.assertIsNone(self.ledger.snapshot()['meta']['controller'])

    def test_pause_between_brain_request_and_claim_prevents_task(self):
        self.begin()
        self.publish('journal', {'operation': 'claim', 'id': 'task-1', 'repository': 'a',
            'title': 'Fixture', 'paths': ['tests/test_fixture.py'], 'instructions': 'Offline only',
            'acceptance': ['Tests'], 'model': 'fixture', 'effort': 'low', 'rationale': 'Bounded', 'allowance': 1000})
        self.mutate(lambda m: m['standardRun'].update(status='stopping'))
        mailbox.service(self.host, self.cid, self.brain, self.turn, self.sequence+1)
        self.assertEqual(mailbox.status(self.handoff, self.sequence+1)['status'], 'unavailable')
        self.assertEqual(standard.read(self.ledger)['run']['tasks'], [])

    def test_missing_usage_is_not_zero_and_fences_claim(self):
        self.call('acquire'); self.call('receive')
        self.publish('journal', {'operation': 'claim', 'id': 'task-1'})
        mailbox.service(self.host, self.cid, self.brain, self.turn, self.sequence+1)
        self.assertEqual(mailbox.status(self.handoff, self.sequence+1)['status'], 'unavailable')
        self.assertEqual(standard.read(self.ledger)['run']['brainUsageCoverage'], 'not_observed')

    def test_existing_held_play_assessment_never_attaches_backfills_or_responds(self):
        with self.ledger.tx() as db:
            c=self.ledger.get(db,'commands',self.cid)
            c['notification'].pop('runControl')
            self.ledger.put(db,'commands',self.cid,c)
        before = self.proof()
        result = mailbox.continuation(self.ledger, self.cid)
        self.assertEqual(result['status'], 'held_original_requires_owner_resolution')
        self.assertEqual(result['actionsTaken'], [])
        self.assertFalse(result['prospectiveMailbox'])
        self.assertEqual(before, self.proof())

    def test_client_never_opens_databases_registry_or_sockets(self):
        with (patch('sqlite3.connect', side_effect=AssertionError('No SQLite')),
              patch('socket.socket', side_effect=AssertionError('No socket'))):
            self.publish('state')
            self.assertEqual(mailbox.status(self.handoff, 1)['status'], 'waiting_for_original_observer')

    def test_read_only_cli_preserves_logical_data_and_file_permissions(self):
        paths = [self.registry.db, self.ledger.db]
        before = self.proof()
        permissions = {str(p): p.stat().st_mode for p in paths}
        run = subprocess.run([sys.executable, '-B', '-m', 'orchestrator.cli', '--platform', str(self.registry.root),
            '--workspace', 'v3', 'standard-state'], cwd=mailbox.SOURCE, capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['run']['id'], self.run_id)
        self.assertEqual(before, self.proof())
        self.assertEqual(permissions, {str(p): p.stat().st_mode for p in paths})
        with self.assertRaises(Refusal):
            with Ledger(self.ledger.root, read_only=True).tx(): pass
        with self.assertRaises(sqlite3.OperationalError):
            with Registry(self.registry.root, read_only=True).tx() as db:
                db.execute('DELETE FROM workspaces')

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('sandbox-exec'), 'Requires macOS sandbox')
    def test_actual_sandbox_call_with_registry_sqlite_and_network_access_denied(self):
        profile = ('(version 1)(allow default)(deny network*)(deny file-write* (subpath '+json.dumps(str(self.registry.root))+'))'
                   '(deny file-read* (subpath '+json.dumps(str(self.registry.root))+'))'
                   '(deny file-read* (regex #".*[.]sqlite3(-wal|-shm)?$"))'
                   '(deny file-write* (regex #".*[.]sqlite3(-wal|-shm)?$"))'
                   '(deny file-write* (subpath '+json.dumps(str(mailbox.SOURCE))+'))')
        operations=[('state',{}),('acquire',{}),('receive',{}),('usage',{}),
            ('journal',{'operation':'claim','id':'task-1','repository':'a','title':'Sandbox fixture',
                'paths':['tests/test_fixture.py'],'instructions':'Offline fixture only',
                'acceptance':['Tests'],'model':'fixture','effort':'low','rationale':'Bounded','allowance':1000}),
            ('seed',{'taskId':'task-1'}),('journal',{'operation':'cancel_unissued','taskId':'task-1'}),
            ('journal',{'operation':'checkpoint','outcome':'blocked',
                'summary':'Disposable sandbox fixture, no native worker and explicitly unqualified','brainObservedTokens':None}),
            ('release',{'summary':'Disposable checkpoint retained; terminal safety unknown'})]
        stop=threading.Event()
        proxy=SimpleNamespace()
        def service():
            while not stop.wait(.02):
                mailbox.service_pending(self.host,proxy,self.cid,self.brain,self.turn)
        thread=threading.Thread(target=service); thread.start()
        try:
            for sequence,(operation,payload) in enumerate(operations,1):
                call=self.ledger.root/('sandbox-call-'+str(sequence)+'.json')
                inspection._write_once(call,{'sequence':sequence,'operation':operation,'payload':payload})
                run=subprocess.run([shutil.which('sandbox-exec'),'-p',profile,sys.executable,'-B','-m','orchestrator.cli',
                    '--run-handoff',str(self.handoff),'standard-run-call',str(call)],cwd=self.repo,
                    env={**os.environ,'PYTHONPATH':str(mailbox.SOURCE)},capture_output=True,text=True,timeout=40)
                self.assertEqual(run.returncode,0,run.stderr)
                self.assertEqual(json.loads(run.stdout)['status'],'completed',run.stdout)
        finally:
            stop.set();thread.join(5)
        self.assertFalse(thread.is_alive())
        run=standard.read(self.ledger)['run']
        self.assertEqual(run['usageHighWater'],200)
        for key in ('id','startedAt','expiresAt','ownerReceipt','limits'):
            self.assertEqual(run[key],self.run[key])
        self.assertIsNone(self.ledger.snapshot()['meta']['controller'])
        self.assertEqual(len(self.sent),1)


if __name__ == '__main__':
    unittest.main()
