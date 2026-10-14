"""Isolated identity/history, permanent-claim and original-run conservation tests."""
import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from orchestrator import public_identity_transfer as transfer, standard
from orchestrator.app_server_wake import _read_binding as original_binding_reader
from orchestrator.app_server_wake import load_binding as original_binding_loader
from orchestrator.core import Refusal, digest
from orchestrator.workspaces import fingerprint
import test_public_task_migration as fixtures
import test_native_policy_evidence as policy


class TransferTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.MigrationTest(methodName="runTest")
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        f = self.fixture.fixture
        self.ledger, self.registry = f.ledger, f.registry
        self.source, self.destination = self.fixture.original, self.fixture.current
        self.destination["brains"][f.brain]["identityTransferEvidence"] = {
            "protocol": transfer.KIND, "sourceCommit": "a" * 40, "sourceTree": "b" * 40}
        with self.ledger.tx() as db:
            play = self.ledger.get(db, "commands", f.command_id)
            play["notification"]["nativeTurnStatus"] = "completed"
            play["notification"]["nativeThreadObservation"].update(streamStatus="closed", nativeTurnId="owned-turn-1")
            self.ledger.put(db, "commands", play["id"], play)
        self.brain, self.cwd = f.brain, self.source["brains"][f.brain]["cwd"]
        self.project_id = self.source["brains"][f.brain]["projectId"]
        self.root = f.host.fixture.fixture.root
        self.source_home, self.destination_home = self.root / "source-home", self.root / "destination-home"
        for home in (self.source_home, self.destination_home):
            home.mkdir(mode=0o700); (home / "config.toml").write_text(transfer.CONFIG); (home / "config.toml").chmod(0o600)
        sessions = self.source_home / "sessions"; sessions.mkdir(mode=0o700)
        self.file = sessions / ("rollout-original-" + self.brain + ".jsonl")
        self.meta = {"id": self.brain, "session_id": self.brain, "cwd": self.cwd, "history_mode": "legacy"}
        self.rows = [{"type": "session_meta", "payload": self.meta},
                     {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "owned-turn-1"}}]
        self.write_history()
        self.original_bytes = self.file.read_bytes()
        self.project = {"id": self.project_id, "name": "Original", "roots": [{"path": self.cwd}], "metadata": {"retained": "yes"},
                        "position": 2, "createdAt": 1000, "updatedAt": 2000, "recencyAt": 3000}
        self.thread = {"id": self.brain, "sessionId": self.brain, "projectId": self.project_id, "cwd": self.cwd,
                       "status": {"type": "notLoaded"}, "path": str(self.file),
                       "turns": [{"id": "owned-turn-1", "status": "completed", "items": []}]}
        self.calls, self.restored, self.loaded, self.assigned = [], False, False, False
        self.fail_at = self.callback = None
        outer = self
        class Proxy:
            def __init__(self, endpoint):
                self.source = endpoint == outer.source["endpoint"]
                self.initialization = {"codexHome": str(outer.source_home if self.source else outer.destination_home)}
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def _rpc(self, method, params):
                outer.calls.append((self.source, method, copy.deepcopy(params)))
                if outer.callback: outer.callback(method, params)
                if outer.fail_at == method: raise Refusal("Synthetic interrupted effect")
                if self.source:
                    if method == "project/read": return {"project": copy.deepcopy(outer.project)}
                    if method == "thread/read": return {"thread": copy.deepcopy(outer.thread)}
                    raise AssertionError("Unexpected source mutation")
                if method == "project/list": return {"data": [outer.project] if outer.restored else [], "nextCursor": None}
                if method == "thread/list": return {"data": [outer.thread] if outer.loaded else [], "nextCursor": None}
                if method == "mcpServerStatus/list": return {"data": [], "nextCursor": None}
                if method == "project/restoreMetadata":
                    outer.restored = True
                    return {"version": 1, "project": dict(outer.project, recencyAt=None)}
                if method == "thread/resume":
                    outer.loaded = True; outer.target = Path(params["path"])
                    return {"thread": {"id": outer.brain, "sessionId": outer.brain, "cwd": outer.cwd, "status": {"type": "idle"}}}
                if method == "thread/effectivePolicy/read": return policy.response(outer.brain, outer.cwd)
                if method == "thread/metadata/update": outer.assigned = True; return {"thread": {}}
                if method == "thread/read":
                    result = copy.deepcopy(outer.thread); result.update(status={"type": "idle"}, path=str(outer.target))
                    return {"thread": result}
                raise AssertionError("Unexpected destination effect")
        for item in (patch.object(transfer, "load_binding", side_effect=lambda p: copy.deepcopy(self.source if str(p) == str(self.fixture.paths[1]) else self.destination)),
                     patch.object(transfer, "TransferProxy", Proxy)):
            item.start(); self.addCleanup(item.stop)

    def write_history(self):
        self.file.write_bytes(("\n".join(json.dumps(row) for row in self.rows) + "\n").encode()); self.file.chmod(0o600)

    def prepare(self):
        self.directory = self.root / "transfer"
        result = transfer.prepare(self.registry, self.ledger, self.fixture.paths[1], self.fixture.paths[0], self.directory)
        self.spec = json.loads((self.directory / "transfer.json").read_text())
        self.review = result["reviewHash"]
        return result

    def apply(self): return transfer.apply(self.registry, self.ledger, self.spec, self.review)

    def test_exact_identity_history_and_original_usage_are_preserved_without_turn_start(self):
        with standard.read_db(self.ledger.db) as db: before = fingerprint(db)
        saved = self.ledger.snapshot()
        preview = self.prepare()
        self.assertFalse(self.restored or self.loaded or self.assigned)
        self.assertEqual(preview["validity"], "until_scope_changes")
        result = self.apply()
        self.assertEqual(result["status"], "metadata_transferred")
        self.assertTrue(self.restored and self.loaded and self.assigned)
        self.assertEqual(self.target.read_bytes(), self.original_bytes)
        self.assertEqual(self.file.read_bytes(), self.original_bytes)
        self.assertEqual(result["historicalTerminalSafety"], "unknown")
        self.assertEqual(result["sourceCurrentTerminalSafety"], "unknown")
        self.assertFalse(result["migrationQualified"] or result["resumeAuthorized"] or result["bindingInstalled"] or result["pilotAccepted"])
        self.assertEqual(self.ledger.snapshot()["meta"], saved["meta"])
        self.assertEqual(self.ledger.snapshot()["commands"], saved["commands"])
        with standard.read_db(self.ledger.db) as db: self.assertEqual(fingerprint(db), before)
        self.assertFalse(any(m in {"turn/start", "turn/interrupt", "project/import"} for _, m, _ in self.calls))

    def test_review_does_not_expire_by_reading_time(self):
        self.prepare()
        with patch.object(transfer.time, "time", return_value=99999999999):
            self.assertEqual(transfer.preview(self.spec)["reviewHash"], self.review)
            self.assertEqual(self.apply()["status"], "metadata_transferred")

    def test_exact_hash_and_closed_spec_required(self):
        self.prepare()
        with self.assertRaises(Refusal): transfer.apply(self.registry, self.ledger, self.spec, "wrong")
        self.assertFalse(self.restored)
        with self.assertRaises(Refusal): transfer.preview(dict(self.spec, arbitrary="mutation"))

    def test_repeat_and_every_interrupted_write_permanently_consume_intent(self):
        self.prepare(); self.fail_at = "project/restoreMetadata"
        with self.assertRaises(Refusal): self.apply()
        self.assertTrue((self.directory / "attempt/project_restore.claim").exists())
        count = sum(m == "project/restoreMetadata" for _, m, _ in self.calls)
        self.fail_at = None
        with self.assertRaises(Refusal): self.apply()
        self.assertEqual(sum(m == "project/restoreMetadata" for _, m, _ in self.calls), count)

    def test_failed_load_never_becomes_another_load_or_assignment(self):
        self.prepare(); self.fail_at = "thread/resume"
        with self.assertRaises(Refusal): self.apply()
        self.assertTrue((self.directory / "attempt/inspection_load.claim").exists())
        self.assertFalse(self.assigned)
        with self.assertRaises(Refusal): self.apply()
        self.assertEqual(sum(m == "thread/resume" for _, m, _ in self.calls), 1)

    def test_source_history_or_native_turn_drift_invalidates_review(self):
        self.prepare(); self.thread["turns"][-1]["id"] = "different"
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.restored)

    def test_usage_change_or_new_pause_invalidates_review(self):
        self.prepare()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["standardRun"]["brainObservedTokens"] += 1
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.restored)

    def test_source_unended_turn_or_activity_refuses_snapshot(self):
        self.thread["turns"][-1]["status"] = "inProgress"
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.restored)

    def test_foreign_project_brain_checkout_or_restricted_policy_refuses(self):
        record = self.destination["brains"][self.brain]
        for key, value in (("catalogProjectId", "changed"), ("projectId", "changed"), ("cwd", "/changed"),
                           ("nativePolicy", {"sandbox": "danger-full-access"})):
            saved = copy.deepcopy(record[key]); record[key] = value
            with self.subTest(key=key), self.assertRaises(Refusal): self.prepare()
            record[key] = saved
        self.assertFalse(self.calls)

    def test_paginated_parent_dynamic_tools_and_goal_history_are_not_flat_exports(self):
        for key, value in (("history_mode", "paginated"), ("history_base", {"foreign": "history"}),
                           ("parent_thread_id", "foreign"), ("dynamic_tools", [{"name": "secret"}])):
            self.meta[key] = value; self.write_history()
            with self.subTest(key=key), self.assertRaises(Refusal): self.prepare()
            self.meta.pop(key)
        self.rows.append({"type": "event_msg", "payload": {"type": "goal_updated"}}); self.write_history()
        with self.assertRaises(Refusal): self.prepare()

    def test_partial_duplicate_meta_symlink_and_hardlink_refuse(self):
        self.file.write_bytes(self.original_bytes[:-1])
        with self.assertRaises(Refusal): self.prepare()
        self.write_history(); self.rows.append(self.rows[0]); self.write_history()
        with self.assertRaises(Refusal): self.prepare()
        self.rows.pop(); self.write_history()
        alias = self.root / "alias"; os.link(self.file, alias)
        with self.assertRaises(Refusal): self.prepare()
        alias.unlink(); original = self.file; self.thread["path"] = str(self.root / "symlink")
        Path(self.thread["path"]).symlink_to(original)
        with self.assertRaises(Refusal): self.prepare()

    def test_destination_auth_or_different_configuration_refuses_before_claim(self):
        for name in ("auth.json", "plugins", "managed-config.toml"):
            file = self.destination_home / name; file.write_text("PRIVATE")
            with self.subTest(name=name), self.assertRaises(Refusal): self.prepare()
            file.unlink()
        (self.destination_home / "config.toml").write_text("approval_policy = 'never'\n")
        with self.assertRaises(Refusal): self.prepare()

    def test_archive_replacement_content_or_permissions_refuse(self):
        self.prepare(); archive = Path(self.spec["archivePath"])
        archive.chmod(0o600); archive.write_bytes(self.original_bytes + b"altered")
        with self.assertRaises(Refusal): self.apply()
        archive.write_bytes(self.original_bytes); archive.chmod(0o644)
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.restored)

    def test_existing_target_state_and_history_conflicts_never_overwrite(self):
        self.prepare(); self.restored = True
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.loaded)

    def test_policy_change_after_load_retains_intent_and_never_assigns_or_starts_work(self):
        self.prepare()
        original = policy.response
        def denied(*args):
            result = original(*args); result["policy"]["codeModeOffEnforced"] = False
            return result
        with patch.object(policy, "response", side_effect=denied), self.assertRaises(Refusal): self.apply()
        self.assertTrue(self.loaded)
        self.assertFalse(self.assigned)

    def test_source_snapshot_and_explicit_archive_never_copy_a_native_database(self):
        (self.source_home / "auth.json").write_text("PRIVATE")
        (self.source_home / "state.sqlite").write_text("PRIVATE")
        self.prepare(); self.apply()
        self.assertFalse((self.destination_home / "auth.json").exists())
        self.assertFalse((self.destination_home / "state.sqlite").exists())
        self.assertEqual(hashlib.sha256(self.original_bytes).hexdigest(), self.spec["snapshot"]["rollout"]["sha256"])

    def test_status_reads_only_retained_files_and_repeat_never_connects(self):
        self.prepare()
        before = copy.deepcopy(self.calls)
        self.assertEqual(transfer.status(self.directory)["status"], "prepared_not_submitted")
        self.assertEqual(self.calls, before)
        self.apply(); before = copy.deepcopy(self.calls)
        self.assertEqual(transfer.status(self.directory)["status"], "metadata_transferred")
        with self.assertRaises(Refusal): self.apply()
        self.assertEqual(self.calls, before)

    def test_interrupted_stage_is_unknown_not_safe_and_status_never_recollects(self):
        self.prepare(); self.fail_at = "thread/resume"
        with self.assertRaises(Refusal): self.apply()
        before = copy.deepcopy(self.calls)
        result = transfer.status(self.directory)
        self.assertEqual(result["status"], "outcome_unknown")
        self.assertEqual(result["terminalSafety"], "unknown")
        self.assertFalse(result["migrationQualified"])
        self.assertEqual(self.calls, before)

    def test_same_bytes_archive_replacement_still_invalidates_review(self):
        self.prepare(); archive = Path(self.spec["archivePath"])
        replacement = archive.with_name("replacement")
        replacement.write_bytes(archive.read_bytes()); replacement.chmod(0o400); os.replace(replacement, archive)
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.restored)

    def test_pause_race_after_project_restore_prevents_inspection_load(self):
        self.prepare()
        def race(method, _):
            if method == "project/restoreMetadata":
                self.callback = None
                with self.ledger.tx() as db:
                    meta = self.ledger.get(db, "meta", 1); meta["standardRun"]["status"] = "stopping"
                    self.ledger.put(db, "meta", 1, meta)
        self.callback = race
        with self.assertRaises(Refusal): self.apply()
        self.assertTrue(self.restored); self.assertFalse(self.loaded)

    def test_later_persisted_plugins_or_foreign_roots_cannot_be_inherited(self):
        for field, value in (("plugins", ["private"]), ("runtime_workspace_roots", ["/foreign"])):
            self.rows.append({"type": "event_msg", "payload": {"type": "thread_settings_applied", "thread_settings": {field: value}}})
            self.write_history()
            with self.subTest(field=field), self.assertRaises(Refusal): self.prepare()
            self.rows.pop()

    def test_ended_but_different_latest_turn_is_not_original_play_history(self):
        self.thread["turns"][-1]["id"] = "other-ended-turn"
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse((self.root / "transfer").exists())

    def test_source_catalog_change_between_claim_and_load_retains_ownership(self):
        self.prepare()
        def race(method, _):
            if method == "project/restoreMetadata":
                self.callback = None; self.project["name"] = "Changed scope"
        self.callback = race
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.loaded)

    def test_destination_configuration_race_never_loads_under_different_settings(self):
        self.prepare()
        def race(method, _):
            if method == "project/restoreMetadata":
                self.callback = None; (self.destination_home / "config.toml").write_text("approval_policy = 'never'\n")
        self.callback = race
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.loaded)

    def test_native_readable_rollout_requires_private_home_and_no_write_alias(self):
        self.file.chmod(0o644)
        self.prepare(); self.apply()
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o644)

    def test_shared_source_home_never_qualifies_as_a_private_snapshot(self):
        self.source_home.chmod(0o755)
        with self.assertRaises(Refusal): self.prepare()

    def test_group_writable_original_rollout_is_never_exported(self):
        self.file.chmod(0o660)
        with self.assertRaises(Refusal): self.prepare()

    def test_complete_self_contained_paginated_root_is_preserved_without_conversion(self):
        self.meta["history_mode"] = "paginated"
        for index, row in enumerate(self.rows): row["ordinal"] = index
        self.write_history(); original = self.file.read_bytes()
        self.prepare(); self.apply()
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(self.file.read_bytes(), original)

    def test_paginated_ordinal_gaps_duplicates_and_noninteger_values_refuse(self):
        self.meta["history_mode"] = "paginated"; self.rows[0]["ordinal"] = 0
        for ordinal in (None, 0, 2, True):
            self.rows[1]["ordinal"] = ordinal; self.write_history()
            with self.subTest(ordinal=ordinal), self.assertRaises(Refusal): self.prepare()

    def test_missing_or_different_exact_restore_build_contract_refuses_before_io(self):
        record = self.destination["brains"][self.brain]
        saved = record.pop("identityTransferEvidence")
        with self.assertRaises(Refusal): self.prepare()
        record["identityTransferEvidence"] = dict(saved, sourceCommit="c" * 40)
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.calls)

    def test_private_binding_reader_accepts_only_the_matching_opt_in_build(self):
        from orchestrator import app_server_wake
        path = self.root / "transfer-binding.json"
        path.write_text(json.dumps(self.destination)); path.chmod(0o600)
        with patch.object(app_server_wake, "validate_endpoint"), patch.object(app_server_wake, "_read_binding", original_binding_reader):
            self.assertEqual(original_binding_loader(path), self.destination)
            changed = copy.deepcopy(self.destination)
            changed["brains"][self.brain]["identityTransferEvidence"]["sourceTree"] = "c" * 40
            path.write_text(json.dumps(changed))
            with self.assertRaises(Refusal): original_binding_loader(path)

    def test_cli_preparation_and_status_are_non_waking_and_exact_apply_is_distinct(self):
        from orchestrator import cli
        def invoke(arguments):
            output = io.StringIO()
            with patch("sys.argv", ["cli", "--platform", str(self.registry.root), "--workspace", self.ledger.workspace_id, *arguments]), \
                 patch("orchestrator.workspaces.Registry", return_value=self.registry), contextlib.redirect_stdout(output):
                cli.main()
            return json.loads(output.getvalue())
        directory = self.root / "cli-transfer"
        preview = invoke(["standard-public-transfer-prepare", str(self.fixture.paths[1]), str(self.fixture.paths[0]), str(directory)])
        self.assertFalse(self.restored or self.loaded)
        saved_calls = copy.deepcopy(self.calls)
        self.assertEqual(invoke(["standard-public-transfer-status", str(directory)])["status"], "prepared_not_submitted")
        self.assertEqual(self.calls, saved_calls)
        result = invoke(["standard-public-transfer-apply", str(directory / "transfer.json"), "--confirm-hash", preview["reviewHash"]])
        self.assertEqual(result["status"], "metadata_transferred")
        self.assertFalse(result["migrationQualified"])

    def test_cli_cannot_infer_workspace_or_accept_an_implicit_apply(self):
        from orchestrator import cli
        with patch("sys.argv", ["cli", "standard-public-transfer-apply", "/missing"]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main()

    def test_new_directory_review_or_host_never_replays_a_consumed_transfer(self):
        self.prepare(); self.fail_at = "project/restoreMetadata"
        with self.assertRaises(Refusal): self.apply()
        self.fail_at = None; before = copy.deepcopy(self.calls)
        with self.assertRaises(Refusal):
            transfer.prepare(self.registry, self.ledger, self.fixture.paths[1], self.fixture.paths[0], self.root / "another-review")
        self.assertEqual(self.calls, before)
        self.assertTrue(Path(self.spec["fencePath"]).exists())

    def test_even_an_already_prepared_different_directory_is_consumed_by_the_original_play_fence(self):
        self.prepare(); first, first_review = copy.deepcopy(self.spec), self.review
        second_directory = self.root / "second-prepared"
        second_review = transfer.prepare(self.registry, self.ledger, self.fixture.paths[1], self.fixture.paths[0], second_directory)["reviewHash"]
        second = transfer.load_spec(second_directory / "transfer.json")
        transfer.apply(self.registry, self.ledger, first, first_review)
        before = copy.deepcopy(self.calls)
        with self.assertRaises(Refusal): transfer.apply(self.registry, self.ledger, second, second_review)
        self.assertTrue(transfer.status(second_directory)["consumed"])
        self.assertEqual(self.calls, before)

    def test_native_scanner_target_is_published_complete_and_without_a_hardlink_alias(self):
        self.prepare(); self.apply()
        self.assertFalse((self.target.parent / "history.pending").exists())
        self.assertEqual(self.target.stat().st_nlink, 1)

    def test_late_original_play_metadata_does_not_change_the_canonical_one_shot_identity(self):
        self.prepare(); self.fail_at = "project/restoreMetadata"
        with self.assertRaises(Refusal): self.apply()
        self.fail_at = None
        with self.ledger.tx() as db:
            play = self.ledger.get(db, "commands", self.fixture.fixture.command_id)
            play["notification"]["lateRetainedObservation"] = "fixture-only"
            self.ledger.put(db, "commands", play["id"], play)
        with self.assertRaises(Refusal):
            transfer.prepare(self.registry, self.ledger, self.fixture.paths[1], self.fixture.paths[0], self.root / "late-review")

    def test_fence_drift_after_restore_never_permits_the_inspection_load(self):
        self.prepare()
        def race(method, _):
            if method == "project/restoreMetadata":
                self.callback = None; Path(self.spec["fencePath"]).write_text('{}')
        self.callback = race
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.loaded)

    def test_unconfirmed_original_observer_never_becomes_transfer_authority(self):
        with self.ledger.tx() as db:
            play = self.ledger.get(db, "commands", self.fixture.fixture.command_id)
            play["notification"]["nativeThreadObservation"]["streamStatus"] = "unconfirmed"
            self.ledger.put(db, "commands", play["id"], play)
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.calls)


if __name__ == "__main__": unittest.main()
