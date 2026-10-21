"""Explicit post-preparation worker evidence; no load, receipt turn or Play.

Readiness observations are separate from execution authority and the consumed
original readiness. Even a complete observation never removes a startup fence.
"""
import argparse
import math
import os
from pathlib import Path
import sqlite3
import time

from . import prestart_startup as startup, public_readiness as public
from .core import Refusal, SHA, canonical, digest, require
from .native_read_client import ReadProxy, decode, validate_endpoint
from .native_policy_evidence import matches as policy_matches
from .public_native_tasks import validate_contract
from .standard_successor import pin

KIND = 'post_startup_worker_readiness_v1'
PR189_SOURCE = 'b5578722258be1466335191cd186407af5ac1c955d64a5b3b2352ea6a4dc7e55'
BOUNDARY = {'nativeLoadMade': False, 'nativeTurnStarted': False, 'subscriptionMade': False,
    'oldReadinessReplayed': False, 'oldReceiptReconstructed': False, 'playAuthorized': False,
    'recoveryAuthorized': False, 'bindingChanged': False, 'usageReset': False,
    'ownershipReleased': False, 'normalWritesUnfenced': False, 'modelEntitlementVerified': False,
    'currentTerminalSafety': 'unknown', 'historicalTerminalSafety': 'unknown', 'pilotAccepted': False}
JOURNAL = {'intent.json', 'load.claim.json', 'load.json', 'handoff-pin.json', 'turn.claim.json',
           'turn.json', 'turn-pin.json', 'receipt.claim.json', 'receipt.json', 'usage.json', 'outcome.json'}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def inventory(root, names=None):
    root = startup.prior.old.private_path(root, existing=True)
    files = sorted(root.iterdir())
    require(len(files) <= 32 and (names is None or {p.name for p in files} == names),
            'Complete original startup journal required; extra, partial or stopped records stay fenced')
    return {str(p): pin(startup.private_file(p)) for p in files}


