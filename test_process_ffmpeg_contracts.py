"""Pruebas de ejecución FFmpeg para todas las funciones del catálogo."""

import shutil
import subprocess
import unittest

from processes import AudioFunctionAction, AudioProcessContext, FilterLabelFactory, registry
from processes.catalog import function_registry


LOUDNESS_STATS = {
    "input_i": -21.0, "input_lra": 4.0, "input_tp": -12.0,
    "input_thresh": -31.0, "target_offset": 0.0,
}


class FFmpegFunctionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("ffmpeg"):
            raise unittest.SkipTest("FFmpeg no está instalado")
        cls.plugins = {plugin.plugin_id: plugin for plugin in registry}
        cls.context = AudioProcessContext(
            "contract-fixture", 48000, 2, duration=0.2,
            analysis={
                "noise_floor_db": -50.0, "clipping": True, "true_peak": -1.0,
                "impulsive_noise": True, "spectrum": {}, "band_rms": {},
                "band_peak": {}, "stereo_width": 1.0, "crest_factor": 10.0,
                "lufs": -21.0, "lra": 4.0, "sibilance": True,
                "sample_rate": 48000, "duration": 0.2,
                "loudness_stats": LOUDNESS_STATS,
            },
        )

    def representative_action(self, function_id):
        params = {}
        target = None
        if function_id == "audio.repair.trim_silence":
            params = {"start_threshold_db": -50.0, "start_duration_seconds": 0.01,
                      "end_threshold_db": -45.0, "end_duration_seconds": 0.01}
        elif function_id.startswith("audio.repair."):
            params = {"level": "Leve"}
        elif function_id == "audio.tone_eq.band":
            target, params = "low_mid", {"frequency_hz": 350.0, "gain_db": -1.0, "q": 1.2, "filter_type": "peaking"}
        elif function_id == "audio.dynamic_eq.resonance":
            target, params = "high_mid", {
                "frequency_hz": 3200.0, "q": 3.0, "threshold_db": -30.0,
                "max_reduction_db": 2.0, "ratio": 2.0, "attack_ms": 15.0,
                "release_ms": 180.0, "scope": "stereo", "filter_type": "bell",
            }
        elif function_id == "audio.dynamic_eq.motion":
            target, params = "air", {
                "frequency_hz": 9000.0, "q": 0.8, "threshold_db": -35.0,
                "gain_db": 0.5, "ratio": 1.5, "attack_ms": 80.0,
                "release_ms": 350.0, "scope": "stereo", "filter_type": "highshelf",
            }
        elif function_id == "audio.vocal.resonance_suppressor":
            params = {"frequency_hz": 3400.0, "q": 3.5, "threshold_db": -28.0,
                      "max_reduction_db": 1.5, "ratio": 2.0, "attack_ms": 18.0,
                      "release_ms": 180.0, "filter_type": "bell"}
        elif function_id == "audio.vocal.center_naturalizer":
            params = {"body_frequency_hz": 300.0, "body_gain_db": 0.5,
                      "harshness_frequency_hz": 3500.0, "harshness_reduction_db": 1.0,
                      "air_frequency_hz": 8500.0, "air_reduction_db": 0.5, "mix": 0.25}
        elif function_id == "audio.transient.dynamic_control":
            params = {"amount_db": -1.0, "threshold_db": -18.0, "attack_ms": 10.0, "release_ms": 120.0}
        elif function_id == "audio.stereo.correlation_guard":
            params = {"width": 0.9}
        elif function_id == "audio.low_end.dynamic_balance":
            params = {"frequency_hz": 100.0, "q": 0.7, "threshold_db": -28.0, "gain_db": -1.0,
                      "ratio": 1.5, "attack_ms": 60.0, "release_ms": 300.0, "filter_type": "lowshelf"}
        elif function_id == "audio.spectral.deharsh":
            params = {"frequency_hz": 3800.0, "q": 0.8, "threshold_db": -28.0, "max_reduction_db": 1.0,
                      "ratio": 1.5, "attack_ms": 30.0, "release_ms": 220.0, "filter_type": "bell"}
        elif function_id == "audio.spectral.dullness_recovery":
            params = {"frequency_hz": 8500.0, "q": 0.7, "threshold_db": -35.0, "max_boost_db": 0.5,
                      "ratio": 1.4, "attack_ms": 80.0, "release_ms": 400.0, "filter_type": "highshelf"}
        elif function_id.startswith("audio.multiband."):
            target = "mid"
            params = {
                "audio.multiband.eq": {"gain_db": -1.0},
                "audio.multiband.stereo_width": {"width": 1.1},
                "audio.multiband.compressor": {"threshold_db": -18.0, "ratio": 1.4, "attack_ms": 10.0, "release_ms": 80.0},
                "audio.multiband.limiter": {"ceiling_db": -3.0, "release_ms": 50.0},
                "audio.multiband.saturation": {"drive_db": 1.0, "mix": 0.2, "type": "Tape"},
            }[function_id]
        elif function_id == "audio.saturation.softclip":
            params = {"drive_db": 2.0, "mix": 0.25, "type": "Tape", "oversampling": 2}
        elif function_id == "audio.saturation.exciter":
            params = {"frequency_hz": 8000.0, "amount": 1.0, "mix": 0.25}
        elif function_id == "audio.saturation.hard_clip":
            params = {"ceiling_db": -1.5}
        elif function_id == "audio.deesser.sibilance_reduction":
            params = {"frequency_hz": 6000.0, "intensity": 0.7}
        elif function_id == "audio.glue.bus_compressor":
            params = {"threshold_db": -18.0, "ratio": 1.4, "attack_ms": 20.0, "release_ms": 120.0, "knee_db": 6.0, "makeup_db": -2.0}
        elif function_id == "audio.autogain.headroom":
            params = {"gain_db": -6.0}
        elif function_id in ("audio.autogain.interstage_limiter", "audio.autogain.final_peak"):
            params = {"ceiling_db": -3.0}
        elif function_id == "audio.loudness.normalize":
            params = {"target_lufs": -14.0, "true_peak_db": -1.0, "lra": 11.0, "dual_mono": False}
        elif function_id.startswith("audio.loudness.fade_"):
            params = {"duration_seconds": 0.05}
        elif function_id == "audio.limiter.true_peak":
            params = {"ceiling_db": -1.0, "release_ms": 100.0, "lookahead_ms": 5.0, "mode": "transparent", "oversampling": 4}
        return AudioFunctionAction(function_id, params=params, target=target)

    def test_every_catalog_function_executes_in_ffmpeg(self):
        for spec in function_registry.all():
            with self.subTest(function_id=spec.function_id):
                action = self.representative_action(spec.function_id)
                plugin = self.plugins[spec.plugin_id]
                chain, output = plugin.build_function(action, "0:a", self.context, FilterLabelFactory())
                self.assertTrue(chain)
                verified = "contract_verified"
                command = [
                    "ffmpeg", "-v", "info", "-f", "lavfi", "-i",
                    "aevalsrc=0.08*sin(2*PI*440*t)|0.08*sin(2*PI*660*t):s=48000:d=0.2",
                    "-filter_complex", f"{chain};[{output}]ashowinfo[{verified}]",
                    "-map", f"[{verified}]", "-f", "null", "-",
                ]
                result = subprocess.run(command, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("rate:48000", result.stderr)
                self.assertIn("channels:2", result.stderr)

    def test_oversampling_preserves_common_sample_rates(self):
        cases = (
            ("audio.saturation.softclip", "audio.saturation", {"drive_db": 2.0, "mix": 0.25, "oversampling": 2}),
            ("audio.limiter.true_peak", "audio.master_limiter", {"ceiling_db": -1.0, "oversampling": 4}),
        )
        for sample_rate in (44100, 48000, 88200, 96000, 192000):
            analysis = dict(self.context.analysis)
            analysis["sample_rate"] = sample_rate
            context = AudioProcessContext("rate-fixture", sample_rate, 2, 0.1, analysis)
            for function_id, plugin_id, params in cases:
                with self.subTest(function_id=function_id, sample_rate=sample_rate):
                    chain, output = self.plugins[plugin_id].build_function(
                        AudioFunctionAction(function_id, params=params), "0:a", context, FilterLabelFactory()
                    )
                    command = [
                        "ffmpeg", "-v", "info", "-f", "lavfi", "-i",
                        f"aevalsrc=0.05*sin(2*PI*440*t)|0.05*sin(2*PI*660*t):s={sample_rate}:d=0.1",
                        "-filter_complex", f"{chain};[{output}]ashowinfo[verified]",
                        "-map", "[verified]", "-f", "null", "-",
                    ]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f"rate:{sample_rate}", result.stderr)
                    self.assertIn("channels:2", result.stderr)

    def test_zero_stereo_width_uses_ffmpeg_minimum_and_executes(self):
        plugin = self.plugins["audio.multiband"]
        chain, output = plugin.build_function(
            AudioFunctionAction(
                "audio.multiband.stereo_width",
                target="sub_bass",
                params={"width": 0.0},
            ),
            "0:a",
            self.context,
            FilterLabelFactory(),
        )
        self.assertIn("slev=0.015625", chain)
        self.assertNotIn("slev=0.000000", chain)
        result = subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
            "aevalsrc=0.08*sin(2*PI*440*t)|0.08*sin(2*PI*660*t):s=48000:d=0.2",
            "-filter_complex", chain, "-map", f"[{output}]", "-f", "null", "-",
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dynamic_eq_mid_scope_recombines_stereo_and_executes(self):
        plugin = self.plugins["audio.dynamic_eq"]
        action = AudioFunctionAction(
            "audio.dynamic_eq.resonance", target="high_mid", operation="cut",
            evidence={"measured_excess_db": 2.0, "resonance_frequency_hz": 3200.0,
                      "mid_side_ratio": 0.8},
            params={
                "frequency_hz": 3200.0, "q": 4.0, "threshold_db": -32.0,
                "max_reduction_db": 1.5, "ratio": 2.0, "attack_ms": 12.0,
                "release_ms": 160.0, "scope": "mid", "filter_type": "bell",
            },
        )
        chain, output = plugin.build_function(
            action, "0:a", self.context, FilterLabelFactory()
        )
        self.assertIn("stereotools=mode=lr>ms", chain)
        self.assertIn("stereotools=mode=ms>lr", chain)
        result = subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
            "aevalsrc=0.08*sin(2*PI*3200*t)|0.05*sin(2*PI*1000*t):s=48000:d=0.2",
            "-filter_complex", chain, "-map", f"[{output}]", "-f", "null", "-",
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dynamic_motion_below_one_db_uses_parallel_mix(self):
        plugin = self.plugins["audio.dynamic_eq"]
        action = AudioFunctionAction(
            "audio.dynamic_eq.motion", target="air", operation="boost",
            evidence={"measured_deficit_db": 1.0},
            params={
                "frequency_hz": 9000.0, "q": 0.8, "threshold_db": -35.0,
                "gain_db": 0.4, "ratio": 1.5, "attack_ms": 80.0,
                "release_ms": 350.0, "scope": "stereo", "filter_type": "highshelf",
            },
        )
        chain, _ = plugin.build_function(action, "0:a", self.context, FilterLabelFactory())
        self.assertIn("range=1.000", chain)
        self.assertIn("weights=0.600000 0.400000", chain)

    def test_vocal_plugins_process_only_mid_and_recombine(self):
        plugin = self.plugins["audio.vocal"]
        for function_id in ("audio.vocal.resonance_suppressor", "audio.vocal.center_naturalizer"):
            with self.subTest(function_id=function_id):
                chain, output = plugin.build_function(
                    self.representative_action(function_id), "0:a", self.context, FilterLabelFactory())
                self.assertIn("stereotools=mode=lr>ms", chain)
                self.assertIn("stereotools=mode=ms>lr", chain)
                result = subprocess.run([
                    "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "aevalsrc=0.08*sin(2*PI*3400*t)|0.05*sin(2*PI*900*t):s=48000:d=0.2",
                    "-filter_complex", chain, "-map", f"[{output}]", "-f", "null", "-",
                ], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_complementary_positive_paths_execute(self):
        cases = (
            ("audio.transient", AudioFunctionAction("audio.transient.dynamic_control", operation="boost",
                params={"amount_db": 0.8, "threshold_db": -18.0, "attack_ms": 10.0, "release_ms": 120.0})),
            ("audio.stereo_guard", AudioFunctionAction("audio.stereo.correlation_guard", operation="expand",
                params={"width": 1.1})),
            ("audio.low_end", AudioFunctionAction("audio.low_end.dynamic_balance", operation="boost",
                params={"frequency_hz": 100.0, "q": 0.7, "threshold_db": -28.0, "gain_db": 0.6,
                        "ratio": 1.5, "attack_ms": 60.0, "release_ms": 300.0, "filter_type": "lowshelf"})),
        )
        for plugin_id, action in cases:
            with self.subTest(function_id=action.function_id):
                chain, output = self.plugins[plugin_id].build_function(
                    action, "0:a", self.context, FilterLabelFactory())
                result = subprocess.run([
                    "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "aevalsrc=0.08*sin(2*PI*100*t)|0.05*sin(2*PI*900*t):s=48000:d=0.2",
                    "-filter_complex", chain, "-map", f"[{output}]", "-f", "null", "-",
                ], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
