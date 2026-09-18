"""Opt-in browser QA: isolated fixture ledger and mocked inference, no live controls.

Run from the repo: python3 -m tests.manual_assistant_fixture is NOT required;
use PYTHONPATH=.:tests python3 tests/manual_assistant_fixture.py.
Private auth URL is written to the printed temporary directory, never stdout.
"""
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from orchestrator.core import Ledger, Refusal
from orchestrator.decisions import publish
from orchestrator.server import Dashboard
from test_decisions import fixture
from test_assistant import CONFIG, response


def reply(route, payload, **_options):
    data = json.loads(payload["messages"][-1]["content"])
    if "fixture failure" in data["conversation"][-1]["content"]:
        raise Refusal("Fixture service unavailable; no retry sent")
    question = data["conversation"][-1]["content"]
    result = response()
    answer = json.loads(result["choices"][0]["message"]["content"])
    if "stop the brain" in question.lower():
        answer.update(answer="Review the safe-checkpoint stop below. No action has been submitted.", action={"key":"brain_stop"})
    elif "answer:" in question.lower():
        answer.update(answer="Review your exact answer before saving it. This does not authorize execution.",
                      action={"key":"answer_D1", "text":question.split(":", 1)[1].strip()})
    result["choices"][0]["message"]["content"] = json.dumps(answer)
    return result


if __name__ == "__main__":
    root = Path(tempfile.mkdtemp(prefix="orchestrator-assistant-ui-"))
    ledger = Ledger(root / "state")
    spec = fixture(ledger)
    token = ledger.acquire("brain-fixture:ui")
    publish(ledger, token, spec)
    env = root / ".env"
    env.write_text(f"CODEX_LLM_BASE_URL={CONFIG.base_url}\nCODEX_LLM_API_KEY={CONFIG.api_key}\n")
    env.chmod(0o600)
    server = Dashboard(ledger, 8769, inference_env=env)
    with os.fdopen(os.open(root / "session.json", os.O_CREAT | os.O_WRONLY, 0o600), "w") as stream:
        json.dump({"url": server.origin + "/#token=" + server.bootstrap}, stream)
    print(root, flush=True)
    with patch("orchestrator.assistant.Client.request", side_effect=reply):
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()
