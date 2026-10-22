"""Explicit certificate-aware worker evidence, never a load or execution route.

The current issued host is read without changing the historical binding. A
review covers only one bounded observation in a new private directory. Neither
the review nor a complete observation lifts the preparation/identity fences.
"""
import argparse
import copy
import os
from pathlib import Path
import sqlite3
import time

from . import post_reboot_dashboard as dashboard, worker_readiness as worker
from .core import Refusal, SHA, canonical, digest, require
from .host_lifecycle import sync_directory
from .native_read_client import validate_endpoint
from .public_native_tasks import validate_contract
from .standard_quarantine import exclusive

KIND = 'certificate_worker_readiness_v1'
BOUNDARY = {**worker.BOUNDARY, 'registryWritten': False, 'ledgerWritten': False,
            'ordinaryRoutesUnfenced': False, 'historicalEvidenceRefreshed': False,
            'nativeMetadataCollectedOnPoll': False}
FIELDS = {'version', 'kind', 'sourceHash', 'repairFile', 'launchedSource', 'context',
          'catalogPin', 'directory', 'boundary'}
NATIVE_FIELDS = {'activity', 'latestTurn', 'policy', 'trackedTerminals', 'authenticationHash',
                 'environmentHash', 'environmentScope'}
REPORT_FIELDS = {'version', 'kind', 'reviewHash', 'observedAt', 'throughAt', 'backend', 'schema',
                 'native', 'models', 'modelPageHashes', 'usage', 'checkpointReserveTokens',
                 'status', 'blockers', 'remainingAuthority', 'executionReviewAvailable', 'boundary'}
REMAINING = ['separately_qualified_worker_phase_control', 'exact_worker_phase_review', 'new_exact_play']


def scope(repair_file, launched_source):
    # This reader revalidates the completed certificate, entire original
    # preparation, all databases and the actual issued process/socket. It does
    # not connect to either the current host or the retired binding endpoint.
    c, certificate, _, _ = dashboard.foundation(repair_file, launched_source)
    original = dashboard.read(Path(certificate['witness']) / 'report.json')['context']
    require(original['workspaceId'] == c['workspaceId'] and original['brainId'] == c['brainId'] and
            original['nativeTurnId'] == c['latestTurnId'] and original['usage'] == c['originalUsage'],
            'Exact certificate-backed completed preparation and accounting required')
    phase = original['phase']; usage = c['originalUsage']
    n = usage['observedLastTurnTokens']
    require((n is None or type(n) is int and 0 <= n <= 1000000000) and
            type(phase['maxTokens']) is int and phase['maxTokens'] > 0 and
            type(usage['carriedPhaseCeiling']) is int and usage['carriedPhaseCeiling'] == phase['carriedPhaseCeiling'] and
            type(usage['chargedReservationFloor']) is int and usage['chargedReservationFloor'] == max(phase['maxTokens'], n or 0) and
            type(usage['futurePhaseCeiling']) is int and usage['futurePhaseCeiling'] ==
                max(0, usage['carriedPhaseCeiling'] - usage['chargedReservationFloor']),
            'Preserve full preparation reservation or larger overrun; unknown usage is not zero')
    reserve = phase['mission']['authority']['checkpointReserveTokens']
    require(type(reserve) is int and reserve >= 0, 'Original reviewed checkpoint reserve required')
    validate_contract(c['record'].get('nativeTaskBackend'), c['record'].get('policyEvidence'))
    return {'host': c, 'phase': phase, 'checkpointReserveTokens': reserve}


def prepare(repair_file, launched_source, catalog_file, directory):
    """File-only until-scope-changes review; no native inspection or claim."""
    c = scope(repair_file, launched_source)
    catalog_pin = dashboard.catalog(catalog_file, c['host'])
    output = dashboard.disjoint(directory, c['host'])
    q = {'version': 1, 'kind': KIND, 'sourceHash': dashboard.source_hash(),
         'repairFile': str(repair_file), 'launchedSource': str(launched_source),
         'context': c, 'catalogPin': catalog_pin, 'directory': str(output), 'boundary': dict(BOUNDARY)}
    require(len(canonical(q).encode()) <= 64000, 'Bounded exact worker-observation review required')
    return {'request': q, 'reviewHash': digest(q), 'validUntil': 'scope_changes',
            'effect': 'One explicit metadata-only worker-readiness observation; no load, turn, binding change or Play',
            'executionReviewAvailable': False}


def validate(q, *, completed=False):
    require(isinstance(q, dict) and set(q) == FIELDS and type(q['version']) is int and q['version'] == 1 and
            q['kind'] == KIND and q['boundary'] == BOUNDARY and q['sourceHash'] == dashboard.source_hash(),
            'Exact qualified worker-observation review required')
    require(scope(q['repairFile'], q['launchedSource']) == q['context'] and
            dashboard.catalog(q['catalogPin']['path'], q['context']['host']) == q['catalogPin'],
            'Reviewed certificate, host, dual identities, accounting or catalog changed')
    dashboard.disjoint(q['directory'], q['context']['host'], new=not completed)
    return q


