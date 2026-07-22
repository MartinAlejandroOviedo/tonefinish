import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave


ROOT = Path(__file__).resolve().parent
CLI = ROOT / "scripts" / "finisher_spasm_cli"


class SpasmCliTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg-spasm"), "skill ffmpeg de SpASM no disponible")
    def test_apply_output_gain_does_not_require_ripgrep(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.wav"
            output = Path(tmp) / "output.wav"
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(48_000)
                wav.writeframes(struct.pack("<h", 0) * 4_800)

            request = {
                "method": "apply_output_gain",
                "args": [
                    {"__type__": "path", "value": str(source)},
                    {"__type__": "path", "value": str(output)},
                    -0.67,
                    -2.8,
                ],
                "kwargs": {
                    "limiter_ceiling_db": -2.2,
                    "output_format": "wav",
                    "output_bit_depth": "24",
                    "overwrite": True,
                },
            }
            env = os.environ.copy()
            env["FINISHER_FFMPEG_BIN"] = shutil.which("ffmpeg-spasm") or "ffmpeg-spasm"
            env["FINISHER_SPASM_BIN"] = str(ROOT.parents[1] / "SpASM" / "spasm")
            result = subprocess.run(
                [str(CLI), "call", "--json"],
                input=json.dumps(request),
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertTrue(json.loads(result.stdout)["ok"])
            self.assertTrue(output.is_file())
            self.assertNotIn("rg -", CLI.read_text(encoding="utf-8"))
            self.assertIn("level=false", CLI.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
