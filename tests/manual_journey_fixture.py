"""Disposable Roadmap & Play browser fixture; no native tasks or live data.

Run: python3 tests/manual_journey_fixture.py --port 8797
Uses the local signed-control API with temporary ledgers and a temporary Git repo.
Every project is synthetic. No notifier, inference service or scheduler is enabled.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import contextlib
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator.core import Ledger
from orchestrator.server import Dashboard, WorkspaceRuntime
from orchestrator.standard import brain, read
from test_standard import StandardTest
from test_assistant import CONFIG
from orchestrator.missions import change
from test_missions import specification, request

original_snapshot = WorkspaceRuntime.snapshot
ASSISTANT = False
LONG_REPORT = ('Implemented search and source navigation. Corrected project isolation checks. '
               'No merge or live rollout occurred. '
               'Verification covered version-bound citations, explicit missing evidence and bounded excerpts. ' * 6)


def snapshot(runtime):
    state = original_snapshot(runtime)
    if ASSISTANT:
        state['inference'].update(configured=True, model=CONFIG.model, assistantModel=CONFIG.model)
    state['workspace']['name'] = 'Disposable UX preview · ' + runtime.workspace_id
    if runtime.workspace_id == 'completed':
        state['standard']['run']['checkpoint']['summary'] = LONG_REPORT
    # Display-only roadmap example. It is deliberately not a source-reading or
    # admission fixture: the registered ledger remains authoritative for writes.
    state['observations']['roadmaps'] = {'plans': [{
        'repository': 'a', 'path': 'docs/ROADMAP.md',
        'title': 'Product roadmap · synthetic preview', 'status': 'observed',
        'commit': 'a' * 40, 'at': 0, 'documentId': None,
        'items': [{'checked': True, 'label': 'Prepare the project foundation', 'line': 3, 'scope': 'current'},
                  {'checked': False, 'label': 'Deliver one reviewed feature phase', 'line': 4, 'scope': 'current'}]
    }], 'drafts': []}
    return state


def assistant_reply(route, payload, **options):
    data = json.loads(payload['messages'][-1]['content'])
    question = data['conversation'][-1]['content'].lower()
    actions = {a['key']:a for a in data['snapshot']['actions']}
    preferred = (['usage_check'] if 'usage' in question else ['phase_pause'] if 'pause' in question else
                 ['phase_resume'] if 'resume' in question else ['phase_prepare'] if 'prepare' in question and 'next phase' in question else
                 ['phase_review','codex_check','phase_play','phase_prepare'])
    key = next((k for k in preferred if actions.get(k, {}).get('available')), None)
    result = {'answer':'Here is the next step for this disposable project. Review it and confirm here when ready.',
              'links':[], 'evidence':['F42'], 'action':{'key':key} if key else None}
    return {'model':CONFIG.model,'request_key_source':'local-inference','usage':{'total_tokens':60},
            'choices':[{'finish_reason':'stop','message':{'content':json.dumps(result)}}]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8797)
    parser.add_argument('--assistant', action='store_true', help='Mock local inference for conversational phase QA')
    args = parser.parse_args()
    ASSISTANT = args.assistant
    fixture = StandardTest()
    fixture.setUp()
    try:
        subprocess.run(['git', '-C', str(fixture.repo), '-c', 'user.name=Disposable fixture',
                        '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty',
                        '-qm', 'Disposable preview'], check=True)
        (fixture.root / 'empty-codex-logs').mkdir()
        for identity in ['alpha', 'draft', 'running', 'paused', 'completed', 'needs-catalog']:
            ledger, token = (fixture.ledger, fixture.token) if identity == 'alpha' else fixture.workspace(identity)
            (ledger.root / 'observations.json').write_text(json.dumps({'codexHome': str(fixture.root / 'empty-codex-logs')}))
            if identity == 'draft':
                from orchestrator.missions import read as mission_read
                change(ledger, request(spec=specification(mode='phase_delegated'), expectedRevision=mission_read(ledger)['revision']))
            if identity in ('running', 'paused', 'completed'):
                fixture.control(ledger=ledger)
                run_id = read(ledger)['run']['id']
                brain(fixture.registry, ledger, token, {'operation': 'receive', 'runId': run_id})
                if identity == 'completed':
                    def call(operation, **values):
                        return brain(fixture.registry, ledger, token, {'operation': operation, 'runId': run_id, **values})
                    call('claim', id='fixture-task', repository='a', title='Synthetic completed task',
                         paths=['tests/test_fixture.py'], instructions='Synthetic fixture only.',
                         acceptance=['Synthetic evidence'], model='fixture', effort='low',
                         rationale='UI fixture', allowance=1000)
                    call('issue', taskId='fixture-task')
                    call('bind', taskId='fixture-task', threadId=str(uuid.uuid4()), clientThreadId=None, hostId='local')
                    call('observe', taskId='fixture-task', nativeStatus='completed', observedTokens=None,
                         trackedTerminals='none', observedAt=time.time(), source='Synthetic browser fixture')
                    call('finish', taskId='fixture-task', outcome='completed', evidence={
                        'source': 'Synthetic commit', 'tests': 'Synthetic tests', 'artifacts': [],
                        'preservation': 'Disposable fixture', 'summary': 'Synthetic evidence only; no native task ran.'})
                if identity != 'running':
                    if identity == 'paused':
                        fixture.control('pause', ledger=ledger)
                        brain(fixture.registry, ledger, token, {'operation': 'receive', 'runId': run_id})
                    brain(fixture.registry, ledger, token, {'operation': 'checkpoint', 'runId': run_id,
                          'outcome': identity, 'summary': 'Synthetic checkpoint: review the result before continuing.',
                          'brainObservedTokens': None})
            if identity == 'needs-catalog':
                with ledger.tx() as db:
                    meta = ledger.get(db, 'meta', 1)
                    meta.pop('standardCatalog', None)
                    ledger.put(db, 'meta', 1, meta)
            ledger.release(token, 'Synthetic fixture setup complete. No native effects.')
        ledger = Ledger(fixture.root / 'needs-plan')
        ledger.initialize({'schemaVersion': 1, 'brainId': 'fixture-brain', 'repositories': [
            {'id': 'a', 'path': str(fixture.repo), 'projectId': 'projectless', 'ref': 'HEAD',
             'policyProfile': 'standard', 'mergePolicy': 'manual'}]})
        fixture.registry.register('needs-plan', 'needs-plan', ledger.root)
        server = Dashboard(fixture.ledger, args.port, inference_env=fixture.root / '.env',
                           runtime_root=fixture.root, registry=fixture.registry)
        server.bootstrap = 'disposable-roadmap-journey-preview'
        print(server.origin + '/#token=' + server.bootstrap, flush=True)
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(WorkspaceRuntime, 'snapshot', snapshot))
            if ASSISTANT:
                stack.enter_context(patch('orchestrator.assistant.settings', return_value=CONFIG))
                stack.enter_context(patch('orchestrator.assistant.Client.request', side_effect=assistant_reply))
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    finally:
        fixture.tearDown()
