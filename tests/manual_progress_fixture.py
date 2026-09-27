"""Disposable receipt-to-next-step browser rehearsal; no native or inference calls.

Run with a terminal: python3 tests/manual_progress_fixture.py --port 8774
Send and confirm a brain message in the assistant, then type `reply` here. The
fixture retains a synthetic reply/draft. Polling/reloading must update the UI.
Type `quit` to close and delete the temporary ledger/repository.
"""
import argparse
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from test_assistant_journey import AssistantJourneyTest
from test_missions import request, specification
from orchestrator import conversation, missions
from orchestrator.server import Dashboard


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8774)
    args = parser.parse_args()
    fixture = AssistantJourneyTest(); fixture.setUp()
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
