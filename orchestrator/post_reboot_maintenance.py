"""Forward-only, file-only epoch migration for a completed preparation.

The old registry, binding and every authority record stay byte-logically intact.
Only the explicit maintenance reader can use the new certificate. Normal routes,
native effects, loading, Play and historical evidence retain their old fences.
"""
import argparse
import contextlib
import hashlib
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import time
from types import SimpleNamespace

from . import worker_readiness as worker, prestart_startup as startup
from . import partial_admission as partial, workspace_identity_recovery as recovery
from .core import Refusal, canonical, digest, require
from .host_lifecycle import sync_directory
from .native_read_client import decode, file_identity, secure_path
from .standard_quarantine import exclusive
from .workspaces import identity, private_path

KIND = 'post_reboot_maintenance_epoch_v2'
FENCE = 'post-reboot-maintenance.claim.json'
PR190 = '9b50866bc27ba97c17f3ac1fd73d9002ad5623bea84a1b9fc00534a244ada197'
BOUNDARY = {**worker.BOUNDARY, 'registryWritten': False, 'ledgerWritten': False,
            'ordinaryRoutesUnfenced': False, 'maintenanceReadOnly': True,
            'historicalEvidenceRefreshed': False, 'hostLaunchAuthorized': False}
FIELDS = {'version', 'kind', 'sourceHash', 'workspaceId', 'platform', 'witness',
          'context', 'journal', 'boundary'}


def device(info):
    return info.st_dev


def boot_epoch():
    """Fixed OS metadata read, not an elapsed-time or terminal-safety assertion."""
    r = subprocess.run(['/usr/sbin/sysctl', '-n', 'kern.boottime'], capture_output=True,
                       timeout=5, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
    require(r.returncode == 0 and not r.stderr and len(r.stdout) < 256, 'Complete boot metadata required')
    m = re.fullmatch(rb'\{ sec = ([0-9]+), usec = ([0-9]+) \}[^\n]*\n?', r.stdout)
    require(m is not None and int(m[2]) < 1000000, 'Unsupported boot metadata')
    return int(m[1]) + int(m[2]) / 1000000


def boot_session():
    """Kernel boot identity, unlike calendar-adjusted kern.boottime, is stable."""
    r = subprocess.run(['/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'], capture_output=True,
                       timeout=5, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})
    require(r.returncode == 0 and not r.stderr and len(r.stdout) < 128,
            'Complete boot-session identity required')
    m = re.fullmatch(rb'([a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})\n?', r.stdout)
    require(m is not None and m[1].replace(b'-', b'') != b'0' * 32, 'Unsupported boot-session identity')
    return m[1].decode('ascii').lower()


def pin(path):
    path = startup.private_file(path)  # Also validates every ancestor's ownership/permissions.
    require(path.is_absolute() and path.resolve(strict=True) == path and
            path.name not in ('auth.json', '.env'), 'Canonical non-credential record required')
    private_path(path.parent, existing=True)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
            not info.st_mode & 0o077 and info.st_nlink == 1 and info.st_size <= 65536,
            'Bounded private single-link record required')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        require(file_identity(os.fstat(stream.fileno())) == file_identity(info), 'Record changed')
        raw = stream.read(65537)
    require(len(raw) == info.st_size and file_identity(path.lstat()) == file_identity(info), 'Record changed during read')
    return {'path': str(path), 'epoch': [device(info), *file_identity(info)[1:]],
            'sha256': hashlib.sha256(raw).hexdigest()}


def read(path):
    before = pin(path)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        require([device(os.fstat(stream.fileno())), *file_identity(os.fstat(stream.fileno()))[1:]] == before['epoch'],
                'Record changed before decoding')
        value = decode(stream.read(65537))
    require(pin(path) == before, 'Record changed during decoding')
    return value


