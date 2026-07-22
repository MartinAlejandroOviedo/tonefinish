import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace

from auto_master_intelligence import _build_adjustments_from_ia
from ia_mastering import build_analysis_prompt, load_past_strategies, validate_mastering_strategy
from processes.contracts import ContractError, infer_action_operation
from ui.workers import _verify_worker_ai_source
from processes.audit import (
    build_execution_audit, catalog_fingerprint, effective_execution_actions,
    fingerprint_audio_source, verify_audio_source,
)


def action(function_id, params, *, target=None, reason="medición", confidence=0.9,
           operation=None, evidence=None):
    resolved_operation = operation or infer_action_operation(function_id, params)
    default_evidence = {"measured_value": 1.0}
    if resolved_operation == "cut":
        default_evidence["measured_excess_db"] = 1.0
    elif resolved_operation == "boost":
        default_evidence["measured_deficit_db"] = 1.0
        if function_id in {
            "audio.autogain.output_gain", "audio.glue.bus_compressor",
            "audio.multiband.compressor",
        }:
            default_evidence["compensation_required_db"] = 1.0
    value = {
        "function_id": function_id,
        "enabled": True,
        "operation": resolved_operation,
        "params": params,
        "evidence": evidence or default_evidence,
        "reason": reason,
        "confidence": confidence,
    }
    if target is not None:
        value["target"] = target
    return value


