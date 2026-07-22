from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


class PackagingContractTests(unittest.TestCase):
    def test_deb_contains_runtime_modules_and_spasm_dependencies(self):
        script = (ROOT / "packaging" / "build_deb.sh").read_text(encoding="utf-8")
        self.assertIn("output_naming.py", script)
        self.assertIn("adaptive_master_renderer.py", script)
        self.assertIn("spasm (>= 0.2.3)", script)
        self.assertIn("spasm-skill-ffmpeg-subset (>= 0.2.3~exp1)", script)

    def test_spasm_cli_prefers_installed_runtime(self):
        script = (ROOT / "scripts" / "finisher_spasm_cli").read_text(encoding="utf-8")
        installed_lookup = script.index("command -v spasm")
        development_fallback = script.index("/home/martin/Documentos/SpASM/spasm")
        self.assertLess(installed_lookup, development_fallback)


if __name__ == "__main__":
    unittest.main()
