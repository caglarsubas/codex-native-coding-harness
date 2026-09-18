import contextlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from orchestrator.core import Ledger, Refusal
from orchestrator.observations import (artifact, capture, capture_artifacts, git_observation,
    first_status_table, ingest_rollout, parse_checklist, read_regular, refresh_observations, usage_summary)


def usage(n):
    return dict(input_tokens=n, cached_input_tokens=n // 2, output_tokens=n // 10,
        reasoning_output_tokens=n // 20, total_tokens=n + n // 10)


def record(kind, payload, second=0):
    return {"type": kind, "timestamp": f"2026-09-18T00:00:{second:02d}Z", "payload": payload}


class ObservationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "repo"; self.repo.mkdir()
        self.ledger = Ledger(self.root / "state")
        self.aliases = {str(self.repo): "fixture"}
        self.metadata = record("session_meta", {"id": "task-1", "cwd": str(self.repo)})
        self.context = record("turn_context", {"model": "model-a", "effort": "high", "cwd": str(self.repo), "turn_id": "turn-1"}, 1)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, records):
        path.write_text("".join(json.dumps(r) + "\n" for r in records))

    def tokens(self, total, last, second):
        return record("event_msg", {"type": "token_count", "info": {"total_token_usage": usage(total), "last_token_usage": usage(last)}}, second)

    def ingest(self, path, roots=None):
        with self.ledger.tx() as db:
            ingest_rollout(db, path, self.aliases, roots or [])
            return usage_summary(db)

    def test_duplicate_archive_counters_and_incremental_replay(self):
        path = self.root / "one.jsonl"
        self.write(path, [self.metadata, self.context, self.tokens(100, 100, 2), self.tokens(100, 100, 3), self.tokens(200, 100, 4)])
        self.assertEqual(self.ingest(path)["aggregate"]["total_tokens"], 220)
        self.assertEqual(self.ingest(path)["aggregate"]["total_tokens"], 220)
        archive = self.root / "archive.jsonl"; archive.write_bytes(path.read_bytes())
        result = self.ingest(archive)
        self.assertEqual(result["aggregate"]["total_tokens"], 220)
        self.assertEqual(result["aggregate"]["sessions"], 1)
        self.assertEqual(result["coverage"]["repeatedCountersIgnored"], 1)

    def test_continuation_and_model_effort_switch_keeps_old_attribution(self):
        path = self.root / "one.jsonl"
        self.write(path, [self.metadata, self.context, self.tokens(100, 100, 2)])
        self.ingest(path)
        continuation = self.root / "continuation.jsonl"
        changed = record("turn_context", {"model": "model-b", "effort": "low", "cwd": str(self.repo)}, 3)
        self.write(continuation, [self.metadata, changed, self.tokens(200, 100, 4)])
        result = self.ingest(continuation)
        self.assertEqual(result["aggregate"]["total_tokens"], 220)
        self.assertEqual([(r["model"],r["effort"],r["total_tokens"]) for r in result["modelEffort"]], [("model-a","high",110),("model-b","low",110)])

    def test_prefix_reset_and_ambiguous_delta_are_not_full_lifetime_spend(self):
        path = self.root / "partial.jsonl"
        self.write(path, [self.metadata, self.context, self.tokens(900,100,2), self.tokens(100,100,3), self.tokens(400,100,4)])
        result = self.ingest(path)
        self.assertEqual(result["aggregate"]["total_tokens"], 330)
        self.assertEqual(result["coverage"]["missingPrefixes"], 1)
        self.assertEqual(result["coverage"]["counterResets"], 1)
        self.assertEqual(result["coverage"]["ambiguousDeltas"], 1)

    def test_fork_does_not_count_copied_parent_history(self):
        path = self.root / "fork.jsonl"
        meta = record("session_meta", {"id":"child", "forked_from_id":"task-1", "cwd":str(self.repo), "timestamp":"2026-09-18T00:00:03Z"}, 3)
        self.write(path, [meta, self.context, self.tokens(100,100,2), self.tokens(200,100,4)])
        result = self.ingest(path)
        self.assertEqual(result["aggregate"]["total_tokens"], 110)

    def test_fork_parent_header_and_retimestamped_messages_cannot_replace_identity(self):
        path = self.root / "fork.jsonl"
        child = record("session_meta", {"id":"child", "session_id":"parent", "forked_from_id":"parent", "cwd":str(self.repo), "source":{"subagent":{}}},3)
        copied_parent = record("session_meta", {"id":"parent", "cwd":str(self.repo)},3)
        copied_message = record("response_item", {"type":"message","role":"user","content":[{"text":"inherited"}]},3)
        context = record("turn_context", {"model":"model-a","effort":"high","cwd":str(self.repo)},4)
        self.write(path,[child,copied_parent,copied_message,context,self.tokens(100,100,5)])
        result = self.ingest(path)
        self.assertEqual(result["sessions"][0]["id"],"child")
        self.assertEqual(result["aggregate"]["userMessages"],0)
        self.assertEqual(result["aggregate"]["agentTasks"],1)
        self.assertEqual(result["aggregate"]["total_tokens"],110)

    def test_messages_count_once_and_no_transcripts_stored(self):
        path = self.root / "messages.jsonl"
        message = record("response_item", {"type":"message", "role":"user", "content":[{"text":"VERY_PRIVATE_TEXT"}]},2)
        self.write(path, [self.metadata,self.context,message,message,record("event_msg",{"type":"user_message","message":"VERY_PRIVATE_TEXT"},2)])
        result = self.ingest(path)
        self.assertEqual(result["aggregate"]["userMessages"],1)
        self.assertNotIn("VERY_PRIVATE_TEXT", json.dumps(result))
        with contextlib.closing(self.ledger.connect()) as db:
            self.assertNotIn("VERY_PRIVATE_TEXT", str(db.execute("SELECT data FROM usage_events").fetchall()))

    def test_incomplete_tail_recovers_and_invalid_record_diagnosed(self):
        path = self.root / "tail.jsonl"
        self.write(path,[self.metadata,self.context])
        pending = json.dumps(self.tokens(100,100,2))
        with path.open("a") as stream: stream.write(pending[:30])
        self.assertEqual(self.ingest(path)["aggregate"]["samples"],0)
        with path.open("a") as stream: stream.write(pending[30:] + "\nnot json\n")
        result = self.ingest(path)
        self.assertEqual(result["aggregate"]["samples"],1)
        self.assertEqual(result["coverage"]["malformed"],1)

    def test_unrelated_session_body_not_read_and_scope_change_reimports(self):
        path = self.root / "other.jsonl"
        self.write(path,[record("session_meta",{"id":"other","cwd":str(self.root / 'other')})])
        with path.open("a") as stream: stream.write("not json\n")
        self.assertEqual(self.ingest(path)["coverage"]["malformed"],0)
        self.aliases[str(self.root / "other")] = "other"
        self.assertEqual(self.ingest(path)["coverage"]["malformed"],1)

    def test_artifacts_preserve_versions_not_duplicate_same_bytes(self):
        with self.ledger.tx() as db:
            meta = {"name":"plan.md","references":[],"orderAt":1,"repository":"fixture"}
            one = capture(db,"plan",b"version one",meta)
            again = capture(db,"plan",b"version one",meta)
            two = capture(db,"plan",b"version two",meta)
            three = capture(db,"plan",b"version one",meta)
        self.assertEqual(one["id"],again["id"])
        self.assertEqual(two["version"],2)
        self.assertEqual(three["version"],3)
        self.assertEqual(artifact(self.ledger,one["id"])[1],b"version one")
        self.assertRaises(Refusal,artifact,self.ledger,"../../secrets")

    def test_symlink_and_parent_symlink_and_outside_roots_refused(self):
        folder = self.repo / "reports"; folder.mkdir()
        source = folder / "test.md"; source.write_text("safe")
        self.assertEqual(read_regular(source,folder,30),b"safe")
        link = folder / "link.md"; link.symlink_to(source)
        self.assertRaises(OSError,read_regular,link,folder,30)
        directory_link = self.repo / "alias"; directory_link.symlink_to(folder)
        self.assertRaises(OSError,read_regular,directory_link / "test.md",self.repo,30)
        self.assertRaises(Refusal,read_regular,source,self.root / "elsewhere",30)
        self.assertRaises(Refusal,read_regular,source,folder,2)
        self.assertRaises(Refusal,read_regular,folder / ".." / "reports" / "test.md",folder,30)

    def test_linked_artifact_and_later_task_reference(self):
        artifact_path = self.repo / "plan.md"; artifact_path.write_text("# plan")
        roots = [{"path":str(self.repo),"repository":"fixture"}]
        path = self.root / "artifact.jsonl"
        message = record("response_item",{"type":"message","role":"assistant","content":[{"text":f"[Plan](<{artifact_path}:12>)"}]},2)
        self.write(path,[self.metadata,self.context,message]); self.ingest(path,roots)
        with self.ledger.tx() as db:
            self.assertEqual(capture_artifacts(db,roots),[])
        saved = self.ledger.snapshot()["observations"]["artifacts"]
        self.assertEqual(len(saved),1)
        self.assertEqual(saved[0]["references"][0]["session"],"task-1")
        self.assertIsNone(saved[0]["createdAt"])

    def test_checklist_does_not_parse_examples_or_infer_acceptance(self):
        items = parse_checklist("# Plan\n- [x] Source done\n- [ ] Runtime pending\n```md\n- [x] example\n```\n")
        self.assertEqual(len(items),2)
        self.assertEqual([i["checked"] for i in items],[True,False])
        self.assertEqual(items[0]["line"],2)

    def test_git_tracks_dirty_worktree_and_never_claims_push_from_local_ref(self):
        def run(*args): return subprocess.run(["git","-C",str(self.repo),*args],check=True,capture_output=True)
        run("init","-b","main"); run("config","user.name","Fixture"); run("config","user.email","fixture@example.invalid")
        (self.repo / "test.md").write_text("test"); run("add","test.md"); run("commit","-m","fixture")
        repo = {"id":"fixture","path":str(self.repo),"ref":"HEAD"}
        result = git_observation(repo)
        self.assertEqual(result["status"],"measured")
        self.assertEqual(result["worktrees"][0]["status"],"clean")
        self.assertEqual(result["branches"][0]["pushStatus"],"not_observed")
        (self.repo / "test.md").write_text("modified")
        self.assertEqual(git_observation(repo)["worktrees"][0]["status"],"dirty")

    def test_remote_error_is_not_empty_success_and_does_not_execute_shell(self):
        repo = {"id":"fixture","path":None,"ref":"HEAD"}
        result = git_observation(repo,True)
        self.assertEqual(result["status"],"unavailable")

    def test_status_table_keeps_first_checkpoint_without_guessing_checkmarks(self):
        text = "# Status\n| Phase | Status |\n|---|---|\n| v1 | DONE_SOURCE |\n\n# Old\n| Phase | Status |\n|---|---|\n| v1 | WAITING |"
        table = first_status_table(text)
        self.assertEqual(table["rows"], [["v1", "DONE_SOURCE"]])
        self.assertEqual(parse_checklist(text), [])

    def test_remote_branch_comparison_does_not_mistake_base_upstream_for_push(self):
        repo = {"id":"fixture", "path":str(self.repo), "ref":"HEAD"}
        local_sha = "a" * 40
        def fake_git(path, *args, **kwargs):
            if args[:2] == ("worktree","list"): return ""
            if args[0] == "for-each-ref": return "codex/new\t" + local_sha + "\torigin/main\t\t."
            if args[:2] == ("remote","get-url"): return "git@github.com:example/project.git"
            raise AssertionError(args)
        pulls = [{"number":1,"html_url":"https://github.com/example/project/pull/1","title":"Closed, not merged","state":"closed","head":{"ref":"old","sha":local_sha},"base":{"ref":"main"},"merged_at":None}]
        responses = [subprocess.CompletedProcess([],0,json.dumps(pulls).encode()), subprocess.CompletedProcess([],0,json.dumps([{"name":"main","commit":{"sha":local_sha}}]).encode())]
        with patch("orchestrator.observations.head",return_value=local_sha), patch("orchestrator.observations.git",side_effect=fake_git), patch("orchestrator.observations.subprocess.run",side_effect=responses) as runner:
            observed = git_observation(repo,True)
        self.assertEqual(observed["branches"][0]["pushStatus"],"not_in_remote_page")
        self.assertEqual(observed["pullRequests"][0]["state"],"closed")
        self.assertIsNone(observed["pullRequests"][0]["mergeCommit"])
        for call in runner.call_args_list:
            self.assertEqual(call.args[0][:4],["gh","api","--method","GET"])
            self.assertNotIn("shell",call.kwargs)


if __name__ == "__main__": unittest.main()
