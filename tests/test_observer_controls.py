import contextlib
import copy
import json
import sqlite3
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import observer_controls as controls, native_evidence as evidence
from orchestrator.core import Refusal, canonical
from orchestrator.workspaces import fingerprint
import test_dispatch_admission
import test_native_evidence


class ObserverControlsTest(test_native_evidence.EndpointFixture, unittest.TestCase):
    def setUp(self):
        self.endpoint_setup()
        self.fx = test_dispatch_admission.DispatchAdmissionTest(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.ledger, self.registry, self.store = self.fx.ledger, self.fx.registry, self.fx.store
        self.fx.meta(paused=True); self.aid = self.fx.binding["id"]
        self.api = controls.ObserverControls(); self.session = "observer-owner-fixture"

    def state(self): return controls.inspect(self.registry, self.ledger, "a")
    def logical(self):
        out = []
        for path in (self.registry.db, self.ledger.db, self.store.db):
            with controls.views.readonly(path) as db: out.append(fingerprint(db))
        return out
    def request(self, op="review", **fields):
        r = self.state()
        return {"operation": op, "expectedRevision": r["workspaceRevision"], "contextHash": r["contextHash"],
            **({"allocationId": self.aid, **{k: self.endpoint[k] for k in ("executable", "socket", "serverIdentityHash")}} if op == "review" else
               {"endpointHash": r["endpoint"]["endpointHash"]}), **fields}
    def preview(self, op="review", **fields): return self.api.preview(self.registry, self.ledger, "a", self.request(op, **fields), self.session)
    def confirm(self, p, **fields): return self.api.confirm(self.registry, self.ledger, "a", {"proposal":p,"confirmed":True,**fields}, self.session)

    def test_inspect_preview_and_confirmation_never_spawn_or_connect(self):
        before = self.logical()
        with patch("subprocess.Popen", side_effect=AssertionError("No process")), patch.object(evidence, "ReadProxy", side_effect=AssertionError("No connection")):
            r = self.state(); p = self.preview(); self.assertEqual(before, self.logical())
            self.assertTrue(r["canReview"]); self.confirm(p)
        self.assertEqual(before[0], self.logical()[0]); self.assertEqual(before[2], self.logical()[2])
        self.assertFalse((self.root / "requests.jsonl").exists())

    def test_review_revoke_and_old_retry_never_restore_access(self):
        before = self.ledger.snapshot(); p = self.preview(); saved = self.confirm(p)
        self.assertFalse(saved["nativeCallMade"]); self.assertFalse(saved["executionAuthorized"])
        r = self.preview("revoke"); self.confirm(r); before_retry = self.logical()
        with patch("orchestrator.observer_controls.time.time", return_value=time.time()+301):
            self.assertTrue(self.confirm(p)["replayed"]); self.assertTrue(self.confirm(r)["replayed"])
        self.assertEqual(before_retry, self.logical()); self.assertTrue(self.state()["endpoint"]["revoked"])
        for key in ("workers", "commands", "queue"): self.assertEqual(before[key], self.ledger.snapshot()[key])
        self.assertEqual(before["meta"]["paused"], self.ledger.snapshot()["meta"]["paused"])

    def test_browser_number_roundtrip_preserves_exact_socket_identity(self):
        preview = self.preview()
        identity = preview["document"]["request"]["endpoint"]["socketIdentity"]
        self.assertTrue(all(isinstance(v, str) for v in identity.values()))
        self.assertGreater(int(identity["changedNs"]), 2**53)
        # Model JSON.parse/JSON.stringify's IEEE-754 integer conversion.
        returned = json.loads(json.dumps(preview), parse_int=lambda v: int(float(v)))
        self.assertEqual(returned, preview)
        self.confirm(returned)
        self.assertEqual(self.state()["endpoint"]["endpoint"]["socketIdentity"], self.endpoint["socketIdentity"])

    def test_signature_session_confirmation_and_restart_are_bound(self):
        p = self.preview(); changed = copy.deepcopy(p); changed["document"]["request"]["endpoint"]["sha256"] = "b"*64
        for body in ({"proposal":changed,"confirmed":True},{"proposal":p,"confirmed":False},{"proposal":p,"confirmed":1},{"proposal":p,"confirmed":True,"execute":True}):
            with self.assertRaises(Refusal): self.api.confirm(self.registry, self.ledger, "a", body, self.session)
        with self.assertRaises(Refusal): self.api.confirm(self.registry, self.ledger, "a", {"proposal":p,"confirmed":True}, "other")
        with self.assertRaises(Refusal): controls.ObserverControls().confirm(self.registry, self.ledger, "a", {"proposal":p,"confirmed":True}, self.session)

    def test_expired_preview_and_pause_drift_refuse(self):
        p = self.preview()
        with patch("orchestrator.observer_controls.time.time", return_value=time.time()+301), self.assertRaisesRegex(Refusal,"expired"): self.confirm(p)
        self.fx.meta(paused=False)
        with self.assertRaises(Refusal): self.confirm(p)
        with patch.object(controls, "inspect_endpoint", side_effect=AssertionError("No file access")), self.assertRaises(Refusal): self.preview()

    def test_changed_executable_refuses_new_review_but_not_revocation(self):
        self.confirm(self.preview()); p = self.preview()
        self.binary.write_text("changed fixture executable"); self.binary.chmod(0o700)
        with self.assertRaises(Refusal): self.confirm(p)
        self.confirm(self.preview("revoke")); self.assertTrue(self.state()["endpoint"]["revoked"])

    def test_missing_socket_and_shared_store_do_not_prevent_revocation(self):
        self.confirm(self.preview()); self.sock.close(); (self.root / "observer.sock").unlink()
        moved = self.store.db.with_name("saved-admission.sqlite3"); self.store.db.rename(moved)
        try:
            r = self.state(); self.assertTrue(r["canRevoke"]); self.assertFalse(r["canReview"])
            self.confirm(self.preview("revoke")); self.assertFalse(self.store.db.exists())
        finally: moved.rename(self.store.db)

    def test_missing_file_errors_are_sanitized(self):
        with self.assertRaises(Refusal) as error: self.preview(executable=str(self.root / "PRIVATE-MISSING"))
        self.assertNotIn("PRIVATE-MISSING", str(error.exception)); self.assertNotIn(str(self.root), str(error.exception))

    def test_symlink_unsafe_socket_and_noncanonical_paths_refuse(self):
        link = self.root / "linked"; link.symlink_to(self.binary)
        for fields in ({"executable":str(link)},{"socket":"http://127.0.0.1:1"},{"executable":"relative"},{"serverIdentityHash":"not-a-hash"}):
            with self.subTest(fields=fields), self.assertRaises(Refusal): self.preview(**fields)
        (self.root / "observer.sock").chmod(0o666)
        with self.assertRaises(Refusal): self.preview()

    def test_harness_closed_and_foreign_allocations_refuse_before_path_access(self):
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "a"); repo["policyProfile"] = "harness"; self.ledger.put(db,"repos","a",repo)
        with patch.object(controls,"inspect_endpoint",side_effect=AssertionError("No endpoint access")), self.assertRaises(Refusal): self.preview()
        self.assertFalse(self.state()["canReview"])
        with self.ledger.tx() as db:
            repo["policyProfile"] = "standard"; self.ledger.put(db,"repos","a",repo)
        self.assertNotEqual(self.aid, "foreign")
        with self.assertRaises(Refusal): self.preview(allocationId="foreign")
        with self.store.tx() as db:
            a = self.store.get(db,"allocations",self.aid); a["closed"] = True; self.store.put(db,"allocations",self.aid,a)
        with self.assertRaises(Refusal): self.preview()

    def test_allocation_change_and_store_replacement_refuse(self):
        p = self.preview()
        with self.store.tx() as db:
            a = self.store.get(db,"allocations",self.aid); a["closed"] = True; self.store.put(db,"allocations",self.aid,a)
        with self.assertRaises(Refusal): self.confirm(p)
        with patch.object(controls, "identities", return_value={"registry":"changed","ledger":"changed"}), self.assertRaises(Refusal): self.confirm(p)

    def test_shared_identity_replacement_without_local_revision_refuses(self):
        p=self.preview(); original=controls.views.file_identity
        def identity(path): return (123,456) if path==self.store.db else original(path)
        with patch.object(controls.views,"file_identity",side_effect=identity), self.assertRaisesRegex(Refusal,"Shared store identity"):
            self.confirm(p)

    def test_socket_permission_replacement_invalidates_preview(self):
        p=self.preview(); (self.root / "observer.sock").chmod(0o640)
        with self.assertRaisesRegex(Refusal,"endpoint changed"): self.confirm(p)

    def test_uninitialized_shared_store_is_not_created_on_inspection(self):
        moved=self.store.db.with_name("saved-admission.sqlite3"); self.store.db.rename(moved)
        try:
            r=self.state(); self.assertFalse(r["canReview"]); self.assertEqual(r["sharedStatus"],"unavailable")
            self.assertFalse(self.store.db.exists())
        finally: moved.rename(self.store.db)

    def test_history_pointer_and_revocation_markers_fail_closed(self):
        self.confirm(self.preview())
        with self.ledger.tx() as db:
            meta=self.ledger.get(db,"meta",1); del meta["nativeEvidenceEndpointRevoked"]; self.ledger.put(db,"meta",1,meta)
        self.assertEqual(self.state()["status"],"unavailable"); self.assertFalse(self.state()["canRevoke"])
        with self.assertRaises(Refusal): self.preview()

    def test_history_bounds_precede_document_decoding(self):
        with self.ledger.tx() as db:
            for i in range(1001): db.execute("INSERT INTO snapshots VALUES(?,?,?)", (str(i), controls.KIND, "{}"))
        with patch.object(controls.runs,"document",side_effect=AssertionError("Bound first")):
            self.assertEqual(self.state()["status"],"unavailable")

    def test_concurrent_confirm_and_rollback_are_atomic(self):
        p = self.preview(); before=self.logical()
        with patch.object(self.ledger,"event",side_effect=RuntimeError("rollback")), self.assertRaises(RuntimeError): self.confirm(p)
        self.assertEqual(before,self.logical())
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(lambda _: self.confirm(p),range(2)))
        self.assertEqual(sum(not r["replayed"] for r in results),1); self.assertEqual(len(self.state()["history"]),1)

    def test_review_revoke_race_does_not_restore_permission(self):
        self.confirm(self.preview()); a,b=self.preview(),self.preview("revoke")
        def confirm(p):
            try: return self.confirm(p)
            except Refusal: return None
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(confirm,(a,b)))
        self.assertEqual(sum(r is not None for r in results),1)

    def test_allocation_lock_remains_held_through_local_receipt_commit(self):
        p = self.preview(); original=evidence.review_endpoint_in
        def check_lock(*args,**kwargs):
            with contextlib.closing(sqlite3.connect(self.store.db,timeout=.01)) as db:
                with self.assertRaises(sqlite3.OperationalError): db.execute("BEGIN IMMEDIATE")
            return original(*args,**kwargs)
        with patch.object(evidence,"review_endpoint_in",side_effect=check_lock): self.confirm(p)

    def test_saved_reports_remain_historical_and_privacy_bounded(self):
        fx=test_native_evidence.CollectionTest(); fx.setUp(); self.addCleanup(fx.doCleanups); fx.collect()
        r=controls.inspect(fx.bridge.registry,fx.ledger,"a"); report=r["reports"][0]
        self.assertFalse(report["completeEvidence"]); self.assertFalse(report["effectContextChecked"])
        for private in ("worker-fixture","brain-a","fixture-model","SECRET","configuredSettings"):
            self.assertNotIn(private,canonical(report))
        with patch("orchestrator.observer_controls.time.time",return_value=time.time()+61):
            again=controls.inspect(fx.bridge.registry,fx.ledger,"a")["reports"][0]
        self.assertTrue(again["stale"]); self.assertEqual(report["finishedAt"],again["finishedAt"])

    def test_cached_summary_omits_paths_ids_and_endpoint_material(self):
        self.confirm(self.preview()); r=self.state(); s=controls.summary(r,r["workspaceRevision"]+1)
        self.assertTrue(s["workspaceChanged"]); self.assertFalse(s["completeEvidence"])
        for private in (str(self.root),self.aid,"serverIdentityHash","socket","executable","endpointHash"):
            self.assertNotIn(private,canonical(s))

    def test_corrupt_report_does_not_prevent_endpoint_revocation(self):
        self.confirm(self.preview())
        with self.ledger.tx() as db: db.execute("INSERT INTO snapshots VALUES(?,?,?)",("bad-report",evidence.KIND,"{}"))
        r=self.state(); self.assertEqual(r["reportsStatus"],"unavailable"); self.assertTrue(r["canRevoke"])
        self.confirm(self.preview("revoke"))


if __name__ == "__main__": unittest.main()
