"""Checkout-local startup receipt/proposal IPC. Never opens SQL or a socket."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

# Deliberately standalone: the sandbox helper imports no ledger, registry,
# credential, native-client or socket implementation, even transitively.
SHA=re.compile(r'[a-f0-9]{64}')

def require(condition,message):
    if not condition: raise ValueError(message)

def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()

def private_file(file):
    p=Path(file); require(p.is_absolute() and p.resolve(strict=True)==p,'Exact non-symlink private path required')
    s=p.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and
        s.st_mode & 0o077==0 and s.st_size<=65000,'Bounded private single-link file required')
    return p

def exclusive(file,value):
    raw=canonical(value).encode(); require(len(raw)<=65000,'Bounded mailbox write required')
    with os.fdopen(os.open(file,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    fd=os.open(Path(file).parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

PROTOCOL='startup_preparation_mailbox_v1'
PURPOSE='new_startup_preparation'
NAMES={'handoff.json','turn.json','request.json','reply.json'}

def read(file):
    file=private_file(file)
    def epoch(s): return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_nlink)
    before=epoch(file.stat())
    with os.fdopen(os.open(file,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
        require(epoch(os.fstat(stream.fileno()))==before,'Mailbox file changed before read')
        value=json.loads(stream.read(65001))
        require(epoch(os.fstat(stream.fileno()))==before,'Mailbox file changed while reading')
    require(epoch(file.stat())==before,'Mailbox file changed after read'); return value

def handoff(file):
    p=Path(file); h=read(p)
    require(p.name=='handoff.json' and set(h)=={'protocol','purpose','startupId','reviewHash','brainId','phase',
        'mission','source','sourceHash','mailbox','boundary'} and h['protocol']==PROTOCOL and h['purpose']==PURPOSE and
        h['mailbox']==str(p.parent) and isinstance(h['reviewHash'],str) and SHA.fullmatch(h['reviewHash']) and
        type(h['phase']['workerLimit']) is int and h['phase']['workerLimit']==0 and h['phase']['repositoryWrites'] is False,
        'Exact checkout-local startup handoff required')
    return h

def validate_result(h,value):
    require(isinstance(value,dict) and set(value)=={'receipt','proposal'} and len(canonical(value).encode())<=12000,
        'Closed bounded new-startup result required; no catalog or historical receipt')
    require(canonical(value['receipt'])==canonical({'startupId':h['startupId'],'brainId':h['brainId'],
        'phaseId':h['phase']['id'],'purpose':PURPOSE,'acknowledged':True}),'Only this new startup receipt is permitted')
    p=value['proposal']
    require(isinstance(p,dict) and set(p)=={'objective','steps','checks','stoppingCheckpoint'},'Inert proposal fields only')
    for key in ('objective','stoppingCheckpoint'):
        require(isinstance(p[key],str) and 1<=len(p[key])<=2000,'Bounded proposal text required')
    for key in ('steps','checks'):
        require(isinstance(p[key],list) and 1<=len(p[key])<=10 and
            all(isinstance(s,str) and 1<=len(s)<=1000 for s in p[key]),'Bounded inert proposal list required')
    return value

def state(file):
    h=handoff(file); turn=read(Path(file).parent/'turn.json')
    require(set(turn)=={'startupId','reviewHash','nativeTurnId'} and turn['startupId']==h['startupId'] and
        turn['reviewHash']==h['reviewHash'] and isinstance(turn['nativeTurnId'],str) and
        0<len(turn['nativeTurnId'])<=128,'Exact original startup turn acknowledgment required')
    return {'startupId':h['startupId'],'phase':h['phase'],'mission':h['mission'],
        'brainId':h['brainId'],'nativeTurnId':turn['nativeTurnId'],'purpose':PURPOSE,'boundary':h['boundary'],
        'resultSchema':{'receipt':{'startupId':h['startupId'],'brainId':h['brainId'],'phaseId':h['phase']['id'],
            'purpose':PURPOSE,'acknowledged':True},'proposal':{'objective':'bounded text',
            'steps':['inert proposed step'],'checks':['proposed check'],'stoppingCheckpoint':'bounded text'}}}

def complete(file,result_file):
    h=handoff(file); state(file); root=Path(file).parent; result_file=private_file(result_file)
    require(result_file.parent==root and result_file.name not in NAMES,
        'Use a distinct private result file in this same checkout-local mailbox')
    result=validate_result(h,read(result_file)); request={'protocol':PROTOCOL,'handoffHash':digest(h),'result':result}
    target=root/'request.json'
    if os.path.lexists(target): require(read(target)==request,'Never replace a startup result')
    else: exclusive(target,request)
    return {'status':'submitted_to_original_startup_observer','startupId':h['startupId'],
        'nativeActions':0,'historicalReceiptReconstructed':False}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--handoff',required=True)
    s=p.add_subparsers(dest='action',required=True); s.add_parser('state'); c=s.add_parser('complete'); c.add_argument('result')
    a=p.parse_args(); print(canonical(state(a.handoff) if a.action=='state' else complete(a.handoff,a.result)))

if __name__=='__main__': main()