def historical_pin(path, expected, old, new, boot):
    """Only this historical comparison translates a device; no live pin does."""
    actual = pin(path); epoch = actual['epoch']
    require(epoch[0] == new and epoch[7] / 1e9 <= boot, 'Pre-reboot record required; no new capture for an old effect')
    require(set(expected) == {'identity', 'sha256'} and len(expected['identity']) == 4 and
            all(type(n) is int for n in expected['identity']) and expected['identity'][0] == old and
            [epoch[1], epoch[5], epoch[6]] == expected['identity'][1:] and
            actual['sha256'] == expected['sha256'], 'Only device drift; inode/content/epoch changes refuse')
    return actual


def source_epoch(expected, old, new, boot, allowed):
    require(set(expected) == {'root', 'sourceHash', 'epochHash'} and expected['sourceHash'] in allowed,
            'Explicit qualified historical implementation required')
    current = startup.prior.source_proof(expected['root'])  # Hash bytes only; never execute old Python.
    epochs = {}
    for file in sorted((Path(expected['root']) / 'orchestrator').glob('*.py')):
        s = file.lstat()
        require(device(s) == new and s.st_ctime_ns / 1e9 <= boot, 'Historical source must predate this boot')
        epochs[file.name] = [old, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns,
                             s.st_mode, s.st_uid, s.st_nlink]
    require(current['sourceHash'] == expected['sourceHash'] and digest(epochs) == expected['epochHash'],
            'Historical source changed beyond its device; no import or fallback')
    return {**current, 'currentEpochHash': digest({k: [new, *v[1:]] for k, v in epochs.items()})}


def databases(registry):
    values = startup.databases(registry)
    for value in values.values():
        value['identity'][0] = device(Path(value['path']).stat())
    return values


def retired_endpoint(binding):
    """Inspect only the original binary and absent socket; never connect it."""
    endpoint = binding['endpoint']
    require(set(endpoint) == {'executable', 'sha256', 'socket', 'socketIdentity', 'serverIdentityHash'} and
            all(isinstance(endpoint[k], str) and re.fullmatch('[a-f0-9]{64}', endpoint[k])
                for k in ('sha256', 'serverIdentityHash')), 'Exact original endpoint contract required')
    path = Path(endpoint['socket'])
    require(path.is_absolute() and path.resolve() == path and not os.path.lexists(path),
            'Retired socket must be absent; never connect, unlink, recreate or adopt it')
    binary, before = secure_path(endpoint['executable'])
    with binary.open('rb') as stream:
        require(file_identity(os.fstat(stream.fileno())) == file_identity(before), 'Original binary changed')
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    require(actual == endpoint['sha256'] and file_identity(binary.stat()) == file_identity(before),
            'Exact original native binary bytes required; never execute it')
    return {'endpointHash': digest(endpoint), 'executableHash': actual, 'oldSocketAbsent': True,
            'nativeConnectionMade': False, 'protectedDirectories': [str(binary.parent), str(path.parent)]}


def route(platform, workspace):
    """Private query-only reader; not a Registry/Ledger writer or effect route."""
    identity(workspace); root = private_path(platform, existing=True)
    registry = SimpleNamespace(root=root, db=root / 'platform.sqlite3')
    with recovery.read_database(registry.db) as db:
        row, saved = recovery.selected_row(db, workspace)
    ledger = partial.reader(row['root'], workspace, root)
    require(saved['brainId'] == row['brain'], 'Registered brain changed')
    return registry, ledger, saved


def location(registry, ledger, startup_hash):
    # Inode + original startup owner, never the new device, review ID or source.
    return registry.root / 'post-reboot-maintenance' / digest({
        'workspace': ledger.workspace_id, 'inode': ledger.db.stat().st_ino, 'startup': startup_hash})


