from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from orchestrator.installed_codex import resolve_cli, open_desktop_brain

OLD = '/Applications/ChatGPT.app/Contents/Resources/codex'
NEW = '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'


class InstalledCodexTest(unittest.TestCase):
    @patch('orchestrator.installed_codex.sys.platform', 'darwin')
    @patch.object(Path, 'is_dir', return_value=True)
    @patch.object(Path, 'resolve', autospec=True, side_effect=lambda p, **kw: p)
    @patch('orchestrator.installed_codex.subprocess.run')
    def test_desktop_open_uses_only_verified_bundle_and_exact_native_link(self, run, *_):
        brain='11111111-1111-4111-8111-111111111111'
        run.return_value=subprocess.CompletedProcess([],0)
        self.assertTrue(open_desktop_brain(NEW,brain))
        self.assertEqual(run.call_args_list[-1].args[0],['/usr/bin/open','-g','-a','/Applications/ChatGPT.app','codex://threads/'+brain])
        run.reset_mock();run.return_value=subprocess.CompletedProcess([],1)
        self.assertFalse(open_desktop_brain(NEW,brain));self.assertEqual(run.call_count,1)
        run.reset_mock()
        self.assertFalse(open_desktop_brain('/tmp/codex',brain))
        self.assertFalse(open_desktop_brain(NEW,brain+'?prompt=unsafe'))
        run.assert_not_called()

    @patch('orchestrator.installed_codex.sys.platform', 'darwin')
    @patch.object(Path, 'exists', return_value=False)
    @patch.object(Path, 'is_file', return_value=True)
    @patch.object(Path, 'resolve', autospec=True, side_effect=lambda p, **kw: p)
    @patch('orchestrator.installed_codex.subprocess.run')
    def test_only_signed_known_bundle_relocation(self, run, *_):
        run.return_value = subprocess.CompletedProcess([], 0)
        self.assertEqual(resolve_cli(OLD), Path(NEW))
        argv = run.call_args.args[0]
        self.assertEqual(argv[0], '/usr/bin/codesign')
        self.assertIn('2DC432GLL2', argv[3])
        self.assertEqual(argv[-1], NEW)
        run.return_value = subprocess.CompletedProcess([], 1)
        self.assertEqual(resolve_cli(OLD), Path(OLD))
        run.side_effect = subprocess.TimeoutExpired([], 5)
        self.assertEqual(resolve_cli(OLD), Path(OLD))

    @patch('orchestrator.installed_codex.subprocess.run')
    def test_existing_or_arbitrary_missing_path_never_discovers_or_executes(self, run):
        with patch.object(Path, 'exists', return_value=True):
            self.assertEqual(resolve_cli(OLD), Path(OLD))
        with patch.object(Path, 'exists', return_value=False):
            for path in ['/tmp/ChatGPT.app/Contents/Resources/codex',
                         '/Applications/Other.app/Contents/Resources/codex',
                         '/missing/codex', 'codex']:
                self.assertEqual(resolve_cli(path), Path(path))
        run.assert_not_called()

    @patch('orchestrator.installed_codex.sys.platform', 'darwin')
    @patch.object(Path, 'exists', return_value=False)
    @patch.object(Path, 'is_file', return_value=True)
    @patch.object(Path, 'resolve', return_value=Path('/tmp/substituted'))
    @patch('orchestrator.installed_codex.subprocess.run')
    def test_symlink_relocation_refused(self, run, *_):
        self.assertEqual(resolve_cli(OLD), Path(OLD))
        run.assert_not_called()
