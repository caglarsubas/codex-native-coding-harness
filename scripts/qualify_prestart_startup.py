"""Actual disposable new startup; original failure and mailbox ack are synthetic."""
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

from qualify_readiness_owned import Fixture as ReadinessFixture
from orchestrator import prestart_startup as startup, startup_mailbox as mailbox, projects
from orchestrator import readiness_owned as owned, standard, standard_preplay as preplay
from orchestrator.app_server_wake import WakeProxy
from orchestrator.core import canonical, require
from orchestrator.native_read_client import NativeReadFailure
from orchestrator.public_pilot_inspection import exclusive


class Fixture(ReadinessFixture):
    def __init__(self,endpoint,brain,project,cwd):
        super().__init__(endpoint,brain,project,cwd)
        subprocess.run(['/usr/bin/git','-C',str(cwd),'-c','user.name=Fixture','-c',
            'user.email=fixture@localhost','commit','--allow-empty','-qm','disposable startup'],
            check=True,capture_output=True)
        native=self.binding['brains'][brain]['catalogProjectId']
        projects.record(self.registry,{'schemaVersion':2,'projects':[{'projectId':native,
            'projectKind':'local','hostId':'local','label':'Synthetic app catalog mapping',
            'path':str(cwd),'isGitRepository':True}]},time.time())
        projects.bind(self.registry,'ready','local',native,projects.catalog(self.registry)['hash'])
        self.binding_file=cwd.parent/'startup-binding.json'; exclusive(self.binding_file,self.binding)

    def provider_ack(self):
        """Only publication is simulated; native load, policy and turn are real."""
        box=Path(self.q['request']['mailbox']); deadline=time.monotonic()+30
        while not (box/'turn.json').exists():
            require(time.monotonic()<deadline,'New startup turn was not acknowledged'); time.sleep(.02)
        value=mailbox.state(box/'handoff.json')['resultSchema']
        value['proposal']={'objective':'Disposable inert pilot proposal','steps':['Review new phase'],
            'checks':['Check exact native policy'],'stoppingCheckpoint':'Stop before worker Play'}
        exclusive(box/'fixture-result.json',value)
        # Execute the real standalone helper in isolated Python from the target
        # checkout. No controller import, SQL, socket or installed-skill route.
        result=subprocess.run(['python3','-I','-B',str(Path(mailbox.__file__)),
            '--handoff',str(box/'handoff.json'),'complete',str(box/'fixture-result.json')],
            cwd=self.binding['brains'][self.brain]['cwd'],capture_output=True,timeout=10)
        require(result.returncode==0,'Standalone sandbox result helper refused')
        self.ack_published=True

    def run(self):
        q=owned.prepare(self.registry,self.ledger,self.binding,self.cid)
        owned.confirm(self.registry,self.ledger,self.binding,q)
        original_rpc=WakeProxy._rpc
        def deadline(proxy,method,params):
            if method=='account/read':
                raise NativeReadFailure('deadline_exceeded','Synthetic qualification-only original pre-load failure')
            return original_rpc(proxy,method,params)
        with patch.object(WakeProxy,'_rpc',deadline): self.notifier.notify(self.cid)
        with standard.read_db(self.ledger.db) as db: original=self.ledger.get(db,'commands',self.cid)
        require(original['notification']['nativeFailure']=={'version':1,'stage':'authentication_check',
            'reason':'deadline_exceeded','resumeAttempted':False,'turnStartAttempted':False},
            'Fixture must reproduce only the positive supported original failure')
        before=startup.databases(self.registry)
        self.q=startup.prepare(self.registry,self.ledger,self.binding_file,self.cid,preplay.SOURCE)
        backup=self.ledger.root.parent.parent/'startup-private-backup'
        startup.backup(self.registry,self.ledger,self.q['request'],backup,writers_stopped=True)
        s=startup.confirm(self.registry,self.ledger,self.q['request'],self.q['reviewHash'],
            backup_root=backup,writers_stopped=True)
        require(s['status']=='startup_preparation_completed' and s['newReceiptRecorded'] and self.ack_published,
            'Distinct startup receipt and native completion required: '+canonical(s))
        require(startup.databases(self.registry)==before,'Original fixture databases changed')
        with standard.read_db(self.ledger.db) as db:
            require(self.ledger.get(db,'commands',self.cid)==original,'Original readiness request changed')
        outcome=mailbox.read(Path(self.q['request']['journal'])/'outcome.json')
        require(outcome['connectionClosed'] and outcome['reconnectAllowed'] is False and
            not (self.ledger.root/('preplay-catalog-'+self.cid+'-reply.json')).exists(),
            'Original connection close and no old catalog receipt required')
        return {'newStartupLoads':1,'newStartupTurns':1,'newPurpose':'new_startup_preparation',
            'restrictedLoadedPolicyObserved':True,'oneConnectionOwnsLoadTurnAndReceipt':True,
            'oldDatabasesAndRequestPreserved':True,'readinessReplays':0,'playOrRecoveryReplays':0,
            'originalFailureSource':'synthetic_injected_preload_deadline',
            'mailboxAckSource':'synthetic_fixture_not_model_tool_compliance',
            'standaloneHelperInvoked':True,'fixtureCatalogAndBuildPinsSynthetic':True,
            'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','pilotAccepted':False}