def context(platform, workspace, witness, *, reviewed_boot=None):
    session = boot_session()
    registry, ledger, saved = route(platform, workspace)
    witness = private_path(witness, existing=True)
    require({p.name for p in witness.iterdir()} == {'intent.json', 'report.json', 'seal.json'},
            'Complete original worker observation required, not an arbitrary evidence file')
    report, intent, seal = (read(witness / n) for n in ('report.json', 'intent.json', 'seal.json'))
    c = report['context']; old = saved['databaseIdentity'][0]; new = device(ledger.db.stat()); observed_boot = boot_epoch()
    require(type(observed_boot) in (int, float) and math.isfinite(observed_boot) and
            0 < observed_boot <= time.time(), 'Complete current boot boundary required')
    if reviewed_boot is None:
        reviewed_boot = {'bootSessionUuid': session, 'bootedAt': observed_boot}
    require(isinstance(reviewed_boot, dict) and set(reviewed_boot) == {'bootSessionUuid', 'bootedAt'} and
            reviewed_boot['bootSessionUuid'] == session and type(reviewed_boot['bootedAt']) in (int, float) and
            math.isfinite(reviewed_boot['bootedAt']) and 0 < reviewed_boot['bootedAt'] <= time.time(),
            'Exact reviewed boot session and original timestamp boundary required')
    # Never renew the reviewed cutoff. A backward calendar adjustment tightens,
    # not relaxes, the historical bound; a new boot UUID always refuses.
    boot = min(observed_boot, reviewed_boot['bootedAt'])
    require(type(old) is int and type(new) is int and old != new and
            report['version'] == 1 and report['kind'] == worker.KIND and report['boundary'] == worker.BOUNDARY and
            c['kind'] == worker.KIND and c['boundary'] == worker.BOUNDARY and
            c['implementationHash'] in (PR190, startup.owned.preplay.source_hash()) and
            report['status'] in ('blocked', 'evidence_complete_not_activated') and
            type(report['observedAt']) in (int, float) and type(report['throughAt']) in (int, float) and
            math.isfinite(report['observedAt']) and 0 < report['observedAt'] <= report['throughAt'] <= boot and
            intent == {'kind': worker.KIND, 'contextHash': digest(c), 'context': c} and
            report['contextHash'] == digest(c), 'Exact pre-reboot qualified observation required; never fresh native evidence')
    require(set(seal) == {'kind', 'intentPin', 'reportPin'} and seal['kind'] == worker.KIND,
            'Original observation seal required')
    pins = {str(witness / n): historical_pin(witness / n, seal[k], old, new, boot)
            for n, k in (('intent.json', 'intentPin'), ('report.json', 'reportPin'))}
    require(pin(witness / 'seal.json')['epoch'][7] / 1e9 <= boot, 'Seal must predate reboot')
    pins[str(witness / 'seal.json')] = pin(witness / 'seal.json')
    root = Path(c['startupJournal']); original = read(root / 'intent.json'); q = original['request']; p = q['predecessor']
    require(startup.valid(q) and q['sourceHash'] == p['sourceHash'] == q['executionSource']['sourceHash'] and
            original == {'kind': startup.KIND, 'reviewHash': digest(q), 'request': q} and
            c['startupReviewHash'] == digest(q) and c['workspaceId'] == workspace and
            c['brainId'] == saved['brainId'] == p['brainId'] and c['startupSource'] == q['executionSource'] and
            c['databases'] == q['databases'] and c['repository'] == q['repository'] and
            c['bindingFile'] == p['bindingFile'] and c['bindingHash'] == p['bindingHash'] and
            c['scope'] == p['scope'] and c['phase'] == q['phase'] and c['missionHash'] == p['missionHash'] and
            c['missionReviewHash'] == p['reviewHash'], 'Original canonical preparation/identity/accounting lineage required')
    old_identity = q['databases']['workspace:' + workspace]['identity']
    require(saved['databaseIdentity'] == old_identity == [old, ledger.db.stat().st_ino] and
            q['journal'] == str(registry.root / 'prestart-startups' / digest({'workspaceId': workspace,
                                'ledgerIdentity': old_identity})) and root == Path(q['journal']) and
            q['mailbox'] == str(ledger.root / ('startup-preparation-' + root.name[:24])),
            'Original inode and canonical startup required; never rearm under a new device')
    owner = {'kind': startup.KIND, 'reviewHash': digest(q), 'journal': str(root)}
    require(read(ledger.root / startup.FENCE) == read(ledger.root / startup.ANCHOR) == owner,
            'Both permanent startup fences must remain unchanged')
    require({f.name for f in root.iterdir()} == worker.JOURNAL and
            {str(f) for f in Path(q['mailbox']).iterdir()} ==
            {f for f in c['files'] if Path(f).parent == Path(q['mailbox'])},
            'Partial, Stop, permission or unlisted startup/mailbox records stay fenced')
    required = {str(root / n) for n in worker.JOURNAL} | {str(ledger.root / n) for n in (startup.FENCE, startup.ANCHOR)}
    required |= set(p['sidecarPins']) | {p['bindingFile']} | {str(f) for f in Path(q['mailbox']).iterdir()}
    require(set(c['files']) == required and all(c['files'][f] == v for f, v in p['sidecarPins'].items()) and
            c['files'][p['bindingFile']] == p['bindingPin'], 'Complete original effect-independent pin inventory required')
    pins.update({f: historical_pin(f, expected, old, new, boot) for f, expected in c['files'].items()})
    actual = databases(registry)
    require(set(actual) == set(q['databases']), 'Registered database inventory changed')
    for key, v in actual.items():
        before = q['databases'][key]
        require(v['path'] == before['path'] and v['fingerprint'] == before['fingerprint'] and
                v['identity'] == [new, before['identity'][1]] and before['identity'][0] == old,
                'All original database schemas, rows and inodes must match; missing usage is not zero')
    with startup.standard.read_db(ledger.db) as db:
        meta = ledger.get(db, 'meta', 1); commands = ledger.all(db, 'commands')
        require(meta['schemaVersion'] == 7 and meta['paused'] is True and digest(meta) == p['metaHash'] and
                not any(meta.get(k) for k in ('standardRun', 'controller', 'runner', 'admissionBinding', 'brainHandoff')) and
                all(not ledger.all(db, k) for k in ('workers', 'queue', 'decisions', 'continuations')) and
                commands == [p['command']], 'Exact empty paused admitted state and original queued request required')
    failure = commands[0].get('notification') or {}
    require(commands[0]['status'] == 'queued' and commands[0]['kind'] == startup.standard.CATALOG_REFRESH_KIND and
            failure.get('status') == 'unavailable' and failure.get('nativeFailure') == {
                'version': 1, 'stage': 'authentication_check', 'reason': 'deadline_exceeded',
                'resumeAttempted': False, 'turnStartAttempted': False}, 'Positive original pre-load failure only; no unknown delivery')
    out, turn, receipt, usage = (read(root / n) for n in ('outcome.json', 'turn.json', 'receipt.json', 'usage.json'))
    require(out == {'kind': startup.KIND, 'reviewHash': digest(q), 'status': out.get('status'),
                'nativeTurnId': turn.get('nativeTurnId'), 'lastStage': 'original_connection_observation',
                'turnStartAttempted': True, 'connectionClosed': True, 'reconnectAllowed': False,
                'originalReadinessOutcome': 'unqualified_preserved', 'terminalSafety': 'unknown', 'pilotAccepted': False} and
            out['status'] in ('startup_preparation_completed', 'startup_budget_checkpoint') and
            turn == {'reviewHash': digest(q), 'nativeTurnId': c['nativeTurnId']} and
            receipt['reviewHash'] == digest(q) and receipt['nativeTurnId'] == c['nativeTurnId'] and
            receipt['requestPin'] == c['files'][str(Path(q['mailbox']) / 'request.json')] and
            c['usage'] == usage and usage['oldUsageChanged'] is False and usage['coverage'] == 'per_turn_not_lifetime',
            'Positive closed preparation and exact retained usage required; no receipt fabrication')
    box = Path(q['mailbox']); h = read(box / 'handoff.json')
    require(h['source'] == q['executionSource']['root'] and h['sourceHash'] == q['sourceHash'] and
            h['reviewHash'] == digest(q) and h['startupId'] == root.name and h['brainId'] == p['brainId'] and
            h['boundary'] == startup.BOUNDARY and
            read(box / 'request.json') == {'protocol': startup.mailbox.PROTOCOL, 'handoffHash': digest(h), 'result': receipt['result']} and
            read(box / 'reply.json') == {'startupId': root.name, 'status': 'new_startup_result_recorded',
                'receiptHash': digest(receipt), 'playAuthorized': False} and
            read(root / 'receipt.claim.json') == {'reviewHash': digest(q), 'nativeTurnId': c['nativeTurnId'],
                'requestPin': c['files'][str(box / 'request.json')]} and
            read(root / 'turn-pin.json') == c['files'][str(box / 'turn.json')] and
            read(root / 'load.claim.json') == {'reviewHash': digest(q), 'loadRequired': q['before']['activity'] == 'notLoaded'} and
            read(root / 'turn.claim.json') == {'reviewHash': digest(q), 'purpose': startup.mailbox.PURPOSE} and
            type(receipt['recordedAt']) in (int, float) and math.isfinite(receipt['recordedAt']) and
            0 < receipt['recordedAt'] <= boot, 'Original publication, receipt/reply and permanent claims must agree')
    n = usage['observedLastTurnTokens']
    require(n is None or type(n) is int and 0 <= n <= 1000000000, 'Unknown usage stays unknown')
    require(type(usage['chargedReservationFloor']) is int and type(usage['futurePhaseCeiling']) is int and
            usage['chargedReservationFloor'] == max(q['phase']['maxTokens'], n or 0) and
            usage['futurePhaseCeiling'] == max(0, usage['carriedPhaseCeiling'] - usage['chargedReservationFloor']) and
            usage['carriedPhaseCeiling'] == q['phase']['carriedPhaseCeiling'] and
            'lifetime_coverage_not_asserted' in usage['gaps'] and
            (n is not None or 'startup_usage_missing_or_incomplete' in usage['gaps']) and
            out['status'] == ('startup_budget_checkpoint' if n is not None and n > q['phase']['maxTokens']
                              else 'startup_preparation_completed'), 'Preserve reservation/overrun and coverage gaps')
    proofs = [source_epoch(q['executionSource'], old, new, boot, (worker.PR189_SOURCE, startup.owned.preplay.source_hash())),
              source_epoch(p['originalSource'], old, new, boot, (startup.prior.PR187_SOURCE, startup.owned.preplay.source_hash()))]
    require(startup.git_view(p['scope']['checkout'], ledger.root) == q['repository'], 'Checkout drift requires separate review')
    binding = read(p['bindingFile'])
    require(digest(binding) == p['bindingHash'], 'Preserve original binding bytes')
    endpoint = retired_endpoint(binding)
    require(boot_session() == session, 'Boot session changed during inspection')
    return {'workspaceId': workspace, 'root': str(ledger.root), 'brainId': p['brainId'],
            'startupReviewHash': digest(q), 'oldDevice': old, 'currentDevice': new,
            'bootedAt': reviewed_boot['bootedAt'], 'bootSessionUuid': session,
            'checkout': p['scope']['checkout'],
            'databases': actual, 'files': pins, 'sourceEpochs': proofs, 'bindingHash': p['bindingHash'],
            'retiredEndpoint': endpoint,
            'originalReadinessCommand': commands[0]['id'], 'originalUsage': usage,
            'historicalObservedAt': report['observedAt'], 'historicalThroughAt': report['throughAt'],
            'boundary': dict(BOUNDARY)}


