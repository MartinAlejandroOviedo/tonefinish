"""Pruebas del orquestador único y la migración de configuración histórica."""

import pathlib
import subprocess
import tempfile
import unittest

from audio_processing import build_preprocess_chain, normalize_audio
from processes.contracts import AudioFunctionAction, AudioProcessContext
from processes.orchestrator import (
    migrate_legacy_preprocess_config, migrate_legacy_registry_state, orchestrator,
)


BANDS = {
    "Subbass (20-60 Hz)": -24.0, "Bass (60-250 Hz)": -18.0,
    "Low-Mid (250-500 Hz)": -20.0, "Mid (500-2k Hz)": -18.0,
    "High-Mid (2k-6k Hz)": -22.0, "Air (6k-16k Hz)": -26.0,
}


class AudioProcessOrchestratorTests(unittest.TestCase):
    def test_orchestrator_applies_actions_in_requested_order(self):
        actions = [
            AudioFunctionAction("audio.autogain.headroom", params={"gain_db": -6.0}),
            AudioFunctionAction("audio.tone_eq.band", target="mid", params={
                "frequency_hz": 1000.0, "gain_db": -1.0, "q": 1.0, "filter_type": "peaking",
            }),
            AudioFunctionAction("audio.autogain.final_peak", params={"ceiling_db": -3.0}),
        ]
        graph = orchestrator.compile(actions, AudioProcessContext("track", 48000, 2))
        self.assertEqual([a.function_id for a in graph.applied_actions], [a.function_id for a in actions])
        self.assertEqual(graph.applied_actions[1].operation, "cut")
        self.assertIn("g=-1.00", graph.filter_chain)
        self.assertEqual(graph.output_label, "autogain_final_peak_out_1")
        self.assertNotIn("[0:a]volume=-3", graph.filter_chain)

    def test_consecutive_multiband_actions_share_one_crossover(self):
        actions = [
            AudioFunctionAction("audio.multiband.eq", target="bass", params={"gain_db": -1.0}),
            AudioFunctionAction("audio.multiband.eq", target="mid", params={"gain_db": 0.5}),
            AudioFunctionAction("audio.multiband.stereo_width", target="air", params={"width": 1.2}),
        ]
        graph = orchestrator.compile(actions, AudioProcessContext("track", 48000, 2))
        self.assertEqual(graph.filter_chain.count("asplit=6"), 1)
        self.assertEqual(len(graph.applied_actions), 3)
        self.assertEqual(
            [action.operation for action in graph.applied_actions],
            ["cut", "boost", "expand"],
        )
        self.assertIn("volume=-1.00dB", graph.filter_chain)
        self.assertIn("volume=0.50dB", graph.filter_chain)

    def test_legacy_configuration_migrates_to_function_ids(self):
        actions = migrate_legacy_preprocess_config(
            band_stats=BANDS, dynamic_eq=True, stereo_width=False, deesser=True,
            deesser_freq_hz=6500.0, deesser_intensity=0.8,
            tone_mid_db=-1.0, saturation_enabled=True,
            saturation_drive_db=2.0, saturation_mix=0.25,
            glue_enabled=True, autogain_enabled=True,
        )
        ids = [action.function_id for action in actions]
        self.assertIn("audio.deesser.sibilance_reduction", ids)
        self.assertIn("audio.tone_eq.band", ids)
        self.assertIn("audio.multiband.compressor", ids)
        self.assertIn("audio.saturation.softclip", ids)
        self.assertIn("audio.glue.bus_compressor", ids)
        self.assertEqual(ids[0], "audio.autogain.headroom")
        self.assertEqual(ids[-1], "audio.autogain.final_peak")

    def test_serialized_registry_state_is_migrated(self):
        state = {
            "order": ["repair", "tone_eq", "saturation", "autogain", "loudness"],
            "processes": {
                "repair": {"enabled": True, "params": {"noise_level": "Leve"}},
                "tone_eq": {"enabled": True, "params": {"low_mid_db": -1.5, "mid_db": 0.5}},
                "saturation": {"enabled": True, "params": {
                    "saturation_enabled": True, "drive_db": 2.0, "mix": 0.2, "saturation_type": "Tape",
                }},
                "autogain": {"enabled": True, "params": {"autogain_enabled": True, "headroom_db": -16.0}},
                "loudness": {"enabled": True, "params": {"target_lufs": -14.0, "true_peak": -1.0, "lra": 11.0}},
            },
        }
        actions = migrate_legacy_registry_state(state)
        ids = [action.function_id for action in actions]
        self.assertIn("audio.repair.denoise", ids)
        self.assertGreaterEqual(ids.count("audio.tone_eq.band"), 2)
        self.assertIn("audio.saturation.softclip", ids)
        self.assertEqual(ids[-1], "audio.loudness.normalize")

    def test_public_legacy_api_executes_the_plugin_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = pathlib.Path(tmp) / "fixture.wav"
            create = subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "aevalsrc=0.05*sin(2*PI*440*t)|0.05*sin(2*PI*660*t):s=44100:d=0.2",
                "-c:a", "pcm_s16le", str(input_path),
            ], capture_output=True, text=True)
            self.assertEqual(create.returncode, 0, create.stderr)
            chain, output = build_preprocess_chain(
                input_path=input_path, band_stats=BANDS, dynamic_eq=False,
                stereo_width=False, deesser=False, tone_mid_db=-1.0,
                saturation_enabled=True, saturation_drive_db=2.0,
                saturation_mix=0.2, autogain_enabled=True,
            )
            self.assertIn("tone_eq_band", chain)
            self.assertIn("saturation_softclip", chain)
            render = subprocess.run([
                "ffmpeg", "-v", "error", "-i", str(input_path),
                "-filter_complex", chain, "-map", f"[{output}]", "-f", "null", "-",
            ], capture_output=True, text=True, timeout=20)
            self.assertEqual(render.returncode, 0, render.stderr)

    def test_normalize_audio_uses_plugins_for_preprocess_and_master(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = pathlib.Path(tmp) / "input.wav"
            output_path = pathlib.Path(tmp) / "output.wav"
            create = subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "aevalsrc=0.05*sin(2*PI*440*t)|0.05*sin(2*PI*660*t):s=48000:d=1",
                "-c:a", "pcm_s16le", str(input_path),
            ], capture_output=True, text=True)
            self.assertEqual(create.returncode, 0, create.stderr)
            stats = {
                "input_i": -24.0, "input_lra": 10.0, "input_tp": -12.0,
                "input_thresh": -34.0, "target_offset": 0.0,
            }
            normalize_audio(
                input_path=input_path, output_path=output_path, stats=stats,
                target_lufs=-14.0, true_peak=-1.0, overwrite=True, verbose=False,
                tone_mid_db=-1.0, master_limiter_enabled=True,
                output_format="wav",
            )
            self.assertTrue(output_path.exists())
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=sample_rate,channels", "-of", "csv=p=0",
                str(output_path),
            ], capture_output=True, text=True)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(probe.stdout.strip(), "48000,2")


if __name__ == "__main__":
    unittest.main()
