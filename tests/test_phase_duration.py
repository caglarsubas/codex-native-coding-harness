"""One reviewed duration, with byte-compatible historical missions."""
import copy
import contextlib
import unittest

from orchestrator import missions, standard
from orchestrator.assistant_journey import catalog
from orchestrator.core import Refusal
import test_assistant_journey
import test_standard
from test_missions import request, specification


class PhaseDurationTest(unittest.TestCase):
    def setUp(self):
        self.f = test_standard.StandardTest()
        self.f.setUp()
        self.ledger = self.f.ledger

    def tearDown(self):
        self.f.tearDown()

    def review_duration(self, hours):
        spec = specification(mode="phase_delegated")
        spec["phase"]["durationHours"] = hours
        current = missions.change(self.ledger, request(spec=spec,
            expectedRevision=missions.read(self.ledger)["revision"]))["current"]
        return missions.change(self.ledger, request("review", current["revision"],
            documentHash=current["documentHash"], confirmed=True))["current"]

    def preview(self, hours):
        return self.f.controls.preview(self.ledger, {"operation": "play",
            "contextHash": standard.read(self.ledger)["contextHash"],
            "brainAllowance": 10000, "durationHours": hours}, "session")

    def test_structured_duration_is_optional_strict_and_hash_bound(self):
        before = missions.read(self.ledger)["document"]
        self.assertNotIn("durationHours", before["spec"]["phase"])
        for invalid in (True, False, 0, 25, "4", 4.0, None):
            with self.subTest(invalid=invalid), self.assertRaises(Refusal):
                self.review_duration(invalid)
        for hours in (1, 4, 24):
            current = self.review_duration(hours)
            self.assertEqual(current["document"]["spec"]["phase"]["durationHours"], hours)
        self.assertEqual(self.ledger.document(missions.read(self.ledger)["document"]["previousHash"])["spec"]["phase"]["durationHours"], 4)
        # Reading an old immutable version never backfills a duration.
        self.assertNotIn("durationHours", before["spec"]["phase"])

    def test_play_preview_and_confirmation_both_enforce_reviewed_duration(self):
        self.review_duration(4)
        with contextlib.closing(self.ledger.connect()) as db:
            before = list(db.iterdump())
        for hours in (1, 8, 24):
            with self.subTest(hours=hours), self.assertRaisesRegex(Refusal, "match.*reviewed phase duration"):
                self.preview(hours)
        with contextlib.closing(self.ledger.connect()) as db:
            self.assertEqual(before, list(db.iterdump()))
        p = self.preview(4)
        # Even a trusted adapter that accidentally signs the wrong hours cannot
        # bypass the transaction's independent mission check.
        bad = copy.deepcopy(p)
        bad["preview"]["durationHours"] = 24
        bad["signature"] = self.f.controls.sign(bad["preview"])
        with self.assertRaisesRegex(Refusal, "match.*reviewed phase duration"):
            self.f.controls.confirm(self.f.registry, self.ledger, {**bad, "confirmed": True}, "session")
        self.assertIsNone(standard.read(self.ledger)["run"])
        self.f.controls.confirm(self.f.registry, self.ledger, {**p, "confirmed": True}, "session")
        run = standard.read(self.ledger)["run"]
        self.assertEqual(run["expiresAt"], run["startedAt"] + 4 * 3600)
        self.assertEqual(run["ownerReceipt"]["durationHours"], 4)

    def test_duration_checkpoint_blocks_resume_and_new_effects_before_play_expiry(self):
        self.f.control()
        self.f.call("receive")
        self.f.call("checkpoint", outcome="paused", summary="Reviewed narrative duration reached",
                    brainObservedTokens=None, reasonCodes=["duration"])
        before = standard.read(self.ledger)["run"]
        self.assertIn("Recorded duration stop", " ".join(standard.read(self.ledger)["blockers"]))
        with self.assertRaises(Refusal):
            self.f.control("resume")
        with self.assertRaises(Refusal):
            self.f.claim()
        self.assertEqual(before, standard.read(self.ledger)["run"])

    def test_structured_window_drift_fences_continuation_without_changing_usage(self):
        self.review_duration(8)
        self.f.control()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"]["expiresAt"] += 3600
            self.ledger.put(db, "meta", 1, meta)
        before = standard.read(self.ledger)["run"]
        self.assertIn("differs from the reviewed", " ".join(standard.read(self.ledger)["blockers"]))
        with self.assertRaises(Refusal):
            self.f.claim()
        self.assertEqual(before, standard.read(self.ledger)["run"])

    def test_legacy_narrative_is_not_parsed_or_rewritten_as_authority(self):
        spec = specification(mode="phase_delegated")
        spec["phase"]["stopConditions"] = ["Stop after four hours"]
        m = missions.change(self.ledger, request(spec=spec,
            expectedRevision=missions.read(self.ledger)["revision"]))["current"]
        missions.change(self.ledger, request("review", m["revision"],
            documentHash=m["documentHash"], confirmed=True))
        self.f.control()
        self.assertEqual(standard.read(self.ledger)["run"]["ownerReceipt"]["durationHours"], 8)
        self.assertNotIn("durationHours", missions.read(self.ledger)["document"]["spec"]["phase"])


class JourneyDurationTest(unittest.TestCase):
    def test_chat_preview_uses_reviewed_duration_not_default_and_rejects_edit(self):
        f = test_assistant_journey.AssistantJourneyTest()
        f.setUp()
        try:
            spec = specification(mode="phase_delegated")
            spec["phase"]["durationHours"] = 4
            m = missions.change(f.ledger, request(spec=spec,
                expectedRevision=missions.read(f.ledger)["revision"]))["current"]
            missions.change(f.ledger, request("review", m["revision"],
                documentHash=m["documentHash"], confirmed=True))
            p = f.prepare("phase_play")
            self.assertEqual(p["document"]["request"]["preview"]["durationHours"], 4)
            self.assertTrue(p["document"]["preview"]["runSettings"]["durationBoundToMission"])
            state = f.snapshot()
            with self.assertRaises(Refusal):
                f.proposals.prepare(catalog(state)["phase_play"], state, f.session,
                    play_settings={"durationHours": 24, "brainAllowance": 10000})
            self.assertIsNone(standard.read(f.ledger)["run"])
        finally:
            f.tearDown()