def context(registry, ledger, source):
    """Validate a completed canonical startup and all immutable earlier context.

    Historical Python is only hashed. The one allowlisted implementation
    difference is compared separately, never written into an original record.
    """
    root = startup.location(registry, ledger)
    files = inventory(root, JOURNAL)
    intent = startup.mailbox.read(root / 'intent.json')
    q = intent.get('request')
    require(startup.valid(q) and intent == {'kind': startup.KIND, 'reviewHash': digest(q), 'request': q},
            'Exact original new-startup intent required')
    proof = startup.prior.source_proof(source)
    require(proof == q['executionSource'] and q['sourceHash'] == proof['sourceHash'] and
            q['sourceHash'] in (PR189_SOURCE, startup.owned.preplay.source_hash()),
            'Explicit unchanged qualified startup implementation required; never execute historical Python')
    p = q['predecessor']
    actual = startup.prior.context(registry, ledger, p['bindingFile'], p['command']['id'], p['originalSource']['root'])
    require(p['sourceHash'] == q['sourceHash'] and
            {k: v for k, v in actual.items() if k != 'sourceHash'} ==
            {k: v for k, v in p.items() if k != 'sourceHash'},
            'Original request, admission, source lineage or binding changed')
    owner = {'kind': startup.KIND, 'reviewHash': digest(q), 'journal': str(root)}
    require(q['journal'] == str(root) and q['mailbox'] == str(ledger.root / ('startup-preparation-' + root.name[:24])) and
            startup.mailbox.read(ledger.root / startup.FENCE) == owner and
            startup.mailbox.read(ledger.root / startup.ANCHOR) == owner and
            startup.databases(registry) == q['databases'] and
            startup.git_view(p['scope']['checkout'], ledger.root) == q['repository'] and
            startup.phase(ledger, q['phase']['maxTokens']) == q['phase'],
            'Preserved original databases, repository, accounting and both startup markers required')
    s = startup.status_in(ledger)
    require(s and s.get('status') in ('startup_preparation_completed', 'startup_budget_checkpoint') and
            s.get('newReceiptRecorded') is True, 'Positive completed preparation receipt required; no recovery of unknown attempts')
    out = startup.mailbox.read(root / 'outcome.json')
    turn = startup.mailbox.read(root / 'turn.json')
    require(set(out) == {'kind', 'reviewHash', 'status', 'nativeTurnId', 'lastStage', 'turnStartAttempted',
            'connectionClosed', 'reconnectAllowed', 'originalReadinessOutcome', 'terminalSafety', 'pilotAccepted'} and
            out == {'kind': startup.KIND, 'reviewHash': digest(q), 'status': s['status'],
                'nativeTurnId': turn.get('nativeTurnId'), 'lastStage': 'original_connection_observation',
                'turnStartAttempted': True, 'connectionClosed': True, 'reconnectAllowed': False,
                'originalReadinessOutcome': 'unqualified_preserved', 'terminalSafety': 'unknown', 'pilotAccepted': False} and
            set(turn) == {'reviewHash', 'nativeTurnId'} and turn['reviewHash'] == digest(q) and
            isinstance(turn['nativeTurnId'], str) and 0 < len(turn['nativeTurnId']) <= 128,
            'Exact positively ended original preparation observer required')
    box = Path(q['mailbox']); mail = inventory(box)
    require({'handoff.json', 'turn.json', 'request.json', 'reply.json'} <= {Path(p).name for p in mail},
            'Original checkout-local mailbox incomplete')
    h = startup.mailbox.handoff(box / 'handoff.json')
    receipt = startup.mailbox.read(root / 'receipt.json')
    claim = startup.mailbox.read(root / 'receipt.claim.json')
    require(h['source'] == proof['root'] and h['sourceHash'] == q['sourceHash'] and
            h['reviewHash'] == digest(q) and h['startupId'] == root.name and h['brainId'] == p['brainId'] and
            h['phase'] == {k: v for k, v in q['phase'].items() if k != 'mission'} and h['mission'] == q['phase']['mission'] and
            h['boundary'] == startup.BOUNDARY and receipt['nativeTurnId'] == turn['nativeTurnId'] and
            claim == {'reviewHash': digest(q), 'nativeTurnId': turn['nativeTurnId'], 'requestPin': pin(box / 'request.json')} and
            startup.mailbox.read(root / 'turn-pin.json') == pin(box / 'turn.json') and
            startup.mailbox.read(box / 'turn.json') == {'startupId': root.name, 'reviewHash': digest(q),
            'nativeTurnId': turn['nativeTurnId']} and finite(receipt['recordedAt']) and receipt['recordedAt'] <= time.time(),
            'Original new receipt and mailbox owner changed')
    # The reply has no native-action grant. Validate the actual closed reply.
    require(startup.mailbox.read(box / 'reply.json') == {'startupId': root.name,
            'status': 'new_startup_result_recorded', 'receiptHash': digest(receipt), 'playAuthorized': False},
            'Original observer reply changed')
    require(startup.mailbox.read(box / 'request.json') == {'protocol': startup.mailbox.PROTOCOL,
            'handoffHash': digest(h), 'result': receipt['result']}, 'Receipt must match its original exact publication')
    require(startup.mailbox.read(root / 'load.claim.json') == {'reviewHash': digest(q),
            'loadRequired': q['before']['activity'] == 'notLoaded'} and
            startup.mailbox.read(root / 'turn.claim.json') == {'reviewHash': digest(q), 'purpose': startup.mailbox.PURPOSE},
            'Original one-shot preparation claims changed')
    load = startup.mailbox.read(root / 'load.json')
    require(set(load) == {'reviewHash', 'loadedByThisStartup', 'observedAt', 'scope', 'terminalSafety'} and
            load['reviewHash'] == digest(q) and load['loadedByThisStartup'] is (q['before']['activity'] == 'notLoaded') and
            load['terminalSafety'] == 'unknown' and finite(load['observedAt']) and load['observedAt'] <= receipt['recordedAt'],
            'Original load record is not a current policy or safety assertion')
    loaded = load['scope']
    require(set(loaded) == {'activity', 'latestTurn', 'policy', 'trackedTerminals', 'authenticationHash',
            'environmentHash', 'environmentScope'} and loaded['activity'] == 'idle' and
            loaded['latestTurn'] == q['before']['latestTurn'] and policy_matches(loaded['policy']) and
            loaded['trackedTerminals'] == [] and loaded['environmentScope'] == 'thread' and
            loaded['authenticationHash'] == q['before']['authenticationHash'] and
            loaded['environmentHash'] == digest({'data': [], 'nextCursor': None}),
            'Positive original restricted loaded scope required, never a current safety assertion')
    u = startup.mailbox.read(root / 'usage.json')
    require(set(u) == {'observedLastTurnTokens', 'coverage', 'gaps', 'sampleHashes', 'chargedReservationFloor',
            'carriedPhaseCeiling', 'futurePhaseCeiling', 'oldUsageChanged'} and u['coverage'] == 'per_turn_not_lifetime' and
            u['oldUsageChanged'] is False and u['carriedPhaseCeiling'] == q['phase']['carriedPhaseCeiling'] and
            isinstance(u['gaps'], list) and all(v in ('startup_usage_missing_or_incomplete', 'lifetime_coverage_not_asserted') for v in u['gaps']) and
            isinstance(u['sampleHashes'], list) and len(u['sampleHashes']) <= 32 and
            all(isinstance(v, str) and SHA.fullmatch(v) for v in u['sampleHashes']),
            'Closed original preparation accounting required')
    n = u['observedLastTurnTokens']
    require(n is None or type(n) is int and 0 <= n <= 1000000000, 'Unknown preparation usage is not measured zero')
    require('lifetime_coverage_not_asserted' in u['gaps'] and
            len(u['gaps']) == len(set(u['gaps'])) and
            (n is not None or 'startup_usage_missing_or_incomplete' in u['gaps']) and
            (n is None or u['sampleHashes']), 'Retain explicit accounting gaps and actual sample provenance')
    require(s['status'] == ('startup_budget_checkpoint' if n is not None and n > q['phase']['maxTokens']
                           else 'startup_preparation_completed'), 'Original preparation budget outcome changed')
    charge = max(q['phase']['maxTokens'], n or 0)
    require(type(u['chargedReservationFloor']) is int and u['chargedReservationFloor'] == charge and
            type(u['futurePhaseCeiling']) is int and u['futurePhaseCeiling'] == max(0, u['carriedPhaseCeiling'] - charge),
            'Preserve full reservation or larger observed overrun; no allowance reset')
    paths = {**files, **mail, **{str(ledger.root / k): pin(ledger.root / k) for k in (startup.FENCE, startup.ANCHOR)},
             **p['sidecarPins'], p['bindingFile']: p['bindingPin']}
    result = {'kind': KIND, 'implementationHash': startup.owned.preplay.source_hash(),
        'startupSource': proof, 'startupReviewHash': digest(q), 'startupJournal': str(root), 'files': paths,
        'databases': q['databases'], 'repository': q['repository'], 'workspaceId': ledger.workspace_id,
        'brainId': p['brainId'], 'nativeTurnId': turn['nativeTurnId'], 'bindingHash': p['bindingHash'],
        'bindingFile': p['bindingFile'], 'scope': p['scope'], 'missionHash': p['missionHash'],
        'missionReviewHash': p['reviewHash'], 'usage': u, 'phase': q['phase'], 'boundary': dict(BOUNDARY)}
    require(len(canonical(result).encode()) <= 50000, 'Bounded complete worker-readiness context required')
    return result


