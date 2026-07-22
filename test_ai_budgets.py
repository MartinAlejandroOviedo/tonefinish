import unittest

from ia_mastering import validate_mastering_strategy
from processes.budgets import (
    GAIN_GOVERNOR_ID, OVERLAP_GOVERNOR_ID, TONAL_GOVERNOR_ID,
    evaluate_action_budgets,
    estimate_effective_band_boosts,
    HEADROOM_GOVERNOR_ID,
)
from processes.catalog import function_registry
from processes.contracts import AudioFunctionAction


def eq_action(gain_db, target, operation, evidence):
    return {
        "function_id": "audio.multiband.eq", "enabled": True,
        "operation": operation, "target": target, "params": {"gain_db": gain_db},
        "evidence": evidence, "reason": "balance espectral medido", "confidence": 0.9,
    }


class AiBudgetTests(unittest.TestCase):
    def validate(self, actions):
        return validate_mastering_strategy(
            {"audio_id": "budget.wav", "actions": actions},
            audio_id="budget.wav", target_lufs=-15.5, true_peak=-2.2,
            pre_stats={"input_lra": 8.0, "crest_factor": 11.0},
        )

    def test_valid_cut_and_boost_report_used_and_remaining_budget(self):
        result = self.validate([
            eq_action(-1.5, "high_mid", "cut", {"measured_excess_db": 2.1}),
            eq_action(0.75, "air", "boost", {"measured_deficit_db": 1.2}),
        ])
        report = result["decision_trace"]["budget_report"]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["totals"]["tonal_cut_db"], 1.5)
        self.assertEqual(report["totals"]["tonal_boost_db"], 0.75)
        self.assertEqual(report["remaining"]["tonal_boost_db"], 2.25)

    def test_individual_tonal_boost_over_limit_is_rejected(self):
        result = self.validate([
            eq_action(2.5, "air", "boost", {"measured_deficit_db": 3.0}),
        ])
        rejection = result["decision_trace"]["rejected_actions"][0]
        self.assertIn(TONAL_GOVERNOR_ID, rejection["error"])
        self.assertNotIn("audio.multiband.eq", result["decision_trace"]["effective_order"])

    def test_split_boost_cannot_exceed_accumulated_budget(self):
        result = self.validate([
            eq_action(1.5, "mid", "boost", {"measured_deficit_db": 2.0}),
            eq_action(1.5, "high_mid", "boost", {"measured_deficit_db": 2.0}),
            eq_action(0.5, "air", "boost", {"measured_deficit_db": 1.0}),
        ])
        self.assertEqual(
            [a["target"] for a in result["actions"] if a["function_id"] == "audio.multiband.eq"],
            ["mid", "high_mid"],
        )
        self.assertIn("acumulado", result["decision_trace"]["rejected_actions"][0]["error"])

    def test_cut_requires_measured_excess(self):
        result = self.validate([
            eq_action(-1.0, "high_mid", "cut", {"band_rms_db": -15.0}),
        ])
        self.assertIn("measured_excess_db", result["decision_trace"]["rejected_actions"][0]["error"])

    def test_overlapping_boosts_in_same_band_are_rejected(self):
        result = self.validate([
            eq_action(1.25, "air", "boost", {"measured_deficit_db": 2.0}),
            eq_action(1.0, "air", "boost", {"measured_deficit_db": 2.0}),
        ])
        self.assertEqual(
            len([a for a in result["actions"] if a["function_id"] == "audio.multiband.eq"]), 1
        )
        self.assertIn(OVERLAP_GOVERNOR_ID, result["decision_trace"]["rejected_actions"][0]["error"])

    def test_positive_output_gain_requires_explicit_compensation_evidence(self):
        raw = {
            "function_id": "audio.autogain.output_gain", "enabled": True,
            "operation": "boost", "params": {"gain_db": 1.0},
            "evidence": {"measured_deficit_db": 1.0},
            "reason": "compensación", "confidence": 0.9,
        }
        result = self.validate([raw])
        self.assertIn(GAIN_GOVERNOR_ID, result["decision_trace"]["rejected_actions"][0]["error"])
        self.assertIn("compensation_required_db", result["decision_trace"]["rejected_actions"][0]["error"])

    def test_budget_evaluator_never_changes_signed_values(self):
        actions = [
            function_registry.validate(AudioFunctionAction(
                "audio.multiband.eq", target="high_mid", params={"gain_db": -2.0},
                operation="cut", evidence={"measured_excess_db": 2.5},
            )),
            function_registry.validate(AudioFunctionAction(
                "audio.multiband.eq", target="air", params={"gain_db": 1.0},
                operation="boost", evidence={"measured_deficit_db": 1.4},
            )),
        ]
        report = evaluate_action_budgets(actions)
        self.assertEqual([a.params["gain_db"] for a in actions], [-2.0, 1.0])
        self.assertEqual([c["value_db"] for c in report["contributions"]], [-2.0, 1.0])

    def test_different_plugins_accumulate_effective_boost_in_same_band(self):
        actions = [
            AudioFunctionAction("audio.multiband.eq", target="mid",
                                params={"gain_db": 1.5}),
            AudioFunctionAction("audio.transient.dynamic_control",
                                params={"amount_db": 1.2, "threshold_db": -18.0,
                                        "attack_ms": 10.0, "release_ms": 120.0}),
        ]
        report = evaluate_action_budgets(actions)
        self.assertAlmostEqual(
            estimate_effective_band_boosts(actions)["effective_boost_by_band_db"]["mid"], 2.7)
        self.assertTrue(any(v["governor_id"] == HEADROOM_GOVERNOR_ID
                            for v in report["violations"]))

    def test_cuts_do_not_hide_dynamic_boost_headroom(self):
        actions = [
            AudioFunctionAction("audio.multiband.eq", target="air", params={"gain_db": -2.0}),
            AudioFunctionAction("audio.spectral.dullness_recovery",
                                params={"frequency_hz": 9000.0, "max_boost_db": 2.6,
                                        "threshold_db": -30.0, "ratio": 2.0,
                                        "attack_ms": 20.0, "release_ms": 150.0}),
        ]
        estimate = estimate_effective_band_boosts(actions)
        self.assertEqual(estimate["effective_boost_by_band_db"]["air"], 2.6)


if __name__ == "__main__":
    unittest.main()
