import unittest

from adaptive_master_shadow import build_adaptive_shadow_report


class AdaptiveShadowTests(unittest.TestCase):
    def test_effective_renderer_safe_profile_is_apply_ready(self):
        report = build_adaptive_shadow_report({"section_decisions": [{
            "section_id": 1, "label": "chorus", "confidence": 0.8,
            "actions": {"eq_db": {"air_db": -1.0}, "saturation_mix_mult": 0.91,
                        "stereo_motion_amount_mult": 0.90, "limiter_tp_margin_db": -0.08},
        }]})
        self.assertLessEqual(report["summary"]["global_risk"], 0.60)
        self.assertTrue(report["summary"]["apply_ready"])
        self.assertEqual(report["mode"], "apply_candidate")

    def test_section_saturation_multiplier_is_measured_without_crashing(self):
        report = build_adaptive_shadow_report({
            "section_decisions": [{
                "section_id": 1,
                "label": "chorus",
                "confidence": 0.8,
                "actions": {
                    "eq_db": {"air_db": -0.8},
                    "saturation_mix_mult": 0.91,
                    "stereo_motion_amount_mult": 0.95,
                    "limiter_tp_margin_db": -0.08,
                },
            }],
        })
        self.assertEqual(report["summary"]["sections"], 1)
        self.assertAlmostEqual(report["summary"]["sat_peak_dev"], 0.09)
        self.assertIn(report["mode"], {"shadow_only", "apply_candidate"})


if __name__ == "__main__":
    unittest.main()
