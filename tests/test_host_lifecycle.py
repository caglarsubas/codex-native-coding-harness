import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import sys
from unittest.mock import patch

from orchestrator.core import Refusal, digest
from orchestrator.host_lifecycle import launch, monitor, specification


class HostLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve(); self.root.chmod(0o700)
        self.launcher = self.root / "guarded-launch.zsh"
        self.launcher.write_text("exit 0\n"); self.launcher.chmod(0o600)
        self.spec = {"schemaVersion": 1, "profile": "standard_owned_host_v1", "launcher": str(self.launcher),
                     "launcherSha256": hashlib.sha256(self.launcher.read_bytes()).hexdigest(), "cwd": str(self.root)}
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps(self.spec)); self.manifest.chmod(0o600)
        self.attempt = self.root / "attempt"

    def tearDown(self):
        self.tmp.cleanup()

    def start(self):
        return launch(self.manifest, self.attempt, digest(self.spec))

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "inherited-not-printed"})
    @patch("orchestrator.host_lifecycle.subprocess.Popen")
    def test_exclusive_detached_intent_no_ttl_or_restart(self, popen):
        result = self.start()
        self.assertFalse(result["hostReady"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertNotIn("env", popen.call_args.kwargs, "Inherit current native context, never synthesize or persist its pipe")
        self.assertNotIn("inherited-not-printed", (self.attempt / "launch.json").read_text())
        with self.assertRaisesRegex(Refusal, "already exists"):
            self.start()
        self.assertEqual(popen.call_count, 1)
        popen.reset_mock(); popen.return_value.pid = 123; popen.return_value.wait.return_value = -15
        monitor(self.attempt)
        popen.return_value.wait.assert_called_once_with()
        record = json.loads((self.attempt / "status.json").read_text())
        self.assertEqual(record["signal"], 15)
        self.assertFalse(record["restarted"])
        with self.assertRaisesRegex(Refusal, "already claimed"):
            monitor(self.attempt)
        self.assertEqual(popen.call_count, 1)

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "inherited"})
    def test_start_failure_retains_intent_and_never_retries(self):
        with patch("orchestrator.host_lifecycle.subprocess.Popen", side_effect=OSError("PRIVATE")) as popen:
            with self.assertRaises(Refusal): self.start()
            with self.assertRaises(Refusal): self.start()
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(json.loads((self.attempt / "status.json").read_text())["status"], "launch_failed")

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "fixture-only"})
    def test_monitor_failure_after_creation_stays_unknown_not_unlaunched(self):
        with patch("orchestrator.host_lifecycle.subprocess.Popen") as popen:
            self.start()
            popen.reset_mock()
            popen.return_value.pid = 123
            popen.return_value.wait.side_effect = OSError("PRIVATE")
            monitor(self.attempt)
            record = json.loads((self.attempt / "status.json").read_text())
            self.assertEqual(record["status"], "process_outcome_unknown")
            self.assertEqual(record["pid"], 123)
            self.assertNotIn("PRIVATE", str(record))
            with self.assertRaises(Refusal): monitor(self.attempt)
            with self.assertRaises(Refusal): self.start()
            self.assertEqual(popen.call_count, 1)

    def test_wrong_hash_missing_context_and_changed_launcher_fail_before_intent(self):
        with patch("orchestrator.host_lifecycle.subprocess.Popen") as popen:
            with self.assertRaises(Refusal): launch(self.manifest, self.attempt, "wrong")
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(Refusal): self.start()
            self.launcher.write_text("changed")
            with self.assertRaises(Refusal): self.start()
            popen.assert_not_called()
        self.assertFalse(self.attempt.exists())

    def test_public_or_symlink_launcher_and_wrong_profile_refused(self):
        self.launcher.chmod(0o644)
        with self.assertRaises(Refusal): specification(self.manifest)
        self.launcher.chmod(0o600)
        link = self.root / "link"; link.symlink_to(self.launcher)
        for fields in ({"launcher": str(link)}, {"profile": "harness"}, {"cwd": "relative"}):
            self.manifest.write_text(json.dumps({**self.spec, **fields}))
            with self.assertRaises(Refusal): specification(self.manifest)

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "fixture-only-no-native-host"})
    def test_real_detached_supervisor_records_fixture_exit_after_starter_returns(self):
        # Harmless disposable shell only. This is process lifetime evidence,
        # never Codex host, native-tool or pilot qualification.
        self.launcher.write_text("sleep 0.3\nexit 7\n")
        self.spec["launcherSha256"] = hashlib.sha256(self.launcher.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(self.spec))
        starter = subprocess.run([sys.executable, "-m", "orchestrator.host_lifecycle", "start", str(self.manifest),
                                  str(self.attempt), "--confirm-hash", digest(self.spec)],
                                 capture_output=True, text=True, timeout=5, check=True)
        result = json.loads(starter.stdout)
        starter_finished_at = time.time()
        self.assertEqual(result["status"], "launch_requested")
        until = time.monotonic() + 5
        record = {}
        while time.monotonic() < until:
            record = json.loads((self.attempt / "status.json").read_text())
            if record["status"] == "process_exited": break
            time.sleep(0.01)
        self.assertEqual(record["status"], "process_exited")
        self.assertEqual(record["exitCode"], 7)
        self.assertGreater(record["observedAt"], starter_finished_at, "The supervised child outlives the exited starter process")
        self.assertFalse(record["hostReady"])
