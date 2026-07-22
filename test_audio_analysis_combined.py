import pathlib, unittest
from types import SimpleNamespace
from unittest.mock import patch
from audio_analysis import analyze_eq_and_voice

class CombinedBandAnalysisTests(unittest.TestCase):
    def test_explicit_output_and_filter_ids_make_reverse_ffmpeg_logs_deterministic(self):
        lines=[]
        for index,value in reversed(list(zip((3,7,11,15,19,23,27),(-21,-18,-26,-27,-30,-32,-24)))):
            lines.append(f"[Parsed_volumedetect_{index} @ x] mean_volume: {value}.0 dB")
            lines.append(f"[Parsed_volumedetect_{index} @ x] max_volume: {value+10}.0 dB")
        captured=[]
        def fake_run(cmd,verbose=False):
            captured.extend(cmd); return SimpleNamespace(returncode=0,stderr="\n".join(lines),stdout="")
        with patch("audio_analysis.run_ffmpeg",side_effect=fake_run):
            bands,_,voice=analyze_eq_and_voice(pathlib.Path("input.wav"),False,4.0)
        self.assertIn("[analysis_out]",captured)
        self.assertEqual(list(bands.values()),[-21.0,-18.0,-26.0,-27.0,-30.0,-32.0])
        self.assertEqual(voice,-24.0)

if __name__=="__main__": unittest.main()
