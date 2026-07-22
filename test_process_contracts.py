"""Pruebas del contrato estable de funciones de audio (Fase 1)."""

import unittest

from processes import registry
from processes.catalog import FUNCTION_SPECS, function_registry
from processes.contracts import (
    AudioFunctionAction, AudioFunctionRegistry, AudioFunctionSpec,
    AudioProcessContext, ContractError, FilterLabelFactory,
)


class FunctionCatalogTests(unittest.TestCase):
    def test_all_function_ids_are_unique(self):
        ids = [spec.function_id for spec in FUNCTION_SPECS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_registered_plugin_exposes_functions(self):
        for plugin in registry:
            with self.subTest(plugin=plugin.plugin_id):
                self.assertTrue(plugin.function_specs())

    def test_every_spec_points_to_registered_plugin(self):
        registered = {plugin.plugin_id for plugin in registry}
        for spec in function_registry.all():
            self.assertIn(spec.plugin_id, registered)

    def test_legacy_aliases_resolve(self):
        self.assertEqual(function_registry.resolve_id("brickwall"), "audio.limiter.true_peak")
        self.assertEqual(function_registry.resolve_id("dynamic_eq"), "audio.multiband.compressor")

    def test_duplicate_function_id_is_rejected(self):
        catalog = AudioFunctionRegistry()
        spec = AudioFunctionSpec("audio.test.function", "audio.test", "Test", "Test")
        catalog.register(spec)
        with self.assertRaises(ContractError):
            catalog.register(spec)

    def test_unknown_parameters_are_rejected(self):
        action = AudioFunctionAction(
            "audio.saturation.softclip", params={"drive_db": 2.0, "invented": 3}
        )
        with self.assertRaises(ContractError):
            function_registry.validate(action)

    def test_parameter_ranges_are_enforced(self):
        action = AudioFunctionAction(
            "audio.saturation.softclip", params={"drive_db": 99.0}
        )
        with self.assertRaises(ContractError):
            function_registry.validate(action)

    def test_negative_cut_survives_contract_validation(self):
        action = function_registry.validate(AudioFunctionAction(
            "audio.tone_eq.band", target="high_mid",
            params={"frequency_hz": 3200.0, "gain_db": -2.25, "q": 2.5,
                    "filter_type": "peaking"},
            operation="cut", evidence={"measured_excess_db": 2.8},
        ))
        self.assertEqual(action.operation, "cut")
        self.assertEqual(action.params["gain_db"], -2.25)
        self.assertEqual(action.evidence["measured_excess_db"], 2.8)

    def test_positive_boost_survives_contract_validation(self):
        action = function_registry.validate(AudioFunctionAction(
            "audio.multiband.eq", target="air", params={"gain_db": 0.75},
            operation="boost", evidence={"measured_deficit_db": 1.1},
        ))
        self.assertEqual(action.operation, "boost")
        self.assertEqual(action.params["gain_db"], 0.75)

    def test_width_operation_cannot_contradict_value(self):
        with self.assertRaisesRegex(ContractError, "narrow requiere width"):
            function_registry.validate(AudioFunctionAction(
                "audio.multiband.stereo_width", target="air", params={"width": 1.2},
                operation="narrow", evidence={"stereo_width": 1.4},
            ))

    def test_conflicting_functions_are_rejected(self):
        actions = [
            AudioFunctionAction("audio.saturation.softclip", params={"mix": 0.2}),
            AudioFunctionAction("audio.saturation.exciter", params={"mix": 0.2}),
        ]
        with self.assertRaises(ContractError):
            function_registry.validate_plan(actions)

    def test_required_analysis_is_enforced_when_context_is_provided(self):
        context = AudioProcessContext("track", 48000, 2, analysis={})
        action = AudioFunctionAction(
            "audio.deesser.sibilance_reduction",
            params={"frequency_hz": 6000.0, "intensity": 0.7},
        )
        with self.assertRaises(ContractError):
            function_registry.validate_plan([action], context)

    def test_ai_action_round_trip_preserves_function_id(self):
        source = {
            "function_id": "audio.multiband.eq", "target": "bass",
            "params": {"gain_db": -1.0}, "reason": "Exceso de graves",
            "confidence": 0.9,
        }
        action = AudioFunctionAction.from_dict(source)
        self.assertEqual(action.to_dict(), {**source, "enabled": True})

    def test_band_function_requires_stable_target(self):
        with self.assertRaises(ContractError):
            function_registry.validate(AudioFunctionAction("audio.multiband.eq", params={"gain_db": 1.0}))
        validated = function_registry.validate(AudioFunctionAction(
            "audio.multiband.eq", target="low_mid", params={"gain_db": -1.5}
        ))
        self.assertEqual(validated.target, "low_mid")

    def test_context_rejects_invalid_audio_format(self):
        with self.assertRaises(ContractError):
            AudioProcessContext("track", 0, 2)

    def test_labels_are_unique_and_deterministic(self):
        labels = FilterLabelFactory()
        self.assertEqual(labels.new("audio.tone_eq.band"), "tone_eq_band_out_1")
        self.assertEqual(labels.new("audio.tone_eq.band"), "tone_eq_band_out_2")


if __name__ == "__main__":
    unittest.main()
