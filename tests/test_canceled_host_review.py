"""Launch-review fixtures; no credentials opened, native socket or real exec."""
import copy
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from orchestrator import canceled_host_review as api, canceled_play, public_host_lifecycle as launch
from orchestrator.core import Refusal, digest
from orchestrator.partial_admission import database_proof
import test_canceled_play as canceled
import test_standard_run_mailbox as mailbox
from test_public_host_runtime import package_fixture, macho


class CanceledHostTest(unittest.TestCase):
    def setUp(self):
        original=mailbox.RunMailboxTest.setUp
        def setup(f):
            original(f)
            package=package_fixture(f.root/'old-package')
            f.home=f.root/'native-home'; f.home.mkdir(mode=0o700)
            (f.home/'config.toml').write_text(launch.CONFIG); (f.home/'config.toml').chmod(0o600)
            sockets=f.root/'old-ipc'; sockets.mkdir(mode=0o700)
            f.launch=launch.setup_scope(package['root'],f.repo,f.home,sockets)
            for name,raw in (('state_5.sqlite',b'opaque fixture state'),
                             ('auth.json',b'FAKE_CREDENTIAL_NEVER_READ')):
                (f.home/name).write_bytes(raw); (f.home/name).chmod(0o600)
            history=f.home/'sessions'; history.mkdir(mode=0o700)
            (history/('rollout-'+f.brain+'.jsonl')).write_bytes(b'opaque fixture history')
            (history/('rollout-'+f.brain+'.jsonl')).chmod(0o600)
            f.binding['endpoint'].update(executable=str(Path(package['root'])/'bin/codex'),sha256=package['executableHash'])
        with patch.object(mailbox.RunMailboxTest,'setUp',setup):
            self.old=canceled.CanceledPlayTest('runTest'); self.old.setUp()
        self.addCleanup(self.old.doCleanups); self.f=self.old.f
        self.registry,self.ledger=self.old.registry,self.old.ledger
        self.previous=self.f.root/'issued-old'; self.previous.mkdir(mode=0o700)
        self.state={'pid':123456789,'processIdentity':'123456789 fixture','specHash':digest(self.f.launch)}
        issued=(self.f.launch,self.state,[],str(self.old.binding_file),[self.f.launch['socketDirectory']],[str(self.previous)],[])
        p=patch.object(api.lineage,'issued',return_value=issued); p.start(); self.addCleanup(p.stop)
        p=patch.object(api.shared,'quiescent'); self.quiet=p.start(); self.addCleanup(p.stop)
        p=patch.object(api.shared,'source_tree',return_value='a'*40); p.start(); self.addCleanup(p.stop)
        p=patch('socket.socket',side_effect=AssertionError('No native connection')); p.start(); self.addCleanup(p.stop)
        self.package=package_fixture(self.f.root/'new-package',macho()+b'distinct subscribe build')
        self.sockets=self.f.root/'new-ipc'; self.sockets.mkdir(mode=0o700)
        self.directory=self.f.root/'replacement'; self.file=self.directory/'replacement.json'
        self.before=[database_proof(p) for p in (self.registry.db,self.ledger.db)]
        self.sidecars=canceled_play.sidecars(self.ledger); self.binding_pin=canceled_play.prior.file_epoch(self.old.binding_file)

    def prepare(self):
        return api.prepare(self.registry,self.ledger,self.previous,self.old.binding_file,self.old.cid,
            self.package['root'],self.sockets,self.directory)

    def conserved(self):
        self.assertEqual(self.before,[database_proof(p) for p in (self.registry.db,self.ledger.db)])
        self.assertEqual(self.sidecars,canceled_play.sidecars(self.ledger))
        self.assertEqual(self.binding_pin,canceled_play.prior.file_epoch(self.old.binding_file))

    def test_private_backup_never_reads_or_copies_credentials_and_review_has_no_timer(self):
        real=Path.open
        def guarded(path,*a,**kw):
            self.assertNotEqual(path,self.f.home/'auth.json'); return real(path,*a,**kw)
        with patch.object(Path,'open',guarded): report=self.prepare()
        self.assertFalse((self.directory/'native-home-backup/auth.json').exists())
        self.assertFalse(report['startsHost']); self.assertEqual(report['boundary'],api.BOUNDARY)
        with patch('time.time',return_value=time.time()+999999):
            self.assertEqual(api.preview(self.registry,self.ledger,self.file)['reviewHash'],report['reviewHash'])
        self.assertEqual(api.status(self.file)['status'],'prepared_not_submitted'); self.conserved()

    def test_wrong_hash_cannot_claim_or_launch(self):
        self.prepare()
        with patch.object(api.os,'execve') as execute,self.assertRaises(Refusal):
            api.execute(self.registry,self.ledger,self.file,'f'*64)
        execute.assert_not_called(); self.conserved()

    def test_exact_claim_before_one_exec_failure_cannot_be_retried_or_reset(self):
        report=self.prepare(); q=api.load(self.file)
        def failed(binary,argv,env):
            self.assertTrue((Path(q['fencePath'])/'exec.claim.json').exists())
            self.assertEqual(argv,[binary,'app-server','--listen','unix://'+str(self.sockets/'host.sock')])
            self.assertEqual(env['CODEX_HOME'],str(self.f.home)); raise OSError('fixture')
        with patch.object(api.sys,'platform','darwin'),patch.object(api.platform,'machine',return_value='arm64'),\
             patch.object(api.os,'chdir'),patch.object(api.os,'dup2'),patch.object(api.os,'execve',side_effect=failed) as execute:
            with self.assertRaises(Refusal): api.execute(self.registry,self.ledger,self.file,report['reviewHash'])
            with self.assertRaises(Refusal): api.execute(self.registry,self.ledger,self.file,report['reviewHash'])
        self.assertEqual(execute.call_count,1)
        self.assertEqual(api.status(self.file)['status'],'launch_claimed_outcome_unknown')
        self.directory=self.f.root/'different-review'
        with self.assertRaises(Refusal): self.prepare()
        self.conserved()

    def test_home_backup_credential_epoch_and_new_package_drift_refuse(self):
        self.prepare(); os.utime(self.f.home/'auth.json',None)
        with self.assertRaises(Refusal): api.validate(self.registry,self.ledger,self.file)
        self.conserved()

    def test_archive_mutation_refuses(self):
        self.prepare(); (self.directory/'native-home-backup/state_5.sqlite').write_bytes(b'changed')
        with self.assertRaises(Refusal): api.validate(self.registry,self.ledger,self.file)
        self.conserved()

    def test_live_or_unknown_original_process_refuses_without_preparation(self):
        self.quiet.side_effect=Refusal('Process/home writer unknown')
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists()); self.conserved()

    def test_original_package_is_not_a_replacement_or_retry(self):
        self.package=self.f.launch['runtimePackage']
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists()); self.conserved()

    def test_crafted_archive_or_overlapping_socket_is_not_a_new_review(self):
        self.prepare(); q=api.load(self.file)
        for field,value in (('backupPath',str(self.f.home)),('socketDirectory',str(self.f.home)),
                            ('previousAttempt',str(self.directory))):
            changed=copy.deepcopy(q); changed[field]=value
            self.file.write_text(api.canonical(changed))
            with self.subTest(field=field),self.assertRaises(Refusal): api.validate(self.registry,self.ledger,self.file)
        self.conserved()

    def test_ordinary_pending_and_unknown_terminal_status_still_fail_closed(self):
        with self.ledger.tx() as db:
            c=self.ledger.get(db,'commands',self.old.cid); c['notification']['nativeTurnStatus']='unknown'
            self.ledger.put(db,'commands',self.old.cid,c)
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists())


if __name__=='__main__': unittest.main()
