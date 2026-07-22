import json, pathlib, shutil, subprocess, tempfile, unittest
from processes import (AudioFunctionAction, AudioProcessContext, ContractError, FilterLabelFactory,
                       build_catalog_certification, compare_audio_ab, registry, write_catalog_certification)
from processes.catalog import function_registry

class PluginQualityTests(unittest.TestCase):
    def test_every_catalog_function_has_registered_implementation(self):
        report=build_catalog_certification(registry)
        self.assertEqual(report["functions_total"],36)
        self.assertEqual(report["implemented_total"],36)
        self.assertEqual(report["status"],"passed")
        with tempfile.TemporaryDirectory() as tmp:
            path=write_catalog_certification(pathlib.Path(tmp)/"cert.json",registry)
            self.assertEqual(json.loads(path.read_text())["status"],"passed")

    def test_every_parameter_schema_rejects_an_out_of_range_or_invalid_value(self):
        for spec in function_registry.all():
            with self.subTest(function_id=spec.function_id):
                name,param=next(iter(spec.parameters.items()))
                if param.minimum is not None: bad=param.minimum-1
                elif param.maximum is not None: bad=param.maximum+1
                elif param.choices: bad="__invalid_choice__"
                elif param.value_type=="bool": bad="false"
                else: bad=None
                target=spec.supported_targets[0] if spec.supported_targets else None
                with self.assertRaises(ContractError):
                    function_registry.validate(AudioFunctionAction(spec.function_id,params={name:bad},target=target))

    def test_zero_is_neutral_for_every_signed_bidirectional_control(self):
        cases=(("audio.tone_eq.band","gain_db","mid"),("audio.tone_eq.tilt","gain_db",None),
               ("audio.multiband.eq","gain_db","mid"),("audio.dynamic_eq.motion","gain_db","mid"),
               ("audio.transient.dynamic_control","amount_db",None),("audio.low_end.dynamic_balance","gain_db",None),
               ("audio.autogain.output_gain","gain_db",None),("audio.multiband.saturation","drive_db","mid"),
               ("audio.saturation.softclip","drive_db",None))
        for function_id,param,target in cases:
            with self.subTest(function_id=function_id):
                action=function_registry.validate(AudioFunctionAction(function_id,params={param:0.0},target=target,operation="neutral"))
                self.assertEqual(action.operation,"neutral"); self.assertEqual(action.params[param],0.0)

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg requerido")
    def test_mid_side_plugin_ab_preserves_phase_duration_and_headroom(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=pathlib.Path(tmp); bypass=tmp/"bypass.wav"; processed=tmp/"processed.wav"
            source="aevalsrc=0.06*sin(2*PI*3400*t)+0.02*sin(2*PI*300*t)|0.05*sin(2*PI*3400*t):s=48000:d=0.5"
            subprocess.run(["ffmpeg","-y","-v","error","-f","lavfi","-i",source,str(bypass)],check=True)
            plugin={p.plugin_id:p for p in registry}["audio.vocal"]
            action=AudioFunctionAction("audio.vocal.center_naturalizer",operation="protect",params={
                "body_frequency_hz":300.0,"body_gain_db":0.5,"harshness_frequency_hz":3500.0,
                "harshness_reduction_db":1.0,"air_frequency_hz":8500.0,"air_reduction_db":0.4,"mix":0.25})
            graph,out=plugin.build_function(action,"0:a",AudioProcessContext("ab",48000,2,0.5,{}),FilterLabelFactory())
            subprocess.run(["ffmpeg","-y","-v","error","-i",str(bypass),"-filter_complex",graph,"-map",f"[{out}]",str(processed)],check=True)
            report=compare_audio_ab(bypass,processed)
            self.assertTrue(report["passed_integrity"],report)
            self.assertEqual(report["clipped_samples"],0)
            self.assertGreater(report["waveform_correlation"],0.99)
            self.assertLess(abs(report["level_delta_db"]),0.5)
            self.assertAlmostEqual(report["duration_seconds"],0.5,places=2)

if __name__=="__main__": unittest.main()