class AiFunctionDecisionTests(unittest.TestCase):
    def test_prompt_identifies_audio_and_exposes_live_function_catalog(self):
        prompt = build_analysis_prompt({}, {}, {}, "SUNO", audio_id="track-42")
        self.assertIn("Audio ID: track-42", prompt)
        self.assertIn('"audio.tone_eq.band"', prompt)
        self.assertIn('"audio.limiter.true_peak"', prompt)
        self.assertIn('"supported_operations"', prompt)
        self.assertIn('"operation": "cut"', prompt)
        self.assertIn('"evidence"', prompt)

    def test_validator_keeps_valid_action_and_injects_output_guardrails(self):
        strategy = {
            "audio_id": "track-42",
            "diagnosis": "medios cargados",
            "what_to_fix": ["low-mid"],
            "what_to_keep": ["transientes"],
            "actions": [action(
                "audio.tone_eq.band",
                {"frequency_hz": 350.0, "gain_db": -1.5, "q": 1.2, "filter_type": "peaking"},
                target="low_mid",
            )],
            "notes": [],
        }
        result = validate_mastering_strategy(
            strategy, audio_id="track-42", target_lufs=-15.0,
            true_peak=-1.5, pre_stats={"input_lra": 8.0, "crest_factor": 11.0},
        )
        ids = [item["function_id"] for item in result["actions"]]
        self.assertEqual(ids, [
            "audio.tone_eq.band", "audio.loudness.normalize", "audio.limiter.true_peak"
        ])
        self.assertEqual(len(result["decision_trace"]["injected_guardrails"]), 2)
        self.assertEqual(result["actions"][0]["operation"], "cut")
        self.assertEqual(result["actions"][0]["params"]["gain_db"], -1.5)

    def test_validator_rejects_unsafe_and_unknown_actions_with_trace(self):
        strategy = {
            "audio_id": "compressed.wav",
            "actions": [
                action("audio.multiband.stereo_width", {"width": 1.4}, target="sub_bass"),
                action("audio.saturation.softclip", {
                    "drive_db": 3.0, "mix": 0.3, "type": "Tape", "oversampling": 2,
                }),
                action("audio.plugin.inventado", {}),
            ],
        }
        result = validate_mastering_strategy(
            strategy, audio_id="compressed.wav", target_lufs=-14.0,
            true_peak=-1.0, pre_stats={"input_lra": 3.0, "crest_factor": 7.0},
        )
        self.assertEqual(len(result["decision_trace"]["rejected_actions"]), 3)
        self.assertEqual(
            [item["function_id"] for item in result["actions"]],
            ["audio.loudness.normalize", "audio.limiter.true_peak"],
        )

    def test_disabled_ai_action_is_rejected_instead_of_silently_skipped(self):
        disabled = action(
            "audio.tone_eq.band",
            {"frequency_hz": 500.0, "gain_db": -1.0, "q": 1.0, "filter_type": "peaking"},
            target="low_mid",
        )
        disabled["enabled"] = False
        result = validate_mastering_strategy(
            {"audio_id": "disabled.wav", "actions": [disabled]},
            audio_id="disabled.wav", target_lufs=-14.0,
            true_peak=-1.0, pre_stats={},
        )
        self.assertEqual(len(result["decision_trace"]["rejected_actions"]), 1)
        self.assertNotIn("audio.tone_eq.band", result["decision_trace"]["effective_order"])

    def test_direction_must_match_signed_parameter(self):
        contradictory = action(
            "audio.tone_eq.band",
            {"frequency_hz": 3000.0, "gain_db": -1.5, "q": 2.0, "filter_type": "peaking"},
            target="high_mid", operation="boost",
        )
        result = validate_mastering_strategy(
            {"audio_id": "sign.wav", "actions": [contradictory]},
            audio_id="sign.wav", target_lufs=-15.0, true_peak=-2.0, pre_stats={},
        )
        self.assertEqual(len(result["decision_trace"]["rejected_actions"]), 1)
        self.assertNotIn("audio.tone_eq.band", result["decision_trace"]["effective_order"])

    def test_ai_action_without_evidence_is_rejected(self):
        raw = action(
            "audio.multiband.eq", {"gain_db": -1.0}, target="air", operation="cut"
        )
        raw["evidence"] = {}
        result = validate_mastering_strategy(
            {"audio_id": "evidence.wav", "actions": [raw]},
            audio_id="evidence.wav", target_lufs=-15.0, true_peak=-2.0, pre_stats={},
        )
        self.assertEqual(len(result["decision_trace"]["rejected_actions"]), 1)

    def test_nested_provider_loudness_is_flattened_and_local_measurement_wins(self):
        normalize = action("audio.loudness.normalize", {
            "target_lufs": -15.5, "true_peak_db": -2.2, "lra": 11.0, "dual_mono": False,
        }, operation="protect", evidence={"loudness_stats": {
            "integrated_lufs": -14.1, "true_peak_db": -4.1, "lra": 3.7}})
        result = validate_mastering_strategy(
            {"audio_id": "local-wins.wav", "actions": [normalize]},
            audio_id="local-wins.wav", target_lufs=-15.5, true_peak=-2.2,
            pre_stats={"input_i": -34.54, "input_tp": -24.5})
        self.assertFalse(result["decision_trace"]["rejected_actions"])
        validated = next(a for a in result["actions"] if a["function_id"] == "audio.loudness.normalize")
        self.assertEqual(validated["evidence"]["measured_input_lufs"], -34.54)
        self.assertEqual(validated["evidence"]["measured_input_true_peak_db"], -24.5)
        self.assertEqual(validated["evidence"]["measurement_source"], "local_ffmpeg")

    def test_neutral_decision_is_traced_but_not_executed(self):
        neutral = action(
            "audio.multiband.eq", {"gain_db": 0.0}, target="mid", operation="neutral"
        )
        result = validate_mastering_strategy(
            {"audio_id": "neutral.wav", "actions": [neutral]},
            audio_id="neutral.wav", target_lufs=-15.0, true_peak=-2.0, pre_stats={},
        )
        self.assertEqual(len(result["decision_trace"]["neutral_decisions"]), 1)
        self.assertNotIn("audio.multiband.eq", result["decision_trace"]["effective_order"])

    def test_dynamic_resonance_requires_matching_measurement_and_band(self):
        resonance = action(
            "audio.dynamic_eq.resonance",
            {"frequency_hz": 3200.0, "q": 4.0, "threshold_db": -30.0,
             "max_reduction_db": 2.0, "ratio": 2.0, "attack_ms": 15.0,
             "release_ms": 180.0, "scope": "mid", "filter_type": "bell"},
            target="high_mid", operation="cut",
            evidence={"measured_excess_db": 2.4, "resonance_frequency_hz": 3250.0,
                      "mid_side_ratio": 0.78},
        )
        result = validate_mastering_strategy(
            {"audio_id": "dynamic.wav", "actions": [resonance]},
            audio_id="dynamic.wav", target_lufs=-15.5, true_peak=-2.2, pre_stats={},
            dynamic_eq_evidence={
                "mid_side_ratio": 0.78,
                "resonance_candidates": [{"frequency_hz": 3250.0, "target": "high_mid",
                                           "measured_excess_db": 2.4}],
            },
        )
        self.assertIn("audio.dynamic_eq.resonance", result["decision_trace"]["effective_order"])
        self.assertEqual(result["decision_trace"]["budget_report"]["totals"]["tonal_cut_db"], 2.0)

    def test_dynamic_eq_rejects_frequency_outside_target_band(self):
        motion = action(
            "audio.dynamic_eq.motion",
            {"frequency_hz": 9000.0, "q": 0.8, "threshold_db": -35.0,
             "gain_db": 0.5, "ratio": 1.5, "attack_ms": 80.0,
             "release_ms": 350.0, "scope": "stereo", "filter_type": "highshelf"},
            target="mid", operation="boost", evidence={"measured_deficit_db": 1.0},
        )
        result = validate_mastering_strategy(
            {"audio_id": "wrong-band.wav", "actions": [motion]},
            audio_id="wrong-band.wav", target_lufs=-15.5, true_peak=-2.2, pre_stats={},
        )
        self.assertIn("fuera de target", result["decision_trace"]["rejected_actions"][0]["error"])

    def test_dynamic_mid_scope_rejects_weak_center_evidence(self):
        resonance = action(
            "audio.dynamic_eq.resonance",
            {"frequency_hz": 3200.0, "q": 4.0, "threshold_db": -30.0,
             "max_reduction_db": 1.5, "ratio": 2.0, "attack_ms": 15.0,
             "release_ms": 180.0, "scope": "mid", "filter_type": "bell"},
            target="high_mid", operation="cut",
            evidence={"measured_excess_db": 2.0, "resonance_frequency_hz": 3200.0,
                      "mid_side_ratio": 0.45},
        )
        result = validate_mastering_strategy(
            {"audio_id": "weak-mid.wav", "actions": [resonance]},
            audio_id="weak-mid.wav", target_lufs=-15.5, true_peak=-2.2, pre_stats={},
            dynamic_eq_evidence={
                "mid_side_ratio": 0.45,
                "resonance_candidates": [{"frequency_hz": 3200.0, "target": "high_mid",
                                           "measured_excess_db": 2.0}],
            },
        )
        self.assertIn("predominio central", result["decision_trace"]["rejected_actions"][0]["error"])

    def test_vocal_resonance_requires_authoritative_center_evidence(self):
        vocal = action(
            "audio.vocal.resonance_suppressor",
            {"frequency_hz": 3400.0, "q": 3.5, "threshold_db": -28.0,
             "max_reduction_db": 1.5, "ratio": 2.0, "attack_ms": 18.0,
             "release_ms": 180.0, "filter_type": "bell"}, operation="cut",
            evidence={"measured_excess_db": 2.1, "resonance_frequency_hz": 3420.0,
                      "mid_side_ratio": 0.78, "vocal_center_confidence": 0.82})
        result = validate_mastering_strategy(
            {"audio_id": "vocal.wav", "actions": [vocal]}, audio_id="vocal.wav",
            target_lufs=-15.5, true_peak=-2.0, pre_stats={},
            dynamic_eq_evidence={"mid_side_ratio": 0.78, "vocal_center_confidence": 0.82,
                "resonance_candidates": [{"frequency_hz": 3420.0, "target": "high_mid",
                                            "measured_excess_db": 2.1}]})
        self.assertIn("audio.vocal.resonance_suppressor", result["decision_trace"]["effective_order"])

    def test_vocal_naturalizer_requires_measured_add_and_cut_evidence(self):
        naturalizer = action(
            "audio.vocal.center_naturalizer",
            {"body_frequency_hz": 300.0, "body_gain_db": 0.6,
             "harshness_frequency_hz": 3500.0, "harshness_reduction_db": 1.2,
             "air_frequency_hz": 8500.0, "air_reduction_db": 0.4, "mix": 0.25},
            operation="protect", evidence={"mid_side_ratio": 0.8,
                "vocal_center_confidence": 0.85, "measured_body_deficit_db": 1.0,
                "measured_harshness_excess_db": 1.8, "measured_air_excess_db": 0.8})
        result = validate_mastering_strategy(
            {"audio_id": "natural.wav", "actions": [naturalizer]}, audio_id="natural.wav",
            target_lufs=-15.5, true_peak=-2.0, pre_stats={},
            dynamic_eq_evidence={"mid_side_ratio": 0.8, "vocal_center_confidence": 0.85})
        self.assertIn("audio.vocal.center_naturalizer", result["decision_trace"]["effective_order"])

    def test_vocal_processing_rejects_uncertain_center(self):
        vocal = action("audio.vocal.resonance_suppressor",
            {"frequency_hz": 3400.0, "q": 3.5, "threshold_db": -28.0,
             "max_reduction_db": 1.0, "ratio": 2.0, "attack_ms": 18.0,
             "release_ms": 180.0, "filter_type": "bell"}, operation="cut",
            evidence={"measured_excess_db": 2.0, "resonance_frequency_hz": 3400.0,
                      "mid_side_ratio": 0.5, "vocal_center_confidence": 0.4})
        result = validate_mastering_strategy(
            {"audio_id": "uncertain.wav", "actions": [vocal]}, audio_id="uncertain.wav",
            target_lufs=-15.5, true_peak=-2.0, pre_stats={},
            dynamic_eq_evidence={"mid_side_ratio": 0.5, "vocal_center_confidence": 0.4,
                "resonance_candidates": []})
        self.assertIn("presencia central confiable", result["decision_trace"]["rejected_actions"][0]["error"])

    def test_complementary_plugins_require_and_accept_matching_local_metrics(self):
        cases = [
            ("audio.transient.dynamic_control", {"amount_db": -1.0, "threshold_db": -18.0,
             "attack_ms": 10.0, "release_ms": 120.0}, "cut", {"transient_crest_db": 13.0},
             {"transient_crest_db": 13.0}),
            ("audio.stereo.correlation_guard", {"width": 1.1}, "expand",
             {"stereo_correlation": 0.82}, {"stereo_correlation": 0.82}),
            ("audio.low_end.dynamic_balance", {"frequency_hz": 100.0, "q": 0.7,
             "threshold_db": -28.0, "gain_db": 0.5, "ratio": 1.5, "attack_ms": 60.0,
             "release_ms": 300.0, "filter_type": "lowshelf"}, "boost",
             {"low_end_level_db": -4.0, "low_end_mid_ratio": 0.8, "measured_deficit_db": 1.0},
             {"low_end_level_db": -4.0, "low_end_mid_ratio": 0.8}),
            ("audio.spectral.deharsh", {"frequency_hz": 3800.0, "q": 0.8,
             "threshold_db": -28.0, "max_reduction_db": 1.0, "ratio": 1.5,
             "attack_ms": 30.0, "release_ms": 220.0, "filter_type": "bell"}, "cut",
             {"harshness_excess_db": 2.0, "measured_excess_db": 2.0}, {"harshness_excess_db": 2.0}),
            ("audio.spectral.dullness_recovery", {"frequency_hz": 8500.0, "q": 0.7,
             "threshold_db": -35.0, "max_boost_db": 0.5, "ratio": 1.4,
             "attack_ms": 80.0, "release_ms": 400.0, "filter_type": "highshelf"}, "boost",
             {"dullness_deficit_db": 2.0, "measured_deficit_db": 2.0}, {"dullness_deficit_db": 2.0}),
        ]
        for function_id, params, operation, evidence, local in cases:
            with self.subTest(function_id=function_id):
                result = validate_mastering_strategy(
                    {"audio_id": "complement.wav", "actions": [action(
                        function_id, params, operation=operation, evidence=evidence)]},
                    audio_id="complement.wav", target_lufs=-15.5, true_peak=-2.0,
                    pre_stats={}, dynamic_eq_evidence=local)
                self.assertIn(function_id, result["decision_trace"]["effective_order"])

    def test_unsafe_stereo_expansion_is_rejected(self):
        expand = action("audio.stereo.correlation_guard", {"width": 1.15}, operation="expand",
                        evidence={"stereo_correlation": 0.3})
        result = validate_mastering_strategy(
            {"audio_id": "phase.wav", "actions": [expand]}, audio_id="phase.wav",
            target_lufs=-15.5, true_peak=-2.0, pre_stats={},
            dynamic_eq_evidence={"stereo_correlation": 0.3})
        self.assertIn("correlación local", result["decision_trace"]["rejected_actions"][0]["error"])

    def test_guardrails_are_canonicalized_to_the_real_final_stage(self):
        limiter = action("audio.limiter.true_peak", {
            "ceiling_db": -1.0, "release_ms": 150.0, "lookahead_ms": 5.0,
            "mode": "transparent", "oversampling": 4,
        })
        tone = action(
            "audio.tone_eq.band",
            {"frequency_hz": 1000.0, "gain_db": -1.0, "q": 1.0, "filter_type": "peaking"},
            target="mid",
        )
        result = validate_mastering_strategy(
            {"audio_id": "ordered.wav", "actions": [limiter, tone]},
            audio_id="ordered.wav", target_lufs=-14.0,
            true_peak=-1.0, pre_stats={},
        )
        order = result["decision_trace"]["effective_order"]
        self.assertEqual(order[-2:], ["audio.loudness.normalize", "audio.limiter.true_peak"])
        self.assertEqual([item["function_id"] for item in result["actions"]], order)

    def test_audio_id_mismatch_is_fatal(self):
        with self.assertRaises(ContractError):
            validate_mastering_strategy(
                {"audio_id": "other", "actions": []}, audio_id="expected",
                target_lufs=-14.0, true_peak=-1.0, pre_stats={},
            )

    def test_compatibility_adapter_preserves_canonical_actions_and_trace(self):
        canonical = action(
            "audio.tone_eq.band",
            {"frequency_hz": 300.0, "gain_db": -1.0, "q": 1.0, "filter_type": "peaking"},
            target="low_mid",
        )
        trace = {"audio_id": "one.wav", "rejected_actions": []}
        adjustments = _build_adjustments_from_ia(
            {"actions": [canonical], "decision_trace": trace, "diagnosis": "ok", "notes": []},
            object(),
        )
        self.assertEqual(adjustments["audio_actions"], [canonical])
        self.assertEqual(adjustments["decision_trace"], trace)

    def test_execution_audit_closes_loop_with_measured_output(self):
        actions = [action(
            "audio.loudness.normalize",
            {"target_lufs": -14.0, "true_peak_db": -1.0, "lra": 11.0, "dual_mono": False},
        )]
        audit = build_execution_audit(
            actions,
            before_stats={"input_i": -22.0, "input_tp": -8.0},
            after_stats={"output_i": -14.2, "output_tp": -1.1},
            target_lufs=-14.0,
            true_peak=-1.0,
        )
        self.assertEqual(audit["status"], "passed")
        self.assertTrue(audit["catalog_fingerprint"].startswith("sha256:"))
        self.assertEqual(audit["action_results"][0]["function_id"], "audio.loudness.normalize")
        self.assertEqual(audit["action_results"][0]["operation"], "protect")
        self.assertIn("params", audit["action_results"][0])
        self.assertTrue(audit["action_results"][0]["action_fingerprint"].startswith("sha256:"))
        self.assertEqual(audit["operation_summary"]["protect"], 1)

    def test_execution_audit_warns_when_targets_are_not_met(self):
        audit = build_execution_audit(
            [], before_stats={},
            after_stats={"input_i": -16.0, "input_tp": -0.2},
            target_lufs=-14.0, true_peak=-1.0,
        )
        self.assertEqual(audit["status"], "warning")
        self.assertFalse(audit["checks"]["loudness"]["passed"])
        self.assertFalse(audit["checks"]["true_peak"]["passed"])

    def test_effective_execution_order_matches_pipeline_stages(self):
        actions = [
            action("audio.limiter.true_peak", {
                "ceiling_db": -1.0, "release_ms": 100.0, "lookahead_ms": 5.0,
                "mode": "transparent", "oversampling": 4,
            }),
            action("audio.autogain.headroom", {"gain_db": -8.0}),
            action("audio.loudness.normalize", {
                "target_lufs": -14.0, "true_peak_db": -1.0, "lra": 11.0,
                "dual_mono": False,
            }),
        ]
        order = [item.function_id for item in effective_execution_actions(actions)]
        self.assertEqual(order, [
            "audio.autogain.headroom", "audio.loudness.normalize", "audio.limiter.true_peak",
        ])

    def test_decision_trace_identifies_catalog_version(self):
        result = validate_mastering_strategy(
            {"audio_id": "versioned.wav", "actions": []},
            audio_id="versioned.wav", target_lufs=-14.0,
            true_peak=-1.0, pre_stats={},
        )
        self.assertEqual(result["decision_trace"]["catalog_fingerprint"], catalog_fingerprint())

    def test_decision_trace_binds_strategy_to_audio_content(self):
        result = validate_mastering_strategy(
            {"audio_id": "bound.wav", "actions": []},
            audio_id="bound.wav", target_lufs=-14.0, true_peak=-1.0,
            pre_stats={}, source_fingerprint="sha256:audio-version-one",
        )
        self.assertEqual(
            result["decision_trace"]["source_fingerprint"],
            "sha256:audio-version-one",
        )

    def test_audio_binding_rejects_file_changed_after_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "audio.wav"
            source.write_bytes(b"version-one")
            fingerprint = fingerprint_audio_source(source)
            self.assertEqual(verify_audio_source(source, fingerprint), fingerprint)
            source.write_bytes(b"version-two")
            with self.assertRaisesRegex(ValueError, "cambió después del análisis"):
                verify_audio_source(source, fingerprint)

    def test_batch_source_binding_uses_current_file_not_worker_attribute(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "batch-track.wav"
            source.write_bytes(b"batch-audio")
            worker = SimpleNamespace(
                _ai_source_fingerprint=fingerprint_audio_source(source),
                _ai_audio_actions=[{"function_id": "audio.loudness.normalize"}],
            )
            # BatchWorker no tiene input_path propio: recibe la pista de la iteración.
            _verify_worker_ai_source(worker, source)

    def test_learning_ignores_outputs_that_failed_quality_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            base = {
                "used_ai_strategy": True,
                "status": "applied",
                "adjustments": {"diagnostics": "test", "audio_actions": []},
            }
            failed = dict(base)
            failed["decision_trace"] = {"execution_audit": {"status": "warning"}}
            passed = dict(base)
            passed["executed_actions"] = []
            passed["decision_trace"] = {"execution_audit": {"status": "passed"}}
            (root / "failed.ai_master.json").write_text(json.dumps(failed), encoding="utf-8")
            (root / "passed.ai_master.json").write_text(json.dumps(passed), encoding="utf-8")
            examples = load_past_strategies(str(root))
            self.assertEqual(len(examples), 1)
            self.assertTrue(examples[0]["file"].endswith("passed.ai_master.json"))


if __name__ == "__main__":
    unittest.main()
