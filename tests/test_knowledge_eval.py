"""Fixed, source-checked retrieval questions for the tooling repository at HEAD.

The expected modules are manually reviewed implementation owners, not inferred
acceptance evidence. A later revision must re-review this evaluation set.
"""
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from orchestrator.core import Ledger
from orchestrator import project_knowledge as knowledge


QUESTIONS = [
    ('How does a standard phase Play preview bind owner review?', 'orchestrator/standard.py'),
    ('Where are brain conversation messages retained and replied to?', 'orchestrator/conversation.py'),
    ('How is browser authentication remembered for a local client?', 'orchestrator/browser_auth.py'),
    ('How are narrative roadmap current and historical sections classified?', 'orchestrator/roadmaps.py'),
    ('Where are local Codex token counters observed?', 'orchestrator/observations.py'),
    ('How are native Codex project catalog bindings retained?', 'orchestrator/projects.py'),
    ('Which assistant state metadata is safe for inference?', 'orchestrator/assistant_state.py'),
    ('How is the executive inference prompt assembled?', 'orchestrator/inference.py'),
    ('How are notification delivery instructions prepared?', 'orchestrator/notification.py'),
    ('How does a workspace pause request settle?', 'orchestrator/workspace_pause.py'),
    ('Where are model capability and effort selections checked?', 'orchestrator/model_policy.py'),
    ('How is an exact PR merge handoff verified?', 'orchestrator/standard_merge.py'),
    ('How does dashboard browser history navigation work?', 'web/routing.js'),
    ('Where are artifact retention controls applied?', 'orchestrator/retention_controls.py'),
    ('How are repository Git blobs and revisions observed?', 'orchestrator/repository.py'),
    ('How does source observation track local checkout provenance?', 'orchestrator/source_observation.py'),
    ('How are native task lifecycle states reconciled?', 'orchestrator/native_lifecycle.py'),
    ('How are phase checkpoint decisions recorded?', 'orchestrator/phase_checkpoints.py'),
    ('Where are worker results independently reviewed?', 'orchestrator/result_review.py'),
    ('How does dashboard standard run status render?', 'web/standard.js'),
]


class KnowledgeEvaluationTest(unittest.TestCase):
    def test_twenty_real_questions_and_missing_evidence(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / 'private')
            ledger.initialize({'schemaVersion': 1, 'brainId': str(uuid.uuid4()), 'repositories': [
                {'id': 'tooling', 'path': str(repo), 'projectId': 'projectless', 'ref': 'HEAD',
                 'policyProfile': 'standard', 'mergePolicy': 'manual'}]})
            (ledger.root / 'knowledge.json').write_text(json.dumps({
                'schemaVersion': 1, 'repositories': {'tooling': ['orchestrator/', 'web/']},
                'graphify': None}))
            state = knowledge.refresh(ledger, 'tooling')
            self.assertEqual(state['commit'], knowledge._git(repo, 'rev-parse', 'HEAD', maximum=100).decode().strip())
            correct, misses = 0, []
            # Evaluate the version-pinned index at HEAD, independently of this test
            # process's uncommitted source changes; freshness is covered separately.
            with patch.object(knowledge, 'status', return_value={**state, 'status': 'current'}):
                for question, expected in QUESTIONS:
                    result = knowledge.search(ledger, 'tooling', question)
                    for hit in result['results']:
                        citation = knowledge.source(ledger, 'tooling', hit['indexHash'], hit['path'], hit['line'])
                        self.assertEqual(citation['commit'], hit['commit'])
                    matched = any(hit['path'] == expected for hit in result['results'])
                    correct += matched
                    if not matched: misses.append((question, [hit['path'] for hit in result['results']]))
            self.assertGreaterEqual(correct, 18, f'Only {correct}/20 expected sources retrieved: {misses}')
            for missing in ('NONEXISTENT_XYZ_PRIVILEGE', 'UNRECORDED_MARS_ACCEPTANCE_SIGNOFF'):
                self.assertEqual(knowledge.search(ledger, 'tooling', missing)['results'], [])
            print(f'Knowledge retrieval: {correct}/20 expected sources in top ten; 2 missing-evidence identifiers returned no citations')


if __name__ == '__main__':
    unittest.main()
