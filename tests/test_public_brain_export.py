"""Exact shared-home export, privacy, drift and immutable transfer integration."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from orchestrator import public_brain_export as export, public_identity_transfer as transfer, standard
from orchestrator.core import Refusal
from orchestrator.workspaces import fingerprint
import test_public_identity_transfer as fixtures


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.TransferTest(methodName="runTest")
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.home = self.f.source_home; self.home.chmod(0o755)
        self.f.file.chmod(0o644)
        self.directory = self.f.root / "private-export"
        self.source_path = self.f.fixture.paths[1]
        self.auth = self.home / "auth.json"; self.auth.write_text("Fixture credentials must not be copied.")
        self.sibling = self.home / "sessions/rollout-foreign.jsonl"; self.sibling.write_text("Foreign fixture conversation.")
        for item in (patch.object(export, "shared_home", return_value=self.home),
                     patch.object(export, "load_binding", side_effect=lambda _: copy.deepcopy(self.f.source)),
                     patch.object(export, "SourceProxy", side_effect=lambda endpoint, scope: transfer.TransferProxy(endpoint))):
            item.start(); self.addCleanup(item.stop)

    def collect(self):
        return export.export(self.f.registry, self.f.ledger, self.source_path, self.directory)

    def manifest(self): return self.directory / "export.json"

    def prepare(self):
        return transfer.prepare(self.f.registry, self.f.ledger, self.source_path, self.f.fixture.paths[0],
                                self.f.root / "transfer", source_export=self.manifest())

    def assert_not_written(self):
        self.assertFalse(self.f.restored or self.f.loaded or self.f.assigned)
        self.assertTrue(all(method in {"project/read", "thread/read"} for _, method, _ in self.f.calls))

    def test_exact_export_preserves_source_permissions_and_database(self):
        with standard.read_db(self.f.ledger.db) as db: before = fingerprint(db)
        old = self.f.ledger.snapshot(); modes = [p.stat().st_mode for p in (self.home, self.f.file, self.auth)]
        result = self.collect()
        self.assertEqual(result["status"], "private_export_retained")
        self.assertEqual((self.directory / "history.jsonl").read_bytes(), self.f.original_bytes)
        self.assertEqual((self.directory / "history.jsonl").stat().st_mode & 0o777, 0o400)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ["export.json", "history.jsonl", "intent.json"])
        self.assertEqual(modes, [p.stat().st_mode for p in (self.home, self.f.file, self.auth)])
        current = self.f.ledger.snapshot()
        self.assertEqual(old["meta"], current["meta"])
        self.assertEqual(old["commands"], current["commands"])
        with standard.read_db(self.f.ledger.db) as db: self.assertEqual(before, fingerprint(db))
        self.assert_not_written(); self.assertEqual(result["boundary"]["terminalSafety"], "unknown")

    def test_no_sibling_credential_config_or_native_database_is_opened(self):
        opened = []; real = os.open
        def capture(path, *args, **kwargs):
            opened.append(str(path)); return real(path, *args, **kwargs)
        with patch.object(export.os, "open", side_effect=capture): self.collect()
        self.assertFalse(any(Path(p).name in {"auth.json", "config.toml", "rollout-foreign.jsonl"} for p in opened))
        self.assertFalse(any("state_" in Path(p).name for p in opened))
        self.assert_not_written()

    def test_existing_directory_never_overwrites_or_recollects(self):
        self.collect(); calls = copy.deepcopy(self.f.calls)
        with self.assertRaises(Refusal): self.collect()
        self.assertEqual(calls, self.f.calls)

    def test_status_is_file_only_and_does_not_renew_time(self):
        first = self.collect(); calls = copy.deepcopy(self.f.calls)
        with patch.object(export.time, "time", return_value=99999999999): second = export.status(self.directory)
        self.assertEqual(first, second); self.assertEqual(calls, self.f.calls)

    def test_direct_legacy_transfer_still_refuses_shared_home(self):
        self.collect()
        with self.assertRaises(Refusal): self.f.prepare()
        self.assertFalse(self.f.restored)

    def test_export_pinned_version_two_transfer_keeps_all_existing_claims(self):
        self.collect(); preview = self.prepare()
        spec = transfer.load_spec(self.f.root / "transfer/transfer.json")
        self.assertEqual(spec["version"], 2)
        self.assertEqual(spec["sourceExport"], export.descriptor(self.manifest()))
        result = transfer.apply(self.f.registry, self.f.ledger, spec, preview["reviewHash"])
        self.assertEqual(result["status"], "metadata_transferred")
        self.assertFalse(result["migrationQualified"] or result["resumeAuthorized"])
        before = copy.deepcopy(self.f.calls)
        with self.assertRaises(Refusal): transfer.apply(self.f.registry, self.f.ledger, spec, preview["reviewHash"])
        self.assertEqual(before, self.f.calls)

    def test_changed_export_manifest_invalidates_transfer_before_native_write(self):
        self.collect(); preview = self.prepare(); spec = transfer.load_spec(self.f.root / "transfer/transfer.json")
        self.manifest().write_bytes(self.manifest().read_bytes() + b"\n")
        with self.assertRaises(Refusal): transfer.apply(self.f.registry, self.f.ledger, spec, preview["reviewHash"])
        self.assertFalse(self.f.restored)

    def test_source_change_after_export_is_not_replaced_by_private_archive(self):
        self.collect(); self.f.rows.append({"type":"event_msg","payload":{"type":"fixture_changed"}}); self.f.write_history()
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.f.restored)

    def test_usage_scope_or_original_play_drift_invalidates_export(self):
        self.collect()
        with self.f.ledger.tx() as db:
            meta = self.f.ledger.get(db,"meta",1); meta["standardRun"]["brainObservedTokens"] += 1
            self.f.ledger.put(db,"meta",1,meta)
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.f.restored)

    def test_unsafe_source_directory_or_file_permissions_refuse(self):
        for path, mode in ((self.home,0o777),(self.home/"sessions",0o777),(self.f.file,0o666)):
            original = path.stat().st_mode & 0o777; path.chmod(mode)
            with self.subTest(path=path), self.assertRaises(Refusal): self.collect()
            path.chmod(original)
        self.assertFalse(self.directory.exists())

    def test_shared_home_must_be_exact_os_user_scope(self):
        with patch.object(export,"shared_home",return_value=self.f.root/"another-user"), self.assertRaises(Refusal): self.collect()
        self.assertFalse(self.directory.exists())

    def test_source_symlink_or_hardlink_alias_refuses(self):
        alias=self.f.file.with_suffix(".alias"); self.f.file.rename(alias); self.f.file.symlink_to(alias)
        with self.assertRaises(Refusal): self.collect()
        self.f.file.unlink(); alias.rename(self.f.file)
        os.link(self.f.file,alias)
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse(self.directory.exists())

    def test_symlinked_session_ancestor_refuses(self):
        sessions=self.home/"sessions"; moved=self.home/"moved"; sessions.rename(moved); sessions.symlink_to(moved)
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse(self.directory.exists())

    def test_native_foreign_path_cannot_export_a_sibling(self):
        self.f.thread["path"] = str(self.sibling)
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse(self.directory.exists())

    def test_foreign_session_identity_checkout_or_history_base_refuses(self):
        for key,value in (("id","foreign"),("cwd","/foreign"),("history_base",{"foreign":"root"}),
                          ("parent_thread_id","foreign"),("dynamic_tools",[{"name":"opaque"}])):
            saved=copy.deepcopy(self.f.meta); self.f.meta[key]=value; self.f.write_history()
            with self.subTest(key=key),self.assertRaises(Refusal): self.collect()
            self.f.meta=saved; self.f.write_history()
        self.assertFalse(self.directory.exists())

    def test_goal_or_persisted_capabilities_remain_unsupported(self):
        for payload in ({"type":"goal_updated"},
                        {"type":"thread_settings_applied","thread_settings":{"plugin_refs":["fixture"]}}):
            self.f.rows.append({"type":"event_msg","payload":payload}); self.f.write_history()
            with self.subTest(payload=payload),self.assertRaises(Refusal): self.collect()
            self.f.rows.pop(); self.f.write_history()

    def test_partial_or_invalid_paginated_root_refuses(self):
        self.f.file.write_bytes(self.f.original_bytes[:-1])
        with self.assertRaises(Refusal): self.collect()
        self.f.meta["history_mode"]="paginated"; self.f.write_history()
        with self.assertRaises(Refusal): self.collect()
        for ordinal,row in enumerate(self.f.rows): row["ordinal"]=ordinal
        self.f.write_history(); self.assertEqual(self.collect()["status"],"private_export_retained")

    def test_active_or_different_latest_turn_refuses_without_loading(self):
        for change in ({"id":"different","status":"completed"},{"id":"owned-turn-1","status":"inProgress"}):
            self.f.thread["turns"]=[change]
            with self.subTest(change=change),self.assertRaises(Refusal): self.collect()
        self.assert_not_written()

    def test_racing_pause_or_native_view_change_never_publishes_export(self):
        reads=0
        def race(method,params):
            nonlocal reads
            if method == "thread/read":
                reads+=1
                if reads == 2: self.f.thread["turns"][-1]["id"]="changed"
        self.f.callback=race
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse(self.directory.exists())

    def test_racing_context_after_archive_keeps_partial_unknown(self):
        reads=0
        def race(method,params):
            nonlocal reads
            if method == "thread/read":
                reads+=1
                if reads == 3:
                    with self.f.ledger.tx() as db:
                        meta=self.f.ledger.get(db,"meta",1); meta["standardRun"]["brainObservedTokens"]+=1
                        self.f.ledger.put(db,"meta",1,meta)
        self.f.callback=race
        with self.assertRaises(Refusal): self.collect()
        self.assertEqual(export.status(self.directory)["status"],"partial_export_unknown")
        with self.assertRaises(Refusal): self.collect()

    def test_export_destination_must_be_private_and_outside_shared_home_and_checkout(self):
        for directory in (self.home/"export",Path(self.f.cwd)/"export",self.f.ledger.root/"export"):
            with self.subTest(directory=directory), self.assertRaises(Refusal):
                export.export(self.f.registry,self.f.ledger,self.source_path,directory)
        public=self.f.root/"public-parent"; public.mkdir(mode=0o755)
        with self.assertRaises(Refusal): export.export(self.f.registry,self.f.ledger,self.source_path,public/"export")

    def test_directory_identity_swap_refuses_but_unrelated_file_creation_does_not(self):
        real=export.read_shared_rollout; calls=0
        def collect(*args):
            nonlocal calls
            calls+=1
            if calls==2: (self.home/"unrelated-sibling").write_text("Unrelated fixture state.")
            return real(*args)
        with patch.object(export,"read_shared_rollout",side_effect=collect): self.collect()
        self.assert_not_written()

    def test_retained_archive_or_manifest_alias_refuses_status_and_prepare(self):
        self.collect(); archive=self.directory/"history.jsonl"; archive.chmod(0o600); archive.write_text("changed")
        with self.assertRaises(Refusal): export.status(self.directory)
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.f.restored)

    def test_interrupted_persistence_does_not_overwrite_partial_export(self):
        real=export.write_record
        def interrupted(path,value):
            if path.name=="export.json": raise OSError("Fixture interrupted persistence")
            return real(path,value)
        with patch.object(export,"write_record",side_effect=interrupted), self.assertRaises(OSError): self.collect()
        self.assertEqual(export.status(self.directory)["status"],"partial_export_unknown")
        with self.assertRaises(Refusal): self.collect()

    def test_expiry_is_preserved_not_a_native_read_permission_clock(self):
        with patch.object(export.time,"time",return_value=99999999999): result=self.collect()
        self.assertFalse(result["boundary"]["expiryExtended"])
        self.assert_not_written()

    def test_cli_requires_explicit_registry_and_export_is_not_apply(self):
        from orchestrator import cli
        output=io.StringIO()
        with patch("sys.argv",["cli","--platform",str(self.f.registry.root),"--workspace",self.f.ledger.workspace_id,
                               "standard-public-brain-export",str(self.source_path),str(self.directory)]), \
             patch("orchestrator.workspaces.Registry",return_value=self.f.registry),contextlib.redirect_stdout(output):
            cli.main()
        self.assertEqual(json.loads(output.getvalue())["status"],"private_export_retained")
        self.assert_not_written()
        with patch("sys.argv",["cli","standard-public-brain-export","/missing","/missing"]), \
             contextlib.redirect_stderr(io.StringIO()),self.assertRaises((Refusal,SystemExit)):
            cli.main()

    def test_source_proxy_rejects_mutation_discovery_and_other_targets(self):
        # The instance mock above is for fixture I/O; inspect the real class.
        cls=self._real_proxy_class
        proxy=cls.__new__(cls); proxy.scope={"brainId":self.f.brain,"projectId":self.f.project_id}
        for method,params in (("thread/resume",{}),("turn/start",{}),("thread/list",{}),
                              ("thread/read",{"threadId":"foreign","includeTurns":True}),
                              ("project/read",{"projectId":"foreign"})):
            with self.subTest(method=method),self.assertRaises(Refusal): proxy._rpc(method,params)

    def test_source_directory_replacement_invalidates_export_even_with_same_file(self):
        self.collect(); sessions=self.home/"sessions"; moved=self.home/"retired-sessions"
        sessions.rename(moved); sessions.mkdir(mode=0o700)
        (moved/self.f.file.name).rename(self.f.file)
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.f.restored)

    def test_structurally_invalid_records_refuse_without_export_or_native_write(self):
        for rows in ([False],[{"type":"session_meta","payload":["not-metadata"]}],
                     [self.f.rows[0],{"type":"event_msg","payload":{"type":"thread_settings_applied","thread_settings":"opaque"}}]):
            self.f.file.write_text("\n".join(json.dumps(row) for row in rows)+"\n")
            with self.subTest(rows=rows),self.assertRaises(Refusal): self.collect()
        self.assertFalse(self.directory.exists()); self.assert_not_written()

    def test_original_notification_or_pending_control_remains_fenced(self):
        with self.f.ledger.tx() as db:
            play=self.f.ledger.get(db,"commands",self.f.fixture.fixture.command_id)
            play["notification"]["nativeThreadObservation"]["streamStatus"]="unconfirmed"
            self.f.ledger.put(db,"commands",play["id"],play)
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse(self.f.calls)

    def test_export_cannot_bypass_a_consumed_transfer_via_another_directory(self):
        self.collect(); preview=self.prepare(); spec=transfer.load_spec(self.f.root/"transfer/transfer.json")
        self.f.fail_at="project/restoreMetadata"
        with self.assertRaises(Refusal): transfer.apply(self.f.registry,self.f.ledger,spec,preview["reviewHash"])
        self.f.fail_at=None; before=copy.deepcopy(self.f.calls)
        with self.assertRaises(Refusal):
            transfer.prepare(self.f.registry,self.f.ledger,self.source_path,self.f.fixture.paths[0],
                             self.f.root/"another-transfer",source_export=self.manifest())
        self.assertEqual(before,self.f.calls)

    _real_proxy_class = export.SourceProxy


if __name__ == "__main__": unittest.main()
