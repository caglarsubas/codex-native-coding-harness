import contextlib
import copy
import io
import json
import os
import threading
import unittest
from unittest.mock import patch

from orchestrator import cli, missions, run_readiness, task_contracts
from orchestrator.core import Ledger, Refusal, PREFLIGHT_CHECKS, canonical, digest
from orchestrator.workspaces import fingerprint
import test_core
import test_run_readiness


class TaskContractTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_run_readiness.RunReadinessTest(); self.fx.setUp()
        self.ledger, self.registry = self.fx.ledger, self.fx.registry
        self.mission = self.fx.review()
        self.seed = test_core.seed(profile="standard")
        self.q = self.ledger.prepare(self.seed)
        self.token = self.ledger.acquire("brain-a:contract-fixture")
        self.sequence = 0

    def tearDown(self): self.fx.tearDown()

    def spec(self):
        q = self.ledger.snapshot()["queue"][0]; m = missions.read(self.ledger)
        return {"queueId": q["id"], "seedHash": q["seedHash"], "packetDigest": q["packetDigest"],
                "missionHash": m["documentHash"], "reviewReceiptHash": m["receiptHash"],
                "operations": ["edit", "test", "commit", "open_pr"],
                "requestedSettings": {"model": None, "effort": None, "speed": None},
                "estimatedTokens": 10000, "rationale": "Bounded fixture change; preserve native defaults",
                "reuseReason": "One new packet, no existing owned task"}

    def request(self, spec=None):
        self.sequence += 1
        return {"id": "contract-"+str(self.sequence), "expectedRevision": self.ledger.snapshot()["meta"]["revision"], "spec": spec or self.spec()}

    def propose(self, request=None): return task_contracts.propose(self.ledger, self.token, request or self.request())
    def read(self): return task_contracts.read(self.ledger, self.q["id"])

    def command(self, kind, payload=None):
        self.sequence += 1
        return self.ledger.submit({"id": "command-"+str(self.sequence), "kind": kind, "payload": payload or {},
                                   "expectedRevision": self.ledger.snapshot()["meta"]["revision"]})

    def logical(self):
        with contextlib.closing(self.ledger.connect()) as db: return fingerprint(db)

    def test_exact_immutable_binding_and_unknown_settings(self):
        receipt = self.propose(); result = self.read(); doc = result["document"]
        self.assertEqual(result["status"], "bound")
        self.assertEqual(digest(doc), receipt["contractHash"])
        self.assertEqual(doc["workspaceId"], "a"); self.assertEqual(doc["brainId"], "brain-a")
        self.assertEqual(doc["missionRevision"], self.mission["revision"])
        self.assertEqual(doc["spec"]["seedHash"], self.q["seedHash"])
        self.assertEqual(doc["spec"]["operations"], sorted(self.spec()["operations"]))
        self.assertFalse(receipt["executionAuthorized"]); self.assertFalse(receipt["nativeNotificationSent"])
        self.assertIsNone(result["settings"]["applied"]); self.assertIsNone(result["settings"]["observed"])
        self.assertEqual(result["settings"]["capabilityStatus"], "unverified")
        self.assertEqual(result["settings"]["policyStatus"], "not_authorized")

    def test_atomic_format_marker_reopen_and_no_upgrade_on_read(self):
        self.assertEqual(self.ledger.snapshot()["meta"]["schemaVersion"], 1)
        self.assertEqual(self.read()["status"], "not_declared")
        self.assertEqual(self.ledger.snapshot()["meta"]["schemaVersion"], 1)
        self.propose()
        self.assertEqual(Ledger(self.ledger.root).snapshot()["meta"]["schemaVersion"], 2)
        self.assertEqual(task_contracts.read(self.registry.ledger("a"), self.q["id"])["status"], "bound")

    def test_prepare_does_not_change_native_or_platform_ownership(self):
        before = self.ledger.snapshot(); self.propose(); after = self.ledger.snapshot()
        for key in ("workers", "commands", "decisions"): self.assertEqual(before[key], after[key])
        for key in ("brainId", "paused", "controller", "runner", "heartbeat", "concurrency", "pilotPassed"):
            self.assertEqual(before["meta"][key], after["meta"][key])
        self.assertFalse((self.registry.root / "admission.sqlite3").exists())

    def test_only_current_designated_brain_can_propose(self):
        req = self.request(); before = self.logical()
        with self.assertRaises(Refusal): task_contracts.propose(self.ledger, "not-a-token", req)
        self.assertEqual(before, self.logical())
        self.ledger.release(self.token, "Fixture checkpoint")
        token = self.ledger.acquire("other-brain:fixture")
        with self.assertRaises(Refusal): task_contracts.propose(self.ledger, token, self.request())

    def test_legacy_ledger_requires_explicit_workspace_identity(self):
        with self.assertRaises(Refusal): task_contracts.read(Ledger(self.ledger.root), self.q["id"])

    def test_stop_blocks_new_proposals_but_exact_receipt_can_be_recovered(self):
        req = self.request(); receipt = self.propose(req)
        self.command("brain_stop")
        with self.assertRaises(Refusal): self.propose()
        before = self.logical(); self.assertEqual(self.propose(req), receipt)
        self.assertEqual(before, self.logical())

    def test_exact_retry_does_not_reapply_after_mission_revocation(self):
        req = self.request(); receipt = self.propose(req)
        self.fx.fx.review(self.mission, "revoke")
        before = self.logical(); self.assertEqual(self.propose(req), receipt)
        self.assertEqual(self.read()["status"], "stale"); self.assertEqual(before, self.logical())
        changed = copy.deepcopy(req); changed["spec"]["estimatedTokens"] += 1
        with self.assertRaisesRegex(Refusal, "reused"): self.propose(changed)

    def test_new_version_retains_exact_history(self):
        first = self.propose(); original = self.ledger.document(first["contractHash"])
        spec = self.spec(); spec["estimatedTokens"] = 11000
        second = self.propose(self.request(spec)); result = self.read()
        self.assertEqual(result["document"]["previousHash"], first["contractHash"])
        self.assertEqual(result["version"], 2)
        self.assertEqual([r["hash"] for r in result["history"]], [second["contractHash"], first["contractHash"]])
        self.assertEqual(self.ledger.document(first["contractHash"]), original)

    def test_revisions_and_hashes_refuse_without_changes(self):
        for key in ("seedHash", "packetDigest", "missionHash", "reviewReceiptHash"):
            req = self.request(); req["spec"][key] = "f"*64
            before = self.logical()
            with self.assertRaises(Refusal): self.propose(req)
            self.assertEqual(before, self.logical())
        req = self.request(); req["expectedRevision"] -= 1
        with self.assertRaises(Refusal): self.propose(req)

    def test_operations_are_closed_and_a_phase_subset(self):
        for ops in (["deploy"], ["edit", "edit"], [], ["push"], ["merge"], ["rm -rf data"]):
            spec = self.spec(); spec["operations"] = ops
            with self.assertRaises(Refusal): self.propose(self.request(spec))

    def test_token_estimate_preserves_checkpoint_reserve(self):
        for estimate in (0, -1, True, 1.2, 90001, 10**20):
            spec = self.spec(); spec["estimatedTokens"] = estimate
            with self.assertRaises(Refusal): self.propose(self.request(spec))
        spec = self.spec(); spec["estimatedTokens"] = 90000
        self.propose(self.request(spec)); self.assertEqual(self.read()["estimatedTokens"], 90000)

    def test_closed_settings_do_not_claim_support_or_apply(self):
        spec = self.spec(); spec["requestedSettings"] = {"model": "fixture-model", "effort": "fixture-effort", "speed": "fixture-speed"}
        self.propose(self.request(spec)); settings = self.read()["settings"]
        self.assertEqual(settings["requested"], spec["requestedSettings"])
        self.assertEqual(settings["fallback"], "block"); self.assertIsNone(settings["applied"])
        for requested in ({"model": "x"}, {"model": "x", "effort": None, "speed": None, "fallback": True},
                          {"model": "https://secret/key", "effort": None, "speed": None}):
            spec["requestedSettings"] = requested
            with self.assertRaises(Refusal): self.propose(self.request(spec))

    def test_contract_fields_and_text_are_bounded(self):
        for key, value in (("rationale", ""), ("reuseReason", ""), ("rationale", "x"*2001), ("rationale", "bad\x00text")):
            spec = self.spec(); spec[key] = value
            with self.assertRaises(Refusal): self.propose(self.request(spec))
        req = self.request(); req["spec"]["approved"] = True
        with self.assertRaises(Refusal): self.propose(req)

    def test_paths_outside_phase_or_ambiguous_are_refused(self):
        for path in ("other/file", "**", "src//a.py"):
            s = copy.deepcopy(self.seed); s["allowedPaths"] = [path]; self.ledger.prepare(s)
            with self.assertRaisesRegex(Refusal, "paths"): self.propose()

    def test_changed_seed_preserves_fence_until_new_contract(self):
        first = self.propose()
        s = copy.deepcopy(self.seed); s["objective"] = "Changed bounded fixture"; self.ledger.prepare(s)
        self.assertEqual(self.read()["status"], "stale")
        self.assertTrue(self.read()["legacyDispatchBlocked"])
        self.assertEqual(self.read()["contractHash"], first["contractHash"])
        second = self.propose(); self.assertEqual(second["version"], 2)
        self.assertEqual(self.read()["status"], "bound")

    def test_changed_repository_or_mission_keeps_declaration_stale(self):
        self.propose()
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "a"); repo["projectId"] = "changed-project"
            self.ledger.put(db, "repos", "a", repo)
        self.assertEqual(self.read()["status"], "stale")
        with self.assertRaises(Refusal): self.propose()

    def test_invalid_seed_and_contract_never_allow_legacy_dispatch(self):
        receipt = self.propose()
        with self.ledger.tx() as db:
            db.execute("UPDATE snapshots SET data=? WHERE id=?", ('{"secret":"private-payload"}', receipt["contractHash"]))
        result = self.read(); self.assertEqual(result["status"], "invalid")
        self.assertIsNone(result["document"]); self.assertNotIn("private-payload", canonical(result))
        with self.assertRaises(Refusal): self.propose()
        self.assertTrue(result["legacyDispatchBlocked"])

    def test_proposal_invalidates_approval_and_preflight(self):
        self.command("approve", {"queueId": self.q["id"], "seedHash": self.q["seedHash"], "packetDigest": self.q["packetDigest"]})
        self.ledger.preflight(self.token, self.q["id"], {"seedHash": self.q["seedHash"], "packetDigest": self.q["packetDigest"],
            "baseSHA": self.seed["baseSHA"], "projectId": "project-a", "checks": {k: True for k in PREFLIGHT_CHECKS}, "evidence": ["fixture"]})
        self.propose(); q = self.ledger.snapshot()["queue"][0]
        self.assertEqual(q["status"], "proposed"); self.assertIsNone(q["approval"]); self.assertIsNone(q["preflight"])
        with self.assertRaisesRegex(Refusal, "run-aware approval"):
            self.command("approve", {"queueId": q["id"], "seedHash": q["seedHash"], "packetDigest": q["packetDigest"]})

    def test_legacy_reserve_and_begin_cannot_bypass_contract(self):
        self.propose(); self.command("resume"); self.ledger.process(self.token)
        with self.assertRaisesRegex(Refusal, "run-aware"): self.ledger.reserve(self.token, self.q["id"])
        with self.ledger.tx() as db:
            q = self.ledger.get(db, "queue", self.q["id"])
            db.execute("INSERT INTO workers VALUES(?,?,?)", ("fixture-worker", q["id"], canonical({"id": "fixture-worker", "queueId": q["id"], "status": "reserved"})))
        with self.assertRaisesRegex(Refusal, "run-aware"): self.ledger.begin_creation(self.token, "fixture-worker")

    def test_owned_packets_cannot_gain_or_replace_contract(self):
        with self.ledger.tx() as db:
            db.execute("INSERT INTO workers VALUES(?,?,?)", ("worker", self.q["id"], canonical({"id": "worker", "queueId": self.q["id"], "repository": "a", "status": "reserved"})))
        with self.assertRaises(Refusal): self.propose()

    def test_concurrent_distinct_requests_have_one_winner(self):
        requests = [self.request(), self.request()]; results = []; barrier = threading.Barrier(2)
        def run(req):
            barrier.wait()
            try: results.append(self.propose(req))
            except Refusal: results.append(None)
        threads = [threading.Thread(target=run, args=(r,)) for r in requests]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(sum(r is not None for r in results), 1); self.assertEqual(self.read()["version"], 1)

    def test_transaction_failure_rolls_back_schema_and_declaration(self):
        before = self.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("fixture abort")):
            with self.assertRaises(RuntimeError): self.propose()
        self.assertEqual(before, self.logical()); self.assertEqual(self.read()["status"], "not_declared")

    def test_first_format_upgrade_requires_paused_and_no_active_owners(self):
        self.command("resume"); self.ledger.process(self.token)
        with self.assertRaisesRegex(Refusal, "First task declaration"): self.propose()
        self.command("pause")
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["runner"] = {"workerId": "external", "since": 1}
            self.ledger.put(db, "meta", 1, meta)
        before = self.logical()
        with self.assertRaisesRegex(Refusal, "First task declaration"): self.propose()
        self.assertEqual(before, self.logical())

    def test_run_inspection_recognizes_declaration_without_granting_authority(self):
        self.propose(); before = self.logical()
        report = run_readiness.inspect(self.registry, self.ledger); packet = report["packets"][0]
        self.assertEqual(packet["taskContract"]["status"], "bound")
        codes = {i["code"] for i in packet["issues"]}
        self.assertNotIn("operation_contract_missing", codes); self.assertIn("run_authority_missing", codes)
        self.assertFalse(report["executionAuthorized"]); self.assertEqual(before, self.logical())

    def test_cli_requires_workspace_before_creating_ledger(self):
        unused = self.fx.fx.root / "unused"
        with patch("sys.argv", ["cli", "--state", str(unused), "task-contract-state", "a:TEST-001"]):
            with self.assertRaises(Refusal): cli.main()
        self.assertFalse(unused.exists())

    def test_cli_proposal_and_state(self):
        path = self.fx.fx.root / "proposal.json"; path.write_text(json.dumps(self.spec()))
        base = ["cli", "--platform", str(self.registry.root), "--workspace", "a"]
        revision = self.ledger.snapshot()["meta"]["revision"]
        with patch.dict(os.environ, {"ORCHESTRATOR_CONTROLLER_TOKEN": self.token}), patch("sys.argv", base + ["task-contract-propose", str(path), "--revision", str(revision), "--id", "cli-proposal"]), contextlib.redirect_stdout(io.StringIO()) as out:
            cli.main()
        self.assertEqual(json.loads(out.getvalue())["status"], "prepared")
        with patch("sys.argv", base + ["task-contract-state", self.q["id"]]), contextlib.redirect_stdout(io.StringIO()) as out: cli.main()
        self.assertEqual(json.loads(out.getvalue())["status"], "bound")

    def test_other_workspace_cannot_reuse_same_queue_binding(self):
        self.propose(); ledger = Ledger(self.fx.fx.root / "other")
        ledger.initialize({"schemaVersion": 1, "brainId": "brain-other", "repositories": self.ledger.snapshot()["repositories"]})
        self.registry.register("other", "Other", ledger.root); other = self.registry.ledger("other")
        other.prepare(self.seed)
        self.assertEqual(task_contracts.read(other, self.q["id"])["status"], "not_declared")
        token = other.acquire("brain-other:fixture")
        with self.assertRaises(Refusal): task_contracts.propose(other, token, self.request())

    def test_null_pointer_is_a_fence_not_a_legacy_packet(self):
        with self.ledger.tx() as db:
            q = self.ledger.get(db, "queue", self.q["id"]); q["taskContract"] = None
            self.ledger.put(db, "queue", q["id"], q)
        self.assertEqual(self.read()["status"], "invalid"); self.assertTrue(self.read()["legacyDispatchBlocked"])
        s = copy.deepcopy(self.seed); s["objective"] = "Changed"; self.ledger.prepare(s)
        self.assertEqual(self.read()["status"], "invalid")
        with self.assertRaises(Refusal): self.propose()

    def test_malformed_pointer_payload_is_not_returned(self):
        with self.ledger.tx() as db:
            q = self.ledger.get(db, "queue", self.q["id"])
            q["taskContract"] = {"hash": {"private": "hidden-value"}, "version": 1}
            self.ledger.put(db, "queue", q["id"], q)
        result = self.read(); self.assertEqual(result["status"], "invalid")
        self.assertNotIn("hidden-value", canonical(result)); self.assertIsNone(result["contractHash"])

    def test_foreign_workspace_document_is_not_returned(self):
        receipt = self.propose(); doc = self.ledger.document(receipt["contractHash"])
        doc["workspaceId"] = "other"; doc["spec"]["rationale"] = "foreign-private-rationale"
        sid = digest(doc)
        with self.ledger.tx() as db:
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (sid, "task_contract", canonical(doc)))
            q = self.ledger.get(db, "queue", self.q["id"]); q["taskContract"]["hash"] = sid
            self.ledger.put(db, "queue", q["id"], q)
        result = self.read(); self.assertEqual(result["status"], "invalid")
        self.assertNotIn("foreign-private-rationale", canonical(result))

    def test_superseded_draft_and_new_review_require_new_contract(self):
        self.propose(); new = self.fx.fx.save(copy.deepcopy(self.mission["document"]["spec"]), revision=self.mission["revision"])
        self.assertEqual(self.read()["status"], "stale")
        with self.assertRaises(Refusal): self.propose()
        self.fx.fx.review(new); self.propose()
        self.assertEqual(self.read()["status"], "bound"); self.assertEqual(self.read()["version"], 2)

    def test_corrupted_mission_and_oversized_contract_are_redacted(self):
        receipt = self.propose()
        with self.ledger.tx() as db:
            db.execute("UPDATE snapshots SET data=? WHERE id=?", ('"'+'x'*33000+'"', receipt["contractHash"]))
        self.assertEqual(self.read()["status"], "invalid")
        with self.ledger.tx() as db:
            db.execute("UPDATE snapshots SET data=? WHERE id=?", ('{"private":"not-for-output"}', self.mission["documentHash"]))
        with self.assertRaises(Refusal) as error: self.read()
        self.assertNotIn("not-for-output", str(error.exception))

    def test_same_request_concurrent_retry_commits_one_version(self):
        request = self.request(); results = []; barrier = threading.Barrier(2)
        def run():
            barrier.wait(); results.append(self.propose(request))
        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(results), 2); self.assertEqual(results[0], results[1]); self.assertEqual(self.read()["version"], 1)

    def test_harness_declaration_cannot_remove_exact_owner_policy(self):
        spec = self.mission["document"]["spec"]
        spec = copy.deepcopy(spec); spec["phase"]["scope"][0]["repository"] = "harness"
        spec["phase"]["scope"][0]["operations"].append("merge")
        current = self.fx.fx.save(spec, revision=self.mission["revision"]); self.fx.fx.review(current)
        s = test_core.seed(repo="harness"); s["completionAxes"].append("merge")
        q = self.ledger.prepare(s)
        body = self.spec(); body.update(queueId=q["id"], seedHash=q["seedHash"], packetDigest=q["packetDigest"])
        with self.assertRaisesRegex(Refusal, "merge"): self.propose(self.request(body))
        body["operations"].append("merge"); receipt = self.propose(self.request(body))
        self.assertFalse(receipt["executionAuthorized"])
        self.assertEqual(task_contracts.read(self.ledger, q["id"])["document"]["repositoryBinding"]["policyProfile"], "harness")
        spec["authority"]["approvalMode"] = "phase_delegated"
        with self.assertRaisesRegex(Refusal, "Harness"): self.fx.fx.save(spec, revision=current["revision"]+1)
