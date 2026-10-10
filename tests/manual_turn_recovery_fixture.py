"""Disposable rendered recovery rehearsal; every native response is synthetic.

PYTHONPATH=tests:. python3 tests/manual_turn_recovery_fixture.py
No live state, native host, inference service or real cancellation is used.
Ctrl-C removes only this script's temporary fixture through unittest cleanup.
"""
import copy
import time
import sys
from unittest.mock import patch

from orchestrator import projects, turn_recovery as recovery
from orchestrator.core import digest
from orchestrator.app_server_wake import NATIVE_APPROVAL_POLICY
from orchestrator.server import Dashboard
from test_standard import StandardTest
from test_turn_recovery import Proxy, TURN


class RenderProxy(Proxy):
    def _rpc(self, method, params):
        if method == "thread/read":
            return {"thread": {"id": self.scope["brainId"], "cwd": self.scope["cwd"],
                    "projectId": self.scope["projectId"],
                    "status": {"type": "active" if self.turn_status == "inProgress" else self.ended_activity}}}
        return super()._rpc(method, params)


if __name__ == "__main__":
    fixture = StandardTest(); fixture.setUp()
    native_project = "22222222-2222-4222-8222-222222222222"
    ledger, registry = fixture.ledger, fixture.registry
    fixture.control(); fixture.call("receive")
    brain_id = ledger.snapshot()["meta"]["brainId"]
    projects.record(registry, {"schemaVersion": 2, "projects": [{"projectId": native_project,
        "projectKind": "local", "label": "Disposable turn recovery", "hostId": "local",
        "path": str(fixture.repo), "isGitRepository": True}]}, time.time())
    projects.bind(registry, "alpha", "local", native_project, projects.catalog(registry)["hash"])
    binding = {"endpoint": {"fixture": "synthetic-only"}, "brains": {brain_id: {
        "workspaceId": "alpha", "projectId": native_project, "cwd": str(fixture.repo),
        "nativePolicy": NATIVE_APPROVAL_POLICY}}}
    with ledger.tx() as db:
        command = next(c for c in ledger.all(db, "commands") if c["kind"] == "standard_play")
        meta = ledger.get(db, "meta", 1)
        meta["controller"]["owner"] = brain_id + ":synthetic-" + command["id"]
        now = time.time()
        command["notification"] = {"status": "accepted", "brainId": brain_id, "attemptedAt": now - 10,
            "nativeTurnId": TURN, "nativeTurnStatus": "native_attention_required", "nativeDelivery": "owned_turn_start",
            "hostRunId": meta["standardRun"]["id"], "hostBindingHash": digest(binding),
            "nativeThreadObservation": {"version": 1, "rootThreadId": brain_id, "streamStatus": "closed",
                                        "monitoringEndedAt": now - 1, "events": []},
            "nativeResumeProfile": {"version": 1, "brainId": brain_id, "commandId": command["id"],
                "nativeTurnId": TURN, "bindingHash": digest(binding), "requested": NATIVE_APPROVAL_POLICY,
                "resumeAcknowledged": True}}
        ledger.put(db, "meta", 1, meta); ledger.put(db, "commands", command["id"], command)
    RenderProxy.cwd, RenderProxy.project_roots, RenderProxy.native_project_id = str(fixture.repo), [str(fixture.repo)], native_project
    RenderProxy.turn_status, RenderProxy.terminals = "inProgress", {"data": [], "nextCursor": None}
    RenderProxy.ended_activity = "idle"
    prior, retired = None, None
    if "--host-continuity" in sys.argv:
        prior = copy.deepcopy(binding)
        binding["endpoint"] = {"fixture": "reviewed-synthetic-replacement"}
        retired = {"version": 1, "bindingHash": digest(prior), "processId": 12345, "launchClaimHash": "c"*64}
        RenderProxy.turn_status, RenderProxy.ended_activity = "interrupted", "idle"
    class Wake:
        def __init__(self): self.binding = copy.deepcopy(binding)
        def orphan_recovery_idle(self): return True
        def configured(self, brain): return brain == brain_id
        def pending_approval(self, brain): return None
        def connection_status(self, brain):
            return {"status": "unchecked", "checkedAt": None, "detail": "Synthetic rendered rehearsal; no Codex connection."}
        def close(self): pass
    patches = [patch.object(recovery, "RecoveryProxy", RenderProxy), patch.object(recovery, "validate_endpoint"),
               patch("orchestrator.native_project_assignment.validate_endpoint"),
               patch("orchestrator.turn_host_continuity.process_absent", return_value=True)]
    for item in patches: item.start()
    server = Dashboard(ledger, 0, registry=registry, inference_env=fixture.root / "absent.env",
                       turn_recovery_prior_binding=prior, turn_recovery_retired_host=retired)
    server.runtime_for("alpha").notifier.app_server = Wake()
    server.bootstrap = "disposable-turn-recovery-ui-only"
    print(server.origin + "/#token=" + server.bootstrap, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        for item in reversed(patches): item.stop()
        fixture.tearDown()
