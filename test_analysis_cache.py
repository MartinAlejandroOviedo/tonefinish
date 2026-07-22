import json, pathlib, tempfile, unittest
from unittest.mock import patch
import cache
from ui.workers import _analyze_single_file_for_batch

class AnalysisCacheTests(unittest.TestCase):
    def test_legacy_and_all_floor_band_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp); audio=root/"song.wav"; audio.write_bytes(b"audio")
            with patch.object(cache,"CACHE_DIR",root/"cache"):
                digest=cache._compute_file_hash(audio); path=cache._get_cache_path(digest); path.parent.mkdir()
                base={"stats":{},"band_stats":{f"band{i}":-70.0 for i in range(6)}}
                path.write_text(json.dumps(base)); self.assertIsNone(cache.get_cached_analysis(audio))
                base["schema_version"]=cache.CACHE_SCHEMA_VERSION
                path.write_text(json.dumps(base)); self.assertIsNone(cache.get_cached_analysis(audio))

    def test_current_measured_cache_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp); audio=root/"song.wav"; audio.write_bytes(b"audio")
            bands={f"band{i}":-30.0-i for i in range(6)}
            with patch.object(cache,"CACHE_DIR",root/"cache"):
                self.assertTrue(cache.save_analysis_cache(audio,{},bands,[],None))
                self.assertEqual(cache.get_cached_analysis(audio)["band_stats"],bands)

    def test_batch_analysis_uses_named_fields_without_tuple_order_ambiguity(self):
        bands={f"band{i}":-20.0-i for i in range(6)}
        with tempfile.TemporaryDirectory() as tmp:
            audio=pathlib.Path(tmp)/"song.wav"; audio.write_bytes(b"audio")
            with patch("ui.workers.get_cached_analysis",return_value={"band_stats":bands,"voice_rms":-24.0}), \
                 patch("ui.workers.analyze_audio",return_value=({"input_i":-14.0},"")):
                result=_analyze_single_file_for_batch(audio,-15.5,-2.2,4.0,True)
        self.assertEqual(result.raw_stats["input_i"],-14.0)
        self.assertEqual(result.band_stats,bands)
        self.assertEqual(result.voice_rms,-24.0)

if __name__=="__main__": unittest.main()
