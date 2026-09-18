import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orchestrator.activity import BrainActivity, TAIL_BYTES
from orchestrator.core import Ledger, Refusal
from orchestrator.readiness import native_observation


class ActivityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "codex"
        self.logs = self.home / "sessions" / "2026" / "09" / "18"
        self.logs.mkdir(parents=True)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.ledger = Ledger(self.root / "state")
        self.ledger.initialize({"schemaVersion": 1, "brainId": "brain-test", "repositories": [
            {"id": "repo", "path": str(self.repo), "projectId": "project", "ref": "HEAD", "mergePolicy": "manual", "policyProfile": "standard"}]})
        (self.ledger.root / "observations.json").write_text(json.dumps({"codexHome": str(self.home)}))
        self.reader = BrainActivity(self.ledger)
        self.now = 1789710000

    def tearDown(self):
        self.temp.cleanup()

    def event(self, kind, at=None, **extra):
        return {"timestamp": dt.datetime.fromtimestamp(at or self.now, dt.timezone.utc).isoformat(),
                "type": "event_msg", "payload": {"type": kind, **extra}}

    def log(self, events, suffix="", identity="brain-test", cwd=None):
        p = self.logs / ("rollout-date-brain-test" + suffix + ".jsonl")
        header = {"type": "session_meta", "payload": {"id": identity, "cwd": str(cwd or self.repo)}}
        p.write_text("\n".join(json.dumps(r) for r in [header, *events]) + "\n")
        return p

    def snapshot(self, now=None):
        return self.reader.snapshot(self.ledger.snapshot(), self.now if now is None else now)

    def test_fresh_activity_is_separate_from_paused_dispatch_and_old_checkpoint(self):
        self.log([self.event("task_started"), self.event("token_count")])
        before = self.ledger.snapshot()
        result = self.snapshot()
        self.assertEqual(result["status"], "running")
        self.assertTrue(result["fresh"])
        after = self.ledger.snapshot()
        for key in ("meta", "queue", "workers", "events", "observations"):
            self.assertEqual(after[key], before[key])
        self.assertTrue(before["meta"]["paused"])

    def test_completion_and_failure_and_interruption(self):
        for kind, extra, status in [("task_complete", {}, "idle"), ("task_complete", {"error": "secret"}, "failed"), ("turn_aborted", {}, "interrupted")]:
            with self.subTest(kind=kind, extra=extra):
                self.log([self.event(kind, **extra)])
                self.reader = BrainActivity(self.ledger)
                self.assertEqual(self.snapshot()["status"], status)

    def test_stale_running_becomes_unknown_not_idle_and_poll_does_not_refresh_evidence(self):
        self.log([self.event("task_started")])
        first = self.snapshot()
        later = self.snapshot(self.now + 121)
        self.assertEqual(later["status"], "unknown")
        self.assertEqual(later["observedAt"], first["observedAt"])
        self.assertFalse(later["fresh"])
        self.assertEqual(later["lastKnownStatus"],"running")

    def test_stale_finished_preserves_last_observed_idle_without_claiming_freshness(self):
        self.log([self.event("task_complete")])
        result=self.snapshot(self.now+3600)
        self.assertEqual(result["status"],"unknown")
        self.assertEqual(result["lastKnownStatus"],"idle")
        self.assertEqual(result["observedAt"],self.now)
        self.assertFalse(result["fresh"])

    def test_deduplicates_continuations_and_reads_new_events(self):
        self.log([self.event("task_started", self.now - 60)])
        continuation = self.log([self.event("task_started", self.now - 60), self.event("task_complete")], "_continuation")
        self.assertEqual(len(self.snapshot()["events"]), 2)
        with continuation.open("a") as f:
            f.write(json.dumps(self.event("task_started", self.now + 4)) + "\n")
        self.assertEqual(self.snapshot(self.now + 4)["status"], "running")

    def test_file_replacement_and_truncation_do_not_leave_cached_active_state(self):
        p = self.log([self.event("task_started")])
        self.snapshot()
        p.write_text("")
        self.assertEqual(self.snapshot(self.now + 4)["status"], "unknown")

    def test_wrong_session_and_out_of_scope_header_refuse_tail(self):
        for args in ({"identity": "other"}, {"cwd": self.root / "unregistered"}):
            self.log([self.event("task_started")], **args)
            self.reader = BrainActivity(self.ledger)
            self.assertEqual(self.snapshot()["events"], [])

    def test_foreign_thread_events_are_ignored(self):
        self.log([self.event("task_started", thread_id="other")])
        self.assertEqual(self.snapshot()["status"], "unknown")

    def test_private_payloads_never_leave_reader(self):
        self.log([self.event("item_completed", item={"type": "toolCall", "arguments": "SECRET"}),
                  self.event("agent_message", message="SECRET"),
                  self.event("task_complete", last_agent_message="SECRET")])
        raw = json.dumps(self.snapshot())
        for value in ("SECRET", "arguments", "last_agent_message", str(self.logs), str(self.repo)):
            self.assertNotIn(value, raw)

    def test_malformed_and_incomplete_lines_are_safe(self):
        p = self.log([self.event("task_started")])
        with p.open("a") as f:
            f.write('not-json\n[]\n{"type":')
        self.assertEqual(self.snapshot()["status"], "running")

    def test_tail_is_bounded_and_recovers_after_large_record(self):
        p = self.log([self.event("agent_message", message="X" * (TAIL_BYTES * 2)), self.event("task_complete")])
        self.assertGreater(p.stat().st_size, TAIL_BYTES)
        self.assertEqual(self.snapshot()["status"], "idle")
        self.assertEqual(len(self.snapshot()["events"]), 1)

    def test_symlink_file_and_ancestor_are_refused(self):
        p = self.log([self.event("task_started")])
        target = self.root / "private.jsonl"
        p.rename(target); p.symlink_to(target)
        self.assertEqual(self.snapshot()["status"], "unknown")
        self.assertIn("safely", self.snapshot()["reason"])

    def test_symlink_ancestor_and_nonregular_file_are_refused(self):
        from orchestrator.activity import open_regular
        import os
        alias = self.root / "alias"
        alias.symlink_to(self.logs, target_is_directory=True)
        p = self.log([self.event("task_started")])
        with self.assertRaises(OSError): open_regular(alias / p.name)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError): open_regular(fifo)

    def test_unrelated_log_file_is_not_opened(self):
        other = self.logs / "rollout-other.jsonl"
        other.write_text("unrelated conversation")
        with patch("orchestrator.activity.open_regular") as reader:
            self.assertEqual(self.snapshot()["status"], "unknown")
            reader.assert_not_called()

    def test_missing_source_and_discovery_bounds_are_unknown(self):
        self.assertEqual(self.snapshot()["status"], "unknown")
        self.log([self.event("task_started")])
        with patch("orchestrator.activity.MAX_ENTRIES", 0):
            self.assertEqual(self.snapshot(self.now + 4)["status"], "unknown")

    def test_future_event_cannot_mark_brain_running(self):
        self.log([self.event("task_started", self.now + 60)])
        self.assertEqual(self.snapshot()["status"], "unknown")

    def test_native_observation_expires_and_newer_local_evidence_wins(self):
        state = self.ledger.snapshot()
        state["observations"]["native"] = {"observedAt": self.now - 10, "brain": {"id": "brain-test", "title": "Example brain", "status": "running"}}
        self.assertEqual(self.reader.snapshot(state, self.now)["source"], "recorded_native_observation")
        self.assertEqual(self.reader.snapshot(state, self.now + 121)["status"], "unknown")
        self.log([self.event("task_complete")])
        result = self.reader.snapshot(state, self.now + 4)
        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["title"], "Example brain")

    def test_optional_title_import_is_bounded_and_does_not_change_dispatch(self):
        import time
        record = {"schemaVersion": 1, "observedAt": time.time(), "brain": {"id": "brain-test", "title": "Example brain", "status": "idle"}, "projects": []}
        before = self.ledger.snapshot()["meta"]
        native_observation(self.ledger, record)
        self.assertEqual(self.ledger.snapshot()["meta"], before)
        record["brain"]["title"] = "X" * 201
        with self.assertRaises(Refusal): native_observation(self.ledger, record)


if __name__ == "__main__": unittest.main()
