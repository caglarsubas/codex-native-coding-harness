import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch
from types import SimpleNamespace

from orchestrator.core import Ledger, Refusal
from orchestrator import project_knowledge as knowledge


class ProjectKnowledgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        (self.repo / 'src').mkdir(parents=True)
        (self.repo / 'src' / 'service.py').write_text('def approve_packet():\n    return "reviewed"\n')
        (self.repo / 'src' / 'secret.env').write_text('PRIVATE_KEY=hidden\n')
        (self.repo / 'src' / 'settings.py').symlink_to(self.repo / 'src' / 'service.py')
        subprocess.run(['git', '-C', str(self.repo), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.email=test@example.invalid',
                        '-c', 'user.name=Fixture', 'commit', '-qm', 'initial'], check=True)
        self.ledger = Ledger(self.root / 'private')
        self.ledger.initialize({'schemaVersion': 1, 'brainId': str(uuid.uuid4()), 'repositories': [
            {'id': 'app', 'path': str(self.repo), 'projectId': 'projectless', 'ref': 'HEAD',
             'policyProfile': 'standard', 'mergePolicy': 'manual'}]})
        (self.ledger.root / 'knowledge.json').write_text(json.dumps({
            'schemaVersion': 1, 'repositories': {'app': ['src/']}, 'graphify': None}))

    def test_private_index_citations_staleness_and_history(self):
        initial = knowledge.refresh(self.ledger, 'app')
        self.assertEqual(initial['status'], 'current')
        self.assertEqual(initial['fileCount'], 1)
        result = knowledge.search(self.ledger, 'app', 'approve_packet')
        self.assertEqual(result['results'][0]['path'], 'src/service.py')
        self.assertEqual(result['results'][0]['line'], 1)
        self.assertNotIn('hidden', json.dumps(result))
        citation = result['results'][0]
        seed = knowledge.seed_references(self.ledger, 'app', self.repo, ['src/service.py', 'src/secret.env'])
        self.assertEqual([item['path'] for item in seed['items']], ['src/service.py'])
        self.assertNotIn('excerpt', seed['items'][0])
        self.assertIn('approve_packet', knowledge.source(self.ledger, 'app', citation['indexHash'],
                                                         citation['path'], citation['line'])['excerpt'])
        (self.repo / 'src' / 'service.py').write_text('def replaced():\n    return "new"\n')
        subprocess.run(['git', '-C', str(self.repo), 'add', 'src/service.py'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.email=test@example.invalid',
                        '-c', 'user.name=Fixture', 'commit', '-qm', 'changed'], check=True)
        self.assertEqual(knowledge.status(self.ledger, 'app')['status'], 'stale')
        self.assertEqual(knowledge.seed_references(self.ledger, 'app', self.repo, ['src/service.py'])['status'], 'stale')
        self.assertIn('approve_packet', knowledge.source(self.ledger, 'app', citation['indexHash'],
                                                        citation['path'], citation['line'])['excerpt'])
        direct = knowledge.search(self.ledger, 'app', 'replaced')
        self.assertEqual(direct['coverage'], 'direct_current_source')
        hit = direct['results'][0]
        self.assertIsNone(hit['indexHash'])
        self.assertIn('replaced', knowledge.direct_source(self.ledger, 'app', hit['commit'], hit['blob'],
                                                         hit['path'], hit['line'])['excerpt'])

    def test_scope_and_symlink_refusals(self):
        knowledge.refresh(self.ledger, 'app')
        with self.assertRaises(Refusal):
            knowledge.search(self.ledger, 'other', 'approve_packet')
        with self.assertRaises(Refusal):
            knowledge.source(self.ledger, 'app', '0' * 64, 'src/secret.env', 1)
        (self.ledger.root / 'knowledge' / 'app' / 'active.json').unlink()
        (self.ledger.root / 'knowledge' / 'app' / 'active.json').symlink_to(self.repo / 'src' / 'service.py')
        with self.assertRaises(Refusal):
            knowledge.status(self.ledger, 'app')

    def test_record_links_use_existing_versions_and_no_body(self):
        with self.ledger.tx() as db:
            db.execute("INSERT INTO observation_records VALUES(?,?)", ('roadmaps', json.dumps({'plans': [{
                'repository': 'app', 'status': 'observed', 'title': 'Pilot roadmap',
                'path': 'docs/ROADMAP.md', 'documentId': 'a' * 64, 'documentVersion': 2,
                'commit': 'b' * 40, 'at': 10}]})))
            db.execute("INSERT INTO artifact_versions VALUES(?,?,?)", ('c' * 64, json.dumps({
                'id': 'c' * 64, 'repository': 'app', 'name': 'Private artifact', 'path': '/private/file.md',
                'version': 3, 'sha256': 'd' * 64, 'observedAt': 12}), b'SECRET BODY'))
        rows = knowledge.record_links(self.ledger, 'app', 'roadmap')
        self.assertEqual(rows['records'][0]['id'], 'a' * 64)
        self.assertNotIn('SECRET BODY', json.dumps(knowledge.record_links(self.ledger, 'app', 'artifact')))
        with self.assertRaises(Refusal):
            knowledge.record_links(self.ledger, 'other', 'roadmap')

    def test_graph_relationships_are_versioned_and_bounded(self):
        (self.repo / 'src' / 'helper.py').write_text('def helper():\n    return 1\n')
        subprocess.run(['git', '-C', str(self.repo), 'add', 'src/helper.py'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.email=test@example.invalid',
                        '-c', 'user.name=Fixture', 'commit', '-qm', 'helper'], check=True)
        def fake_provider(_cfg, stage):
            graph = stage / 'graphify-out' / 'graph.json'
            graph.parent.mkdir()
            raw = json.dumps({'nodes': [{'id': 'service', 'source_file': 'src/service.py', 'label': 'approve_packet'},
                                        {'id': 'helper', 'source_file': 'src/helper.py', 'label': 'helper'}],
                              'edges': [{'source': 'service', 'target': 'helper', 'relation': 'calls', 'confidence': 'EXTRACTED'}]}).encode()
            graph.write_bytes(raw)
            import hashlib
            return {'status': 'ready', 'graphPath': 'graphify-out/graph.json',
                    'graphSha256': hashlib.sha256(raw).hexdigest(), 'version': knowledge.GRAPHIFY_VERSION}
        with patch.object(knowledge, '_provider', fake_provider):
            state = knowledge.refresh(self.ledger, 'app')
        related = knowledge.related(self.ledger, 'app', state['documentHash'], 'src/service.py')
        self.assertEqual(related['items'][0]['path'], 'src/helper.py')
        self.assertEqual(related['items'][0]['provenance'], 'EXTRACTED')
        with self.assertRaises(Refusal):
            knowledge.related(self.ledger, 'app', state['documentHash'], 'src/secret.env')

    def test_pinned_graphify_invocation_has_no_model_environment(self):
        import hashlib
        executable = self.root / 'graphify-test'
        executable.write_text('#!/bin/sh\nexit 0\n')
        executable.chmod(0o700)
        stage = self.root / 'stage'
        (stage / 'src').mkdir(parents=True)
        calls = []
        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            if '--version' in argv:
                return SimpleNamespace(returncode=0, stdout=b'graphify 0.9.66', stderr=b'')
            graph = stage / 'graphify-out' / 'graph.json'
            graph.parent.mkdir()
            graph.write_text('{"nodes":[],"edges":[]}')
            return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
        provider = {'executable': str(executable), 'version': knowledge.GRAPHIFY_VERSION,
                    'sha256': hashlib.sha256(executable.read_bytes()).hexdigest()}
        with patch.object(knowledge.subprocess, 'run', side_effect=run):
            result = knowledge._provider(provider, stage)
        self.assertEqual(result['status'], 'ready')
        self.assertIn('--code-only', calls[-1][0])
        self.assertEqual(calls[-1][1]['env']['HOME'], str(stage))
        self.assertNotIn('OPENAI_API_KEY', calls[-1][1]['env'])
        provider['sha256'] = '0' * 64
        with self.assertRaises(Refusal):
            knowledge._provider(provider, stage)

    def test_missing_graphify_does_not_disable_cited_source_search(self):
        (self.ledger.root / 'knowledge.json').write_text(json.dumps({
            'schemaVersion': 1, 'repositories': {'app': ['src/']},
            'graphify': {'executable': str(self.root / 'missing-graphify'),
                         'version': knowledge.GRAPHIFY_VERSION, 'sha256': '0' * 64}}))
        state = knowledge.refresh(self.ledger, 'app')
        self.assertEqual(state['provider']['status'], 'failed')
        self.assertEqual(knowledge.search(self.ledger, 'app', 'approve_packet')['results'][0]['path'], 'src/service.py')


if __name__ == '__main__':
    unittest.main()
