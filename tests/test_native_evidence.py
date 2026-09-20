"""Disposable sockets, fake proxy executables and synthetic ledgers only."""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import native_evidence as evidence, native_read_client as client
from orchestrator.core import Refusal, canonical, digest
import test_native_lifecycle

IDENTITY = {"userAgent": "fixture/1", "platformFamily": "unix", "platformOs": "macos", "codexHome": "/fixture/private"}


class EndpointFixture:
    def endpoint_setup(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-read-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.root.chmod(0o700)
        self.sock = socket.socket(socket.AF_UNIX); self.sock.bind(str(self.root / "observer.sock"))
        self.addCleanup(self.sock.close)
        (self.root / "observer.sock").chmod(0o600)
        self.binary = self.root / "codex-fixture"
        self.binary.write_text("#!"+sys.executable+"\n"+'''import json, os, pathlib, sys, time
root = pathlib.Path(__file__).parent
for line in sys.stdin:
    request = json.loads(line)
    with (root / 'requests.jsonl').open('a') as stream: stream.write(json.dumps(request)+'\\n')
    if 'id' not in request: continue
    result = {'userAgent':'fixture/1','platformFamily':'unix','platformOs':'macos','codexHome':'/fixture/private'}
    if request['method'] != 'initialize':
        mode = (root / 'mode').read_text()
        if mode == 'timeout': time.sleep(10)
        if mode == 'closed': sys.exit(0)
        if mode == 'large': print('x'*1000001, flush=True); continue
        if mode == 'duplicate': print('{"id":2,"id":2,"result":{}}', flush=True); continue
        if mode == 'error': print(json.dumps({'id':request['id'],'error':{'message':'SECRET'}}), flush=True); continue
        if mode == 'server_request': print(json.dumps({'id':request['id'],'method':'approve','params':{}}), flush=True); continue
        if mode == 'wrong_id': print(json.dumps({'id':999,'result':{}}), flush=True); continue
        if mode == 'notification': print(json.dumps({'method':'agentMessage','params':{'text':'SECRET'}}), flush=True)
        result = {'ok':True,'secretPresent':'OPENAI_API_KEY' in os.environ}
        if mode == 'collector':
            result = {'data':[],'nextCursor':None}
            if request['method'] == 'thread/read': result = {'thread':{'id':request['params']['threadId'],'parentThreadId':None,'status':{'type':'idle'},'ephemeral':False,'preview':'SECRET'}}
    print(json.dumps({'id':request['id'],'result':result}), flush=True)
''')
        self.binary.chmod(0o700); (self.root / "mode").write_text("good")
        self.endpoint = client.inspect_endpoint(str(self.binary), str(self.root / "observer.sock"), digest(IDENTITY))


class ProxyTest(EndpointFixture, unittest.TestCase):
    def setUp(self): self.endpoint_setup()

    def read(self, **fields):
        with client.ReadProxy(self.endpoint, **fields) as proxy:
            return proxy.call("thread/read", {"threadId": "owned-task", "includeTurns": False})

    def test_real_subprocess_fixed_handshake_and_metadata_read(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "SECRET"}): value = self.read()
        self.assertEqual(value, {"ok": True, "secretPresent": False})
        calls = [json.loads(s) for s in (self.root / "requests.jsonl").read_text().splitlines()]
        self.assertEqual([c["method"] for c in calls], ["initialize", "initialized", "thread/read"])
        self.assertFalse(calls[-1]["params"]["includeTurns"])

    def test_mutation_and_broad_read_refuse_before_rpc(self):
        with client.ReadProxy(self.endpoint) as proxy:
            for method, params in (("turn/start", {}), ("thread/resume", {}), ("thread/archive", {}),
                                   ("command/exec", {}), ("thread/read", {"threadId": "owned", "includeTurns": True}),
                                   ("thread/list", {})):
                with self.assertRaises(Refusal): proxy.call(method, params)
        calls = [json.loads(s) for s in (self.root / "requests.jsonl").read_text().splitlines()]
        self.assertEqual([c["method"] for c in calls], ["initialize", "initialized"])

    def test_errors_ids_duplicate_keys_server_requests_and_oversize_are_closed(self):
        for mode in ("error", "wrong_id", "duplicate", "server_request", "closed", "large"):
            with self.subTest(mode=mode):
                (self.root / "mode").write_text(mode)
                with self.assertRaises(Refusal) as error: self.read()
                self.assertNotIn("SECRET", str(error.exception))

    def test_notification_text_is_discarded(self):
        (self.root / "mode").write_text("notification")
        self.assertNotIn("SECRET", canonical(self.read()))

    def test_deadline_stops_only_owned_proxy(self):
        (self.root / "mode").write_text("timeout")
        start = time.monotonic()
        with self.assertRaisesRegex(Refusal, "deadline"): self.read(timeout=0.15)
        self.assertLess(time.monotonic()-start, 2)
        self.assertTrue((self.root / "observer.sock").exists())

    def test_server_identity_mismatch_never_sends_task_query(self):
        self.endpoint["serverIdentityHash"] = "a"*64
        with self.assertRaisesRegex(Refusal, "identity changed"): self.read()
        calls = [json.loads(s) for s in (self.root / "requests.jsonl").read_text().splitlines()]
        self.assertEqual([c["method"] for c in calls], ["initialize"])

    def test_changed_binary_or_socket_refuses_before_process(self):
        with self.binary.open("a") as stream: stream.write("# changed\n")
        with patch.object(client.subprocess, "Popen", side_effect=AssertionError("No spawn")), self.assertRaises(Refusal): self.read()

    def test_unsafe_or_symlink_endpoint_refuses(self):
        link = self.root / "link"; link.symlink_to(self.binary)
        with self.assertRaises(Refusal): client.inspect_endpoint(str(link), self.endpoint["socket"], digest(IDENTITY))
        self.binary.chmod(0o722)
        with self.assertRaises(Refusal): client.validate_endpoint(self.endpoint)

    def test_changed_socket_identity_refuses(self):
        self.endpoint["socketIdentity"]["inode"] += 1
        with patch.object(client.subprocess, "Popen", side_effect=AssertionError("No spawn")), self.assertRaises(Refusal): self.read()