class WorkerReadProxy(ReadProxy):
    """Closed metadata RPC vocabulary; even internal callers cannot load/start."""
    def __init__(self, endpoint, brain, project):
        super().__init__(endpoint)
        self.brain, self.project = brain, project

    def _rpc(self, method, params):
        if method == 'initialize':
            require(params == {'clientInfo': {'name': 'codex_orchestrator_observer', 'version': '1'},
                    'capabilities': {'experimentalApi': True}}, 'Fixed observer initialization only')
        elif method == 'project/read':
            require(params == {'projectId': self.project}, 'Exact reviewed project only')
        elif method == 'account/read':
            require(params == {'refreshToken': False}, 'No sign-in or credential refresh')
        elif method == 'model/list':
            require(set(params) == {'cursor', 'limit', 'includeHidden'} and params['limit'] == 30 and
                    params['includeHidden'] is False and (params['cursor'] is None or
                    isinstance(params['cursor'], str) and 0 < len(params['cursor']) <= 2048), 'Bounded model metadata only')
        elif method == 'mcpServerStatus/list':
            require(params in ({'detail': 'toolsAndAuthOnly'}, {'cursor': None, 'limit': 64,
                'detail': 'toolsAndAuthOnly', 'threadId': self.brain}), 'Exact scoped empty MCP observation only')
        else:
            require(method in ('thread/read', 'thread/effectivePolicy/read', 'thread/turns/list',
                    'thread/backgroundTerminals/list') and params.get('threadId') == self.brain,
                    'Native mutation, subscription or foreign thread refused')
            # The base call validator checks fixed metadata-only fields and bounds.
            if not getattr(self, '_validating', False):
                self._validating = True
                try: return self.call(method, params)
                finally: self._validating = False
        return super()._rpc(method, params)


