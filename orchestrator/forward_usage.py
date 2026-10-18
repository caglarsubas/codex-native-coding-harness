"""One prospective local usage observation, never a rewrite of disposed history.

Only the exact owner's forward-planning confirmation calls collect(). Preparing,
backing up and reading a result do not read telemetry or renew its sample time.
"""
import contextlib
import hashlib
import math
import os
from pathlib import Path
import time

from . import activity, brain_memory
from .core import digest, require
from .host_runtime import safe_path, stamp
from .observations import TOKENS, config, token_vector
from .standard_successor import pin
from .standard_host_inspection import _read_private
from .standard_quarantine import exclusive

KIND = 'prospective_registered_usage_v1'
FIELDS = {'version','kind','configFile','configPin','home','directories'}


def number(value):
    return type(value) in (int,float) and math.isfinite(value)


def sessions(run):
    require(not run['tasks'], 'Only the empty canceled attempt is covered')
    rows=run.get('brainSegments') or [{'id':run['brainId'],'start':run['startedAt'],'end':None}]
    require(isinstance(rows,list) and 1<=len(rows)<=32 and all(isinstance(r,dict) and
        isinstance(r.get('id'),str) and activity.IDENTITY.fullmatch(r['id']) and
        number(r.get('start')) and r['start']>=run['startedAt'] and
        (r.get('end') is None or number(r['end']) and r['end']>=r['start']) for r in rows) and
        len({r['id'] for r in rows})==len(rows), 'Exact registered brain intervals required')
    return rows


def directories(home):
    root=Path(home)
    require(root.is_absolute() and len(root.parts)>=4, 'Explicit configured log home required')
    # Do not pin directory timestamps/link counts: creating a dated log folder is
    # legitimate. Device/inode, permissions and ancestry must stay identical.
    result={}
    for path in (*root.parents,root,root/'sessions',root/'archived_sessions'):
        if path.parent==root and not os.path.lexists(path): result[str(path)]=None; continue
        info=safe_path(path,directory=True)
        result[str(path)]=list(stamp(info))[:5]
    require(not root.stat().st_mode & 0o077, 'Configured log home must be private')
    return result


def source(ledger):
    file=ledger.root/'observations.json'; before=pin(file); home=config(ledger).get('codexHome')
    require(isinstance(home,str) and pin(file)==before, 'Pinned observation configuration required')
    return {'version':1,'kind':KIND,'configFile':str(file),'configPin':before,
        'home':home,'directories':directories(home)}


def check_source(ledger, value):
    require(isinstance(value,dict) and set(value)==FIELDS and type(value['version']) is int and
        value['version']==1 and value['kind']==KIND and source(ledger)==value,
        'Reviewed usage source/configuration/directory identity changed')


def validate(report, run):
    require(isinstance(report,dict) and report.get('runId')==run['id'] and
        report.get('scopeHash')==brain_memory.scope(run) and report.get('gaps')==[] and
        report.get('coverage')=='observed_local' and number(report.get('collectedAt')) and
        number(report.get('through')) and run['startedAt']<=report['through']<=report['collectedAt'] and
        report['collectedAt']<=time.time(), 'Actual gap-free registered usage required; unknown is not zero')
    rows=report.get('records'); wanted={r['id']:r for r in sessions(run)}
    require(isinstance(rows,list) and len(rows)==len(wanted) and all(isinstance(r,dict) for r in rows) and
        {r.get('sessionId') for r in rows}==set(wanted), 'Complete exact registered session set required')
    for row in rows:
        segment=wanted[row['sessionId']]
        require(row.get('role')=='brain' and row.get('gaps')==[] and token_vector(row.get('tokens')) is not None and
            number(row.get('sampleAt')) and segment['start']<=row['sampleAt']<=min(
                report['through'],segment.get('end') or report['through']) and
            type(row.get('calls')) is int and row['calls']>=1,
            'Exact numeric session counters and original sample times required')
    require(token_vector(report.get('tokens'))=={k:sum(r['tokens'][k] for r in rows) for k in TOKENS},
        'Usage aggregate must equal its exact session vectors, without double-counting cache/reasoning')
    return {r['sessionId']:r for r in rows}


def baseline(original):
    run=original['run']; report=run.get('usageReport')
    require(report and original['usageReceiptHash']==digest(report), 'Retained original usage receipt required')
    validate(report,run)  # Stale is permitted only for the immutable baseline.
    high,brain=run.get('usageHighWater'),run.get('brainObservedTokens')
    require(type(high) is int and type(brain) is int and high>=report['tokens']['total_tokens']>=0 and
        brain>=0 and run.get('brainUsageCoverage')=='observed_partial', 'Known original high-water amounts required')