def blockers(context, native):
    result = []
    if native['activity'] == 'notLoaded': result += ['brain_not_loaded', 'loaded_policy_unknown', 'current_trackers_unknown']
    usage = context['host']['originalUsage']
    if usage['observedLastTurnTokens'] is None or 'startup_usage_missing_or_incomplete' in usage['gaps']:
        result.append('preparation_usage_unknown')
    if usage['futurePhaseCeiling'] <= context['checkpointReserveTokens']:
        result.append('carried_allocation_exhausted')
    return result


def check_report(q, report):
    """Closed retained shape; even saved loaded defaults never grant execution."""
    c = q['context']; host = c['host']; native = report.get('native')
    require(set(report) == REPORT_FIELDS and type(report['version']) is int and report['version'] == 1 and
            report['kind'] == KIND and report['reviewHash'] == digest(q) and report['boundary'] == BOUNDARY and
            report['executionReviewAvailable'] is False and report['remainingAuthority'] == REMAINING and
            report['usage'] == host['originalUsage'] and report['checkpointReserveTokens'] == c['checkpointReserveTokens'] and
            report['backend'] == host['record']['nativeTaskBackend'] and
            isinstance(native, dict) and set(native) == NATIVE_FIELDS and
            native['latestTurn'] == {'id': host['latestTurnId'], 'status': 'completed'} and
            all(isinstance(native[k], str) and SHA.fullmatch(native[k]) for k in ('authenticationHash', 'environmentHash')) and
            native['environmentHash'] == digest({'data': [], 'nextCursor': None}), 'Exact bounded worker report required')
    require((native['activity'] == 'notLoaded' and native['policy'] is None and native['trackedTerminals'] is None and
                native['environmentScope'] == 'host_global') or
            (native['activity'] == 'idle' and worker.policy_matches(native['policy']) and
                native['trackedTerminals'] == [] and native['environmentScope'] == 'thread'),
            'Loaded defaults/trackers require actual restricted evidence; unloaded stays unknown')
    require(report['blockers'] == blockers(c, native) and
            report['status'] == ('blocked' if report['blockers'] else 'evidence_complete_not_activated') and
            worker.finite(report['observedAt']) and worker.finite(report['throughAt']) and
            report['observedAt'] <= report['throughAt'] <= time.time() and
            0 <= report['throughAt'] - report['observedAt'] <= 120, 'Original evidence time or blockers differ')
    schema = report['schema']
    require(isinstance(schema, dict) and set(schema) == {'protocol', 'schemaHashes', 'methods', 'experimentalFields'} and
            schema['protocol'] == report['backend']['protocol'] and schema['methods'] == ['thread/start', 'turn/start'] and
            schema['experimentalFields'] is True and set(schema['schemaHashes']) == set(worker.public.SCHEMAS) and
            all(isinstance(v, str) and SHA.fullmatch(v) for v in schema['schemaHashes'].values()),
            'Complete pinned binary schema summary required, not a worker execution proof')
    models, hashes = report['models'], report['modelPageHashes']
    require(isinstance(models, list) and 0 < len(models) <= 30 and isinstance(hashes, list) and 0 < len(hashes) <= 8 and
            all(isinstance(v, str) and SHA.fullmatch(v) for v in hashes), 'Bounded actual model pages required')
    names = []
    for row in models:
        require(isinstance(row, dict) and set(row) == {'model', 'efforts'} and isinstance(row['model'], str) and
                0 < len(row['model']) <= 100 and isinstance(row['efforts'], list) and row['efforts'] and
                all(isinstance(v, str) and v in worker.public.EFFORTS for v in row['efforts']) and
                len(row['efforts']) == len(set(row['efforts'])), 'Actual supported model/effort intersection required')
        names.append(row['model'])
    require(len(names) == len(set(names)), 'Duplicate model observation')


