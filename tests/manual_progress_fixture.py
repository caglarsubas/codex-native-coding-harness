"""Disposable receipt-to-next-step browser rehearsal; no native or inference calls.

Run with a terminal: python3 tests/manual_progress_fixture.py --port 8774
Add --recovery for an unresolved worker, released controller and budget overrun.
Send and confirm a brain message in the assistant, then type `reply` here. The
fixture retains a synthetic reply/draft. Polling/reloading must update the UI.
Type `quit` to close and delete the temporary ledger/repository.
"""
import argparse
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from test_assistant_journey import AssistantJourneyTest
from test_missions import request, specification
from orchestrator import conversation, missions
from orchestrator.server import Dashboard


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8774)
    parser.add_argument('--recovery', action='store_true', help='Start with an open run, pending worker and budget overrun')
    parser.add_argument('--completed', action='store_true', help='Start at a settled checkpoint needing its next phase')
    args = parser.parse_args()
    fixture = AssistantJourneyTest(); fixture.setUp()
    if args.completed and not args.recovery:
        fixture.fixture.activate(); fixture.fixture.observe(); fixture.fixture.finish()
        fixture.fixture.call('checkpoint', outcome='completed', summary='Disposable completed phase.', brainObservedTokens=None)
    if args.recovery:
        fixture.pending_creation()
        with fixture.ledger.tx() as db:
            meta = fixture.ledger.get(db, 'meta', 1)
            run = meta['standardRun']
            run['limits'].update(tokenBudget=8000000, checkpointReserveTokens=1000000)
            run['usageHighWater'] = 18966347
            run['usageReport'] = {'records':[{'role':'brain'}], 'tokens': {
                'total_tokens':18966347, 'input_tokens':18942144,
                'cached_input_tokens':18764416, 'output_tokens':24203},
                'gaps':['unresolved_native_identity'], 'coverage':'gapped',
                'collectedAt':time.time(), 'through':time.time()}
            fixture.ledger.put(db, 'meta', 1, meta)
        fixture.ledger.release(fixture.fixture.token, 'Disposable fixture: creation ID unresolved; no retry. Usage exceeds the reviewed budget. Next step: reconcile existing work.')
    server = Dashboard(fixture.ledger, args.port, registry=fixture.registry,
                       inference_env=fixture.fixture.root/'no-inference.env')
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    print(server.origin+'/#token='+server.bootstrap, flush=True)
    try:
        for command in sys.stdin:
            if command.strip() == 'quit':
                break
            if command.strip() != 'reply':
                continue
            pending = [c for c in fixture.ledger.snapshot()['commands'] if conversation.pending(c)]
            if len(pending) != 1:
                print('Expected one pending fixture message.', flush=True); continue
            c = pending[0]; token = fixture.fixture.token
            if args.recovery:
                token = fixture.ledger.acquire(fixture.ledger.snapshot()['meta']['brainId']+':fixture-reply')
                conversation.receive(fixture.ledger, token, c['id'])
                conversation.reply(fixture.ledger, token, c['id'], {
                    'message':'The existing worker identity is still unresolved. No worker retry or limit change occurred. Next action: provide the confirmed task link for reconciliation; do not repeat Play.',
                    'artifactIds':[], 'decisionIds':[]})
                fixture.ledger.release(token, 'Fixture recovery reply retained; ownership and usage unchanged.')
                print('Synthetic recovery reply retained; no effects.', flush=True)
                continue
            conversation.receive(fixture.ledger, token, c['id'])
            spec = specification(mode='phase_delegated')
            spec['phase']['id'] = 'next-fixture-phase'
            spec['phase']['title'] = 'Synthetic next phase'
            missions.change(fixture.ledger, request(spec=spec, expectedRevision=missions.read(fixture.ledger)['revision']))
            conversation.reply(fixture.ledger, token, c['id'], {
                'message': 'Next phase draft saved. No Play or worker started. '
                           'The full scope and limits are retained for review. '
                           'This is only a disposable browser test. '
                           'Next exact owner action: review the proposed phase. '
                           'Review does not start development; Play needs a separate confirmation.',
                'artifactIds': [], 'decisionIds': []})
            print('Synthetic reply and draft retained. No native effects.', flush=True)
    finally:
        server.shutdown(); server.server_close(); thread.join(); fixture.tearDown()
