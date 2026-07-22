import json, os, pathlib, shutil, subprocess, tempfile, unittest
from adaptive_master_renderer import build_adaptive_filter, publish_adaptive_candidate, render_adaptive_candidate
from alternative_tools import analyze_loudness_ffmpeg
import analysis_mts
from analysis_mts import write_mts_artifacts
import audio_tools

DECISIONS={"section_decisions":[{"section_id":1,"label":"verse","start_s":0.0,"end_s":1.0,
    "actions":{"eq_db":{"bass_db":0.25,"high_mid_db":-0.3}},
    "guards":{"smoothing_ms":180.0}}]}

class AdaptiveRendererTests(unittest.TestCase):
    def test_filter_contains_signed_automation_and_smoothing(self):
        graph,output,executed=build_adaptive_filter(DECISIONS)
        self.assertTrue(output); self.assertEqual(len(executed),2)
        self.assertIn("g=0.25",graph); self.assertIn("g=-0.3",graph)
        self.assertTrue(all(item["smoothing_ms"]==180.0 for item in executed))

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg requerido")
    def test_candidate_is_rendered_measured_and_published_transactionally(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=pathlib.Path(tmp)/"master.wav"
            result=subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i",
                "aevalsrc=0.05*sin(2*PI*120*t)+0.03*sin(2*PI*3800*t)|0.04*sin(2*PI*120*t):s=48000:d=1",
                str(source)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            before=analyze_loudness_ffmpeg(str(source)); self.assertIsNotNone(before)
            report=render_adaptive_candidate(source,DECISIONS,before.input_i,-1.0)
            self.assertEqual(report["status"],"candidate_ready",report)
            self.assertEqual(len(report["executed_automations"]),2)
            self.assertTrue(publish_adaptive_candidate(source,report))
            self.assertEqual(report["status"],"applied"); self.assertTrue(source.is_file())

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg requerido")
    @unittest.skipUnless(analysis_mts.NUMPY_AVAILABLE,"NumPy requerido para MTS")
    def test_mts_pipeline_applies_or_safely_falls_back_and_audits(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=pathlib.Path(tmp)/"pipeline.wav"
            subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i",
                "aevalsrc=0.04*sin(2*PI*220*t)|0.035*sin(2*PI*330*t):s=32000:d=2.2",str(source)],check=True)
            measured=analyze_loudness_ffmpeg(str(source)); self.assertIsNotNone(measured)
            old={key:os.environ.get(key) for key in ("TONEFINISH_ADAPTIVE_MASTER_ENABLED","TONEFINISH_ADAPTIVE_ROLLOUT_PERCENT")}
            os.environ["TONEFINISH_ADAPTIVE_MASTER_ENABLED"]="1"; os.environ["TONEFINISH_ADAPTIVE_ROLLOUT_PERCENT"]="100"
            try:
                previous_ffmpeg=audio_tools._FFMPEG_BIN; audio_tools._FFMPEG_BIN=shutil.which("ffmpeg") or "ffmpeg"
                paths=write_mts_artifacts(source,source,validation_context={
                    "target_lufs":measured.input_i,"true_peak_target":0.0,
                    "pre_stats":{"input_i":measured.input_i,"input_tp":measured.input_tp},
                    "post_stats":{"input_i":measured.input_i,"input_tp":measured.input_tp},
                    "global_adjustments":{"eq_adjustments":{"Bass (60-250 Hz)":0.2}}})
            finally:
                audio_tools._FFMPEG_BIN=previous_ffmpeg
                for key,value in old.items():
                    if value is None: os.environ.pop(key,None)
                    else: os.environ[key]=value
            report=json.loads(paths["adaptive_render_json_path"].read_text())
            self.assertEqual(report["status"],"applied",report)
            self.assertTrue(report["selected_for_rollout"])
            self.assertTrue(paths["adaptive_render_md_path"].is_file())

if __name__=="__main__": unittest.main()
