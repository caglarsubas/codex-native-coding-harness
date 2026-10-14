"""Disposable ledger, public protocol and race fixtures; no live task effects."""
import copy
import subprocess
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator import public_native_tasks as tasks, native_policy_evidence as policy, standard
from orchestrator import standard_host_inspection as inspection
from orchestrator.core import Refusal, canonical, digest
import test_standard_host_inspection as host_fixtures
import test_native_policy_evidence as policy_fixtures

CONTRACT = {"protocol": tasks.PROTOCOL, "sourceCommit": "a"*40, "sourceTree": "b"*40,
            "trust": "operator_reviewed_build_v1", "desktopBridge": "absent", "repositoryMode": "repo_exclusive"}


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.host = host_fixtures.HostInspectionTest(methodName="runTest")
        self.host.setUp(); self.addCleanup(self.host.doCleanups)
        subprocess.run(["git","-C",str(self.host.fixture.repo),"-c","user.name=Fixture",
                        "-c","user.email=fixture@example.invalid","commit","--allow-empty","-qm","Fixture base"],check=True)
        self.ledger, self.registry, self.token = self.host.ledger, self.host.registry, self.host.token
        self.brain = self.host.fixture.brain_id
        self.run_id, self.command_id = self.host.run_id, self.host.command_id
        self.binding = self.host.binding
        record = self.binding["brains"][self.brain]
        record.update(policyEvidence=policy_fixtures.CONTRACT.copy(), nativeTaskBackend=CONTRACT.copy())
        self.binding["endpoint"]["sha256"] = "c"*64
        self.raw = policy_fixtures.response(self.brain, record["cwd"])
        self.fake = self.host.fixture.fake
        self.fake._rpc = lambda *_: copy.deepcopy(self.raw)
        key = inspection.retain_binding(self.ledger, self.binding)
        effective = policy.collect(self.fake, self.binding, self.brain, self.command_id)
        effective["nativeTurnId"] = "owned-turn-1"
        self.host.note["nativeResumeProfile"]["bindingHash"] = key
        self.host.update(hostBindingHash=key, hostInspectionTransport=inspection.BROKER,
                         nativeEffectivePolicy=effective, nativePolicyContract=policy_fixtures.CONTRACT.copy(),
                         nativePolicyExecutableHash="c"*64, nativeTaskContract=CONTRACT.copy())
        with self.ledger.tx() as db:
            meta = self.ledger.get(db,"meta",1)
            meta["standardRun"]["tasks"][0].update(status="claimed",effectIssued=False,threadId=None,
                                                   clientThreadId=None,nativeStatus="not_created")
            self.ledger.put(db,"meta",1,meta)
        self.thread_id, self.turn_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.calls, self.callback, self.stage = [], None, "ended"
        outer = self
        class Proxy:
            def __init__(self, endpoint, start, turn, brain_id=None):
                outer.start, outer.turn = copy.deepcopy(start), copy.deepcopy(turn)
                self.thread_id = None
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def public_environment(self): pass
            def call(self,method,params): return outer.fake.call(method,params)
            def _rpc(self,method,params):
                outer.calls.append((method,copy.deepcopy(params)))
                response=policy_fixtures.response(params["threadId"], outer.binding["brains"][outer.brain]["cwd"])
                if params["threadId"]==outer.thread_id:response["policy"]["model"]=outer.start["model"]
                return response
            def create(self):
                outer.calls.append(("thread/start",copy.deepcopy(outer.start)))
                self.thread_id = outer.thread_id
                outer.fake.threads[self.thread_id]={"id":self.thread_id,"projectId":outer.start["projectId"],
                    "cwd":outer.start["cwd"],"status":{"type":"idle"}}
                if outer.callback: outer.callback("thread/start")
                return outer.thread_id, "d"*64
            def begin(self):
                outer.calls.append(("turn/start",copy.deepcopy(outer.turn)))
                if outer.callback: outer.callback("turn/start")
                return outer.turn_id, "e"*64
            def ended(self,turn_id):
                if outer.callback: outer.callback("turn/completed")
                return outer.stage
        for item in (patch.object(tasks,"PublicTaskProxy",Proxy),
                     patch("orchestrator.app_server_wake.load_binding",side_effect=lambda _:copy.deepcopy(self.binding))):
            item.start(); self.addCleanup(item.stop)

    def request(self, token=None):
        return tasks.request(self.registry,self.ledger,token or self.token,self.run_id,self.command_id,"task-1")

    def service(self):
        return tasks.service_request(self.ledger,self.binding,self.command_id,self.brain,"owned-turn-1","task-1")

    def task(self): return standard.read(self.ledger)["run"]["tasks"][0]

    def pause(self, *_):
        with self.ledger.tx() as db:
            meta=self.ledger.get(db,"meta",1);meta["standardRun"]["status"]="stopping"
            self.ledger.put(db,"meta",1,meta)

    def test_request_has_no_protected_endpoint_prompt_or_native_call(self):
        result=self.request()
        self.assertEqual(result["stage"],"requested")
        saved=inspection._read_private(tasks._paths(self.ledger,self.command_id,"task-1")["request"])
        self.assertEqual(set(saved),tasks.REQUEST_FIELDS)
        for secret in (self.token,str(self.host.fixture.repo),"socket","instructions","method"):
            self.assertNotIn(secret,canonical(saved))
        self.assertFalse(self.calls);self.assertFalse(self.task()["effectIssued"])
        self.assertEqual(self.request(),result)

    def test_exact_seed_two_claims_late_observation_no_success_or_usage_inference(self):
        before=standard.read(self.ledger)["run"]
        self.request();self.service()
        task=self.task();proof=task["publicNative"]
        self.assertEqual(proof["stage"],"ended")
        self.assertEqual((task["threadId"],proof["turnId"]),(self.thread_id,self.turn_id))
        self.assertEqual((task["nativeStatus"],task["trackedTerminals"]),("idle","none"))
        self.assertEqual(proof["terminalCoverage"],"current_registered_task_only")
        with standard.read_db(self.ledger.db) as db:
            from orchestrator.standard_native_observation import report_in
            report=report_in(db,task["nativeObservationHash"])
        for key in ("taskTreeComplete","processTreeCleanupVerified","tokenUsageMeasured","executionAuthorized","ownershipReleased"):
            self.assertFalse(report["boundary"][key])
        self.assertIsNone(task["observedTokens"]);self.assertIsNone(task["result"])
        self.assertEqual(self.start["projectId"],self.host.fixture.project_id)
        self.assertEqual(self.start["model"],"fixture");self.assertEqual(self.turn["effort"],"low")
        self.assertIn(task["seedHash"],self.turn["input"][0]["text"])
        self.assertFalse(self.start["config"]["features"]["code_mode"]["enabled"])
        for key in ("brainObservedTokens","brainUsageCoverage","startedAt","expiresAt","ownerReceipt","limits"):
            self.assertEqual(standard.read(self.ledger)["run"][key],before[key])
        calls=copy.deepcopy(self.calls);self.service();self.request();self.assertEqual(self.calls,calls)
        self.assertEqual([m for m,_ in self.calls].count("thread/start"),1)
        self.assertEqual([m for m,_ in self.calls].count("turn/start"),1)

    def test_no_desktop_issue_or_manual_bind_fallback(self):
        with self.assertRaisesRegex(Refusal,"public task backend"):
            self.host.fixture.fixture.call("issue",taskId="task-1")
        self.request();self.stage="uncertain";self.service()
        with self.assertRaises(Refusal):
            self.host.fixture.fixture.call("bind",taskId="task-1",threadId=self.thread_id,clientThreadId=None,hostId="local")
        self.assertEqual(self.task()["publicNative"]["stage"],"uncertain")

    def test_pause_before_request_and_invalid_controller_never_collect(self):
        with self.assertRaises(Refusal): self.request("wrong")
        self.pause()
        with self.assertRaises(Refusal):self.request()
        self.assertFalse(self.calls)

    def test_pause_between_request_and_service_consumes_query_without_creation(self):
        self.request();self.pause();self.service()
        self.assertEqual(self.request()["stage"],"refused")
        self.assertFalse(self.calls);self.assertFalse(self.task()["effectIssued"])
        self.service();self.assertFalse(self.calls)

    def test_pause_after_creation_prevents_turn_and_retains_native_identity(self):
        self.request();self.callback=lambda method:self.pause() if method=="thread/start" else None
        self.service()
        self.assertEqual(self.task()["threadId"],self.thread_id)
        self.assertEqual(self.task()["publicNative"]["stage"],"pre_turn_blocked")
        self.assertNotIn("turn/start",[m for m,_ in self.calls])
        self.assertTrue(self.task()["effectIssued"])

    def test_pause_after_turn_keeps_late_facts_without_resuming_or_releasing(self):
        self.request();self.callback=lambda method:self.pause() if method=="turn/start" else None
        self.service()
        self.assertEqual(self.task()["publicNative"]["stage"],"ended")
        self.assertEqual(standard.read(self.ledger)["run"]["status"],"stopping")
        self.assertIsNotNone(self.ledger.snapshot()["meta"]["controller"])

    def test_native_permission_never_autoaccepted_or_marked_safe(self):
        self.request();self.stage="native_attention_required";self.service()
        self.assertEqual(self.task()["publicNative"]["stage"],self.stage)
        self.assertEqual(self.task()["trackedTerminals"],"unknown")
        self.assertFalse(any("Approval" in m for m,_ in self.calls))

    def test_uncertain_turn_cannot_finish_even_with_supplied_idle_observation(self):
        self.request();self.stage="uncertain";self.service()
        self.host.fixture.fixture.observe()
        with self.assertRaisesRegex(Refusal,"Uncertain public"):
            self.host.fixture.fixture.finish()

    def test_ended_turn_with_unloaded_tracker_keeps_terminal_safety_unknown(self):
        self.request()
        def unload(method):
            if method=="turn/completed":self.fake.threads[self.thread_id]["status"]={"type":"notLoaded"}
        self.callback=unload;self.service()
        self.assertEqual(self.task()["publicNative"]["stage"],"ended")
        self.assertEqual(self.task()["trackedTerminals"],"unknown")
        self.assertEqual(self.task()["publicNative"]["terminalCoverage"],"unknown")
        with self.assertRaises(Refusal):self.host.fixture.fixture.finish()

    def test_complete_public_observation_can_use_existing_result_gate_without_socket_access(self):
        self.request();self.service()
        self.assertEqual(self.task()["trackedTerminals"],"none")
        self.host.fixture.fixture.finish()
        self.assertEqual(self.task()["status"],"completed")
        self.assertEqual(standard.read(self.ledger)["run"]["status"],"running")

    def test_public_claim_marks_schema_only_at_effect_and_old_helpers_refuse(self):
        from orchestrator import core
        before=self.ledger.snapshot()["meta"]["schemaVersion"]
        self.request();self.assertEqual(self.ledger.snapshot()["meta"]["schemaVersion"],before)
        self.service()
        self.assertEqual(self.ledger.snapshot()["meta"]["schemaVersion"],5)
        with patch.object(core,"LEDGER_VERSIONS",(1,2,3,4)),self.assertRaises(Refusal):core.Ledger(self.ledger.root)
        self.host.fixture.fixture.finish()
        self.assertEqual(self.ledger.snapshot()["meta"]["schemaVersion"],5)

    def test_expired_interrupted_or_changed_request_never_reissued(self):
        self.request();paths=tasks._paths(self.ledger,self.command_id,"task-1")
        saved=inspection._read_private(paths["request"])
        with patch.object(tasks.time,"time",return_value=saved["requestedAt"]+31): self.service()
        self.assertFalse(self.calls);self.assertEqual(self.request()["stage"],"refused")
        self.assertEqual(inspection._read_private(paths["request"]),saved)

    def test_interrupted_collector_never_recollects(self):
        self.request();paths=tasks._paths(self.ledger,self.command_id,"task-1")
        inspection._write_once(paths["claim"],{"interrupted":True})
        self.service();self.assertFalse(self.calls);self.assertFalse(paths["reply"].exists())

    def test_existing_legacy_creation_never_adopted(self):
        with self.ledger.tx() as db:
            meta=self.ledger.get(db,"meta",1)
            meta["standardRun"]["tasks"][0].update(status="creating",effectIssued=True)
            self.ledger.put(db,"meta",1,meta)
        with self.assertRaisesRegex(Refusal,"fallback"):self.request()
        self.assertFalse(self.calls)

    def test_foreign_seed_or_task_or_contract_refuses_before_native_write(self):
        self.request()
        with self.ledger.tx() as db:
            meta=self.ledger.get(db,"meta",1);meta["standardRun"]["tasks"][0]["paths"]=["private.txt"]
            self.ledger.put(db,"meta",1,meta)
        self.service();self.assertFalse(self.calls)
        self.assertEqual(self.request()["stage"],"refused")

    def test_changed_model_or_repository_mode_not_silently_substituted(self):
        self.binding["brains"][self.brain]["nativeTaskBackend"]["repositoryMode"]="isolated_worktrees"
        with self.assertRaises(Refusal):tasks.arguments({"task":self.task(),"repository":{"path":"other"}},self.binding["brains"][self.brain])
        self.assertFalse(self.calls)

    def test_observer_tick_without_request_does_not_collect(self):
        from orchestrator.app_server_wake import AppServerWake
        host=AppServerWake(self.binding,self.ledger)
        tasks.service_pending(host,self.command_id,self.brain,"owned-turn-1")
        self.assertFalse(self.calls);self.assertEqual(host._public_task_workers,{})

    def test_cross_workspace_owner_and_budget_races_refuse_at_effect_boundary(self):
        self.request()
        beta, _=self.host.fixture.fixture.workspace("beta")
        with beta.tx() as db:
            meta=beta.get(db,"meta",1)
            meta["standardRun"]={"tasks":[{"id":"foreign","status":"creating","repositoryIdentity":self.task()["repositoryIdentity"]}]}
            beta.put(db,"meta",1,meta)
        self.service();self.assertFalse(self.calls)

    def test_budget_overrun_after_creation_blocks_first_turn(self):
        self.request()
        def overrun(method):
            if method=="thread/start":
                with self.ledger.tx() as db:
                    meta=self.ledger.get(db,"meta",1)
                    meta["standardRun"]["brainObservedTokens"]=10**9
                    self.ledger.put(db,"meta",1,meta)
        self.callback=overrun;self.service()
        self.assertNotIn("turn/start",[m for m,_ in self.calls])
        self.assertEqual(self.task()["publicNative"]["stage"],"pre_turn_blocked")

    def test_unloaded_new_worker_is_not_safe_to_start_or_recreate(self):
        self.request()
        def unload(method):
            if method=="thread/start":self.fake.threads[self.thread_id]["status"]={"type":"notLoaded"}
        self.callback=unload;self.service()
        self.assertNotIn("turn/start",[m for m,_ in self.calls])
        self.assertEqual(self.task()["publicNative"]["stage"],"pre_turn_blocked")
        self.assertEqual(self.task()["trackedTerminals"],"unknown")

    def test_source_base_drift_after_creation_blocks_first_turn(self):
        self.request()
        def drift(method):
            if method=="thread/start":
                subprocess.run(["git","-C",str(self.host.fixture.repo),"-c","user.name=Fixture",
                    "-c","user.email=fixture@example.invalid","commit","--allow-empty","-qm","Source drift"],check=True)
        self.callback=drift;self.service()
        self.assertNotIn("turn/start",[m for m,_ in self.calls])
        self.assertEqual(self.task()["publicNative"]["stage"],"pre_turn_blocked")

    def test_malicious_mailbox_cannot_supply_a_method_or_fake_version(self):
        self.request();paths=tasks._paths(self.ledger,self.command_id,"task-1")
        saved=inspection._read_private(paths["request"])
        paths["request"].unlink()
        inspection._write_once(paths["request"],{**saved,"version":True,"method":"turn/interrupt"})
        self.service();self.assertFalse(self.calls)