def prepare(platform, workspace, witness):
    c = context(platform, workspace, witness); registry, ledger, _ = route(platform, workspace)
    journal = location(registry, ledger, c['startupReviewHash'])
    require(not os.path.lexists(journal) and not os.path.lexists(ledger.root / FENCE),
            'Maintenance epoch already claimed or partial; no retry or device/source successor')
    q = {'version': 2, 'kind': KIND, 'sourceHash': startup.owned.preplay.source_hash(), 'workspaceId': workspace,
         'platform': str(registry.root), 'witness': str(Path(witness)), 'context': c,
         'journal': str(journal), 'boundary': dict(BOUNDARY)}
    require(len(canonical(q).encode()) <= 64000, 'Complete bounded maintenance review required')
    return {'request': q, 'reviewHash': digest(q), 'validUntil': 'scope_changes',
            'effect': 'Retain one read-only current-epoch certificate; no registry/binding rewrite or native effect'}


def current(q):
    require(isinstance(q, dict) and set(q) == FIELDS and type(q['version']) is int and q['version'] == 2 and
            q['kind'] == KIND and q['boundary'] == BOUNDARY and
            q['sourceHash'] == startup.owned.preplay.source_hash() and
            isinstance(q['context'], dict) and all(k in q['context'] for k in ('bootSessionUuid', 'bootedAt')) and
            q['context'] == context(q['platform'], q['workspaceId'], q['witness'], reviewed_boot={
                k: q['context'][k] for k in ('bootSessionUuid', 'bootedAt')}), 'Maintenance scope changed')
    registry, ledger, _ = route(q['platform'], q['workspaceId'])
    require(q['journal'] == str(location(registry, ledger, q['context']['startupReviewHash'])), 'Canonical maintenance owner required')
    return registry, ledger


