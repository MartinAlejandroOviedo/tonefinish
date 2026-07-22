"""
ia_mastering.py — Estrategia de mastering completa por IA.
La IA recibe el análisis completo del track y controla CADA plugin.
Si no hay IA disponible, usa el gap-based engine existente.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, Optional

from bandcamp_bok import call_ai_multi

from processes.catalog import function_registry
from processes.contracts import AudioFunctionAction, ContractError
from processes.audit import catalog_fingerprint, effective_execution_actions, fingerprint_audio_source
from processes.budgets import DEFAULT_BUDGET_POLICY, evaluate_action_budgets


MASTERING_SYSTEM_PROMPT = """Sos un ingeniero de mastering senior.
Analizás cada track individualmente y solo podés decidir funciones presentes en el
catálogo recibido. Cada acción debe incluir function_id exacto, operation, params,
evidence, reason y confidence. Para funciones multibanda o audio.tone_eq.band también debe incluir target
con uno de estos IDs: sub_bass, bass, low_mid, mid, high_mid, air.

Reglas de seguridad:
- No proceses una banda o problema que ya esté correcto.
- sub_bass nunca debe ensancharse por encima de 1.0.
- Evitá compresión, glue y saturación adicionales si LRA o crest ya son bajos.
- Conservá transientes y no uses parámetros fuera del catálogo.
- operation debe ser compatible con supported_operations de la función.
- cut requiere ganancia negativa; boost requiere ganancia positiva.
- narrow requiere width menor que 1; expand requiere width mayor que 1.
- Preferí cut antes que boost cuando la medición muestre exceso de energía.
- No uses boost, cut, attenuate, narrow ni expand sin evidence medible y concreta.
- Si no existe evidencia suficiente, omití la acción; no inventes correcciones.
- Todo cut tonal requiere evidence.measured_excess_db positivo.
- Todo boost tonal requiere evidence.measured_deficit_db positivo.
- Ganancia o makeup positivos requieren evidence.compensation_required_db positivo.
- Dynamic EQ requiere target de banda y frequency_hz dentro de esa banda.
- audio.dynamic_eq.resonance requiere evidence.resonance_frequency_hz y measured_excess_db.
- scope=mid|side requiere evidence.mid_side_ratio; no asumas aislamiento vocal.
- Respetá el presupuesto tonal y de ganancia recibido; nunca repartas varios boosts para eludirlo.
- Incluí audio.loudness.normalize y audio.limiter.true_peak para la salida final.
- El orden de actions es el orden de procesamiento.
Respondé solo JSON válido, sin markdown."""

OUTPUT_SCHEMA = """{
  "audio_id": "ID recibido sin modificar",
  "diagnosis": "diagnóstico breve en español",
  "what_to_fix": ["problema concreto"],
  "what_to_keep": ["elemento que no debe alterarse"],
  "actions": [
    {
      "function_id": "audio.tone_eq.band",
      "enabled": true,
      "operation": "cut",
      "target": "low_mid",
      "params": {"frequency_hz": 350.0, "gain_db": -1.5, "q": 1.2, "filter_type": "peaking"},
      "evidence": {"measured_excess_db": 2.1, "band_rms_db": -13.9},
      "reason": "Acumulación entre 250 y 500 Hz",
      "confidence": 0.85
    }
  ],
  "notes": ["decisión adicional"]
}"""


def _catalog_for_prompt() -> str:
    return json.dumps(function_registry.to_dict(), ensure_ascii=False, separators=(",", ":"))


def build_analysis_prompt(pre_stats: Dict[str, float], band_stats: Dict[str, float],
                          band_peaks: Dict[str, float], style: str,
                          target_lufs: float = -15.5, true_peak: float = -1.5,
                          voice_rms: Optional[float] = None,
                          stereo_width: float = 0.5, stereo_category: str = "Normal",
                          has_clipping: bool = False, noise_floor_db: float = -60,
                          audio_id: str = "unknown",
                          dynamic_eq_evidence: Dict[str, Any] | None = None) -> str:
    """Construye el prompt completo con todas las métricas del track."""

    bands = ["Subbass (20-60 Hz)", "Bass (60-250 Hz)", "Low-Mid (250-500 Hz)",
             "Mid (500-2k Hz)", "High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"]

    ideal_rms = {"Subbass (20-60 Hz)": -18, "Bass (60-250 Hz)": -14,
                 "Low-Mid (250-500 Hz)": -16, "Mid (500-2k Hz)": -15,
                 "High-Mid (2k-6k Hz)": -16, "Air (6k-16k Hz)": -18}
    ideal_peak = {"Subbass (20-60 Hz)": -3, "Bass (60-250 Hz)": -2,
                  "Low-Mid (250-500 Hz)": -2.5, "Mid (500-2k Hz)": -2.5,
                  "High-Mid (2k-6k Hz)": -3, "Air (6k-16k Hz)": -4}

    lines = [
        "=== ANÁLISIS COMPLETO DEL TRACK ===",
        f"Audio ID: {audio_id}",
        f"Estilo: {style}",
        f"LUFS integrado: {pre_stats.get('input_i', -35):.1f} LUFS",
        f"True Peak: {pre_stats.get('input_tp', -25):.1f} dBTP",
        f"LRA (rango dinámico): {pre_stats.get('input_lra', 7):.1f} LU",
        f"Crest factor: {pre_stats.get('crest_factor', 10):.1f} dB",
        f"Piso de ruido: {noise_floor_db:.1f} dB",
        f"Tiene clipping: {'sí' if has_clipping else 'no'}",
        f"Voz detectada: {'sí' if voice_rms and voice_rms > -30 else 'no'}",
        f"Ancho stereo: {stereo_width:.2f} ({stereo_category})",
        f"Target LUFS: {target_lufs}",
        f"Target True Peak: {true_peak} dBTP",
        "",
        "=== ANÁLISIS POR BANDA (RMS / Peak / Crest / Ideal RMS / Gap) ===",
    ]
    for band in bands:
        rms = band_stats.get(band, -70)
        peak = band_peaks.get(band, -70)
        crest = peak - rms if rms > -70 and peak > -70 else 0
        ideal = ideal_rms.get(band, -16)
        gap = rms - ideal
        lines.append(f"  {band}: RMS={rms:.1f}  Peak={peak:.1f}  Crest={crest:.1f}  Ideal={ideal}  Gap={gap:+.1f}")

    lines += [
        "",
        "=== EVIDENCIA PARA EQ DINÁMICA ===",
        json.dumps(dynamic_eq_evidence or {
            "resonance_candidates": [],
            "note": "Sin evidencia: no selecciones audio.dynamic_eq.resonance ni scope Mid/Side",
        }, ensure_ascii=False, separators=(",", ":")),
        "Los plugins audio.vocal.* sólo pueden usarse con vocal_center_confidence>=0.65 y mid_side_ratio>=0.60. ",
        "El supresor debe coincidir con un resonance_candidate local entre 1.8 y 8 kHz. ",
        "El naturalizador exige déficits/excesos medidos; no inventes una voz ni uses vibrato.",
        "Para audio.transient.*, audio.stereo.*, audio.low_end.* y audio.spectral.* copiá la métrica local ",
        "correspondiente en evidence. Nunca expandas estéreo con correlación <0.70 ni realces graves/agudos sin déficit.",
        "",
        "=== PLUGINS DISPONIBLES Y SUS PARÁMETROS ===",
        _catalog_for_prompt(),
        "",
        "=== PRESUPUESTOS MÁXIMOS DE LA CADENA (dB) ===",
        json.dumps(DEFAULT_BUDGET_POLICY, ensure_ascii=False, separators=(",", ":")),
        "",
        "=== FORMato de RESPUESTA REQUERIDO ===",
        "Respondé EXACTAMENTE con este JSON, reemplazando los valores por tus decisiones:",
        OUTPUT_SCHEMA,
        "",
        "Solo el JSON, sin explicaciones ni markdown.",
    ]
    return "\n".join(lines)


def parse_mastering_response(response: str) -> Optional[Dict[str, Any]]:
    """Parsea la respuesta JSON de la IA."""
    try:
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, Exception):
        return None


def validate_mastering_strategy(
    strategy: Dict[str, Any], *, audio_id: str, target_lufs: float,
    true_peak: float, pre_stats: Dict[str, float], source_fingerprint: str | None = None,
    dynamic_eq_evidence: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Valida acciones de IA, aplica guardrails y produce trazabilidad completa."""
    target_lufs = max(-70.0, min(-5.0, float(target_lufs)))
    true_peak = max(-9.0, min(0.0, float(true_peak)))
    allowed = {"audio_id", "diagnosis", "what_to_fix", "what_to_keep", "actions", "notes"}
    unknown = set(strategy) - allowed
    if unknown:
        raise ContractError(f"Campos desconocidos en estrategia IA: {sorted(unknown)}")
    if strategy.get("audio_id") != audio_id:
        raise ContractError("La IA devolvió un audio_id distinto al solicitado")
    raw_actions = strategy.get("actions")
    if not isinstance(raw_actions, list):
        raise ContractError("actions debe ser una lista")

    requested = []
    accepted: list[AudioFunctionAction] = []
    rejected = []
    neutral_decisions = []
    lra = float(pre_stats.get("input_lra", 7.0))
    crest = float(pre_stats.get("crest_factor", 10.0))
    already_compressed = lra <= 4.5 or crest <= 8.5
    density_functions = {
        "audio.glue.bus_compressor", "audio.multiband.compressor",
        "audio.multiband.saturation", "audio.saturation.softclip",
    }
    band_frequency_ranges = {
        "sub_bass": (20.0, 60.0), "bass": (60.0, 250.0),
        "low_mid": (250.0, 500.0), "mid": (500.0, 2000.0),
        "high_mid": (2000.0, 6000.0), "air": (6000.0, 20000.0),
    }

    def authoritative_output_evidence(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Aplana evidencia del proveedor y no permite que invente LUFS/TP de entrada."""
        clean = dict(raw)
        nested = clean.pop("loudness_stats", None)
        if isinstance(nested, dict):
            for key, value in nested.items():
                if isinstance(value, (str, int, float, bool)) and value is not None:
                    clean[f"provider_{key}"] = value
        function_id = str(clean.pop("__function_id", ""))
        if function_id in {"audio.loudness.normalize", "audio.limiter.true_peak"}:
            local_lufs = pre_stats.get("input_i", pre_stats.get("output_i"))
            local_tp = pre_stats.get("input_tp", pre_stats.get("output_tp"))
            if isinstance(local_lufs, (int, float)):
                clean["measured_input_lufs"] = float(local_lufs)
            if isinstance(local_tp, (int, float)):
                clean["measured_input_true_peak_db"] = float(local_tp)
            clean["measurement_source"] = "local_ffmpeg"
        return clean

    for raw in raw_actions:
        requested.append(raw)
        try:
            if not isinstance(raw, dict):
                raise ContractError("Cada acción debe ser un objeto")
            if not str(raw.get("reason", "")).strip():
                raise ContractError("reason es obligatorio")
            if raw.get("confidence") is None:
                raise ContractError("confidence es obligatorio")
            if not str(raw.get("operation", "")).strip():
                raise ContractError("operation es obligatorio")
            evidence = raw.get("evidence")
            if not isinstance(evidence, dict) or not evidence:
                raise ContractError("evidence medible es obligatoria")
            canonical_raw = dict(raw)
            canonical_raw["evidence"] = authoritative_output_evidence({**evidence, "__function_id": raw.get("function_id")})
            action = function_registry.validate(AudioFunctionAction.from_dict(canonical_raw))
            if not action.enabled:
                raise ContractError("La IA no debe enviar acciones deshabilitadas; debe omitirlas")
            if action.operation == "neutral":
                neutral_decisions.append(action.to_dict())
                continue
            if action.function_id.startswith("audio.dynamic_eq."):
                low_hz, high_hz = band_frequency_ranges[str(action.target)]
                frequency_hz = float(action.params.get("frequency_hz", 0.0))
                if not low_hz <= frequency_hz <= high_hz:
                    raise ContractError(
                        f"frequency_hz={frequency_hz} fuera de target={action.target} ({low_hz}-{high_hz} Hz)"
                    )
                if action.function_id == "audio.dynamic_eq.resonance":
                    try:
                        measured_frequency = float(action.evidence["resonance_frequency_hz"])
                    except (KeyError, TypeError, ValueError):
                        raise ContractError(
                            "audio.dynamic_eq.resonance requiere evidence.resonance_frequency_hz"
                        )
                    tolerance_hz = max(100.0, frequency_hz * 0.10)
                    if abs(measured_frequency - frequency_hz) > tolerance_hz:
                        raise ContractError("frequency_hz no coincide con la resonancia medida")
                    candidates = list((dynamic_eq_evidence or {}).get("resonance_candidates", []))
                    authoritative = next((
                        item for item in candidates
                        if isinstance(item, dict)
                        and str(item.get("target")) == str(action.target)
                        and abs(float(item.get("frequency_hz", -1.0)) - frequency_hz) <= tolerance_hz
                    ), None)
                    if authoritative is None:
                        raise ContractError("La resonancia no aparece en el análisis espectral local")
                    local_excess = float(authoritative.get("measured_excess_db", 0.0))
                    claimed_excess = float(action.evidence.get("measured_excess_db", 0.0))
                    if abs(local_excess - claimed_excess) > 0.75:
                        raise ContractError("measured_excess_db no coincide con el análisis local")
                scope = str(action.params.get("scope", "stereo"))
                if scope in {"mid", "side"}:
                    try:
                        mid_side_ratio = float(action.evidence["mid_side_ratio"])
                    except (KeyError, TypeError, ValueError):
                        raise ContractError("scope Mid/Side requiere evidence.mid_side_ratio")
                    if not 0.0 <= mid_side_ratio <= 1.0:
                        raise ContractError("evidence.mid_side_ratio debe estar entre 0 y 1")
                    try:
                        local_mid_side_ratio = float((dynamic_eq_evidence or {})["mid_side_ratio"])
                    except (KeyError, TypeError, ValueError):
                        raise ContractError("No existe medición local Mid/Side para autorizar scope")
                    if abs(local_mid_side_ratio - mid_side_ratio) > 0.05:
                        raise ContractError("evidence.mid_side_ratio no coincide con el análisis local")
                    if scope == "mid" and mid_side_ratio < 0.60:
                        raise ContractError("scope=mid requiere predominio central medido")
                    if scope == "side" and mid_side_ratio > 0.40:
                        raise ContractError("scope=side requiere predominio lateral medido")
            if action.function_id.startswith("audio.vocal."):
                local = dynamic_eq_evidence or {}
                local_ratio = float(local.get("mid_side_ratio", 0.0))
                local_confidence = float(local.get("vocal_center_confidence", 0.0))
                claimed_ratio = float(action.evidence.get("mid_side_ratio", -1.0))
                claimed_confidence = float(action.evidence.get("vocal_center_confidence", -1.0))
                if local_ratio < 0.60 or local_confidence < 0.65:
                    raise ContractError("Procesamiento vocal requiere presencia central confiable")
                if abs(claimed_ratio - local_ratio) > 0.05 or abs(claimed_confidence - local_confidence) > 0.05:
                    raise ContractError("La evidencia vocal no coincide con el análisis local")
                if action.function_id == "audio.vocal.resonance_suppressor":
                    frequency = float(action.params.get("frequency_hz", 0.0))
                    measured = float(action.evidence.get("resonance_frequency_hz", 0.0))
                    tolerance = max(100.0, frequency * 0.10)
                    candidate = next((item for item in local.get("resonance_candidates", [])
                                      if 1800.0 <= float(item.get("frequency_hz", 0.0)) <= 8000.0
                                      and abs(float(item.get("frequency_hz", 0.0)) - frequency) <= tolerance), None)
                    if candidate is None or abs(measured - frequency) > tolerance:
                        raise ContractError("Resonancia vocal no confirmada por el análisis local")
                    if abs(float(candidate.get("measured_excess_db", 0.0))
                           - float(action.evidence.get("measured_excess_db", 0.0))) > 0.75:
                        raise ContractError("Exceso vocal declarado no coincide con el análisis local")
                else:
                    body = float(action.params.get("body_gain_db", 0.0))
                    harsh = float(action.params.get("harshness_reduction_db", 0.0))
                    air = float(action.params.get("air_reduction_db", 0.0))
                    if body + harsh + air <= 0.0:
                        raise ContractError("Naturalizador vocal requiere al menos una corrección")
                    if body > 0.0 and float(action.evidence.get("measured_body_deficit_db", 0.0)) <= 0.0:
                        raise ContractError("Recuperar cuerpo requiere measured_body_deficit_db")
                    if harsh > 0.0 and float(action.evidence.get("measured_harshness_excess_db", 0.0)) <= 0.0:
                        raise ContractError("Reducir dureza requiere measured_harshness_excess_db")
                    if air > 0.0 and float(action.evidence.get("measured_air_excess_db", 0.0)) <= 0.0:
                        raise ContractError("Suavizar aire requiere measured_air_excess_db")
            if action.function_id in {
                "audio.transient.dynamic_control", "audio.stereo.correlation_guard",
                "audio.low_end.dynamic_balance", "audio.spectral.deharsh",
                "audio.spectral.dullness_recovery",
            }:
                local = dynamic_eq_evidence or {}
                evidence_keys = {
                    "audio.transient.dynamic_control": "transient_crest_db",
                    "audio.stereo.correlation_guard": "stereo_correlation",
                    "audio.low_end.dynamic_balance": "low_end_level_db",
                    "audio.spectral.deharsh": "harshness_excess_db",
                    "audio.spectral.dullness_recovery": "dullness_deficit_db",
                }
                metric = evidence_keys[action.function_id]
                if metric not in local or metric not in action.evidence:
                    raise ContractError(f"{action.function_id} requiere evidencia local {metric}")
                tolerance = 0.05 if metric == "stereo_correlation" else 0.75
                if abs(float(local[metric]) - float(action.evidence[metric])) > tolerance:
                    raise ContractError(f"evidence.{metric} no coincide con el análisis local")
                if action.function_id == "audio.stereo.correlation_guard":
                    width = float(action.params.get("width", 1.0)); correlation = float(local[metric])
                    if width > 1.0 and correlation < 0.70:
                        raise ContractError("Expandir estéreo requiere correlación local >= 0.70")
                    if width < 1.0 and correlation >= 0.0:
                        raise ContractError("Estrechar estéreo requiere correlación local negativa")
                if action.function_id == "audio.low_end.dynamic_balance":
                    ratio = float(local.get("low_end_mid_ratio", -1.0))
                    claimed = float(action.evidence.get("low_end_mid_ratio", -2.0))
                    if not 0.0 <= ratio <= 1.0 or abs(ratio - claimed) > 0.05:
                        raise ContractError("low_end_mid_ratio no coincide con el análisis local")
                if action.function_id == "audio.spectral.deharsh" and float(local[metric]) <= 0.0:
                    raise ContractError("De-harsh requiere dureza medida positiva")
                if action.function_id == "audio.spectral.dullness_recovery" and float(local[metric]) <= 0.0:
                    raise ContractError("Recuperar claridad requiere déficit medido positivo")
            if already_compressed and action.function_id in density_functions:
                raise ContractError(
                    f"Guardrail: material ya comprimido (LRA={lra:.1f}, crest={crest:.1f})"
                )
            if (action.function_id == "audio.multiband.stereo_width"
                    and action.target == "sub_bass"
                    and float(action.params.get("width", 1.0)) > 1.0):
                raise ContractError("Guardrail: sub_bass no puede ensancharse por encima de 1.0")
            # Validar conflictos contra lo ya aceptado; la acción posterior se rechaza.
            function_registry.validate_plan([*accepted, action])
            prospective_budget = evaluate_action_budgets([*accepted, action])
            if prospective_budget["violations"]:
                violation = prospective_budget["violations"][-1]
                raise ContractError(
                    f"{violation['governor_id']}: {violation['error']}"
                )
            accepted.append(action)
        except (ContractError, TypeError, ValueError) as exc:
            rejected.append({"action": raw, "error": str(exc)})

    injected: list[AudioFunctionAction] = []
    normalize = next((a for a in accepted if a.function_id == "audio.loudness.normalize"), None)
    if normalize is None:
        normalize = AudioFunctionAction(
            "audio.loudness.normalize",
            params={"target_lufs": target_lufs, "true_peak_db": true_peak, "lra": 11.0, "dual_mono": False},
            reason="Guardrail obligatorio de loudness", confidence=1.0,
            operation="protect", evidence={"target_lufs": target_lufs, "target_true_peak_db": true_peak},
        )
        accepted.append(normalize)
        injected.append(normalize)
    else:
        params = dict(normalize.params)
        params.update({"target_lufs": target_lufs, "true_peak_db": true_peak})
        replacement = AudioFunctionAction(
            normalize.function_id, normalize.enabled, params, normalize.target,
            normalize.reason, normalize.confidence, normalize.operation, normalize.evidence,
        )
        accepted[accepted.index(normalize)] = function_registry.validate(replacement)
        normalize = replacement

    limiter = next((a for a in accepted if a.function_id == "audio.limiter.true_peak"), None)
    if limiter is None:
        limiter = AudioFunctionAction(
            "audio.limiter.true_peak",
            params={"ceiling_db": true_peak, "release_ms": 150.0, "lookahead_ms": 5.0,
                    "mode": "transparent", "oversampling": 4},
            reason="Guardrail obligatorio de True Peak", confidence=1.0,
            operation="protect", evidence={"ceiling_db": true_peak},
        )
        accepted.append(limiter)
        injected.append(limiter)
    else:
        params = dict(limiter.params)
        params["ceiling_db"] = min(float(params.get("ceiling_db", true_peak)), true_peak)
        replacement = AudioFunctionAction(
            limiter.function_id, limiter.enabled, params, limiter.target,
            limiter.reason, limiter.confidence, limiter.operation, limiter.evidence,
        )
        accepted[accepted.index(limiter)] = function_registry.validate(replacement)
        limiter = replacement

    # La salida siempre termina en normalización y limitador, aunque la IA los haya
    # colocado antes. Así el orden persistido coincide con el grafo realmente ejecutado.
    output_ids = {"audio.loudness.normalize", "audio.limiter.true_peak"}
    accepted = [action for action in accepted if action.function_id not in output_ids]
    accepted.extend([normalize, limiter])
    accepted = effective_execution_actions(accepted)
    budget_report = evaluate_action_budgets(accepted)

    normalized = dict(strategy)
    normalized["actions"] = [action.to_dict() for action in accepted]
    normalized["decision_trace"] = {
        "audio_id": audio_id,
        "catalog_fingerprint": catalog_fingerprint(),
        "source_fingerprint": source_fingerprint,
        "requested_actions": requested,
        "validated_actions": [action.to_dict() for action in accepted],
        "rejected_actions": rejected,
        "neutral_decisions": neutral_decisions,
        "injected_guardrails": [action.to_dict() for action in injected],
        "effective_order": [action.function_id for action in accepted],
        "operation_summary": {
            operation: sum(1 for action in accepted if action.operation == operation)
            for operation in ("cut", "boost", "attenuate", "expand", "narrow", "protect")
        },
        "budget_report": budget_report,
        "dynamic_eq_evidence": dynamic_eq_evidence or {},
    }
    return normalized


def build_suno_classic_strategy(
    *, audio_id: str, target_lufs: float, true_peak: float,
    pre_stats: Dict[str, float], band_stats: Dict[str, float] | None = None,
    voice_rms: float | None = None, fallback_reason: str = "IA no disponible",
) -> Dict[str, Any]:
    """Fallback canónico: usa los mismos function_id, validación y traza que la IA."""
    bands = band_stats or {}
    actions: list[dict[str, Any]] = []

    def add(
        function_id: str, params: Dict[str, Any], reason: str,
        target: str | None = None, *, operation: str | None = None,
        evidence: Dict[str, Any] | None = None,
    ) -> None:
        item: dict[str, Any] = {
            "function_id": function_id, "enabled": True, "params": params,
            "operation": operation, "evidence": evidence or {"source": "suno_classic_rule"},
            "reason": reason, "confidence": 1.0,
        }
        if target:
            item["target"] = target
        actions.append(item)

    source_lufs = float(pre_stats.get("input_i", -24.0))
    add("audio.autogain.headroom", {"gain_db": -12.0 if source_lufs < -25.0 else -17.0},
        "SUNO Clásico: margen seguro antes del procesamiento", operation="protect",
        evidence={"source_lufs": source_lufs})
    if voice_rms is not None and float(voice_rms) > -30.0:
        add("audio.deesser.sibilance_reduction", {"frequency_hz": 6000.0, "intensity": 0.4},
            "SUNO Clásico: control vocal conservador", operation="attenuate",
            evidence={"voice_rms_db": float(voice_rms)})
    if float(bands.get("High-Mid (2k-6k Hz)", -70.0)) > -22.0:
        add("audio.multiband.eq", {"gain_db": -0.8},
            "SUNO Clásico: suavizar dureza en presencia", "high_mid", operation="cut",
            evidence={
                "band_rms_db": float(bands["High-Mid (2k-6k Hz)"]),
                "measured_excess_db": float(bands["High-Mid (2k-6k Hz)"]) - (-22.0),
            })
    if float(bands.get("Air (6k-16k Hz)", -70.0)) > -24.0:
        add("audio.multiband.eq", {"gain_db": -1.0},
            "SUNO Clásico: controlar aire metálico", "air", operation="cut",
            evidence={
                "band_rms_db": float(bands["Air (6k-16k Hz)"]),
                "measured_excess_db": float(bands["Air (6k-16k Hz)"]) - (-24.0),
            })
    for target, width in (
        ("sub_bass", 0.0), ("bass", 0.4), ("low_mid", 0.7),
        ("high_mid", 1.15), ("air", 1.25),
    ):
        add("audio.multiband.stereo_width", {"width": width},
            "SUNO Clásico: imagen estéreo segura por banda", target,
            operation="narrow" if width < 1.0 else "expand" if width > 1.0 else "neutral",
            evidence={"target_width": width, "policy": "suno_classic_stereo"})

    source_fingerprint = None
    try:
        source_path = pathlib.Path(audio_id)
        if source_path.is_file():
            source_fingerprint = fingerprint_audio_source(source_path)
    except (OSError, ValueError):
        pass
    strategy = validate_mastering_strategy(
        {
            "audio_id": audio_id,
            "diagnosis": "Fallback determinístico SUNO Clásico",
            "what_to_fix": [], "what_to_keep": ["dinámica y transientes"],
            "actions": actions,
            "notes": [fallback_reason],
        },
        audio_id=audio_id, target_lufs=target_lufs, true_peak=true_peak,
        pre_stats=pre_stats, source_fingerprint=source_fingerprint,
    )
    strategy["strategy_source"] = "fallback_suno_classic"
    strategy["fallback_preset"] = "SUNO Clásico"
    strategy["fallback_reason"] = fallback_reason
    return strategy


def get_mastering_strategy(
    band_stats: Dict[str, float],
    band_peaks: Dict[str, float],
    pre_stats: Dict[str, float],
    style: str = "SUNO",
    target_lufs: float = -15.5,
    true_peak: float = -1.5,
    providers: list | None = None,
    voice_rms: Optional[float] = None,
    stereo_width: float = 0.5,
    stereo_category: str = "Normal",
    has_clipping: bool = False,
    noise_floor_db: float = -60,
    past_examples: list | None = None,
    audio_id: str = "unknown",
) -> Optional[Dict[str, Any]]:
    """Intenta obtener estrategia de mastering completa por IA.
    Opcionalmente incluye ejemplos de estrategias pasadas exitosas para aprendizaje."""
    if not providers:
        return None

    source_fingerprint = None
    dynamic_eq_evidence: Dict[str, Any] = {}
    source_path = pathlib.Path(audio_id)
    try:
        if source_path.is_file():
            source_fingerprint = fingerprint_audio_source(source_path)
    except (OSError, ValueError):
        source_fingerprint = None
    try:
        if source_path.is_file():
            from spectrum_analyzer import analyze_dynamic_eq_evidence
            dynamic_eq_evidence = analyze_dynamic_eq_evidence(source_path)
    except Exception:
        dynamic_eq_evidence = {}

    prompt = build_analysis_prompt(
        pre_stats, band_stats, band_peaks, style, target_lufs, true_peak,
        voice_rms, stereo_width, stereo_category, has_clipping, noise_floor_db, audio_id,
        dynamic_eq_evidence,
    )
    # Inyectar ejemplos pasados si existen
    if past_examples:
        prompt += "\n\n=== EJEMPLOS DE ESTRATEGIAS EXITOSAS ANTERIORES ===\n"
        prompt += "Usá estos como referencia de lo que funcionó bien en tracks similares:\n\n"
        for i, ex in enumerate(past_examples[:3], 1):
            diag = ex.get("diagnosis", "")
            fixes = ex.get("what_to_fix", [])
            keeps = ex.get("what_to_keep", [])
            prompt += f"Ejemplo {i}: {diag}\n"
            if fixes:
                prompt += f"  Se corrigió: {', '.join(fixes)}\n"
            if keeps:
                prompt += f"  Se mantuvo: {', '.join(keeps)}\n"
            actions = ex.get("actions", [])
            action_ids = [
                item.get("function_id") for item in actions
                if isinstance(item, dict) and item.get("function_id")
            ]
            if action_ids:
                prompt += f"  Funciones verificadas: {', '.join(action_ids)}\n"
            prompt += "\n"

    result = call_ai_multi(providers, MASTERING_SYSTEM_PROMPT, prompt,
                           max_tokens=2500, temperature=0.3)

    if not result:
        raise ContractError("El proveedor IA no devolvió respuesta (tokens, cuota o conexión)")
    parsed = parse_mastering_response(result)
    if not parsed:
        raise ContractError("La respuesta IA no contiene JSON válido")
    return validate_mastering_strategy(
        parsed, audio_id=audio_id, target_lufs=target_lufs,
        true_peak=true_peak, pre_stats=pre_stats,
        source_fingerprint=source_fingerprint,
        dynamic_eq_evidence=dynamic_eq_evidence,
    )


def load_past_strategies(log_dir: str = "", max_age_days: int = 30, max_count: int = 5) -> list:
    """Carga estrategias pasadas exitosas de archivos .ai_master.json en el directorio de logs.
    Solo incluye las que tienen rating 'Bueno' o fueron aplicadas por IA."""
    import json as _json
    import os as _os
    import time as _time
    from pathlib import Path as _Path

    examples = []
    now = _time.time()
    cutoff = now - max_age_days * 86400

    search_dirs = []
    if log_dir:
        search_dirs.append(_Path(log_dir))
    # También buscar en directorios de salida comunes
    for base in [_Path.home() / "Disco2" / "TeraBoxDownload",
                 _Path("/home/martin/Disco2/TeraBoxDownload")]:
        if base.exists():
            for d in base.iterdir():
                if d.is_dir() and (d / "log").exists():
                    search_dirs.append(d / "log")

    for log_path in search_dirs:
        if not log_path.exists():
            continue
        try:
            for f in sorted(log_path.glob("*.ai_master.json"), reverse=True):
                if len(examples) >= max_count:
                    break
                try:
                    if _os.path.getmtime(str(f)) < cutoff:
                        continue
                    data = _json.loads(f.read_text(encoding="utf-8"))
                    if data.get("used_ai_strategy") and data.get("status") == "applied":
                        audit = data.get("decision_trace", {}).get("execution_audit")
                        if isinstance(audit, dict) and audit.get("status") != "passed":
                            continue
                        adj = data.get("adjustments", {})
                        if isinstance(adj, dict):
                            examples.append({
                                "diagnosis": adj.get("diagnostics", ""),
                                "what_to_fix": adj.get("suggestions", []),
                                "what_to_keep": [],
                                "actions": data.get("executed_actions", []),
                                "file": str(f),
                            })
                except Exception:
                    continue
        except Exception:
            continue

    return examples[:max_count]
