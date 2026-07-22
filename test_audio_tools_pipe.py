import struct, unittest
from types import SimpleNamespace
from unittest.mock import patch
import audio_tools

class AudioToolsPipeTests(unittest.TestCase):
    def test_binary_analysis_uses_stdout_marker_not_filename_pipe_colon_one(self):
        captured=[]
        def fake_run(cmd, **kwargs):
            captured.append(cmd)
            return SimpleNamespace(returncode=0,stdout=struct.pack("4f",0.0,0.1,-0.1,0.0),stderr=b"")
        with patch("audio_tools.subprocess.run",side_effect=fake_run):
            samples=audio_tools.get_audio_mono_samples("input.wav",sample_rate=8000,max_seconds=1)
        self.assertEqual(len(samples),4)
        self.assertEqual(captured[0][-1],"-")
        self.assertNotIn("pipe:1",captured[0])

if __name__=="__main__": unittest.main()
