import copy
import hashlib
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator import historical_hosts as hosts, historical_effects as history, ended_recovery_record as record
from orchestrator.core import Refusal, canonical, digest
from orchestrator.host_lifecycle import review_hash
from orchestrator.native_read_client import ReadProxy
import test_historical_effects as fixture


class MultiHostHistoryTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.HistoricalEffectsTest(); self.f.setUp()
        self.ledger = self.f.ledger
        self.pause_binding = copy.deepcopy(self.f.host.binding)
        self.play_binding = copy.deepcopy(self.pause_binding)
        self.play_binding["endpoint"] = {"historical": "play-only-never-connect"}
        self.f.host.binding["endpoint"] = {"current": "reviewed-inspection"}
        self.commands = record.saved_state(self.ledger)["commands"]
        with self.ledger.tx() as db:
            play = next(c for c in self.commands if c["kind"] == "standard_play")
            play["notification"]["hostBindingHash"] = digest(self.play_binding)
            play["notification"]["nativeThreadObservation"]["streamStatus"] = "unconfirmed"
            self.ledger.put(db, "commands", play["id"], play)
        self.chain = {"version":1, "workspaceId":self.ledger.workspace_id, "brainId":self.f.brain,
            "candidateBindingHash":digest(self.f.host.binding),
            "hosts":[self.entry(self.play_binding, 23456), self.entry(self.pause_binding, 23457)]}
        self.controls = SimpleNamespace(host_chain=self.chain, prior_binding=None, retired_host=None)
        self.f.f.f.base.runtime.historical_controls = self.controls
        self.absent = patch("orchestrator.turn_host_continuity.process_absent", return_value=True)
        self.absent_mock = self.absent.start()
        self.before = record.saved_state(self.ledger)

    def tearDown(self):
        self.absent.stop(); self.f.tearDown()

    def pin(self, path, content):
        path.write_bytes(content); path.chmod(0o600)
        return {"path":str(path), "sha256":hashlib.sha256(content).hexdigest()}

    def entry(self, binding, pid):
        folder = self.f.f.f.fixture.root / ("historical-host-"+str(pid)); folder.mkdir(mode=0o700)
        spec = {"cwd":binding["brains"][self.f.brain]["cwd"], "schemaVersion":2}
        intent = {"spec":spec, "manifestHash":digest(spec), "mode":"exec", "reviewHash":review_hash(spec,"exec")}
        return {"binding":binding, "retiredHost":{"version":1, "bindingHash":digest(binding),
                "processId":pid, "launchClaimHash":digest(intent)},
            "launch":{"intent":self.pin(folder/"launch.json", canonical(intent).encode()),
                      "process":self.pin(folder/"status.json",canonical({"pid":pid,"mode":"exec","status":"exec_boundary_issued"}).encode()),
                      "execClaim":self.pin(folder/"exec.claim", b"")}}

    def test_full_chain_preserves_unconfirmed_observer_and_original_bytes(self):
        p = self.f.preview()
        evidence = p["document"]["request"]["evidence"]
        self.assertEqual(len(evidence["hostChain"]["hosts"]),2)
        self.assertEqual(self.absent_mock.call_count,4)
        self.assertFalse(self.f.confirm(p)[1])
        after = record.saved_state(self.ledger)
        self.assertEqual(after["meta"]["standardRun"], self.before["meta"]["standardRun"])
        for command in self.before["commands"]: self.assertEqual(self.f.f.f.base.retained(command["id"]),command)
        self.assertEqual(self.f.metadata.calls[0][0],"project/read")
        self.assertFalse(set(m for m,_ in self.f.metadata.calls) & {"turn/start","turn/interrupt","thread/resume"})
        closed = self.f.preview(True); self.assertFalse(self.f.confirm(closed)[1])
        self.assertFalse(self.ledger.snapshot()["meta"]["pilotPassed"])

    def test_missing_chain_never_falls_back_to_original_endpoint(self):
        self.controls.host_chain = None
        self.f.metadata.calls.clear()
        with self.assertRaises(Refusal): self.f.preview()
        self.assertFalse(self.f.metadata.calls)

    def test_large_complete_report_has_one_signed_copy_and_fits_http_envelope(self):
        evidence = self.f.preview()["document"]["request"]["evidence"]
        # Representative complete multi-host metadata, not live pilot content.
        # The old duplicate gap/requirements projection overflowed this shape.
        report = evidence["report"]
        report["version"] = 2
        report["effectOutcome"] = "unknown"
        report["historicalTerminalCoverage"] = "unknown"
        report["taskTreeComplete"] = False
        report["gaps"] = ["historical_terminal_unknown:" + str(i).zfill(36) for i in range(34)]
        report["missingEvidence"] = [{"id": str(i).zfill(36), "turnId": "a"*36,
            "need": "historical_terminal_cleanup"} for i in range(34)]
        report["inventory"]["calls"] = [{"id": str(i).zfill(36), "turnId": "a"*36,
            "name": "exec_command", "argumentsHash": "b"*64, "commandHash": "c"*64,
            "parametersHash": "d"*64, "itemHash": "e"*64} for i in range(26)]
        self.assertGreater(len(canonical(report).encode()), 16000)
        self.assertLessEqual(len(canonical(report).encode()), 20000)
        with patch.object(history, "inspect", return_value=evidence):
            proposal = self.f.preview()
        signed = proposal["document"]["request"]["evidence"]["report"]
        self.assertEqual(signed, report, "No proof or unresolved requirement may be removed")
        details = proposal["document"]["preview"]["details"]
        self.assertNotIn("gaps", details["historicalEvidence"])
        self.assertNotIn("missingEvidence", details["historicalEvidence"])
        self.assertEqual(details["historicalGapCount"], 34)
        body = {"proposal": proposal, "confirmed": True}
        self.assertLessEqual(len(canonical(body).encode()), 30000)
        self.assertLess(len(json.dumps(body).encode()), 32768)
        self.assertEqual(record.saved_state(self.ledger), self.before)

    def test_genuinely_oversized_report_still_refuses_without_truncation(self):
        evidence = self.f.preview()["document"]["request"]["evidence"]
        evidence["report"]["gaps"] = ["unmatched_call:" + str(i).zfill(180) for i in range(200)]
        with patch.object(history, "inspect", return_value=evidence), self.assertRaises(Refusal):
            self.f.preview()
        self.assertEqual(record.saved_state(self.ledger), self.before)

    def test_every_request_host_required_no_unrelated_or_duplicate_host(self):
        original = copy.deepcopy(self.chain["hosts"])
        for entries in (original[:1], original+original[:1], []):
            self.chain["hosts"] = entries
            with self.subTest(entries=len(entries)), self.assertRaises(Refusal): self.f.preview()
        self.chain["hosts"] = original

    def test_live_reused_or_unknown_historical_pid_refuses_before_connection(self):
        self.absent_mock.return_value = False
        self.f.metadata.calls.clear()
        with self.assertRaises(Refusal): self.f.preview()
        self.assertFalse(self.f.metadata.calls)

    def test_pid_reappearing_or_launch_bytes_changed_after_review_refuses(self):
        p = self.f.preview()
        self.absent_mock.side_effect = [True,False]
        with self.assertRaises(Refusal): self.f.confirm(p)
        self.absent_mock.side_effect = None
        Path(self.chain["hosts"][0]["launch"]["process"]["path"]).write_text("{}")
        with self.assertRaises(Refusal): self.f.confirm(p)
        self.assertEqual(record.saved_state(self.ledger),self.before)

    def test_original_pid_and_reviewed_intent_must_match(self):
        for field in ("processId","launchClaimHash"):
            value = self.chain["hosts"][0]["retiredHost"][field]
            self.chain["hosts"][0]["retiredHost"][field] = 99999 if field == "processId" else "f"*64
            with self.subTest(field=field), self.assertRaises(Refusal): self.f.preview()
            self.chain["hosts"][0]["retiredHost"][field] = value

    def test_workspace_candidate_and_both_project_ids_cannot_change(self):
        for field in ("workspaceId", "brainId", "candidateBindingHash"):
            value = self.chain[field]; self.chain[field] = "f"*64
            with self.subTest(field=field), self.assertRaises(Refusal): self.f.preview()
            self.chain[field] = value
        for field in ("projectId","catalogProjectId","cwd","nativePolicy","workspaceId"):
            row = self.f.host.binding["brains"][self.f.brain]; value = row[field]; row[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(Refusal): self.f.preview()
            row[field] = value

    def test_chain_cannot_authorize_older_record_or_native_recovery(self):
        with self.assertRaises(Refusal): record.inspection_context(self.f.registry,self.ledger,self.f.host,self.controls)
        self.assertIsNone(self.f.f.controls.prior_binding)
        self.assertIsNone(self.f.f.controls.retired_host)
        self.assertFalse(hasattr(self.f.f.controls,"host_chain"))

    def test_unknown_delivery_approval_intent_later_or_active_turn_still_refuses(self):
        for change in ({"nativeDelivery":"unknown"},{"nativeApprovals":[{"id":"pending"}]}):
            with self.ledger.tx() as db:
                play = next(c for c in self.ledger.all(db,"commands") if c["kind"]=="standard_play")
                previous=copy.deepcopy(play); play["notification"].update(change); self.ledger.put(db,"commands",play["id"],play)
            with self.assertRaises(Refusal): self.f.preview()
            with self.ledger.tx() as db: self.ledger.put(db,"commands",previous["id"],previous)
        self.f.turns[-1]["status"]="inProgress"
        with self.assertRaises(Refusal):self.f.preview()

    def test_chain_file_private_and_pins_no_symlinks(self):
        path=self.f.f.f.fixture.root/"chain.json"
        self.pin(path,canonical(self.chain).encode()); self.assertEqual(hosts.load(path),self.chain)
        path.chmod(0o644)
        with self.assertRaises(Refusal):hosts.load(path)
        path.chmod(0o600); link=path.with_name("chain-link.json"); link.symlink_to(path)
        with self.assertRaises(Refusal):hosts.load(link)

    def test_retained_chain_is_revalidated_and_cannot_be_substituted(self):
        p=self.f.preview()
        evidence=p["document"]["request"]["evidence"]
        proof=history.continuity.from_browser(evidence["hostContinuity"])
        commands=history.eligible(record.saved_state(self.ledger))
        # eligible returns Pause/recovery/Play, but coverage is order-independent.
        hosts.check_retained(evidence["hostChain"],proof,commands,self.ledger)
        changed=copy.deepcopy(evidence["hostChain"])
        changed["hosts"][0]["retiredHost"]["processId"]+=1
        with self.assertRaises(Refusal):hosts.check_retained(changed,proof,commands,self.ledger)
        self.assertEqual(record.saved_state(self.ledger),self.before)


class MissingEffectEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.f=fixture.HistoricalEffectsTest(); self.f.setUp()
        self.old=self.f.metadata._rpc
        self.paged={t["id"]:[{"turnId":t["id"],"item":copy.deepcopy(i)} for i in t["items"]] for t in self.f.turns}
        self.f.metadata._rpc=self.rpc

    def tearDown(self):self.f.tearDown()

    def rpc(self,method,params):
        if method=="thread/items/list":
            self.f.metadata.calls.append((method,copy.deepcopy(params)))
            offset=int(params["cursor"] or 0); rows=self.paged[params["turnId"]]
            return {"data":copy.deepcopy(rows[offset:offset+64]),"nextCursor":str(offset+64) if offset+64<len(rows) else None}
        return self.old(method,params)

    def report(self):return self.f.preview()["document"]["request"]["evidence"]["report"]

    def test_secondary_persisted_view_recovers_exact_missing_declined_item_without_load(self):
        self.f.turns[-1]["items"]=[]
        r=self.report(); self.assertEqual(r["effectOutcome"],"not_executed")
        self.assertEqual(r["native"]["turns"][0]["persistedItemsCoverage"],"observed")
        self.assertNotIn("thread/resume",[m for m,_ in self.f.metadata.calls])

    def test_secondary_missing_result_is_not_absence_or_denial(self):
        self.f.turns[-1]["items"]=[]; self.paged["play-turn"]=[]
        r=self.report(); self.assertIn("missing_call_result:call-1",r["gaps"])
        self.assertIn({"id":"call-1","turnId":"play-turn","need":"saved_call_result"},r["missingEvidence"])

    def test_saved_output_is_hashed_but_not_a_native_denial_or_cleanup_proof(self):
        self.f.turns[-1]["items"]=[]; self.paged["play-turn"]=[]
        self.f.write_log({"type":"response_item","payload":{"type":"function_call_output","call_id":"call-1","output":"PRIVATE denied and all clean"}})
        r=self.report(); self.assertNotIn("PRIVATE",json.dumps(r))
        self.assertNotIn("missing_call_result:call-1",r["gaps"])
        self.assertIn("unmatched_effect:call-1",r["gaps"]); self.assertEqual(r["effectOutcome"],"unknown")

    def test_duplicate_foreign_or_conflicting_secondary_items_refuse(self):
        rows=copy.deepcopy(self.paged["play-turn"])
        for alter in (lambda:self.paged["play-turn"].append(copy.deepcopy(rows[0])),
                      lambda:self.paged["play-turn"][0].update(turnId="foreign"),
                      lambda:self.paged["play-turn"][0]["item"].update(status="completed",exitCode=0)):
            alter()
            with self.assertRaises(Refusal):self.report()
            self.paged["play-turn"]=copy.deepcopy(rows)

    def test_cursor_pagination_bounded_and_full(self):
        for i in range(70):self.paged["play-turn"].append({"turnId":"play-turn","item":{"id":"info-"+str(i),"type":"agentMessage","text":"PRIVATE"}})
        self.assertEqual(self.report()["effectOutcome"],"not_executed")
        self.assertTrue(any(m=="thread/items/list" and p["cursor"]=="64" for m,p in self.f.metadata.calls))

    def test_interrupted_secondary_pagination_never_discards_observed_pages(self):
        for i in range(70):self.paged["play-turn"].append({"turnId":"play-turn","item":{"id":"info-"+str(i),"type":"agentMessage"}})
        previous=self.f.metadata._rpc
        def interrupted(method,params):
            if method=="thread/items/list" and params["cursor"] is not None:raise Refusal("store read interrupted")
            return previous(method,params)
        self.f.metadata._rpc=interrupted
        with self.assertRaisesRegex(Refusal,"cannot be discarded"):self.report()

    def test_secondary_cursor_cycle_and_oversize_refuse(self):
        previous=self.f.metadata._rpc
        def cycling(method,params):
            if method=="thread/items/list":
                return {"data":[{"turnId":params["turnId"],"item":{"id":"page-"+str(params["cursor"]),"type":"agentMessage"}}],"nextCursor":"cycle"}
            return previous(method,params)
        self.f.metadata._rpc=cycling
        with self.assertRaises(Refusal):self.report()
        self.f.metadata._rpc=previous
        for i in range(history.MAX_ITEMS):self.paged["play-turn"].append({"turnId":"play-turn","item":{"id":"info-"+str(i),"type":"agentMessage"}})
        with self.assertRaises(Refusal):self.report()

    def test_secondary_entry_metadata_drift_refuses_confirmation(self):
        p=self.f.preview()
        self.paged["play-turn"][0]["completedAtMs"]=1234
        with self.assertRaises(Refusal):self.f.confirm(p)
        self.assertFalse(any(c["kind"]==history.KIND for c in record.saved_state(self.f.ledger)["commands"]))

    def test_effect_id_reuse_across_turns_refuses(self):
        item=copy.deepcopy(self.f.turns[-1]["items"][0])
        self.f.turns[0]["items"].append(item)
        self.paged[self.f.turns[0]["id"]].append({"turnId":self.f.turns[0]["id"],"item":item})
        with self.assertRaises(Refusal):self.report()

    def test_nested_executed_result_links_but_never_proves_cleanup(self):
        self.f.turns[-1]["items"][0].update(status="completed",exitCode=0)
        self.paged["play-turn"][0]["item"]=copy.deepcopy(self.f.turns[-1]["items"][0])
        self.f.write_log({"type":"event_msg","payload":{"type":"item_completed","thread_id":self.f.brain,"turn_id":"play-turn",
            "item":{"id":"call-1","type":"CommandExecution","command":"PRIVATE COMMAND","status":"Completed","exit_code":0}}})
        r=self.report(); self.assertNotIn("additional_native_effect:call-1",r["gaps"])
        self.assertIn("historical_terminal_unknown:call-1",r["gaps"])
        self.assertEqual(r["effectOutcome"],"unknown")

    def test_orphaned_duplicate_or_cross_turn_call_output_refuses(self):
        for ident in ("foreign",None):
            self.f.write_log({"type":"response_item","payload":{"type":"function_call_output","call_id":ident,"output":"PRIVATE"}})
            with self.assertRaises(Refusal):self.report()
        self.f.write_log({"type":"response_item","payload":{"type":"function_call_output","call_id":"call-1","output":"PRIVATE"}})
        lines=self.f.raw.read_text().splitlines(); self.f.raw.write_text("\n".join(lines[:3]+[lines[3]]+lines[3:])+"\n")
        with self.assertRaises(Refusal):self.report()

    def test_transport_permits_only_seen_exact_turn_and_cursor(self):
        proxy=self.f.real_proxy({}, {"brainId":"brain","projectId":"project"})
        params={"threadId":"brain","turnId":"turn","cursor":None,"limit":64,"sortDirection":"asc"}
        with self.assertRaises(Refusal):proxy._rpc("thread/items/list",params)
        proxy.history_turns.add("turn")
        with patch.object(ReadProxy,"_rpc",return_value={"data":[],"nextCursor":None}):self.assertEqual(proxy._rpc("thread/items/list",params)["data"],[])
        for change in ({"threadId":"foreign"},{"turnId":"foreign"},{"cursor":"guessed"},{"limit":100},{"sortDirection":"desc"}):
            with self.subTest(change=change), self.assertRaises(Refusal):proxy._rpc("thread/items/list",params|change)
        for method in ("thread/resume","turn/start","turn/interrupt","command/exec","thread/list","approval/respond"):
            with self.subTest(method=method), self.assertRaises(Refusal):proxy._rpc(method,{})