def observe(registry, ledger, source):
    before = context(registry, ledger, source)
    binding = startup._read_binding(before['bindingFile'])
    require(digest(binding) == before['bindingHash'], 'Exact unchanged binding required')
    record = binding['brains'][before['brainId']]
    backend = validate_contract(record.get('nativeTaskBackend'), record.get('policyEvidence'))
    validate_endpoint(binding['endpoint'])
    schema = public.export_schemas(binding['endpoint']['executable'], binding['endpoint']['sha256'])
    started = time.time()
    with WorkerReadProxy(binding['endpoint'], before['brainId'], record['projectId']) as proxy:
        first = startup.owned.repeated(proxy, binding, before['brainId'])
        require(first['latestTurn'] == {'id': before['nativeTurnId'], 'status': 'completed'},
                'A different native turn cannot inherit preparation readiness')
        models, pages = public.models(proxy)
        second_models, second_pages = public.models(proxy)
        second = startup.owned.repeated(proxy, binding, before['brainId'])
        require(first == second and models == second_models and pages == second_pages,
                'Changing policy, environment, identity, account or model pages remain unknown')
        through = time.time()
    require(context(registry, ledger, source) == before, 'Original scope changed during worker evidence collection')
    validate_endpoint(binding['endpoint'])
    require(0 <= time.time() - started <= 120, 'Worker evidence stale before publication; no freshness renewal')
    blockers = []
    if second['activity'] != 'idle': blockers.append('brain_not_loaded')
    u = before['usage']
    if u['observedLastTurnTokens'] is None or 'startup_usage_missing_or_incomplete' in u['gaps']:
        blockers.append('preparation_usage_unknown')
    reserve = before['phase']['mission']['authority']['checkpointReserveTokens']
    if u['futurePhaseCeiling'] <= reserve: blockers.append('carried_allocation_exhausted')
    return {'version': 1, 'kind': KIND, 'context': before, 'contextHash': digest(before),
        'observedAt': started, 'throughAt': through, 'bindingHash': digest(binding),
        'executableHash': binding['endpoint']['sha256'], 'backend': backend, 'schema': schema,
        'native': second, 'models': models, 'modelPageHashes': pages,
        'status': 'blocked' if blockers else 'evidence_complete_not_activated', 'blockers': blockers,
        'remainingAuthority': ['worker_phase_review', 'new_exact_play'], 'boundary': dict(BOUNDARY)}


