"""Local source qualification; disposable tests only, no live native connection.

Retain full logs in a newly created private evidence directory outside source.
Does not install source, start/rebind a live host, send a control or run paid CI.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SOURCE = Path(__file__).resolve().parents[1]


def qualify(evidence):
    evidence = evidence.resolve(strict=True)
    if evidence.is_relative_to(SOURCE) or any(evidence.iterdir()):
        raise ValueError('Use a new empty private evidence directory outside source')
    if evidence.stat().st_uid != os.getuid() or evidence.stat().st_mode & 0o077:
        raise ValueError('Private owner-only evidence directory required')
    records = []
    def source_pin():
        files = sorted(p for directory in ('orchestrator', 'scripts', 'tests', 'web')
                       for p in (SOURCE / directory).iterdir() if p.suffix in ('.py', '.js'))
        contents = {str(p.relative_to(SOURCE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
        return hashlib.sha256(json.dumps(contents, sort_keys=True).encode()).hexdigest()
    before = source_pin()

    def run(name, argv):
        started = time.monotonic()
        print('Starting ' + name, flush=True)
        with (evidence / (name + '.log')).open('xb') as stream:
            os.chmod(stream.name, 0o600)
            result = subprocess.run(argv, cwd=SOURCE, stdout=stream, stderr=subprocess.STDOUT,
                                    env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=3600)
        record = {'name': name, 'argv': argv, 'exitCode': result.returncode,
                  'seconds': round(time.monotonic()-started, 3)}
        records.append(record)
        print(json.dumps(record), flush=True)
        if result.returncode:
            raise RuntimeError(name + ' failed; inspect the retained log')

    run('python-full', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
    javascript = sorted(SOURCE.glob('tests/test_*.js'))
    for file in javascript:
        run(file.stem, ['node', str(file.relative_to(SOURCE))])
    syntax = sorted(SOURCE.glob('web/*.js'))
    for file in syntax:
        run('syntax-' + file.stem, ['node', '--check', str(file.relative_to(SOURCE))])
    python = sorted(SOURCE.glob('orchestrator/*.py')) + sorted(SOURCE.glob('scripts/*.py'))
    for file in python:
        ast.parse(file.read_text(), filename=str(file))
    run('diff-check', ['git', 'diff', '--check'])
    if source_pin() != before:
        raise RuntimeError('Source changed during qualification; rerun the full suite on final bytes')
    summary = {'sourceQualificationOnly': True, 'pythonSuitePassed': True,
               'qualifiedSourceHash': before,
               'javascriptSuites': len(javascript), 'syntaxChecks': len(syntax),
               'pythonAstFiles': len(python), 'records': records,
               'liveNativeWrites': 0, 'installed': False, 'pilotAccepted': False}
    with (evidence / 'summary.json').open('x') as stream:
        os.chmod(stream.name, 0o600)
        json.dump(summary, stream, indent=2)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.evidence), indent=2))
