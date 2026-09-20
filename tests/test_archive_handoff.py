"""Fixture-only archival lifecycle. Never calls a native tool or live archive."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import archive_handoff as archive, run_authority as runs, workspace_pause
from orchestrator.core import Refusal, canonical, digest
import test_local_preservation
import test_result_review


class ArchiveHandoffTest(unittest.TestCase):
    def setUp(self):
        self.p = test_local_preservation.PreservationHandoffTest(); self.p.setUp(); self.addCleanup(self.p.doCleanups)
        self.fx = self.p.fx
        result, request = self.p.prepare(); self.preserved = self.p.collect(request)
        self.accepted = self.fx.call("review", self.p.review_request(result, self.preserved))
        self.api = archive.ArchiveHandoff(self.fx.api.bridge)
        self.ledger, self.token, self.wid = self.fx.ledger, self.fx.token, self.fx.wid
        self.serial = 0

    def worker(self): return self.fx.fx.worker()
    def revision(self): return self.fx.revision()
    def next_id(self): self.serial += 1; return "archive-fixture-" + str(self.serial)
    def state(self): return self.api.state(self.token, self.wid)

    def inventory(self):
        at = time.time()
        return {"observedAt": at, "evidenceHash": digest("inventory fixture"), "complete": True,
                "includesDescendants": True, "effectsComplete": True, "tasks": [{
                    "hostId": "local", "threadId": self.worker()["threadId"], "status": "idle",
                    "observedAt": at, "evidenceHash": digest("task fixture"), "worktreePreserved": True}]}

    def owner(self, **payload):
        request = {"id": self.next_id(), "kind": "archive", "expectedRevision": self.revision(),
                   "payload": self.state()["ownerRequestPayload"] | payload}
        return self.ledger.submit(request, actor="explicit_user_via_brain")

    def prepare(self):
        command = self.owner(); actions = self.ledger.process(self.token)
        self.assertEqual(actions, [{"kind": "archive_handoff_required", "commandId": command["id"],
                                   "workerId": self.wid, "nativeCallMade": False, "sendPermit": False}])
        prepared = self.api.prepare(self.token, self.wid, {"commandId": command["id"], "expectedRevision": self.revision(), "inventory": self.inventory()})
        return command, prepared

    def check_request(self, prepared):
        return {"handoffHash": prepared["handoffHash"], "expectedRevision": self.revision(), "inventory": self.inventory()}

    def observation(self, prepared, outcome="archived", **fields):
        return {"id": self.next_id(), "handoffHash": prepared["handoffHash"],
                "hostId": "local", "threadId": self.worker()["threadId"],
                "expectedObservationHash": self.worker().get("archiveObservationHash"), "outcome": outcome,
                "observedAt": time.time(), "evidenceHash": digest("native fixture"), **fields}

    def cli(self, operation, request=None, *, token=None, workspace="a", select=True):
        argv = [sys.executable, "-m", "orchestrator.cli"]
        if select: argv += ["--platform", str(self.fx.registry.root), "--workspace", workspace]
        argv += ["archive-handoff-" + operation, self.wid]
        if request is not None:
            path = self.fx.root / (self.next_id()+".json"); path.write_text(canonical(request)); argv.append(str(path))
        result = subprocess.run(argv, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
                                env={**os.environ, "ORCHESTRATOR_CONTROLLER_TOKEN": token or self.token})
        return result

    def test_cli_state_prepare_check_record_round_trip(self):
        shared = self.fx.store.snapshot(); command = self.owner(); self.ledger.process(self.token)
        prepared = self.cli("prepare", {"commandId": command["id"], "expectedRevision": self.revision(), "inventory": self.inventory()})
        self.assertEqual(prepared.returncode, 0, prepared.stderr); prepared = json.loads(prepared.stdout)
        self.assertFalse(prepared["sendPermit"]); self.assertNotIn("arguments", prepared)
        checked = self.cli("check", self.check_request(prepared))
        self.assertEqual(checked.returncode, 0, checked.stderr); checked = json.loads(checked.stdout)
        self.assertEqual(checked["tool"], "set_thread_archived")
        self.assertEqual(checked["arguments"], {"hostId": "local", "threadId": self.worker()["threadId"], "archived": True})
        self.assertFalse(self.worker()["archived"]); self.assertTrue(checked["sendPermit"])
        request = self.observation(prepared); observed = self.cli("record", request)
        self.assertEqual(observed.returncode, 0, observed.stderr); observed = json.loads(observed.stdout)
        self.assertEqual(observed["outcome"], "archived"); self.assertFalse(observed["sendPermit"])
        self.assertTrue(self.worker()["archived"]); self.assertEqual(shared, self.fx.store.snapshot())
        self.assertEqual(self.fx.call("state")["review"], self.accepted)
        self.assertEqual(self.cli("state").returncode, 0)
        self.assertTrue(workspace_pause.needs_supervision(self.worker()))
        self.assertFalse(self.ledger.snapshot()["meta"]["pilotPassed"])

    def test_no_owner_request_no_archival_and_worker_id_only_stays_blocked(self):
        before = self.fx.logical()
        with self.assertRaises(Refusal):
            self.api.prepare(self.token, self.wid, {"commandId": "missing", "expectedRevision": self.revision(), "inventory": self.inventory()})
        with self.assertRaisesRegex(Refusal, "archival"):
            self.ledger.submit({"id": self.next_id(), "kind": "archive", "expectedRevision": self.revision(), "payload": {"workerId": self.wid}})
        self.assertEqual(before, self.fx.logical())

    def test_owner_bindings_cleanup_acknowledgment_and_actor_are_exact(self):
        for change in ({"reviewHash": "a"*64}, {"preservationArtifactId": "b"*64},
                       {"confirmed": False}, {"allowManagedWorktreeCleanup": False}, {"confirmed": 1}):
            with self.subTest(change=change), self.assertRaises(Refusal): self.owner(**change)
        with self.assertRaisesRegex(Refusal, "explicit owner"):
            self.ledger.submit({"id": self.next_id(), "kind": "archive", "expectedRevision": self.revision(),
                                "payload": self.state()["ownerRequestPayload"]}, actor="designated_brain")

    def test_duplicate_owner_request_and_generic_ack_refuse(self):
        command, _ = self.prepare()
        with self.assertRaises(Refusal): self.owner()
        with self.assertRaisesRegex(Refusal, "archival"): self.ledger.acknowledge(self.token, command["id"], True, "unverified")
        self.assertFalse(self.worker()["archived"])

    def test_current_inventory_idle_worktree_and_coverage_are_required(self):
        command = self.owner(); self.ledger.process(self.token)
        changes = [{"complete": False}, {"includesDescendants": False}, {"effectsComplete": False}, {"tasks": []},
                   {"observedAt": time.time()-100}, {"observedAt": time.time()+100}]
        for change in changes:
            request = {"commandId": command["id"], "expectedRevision": self.revision(), "inventory": self.inventory() | change}
            with self.subTest(change=change), self.assertRaises(Refusal): self.api.prepare(self.token, self.wid, request)
        for change in ({"status": "running"}, {"status": "unknown"}, {"threadId": "different"},
                       {"worktreePreserved": False}, {"observedAt": command["createdAt"]-1}):
            inventory = self.inventory(); inventory["tasks"][0].update(change)
            with self.subTest(change=change), self.assertRaises(Refusal):
                self.api.prepare(self.token, self.wid, {"commandId": command["id"], "expectedRevision": self.revision(), "inventory": inventory})

    def test_new_descendants_block_root_archive(self):
        command = self.owner(); self.ledger.process(self.token)
        pair = ("local", self.worker()["threadId"])
        with patch.object(self.api.results.reviewer.settlement, "known_descendants", return_value={pair, ("local", "new-child")}):
            with self.assertRaisesRegex(Refusal, "descendants"):
                self.api.prepare(self.token, self.wid, {"commandId": command["id"], "expectedRevision": self.revision(), "inventory": self.inventory()})

    def test_owner_request_must_be_received_and_check_cannot_reuse_prepare_inventory(self):
        command = self.owner(); inventory = self.inventory()
        request = {"commandId": command["id"], "expectedRevision": self.revision(), "inventory": inventory}
        with self.assertRaisesRegex(Refusal, "pending owner"): self.api.prepare(self.token, self.wid, request)
        self.ledger.process(self.token); request["expectedRevision"] = self.revision()
        prepared = self.api.prepare(self.token, self.wid, request)
        with self.assertRaisesRegex(Refusal, "predates"):
            self.api.check(self.token, self.wid, self.check_request(prepared) | {"inventory": inventory})

    def test_concurrent_send_checks_issue_exactly_one_permit(self):
        _, prepared = self.prepare(); request = self.check_request(prepared)
        def call():
            try: return self.api.check(self.token, self.wid, request)
            except Refusal: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: call(), range(2)))
        self.assertEqual(sum(bool(r and r["sendPermit"]) for r in results), 1)
        with self.assertRaises(Refusal): self.api.check(self.token, self.wid, request)
        self.assertFalse(self.state()["sendPermit"])

    def test_pause_blocks_check_but_late_confirmation_is_retained(self):
        _, prepared = self.prepare(); request = self.check_request(prepared)
        self.api.check(self.token, self.wid, request); self.fx.pause()
        with self.assertRaises(Refusal): self.api.check(self.token, self.wid, request)
        observed = self.api.record(self.token, self.wid, self.observation(prepared))
        self.assertEqual(observed["outcome"], "archived"); self.assertTrue(self.ledger.snapshot()["meta"]["paused"])

    def test_pause_before_send_blocks_and_unsent_cancel_allows_checkpointing(self):
        command, prepared = self.prepare(); self.fx.pause()
        with self.assertRaises(Refusal): self.api.check(self.token, self.wid, self.check_request(prepared))
        cancelled = self.api.record(self.token, self.wid, self.observation(prepared, "cancelled"))
        self.assertEqual(cancelled["outcome"], "cancelled"); self.assertFalse(self.worker()["archived"])
        self.assertEqual(next(c for c in self.ledger.snapshot()["commands"] if c["id"] == command["id"])["status"], "rejected")
        with self.assertRaises(Refusal): self.owner()

    def test_received_unprepared_request_does_not_claim_inflight_native_work(self):
        command = self.owner(); self.ledger.process(self.token); self.fx.pause()
        with self.ledger.tx() as db:
            control = self.ledger.get(db, "commands", command["id"])
            self.assertEqual(control["status"], "queued")
            self.assertTrue(control["archiveReceivedAt"])
            current = workspace_pause.source(self.ledger, db, {"retainedWorkers": []})
            self.assertEqual(current["pendingControls"], [])
        with self.assertRaises(Refusal):
            self.api.prepare(self.token, self.wid, {"commandId": command["id"], "expectedRevision": self.revision(), "inventory": self.inventory()})
        self.assertIsNone(self.state()["handoffHash"])

    def test_maintenance_blocks_send_but_allows_late_observation(self):
        _, prepared = self.prepare()
        fence = self.ledger.root / "admission-fence.json"; fence.touch(mode=0o600)
        with self.assertRaisesRegex(Refusal, "maintenance"): self.api.check(self.token, self.wid, self.check_request(prepared))
        fence.unlink()  # Only the empty synthetic test fence, never a live one.
        self.api.check(self.token, self.wid, self.check_request(prepared)); fence.touch(mode=0o600)
        self.assertEqual(self.api.record(self.token, self.wid, self.observation(prepared))["outcome"], "archived")

    def test_unknown_result_keeps_processing_and_cannot_be_cancelled_as_unsent(self):
        command, prepared = self.prepare(); self.api.check(self.token, self.wid, self.check_request(prepared))
        unknown_request = self.observation(prepared, "unknown")
        unknown = self.api.record(self.token, self.wid, unknown_request)
        self.assertFalse(self.worker()["archived"])
        self.assertEqual(next(c for c in self.ledger.snapshot()["commands"] if c["id"] == command["id"])["status"], "processing")
        with self.assertRaises(Refusal): self.api.record(self.token, self.wid, self.observation(prepared, "cancelled"))
        archived = self.api.record(self.token, self.wid, self.observation(prepared))
        self.assertEqual(archived["outcome"], "archived")
        self.assertEqual(self.api.record(self.token, self.wid, unknown_request), unknown)
        self.assertTrue(self.worker()["archived"])

    def test_expired_replay_and_state_do_not_refresh_or_call_tools(self):
        _, prepared = self.prepare(); self.api.check(self.token, self.wid, self.check_request(prepared))
        request = self.observation(prepared); prior = self.api.record(self.token, self.wid, request)
        self.fx.pause(); (self.ledger.root / "admission-fence.json").touch(mode=0o600); before = self.fx.logical()
        with patch("subprocess.Popen", side_effect=AssertionError("No process or transport")), \
             patch.object(self.fx.store, "clock", return_value=time.time()+1000):
            self.assertEqual(self.api.record(self.token, self.wid, request), prior)
            self.assertEqual(self.state()["observation"], prior)
            self.fx.call("state")
        self.assertEqual(before, self.fx.logical())

    def test_stale_revision_or_expired_handoff_cannot_send(self):
        _, prepared = self.prepare(); request = self.check_request(prepared)
        with self.assertRaises(Refusal): self.api.check(self.token, self.wid, request | {"expectedRevision": 0})
        with patch.object(self.fx.store, "clock", return_value=time.time()+1000), self.assertRaises(Refusal):
            self.api.check(self.token, self.wid, request)

    def test_checkpoint_request_fences_archive(self):
        _, prepared = self.prepare()
        self.ledger.submit({"id": self.next_id(), "kind": "checkpoint", "expectedRevision": self.revision(), "payload": {"workerId": self.wid}})
        with self.assertRaisesRegex(Refusal, "controls"): self.api.check(self.token, self.wid, self.check_request(prepared))

    def test_preservation_corruption_blocks_send_and_historical_state(self):
        _, prepared = self.prepare()
        with self.ledger.tx() as db:
            db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"corrupt", self.preserved["bundleArtifactId"]))
        with self.assertRaises(Refusal): self.api.check(self.token, self.wid, self.check_request(prepared))
        with self.assertRaises(Refusal): self.state()

    def test_prepare_and_send_event_failure_roll_back_their_boundaries(self):
        command = self.owner(); self.ledger.process(self.token)
        before = self.fx.logical()
        request = {"commandId": command["id"], "expectedRevision": self.revision(), "inventory": self.inventory()}
        with patch.object(self.api.ledger, "event", side_effect=RuntimeError("crash")), self.assertRaises(RuntimeError):
            self.api.prepare(self.token, self.wid, request)
        self.assertEqual(before, self.fx.logical())
        prepared = self.api.prepare(self.token, self.wid, request); before = self.fx.logical()
        with patch.object(self.api.ledger, "event", side_effect=RuntimeError("crash")), self.assertRaises(RuntimeError):
            self.api.check(self.token, self.wid, self.check_request(prepared))
        self.assertEqual(before, self.fx.logical()); self.assertIsNone(self.state()["checkHash"])

    def test_result_event_failure_does_not_partially_mark_archived(self):
        _, prepared = self.prepare(); self.api.check(self.token, self.wid, self.check_request(prepared)); before = self.fx.logical()
        request = self.observation(prepared)
        with patch.object(self.api.ledger, "event", side_effect=RuntimeError("crash")), self.assertRaises(RuntimeError):
            self.api.record(self.token, self.wid, request)
        self.assertEqual(before, self.fx.logical()); self.assertFalse(self.worker()["archived"])
        self.assertEqual(self.api.record(self.token, self.wid, request)["outcome"], "archived")

    def test_safe_pause_binding_tracks_handoff_check_and_outcome(self):
        a = workspace_pause.worker_binding(self.worker()); _, prepared = self.prepare()
        b = workspace_pause.worker_binding(self.worker()); self.assertNotEqual(a, b)
        self.api.check(self.token, self.wid, self.check_request(prepared)); c = workspace_pause.worker_binding(self.worker())
        self.assertNotEqual(b, c)
        self.api.record(self.token, self.wid, self.observation(prepared)); d = workspace_pause.worker_binding(self.worker())
        self.assertNotEqual(c, d); self.assertTrue(d["requiresNativeSupervision"])

    def test_forged_archived_projection_or_missing_slot_invalidates_review(self):
        with self.ledger.tx() as db:
            w = self.ledger.get(db, "workers", self.wid); w["archived"] = True; self.ledger.put(db, "workers", self.wid, w)
        with self.assertRaises(Refusal): self.fx.call("state")
        with self.ledger.tx() as db:
            w = self.ledger.get(db, "workers", self.wid); w["archived"] = False; self.ledger.put(db, "workers", self.wid, w)
        _, prepared = self.prepare()
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (archive.slot(self.wid),))
        with self.assertRaisesRegex(Refusal, "slot"): self.state()

    def test_missing_observation_receipt_refuses(self):
        command, prepared = self.prepare(); self.api.check(self.token, self.wid, self.check_request(prepared))
        request = self.observation(prepared); self.api.record(self.token, self.wid, request)
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (archive.observation_key(self.wid, request["id"]),))
        with self.assertRaisesRegex(Refusal, "receipt"): self.state()

    def test_changed_owner_command_invalidates_retained_handoff(self):
        command, _ = self.prepare()
        with self.ledger.tx() as db:
            control = self.ledger.get(db, "commands", command["id"])
            control["payload"]["allowManagedWorktreeCleanup"] = False
            self.ledger.put(db, "commands", command["id"], control)
        with self.assertRaisesRegex(Refusal, "owner binding"): self.state()

    def test_concurrent_outcome_replay_retains_one_record_and_changed_replay_refuses(self):
        _, prepared = self.prepare(); self.api.check(self.token, self.wid, self.check_request(prepared))
        request = self.observation(prepared)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.api.record(self.token, self.wid, request), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertTrue(self.worker()["archived"])
        with self.assertRaisesRegex(Refusal, "different content"):
            self.api.record(self.token, self.wid, request | {"evidenceHash": "b"*64})
        with self.ledger.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (archive.OBSERVATION,)).fetchone()[0], 1)

    def test_outcome_wrong_expected_binding_or_backdate_refuses(self):
        _, prepared = self.prepare()
        with self.assertRaises(Refusal): self.api.record(self.token, self.wid, self.observation(prepared))
        self.api.check(self.token, self.wid, self.check_request(prepared))
        for change in ({"expectedObservationHash": "a"*64}, {"handoffHash": "a"*64}, {"threadId": "wrong"}, {"hostId": "wrong"},
                       {"observedAt": time.time()-100}, {"observedAt": time.time()+100}, {"outcome": "failed"}):
            with self.subTest(change=change), self.assertRaises(Refusal):
                self.api.record(self.token, self.wid, self.observation(prepared, **change))

    def test_wrong_controller_workspace_and_no_default_cli_state(self):
        for args in ({"token": "wrong"}, {"workspace": "missing"}, {"select": False}):
            self.assertNotEqual(self.cli("state", **args).returncode, 0)


class ArchiveScopeTest(unittest.TestCase):
    def fixture(self, descendants=()):
        fixture = test_result_review.ResultReviewTest(); fixture.descendants = descendants
        fixture.setUp(); self.addCleanup(fixture.tearDown); fixture.review()
        return fixture, archive.ArchiveHandoff(fixture.fx.bridge)

    def test_supplied_preservation_note_cannot_authorize_archive(self):
        fixture, api = self.fixture(); before = fixture.logical()
        with self.assertRaisesRegex(Refusal, "measured local preservation"):
            api.state(fixture.token, fixture.wid)
        self.assertEqual(before, fixture.logical())

    def test_settled_descendant_tree_is_not_supported_by_first_archive_handoff(self):
        fixture, api = self.fixture(("descendant-fixture",))
        with self.assertRaisesRegex(Refusal, "without descendants"):
            api.state(fixture.token, fixture.wid)


if __name__ == "__main__": unittest.main()
