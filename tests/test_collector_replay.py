"""Deterministic split-transaction races; disposable fixtures, no remote I/O."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event, get_ident
import unittest
from unittest.mock import patch

from orchestrator import github_evidence, local_preservation, source_observation
from orchestrator.core import Refusal
import test_github_evidence
import test_local_preservation
import test_source_observation


@contextmanager
def suspended_after_lookup(bridge, call):
    """Release the real lookup locks before allowing the competing writer in."""
    looked_up, resume = Event(), Event()
    delayed_thread = None
    original = bridge.locked

    @contextmanager
    def locked(*args, **kwargs):
        with original(*args, **kwargs) as values:
            yield values
        if get_ident() == delayed_thread and not kwargs.get("ownership_change") and not looked_up.is_set():
            looked_up.set()
            if not resume.wait(20):
                raise AssertionError("Timed out waiting to resume collector fixture")

    def delayed():
        nonlocal delayed_thread
        delayed_thread = get_ident()
        return call()

    with patch.object(bridge, "locked", locked), ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(delayed)
        try:
            if not looked_up.wait(20):
                if future.done(): future.result()  # Surface unexpected fixture errors.
                raise AssertionError("Collector did not finish its initial lookup")
            yield future, resume
        finally:
            resume.set()


class ReplayCases:
    """Exercise the same receipt boundary against each real collector."""

    def no_io(self):
        return patch.object(self.module, self.io_name, side_effect=AssertionError("Replay must not recollect"))

    def test_identical_receipt_appearing_between_transactions_replays(self):
        with suspended_after_lookup(self.bridge, lambda: self.collect(self.request)) as (future, resume):
            first = self.collect(self.request)
            before = self.state()
            with self.no_io() as io:
                resume.set()
                self.assertEqual(future.result(timeout=20), first)
                io.assert_not_called()
            self.assertEqual(self.state(), before)  # Includes original times and artifact/receipt counts.

    def test_receipt_appearing_then_pause_replays_without_new_effects(self):
        with suspended_after_lookup(self.bridge, lambda: self.collect(self.request)) as (future, resume):
            first = self.collect(self.request)
            self.pause()
            before = self.state()
            with self.no_io() as io:
                resume.set()
                self.assertEqual(future.result(timeout=20), first)
                io.assert_not_called()
            self.assertEqual(self.state(), before)

    def test_conflicting_receipt_appearing_between_transactions_refuses(self):
        changed = self.request | {"commit": "a" * 40}
        self.assertNotEqual(changed["commit"], self.request["commit"])
        with suspended_after_lookup(self.bridge, lambda: self.collect(changed)) as (future, resume):
            self.collect(self.request)
            before = self.state()
            with self.no_io() as io:
                resume.set()
                with self.assertRaisesRegex(Refusal, "different content"):
                    future.result(timeout=20)
                io.assert_not_called()
            self.assertEqual(self.state(), before)

    def test_unrelated_receipt_does_not_bypass_revision_check(self):
        with suspended_after_lookup(self.bridge, lambda: self.collect(self.request)) as (future, resume):
            self.collect(self.request | {"id": "unrelated-request"})
            before = self.state()
            with self.no_io() as io:
                resume.set()
                with self.assertRaisesRegex(Refusal, "Workspace changed"):
                    future.result(timeout=20)
                io.assert_not_called()
            self.assertEqual(self.state(), before)

    def test_receipt_appearing_with_missing_journal_refuses(self):
        with suspended_after_lookup(self.bridge, lambda: self.collect(self.request)) as (future, resume):
            first = self.collect(self.request)
            journal = first.get("observationHash") or first["preservationHash"]
            with self.ledger.tx() as db:
                db.execute("DELETE FROM snapshots WHERE id=?", (journal,))
            before = self.state()
            with self.no_io() as io:
                resume.set()
                with self.assertRaises(Refusal): future.result(timeout=20)
                io.assert_not_called()
            self.assertEqual(self.state(), before)

    def test_receipt_appearing_with_corrupt_artifact_refuses(self):
        with suspended_after_lookup(self.bridge, lambda: self.collect(self.request)) as (future, resume):
            first = self.collect(self.request)
            with self.ledger.tx() as db:
                db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"tampered", first["artifactId"]))
            before = self.state()
            with self.no_io() as io:
                resume.set()
                with self.assertRaisesRegex(Refusal, "artifact bytes"):
                    future.result(timeout=20)
                io.assert_not_called()
            self.assertEqual(self.state(), before)

    def test_pause_without_matching_receipt_still_refuses_new_collection(self):
        with suspended_after_lookup(self.bridge, lambda: self.collect(self.request)) as (future, resume):
            self.pause()
            before = self.state()
            with self.no_io() as io:
                resume.set()
                with self.assertRaisesRegex(Refusal, "paused"):
                    future.result(timeout=20)
                io.assert_not_called()
            self.assertEqual(self.state(), before)

    def test_maintenance_arriving_in_gap_still_fences_ownership_lock(self):
        with suspended_after_lookup(self.bridge, lambda: self.collect(self.request)) as (future, resume):
            first = self.collect(self.request)
            (self.ledger.root / "admission-fence.json").touch(mode=0o600)
            before = self.state()
            with self.no_io() as io:
                resume.set()
                with self.assertRaisesRegex(Refusal, "maintenance fence"):
                    future.result(timeout=20)
                # A new explicit call may read historical evidence without entering that lock.
                self.assertEqual(self.collect(self.request), first)
                io.assert_not_called()
            self.assertEqual(self.state(), before)


class GitHubReplayTest(ReplayCases, unittest.TestCase):
    def setUp(self):
        fixture = test_github_evidence.GitHubRetentionTest()
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        self.bridge, self.ledger = fixture.api.bridge, fixture.ledger
        self.collect, self.request, self.pause = fixture.observe, fixture.request(), fixture.pause
        self.state = lambda: (fixture.fx.logical(), fixture.store.snapshot())
        self.module, self.io_name = github_evidence, "inspect_github"


class SourceReplayTest(ReplayCases, unittest.TestCase):
    def setUp(self):
        fixture = test_source_observation.SourceRetentionTest()
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        self.bridge, self.ledger = fixture.api.bridge, fixture.ledger
        self.collect, self.request = fixture.observe, fixture.request()
        self.pause = lambda: fixture.fx.fx.fx.fx.fx.fx.command("pause")
        self.state = lambda: (fixture.fx.logical(), fixture.store.snapshot())
        self.module, self.io_name = source_observation, "inspect_source"


class PreservationReplayTest(ReplayCases, unittest.TestCase):
    def setUp(self):
        fixture = test_local_preservation.PreservationHandoffTest()
        self.addCleanup(fixture.doCleanups); fixture.setUp()
        self.bridge, self.ledger = fixture.fx.api.bridge, fixture.ledger
        _, self.request = fixture.prepare()
        self.collect, self.pause, self.state = fixture.collect, fixture.fx.pause, fixture.fx.logical
        self.module, self.io_name = local_preservation, "preserve_git"


if __name__ == "__main__":
    unittest.main()
