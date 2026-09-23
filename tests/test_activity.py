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


class ScopedTaskActivityTest(unittest.TestCase):
    setUp = ActivityTest.setUp
    tearDown = ActivityTest.tearDown
    event = ActivityTest.event
    log = ActivityTest.log
    snapshot = ActivityTest.snapshot

    def linked(self, name='linked'):
        tree = self.root / name
        tree.mkdir()
        gitdir = self.repo / '.git' / 'worktrees' / name
        gitdir.mkdir(parents=True)
        (tree / '.git').write_text('gitdir: '+str(gitdir)+'\n')
        (gitdir / 'commondir').write_text('../..\n')
        (gitdir / 'gitdir').write_text(str(tree / '.git')+'\n')
        return tree, gitdir

    def task_state(self):
        state = self.ledger.snapshot()
        state['standard'] = {'run': {'tasks': [{'id': 'task', 'repository': 'repo', 'threadId': 'worker-test', 'status': 'active'}]}}
        return state

    def worker_log(self, cwd=None, identity='worker-test', events=None):
        path = self.logs / ('rollout-date-'+identity+'.jsonl')
        header = {'type': 'session_meta', 'payload': {'id': identity, 'cwd': str(cwd or self.repo)}}
        path.write_text('\n'.join(json.dumps(row) for row in [header, *(events or [self.event('token_count', message='PRIVATE')])])+'\n')
        return path

    def test_brain_linked_worktree_is_scoped_by_reciprocal_git_metadata(self):
        tree, _ = self.linked()
        self.log([self.event('token_count')], cwd=tree)
        self.assertEqual(self.snapshot()['status'], 'running')

    def test_forged_or_foreign_worktree_cannot_authorize_tail(self):
        tree, gitdir = self.linked()
        self.log([self.event('token_count')], cwd=tree)
        (gitdir / 'gitdir').write_text(str(self.root / 'foreign' / '.git'))
        self.assertEqual(self.snapshot()['status'], 'unknown')
        (gitdir / 'gitdir').write_text(str(tree / '.git'))
        foreign = self.root / 'foreign'
        foreign.mkdir(); (foreign / '.git').mkdir()
        (gitdir / 'commondir').write_text(str(foreign / '.git'))
        self.reader = BrainActivity(self.ledger)
        self.assertEqual(self.snapshot()['status'], 'unknown')

    def test_symlink_worktree_marker_is_refused(self):
        tree, _ = self.linked()
        marker = tree / '.git'
        target = tree / 'marker'
        marker.rename(target); marker.symlink_to(target)
        self.log([self.event('token_count')], cwd=tree)
        self.assertEqual(self.snapshot()['status'], 'unknown')

    def test_registered_worker_metadata_is_transient_scoped_and_expires(self):
        from orchestrator.activity import TaskActivity
        tree, _ = self.linked()
        self.worker_log(cwd=tree)
        state = self.task_state(); before = json.dumps(state, sort_keys=True)
        reader = TaskActivity(self.ledger)
        first = reader.snapshot(state, self.now)
        self.assertEqual(first['worker-test']['status'], 'running')
        self.assertNotIn('PRIVATE', json.dumps(first))
        self.assertNotIn(str(tree), json.dumps(first))
        self.assertEqual(json.dumps(state, sort_keys=True), before)
        later = reader.snapshot(state, self.now+121)
        self.assertFalse(later['worker-test']['fresh'])
        self.assertEqual(later['worker-test']['status'], 'unknown')
        self.assertEqual(first['worker-test']['observedAt'], later['worker-test']['observedAt'])

    def test_pending_terminal_and_unregistered_logs_are_not_read(self):
        from orchestrator.activity import TaskActivity
        self.worker_log(identity='foreign')
        state = self.task_state()
        state['standard']['run']['tasks'] = [
            {'id': 'pending', 'repository': 'repo', 'clientThreadId': 'foreign'},
            {'id': 'done', 'repository': 'repo', 'threadId': 'foreign', 'status': 'completed'}]
        with patch('orchestrator.activity.open_regular') as reader:
            self.assertEqual(TaskActivity(self.ledger).snapshot(state, self.now), {})
            reader.assert_not_called()

    def test_unconfigured_local_adapter_preserves_native_observation_fallback(self):
        from orchestrator.activity import TaskActivity
        with patch('orchestrator.activity.config', return_value={}):
            self.assertEqual(TaskActivity(self.ledger).snapshot(self.task_state(), self.now), {})

    def test_worker_root_is_its_own_repository_not_any_project_repo(self):
        from orchestrator.activity import TaskActivity
        foreign = self.root / 'foreign'; foreign.mkdir()
        self.worker_log(cwd=foreign)
        state = self.task_state()
        state['repositories'].append({'id': 'foreign', 'path': str(foreign)})
        self.assertEqual(TaskActivity(self.ledger).snapshot(state, self.now)['worker-test']['status'], 'unknown')

    def test_changed_scope_evicts_previous_task_and_read_failure_clears_activity(self):
        from orchestrator.activity import TaskActivity
        path = self.worker_log()
        state = self.task_state(); reader = TaskActivity(self.ledger)
        self.assertEqual(reader.snapshot(state, self.now)['worker-test']['status'], 'running')
        path.write_text('invalid header\n')
        failed = reader.snapshot(state, self.now+4)['worker-test']
        self.assertEqual(failed['source'], 'unavailable')
        self.assertIsNone(failed['observedAt'])
        state['standard']['run']['tasks'][0]['threadId'] = 'new-task'
        self.assertEqual(set(reader.snapshot(state, self.now+4)), {'new-task'})

    def test_task_budget_and_future_events_cannot_report_active(self):
        from orchestrator.activity import TaskActivity, MAX_TASKS
        state = self.task_state()
        state['workers'] = [{'repository':'repo','threadId':'task-'+str(i)} for i in range(MAX_TASKS)]
        with patch('orchestrator.activity.candidates') as discover:
            self.assertEqual(TaskActivity(self.ledger).snapshot(state, self.now), {})
            discover.assert_not_called()
        state = self.task_state()
        self.worker_log(events=[self.event('token_count', self.now+60)])
        self.assertEqual(TaskActivity(self.ledger).snapshot(state, self.now)['worker-test']['status'], 'unknown')


if __name__ == "__main__": unittest.main()
