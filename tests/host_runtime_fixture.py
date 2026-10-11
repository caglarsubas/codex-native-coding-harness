"""Tiny non-native package used only in temporary filesystem fixtures."""
import json

from orchestrator.host_runtime import inspect_package


def runtime_fixture(root):
    root.mkdir(mode=0o700)
    for name in ("bin", "CodexCLI.app/Contents/MacOS", "codex-resources/runtime", "codex-path"):
        (root / name).mkdir(parents=True, mode=0o700)
    manifest = {"layoutVersion": 1, "version": "fixture-1", "target": "fixture-darwin",
                "variant": "codex", "entrypoint": "bin/codex", "resourcesDir": "codex-resources", "pathDir": "codex-path"}
    (root / "codex-package.json").write_text(json.dumps(manifest))
    for name in ("bin/codex", "bin/codex-code-mode-host", "CodexCLI.app/Contents/MacOS/codex", "codex-path/rg"):
        (root / name).write_text("#!/bin/sh\nexit 0\n")
        (root / name).chmod(0o700)
    (root / "codex-resources/runtime/notice.txt").write_text("Synthetic runtime bytes; not native qualification.\n")
    return inspect_package(root)