def thread(tid, parent=None, status="idle"):
    return {"id": tid, "parentThreadId": parent, "status": {"type": status}, "ephemeral": False,
            "model": "fixture-model", "reasoningEffort": "high", "preview": "SECRET",
            "turns": [{"text": "SECRET"}], "path": "/secret/rollout", "cwd": "/secret/work"}


class FakeProxy:
    def __init__(self, _):
        self.calls = []; self.children = {}; self.statuses = {}; self.terminals = {}; self.callback = None
        self.query_attempted = False
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def call(self, method, params):
        self.query_attempted = True
        self.calls.append((method, copy.deepcopy(params)))
        if self.callback: self.callback(method, params)
        if method == "thread/list":
            data = [] if params["archived"] else [thread(t, p) for t, p in self.children.items() if self.root(t) == params["ancestorThreadId"]]
            return {"data": data, "nextCursor": None}
        if method == "thread/read":
            tid = params["threadId"]
            return {"thread": thread(tid, self.children.get(tid), self.statuses.get(tid, "idle"))}
        if method == "thread/backgroundTerminals/list":
            return {"data": self.terminals.get(params["threadId"], []), "nextCursor": None}
        raise AssertionError("Unsupported query")
    def root(self, tid):
        for _ in range(65):
            if tid not in self.children: return tid
            tid = self.children[tid]
        return "cycle"


