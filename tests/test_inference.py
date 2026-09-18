import copy
import fcntl
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

from orchestrator.core import Ledger, Refusal, canonical
from orchestrator.inference import (Client, NoRedirect, Settings, generate, projection,
    public_status, settings, validate_response)
from orchestrator.observations import artifact, capture


CONFIG = Settings("https://inference.example/v1", "fixture-key-not-a-real-secret")


def response():
    return {"model": CONFIG.model, "request_key_source": "local-inference",
        "usage": {"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700},
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "headline": "Dispatch is paused", "summary": "No managed work has started.",
            "attention": [{"text": "Pilot acceptance is pending.", "evidence": ["F1"]}],
            "nextSteps": [{"text": "Review a bounded packet before authorizing work.", "evidence": ["F1", "F2"]}]})}}]}


class InferenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = self.root / ".env"
        self.ledger = Ledger(self.root / "state")
        self.write_env()

    def tearDown(self):
        self.tmp.cleanup()

    def write_env(self, model=CONFIG.model, base=CONFIG.base_url):
        self.env.write_text(f'CODEX_LLM_BASE_URL={base}\nCODEX_LLM_API_KEY="{CONFIG.api_key}"\nCODEX_LLM_MODEL={model}\n')
        self.env.chmod(0o600)

    def test_env_is_private_and_models_are_local_only(self):
        self.assertEqual(settings(self.env), CONFIG)
        self.assertNotIn(CONFIG.api_key, repr(settings(self.env)))
        self.assertNotIn(CONFIG.base_url, repr(settings(self.env)))
        for model in ("external:openrouter", "nemotron-3-nano:30b", "$(touch dangerous)"):
            self.write_env(model=model)
            self.assertRaises(Refusal, settings, self.env)
        for base in ("http://inference.example/v1", "https://user:pass@inference.example/v1", "https://inference.example/v1/v1", "https://inference.example/v1?key=secret"):
            self.write_env(base=base)
            self.assertRaises(Refusal, settings, self.env)

    def test_env_missing_world_readable_symlink_and_duplicates_refused(self):
        self.assertRaises(Refusal, settings, self.root / "missing")
        self.env.chmod(0o644)
        self.assertRaises(Refusal, settings, self.env)
        self.env.chmod(0o600)
        link = self.root / "link"; link.symlink_to(self.env)
        self.assertRaises(Refusal, settings, link)
        self.env.write_text(self.env.read_text() + "CODEX_LLM_MODEL=llama3.2:3b\n")
        self.assertRaises(Refusal, settings, self.env)

    def test_separate_assistant_model_is_local_and_server_owned(self):
        self.env.write_text(self.env.read_text()+"CODEX_LLM_ASSISTANT_MODEL=qwen3.8:27b\n")
        cfg=settings(self.env)
        self.assertEqual(cfg.model,CONFIG.model)
        self.assertEqual(cfg.assistant_model,"qwen3.8:27b")
        self.assertEqual(public_status(self.ledger,env_path=self.env)["assistantModel"],"qwen3.8:27b")
        self.write_env()
        self.env.write_text(self.env.read_text()+"CODEX_LLM_ASSISTANT_MODEL=external:openrouter\n")
        self.assertRaises(Refusal,settings,self.env)

    def test_projection_does_not_include_private_free_text(self):
        state = self.ledger.snapshot()
        state["meta"]["checkpoint"] = "secret transcript with /private/path"
        state["meta"]["brainThreadId"] = "private-brain-id"
        state["observations"]["artifacts"] = [{"key": "private-file", "path": "/private/secret", "content": "SECRET_ARTIFACT"}]
        raw = canonical(projection(state))
        for value in ("private", "SECRET_ARTIFACT", "transcript with", CONFIG.api_key):
            self.assertNotIn(value, raw)
        self.assertLess(len(raw.encode()), 20000)

    def test_transport_fixed_auth_and_payload_without_fallback_or_tenant(self):
        client = Client(CONFIG)
        client.opener = Mock()
        client.opener.open.return_value = io.BytesIO(json.dumps(response()).encode())
        client.summarize(projection(self.ledger.snapshot()))
        request = client.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, CONFIG.base_url + "/chat/completions")
        self.assertEqual(client.opener.open.call_args.kwargs, {"timeout": 90})
        self.assertEqual(request.get_header("Authorization"), "Bearer " + CONFIG.api_key)
        payload = json.loads(request.data)
        self.assertEqual(set(payload), {"model", "messages", "temperature", "max_tokens", "stream"})
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertFalse(payload["stream"])
        self.assertNotIn(CONFIG.api_key, str(payload))
        self.assertIsNone(NoRedirect().redirect_request(request, None, 302, "", {}, "https://elsewhere.example"))
        large = Client(Settings(CONFIG.base_url, CONFIG.api_key, "gemma4:26b"))
        with patch.object(large, "request", return_value={}) as request:
            large.summarize(projection(self.ledger.snapshot()))
            self.assertEqual(request.call_args.args[1]["max_tokens"], 4096)

    def test_model_check_returns_only_local_ids_and_no_provider_details(self):
        client = Client(CONFIG)
        with patch.object(client, "request", return_value={"data": [{"id": CONFIG.model}, {"id": "private-provider-model:openrouter"}]}):
            result = client.check()
            self.assertEqual(result["localModels"], [CONFIG.model])
            self.assertNotIn("private-provider", str(result))
        with patch.object(client, "request", return_value={"data": None}):
            self.assertRaises(Refusal, client.check)

    def test_missing_usage_is_not_zero_spend(self):
        value = response(); value["usage"] = None
        with patch.object(Client, "summarize", return_value=value):
            result = generate(self.ledger, self.env)
        self.assertIsNone(result["report"]["usage"]["total_tokens"])
        self.assertEqual(public_status(self.ledger, env_path=self.env)["retainedUsage"]["briefsWithUsage"], 0)

    def test_errors_never_expose_credentials_remote_body_or_url(self):
        client = Client(CONFIG); client.opener = Mock()
        for error in (HTTPError(CONFIG.base_url, 401, CONFIG.api_key, {}, None),
                HTTPError(CONFIG.base_url, 429, CONFIG.api_key, {"Retry-After": "30"}, None),
                HTTPError(CONFIG.base_url, 302, CONFIG.api_key, {}, None),
                HTTPError(CONFIG.base_url, 500, CONFIG.api_key, {}, None), URLError(CONFIG.api_key)):
            client.opener.open.side_effect = error
            with self.assertRaises(Refusal) as caught: client.request("models")
            self.assertNotIn(CONFIG.api_key, str(caught.exception))
            self.assertNotIn(CONFIG.base_url, str(caught.exception))
        client.opener.open.side_effect = None
        for raw in (b"not json", json.dumps({"error": CONFIG.api_key}).encode(), b"x" * 131073):
            client.opener.open.return_value = io.BytesIO(raw)
            with self.assertRaises(Refusal) as caught: client.request("models")
            self.assertNotIn(CONFIG.api_key, str(caught.exception))

    def test_rejects_external_routing_partial_tool_null_and_bad_evidence(self):
        good = response(); facts = projection(self.ledger.snapshot())
        self.assertEqual(validate_response(good, facts, CONFIG)[1]["total_tokens"], 700)
        bad = []
        for field, value in (("request_key_source", "openrouter"), ("model", "other"), ("choices", []), ("usage", "bad")):
            item = copy.deepcopy(good); item[field] = value; bad.append(item)
        item = copy.deepcopy(good); item["choices"][0]["finish_reason"] = "length"; bad.append(item)
        for value in (None, "not json", CONFIG.api_key, '{"headline":"incomplete"}'):
            item = copy.deepcopy(good); item["choices"][0]["message"]["content"] = value; bad.append(item)
        item = copy.deepcopy(good); item["choices"][0]["message"]["tool_calls"] = [{}]; bad.append(item)
        item = copy.deepcopy(good); item["choices"][0]["message"]["content"] = item["choices"][0]["message"]["content"].replace('"F1"', '"F99"'); bad.append(item)
        item = copy.deepcopy(good); item["choices"][0]["message"]["content"] = item["choices"][0]["message"]["content"].replace('Review a bounded packet before authorizing work.', 'Resume orchestration dispatch.'); bad.append(item)
        for item in bad:
            self.assertRaises(Refusal, validate_response, item, facts, CONFIG)

    def test_cache_artifact_versions_staleness_and_no_control_mutation(self):
        original = self.ledger.snapshot()
        with patch.object(Client, "summarize", return_value=response()) as network:
            first = generate(self.ledger, self.env)
            self.assertEqual(first["status"], "generated")
            self.assertEqual(generate(self.ledger, self.env)["status"], "cached")
            self.assertEqual(network.call_count, 1)
            self.assertFalse(public_status(self.ledger, env_path=self.env)["stale"])
            generate(self.ledger, self.env, force=True)
            self.assertEqual(network.call_count, 2)
        state = self.ledger.snapshot()
        self.assertEqual(len(state["observations"]["artifacts"]), 2)
        self.assertEqual(public_status(self.ledger, env_path=self.env)["retainedUsage"]["total_tokens"], 1400)
        raw = artifact(self.ledger, first["report"]["artifactId"])[1]
        self.assertEqual(json.loads(raw)["usage"]["total_tokens"], 700)
        for key in ("meta", "workers", "queue", "commands"):
            self.assertEqual(state[key], original[key])
        self.assertNotIn(CONFIG.api_key, canonical(state))
        self.assertNotIn(CONFIG.base_url, canonical(state))
        with self.ledger.tx() as db:
            capture(db, "plan", b"changed", {"name": "plan.md", "repository": "fixture", "orderAt": 1, "references": []})
        self.assertTrue(public_status(self.ledger, env_path=self.env)["stale"])
        with patch("orchestrator.inference.time.time", return_value=first["report"]["generatedAt"] + 901):
            self.assertTrue(public_status(self.ledger, env_path=self.env)["stale"])

    def test_model_change_invalidates_and_failure_preserves_previous_brief(self):
        with patch.object(Client, "summarize", return_value=response()):
            first = generate(self.ledger, self.env)
        self.write_env(model="llama3.2:3b")
        self.assertTrue(public_status(self.ledger, env_path=self.env)["stale"])
        with patch.object(Client, "summarize", side_effect=Refusal("Service unavailable")):
            self.assertRaises(Refusal, generate, self.ledger, self.env)
        self.assertEqual(self.ledger.snapshot()["observations"]["executive"], first["report"])

    def test_file_lock_serializes_cli_and_dashboard(self):
        with open(self.ledger.root / "inference.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(Client, "summarize") as network:
                self.assertRaises(Refusal, generate, self.ledger, self.env)
                network.assert_not_called()

    def test_reading_status_and_unconfigured_usage_never_calls_model(self):
        with patch.object(Client, "request") as network:
            self.assertTrue(public_status(self.ledger, env_path=self.env)["configured"])
            self.assertFalse(public_status(self.ledger, env_path=self.root / "missing")["configured"])
            network.assert_not_called()


if __name__ == "__main__": unittest.main()
