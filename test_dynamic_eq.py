import pathlib
import shutil
import subprocess
import tempfile
import unittest

try:
    import numpy  # noqa: F401 - dependencia del analizador, no de la prueba
    from spectrum_analyzer import analyze_dynamic_eq_evidence
except ImportError:
    analyze_dynamic_eq_evidence = None


class DynamicEQAnalysisTests(unittest.TestCase):
    @unittest.skipUnless(analyze_dynamic_eq_evidence, "NumPy requerido para el analisis espectral")
    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg requerido")
    def test_analysis_detects_persistent_resonance_and_mid_dominance(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "resonance.wav"
            result = subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "aevalsrc=0.12*sin(2*PI*3200*t)+0.015*sin(2*PI*800*t)|"
                "0.12*sin(2*PI*3200*t)+0.015*sin(2*PI*1200*t):s=44100:d=1.2",
                "-c:a", "pcm_s16le", str(source),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = analyze_dynamic_eq_evidence(source, duration=1.0)
            self.assertGreater(evidence["mid_side_ratio"], 0.8)
            self.assertGreaterEqual(evidence["vocal_center_confidence"], 0.65)
            self.assertGreater(evidence["stereo_correlation"], 0.9)
            self.assertIn("transient_crest_db", evidence)
            self.assertIn("low_end_level_db", evidence)
            self.assertIn("harshness_excess_db", evidence)
            self.assertIn("dullness_deficit_db", evidence)
            candidates = evidence["resonance_candidates"]
            self.assertTrue(
                any(abs(item["frequency_hz"] - 3200.0) < 120.0 for item in candidates),
                candidates,
            )


if __name__ == "__main__":
    unittest.main()