def backup(q, destination, *, writers_stopped=False):
    require(writers_stopped is True, 'Stop older writers before backup')
    registry, ledger = current(q); root = Path(destination); private_path(root.parent, existing=True)
    protected = [registry.root, *[Path(v['path']).parent for v in q['context']['databases'].values()],
                 *[Path(v['root']) for v in q['context']['sourceEpochs']], Path(q['witness']),
                 Path(q['context']['checkout']),
                 *[Path(p) for p in q['context']['retiredEndpoint'].get('protectedDirectories', [])]]
    require(root.is_absolute() and root.resolve() == root and not os.path.lexists(root) and
            all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in protected), 'New disjoint private backup required')
    root.mkdir(mode=0o700); files = {}
    for index, (key, value) in enumerate(sorted(q['context']['databases'].items())):
        dest = root / ('database-'+str(index)+'.sqlite3')
        os.close(os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
        with startup.standard.read_db(value['path']) as src, contextlib.closing(sqlite3.connect(dest)) as dst:
            src.backup(dst)
            require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Backup integrity failed')
            dst.execute('PRAGMA journal_mode=DELETE')
        require(partial.database_proof(dest)['fingerprint'] == value['fingerprint'], 'Backup contents changed')
        files[dest.name] = {'key': key, 'fingerprint': value['fingerprint']}
        with dest.open('rb') as stream: os.fsync(stream.fileno())
    for index, (path, expected) in enumerate(sorted(q['context']['files'].items())):
        dest = root / ('input-'+str(index)+'.json')
        require(pin(path) == expected, 'Original input changed before backup')
        with os.fdopen(os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
            stream.write(Path(path).read_bytes()); stream.flush(); os.fsync(stream.fileno())
        require(pin(dest)['sha256'] == expected['sha256'] and pin(path) == expected, 'Input backup mismatch')
        files[dest.name] = {'pin': pin(dest), 'original': path}
    exclusive(root / 'manifest.json', {'kind': KIND, 'reviewHash': digest(q), 'files': files})
    current(q); sync_directory(root)
    return {'backup': str(root), 'reviewHash': digest(q), 'verified': True}


def verify_backup(q, root):
    root = private_path(root, existing=True); m = read(root / 'manifest.json')
    require(set(m) == {'kind', 'reviewHash', 'files'} and m['kind'] == KIND and m['reviewHash'] == digest(q) and
            {p.name for p in root.iterdir()} == set(m['files']) | {'manifest.json'}, 'Complete exact backup required')
    dbs = q['context']['databases']; originals = q['context']['files']
    expected = {'database-'+str(i)+'.sqlite3' for i in range(len(dbs))} | {'input-'+str(i)+'.json' for i in range(len(originals))}
    require(set(m['files']) == expected, 'Backup inventory incomplete')
    for index, (key, value) in enumerate(sorted(dbs.items())):
        e = m['files']['database-'+str(index)+'.sqlite3']
        require(e == {'key': key, 'fingerprint': value['fingerprint']} and
                partial.database_proof(root / ('database-'+str(index)+'.sqlite3'))['fingerprint'] == value['fingerprint'],
                'Full backup schema and contents required')
    for index, (path, expected_pin) in enumerate(sorted(originals.items())):
        name = 'input-'+str(index)+'.json'; e = m['files'][name]
        require(e == {'pin': pin(root / name), 'original': path} and
                e['pin']['sha256'] == expected_pin['sha256'], 'Immutable input backup changed')


def confirm(q, review_hash, backup_root, *, writers_stopped=False):
    require(review_hash == digest(q) and writers_stopped is True, 'Exact new maintenance confirmation and stopped writers required')
    registry, ledger = current(q); verify_backup(q, backup_root)
    with partial.lock(registry.db), partial.lock(ledger.db), recovery.dashboard_lock(ledger.root):
        current(q); verify_backup(q, backup_root)
        root = Path(q['journal']); root.parent.mkdir(mode=0o700, exist_ok=True); private_path(root.parent, existing=True)
        require(not os.path.lexists(root) and not os.path.lexists(ledger.root / FENCE), 'Canonical claim consumed; inspect only')
        root.mkdir(mode=0o700)
        exclusive(root / 'intent.json', {'kind': KIND, 'reviewHash': review_hash, 'request': q})
        exclusive(ledger.root / FENCE, {'kind': KIND, 'reviewHash': review_hash, 'journal': str(root)})
        current(q)
        exclusive(root / 'result.json', {'kind': KIND, 'reviewHash': review_hash, 'status': 'maintenance_epoch_retained',
                  'backup': str(Path(backup_root)), 'boundary': dict(BOUNDARY)})
    return status(q)


def status(q):
    """Local read-only maintenance; never a normal route, native RPC or renewal."""
    registry, ledger = current(q); root = Path(q['journal'])
    require(read(root / 'intent.json') == {'kind': KIND, 'reviewHash': digest(q), 'request': q} and
            read(ledger.root / FENCE) == {'kind': KIND, 'reviewHash': digest(q), 'journal': str(root)} and
            {p.name for p in root.iterdir()} == {'intent.json', 'result.json'}, 'Partial maintenance remains consumed and unknown')
    result = read(root / 'result.json')
    require(set(result) == {'kind', 'reviewHash', 'status', 'backup', 'boundary'} and result['kind'] == KIND and
            result['reviewHash'] == digest(q) and result['status'] == 'maintenance_epoch_retained' and result['boundary'] == BOUNDARY,
            'Exact completed maintenance certificate required')
    verify_backup(q, result['backup'])
    return {'status': result['status'], 'reviewHash': digest(q), 'workspaceId': q['workspaceId'],
            'maintenanceIdentityRecognized': True, 'normalWritesBlocked': True,
            'blockers': ['native_host_binding_unavailable', 'loaded_policy_unknown_no_reload_authorized', 'worker_phase_authority_separate'],
            'historicalObservedAt': q['context']['historicalObservedAt'], 'boundary': dict(BOUNDARY)}


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('prepare'); a.add_argument('platform'); a.add_argument('workspace'); a.add_argument('witness')
    for action in ('backup', 'confirm', 'status'):
        a = sub.add_parser(action); a.add_argument('review')
        if action != 'status': a.add_argument('backup'); a.add_argument('--writers-stopped', action='store_true')
        if action == 'confirm': a.add_argument('--confirm-hash', required=True)
    a = p.parse_args()
    if a.action == 'prepare': result = prepare(a.platform, a.workspace, a.witness)
    else:
        q = read(a.review)
        result = status(q) if a.action == 'status' else backup(q, a.backup, writers_stopped=a.writers_stopped) if a.action == 'backup' else \
                 confirm(q, a.confirm_hash, a.backup, writers_stopped=a.writers_stopped)
    print(canonical(result))


if __name__ == '__main__':
    try: main()
    except (Refusal, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(canonical({'error': str(error), 'boundary': BOUNDARY})); raise SystemExit(2)
