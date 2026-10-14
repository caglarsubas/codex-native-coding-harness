"""Opt-in compiled-runtime fixture; no live Codex home, socket, ledger or turn.

Pass the exact already reviewed local binary and hash. All threads are ephemeral
in a disposable home and all provider calls are counted by a loopback fixture.
This tests the adapter against real native response bytes, not live pilot safety.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator.core import require
from orchestrator.native_policy_evidence import METHOD, matches, reported
from orchestrator.native_read_client import decode, secure_path

METHODS = {"initialize", METHOD, "thread/loaded/list", "thread/start"}


def qualify(binary, expected_hash):
    path, _ = secure_path(binary)
    with path.open("rb") as stream:
        actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    require(actual_hash == expected_hash, "Reviewed fixture executable changed")
    calls = []
    class Provider(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append(self.path); self.send_error(503)
        do_POST = do_GET
        def log_message(self, *_):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="codex-policy-adapter-fixture.") as directory:
            root = Path(directory).resolve()
            home, cwd = root / "home", root / "checkout"
            home.mkdir(mode=0o700); cwd.mkdir(mode=0o700)
            # Generated fixture only. Never edit real Codex configuration.
            (home / "config.toml").write_text(f'''model = "gpt-6-astra"
model_provider = "policy_fixture"
[model_providers.policy_fixture]
name = "Loopback fixture"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
[features]
code_mode = false
code_mode_only = true
skip_host_skill_discovery = true
plugins = false
apps = false
hooks = false
[analytics]
enabled = false
''')
            # No inherited account/pipe/connection/provider credentials.
            env = {key: os.environ[key] for key in ("HOME", "USER", "LOGNAME", "TMPDIR", "PATH") if key in os.environ}
            env["CODEX_HOME"] = str(home)
            process = subprocess.Popen([binary, "app-server", "--stdio"], cwd=cwd,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=env, start_new_session=True)
            sequence, buffer, methods = 0, b"", []
            try:
                os.set_blocking(process.stdout.fileno(), False)
                def rpc(method, params):
                    nonlocal sequence, buffer
                    require(method in METHODS, "Fixture cannot send that method")
                    methods.append(method); sequence += 1
                    process.stdin.write((json.dumps({"id": sequence, "method": method, "params": params}) + "\n").encode())
                    process.stdin.flush()
                    deadline = time.monotonic() + 20
                    with selectors.DefaultSelector() as selector:
                        selector.register(process.stdout, selectors.EVENT_READ)
                        for _ in range(256):
                            while b"\n" not in buffer:
                                remaining = deadline - time.monotonic()
                                require(remaining > 0 and selector.select(remaining), "Fixture read deadline exceeded")
                                chunk = os.read(process.stdout.fileno(), 65536)
                                require(chunk, "Fixture runtime ended")
                                buffer += chunk
                                require(len(buffer) <= 1_000_000, "Fixture response bound exceeded")
                            line, buffer = buffer.split(b"\n", 1)
                            row = decode(line)
                            if "id" not in row:
                                continue
                            require(row["id"] == sequence and "error" not in row, "Fixture native request refused")
                            return row["result"]
                    raise RuntimeError("Fixture notification bound exceeded")
                initialized = rpc("initialize", {"clientInfo": {"name": "policy_adapter_fixture", "version": "1"},
                    "capabilities": {"experimentalApi": True}})
                require(Path(initialized["codexHome"]).resolve() == home, "Isolated fixture home required")
                process.stdin.write(b'{"method":"initialized","params":{}}\n'); process.stdin.flush()
                missing = str(uuid.uuid4())
                for _ in range(2):
                    require(reported(rpc(METHOD, {"threadId": missing}), missing, str(cwd)) is None,
                            "Unloaded runtime must stay unknown")
                require(rpc("thread/loaded/list", {"cursor": None, "limit": 64})["data"] == [],
                        "Policy reads must not load a thread")
                created = rpc("thread/start", {"cwd": str(cwd), "ephemeral": True,
                    "approvalPolicy": "on-request", "approvalsReviewer": "user", "sandbox": "workspace-write",
                    "config": {"features": {"code_mode": {"enabled": False}}}})
                brain_id = created["thread"]["id"]
                samples = [rpc(METHOD, {"threadId": brain_id}) for _ in range(2)]
                require(samples[0] == samples[1] and all(matches(reported(item, brain_id, str(cwd))) for item in samples),
                        "Actual compiled policy does not match the adapter contract")
                require(not any("responses" in item for item in calls), "Fixture unexpectedly called a model")
                return {"binarySha256": actual_hash, "policyReads": 4, "matchingLoadedDefaults": True,
                        "unloadedStayedUnknown": True, "modelRequests": 0, "turnStarts": 0,
                        "liveHostConnections": 0, "liveNativeWrites": 0, "pilotAccepted": False}
            finally:
                process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate(); process.wait(timeout=5)  # Only this disposable fixture child.
                process.stdout.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.executable, args.sha256), indent=2))