class CollectionTest(EndpointFixture, unittest.TestCase):
    def setUp(self):
        self.endpoint_setup()
        self.fx = test_native_lifecycle.NativeLifecycleTest(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.fx.observe()
        self.ledger, self.token, self.store = self.fx.ledger, self.fx.token, self.fx.store
        self.aid = self.fx.fx.binding["id"]; self.bridge = self.fx.fx.bridge
        self.api = evidence.NativeEvidence(self.bridge)
        self.fx.fx.meta(paused=True)
        self.owner_request = self.request(allocationId=self.aid, endpoint=self.endpoint, confirmed=True)
        evidence.review_endpoint(self.bridge, self.owner_request, actor="dashboard_owner")
        self.fx.fx.meta(paused=False)
        self.fake = FakeProxy(self.endpoint)
        self.mock = patch.object(evidence, "ReadProxy", return_value=self.fake); self.mock.start(); self.addCleanup(self.mock.stop)

    def request(self, **fields):
        rev = self.ledger.snapshot()["meta"]["revision"]
        return {"id": "observer-"+str(rev), "expectedRevision": rev, **fields}
    def collect_request(self):
        plan = self.api.plan(self.token, self.aid)
        return self.request(**{k: plan[k] for k in ("expectedHash", "contextHash", "endpointHash")})
    def collect(self, request=None): return self.api.collect(self.token, self.aid, request or self.collect_request())
    def state(self): return self.api.state(self.token, self.aid)
    def report(self): return self.state()["report"]
    def logical(self): return self.fx.fx.fx.fx.logical(), self.store.snapshot()

    def test_scope_roots_descendants_terminals_and_sensitive_field_redaction(self):
        self.fake.children = {"child": "worker-fixture", "grandchild": "child"}
        self.fake.terminals["child"] = [{"processId": "proc-1", "itemId": "item-1", "osPid": 33, "command": "SECRET", "cwd": "/SECRET"}]
        before = self.store.snapshot(); result = self.collect(); report = self.report()
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual({s["threadId"] for s in report["samples"]}, {"brain-a", "worker-fixture", "child", "grandchild"})
        self.assertNotIn("SECRET", canonical(self.ledger.snapshot()))
        self.assertNotIn("/secret", canonical(report))
        self.assertFalse(result["executionAuthorized"])
        for key in evidence.BOUNDARY: self.assertFalse(report[key])
        self.assertEqual(report["issues"], sorted(evidence.GAPS))
        self.assertEqual(self.state()["status"], "needs_qualified_evidence")

    def test_plan_and_state_do_not_spawn_initialize_or_refresh(self):
        before = self.logical()
        self.api.plan(self.token, self.aid); self.state()
        self.assertEqual(before, self.logical()); self.assertEqual(self.fake.calls, [])

    def test_same_request_replay_is_historical_after_pause_and_revoke(self):
        request = self.collect_request(); result = self.collect(request); calls = len(self.fake.calls)
        self.fx.fx.fx.fx.command("brain_stop")
        evidence.revoke_endpoint(self.ledger, self.request(endpointHash=self.ledger.snapshot()["meta"]["nativeEvidenceEndpointHash"]), actor="dashboard_owner")
        before = self.logical()
        self.assertEqual(self.collect(request), result); self.assertEqual(len(self.fake.calls), calls)
        self.assertEqual(before, self.logical())
        self.assertIn("native_evidence_endpoint_changed", self.state()["issues"])

    def test_unknown_loaded_state_is_not_idle_and_settings_not_telemetry(self):
        self.fake.statuses["worker-fixture"] = "notLoaded"
        self.collect()
        row = next(s for s in self.report()["samples"] if s["threadId"] == "worker-fixture")
        self.assertEqual(row["activity"], "unknown")
        self.assertEqual(row["settingsSource"], "persisted_or_unknown")
        self.assertFalse(self.report()["executionTelemetryAvailable"])

    def test_newer_failed_collection_replaces_old_diagnostic_without_healthy_fallback(self):
        self.collect()
        self.fake.callback = lambda *_: (_ for _ in ()).throw(Refusal("SECRET"))
        self.collect()
        self.assertEqual(self.report()["samples"], [])
        self.assertIn("native_collection_unavailable", self.report()["issues"])
        self.assertNotIn("SECRET", canonical(self.report()))

    def test_topology_or_activity_drift_does_not_prove_a_stable_snapshot(self):
        def drift(method, params):
            if len(self.fake.calls) > 10: self.fake.statuses["worker-fixture"] = "active"
        self.fake.callback = drift
        self.collect()
        self.assertIn("native_metadata_changed_during_collection", self.report()["issues"])
        self.assertFalse(self.report()["repeatReadStable"])

    def test_pause_or_endpoint_revocation_during_io_prevents_report_commit(self):
        for change in ("pause", "revoke"):
            with self.subTest(change=change):
                request = self.collect_request()
                def modify(*_):
                    self.fake.callback = None
                    if change == "pause": self.fx.fx.fx.fx.command("brain_stop")
                    else: evidence.revoke_endpoint(self.ledger, self.request(endpointHash=request["endpointHash"]), actor="dashboard_owner")
                self.fake.callback = modify
                with self.assertRaises(Refusal): self.collect(request)
                self.assertIsNone(self.state()["report"])

    def test_late_safety_collection_while_paused_does_not_unpause(self):
        self.fx.fx.fx.fx.command("brain_stop")
        self.collect(); self.assertTrue(self.ledger.snapshot()["meta"]["paused"])

    def test_changed_scope_wrong_controller_and_foreign_allocation_refuse_before_io(self):
        request = self.collect_request()
        for change in ({"contextHash": "a"*64}, {"endpointHash": "b"*64}, {"unexpected": True}):
            with self.assertRaises(Refusal): self.collect(request | change)
        with self.assertRaises(Refusal): self.api.collect("wrong", self.aid, request)
        with self.assertRaises(Refusal): self.api.plan(self.token, "foreign-phase")
        self.assertEqual(self.fake.calls, [])

    def test_rollback_missing_pointer_and_corrupt_report_refuse(self):
        self.collect(); first = self.state()["reportHash"]; self.collect()
        with self.ledger.tx() as db:
            slot = digest({"kind": evidence.KIND, "allocationId": self.aid})
            db.execute("UPDATE snapshots SET data=? WHERE id=?", (canonical({"reportHash": first}), slot))
        with self.assertRaisesRegex(Refusal, "pointer changed"): self.state()
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (slot,))
        with self.assertRaisesRegex(Refusal, "pointer missing"): self.state()

    def test_collection_receipt_failure_rolls_back_report(self):
        before = self.logical()
        with patch.object(self.api.ledger, "event", side_effect=RuntimeError("fixture")), self.assertRaises(RuntimeError): self.collect()
        self.assertEqual(before, self.logical())

    def test_expiry_never_refreshes_on_read(self):
        self.collect(); report = self.report()
        with patch.object(evidence.time, "time", return_value=report["finishedAt"]+61):
            self.assertIn("native_evidence_stale", self.state()["issues"])
            self.assertEqual(report, self.report())

    def test_owner_only_endpoint_review_and_harness_fence(self):
        with self.assertRaises(Refusal): evidence.review_endpoint(self.bridge, self.owner_request, actor="designated_brain")
        with self.assertRaises(Refusal): evidence.revoke_endpoint(self.ledger, {}, actor="designated_brain")
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "a"); repo["policyProfile"] = "harness"; self.ledger.put(db, "repos", "a", repo)
        with patch.object(evidence, "validate_endpoint", side_effect=AssertionError("No file access")), self.assertRaisesRegex(Refusal, "Harness"):
            self.collect()

    def test_endpoint_review_replay_never_restores_revoked_permission(self):
        evidence.revoke_endpoint(self.ledger, self.request(endpointHash=self.ledger.snapshot()["meta"]["nativeEvidenceEndpointHash"]), actor="dashboard_owner")
        before = self.logical()
        evidence.review_endpoint(self.bridge, self.owner_request, actor="dashboard_owner")
        self.assertEqual(before, self.logical())
        with self.assertRaises(Refusal): self.api.plan(self.token, self.aid)

    def test_endpoint_pointer_rollback_cannot_silently_review_from_old_history(self):
        self.fx.fx.meta(paused=True)
        first = self.ledger.snapshot()["meta"]["nativeEvidenceEndpointHash"]
        evidence.review_endpoint(self.bridge, self.request(allocationId=self.aid, endpoint=self.endpoint, confirmed=True), actor="dashboard_owner")
        self.fx.fx.meta(nativeEvidenceEndpointHash=first)
        with self.assertRaisesRegex(Refusal, "pointer"):
            evidence.review_endpoint(self.bridge, self.request(allocationId=self.aid, endpoint=self.endpoint, confirmed=True), actor="dashboard_owner")
        with self.assertRaises(Refusal): self.api.plan(self.token, self.aid)

    def test_cli_requires_scope_and_has_no_owner_route(self):
        argv = [sys.executable, "-m", "orchestrator.cli", "--platform", str(self.bridge.registry.root), "--workspace", "a"]
        env = {**os.environ, "ORCHESTRATOR_CONTROLLER_TOKEN": self.token}
        result = subprocess.run(argv+["native-evidence-plan", self.aid], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["readOnlyNativeQueriesAttempted"])
        self.assertNotEqual(subprocess.run(argv+["native-evidence-review"], env=env, capture_output=True).returncode, 0)

    def test_real_cli_proxy_collection_and_replay(self):
        (self.root / "mode").write_text("collector")
        request = self.collect_request(); path = self.root / "request.json"; path.write_text(canonical(request))
        argv = [sys.executable, "-m", "orchestrator.cli", "--platform", str(self.bridge.registry.root), "--workspace", "a",
                "native-evidence-collect", self.aid, str(path)]
        env = {**os.environ, "ORCHESTRATOR_CONTROLLER_TOKEN": self.token}
        result = subprocess.run(argv, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.report()["samples"]), 2)
        calls = (self.root / "requests.jsonl").read_text()
        self.assertNotIn("SECRET", canonical(self.report()))
        replay = subprocess.run(argv, env=env, capture_output=True, text=True)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        self.assertEqual(json.loads(replay.stdout), json.loads(result.stdout))
        self.assertEqual((self.root / "requests.jsonl").read_text(), calls)
        path.write_text('{"id":"x","id":"y"}')
        self.assertNotEqual(subprocess.run(argv, env=env, capture_output=True).returncode, 0)

    def test_concurrent_same_request_retains_one_report_without_shared_mutation(self):
        request = self.collect_request(); before = self.store.snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(lambda _: self.collect(request), range(2)))
        self.assertEqual(receipts[0], receipts[1]); self.assertEqual(self.report()["version"], 1)
        self.assertEqual(before, self.store.snapshot())

    def test_foreign_or_cyclic_children_are_not_queried_or_retained(self):
        original = self.fake.call
        for child in (thread("worker-fixture", "brain-a"), thread("bad-child", "bad-child")):
            def response(method, params):
                if method == "thread/list" and params["ancestorThreadId"] == "brain-a" and not params["archived"]:
                    self.fake.query_attempted = True
                    return {"data": [child], "nextCursor": None}
                return original(method, params)
            with patch.object(self.fake, "call", side_effect=response): self.collect()
            self.assertEqual(self.report()["samples"], [])
            self.assertIn("native_collection_unavailable", self.report()["issues"])

    def test_endpoint_pin_failure_records_no_native_query_attempt(self):
        self.mock.stop()
        with self.binary.open("a") as stream: stream.write("# changed\n")
        with patch.object(client.subprocess, "Popen", side_effect=AssertionError("No spawn")): self.collect()
        self.assertFalse(self.report()["readOnlyNativeQueriesAttempted"])
        self.assertIn("native_collection_unavailable", self.report()["issues"])


class PaginationTest(unittest.TestCase):
    def test_missing_cursor_loop_and_oversize_refuse(self):
        for result in ({"data": []}, {"data": [], "nextCursor": "loop"}, {"data": [{}]*65, "nextCursor": None}):
            proxy = unittest.mock.Mock(); proxy.call.return_value = result
            with self.assertRaises(Refusal): evidence.pages(proxy, "thread/list", {})

    def test_missing_settings_and_conflicting_idle_flags_stay_unknown(self):
        row = thread("root"); row["model"] = None; row["reasoningEffort"] = None
        row["status"]["activeFlags"] = ["waitingOnUserInput"]
        value = evidence.thread_metadata(row)
        self.assertEqual(value["activity"], "unknown")
        self.assertEqual(value["configuredSettings"], {"model": None, "effort": None})


if __name__ == "__main__": unittest.main()
