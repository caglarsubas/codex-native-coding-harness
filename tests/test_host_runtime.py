import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from host_runtime_fixture import runtime_fixture
from orchestrator.core import Refusal
from orchestrator.host_runtime import inspect_package, safe_path, validate_pin
from orchestrator.host_lifecycle import exec_foreground, review_hash, validate_spec
import test_host_lifecycle


class HostRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.package = self.root / "runtime"
        self.pin = runtime_fixture(self.package)

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_inventory_is_read_only_and_does_not_execute(self):
        with patch("subprocess.run") as run, patch("subprocess.Popen") as popen, patch("os.execv") as execute:
            self.assertEqual(inspect_package(self.package), self.pin)
            validate_pin(self.pin)
            run.assert_not_called(); popen.assert_not_called(); execute.assert_not_called()
        self.assertEqual(self.pin["fileCount"], 6)
        self.assertNotIn("nativeToolsQualified", self.pin)
        # Unrelated private host journals and credentials are outside the closed
        # package trees and cannot become runtime manifest output.
        (self.package / "secret.private").write_text("PRIVATE_CREDENTIAL")
        self.assertEqual(inspect_package(self.package), self.pin)

    def test_missing_helper_or_resource_layout_is_refused(self):
        for name in ("bin/codex-code-mode-host", "codex-resources/runtime/notice.txt", "codex-path/rg", "bin/codex"):
            path = self.package / name
            content, mode = path.read_bytes(), path.stat().st_mode & 0o777
            path.unlink()
            with self.subTest(name=name), self.assertRaises((Refusal, OSError)):
                validate_pin(self.pin)
            path.write_bytes(content); path.chmod(mode)
            self.pin = inspect_package(self.package)

    def test_symlink_nonregular_or_writable_files_refuse(self):
        path = self.package / "bin/codex-code-mode-host"
        path.unlink(); path.symlink_to(self.package / "bin/codex")
        with self.assertRaises(Refusal): inspect_package(self.package)
        path.unlink(); os.mkfifo(path)
        with self.assertRaises(Refusal): inspect_package(self.package)
        path.unlink(); path.write_text("fixture"); path.chmod(0o777)
        with self.assertRaises(Refusal): inspect_package(self.package)

    def test_hard_link_alias_and_non_executable_helper_refuse(self):
        path = self.package / "bin/codex-code-mode-host"
        alias = self.root / "helper-alias"
        os.link(path, alias)
        with self.assertRaises(Refusal): inspect_package(self.package)
        alias.unlink(); path.chmod(0o600)
        with self.assertRaises(Refusal): inspect_package(self.package)

    def test_empty_directory_and_directory_permission_drift_invalidate_pin(self):
        extra = self.package / "codex-resources/empty"
        extra.mkdir(mode=0o700)
        with self.assertRaises(Refusal): validate_pin(self.pin)
        current = inspect_package(self.package)
        extra.chmod(0o755)
        with self.assertRaises(Refusal): validate_pin(current)

    def test_access_time_change_alone_does_not_invalidate_pin(self):
        path = self.package / "bin/codex-code-mode-host"
        before = path.stat()
        # Pure comparator regression: do not chmod/utime (which changes ctime).
        from orchestrator.host_runtime import stamp
        proxy = SimpleNamespace(**{key:getattr(before,key) for key in
            ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')},
            st_atime=before.st_atime-1000)
        self.assertEqual(stamp(before), stamp(proxy))

    def test_root_symlink_and_unsafe_ancestor_refuse(self):
        alias = self.root / "alias"; alias.symlink_to(self.package, target_is_directory=True)
        with self.assertRaises(Refusal): inspect_package(alias)
        self.root.chmod(0o777)
        try:
            with self.assertRaises(Refusal): inspect_package(self.package)
        finally:
            self.root.chmod(0o700)

    def test_sticky_bit_exception_is_only_for_root_owned_directories(self):
        path = self.package / "bin/codex-code-mode-host"
        original = Path.lstat
        writable_root_file = SimpleNamespace(st_uid=0, st_mode=path.stat().st_mode | 0o1022)
        with patch.object(Path, "lstat", lambda p: writable_root_file if p == path else original(p)):
            with self.assertRaises(Refusal): safe_path(path)

    def test_bytes_modes_membership_and_same_bytes_replacement_invalidate_review(self):
        path = self.package / "codex-resources/runtime/notice.txt"
        for mutation in (lambda: path.write_text("changed"), lambda: path.chmod(0o700),
                         lambda: (self.package / "bin/extra").write_text("added")):
            pin = inspect_package(self.package)
            mutation()
            with self.assertRaisesRegex(Refusal, "changed"):
                validate_pin(pin)
        pin = inspect_package(self.package)
        content = path.read_bytes(); path.unlink(); path.write_bytes(content)
        with self.assertRaises(Refusal): validate_pin(pin)

    def test_closed_manifest_cannot_redirect_or_change_layout(self):
        path = self.package / "codex-package.json"
        layout = json.loads(path.read_text())
        for key, value in (("entrypoint", "../codex"), ("resourcesDir", "/private"),
                           ("layoutVersion", True), ("target", []), ("unreviewedField", True)):
            candidate = {**layout, key: value}; path.write_text(json.dumps(candidate))
            with self.subTest(key=key), self.assertRaises(Refusal): inspect_package(self.package)
        path.write_text(json.dumps(layout))

    def test_manifest_read_is_bounded_and_detects_growth_before_parse(self):
        path = self.package / "codex-package.json"
        path.write_bytes(b'{' + b' ' * 65536)
        with self.assertRaises(Refusal): inspect_package(self.package)

    def test_inspection_has_file_count_and_size_bounds(self):
        with patch("orchestrator.host_runtime.MAX_FILES", 2), self.assertRaises(Refusal):
            inspect_package(self.package)
        with patch("orchestrator.host_runtime.MAX_FILE_BYTES", 1), self.assertRaises(Refusal):
            inspect_package(self.package)
        with patch("orchestrator.host_runtime.MAX_BYTES", 1), self.assertRaises(Refusal):
            inspect_package(self.package)

    def test_change_to_earlier_file_during_later_hash_is_detected(self):
        from orchestrator import host_runtime
        original = host_runtime.file_record
        path = self.package / "CodexCLI.app/Contents/MacOS/codex"
        def mutate(root, relative, remaining):
            result = original(root, relative, remaining)
            if relative == "codex-path/rg":
                path.write_text("drift after hash")
            return result
        with patch.object(host_runtime, "file_record", side_effect=mutate), self.assertRaises(Refusal):
            inspect_package(self.package)

    def test_private_pin_is_closed_and_checks_counts_without_bool_coercion(self):
        for candidate in ({**self.pin, "fileCount": True}, {**self.pin, "totalBytes": 0},
                          {**self.pin, "extra": "PRIVATE"}, {**self.pin, "helperHash": "x" * 64}):
            with self.subTest(candidate=candidate), self.assertRaises(Refusal): validate_pin(candidate)

    def test_cli_preview_starts_nothing_and_returns_only_metadata(self):
        result = subprocess.run([sys.executable, "-m", "orchestrator.host_lifecycle", "package-preview", str(self.package)],
                                capture_output=True, text=True, check=True, timeout=5)
        value = json.loads(result.stdout)
        self.assertEqual(value["runtimePackage"], self.pin)
        self.assertFalse(value["startsHost"]); self.assertFalse(value["nativeToolsQualified"])
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["runtime"])


class RuntimeLaunchTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_host_lifecycle.HostLifecycleTest(); self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "fixture-only"})
    def test_historical_v1_remains_readable_but_cannot_launch(self):
        f = self.fixture
        legacy = {k: v for k, v in f.spec.items() if k != "runtimePackage"}; legacy["schemaVersion"] = 1
        self.assertEqual(validate_spec(legacy), legacy)
        f.manifest.write_text(json.dumps(legacy))
        with patch("orchestrator.host_lifecycle.os.execv") as execute, self.assertRaisesRegex(Refusal, "runtime-package review"):
            exec_foreground(f.manifest, f.attempt, review_hash(legacy, "exec"))
        execute.assert_not_called(); self.assertFalse(f.attempt.exists())

    @patch.dict(os.environ, {"CODEX_APP_TOOLS_PIPE_PATH": "fixture-only"})
    def test_package_drift_after_intent_consumes_claim_without_execution_or_replay(self):
        from orchestrator import host_lifecycle
        f = self.fixture
        original = host_lifecycle.validate_spec
        calls = 0
        def validate(spec):
            nonlocal calls
            calls += 1
            if calls == 2:
                (Path(spec["runtimePackage"]["root"]) / "bin/codex-code-mode-host").write_text("drift")
            return original(spec)
        with patch.object(host_lifecycle, "validate_spec", side_effect=validate), patch.object(host_lifecycle.os, "execv") as execute:
            with self.assertRaises(Refusal): exec_foreground(f.manifest, f.attempt, review_hash(f.spec, "exec"))
            execute.assert_not_called()
        self.assertTrue((f.attempt / "exec.claim").exists())
        self.assertEqual(json.loads((f.attempt / "status.json").read_text())["status"], "launch_intent")
        with self.assertRaises(Refusal): exec_foreground(f.manifest, f.attempt, review_hash(f.spec, "exec"))


if __name__ == "__main__":
    unittest.main()
