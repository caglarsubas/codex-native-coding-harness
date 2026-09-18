"""Two isolated workspaces for browser QA; inference mocked, notifications disabled."""
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from orchestrator.workspaces import Registry
from test_assistant import CONFIG
from manual_assistant_fixture import reply


def workspace_reply(route, payload, **options):
    result = reply(route, payload, **options)
    answer = json.loads(result["choices"][0]["message"]["content"])
    answer.update(answer="This is the selected workspace's synthetic project snapshot. No native task was started.", links=["overview"], evidence=["F30"])
    result["choices"][0]["message"]["content"] = json.dumps(answer)
    return result

if __name__ == "__main__":
    root = Path(tempfile.mkdtemp(prefix="orchestrator-workspace-ui-")).resolve()
    registry = Registry(root / "platform", create=True)
    for wid, name in (("alpha", "Harness platform · fixture"), ("beta", "Second product · fixture")):
        ledger = Ledger(root / wid)
        ledger.initialize({"schemaVersion": 1, "brainId": "brain-" + wid, "repositories": [
            {"id": wid + "-repo", "path": str(root / (wid + "-checkout")), "projectId": "fixture-project-" + wid,
             "ref": "origin/main", "mergePolicy": "manual", "policyProfile": "harness" if wid == "alpha" else "standard"}]})
        registry.register(wid, name, ledger.root)
        registry.save_profile(wid, {"goal": "Build an evidence-led " + ("agent platform" if wid == "alpha" else "product research tool"),
            "successCriteria": ["One bounded milestone independently verified", "No cross-workspace actions"],
            "architecture": "Local Python ledger, native Codex brain and isolated implementation tasks.",
            "techStack": ["Python", "SQLite", "Vanilla JavaScript"],
            "roadmap": "Workspace foundation in review. Next owner checkpoint: authorize one pilot phase.",
            "references": ["Fixture charter v1 · synthetic only"]}, 0)
    env = root / ".env"
    with os.fdopen(os.open(env, os.O_CREAT | os.O_WRONLY, 0o600), "w") as stream:
        stream.write(f"CODEX_LLM_BASE_URL={CONFIG.base_url}\nCODEX_LLM_API_KEY={CONFIG.api_key}\n")
    server = Dashboard(registry.ledger("alpha"), 8769, inference_env=env, registry=registry)
    with os.fdopen(os.open(root / "session.json", os.O_CREAT | os.O_WRONLY, 0o600), "w") as stream:
        json.dump({"url": server.origin + "/#token=" + server.bootstrap}, stream)
    print(root, flush=True)
    with patch("orchestrator.assistant.Client.request", side_effect=workspace_reply):
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()
