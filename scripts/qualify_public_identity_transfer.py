"""Exact native identity/history fixture; no live host, credentials or ledger.

One loopback receipt-only source turn, followed by native metadata restoration
and inspection loading in another disposable home. No transfer turn is started.
The provider overlay is fixture-only, not the live public-host launch profile.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator.core import require
from orchestrator.native_read_client import secure_path
from orchestrator.native_policy_evidence import matches, reported
from orchestrator.public_host_lifecycle import CONFIG, environment
from orchestrator.public_identity_transfer import source_snapshot, rollout
from qualify_public_native_tasks import StdioFixture


def qualify(binary, expected_hash, history_mode="paginated"):
    path, _ = secure_path(binary)
    with path.open("rb") as stream: actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    require(actual_hash == expected_hash, "Reviewed transfer runtime changed")
    requests = []
    class Provider(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_error(404)
        def do_POST(self):
            requests.append(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            require(0 < length < 1_000_000, "Fixture request bound")
            self.rfile.read(length)
            events = [{"type": "response.created", "response": {"id": "source-receipt"}},
                      {"type": "response.output_item.done", "item": {"type": "message", "role": "assistant", "id": "fixture-message",
                       "content": [{"type": "output_text", "text": "Immutable fixture history receipt."}]}},
                      {"type": "response.completed", "response": {"id": "source-receipt", "usage": {"input_tokens": 5, "output_tokens": 5, "total_tokens": 10}}}]
            data = "".join("data: " + json.dumps(e) + "\n\n" for e in events).encode()
            self.send_response(200); self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def log_message(self, *_): pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    runner = threading.Thread(target=server.serve_forever, daemon=True); runner.start()
    processes = []
    try:
        with tempfile.TemporaryDirectory(prefix="codex-native-identity.") as temporary:
            root = Path(temporary).resolve(); cwd = root / "checkout"; cwd.mkdir(mode=0o700)
            homes = [root / name for name in ("source-home", "destination-home")]
            connections = []
            for home in homes:
                home.mkdir(mode=0o700)
                # Explicit loopback-only fixture overlay; no key/auth/desktop pipe.
                (home / "config.toml").write_text('model = "gpt-6-astra"\nmodel_provider = "identity_fixture"\n' + CONFIG +
                    f'''\n[model_providers.identity_fixture]
name = "Loopback identity fixture"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
''')
                (home / "config.toml").chmod(0o600)
                process = subprocess.Popen([binary, "app-server", "--stdio"], cwd=cwd,
                    env=environment({"codexHome": str(home)}), stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
                processes.append(process)
                io = StdioFixture(process)
                io.initialization = io._rpc("initialize", {"clientInfo": {"name": "native_identity_fixture", "version": "1"},
                                    "capabilities": {"experimentalApi": True}})
                require(io.initialization["codexHome"] == str(home), "Fixture home changed")
                process.stdin.write(b'{"method":"initialized","params":{}}\n'); process.stdin.flush()
                connections.append(io)
            source, destination = connections
            project = source._rpc("project/create", {"name": "Original fixture", "roots": [{"path": str(cwd)}],
                     "metadata": {"fixture": "observed-original"}, "idempotencyKey": str(uuid.uuid4())})["project"]
            thread = source._rpc("thread/start", {"cwd": str(cwd), "projectId": project["id"], "model": "gpt-6-astra",
                "approvalPolicy": "on-request", "approvalsReviewer": "user", "sandbox": "workspace-write",
                "config": {"features": {"code_mode": {"enabled": False}, "goals": False}}, "historyMode": history_mode, "ephemeral": False})["thread"]
            brain = thread["id"]
            turn = source._rpc("turn/start", {"threadId": brain, "input": [{"type": "text", "text": "Return a receipt only. No tools, files, tasks or commands.", "text_elements": []}],
                     "approvalPolicy": "on-request", "approvalsReviewer": "user"})["turn"]
            if not source._early_completion:
                for _ in range(1000):
                    row = source._line()
                    if row.get("method") == "turn/completed":
                        p = row["params"]; source._early_completion = (p["threadId"], p["turn"]["id"], p["turn"]["status"]); break
            require(source._early_completion == (brain, turn["id"], "completed"), "Source fixture did not end")
            scope = {"brainId": brain, "projectId": project["id"], "cwd": str(cwd)}
            initial_meta = json.loads(Path(source._rpc("thread/read", {"threadId": brain, "includeTurns": False})["thread"]["path"]).read_bytes().splitlines()[0])["payload"]
            require(initial_meta.get("history_mode", "legacy") == history_mode, "Fixture native history mode changed")
            first, raw = source_snapshot(source, scope)
            second, _ = source_snapshot(source, scope)
            require(first == second and first["latestTurnId"] == turn["id"], "Source fixture snapshot changed")
            require(len(requests) == 1, "Unexpected source model request")
            empty = destination._rpc("project/list", {"limit": 100})
            require(empty == {"data": [], "nextCursor": None}, "Fixture destination not empty")
            restored = destination._rpc("project/restoreMetadata", {"version": 1, "project": first["project"]})
            require(restored == {"version": 1, "project": dict(first["project"], recencyAt=None)}, "Native project identity restore changed metadata")
            copied_dir = homes[1] / "sessions" / ("transfer-" + brain)
            copied_dir.mkdir(mode=0o700, parents=True)
            target = copied_dir / Path(first["rollout"]["path"]).name
            target.write_bytes(raw); target.chmod(0o600)
            loaded = destination._rpc("thread/resume", {"threadId": brain, "path": str(target), "cwd": str(cwd), "excludeTurns": True,
                "approvalPolicy": "on-request", "approvalsReviewer": "user", "sandbox": "workspace-write",
                "config": {"features": {"code_mode": {"enabled": False}, "goals": False, "apps": False, "plugins": False, "hooks": False}}})["thread"]
            require(loaded["id"] == brain and loaded["status"]["type"] == "idle", "Native load changed identity or started activity")
            destination._rpc("thread/metadata/update", {"threadId": brain, "projectId": project["id"]})
            samples = [destination._rpc("thread/read", {"threadId": brain, "includeTurns": True})["thread"] for _ in range(2)]
            require(samples[0] == samples[1] and samples[0]["id"] == brain and samples[0]["projectId"] == project["id"] and
                    samples[0]["cwd"] == str(cwd) and samples[0]["turns"] ==
                    source._rpc("thread/read", {"threadId": brain, "includeTurns": True})["thread"]["turns"], "Native transferred history differs")
            policies = [destination._rpc("thread/effectivePolicy/read", {"threadId": brain}) for _ in range(2)]
            require(policies[0] == policies[1] and matches(reported(policies[0], brain, str(cwd))), "Loaded destination policy differs")
            require(target.read_bytes().startswith(raw) and
                    rollout(first["rollout"]["path"], first["sourceHome"], brain, str(cwd))[0] == raw, "Original history bytes changed")
            require(len(requests) == 1 and "turn/start" not in destination.methods and not list(cwd.iterdir()), "Transfer executed or replayed work")
            require(not any((home / "auth.json").exists() for home in homes), "Fixture inherited credentials")
            return {"binarySha256": actual_hash, "nativeIdentityFixtureQualified": True,
                    "historyMode": history_mode,
                    "sameProjectId": True, "sameBrainId": True, "sameHistoryPrefix": True, "sameTurnProjection": True,
                    "sourceLoopbackReceiptTurns": 1, "transferTurnStarts": 0, "transferModelRequests": 0,
                    "cloudRequests": 0, "liveNativeWrites": 0, "liveHostConnections": 0,
                    "historicalTerminalSafety": "unknown", "migrationQualified": False, "pilotAccepted": False}
    finally:
        for process in processes:
            process.stdin.close()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.terminate(); process.wait(timeout=5)
            process.stdout.close()
        server.shutdown(); server.server_close(); runner.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True); parser.add_argument("--sha256", required=True)
    parser.add_argument("--history-mode", choices=("legacy", "paginated"), default="paginated")
    args = parser.parse_args()
    print(json.dumps(qualify(args.executable, args.sha256, args.history_mode), indent=2))
