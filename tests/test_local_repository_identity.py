"""Disposable explicit local-only identity, not native or terminal qualification."""
import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from orchestrator.core import Refusal
from orchestrator.local_repository_identity import inspect
from orchestrator.resources import repository_identity
from orchestrator.standard_successor import disjoint


class LocalIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.a, self.b = self.root/'a', self.root/'b'
        for repo in (self.a, self.b):
            self.git('init', '-q', str(repo))
            self.git('-C', str(repo), '-c', 'user.name=Fixture', '-c', 'user.email=f@example.invalid',
                     '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', repo.name)

    @staticmethod
    def git(*args):
        env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.run(['git', *args], check=True, capture_output=True, env=env).stdout.decode().strip()

    def scope(self, repo): return {'root': str(repo), 'keys': inspect(repo)['keys']}

    def test_explicit_known_absence_is_not_global_unknown_fallback(self):
        self.assertEqual(repository_identity(self.a)['status'], 'unknown')
        proof = inspect(self.a)
        self.assertEqual(proof['remotes'], 'observed_absent')
        self.assertEqual(len(proof['historyRoots']), 1)
        disjoint([self.scope(self.a)], [self.scope(self.b)])
        self.assertEqual(repository_identity(self.a)['status'], 'unknown')

    def test_copy_and_clone_with_removed_origin_share_history_and_refuse(self):
        clone = self.root/'clone'
        self.git('clone', '-q', '--no-hardlinks', str(self.a), str(clone))
        self.git('-C', str(clone), 'remote', 'remove', 'origin')
        for other in (clone, self.root/'copy'):
            if not other.exists(): shutil.copytree(self.a, other)
            with self.assertRaisesRegex(Refusal, 'must not share'):
                disjoint([self.scope(self.a)], [self.scope(other)])

    def test_ordinary_new_commit_keeps_identity_but_unrelated_root_changes_it(self):
        before = inspect(self.a)
        self.git('-C', str(self.a), '-c', 'user.name=Fixture', '-c', 'user.email=f@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '--allow-empty', '-qm', 'next')
        self.assertEqual(before, inspect(self.a))
        self.git('-C', str(self.a), 'fetch', '-q', str(self.b), 'HEAD:refs/heads/unrelated')
        self.assertNotEqual(before, inspect(self.a))

    def test_origin_is_not_ignored_and_unknown_config_never_means_local(self):
        for url in ('file:///private/fixture', 'https://user:fixture-secret@github.com/a/b', 'git@alias:a/b'):
            self.git('-C', str(self.a), 'config', 'remote.origin.url', url)
            with self.assertRaises(Refusal): inspect(self.a)
            with self.assertRaises(Refusal): inspect(self.a, allow_origin=True)
        self.git('-C', str(self.a), 'remote', 'remove', 'origin')
        for key in ('include.path', 'core.fsmonitor', 'extensions.partialclone', 'url.https://alias.insteadof'):
            self.git('-C', str(self.a), 'config', key, 'fixture')
            with self.assertRaises(Refusal): inspect(self.a)
            self.git('-C', str(self.a), 'config', '--unset-all', key)

    def test_foreign_conventional_clone_still_conflicts_with_local_history(self):
        clone = self.root/'clone'; self.git('clone', '-q', '--no-hardlinks', str(self.a), str(clone))
        self.git('-C', str(clone), 'remote', 'set-url', 'origin', 'https://github.com/fixture/product')
        foreign = inspect(clone, allow_origin=True)
        with self.assertRaises(Refusal): disjoint([{'root':str(clone),'keys':foreign['keys']}], [self.scope(self.a)])

    def test_alternates_grafts_shallow_and_replacement_history_are_not_safe(self):
        for relative in ('objects/info/alternates', 'objects/info/http-alternates', 'info/grafts', 'shallow', 'commondir'):
            path = self.a/'.git'/relative; path.parent.mkdir(exist_ok=True)
            path.write_text('fixture\n')
            with self.assertRaises((Refusal, OSError)): inspect(self.a)
            path.unlink()
        head = self.git('-C', str(self.a), 'rev-parse', 'HEAD')
        self.git('-C', str(self.a), 'update-ref', 'refs/replace/'+head, head)
        with self.assertRaises(Refusal): inspect(self.a)

    def test_alias_worktree_and_unborn_are_unsupported(self):
        alias = self.root/'alias'; alias.symlink_to(self.a)
        with self.assertRaises(Refusal): inspect(alias)
        self.git('-C',str(self.a),'worktree','add','--detach',str(self.root/'worktree'))
        with self.assertRaises(Refusal): inspect(self.a)
        with self.assertRaises(Refusal): inspect(self.root/'worktree')
        self.git('init','-q',str(self.root/'unborn'))
        with self.assertRaises(Refusal): inspect(self.root/'unborn')

    def test_configuration_replacement_and_history_drift_change_scope(self):
        before = inspect(self.a); config = self.a/'.git/config'
        replacement = self.a/'.git/config.new'; replacement.write_bytes(config.read_bytes()); replacement.replace(config)
        self.assertNotEqual(before, inspect(self.a))
        self.git('-C',str(self.a),'config','user.name','Changed fixture')
        self.assertNotEqual(before, inspect(self.a))


if __name__ == '__main__': unittest.main()
