import unittest

from auto_master_intelligence import (
    AudioCharacteristics, DEFAULT_AI_FALLBACK_PRESET, adapt_preset_to_audio,
)
from ui.workers import _needs_severe_recalibration


BANDS = {
    "Subbass (20-60 Hz)": -24.0,
    "Bass (60-250 Hz)": -18.0,
    "Low-Mid (250-500 Hz)": -17.0,
    "Mid (500-2k Hz)": -16.0,
    "High-Mid (2k-6k Hz)": -18.0,
    "Air (6k-16k Hz)": -22.0,
}


class AiOnlyFallbackTests(unittest.TestCase):
    def test_no_tokens_always_selects_suno_classic(self):
        result = adapt_preset_to_audio(
            "Fuego (Trap, Reguetón, Hip-Hop)",
            AudioCharacteristics(BANDS, -30.0),
            ia_providers=[],
        )
        self.assertEqual(result["fallback_preset"], DEFAULT_AI_FALLBACK_PRESET)
        self.assertEqual(result["strategy_source"], "fallback_suno_classic")
        self.assertTrue(any("SUNO Clásico" in note for note in result["notes"]))
        ids = [action["function_id"] for action in result["audio_actions"]]
        self.assertIn("audio.autogain.headroom", ids)
        self.assertIn("audio.loudness.normalize", ids)
        self.assertEqual(ids[-1], "audio.limiter.true_peak")
        self.assertEqual(result["decision_trace"]["effective_order"], ids)
        self.assertTrue(result["decision_trace"]["catalog_fingerprint"].startswith("sha256:"))

    def test_loudness_deviation_seen_in_real_log_forces_recalibration(self):
        self.assertTrue(_needs_severe_recalibration(
            post_stats={"input_i": -14.83, "input_tp": -2.80},
            target_lufs=-15.50,
            true_peak=-2.20,
        ))


if __name__ == "__main__":
    unittest.main()