def collect(registry, ledger, source, destination):
    # A fresh explicit metadata observation, not another command, approval,
    # receipt or attempt. One new disjoint artifact; partial files never overwrite.
    c = context(registry, ledger, source)
    root = Path(destination); startup.prior.old.private_path(root.parent, existing=True)
    protected = [registry.root, *[Path(v['path']).parent for v in c['databases'].values()],
                 Path(source), Path(c['scope']['checkout'])]
    require(root.is_absolute() and root.resolve() == root and not os.path.lexists(root) and
            all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in protected),
            'New private evidence directory disjoint from operational/native/source roots required')
    root.mkdir(mode=0o700)
    startup.exclusive(root / 'intent.json', {'kind': KIND, 'contextHash': digest(c), 'context': c})
    report = observe(registry, ledger, source)
    require(report['context'] == c, 'Original scope changed before observation; preserve partial artifact')
    startup.exclusive(root / 'report.json', report)
    startup.exclusive(root / 'seal.json', {'kind': KIND, 'intentPin': pin(root / 'intent.json'),
        'reportPin': pin(root / 'report.json')})
    return {'status': report['status'], 'report': str(root / 'report.json'), 'blockers': report['blockers'],
            'observedAt': report['observedAt'], 'normalWritesBlocked': True, 'boundary': dict(BOUNDARY)}


def status(registry, ledger, directory):
    """File-only historical inspection; no RPC, export, timestamp or authority."""
    root = startup.prior.old.private_path(directory, existing=True)
    require({p.name for p in root.iterdir()} == {'intent.json', 'report.json', 'seal.json'},
            'Partial worker-readiness observation remains unknown; no automatic recollection')
    def read(name):
        file = startup.private_file(root / name)
        require(file.stat().st_size <= 65000, 'Bounded worker-readiness evidence required')
        return decode(file.read_bytes())
    seal, intent, report = read('seal.json'), read('intent.json'), read('report.json')
    require(seal == {'kind': KIND, 'intentPin': pin(root / 'intent.json'), 'reportPin': pin(root / 'report.json')} and
            report['version'] == 1 and report['kind'] == KIND and report['boundary'] == BOUNDARY and
            intent == {'kind': KIND, 'contextHash': report['contextHash'], 'context': report['context']} and
            digest(report['context']) == report['contextHash'] and finite(report['observedAt']) and finite(report['throughAt']) and
            report['observedAt'] <= report['throughAt'] <= time.time() and
            context(registry, ledger, report['context']['startupSource']['root']) == report['context'],
            'Worker readiness provenance or original scope changed; never promote cached evidence')
    return {'status': report['status'], 'observedAt': report['observedAt'], 'throughAt': report['throughAt'],
        'fresh': 0 <= time.time() - report['observedAt'] <= 120, 'blockers': report['blockers'],
        'normalWritesBlocked': True, 'remainingAuthority': report['remainingAuthority'], 'boundary': dict(BOUNDARY)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform', required=True); p.add_argument('--workspace', required=True)
    sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('collect'); a.add_argument('startup_source'); a.add_argument('destination')
    a = sub.add_parser('status'); a.add_argument('directory')
    args = p.parse_args(); registry, ledger = startup.prior.partial.routes(args.platform, args.workspace)
    result = collect(registry, ledger, args.startup_source, args.destination) if args.action == 'collect' else status(registry, ledger, args.directory)
    print(canonical(result))


if __name__ == '__main__':
    try: main()
    except (Refusal, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(canonical({'error': str(error), 'boundary': dict(BOUNDARY)})); raise SystemExit(2)
