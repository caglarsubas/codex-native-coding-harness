import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from orchestrator.observations import roadmap_observation, setup, config
from orchestrator.roadmaps import roadmap_content, checklist_scope


SOURCE = """# Project
## Current direction
Alpha2 ONGOING. W01 ONGOING_DESIGN. No acceptance claim.
- [ ] Resolve gate
## Retained checkpoints
## Current older direction
- [x] Old source milestone
| Phase | Status |
|---|---|
| Alpha2 | OLD_DONE_SOURCE |
"""
SPEC = {"repository": "fixture", "path": "docs/plan.md", "currentSectionPrefixes": ["Current "],
        "historyBoundary": "Retained checkpoints"}


class RoadmapTest(unittest.TestCase):
    def test_current_narrative_does_not_promote_first_historical_table(self):
        result = roadmap_content(SOURCE, SPEC)
        self.assertEqual(len(result["highlights"]), 1)
        self.assertIn("ONGOING_DESIGN", result["highlights"][0]["text"])
        self.assertEqual(result["tables"][0]["scope"], "historical")
        self.assertEqual(checklist_scope({"line": 4}, result), "current")
        self.assertEqual(checklist_scope({"line": 7}, result), "historical")

    def test_missing_boundary_does_not_guess_current(self):
        result = roadmap_content(SOURCE, {**SPEC, "historyBoundary": "Absent"})
        self.assertEqual(result["highlights"], [])
        self.assertEqual(result["tables"][0]["scope"], "document")
        self.assertTrue(result["issues"])

    def test_new_gate_matches_prefix_only_before_history(self):
        result = roadmap_content(SOURCE.replace("Current direction", "Current successor gate"), SPEC)
        self.assertEqual(result["highlights"][0]["heading"], "Current successor gate")

    def test_explicit_current_table_and_unclassified_supporting_table(self):
        text = "## Current position\n| Gate | State |\n|---|---|\n| G04 | OPEN |\n## Research\n| Provider | Owner |\n|---|---|\n| Candidate | R01 |"
        result = roadmap_content(text, {"currentSectionPrefixes": ["Current "]})
        self.assertEqual([t["scope"] for t in result["tables"]], ["current", "document"])
        self.assertEqual(result["tables"][0]["rows"], [["G04", "OPEN"]])

    def test_code_fences_do_not_create_headings_or_tables(self):
        text = "````md\n```\n## Current false\n| Gate | Status |\n|---|---|\n| Wrong | DONE |\n````\n## Current real\nWAITING"
        result = roadmap_content(text, {"currentSectionPrefixes": ["Current "]})
        self.assertEqual(result["tables"], [])
        self.assertEqual([h["heading"] for h in result["highlights"]], ["Current real"])

    def test_limits_and_unsupported_table_rows_are_explicit(self):
        text = "## Current\n" + ("| Item | State |\n|---|---|\n" + "| item | OPEN |\n" * 110 + "| broken |\n\n") * 35
        result = roadmap_content(text, {"currentSectionPrefixes": ["Current"]})
        self.assertEqual(len(result["tables"]), 32)
        self.assertEqual(result["omittedTables"], 3)
        self.assertEqual(result["tables"][0]["omittedRows"], 11)
        self.assertTrue(result["highlights"][0]["truncated"])

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        setup(self.db)
        self.repos = [{"id": "fixture", "path": "/not-read", "ref": "origin/main"}]

    def tearDown(self):
        self.db.close()

    def test_git_snapshot_preserves_versions_and_literal_states(self):
        with patch("orchestrator.observations.head", return_value="a" * 40), patch("orchestrator.observations.blob", return_value=SOURCE.encode()):
            first = roadmap_observation(self.db, SPEC, self.repos)
            second = roadmap_observation(self.db, SPEC, self.repos)
        self.assertEqual(first["documentId"], second["documentId"])
        self.assertEqual(first["documentVersion"], 1)
        self.assertEqual(first["sourceKind"], "published")
        self.assertEqual(first["items"][1]["scope"], "historical")
        with patch("orchestrator.observations.head", return_value="b" * 40), patch("orchestrator.observations.blob", return_value=(SOURCE + "\nnew text").encode()):
            third = roadmap_observation(self.db, SPEC, self.repos)
        self.assertEqual(third["documentVersion"], 2)
        self.assertEqual(self.db.execute("select count(*) from artifact_versions").fetchone()[0], 2)

    def test_private_proposal_is_separate_and_bounded_by_repository_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            path = root / "proposal.md"
            path.write_text("# Proposal\n- [x] Draft written\nNo publication.")
            spec = {"repository": "fixture", "path": str(path)}
            roots = [{"repository": "fixture", "path": str(root)}]
            with patch("orchestrator.observations.head", side_effect=AssertionError("No Git for drafts")):
                record = roadmap_observation(self.db, spec, self.repos, roots, draft=True)
            self.assertEqual(record["sourceKind"], "proposal")
            self.assertIsNone(record["commit"])
            self.assertEqual(record["status"], "observed")
            wrong = [{"repository": "other", "path": str(root)}]
            self.assertEqual(roadmap_observation(self.db, spec, self.repos, wrong, draft=True)["status"], "unavailable")
            link = root / "link.md"
            link.symlink_to(path)
            self.assertEqual(roadmap_observation(self.db, {**spec, "path": str(link)}, self.repos, roots, draft=True)["status"], "unavailable")

    def test_invalid_mapping_fails_without_source_read(self):
        with patch("orchestrator.observations.head", side_effect=AssertionError("No read")):
            for changes in ({"currentSectionPrefixes": "Current"}, {"path": "../secret"}, {"historyBoundary": ""}, {"command": "ignored"}):
                self.assertEqual(roadmap_observation(self.db, {**SPEC, **changes}, self.repos)["status"], "unavailable")

    def test_empty_narrative_has_no_fake_completion(self):
        result = roadmap_content("# Plan\nImplementation incomplete.", {})
        self.assertEqual(result["tables"], [])
        self.assertEqual(result["highlights"], [])

    def test_config_accepts_explicit_drafts_and_limits_source_count(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = type("Ledger", (), {"root": Path(temp)})()
            path = ledger.root / "observations.json"
            path.write_text(json.dumps({"roadmapDrafts": [{"repository": "fixture", "path": "/private/proposal.md"}]}))
            self.assertEqual(len(config(ledger)["roadmapDrafts"]), 1)
            path.write_text(json.dumps({"roadmaps": [{}] * 33}))
            with self.assertRaises(ValueError):
                config(ledger)
