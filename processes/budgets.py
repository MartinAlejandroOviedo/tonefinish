"""Presupuestos conservadores para decisiones tonales y de ganancia de la IA."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import AudioFunctionAction, BAND_IDS


TONAL_GOVERNOR_ID = "audio.governor.tonal_budget"
GAIN_GOVERNOR_ID = "audio.governor.gain_budget"
OVERLAP_GOVERNOR_ID = "audio.governor.spectral_overlap"
HEADROOM_GOVERNOR_ID = "audio.governor.chain_headroom"

DEFAULT_BUDGET_POLICY = {
    "tonal_boost_individual_max_db": 2.0,
    "tonal_cut_individual_max_db": 3.0,
    "tonal_boost_total_max_db": 3.0,
    "tonal_cut_total_max_db": 6.0,
    "gain_boost_individual_max_db": 2.0,
    "gain_cut_individual_max_db": 3.0,
    "gain_boost_total_max_db": 3.0,
    "gain_cut_total_max_db": 6.0,
    "effective_band_boost_max_db": 2.5,
}

_TONAL_PARAM = {
    "audio.tone_eq.band": "gain_db",
    "audio.tone_eq.tilt": "gain_db",
    "audio.multiband.eq": "gain_db",
    "audio.dynamic_eq.motion": "gain_db",
    "audio.low_end.dynamic_balance": "gain_db",
}


def _gain_contribution(action: AudioFunctionAction) -> float | None:
    if action.function_id == "audio.autogain.output_gain":
        return float(action.params.get("gain_db", 0.0))
    if action.function_id in {"audio.glue.bus_compressor", "audio.multiband.compressor"}:
        return float(action.params.get("makeup_db", 0.0))
    return None


def _bucket(value: float) -> tuple[float, float]:
    return (max(0.0, value), max(0.0, -value))


def _evidence_positive(action: AudioFunctionAction, key: str) -> bool:
    try:
        return float(action.evidence.get(key, 0.0)) > 0.0
    except (TypeError, ValueError):
        return False


def _positive(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def estimate_effective_band_boosts(
    actions: Sequence[AudioFunctionAction],
) -> dict[str, Any]:
    """Estima el peor boost simultáneo de la cadena en cada banda.

    Los cortes no compensan boosts: un proceso dinámico puede no actuar en el
    mismo instante y dos filtros cercanos pueden solaparse parcialmente.
    """
    totals = {band: 0.0 for band in BAND_IDS}
    contributions: list[dict[str, Any]] = []

    def add(index: int, action: AudioFunctionAction, bands: Sequence[str], value: float, source: str) -> None:
        value = _positive(value)
        if value <= 1e-9:
            return
        valid_bands = tuple(band for band in bands if band in totals)
        for band in valid_bands:
            totals[band] += value
        contributions.append({
            "index": index, "function_id": action.function_id,
            "target": action.target, "bands": list(valid_bands),
            "estimated_boost_db": round(value, 3), "source": source,
        })

    all_bands = tuple(BAND_IDS)
    for index, action in enumerate(actions):
        if not action.enabled:
            continue
        fid, p = action.function_id, action.params
        target = (action.target,) if action.target in totals else all_bands

        if fid in {"audio.tone_eq.band", "audio.multiband.eq", "audio.dynamic_eq.motion",
                   "audio.low_end.dynamic_balance"}:
            add(index, action, target, p.get("gain_db", 0.0), "signed_gain")
        elif fid == "audio.tone_eq.tilt":
            gain = float(p.get("gain_db", 0.0))
            add(index, action, ("high_mid", "air") if gain > 0 else ("sub_bass", "bass"),
                abs(gain) / 2.0, "tilt_shelf")
        elif fid == "audio.spectral.dullness_recovery":
            add(index, action, ("high_mid", "air"), p.get("max_boost_db", 0.0), "dynamic_spectral")
        elif fid == "audio.transient.dynamic_control":
            add(index, action, target, p.get("amount_db", 0.0), "upward_dynamics")
        elif fid in {"audio.autogain.output_gain", "audio.glue.bus_compressor"}:
            key = "gain_db" if fid == "audio.autogain.output_gain" else "makeup_db"
            add(index, action, all_bands, p.get(key, 0.0), "global_gain")
        elif fid == "audio.multiband.compressor":
            add(index, action, target, p.get("makeup_db", 0.0), "band_makeup")
        elif fid in {"audio.multiband.saturation", "audio.saturation.softclip"}:
            # El drive se compensa dentro del plugin; se reserva margen para los
            # armónicos añadidos al mezclar la rama wet.
            drive = _positive(p.get("drive_db", 0.0))
            mix = min(1.0, _positive(p.get("mix", 0.0)))
            add(index, action, target, min(1.5, drive * mix * 0.10), "harmonic_energy")
        elif fid == "audio.saturation.exciter":
            amount = _positive(p.get("amount", 0.0))
            mix = min(1.0, _positive(p.get("mix", 0.0)))
            add(index, action, ("high_mid", "air"), min(1.5, amount * mix * 0.15), "exciter_energy")
        elif fid == "audio.vocal.center_naturalizer":
            add(index, action, ("low_mid", "mid"),
                _positive(p.get("body_gain_db", 0.0)) * min(1.0, _positive(p.get("mix", 0.0))),
                "vocal_body")
        elif fid in {"audio.multiband.stereo_width", "audio.stereo.correlation_guard"}:
            width = _positive(p.get("width", 1.0))
            if width > 1.0:
                # Side puede sumar en fase con Mid; 20log10(width) es una cota
                # conservadora del aumento de pico atribuible al ensanchado.
                import math
                add(index, action, target, 20.0 * math.log10(width), "stereo_peak")

    rounded = {band: round(value, 3) for band, value in totals.items()}
    worst_band = max(rounded, key=rounded.get)
    return {
        "effective_boost_by_band_db": rounded,
        "worst_band": worst_band,
        "worst_boost_db": rounded[worst_band],
        "contributions": contributions,
    }


def evaluate_action_budgets(
    actions: Sequence[AudioFunctionAction],
    policy: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Evalúa un plan completo; nunca altera ni cambia el signo de una acción."""
    limits = dict(DEFAULT_BUDGET_POLICY)
    if policy:
        limits.update({key: float(value) for key, value in policy.items() if key in limits})

    tonal_boost = tonal_cut = gain_boost = gain_cut = 0.0
    tonal_by_target: dict[str, dict[str, float]] = {}
    contributions: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []

    for index, action in enumerate(actions):
        tonal_param = _TONAL_PARAM.get(action.function_id)
        resonance_functions = {"audio.dynamic_eq.resonance", "audio.vocal.resonance_suppressor"}
        if action.function_id == "audio.spectral.deharsh":
            tonal_param = "__spectral_cut__"
        elif action.function_id == "audio.spectral.dullness_recovery":
            tonal_param = "__spectral_boost__"
        if tonal_param is not None or action.function_id in resonance_functions:
            value = (
                -float(action.params.get("max_reduction_db", 0.0))
                if action.function_id in resonance_functions
                else -float(action.params.get("max_reduction_db", 0.0)) if tonal_param == "__spectral_cut__"
                else float(action.params.get("max_boost_db", 0.0)) if tonal_param == "__spectral_boost__"
                else float(action.params.get(tonal_param, 0.0))
            )
            boost, cut = _bucket(value)
            tonal_boost += boost
            tonal_cut += cut
            scope = str(action.target or "global")
            scoped = tonal_by_target.setdefault(
                scope, {"boost_db": 0.0, "cut_db": 0.0, "actions": 0.0}
            )
            scoped["boost_db"] += boost
            scoped["cut_db"] += cut
            scoped["actions"] += 1.0
            contributions.append({
                "index": index, "function_id": action.function_id,
                "target": action.target, "budget": "tonal", "value_db": value,
            })
            if boost > limits["tonal_boost_individual_max_db"]:
                violations.append({"governor_id": TONAL_GOVERNOR_ID, "index": index,
                                   "error": "boost tonal individual excedido", "value_db": boost})
            if cut > limits["tonal_cut_individual_max_db"]:
                violations.append({"governor_id": TONAL_GOVERNOR_ID, "index": index,
                                   "error": "corte tonal individual excedido", "value_db": cut})
            if action.operation == "boost" and not _evidence_positive(action, "measured_deficit_db"):
                violations.append({"governor_id": TONAL_GOVERNOR_ID, "index": index,
                                   "error": "boost tonal requiere measured_deficit_db positivo"})
            if action.operation == "cut" and not _evidence_positive(action, "measured_excess_db"):
                violations.append({"governor_id": TONAL_GOVERNOR_ID, "index": index,
                                   "error": "corte tonal requiere measured_excess_db positivo"})

        if action.function_id == "audio.vocal.center_naturalizer":
            mix = float(action.params.get("mix", 0.0))
            boost = float(action.params.get("body_gain_db", 0.0)) * mix
            cut = (float(action.params.get("harshness_reduction_db", 0.0))
                   + float(action.params.get("air_reduction_db", 0.0))) * mix
            tonal_boost += boost
            tonal_cut += cut
            scoped = tonal_by_target.setdefault(
                "vocal_center", {"boost_db": 0.0, "cut_db": 0.0, "actions": 0.0})
            scoped["boost_db"] += boost; scoped["cut_db"] += cut; scoped["actions"] += 1.0
            contributions.append({"index": index, "function_id": action.function_id,
                                  "target": "vocal_center", "budget": "tonal",
                                  "boost_db": round(boost, 3), "cut_db": round(cut, 3)})

        gain_value = _gain_contribution(action)
        if gain_value is not None:
            boost, cut = _bucket(gain_value)
            gain_boost += boost
            gain_cut += cut
            contributions.append({
                "index": index, "function_id": action.function_id,
                "target": action.target, "budget": "gain", "value_db": gain_value,
            })
            if boost > limits["gain_boost_individual_max_db"]:
                violations.append({"governor_id": GAIN_GOVERNOR_ID, "index": index,
                                   "error": "boost de ganancia individual excedido", "value_db": boost})
            if cut > limits["gain_cut_individual_max_db"]:
                violations.append({"governor_id": GAIN_GOVERNOR_ID, "index": index,
                                   "error": "corte de ganancia individual excedido", "value_db": cut})
            if gain_value > 0.0 and not _evidence_positive(action, "compensation_required_db"):
                violations.append({"governor_id": GAIN_GOVERNOR_ID, "index": index,
                                   "error": "ganancia positiva requiere compensation_required_db positivo"})

    totals = {
        "tonal_boost_db": round(tonal_boost, 3), "tonal_cut_db": round(tonal_cut, 3),
        "gain_boost_db": round(gain_boost, 3), "gain_cut_db": round(gain_cut, 3),
    }
    for scope, values in tonal_by_target.items():
        if (values["actions"] > 1.0
                and values["boost_db"] > limits["tonal_boost_individual_max_db"] + 1e-9):
            violations.append({
                "governor_id": OVERLAP_GOVERNOR_ID,
                "error": "boosts tonales superpuestos en la misma banda",
                "target": scope, "value_db": round(values["boost_db"], 3),
                "limit_db": limits["tonal_boost_individual_max_db"],
            })
        if (values["actions"] > 1.0
                and values["cut_db"] > limits["tonal_cut_individual_max_db"] + 1e-9):
            violations.append({
                "governor_id": OVERLAP_GOVERNOR_ID,
                "error": "cortes tonales superpuestos en la misma banda",
                "target": scope, "value_db": round(values["cut_db"], 3),
                "limit_db": limits["tonal_cut_individual_max_db"],
            })
    for name, used, limit_key, governor in (
        ("boost tonal acumulado", tonal_boost, "tonal_boost_total_max_db", TONAL_GOVERNOR_ID),
        ("corte tonal acumulado", tonal_cut, "tonal_cut_total_max_db", TONAL_GOVERNOR_ID),
        ("boost de ganancia acumulado", gain_boost, "gain_boost_total_max_db", GAIN_GOVERNOR_ID),
        ("corte de ganancia acumulado", gain_cut, "gain_cut_total_max_db", GAIN_GOVERNOR_ID),
    ):
        if used > limits[limit_key] + 1e-9:
            violations.append({"governor_id": governor, "error": f"{name} excedido",
                               "value_db": round(used, 3), "limit_db": limits[limit_key]})

    headroom = estimate_effective_band_boosts(actions)
    for band, used in headroom["effective_boost_by_band_db"].items():
        if used > limits["effective_band_boost_max_db"] + 1e-9:
            violations.append({
                "governor_id": HEADROOM_GOVERNOR_ID,
                "error": "boost efectivo acumulado excede el headroom de banda",
                "target": band, "value_db": used,
                "limit_db": limits["effective_band_boost_max_db"],
            })

    remaining = {
        "tonal_boost_db": round(max(0.0, limits["tonal_boost_total_max_db"] - tonal_boost), 3),
        "tonal_cut_db": round(max(0.0, limits["tonal_cut_total_max_db"] - tonal_cut), 3),
        "gain_boost_db": round(max(0.0, limits["gain_boost_total_max_db"] - gain_boost), 3),
        "gain_cut_db": round(max(0.0, limits["gain_cut_total_max_db"] - gain_cut), 3),
    }
    return {
        "status": "passed" if not violations else "rejected",
        "governors": [TONAL_GOVERNOR_ID, GAIN_GOVERNOR_ID, OVERLAP_GOVERNOR_ID,
                      HEADROOM_GOVERNOR_ID],
        "policy": limits, "totals": totals, "remaining": remaining,
        "tonal_by_target": {
            key: {name: round(value, 3) for name, value in values.items()}
            for key, values in tonal_by_target.items()
        },
        "contributions": contributions, "headroom_report": headroom,
        "violations": violations,
    }