class FacadeTest(unittest.TestCase):
    def test_v5_requires_exact_marker_and_standard_run(self):
        from orchestrator.core import supported_ledger_metadata
        good={"schemaVersion":5,"publicTaskLedgerVersion":1,"standardRun":{"protocol":standard.PROTOCOL}}
        self.assertTrue(supported_ledger_metadata(good))
        for changed in ({"publicTaskLedgerVersion":True},{"publicTaskLedgerVersion":None},{"standardRun":None}):
            self.assertFalse(supported_ledger_metadata({**good,**changed}))

    def test_desktop_or_incomplete_mcp_inventory_refuses_before_creation(self):
        for result in ({"data":[{"name":"codex_app"}],"nextCursor":None},
                       {"data":[],"nextCursor":"more"},{"data":[]}):
            proxy=tasks.PublicTaskProxy({}, {}, {})
            with patch.object(proxy.proxy,"_rpc",return_value=result) as rpc,self.assertRaises(Refusal):
                proxy.public_environment()
            rpc.assert_called_once_with("mcpServerStatus/list",{"cursor":None,"limit":64,"detail":"toolsAndAuthOnly"})
            self.assertFalse(proxy.start_attempted)

    def test_closed_contract_rejects_impersonation_extra_grants_or_build_drift(self):
        for edit in ({"desktopBridge":"trusted_forwarder"},{"trust":"vendor_signed"},{"sourceCommit":"c"*40},
                     {"resumeAllowed":True},{"protocol":"codex_app"}):
            with self.assertRaises(Refusal):tasks.validate_contract({**CONTRACT,**edit},policy_fixtures.CONTRACT)

    def test_public_proxy_write_attempt_is_consumed_before_rpc_and_no_generic_write(self):
        start={"cwd":"/fixture","projectId":str(uuid.uuid4()),"model":"fixture",
               "config":{"model_reasoning_effort":"low"}}
        proxy=tasks.PublicTaskProxy({},start,{"input":[]})
        with patch.object(proxy.proxy,"_rpc",side_effect=Refusal("lost response")) as rpc:
            with self.assertRaises(Refusal):proxy.create()
            with self.assertRaises(Refusal):proxy.create()
            rpc.assert_called_once_with("thread/start",start)
        with patch.object(proxy.proxy,"_rpc") as rpc:
            for method in ("thread/resume","turn/interrupt","turn/start","thread/start"):
                with self.assertRaises(Refusal):proxy._rpc(method,{"threadId":str(uuid.uuid4())})
            rpc.assert_not_called()

    def test_foreign_creation_and_pending_id_are_not_confirmed(self):
        start={"cwd":"/fixture","projectId":str(uuid.uuid4()),"model":"fixture","config":{"model_reasoning_effort":"low"}}
        for result in ({"clientThreadId":str(uuid.uuid4())},
                       {"thread":{"id":str(uuid.uuid4()),"cwd":"/foreign","projectId":start["projectId"]},"model":"fixture","reasoningEffort":"low"}):
            proxy=tasks.PublicTaskProxy({},start,{})
            with patch.object(proxy.proxy,"_rpc",return_value=result),self.assertRaises(Refusal):proxy.create()

    def test_early_completion_is_not_current_terminal_safety(self):
        proxy=tasks.PublicTaskProxy({}, {}, {})
        proxy.thread_id=str(uuid.uuid4());turn=str(uuid.uuid4())
        proxy.proxy._early_completion=(proxy.thread_id,turn,"failed")
        self.assertEqual(proxy.ended(turn),"ended")
        proxy.proxy._early_completion=("foreign",turn,"completed")
        with patch.object(proxy.proxy,"watch_connection"),patch.object(proxy.proxy,"_line",return_value={"id":1,"method":"item/commandExecution/requestApproval"}):
            self.assertEqual(proxy.ended(turn),"native_attention_required")


if __name__=="__main__":unittest.main()