def budget(original, maximum, report, *, fresh=True, active=True):
    baseline(original); run=original['run']; previous=run['usageReport']
    before=validate(previous,run); after=validate(report,run)
    require(type(maximum) is int and 1<=maximum<=100000 and (not active or time.time()<run['expiresAt']),
        'Bounded planning allowance within the original phase clock required')
    require(report['collectedAt']>=previous['collectedAt'] and report['through']>=previous['through'] and
        (not fresh or 0<=time.time()-report['collectedAt']<brain_memory.FRESH_SECONDS),
        'Fresh actual prospective observation required; never retimestamp or resample an old report')
    for identity, row in after.items():
        prior=before[identity]
        require(row['sampleAt']>=prior['sampleAt'] and row['calls']>=prior['calls'] and
            all(row['tokens'][k]>=prior['tokens'][k] for k in TOKENS),
            'A missing/regressed session counter cannot refund previously observed consumption')
    total=report['tokens']['total_tokens']; brain=sum(r['tokens']['total_tokens'] for r in after.values())
    require(total>=run['usageHighWater'] and brain>=run['brainObservedTokens'],
        'Prospective evidence must cover every retained cumulative high-water amount')
    require(maximum<=min(run['brainAllowance']-brain,
        run['limits']['tokenBudget']-total-run['limits']['checkpointReserveTokens']),
        'New observed consumption plus planning must fit unchanged brain/phase/reserve limits')


def inventory(value, run):
    paths=sorted(activity.candidates(Path(value['home']),[r['id'] for r in sessions(run)]))
    require(paths, 'Exact registered session logs unavailable')
    result={}
    for path in paths:
        info=safe_path(path)
        require(info.st_uid==os.getuid() and not info.st_mode & 0o077 and info.st_nlink==1 and
            0<info.st_size<=brain_memory.MAX_BYTES, 'Private bounded unaliased telemetry file required')
        result[str(path)]=list(stamp(info))
    require(sum(r[6] for r in result.values())<=brain_memory.MAX_BYTES,
        'Total explicit telemetry read exceeds the bound')
    return result


def collect(ledger, q):
    """Called once, only after canonical owner intent; no native API or DB writes."""
    original=q['original']; run=original['run']; value=q['usageSource']; root=Path(q['journal'])
    require((q['version'],q['kind']) in ((2,'canceled_play_forward_planning_v2'),(3,'same_project_forward_planning_v3')) and
        _read_private(root/'intent.json')=={'kind':q['kind'],'reviewHash':digest(q)},
        'Exact committed prospective owner intent required before collection')
    check_source(ledger,value)
    exclusive(root/'usage.claim.json',{'kind':KIND,'reviewHash':digest(q),'sourceHash':digest(value),
        'baselineHash':original['usageReceiptHash']})
    files=inventory(value,run); hashes={}
    @contextlib.contextmanager
    def opened(path):
        name=str(path); require(name in files, 'Unreviewed telemetry file')
        with activity.open_regular(path) as stream:
            require(list(stamp(os.fstat(stream.fileno())))==files[name], 'Telemetry changed before read')
            sha=hashlib.sha256(); remaining=files[name][6]
            while remaining:
                chunk=stream.read(min(remaining,1024*1024))
                require(chunk, 'Telemetry truncated before read')
                sha.update(chunk); remaining-=len(chunk)
            require(not stream.read(1), 'Telemetry grew beyond the fixed read bound')
            stream.seek(0)
            yield stream
            require(list(stamp(os.fstat(stream.fileno())))==files[name] and
                list(stamp(path.lstat()))==files[name], 'Telemetry changed during read; do not retry')
            hashes[name]=sha.hexdigest()
    now=time.time(); records=[]
    for segment in sessions(run):
        row=brain_memory.session_usage([Path(p) for p in files if segment['id'] in Path(p).name],
            segment['id'],segment['start'],min(now,segment.get('end') or now),True,open_log=opened)
        row['role']='brain'; records.append(row)
    check_source(ledger,value)
    require(inventory(value,run)==files and set(hashes)==set(files), 'Telemetry inventory changed; no resample')
    report={'scopeHash':brain_memory.scope(run),'runId':run['id'],'collectedAt':now,'through':now,
        'records':records,'tokens':{k:sum(r['tokens'][k] for r in records) for k in TOKENS},
        'gaps':sorted({g for r in records for g in r['gaps']}),
        'coverage':'gapped' if any(r['gaps'] for r in records) else 'observed_local',
        'boundary':'New local registered-session observation only; not billing, descendants, cleanup or a hard cap'}
    record={'kind':KIND,'reviewHash':digest(q),'sourceHash':digest(value),
        'baselineHash':original['usageReceiptHash'],'report':report,
        'files':{p:{'epoch':epoch,'sha256':hashes[p]} for p,epoch in files.items()}}
    exclusive(root/'usage.json',record)  # Retain gaps/regressions too; failure never erases evidence.
    budget(original,q['maxTokens'],report)
    return record


def retained(q, expected_pin, *, fresh, active=True):
    root=Path(q['journal']); require(pin(root/'usage.json')==expected_pin, 'Prospective usage record changed')
    value=_read_private(root/'usage.json')
    expected={'kind':KIND,'reviewHash':digest(q),'sourceHash':digest(q['usageSource']),
        'baselineHash':q['original']['usageReceiptHash']}
    require(_read_private(root/'usage.claim.json')==expected and set(value)==set(expected)|{'report','files'} and
        all(value[k]==v for k,v in expected.items()), 'Exact one-shot observation and original baseline required')
    budget(q['original'],q['maxTokens'],value['report'],fresh=fresh,active=active)
    return value
