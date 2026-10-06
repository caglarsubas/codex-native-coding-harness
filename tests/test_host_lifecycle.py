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
from orchestrator.host_lifecycle import launch, monitor, review_hash, run_foreground, specification


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

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "current-app-context-not-persisted"})
    @patch("orchestrator.host_lifecycle.subprocess.Popen")
    def test_foreground_stays_in_caller_without_detached_supervisor(self, popen):
        popen.return_value.pid = 456
        popen.return_value.wait.return_value = 0
        result = run_foreground(self.manifest, self.attempt, review_hash(self.spec, "foreground"))
        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], ["/bin/zsh", str(self.launcher)])
        self.assertNotIn("start_new_session", popen.call_args.kwargs)
        self.assertNotIn("env", popen.call_args.kwargs)
        popen.return_value.wait.assert_called_once_with()
        self.assertEqual(result["status"], "process_exited")
        self.assertEqual(result["mode"], "foreground")
        self.assertFalse(result["hostReady"])
        self.assertFalse(result["nativeToolsQualified"])
        self.assertNotIn("current-app-context-not-persisted", (self.attempt / "launch.json").read_text())
        with self.assertRaisesRegex(Refusal, "already exists"):
            run_foreground(self.manifest, self.attempt, review_hash(self.spec, "foreground"))
        with self.assertRaisesRegex(Refusal, "already exists"):
            self.start()
        self.assertEqual(popen.call_count, 1)

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "fixture-only"})
    @patch("orchestrator.host_lifecycle.subprocess.Popen")
    def test_foreground_needs_mode_bound_review_not_historical_detached_approval(self, popen):
        with self.assertRaisesRegex(Refusal, "mode and manifest"):
            run_foreground(self.manifest, self.attempt, digest(self.spec))
        with self.assertRaisesRegex(Refusal, "mode and manifest"):
            launch(self.manifest, self.attempt, review_hash(self.spec, "foreground"))
        self.assertFalse(self.attempt.exists())
        popen.assert_not_called()

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "fixture-only"})
    @patch("orchestrator.host_lifecycle.subprocess.Popen")
    def test_internal_detached_monitor_cannot_consume_foreground_intent(self, popen):
        from orchestrator.host_lifecycle import prepare_attempt
        prepare_attempt(self.manifest, self.attempt, review_hash(self.spec, "foreground"), "foreground")
        with self.assertRaisesRegex(Refusal, "Supervisor mode"):
            monitor(self.attempt)
        self.assertFalse((self.attempt / "monitor.claim").exists())
        popen.assert_not_called()

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "fixture-only"})
    @patch("orchestrator.host_lifecycle.subprocess.Popen")
    def test_changed_mode_bound_intent_refuses_before_creation(self, popen):
        from orchestrator.host_lifecycle import prepare_attempt
        prepare_attempt(self.manifest, self.attempt, review_hash(self.spec, "foreground"), "foreground")
        journal = json.loads((self.attempt / "launch.json").read_text())
        journal["mode"] = "detached"
        (self.attempt / "launch.json").write_text(json.dumps(journal))
        with self.assertRaisesRegex(Refusal, "intent changed"):
            monitor(self.attempt)
        popen.assert_not_called()

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "fixture-only"})
    @patch("orchestrator.host_lifecycle.subprocess.Popen")
    def test_foreground_interrupt_keeps_unknown_outcome_and_one_shot_claim(self, popen):
        popen.return_value.pid = 456
        popen.return_value.wait.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            run_foreground(self.manifest, self.attempt, review_hash(self.spec, "foreground"))
        status = json.loads((self.attempt / "status.json").read_text())
        self.assertEqual(status["status"], "process_outcome_unknown")
        self.assertEqual(status["pid"], 456)
        self.assertFalse(status["restarted"])
        popen.return_value.terminate.assert_not_called()
        popen.return_value.kill.assert_not_called()
        with self.assertRaises(Refusal):
            run_foreground(self.manifest, self.attempt, review_hash(self.spec, "foreground"))
        with self.assertRaises(Refusal):
            monitor(self.attempt, foreground=True)
        self.assertEqual(popen.call_count, 1)

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "fixture-only"})
    @patch("orchestrator.host_lifecycle.subprocess.Popen")
    def test_historical_detached_intent_remains_readable_without_mode_promotion(self, popen):
        self.start()
        journal = json.loads((self.attempt / "launch.json").read_text())
        del journal["mode"]
        del journal["reviewHash"]
        (self.attempt / "launch.json").write_text(json.dumps(journal))
        popen.reset_mock()
        with self.assertRaisesRegex(Refusal, "Supervisor mode"):
            monitor(self.attempt, foreground=True)
        popen.return_value.pid = 123
        popen.return_value.wait.return_value = 0
        monitor(self.attempt)
        self.assertEqual(json.loads((self.attempt / "status.json").read_text())["mode"], "detached")
        popen.assert_called_once()

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "fixture-only-no-native-host"})
    def test_real_foreground_fixture_keeps_monitor_alive_until_child_exit(self):
        self.launcher.write_text("sleep 0.3\nexit 7\n")
        self.spec["launcherSha256"] = hashlib.sha256(self.launcher.read_bytes()).hexdigest()
        self.manifest.write_text(json.dumps(self.spec))
        started_at = time.time()
        parent = subprocess.run([sys.executable, "-m", "orchestrator.host_lifecycle", "run", str(self.manifest),
                                 str(self.attempt), "--confirm-hash", review_hash(self.spec, "foreground")],
                                capture_output=True, text=True, timeout=5, check=True)
        result = json.loads(parent.stdout)
        self.assertEqual(result["mode"], "foreground")
        self.assertEqual(result["status"], "process_exited")
        self.assertEqual(result["exitCode"], 7)
        self.assertGreater(result["observedAt"], started_at + 0.25)
        self.assertLess(result["observedAt"], time.time())
        self.assertFalse(result["hostReady"])
        self.assertFalse(result["nativeToolsQualified"])

    def test_foreground_preview_is_read_only_and_mode_bound(self):
        preview = subprocess.run([sys.executable, "-m", "orchestrator.host_lifecycle", "preview", str(self.manifest),
                                  "--mode", "foreground"], capture_output=True, text=True, check=True, timeout=5)
        result = json.loads(preview.stdout)
        self.assertEqual(result["reviewHash"], review_hash(self.spec, "foreground"))
        self.assertNotEqual(result["reviewHash"], result["manifestHash"])
        self.assertFalse(result["startsHost"])
        self.assertFalse(result["nativeToolsQualified"])
        self.assertFalse(self.attempt.exists())

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
