import json
import os
import unittest
from unittest.mock import patch

from orchestrator import turn_recovery as recovery, controller_recovery_file as credential, standard
from orchestrator.core import Refusal
import test_turn_recovery as fixture
from test_turn_recovery import Proxy, BRAIN


class ControllerCredentialTest(unittest.TestCase):
    tearDown = fixture.TurnRecoveryTest.tearDown
    preview = fixture.TurnRecoveryTest.preview
    confirm = fixture.TurnRecoveryTest.confirm
    reconcile = fixture.TurnRecoveryTest.reconcile

    def setUp(self):
        fixture.TurnRecoveryTest.setUp(self)
        Proxy.turn_status = "interrupted"
        self.controller = recovery.saved_state(self.ledger)["meta"]["controller"]
        self.path = standard.controller_file(self.ledger)
        self.raw = json.dumps({k: self.controller[k] for k in ("owner", "token")}).encode()
        self.path.write_bytes(self.raw)
        self.path.chmod(0o600)

    def test_review_pins_without_exposing_or_mutating_credential_and_recovery_preserves_bytes(self):
        doc = self.preview()
        self.assertNotIn("fixture-private", str(doc))
        self.assertEqual(self.path.read_bytes(), self.raw)
        self.assertEqual(self.confirm(doc)["status"], "controller_recovered")
        self.assertFalse(self.path.exists())
        entry = recovery.saved_state(self.ledger)["commands"][0]["notification"]["turnRecovery"]
        receipt = entry["controllerCredentialRetirement"]
        archive = self.ledger.root / receipt["archive"]
        self.assertEqual(archive.read_bytes(), self.raw)
        self.assertEqual(archive.stat().st_mode & 0o777, 0o600)
        self.assertEqual(archive.stat().st_nlink, 1)
        self.assertEqual(receipt["fingerprint"], doc["document"]["controllerCredential"])
        # The next designated-brain acquisition is no longer wedged by O_EXCL.
        standard.acquire_private(self.ledger, BRAIN + ":next-checkpoint")
        self.assertTrue(self.path.exists())
        self.assertEqual(archive.read_bytes(), self.raw)
        self.assertEqual(self.confirm(doc)["status"], "controller_recovered")
        self.assertEqual(recovery.saved_state(self.ledger)["meta"]["controller"]["owner"], BRAIN + ":next-checkpoint")

    def test_changed_bytes_or_inode_after_review_refuse_before_claim(self):
        doc = self.preview()
        self.path.write_bytes(self.raw + b" ")
        with self.assertRaises(Refusal): self.confirm(doc)
        self.assertNotIn("turnRecovery", recovery.saved_state(self.ledger)["commands"][0]["notification"])
        self.path.unlink()
        self.path.write_bytes(self.raw); self.path.chmod(0o600)
        with self.assertRaises(Refusal): self.confirm(doc)
        self.assertTrue(self.path.exists())

    def test_symlink_hardlink_public_or_foreign_credential_never_recovers(self):
        self.path.chmod(0o644)
        with self.assertRaises(Refusal): self.preview()
        self.path.chmod(0o600)
        sibling = self.ledger.root / "other-private.json"
        os.link(self.path, sibling)
        with self.assertRaises(Refusal): self.preview()
        sibling.unlink()
        self.path.rename(sibling); self.path.symlink_to(sibling)
        with self.assertRaises(OSError): self.preview()
        self.path.unlink(); sibling.rename(self.path)
        self.path.write_text(json.dumps({"owner": BRAIN + ":different", "token": "another"}))
        with self.assertRaises(Refusal): self.preview()
        self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])

    def test_unknown_terminals_do_not_retire_credential(self):
        Proxy.terminals = {}
        with self.assertRaises(Refusal): self.preview()
        self.assertEqual(self.path.read_bytes(), self.raw)
        self.assertEqual(list(self.ledger.root.glob("standard-controller-recovered-*.json")), [])

    def test_archive_collision_never_overwrites_or_clears_owner(self):
        doc = self.preview()
        archive = self.ledger.root / ("standard-controller-recovered-" + doc["document"]["controllerCredential"]["sha256"] + ".json")
        archive.write_bytes(self.raw); archive.chmod(0o600)  # Same bytes, wrong inode.
        self.assertEqual(self.confirm(doc)["status"], "awaiting_end")
        self.assertEqual(self.path.read_bytes(), self.raw)
        self.assertEqual(archive.read_bytes(), self.raw)
        self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])

    def test_crash_after_archive_link_reconciles_exact_pair_without_repeating_native_effect(self):
        doc = self.preview()
        with patch.object(credential, "_sync", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.confirm(doc)
        self.assertEqual(self.path.stat().st_nlink, 2)
        self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])
        self.assertEqual(self.reconcile()["status"], "controller_recovered")
        self.assertFalse(self.path.exists())
        self.assertEqual(Proxy.interrupts, 0)

    def test_crash_after_unlink_before_ledger_commit_reconciles_retained_exact_credential(self):
        doc = self.preview()
        from orchestrator import run_authority
        with patch.object(run_authority, "fence_in", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.confirm(doc)
        self.assertFalse(self.path.exists())
        self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])
        self.assertEqual(self.reconcile()["status"], "controller_recovered")
        self.assertEqual(Proxy.interrupts, 0)

    def test_unexpected_file_after_absent_review_cannot_be_retired(self):
        self.path.unlink()
        doc = self.preview()
        self.path.write_bytes(self.raw); self.path.chmod(0o600)
        with self.assertRaises(Refusal): self.confirm(doc)
        self.assertTrue(self.path.exists())
        self.assertNotIn("turnRecovery", recovery.saved_state(self.ledger)["commands"][0]["notification"])
