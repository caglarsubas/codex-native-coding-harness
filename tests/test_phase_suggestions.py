import unittest

from orchestrator.phase_suggestions import suggest_phase_limits, suggest_play_settings


def outline(count, *, repository="repo"):
    return [{"title": f"Task {index}", "repository": repository,
             "exactFiles": [f"src/task-{index}.py"]} for index in range(count)]


class PhaseSuggestionTest(unittest.TestCase):
    def test_task_count_tiers_and_included_reserve(self):
        for count, budget, total in ((1, 20_000_000, 3), (2, 20_000_000, 3),
                                     (3, 30_000_000, 6), (5, 30_000_000, 6),
                                     (6, 40_000_000, 10), (10, 40_000_000, 10)):
            with self.subTest(count=count):
                proposal = suggest_phase_limits(outline(count))
                self.assertEqual(proposal["basis"], "structured")
                self.assertTrue(proposal["proposalOnly"])
                self.assertEqual(proposal["limits"]["maxTasks"], total)
                self.assertEqual(proposal["limits"]["tokenBudget"], budget)
                self.assertEqual(proposal["limits"]["checkpointReserveTokens"], budget // 10)
                self.assertEqual(proposal["limits"]["maxParallelTasks"], min(3, count))
                self.assertEqual(proposal["play"]["durationHours"], 24)
                self.assertEqual(proposal["play"]["brainAllowanceTokens"], min(budget * 3 // 10, 12_000_000))

    def test_missing_outline_is_provisional_not_zero_task_authority(self):
        proposal = suggest_phase_limits(None)
        self.assertEqual(proposal["basis"], "provisional")
        self.assertEqual(proposal["plannedTasks"], 0)
        self.assertEqual(proposal["limits"]["tokenBudget"], 20_000_000)
        self.assertEqual(proposal["limits"]["maxParallelTasks"], 1)
        self.assertIn("provisional", " ".join(proposal["caveats"]))
        self.assertIsNone(proposal["usage"]["knownTokens"])
        self.assertIsNone(proposal["usage"]["remainingMeasured"])

    def test_more_than_ten_tasks_needs_owner_input(self):
        proposal = suggest_phase_limits(outline(11))
        self.assertEqual(proposal["basis"], "outside_suggestion_range")
        self.assertIsNone(proposal["limits"])
        self.assertIsNone(proposal["play"])
        self.assertIn("exceeds ten", " ".join(proposal["caveats"]))
        with self.assertRaises(ValueError):
            suggest_phase_limits(outline(21))

    def test_isolated_suggestion_calls_out_separate_integration_slot(self):
        proposal = suggest_phase_limits(outline(10), repository_mode="isolated_worktrees")
        self.assertEqual(proposal["limits"]["maxTasks"], 10)
        self.assertIn("11 total", " ".join(proposal["caveats"]))
        self.assertNotIn("integration task", " ".join(suggest_phase_limits(outline(10))["caveats"]))
        with self.assertRaises(ValueError):
            suggest_phase_limits(outline(1), repository_mode="unexpected")

    def test_parallelism_is_bounded_by_disjoint_exact_files(self):
        tasks = outline(4)
        tasks[1]["exactFiles"] = tasks[0]["exactFiles"]
        proposal = suggest_phase_limits(tasks)
        self.assertEqual(proposal["independentScopes"], 3)
        self.assertEqual(proposal["limits"]["maxParallelTasks"], 3)
        self.assertIn("overlap", " ".join(proposal["caveats"]))
        all_overlap = outline(3)
        for task in all_overlap:
            task["exactFiles"] = ["src/shared.py"]
        self.assertEqual(suggest_phase_limits(all_overlap)["limits"]["maxParallelTasks"], 1)

    def test_aliases_and_ambiguous_paths_never_raise_parallel_suggestion(self):
        tasks = outline(2)
        tasks[0]["exactFiles"] = ["SRC/CAFE\u0301.py"]
        tasks[1]["exactFiles"] = ["src/caf\u00e9.py"]
        self.assertEqual(suggest_phase_limits(tasks)["limits"]["maxParallelTasks"], 1)
        for unsafe in ("../escape.py", "/absolute.py", "src//a.py", "src/./a.py",
                       "src/*", "src/[a].py", "src\\a.py", "src/a.py/"):
            with self.subTest(unsafe=unsafe):
                tasks = outline(2)
                tasks[0]["exactFiles"] = [unsafe]
                proposal = suggest_phase_limits(tasks)
                self.assertEqual(proposal["limits"]["maxParallelTasks"], 1)
                self.assertIn("unambiguous", " ".join(proposal["caveats"]))

    def test_missing_or_duplicate_scope_is_incomplete(self):
        for broken in ({"title": "Task", "repository": "repo", "exactFiles": []},
                       {"title": "Task", "repository": "repo", "exactFiles": ["a.py", "a.py"]},
                       {"title": "Task", "repository": "repo"}):
            with self.subTest(broken=broken):
                result = suggest_phase_limits([broken, outline(1)[0]])
                self.assertEqual(result["limits"]["maxParallelTasks"], 1)
                self.assertEqual(result["basis"], "structured")

    def test_incomplete_usage_preserves_known_high_water_but_no_remaining(self):
        report = {"coverage": "gapped", "gaps": ["invalid_token_record"],
                  "tokens": {"total_tokens": 100}, "highWater": 140,
                  "remainingMeasured": 10, "collectedAt": 25.0}
        proposal = suggest_phase_limits(outline(1), report)
        self.assertEqual(proposal["usage"]["knownTokens"], 140)
        self.assertEqual(proposal["usage"]["coverage"], "incomplete")
        self.assertIsNone(proposal["usage"]["remainingMeasured"])
        self.assertEqual(proposal["usage"]["gaps"], ["invalid_token_record"])
        self.assertIn("unknown", " ".join(proposal["caveats"]))

    def test_complete_usage_is_historical_and_not_subtracted_from_new_phase(self):
        report = {"coverage": "observed_local", "gaps": [],
                  "tokens": {"total_tokens": 200}, "highWater": 240,
                  "remainingMeasured": 50, "collectedAt": 25.0}
        proposal = suggest_phase_limits(outline(1), report)
        self.assertEqual(proposal["usage"]["coverage"], "complete")
        self.assertEqual(proposal["usage"]["knownTokens"], 240)
        self.assertEqual(proposal["usage"]["remainingMeasured"], 50)
        self.assertEqual(proposal["limits"]["tokenBudget"], 20_000_000)
        self.assertIsNone(suggest_phase_limits(outline(1), {**report, "remainingMeasured": None})["usage"]["remainingMeasured"])

    def test_malformed_usage_cannot_fabricate_complete_coverage(self):
        report = {"coverage": "observed_local", "gaps": [], "tokens": {"total_tokens": True},
                  "remainingMeasured": 0, "collectedAt": float("nan")}
        projection = suggest_phase_limits(outline(1), report)["usage"]
        self.assertEqual(projection["coverage"], "incomplete")
        self.assertIsNone(projection["knownTokens"])
        self.assertIsNone(projection["remainingMeasured"])

    def test_play_settings_use_exact_reviewed_budget_not_tier_guess(self):
        self.assertEqual(suggest_play_settings(20_000_000),
                         {"durationHours": 24, "brainAllowanceTokens": 6_000_000})
        self.assertEqual(suggest_play_settings(80_000_000)["brainAllowanceTokens"], 12_000_000)
        self.assertEqual(suggest_play_settings(2)["brainAllowanceTokens"], 1)
        with self.assertRaises(ValueError):
            suggest_play_settings(0)
        self.assertEqual(suggest_play_settings(6_000_000, 4)["durationHours"], 4)
        for invalid in (0, 25, True, "4", 4.0):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                suggest_play_settings(6_000_000, invalid)


if __name__ == "__main__":
    unittest.main()
