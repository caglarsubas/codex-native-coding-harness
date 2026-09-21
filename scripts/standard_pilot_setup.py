"""Explicit disposable pilot setup; no task creation, remote calls or Play.

Requires two already seeded README-only repositories and two native brain IDs.
The caller supplies a new private output directory. Never target live state.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator.core import Ledger, require
from orchestrator.workspaces import Registry
from orchestrator.missions import change


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    p.add_argument('--alpha',required=True,type=Path);p.add_argument('--alpha-brain',required=True)
    p.add_argument('--beta',required=True,type=Path);p.add_argument('--beta-brain',required=True)
    p.add_argument('--confirm-disposable',action='store_true')
    a=p.parse_args()
    require(a.confirm_disposable,'Confirm disposable pilot scope')
    root=a.root.resolve();require(not root.exists(),'Use a new private pilot state directory')
    repos=[('alpha',a.alpha,a.alpha_brain),('beta',a.beta,a.beta_brain)]
    for _,repo,brain in repos:
        uuid.UUID(brain)
        files=subprocess.check_output(['git','-C',str(repo),'ls-files'],text=True).splitlines()
        require(files==['README.md'],'Pilot repository must contain only its seed README')
        require(not subprocess.check_output(['git','-C',str(repo),'remote'],text=True).strip(),'Pilot must have no remote')
        require(not subprocess.check_output(['git','-C',str(repo),'status','--porcelain'],text=True).strip(),'Pilot repository must be clean')
    registry=Registry(root/'platform',create=True)
    for wid,repo,brain in repos:
        ledger=Ledger(root/wid)
        fd=os.open(ledger.root/'observations.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as output:
            json.dump({'artifactRoots':[{'repository':wid,'path':str(repo.resolve())}]},output)
        ledger.initialize({'schemaVersion':1,'brainId':brain,'repositories':[{'id':wid,'path':str(repo.resolve()),
            'projectId':'projectless','ref':'main','mergePolicy':'manual','policyProfile':'standard'}]})
        registry.register(wid,'Disposable '+wid.title()+' pilot',ledger.root)
        ledger=registry.ledger(wid)
        feature='slug' if wid=='alpha' else 'statistics'
        goal=('Build a Unicode-safe slug function with whitespace/hyphen normalization' if wid=='alpha'
              else 'Build a numeric summary function returning count, sum and mean, with an explicit empty-input result')
        spec={'goal':goal,'successCriteria':['Local unittest suite passes','Implementation and tests independently reviewed','One local commit retained; no push'],
            'exclusions':['No network, paid services or GitHub Actions','No changes outside this disposable repository','No merge or archival'],
            'phase':{'id':'pilot-one','title':'Offline '+feature+' fixture','objective':goal,
                'checkpoint':'Stop after verified implementation; owner reviews before any further phase',
                'stopConditions':['Test failure requiring a scope change','Insufficient allowance','Owner Pause'],
                'scope':[{'repository':wid,'allowedPaths':[feature+'.py','test_'+feature+'.py','RESULT.md'], 'operations':['edit','test','commit']}]},
            'authority':{'approvalMode':'phase_delegated','maxParallelTasks':1,'maxTasks':2,'tokenBudget':120000,'checkpointReserveTokens':10000}}
        current=change(ledger,{'id':str(uuid.uuid4()),'operation':'save','expectedRevision':0,'spec':spec})['current']
        change(ledger,{'id':str(uuid.uuid4()),'operation':'review','expectedRevision':current['revision'],'documentHash':current['documentHash'],'confirmed':True})
        registry.save_profile(wid,{'goal':goal,'successCriteria':spec['successCriteria'],
            'architecture':'Single pure function and offline standard-library tests. Disposable local Git project.',
            'techStack':['Python standard library','unittest','Git'], 'roadmap':'One bounded implementation, independent verification, owner checkpoint.', 'references':[]},0)
    print(json.dumps({'platform':str(registry.root),'workspaces':['alpha','beta'],'playActivated':False}))


if __name__=='__main__':main()
