"""Complete local discovery in eight fresh stdlib processes, no native pilot.

Retains exact discovery multiplicity and every result/log in a new private
temporary directory. No workflow, provider, download or live repair is invoked.
"""
import collections
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOURCE)); sys.path.insert(0, str(SOURCE / 'tests'))
from orchestrator.standard_preplay import source_hash


def save(root, name, value):
    with os.fdopen(os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as stream:
        json.dump(value, stream, sort_keys=True); stream.flush(); os.fsync(stream.fileno())


def flat(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite): yield from flat(item)
        else: yield item.id()


def worker(root, index):
    os.umask(0o022)  # Permission fixtures deliberately create public directories.
    inventory = json.loads((root / 'test-inventory.json').read_text())
    ids = inventory['ids'][index::8]; before = source_hash()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in ids)
    if collections.Counter(flat(suite)) != collections.Counter(ids): raise RuntimeError('Discovery changed')
    result = unittest.TextTestRunner(verbosity=2).run(suite); after = source_hash()
    success = result.wasSuccessful() and before == after == inventory['sourceHash']
    save(root, f'python-part-{index}-result.json', {'ids': ids, 'testsRun': result.testsRun,
         'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
         'sourceHash': before, 'afterSourceHash': after, 'success': success})
    return 0 if success else 1


def main():
    os.umask(0o077); os.chdir(SOURCE)
    root = Path(tempfile.mkdtemp(prefix='post-reboot-qualified.')).resolve()
    ids = list(flat(unittest.defaultTestLoader.discover(str(SOURCE / 'tests')))); before = source_hash()
    save(root, 'test-inventory.json', {'ids': ids, 'cases': len(ids),
         'multiplicity': dict(collections.Counter(ids)), 'sourceHash': before})
    print(json.dumps({'qualificationDirectory': str(root), 'cases': len(ids), 'sourceHash': before}), flush=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1'); processes = []
    for index in range(8):
        log = open(root / f'python-part-{index}.log', 'xb')
        process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), str(root), str(index)],
                                   cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT, umask=0o022)
        processes.append((process, log))
    while any(p.poll() is None for p, _ in processes): time.sleep(.25)
    for _, log in processes: log.close()
    parts = [json.loads((root / f'python-part-{i}-result.json').read_text()) for i in range(8)]
    exact = collections.Counter(i for p in parts for i in p['ids']) == collections.Counter(ids)
    after = source_hash()
    passed = exact and all(p['success'] for p in parts) and before == after
    record = {'status': 'passed' if passed else 'failed', 'fullDiscoveryMultiplicityExact': exact,
              'testsRun': sum(p['testsRun'] for p in parts), 'failures': sum(p['failures'] for p in parts),
              'errors': sum(p['errors'] for p in parts), 'skipped': sum(p['skipped'] for p in parts),
              'sourceHash': before, 'afterSourceHash': after}
    save(root, 'python-complete-result.json', record); print(json.dumps(record), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(worker(Path(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) == 3 else main())
