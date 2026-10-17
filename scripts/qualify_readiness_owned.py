"""Disposable Unix-host lifecycle fixture, with a labelled synthetic IPC ack.

The native load, policy/schema reads, turn, original observer and close are real.
Only the model/provider and designated-brain mailbox publication are simulated.
This is not live pilot, account entitlement or model/tool compliance evidence.
"""
import time
import uuid

from orchestrator import missions, readiness_owned as owned, standard, standard_preplay as preplay
from orchestrator.app_server_wake import AppServerWake, NATIVE_APPROVAL_POLICY
from orchestrator.core import Ledger, digest, require
from orchestrator.notification import BrainNotifier
from orchestrator.workspaces import Registry


class Fixture:
    def __init__(self,endpoint,brain,project,cwd):
        registry=Registry(cwd.parent/'readiness-registry',create=True)
        ledger=Ledger(cwd/'.state')
        ledger.initialize({'schemaVersion':1,'brainId':brain,'repositories':[{'id':'fixture','path':str(cwd),
            'projectId':'projectless','ref':'HEAD','policyProfile':'standard','mergePolicy':'manual'}]})
        registry.register('ready','Disposable readiness',ledger.root)
        self.registry,self.ledger=registry,registry.ledger('ready')
        spec={'goal':'Disposable readiness fixture','successCriteria':['Observe exact readiness receipt'],
            'exclusions':['No live hosts or providers'], 'phase':{'id':'fixture','title':'Disposable','objective':'Fixture only',
                'checkpoint':'Stop after receipt','stopConditions':['Any drift'],
                'scope':[{'repository':'fixture','allowedPaths':['fixture.txt'],'operations':['edit','test']} ]},
            'authority':{'approvalMode':'phase_delegated','maxParallelTasks':1,'maxTasks':1,
                'tokenBudget':100000,'checkpointReserveTokens':10000}}
        current=missions.change(self.ledger,{'id':str(uuid.uuid4()),'operation':'save','expectedRevision':0,'spec':spec})['current']
        missions.change(self.ledger,{'id':str(uuid.uuid4()),'operation':'review','expectedRevision':current['revision'],
            'documentHash':current['documentHash'],'confirmed':True})
        # Deliberately synthetic source-build pins. The executable hash/socket
        # are real fixture pins; none of this is a live binding qualification.
        contract={'protocol':'public_app_server_tasks_v1','sourceCommit':'a'*40,'sourceTree':'b'*40,
            'trust':'operator_reviewed_build_v1','desktopBridge':'absent','repositoryMode':'repo_exclusive'}
        self.binding={'endpoint':endpoint,'brains':{brain:{'cwd':str(cwd),'projectId':project,
            'catalogProjectId':str(uuid.uuid4()),'workspaceId':'ready','nativePolicy':dict(NATIVE_APPROVAL_POLICY),
            'nativeTaskBackend':contract,'policyEvidence':{'protocol':'loaded_thread_policy_v1',
                'sourceCommit':'a'*40,'sourceTree':'b'*40}}}}
        self.brain=brain; self.cid=str(uuid.uuid4()); self.ack_published=False
        self.wake=AppServerWake(self.binding,self.ledger)
        self.notifier=BrainNotifier(self.ledger); self.notifier.app_server=self.wake

    def provider_ack(self):
        """Simulate only the fixture brain's closed checkout-local result."""
        deadline=time.monotonic()+20
        while True:
            with standard.read_db(self.ledger.db) as db:
                c=self.ledger.get(db,'commands',self.cid)
            if (c.get('notification') or {}).get('status') == 'accepted': break
            require(time.monotonic()<deadline,'Fixture notification did not reach accepted state')
            time.sleep(.05)
        file=preplay.path(self.ledger.root,self.cid,'handoff')
        value=preplay.state(file); handoff=preplay.handoff(file)
        preplay._write_once(preplay.path(self.ledger.root,self.cid,'request'),{'version':1,
            'handoffHash':digest(handoff),'result':{'operation':'public_catalog_ack','requestId':self.cid,
            'evidenceHash':value['publicReadiness']['evidenceHash']}})
        while preplay.status(file)['status'] != 'completed':
            require(time.monotonic()<deadline,'Original fixture observer did not retain its receipt')
            time.sleep(.05)
        self.ack_published=True

    def run(self):
        review=owned.prepare(self.registry,self.ledger,self.binding,self.cid)
        require(review['before']['activity']=='notLoaded','Fixture must begin unloaded')
        owned.confirm(self.registry,self.ledger,self.binding,review)
        self.notifier.notify(self.cid)
        deadline=time.monotonic()+30
        try:
            while True:
                with standard.read_db(self.ledger.db) as db: c=self.ledger.get(db,'commands',self.cid)
                if c.get('notification',{}).get('nativeThreadObservation',{}).get('streamStatus')=='closed': break
                require(time.monotonic()<deadline,'Fixture turn/observer did not close')
                time.sleep(.05)
            require(c['status']=='completed' and c['notification']['nativeTurnStatus']=='completed' and self.ack_published,
                    'Exact fixture native completion and independent catalog receipt required')
            state=standard.read(self.ledger)
            from orchestrator.public_readiness import retained_catalog
            retained_catalog(state['catalog'],c,self.binding)
            close=owned.record(owned.journal(self.ledger,self.cid,'close'))
            require(close['connectionClosed'] and close['reconnectAllowed'] is False and
                    close['nativeTurnId']==c['notification']['nativeTurnId'],'Original fixture connection close required')
            return {'readinessLoads':1,'readinessTurns':1,'originalObserverReceipt':True,'connectionClosed':True,
                'oneConnectionOwnsLoadCaptureAndTurn':True,'inspectionLoads':0,'replays':0,
                'catalogModelsObserved':len(state['catalog']['models']),'actualRestrictedPolicyObserved':True,
                'mailboxAckSource':'synthetic_fixture_not_model_tool_execution','fixtureSourcePinsAreSynthetic':True,
                'liveBindingQualified':False,'modelEntitlementVerified':False,'terminalSafety':'unknown','pilotAccepted':False}
        finally:
            self.wake.close()
