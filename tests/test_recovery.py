import unittest

from orchestrator.recovery import describe


def state(status="blocked", gaps=None, total=954236):
    gaps = ["invalid_token_record"] if gaps is None else gaps
    return {"standard": {"blockers": ["Measure exact run usage before another effect"],
        "measuredUsage": {"remainingMeasured": None if gaps else 0},
        "run": {"status": status, "phaseId": "bounded-guidance", "tasks": [],
            "usageHighWater": total, "limits": {"tokenBudget": 300000, "checkpointReserveTokens": 75000},
            "usageReport": {"records": [{"role": "brain"}], "tokens": {
                "total_tokens": total, "input_tokens": 952942,
                "cached_input_tokens": 778368, "output_tokens": 1294},
                "coverage": "gapped" if gaps else "observed_local", "gaps": gaps,
                "collectedAt": 12345}}}}


class RecoveryTest(unittest.TestCase):
    def test_gap_and_overrun_are_both_visible_without_fabricating_balance(self):
        result = describe(state())
        self.assertEqual(result["kind"], "usage_and_budget")
        self.assertIn("reviewed limit", result["explanation"])
        self.assertTrue(result["budgetBoundaryReached"])
        self.assertEqual(result["uncachedInput"], 174574)
        self.assertEqual(result["remainingMeasured"], None)
        self.assertEqual(result["registeredTasks"], 0)
        self.assertIn("could not be validated", result["gapLabels"][0])
        self.assertEqual(result["reasonLabels"], ["A fresh phase-scoped usage measurement is required."])

    def test_complete_overrun_and_unknown_gap_are_distinct(self):
        self.assertEqual(describe(state(gaps=[]))["kind"], "budget_boundary")
        unknown = state(gaps=["session_usage_unavailable:private-native-id"])
        self.assertNotIn("private-native-id", str(describe(unknown)))
        self.assertEqual(describe(unknown)["gapLabels"], ["Other incomplete local telemetry."])

    def test_no_report_is_not_zero_and_no_active_blocker_is_hidden(self):
        missing = state()
        missing["standard"]["run"]["usageReport"] = None
        missing["standard"]["run"]["usageHighWater"] = 0
        result = describe(missing)
        self.assertIsNone(result["observedTotal"])
        self.assertIsNone(result["remainingMeasured"])
        clean = state(status="running", gaps=[], total=10)
        clean["standard"]["blockers"] = []
        self.assertIsNone(describe(clean))
        replacement = state()
        replacement["mission"] = {"document": {"spec": {"phase": {"id": "new-phase"}}}}
        self.assertIsNone(describe(replacement))

    def test_regressed_report_keeps_known_high_water(self):
        current = state(gaps=["counter_reset_or_regression"], total=100)
        current["standard"]["run"]["usageHighWater"] = 400000
        result = describe(current)
        self.assertEqual(result["observedTotal"], 100)
        self.assertEqual(result["knownUsageLowerBound"], 400000)
        self.assertTrue(result["budgetBoundaryReached"])
        self.assertIsNone(result["remainingMeasured"])

    def test_paused_budget_stop_does_not_advertise_resume(self):
        paused = describe(state(status="paused", gaps=[]))
        self.assertIn("Do not Resume", paused["nextStep"])


if __name__ == "__main__":
    unittest.main()