def observe(q):
    """One closed proxy, repeated metadata only; no hidden loaded-only fallback."""
    c = q['context']; host = c['host']; endpoint = host['endpoint']; brain = host['brainId']
    binding = {'endpoint': endpoint, 'brains': {brain: copy.deepcopy(host['record'])}}
    backend = validate_contract(host['record'].get('nativeTaskBackend'), host['record'].get('policyEvidence'))
    validate_endpoint(endpoint)
    schema = worker.public.export_schemas(endpoint['executable'], endpoint['sha256'])
    # Start the freshness window before the earliest native sample, not after
    # slow context checks or when the report is later viewed.
    started = time.time()
    with worker.WorkerReadProxy(endpoint, brain, host['record']['projectId']) as proxy:
        first = worker.startup.owned.repeated(proxy, binding, brain)
        require(first['latestTurn'] == {'id': host['latestTurnId'], 'status': 'completed'},
                'Exact original completed preparation must remain latest')
        models, pages = worker.public.models(proxy)
        other_models, other_pages = worker.public.models(proxy)
        second = worker.startup.owned.repeated(proxy, binding, brain)
        require(first == second and models == other_models and pages == other_pages and
                not getattr(proxy, '_early_requests', []),
                'Changing identity, policy, account, model pages, environment or permission state refuses')
        through = time.time()
    require(scope(q['repairFile'], q['launchedSource']) == c, 'Original scope changed during explicit observation')
    validate_endpoint(endpoint)
    require(0 <= time.time() - started <= 120, 'Worker evidence stale before retention; never renew time')
    missing = blockers(c, second)
    report = {'version': 1, 'kind': KIND, 'reviewHash': digest(q), 'observedAt': started, 'throughAt': through,
        'backend': backend, 'schema': schema, 'native': second, 'models': models, 'modelPageHashes': pages,
        'usage': copy.deepcopy(host['originalUsage']), 'checkpointReserveTokens': c['checkpointReserveTokens'],
        'status': 'blocked' if missing else 'evidence_complete_not_activated', 'blockers': missing,
        'remainingAuthority': list(REMAINING),
        'executionReviewAvailable': False, 'boundary': dict(BOUNDARY)}
    check_report(q, report)
    return report


def collect(q, confirmation, fresh_catalog):
    require(confirmation == digest(q), 'Exact worker-observation review required; never infer confirmation')
    validate(q); host = q['context']['host']
    catalog_pin = dashboard.catalog(fresh_catalog, host, fresh=True)
    root = Path(q['directory']); root.mkdir(mode=0o700)
    sync_directory(root.parent)
    exclusive(root / 'intent.json', {'kind': KIND, 'reviewHash': digest(q), 'request': q,
                                   'startupCatalogPin': catalog_pin})
    # Partial artifacts are retained; a second call cannot overwrite/reuse this
    # destination. There is no native-effect claim to migrate or rearm.
    report = observe(q)
    require(scope(q['repairFile'], q['launchedSource']) == q['context'] and
            dashboard.catalog(fresh_catalog, host, fresh=True) == catalog_pin,
            'Scope or actual app catalog changed before retention')
    require(0 <= time.time() - report['observedAt'] <= 120,
            'Worker evidence stale after final scope checks; never renew time')
    require(len(canonical(report).encode()) <= 64000, 'Bounded metadata-only report required')
    exclusive(root / 'report.json', report)
    exclusive(root / 'seal.json', {'kind': KIND, 'intentPin': dashboard.pin(root / 'intent.json'),
                                  'reportPin': dashboard.pin(root / 'report.json')})
    sync_directory(root)
    return status(root)


def status(directory):
    """File-only review of retained evidence. Never export, connect or renew."""
    root = dashboard.repair.launch.isolated_directory(directory)
    require({p.name for p in root.iterdir()} == {'intent.json', 'report.json', 'seal.json'},
            'Partial observation remains unknown; no automatic recollection')
    seal = dashboard.read(root / 'seal.json')
    require(seal == {'kind': KIND, 'intentPin': dashboard.pin(root / 'intent.json'),
                     'reportPin': dashboard.pin(root / 'report.json')}, 'Original immutable observation changed')
    intent, report = (dashboard.read(root / n) for n in ('intent.json', 'report.json'))
    q = intent['request']; validate(q, completed=True)
    require(intent == {'kind': KIND, 'reviewHash': digest(q), 'request': q,
                        'startupCatalogPin': intent['startupCatalogPin']} and
            dashboard.catalog(intent['startupCatalogPin']['path'], q['context']['host']) == intent['startupCatalogPin'],
            'Original exact observation intent/catalog required')
    check_report(q, report)
    return {'status': report['status'], 'reviewHash': digest(q), 'observedAt': report['observedAt'],
        'throughAt': report['throughAt'], 'fresh': 0 <= time.time() - report['observedAt'] <= 120,
        'blockers': report['blockers'], 'normalWritesBlocked': True, 'executionReviewAvailable': False,
        'remainingAuthority': report['remainingAuthority'], 'boundary': dict(BOUNDARY)}


def main():
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='action', required=True)
    p = commands.add_parser('prepare')
    for name in ('repair', 'launched_source', 'catalog', 'directory'): p.add_argument(name)
    p = commands.add_parser('collect'); p.add_argument('review'); p.add_argument('--confirm-hash', required=True)
    p.add_argument('--catalog', required=True)
    p = commands.add_parser('status'); p.add_argument('directory')
    args = parser.parse_args()
    if args.action == 'prepare': result = prepare(args.repair, args.launched_source, args.catalog, args.directory)
    elif args.action == 'collect': result = collect(dashboard.read(args.review), args.confirm_hash, args.catalog)
    else: result = status(args.directory)
    print(canonical(result))


if __name__ == '__main__':
    try: main()
    except (Refusal, OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        print(canonical({'error': 'Certificate worker observation refused; preserve partial records and original state',
                         'boundary': BOUNDARY}))
        raise SystemExit(2)
