from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_adaptive_shadow_report(
    decisions_data: Dict[str, Any],
    context: Dict[str, Any] | None = None,
    force_shadow_mode: bool = False,
) -> Dict[str, Any]:
    sections: List[Dict[str, Any]] = list(decisions_data.get("section_decisions") or [])
    context = context or {}

    eq_peak = 0.0
    sat_peak_dev = 0.0
    motion_peak_dev = 0.0
    tp_margin_min = 0.0
    sections_high_risk = 0
    checks: List[Dict[str, Any]] = []
    recommendations: List[str] = []

    for sec in sections:
        actions = sec.get("actions") or {}
        eq_db = actions.get("eq_db") or {}
        eq_abs_max = max((abs(_f(v, 0.0)) for v in eq_db.values()), default=0.0)
        sat_mult = _f(actions.get("saturation_mix_mult"), 1.0)
        motion_mult = _f(actions.get("stereo_motion_amount_mult"), 1.0)
        tp_margin = _f(actions.get("limiter_tp_margin_db"), 0.0)
        confidence = _f(sec.get("confidence"), 0.5)

        eq_peak = max(eq_peak, eq_abs_max)
        sat_peak_dev = max(sat_peak_dev, abs(sat_mult - 1.0))
        motion_peak_dev = max(motion_peak_dev, abs(motion_mult - 1.0))
        tp_margin_min = min(tp_margin_min, tp_margin)

        section_risk = 0.0
        if eq_abs_max > 0.45:
            section_risk += 0.35
        if abs(sat_mult - 1.0) > 0.12:
            section_risk += 0.25
        if abs(motion_mult - 1.0) > 0.12:
            section_risk += 0.20
        if tp_margin < -0.20:
            section_risk += 0.25
        if confidence < 0.55:
            section_risk += 0.15

        section_risk = _clamp(section_risk, 0.0, 1.0)
        if section_risk >= 0.55:
            sections_high_risk += 1

        checks.append(
            {
                "section_id": sec.get("section_id"),
                "label": sec.get("label", "section"),
                "risk": round(section_risk, 3),
                "eq_abs_max_db": round(eq_abs_max, 3),
                "sat_dev": round(abs(sat_mult - 1.0), 3),
                "motion_dev": round(abs(motion_mult - 1.0), 3),
                "tp_margin_db": round(tp_margin, 3),
            }
        )

    total_sections = max(1, len(sections))
    global_risk = (
        0.30 * _clamp(eq_peak / 0.6, 0.0, 1.0)
        + 0.22 * _clamp(sat_peak_dev / 0.16, 0.0, 1.0)
        + 0.20 * _clamp(motion_peak_dev / 0.16, 0.0, 1.0)
        + 0.12 * _clamp(abs(tp_margin_min) / 0.25, 0.0, 1.0)
        + 0.16 * _clamp(sections_high_risk / total_sections, 0.0, 1.0)
    )
    global_risk = _clamp(global_risk, 0.0, 1.0)

    # El render efectivo limita EQ a ±0.8 dB y luego pasa por guardia LUFS/TP.
    # 0.60 evita bloquear perfiles normales que el render ya recorta de forma segura.
    apply_ready = global_risk <= 0.60 and sections_high_risk <= max(1, int(0.35 * total_sections))

    if eq_peak > 0.5:
        recommendations.append("Reducir max_eq_step_db para transición más suave en tramos agresivos.")
    if sat_peak_dev > 0.12:
        recommendations.append("Limitar saturation_mix_mult en secciones pico para evitar fatiga.")
    if motion_peak_dev > 0.12:
        recommendations.append("Aplicar smoothing temporal extra en stereo_motion_amount_mult.")
    if tp_margin_min < -0.18:
        recommendations.append("Reforzar margen de true peak en secciones con peak_risk.")
    if not recommendations:
        recommendations.append("Perfil adaptativo estable; apto para modo apply con guardrails actuales.")

    mode = "shadow_only" if force_shadow_mode else ("apply_candidate" if apply_ready else "shadow_only")
    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "summary": {
            "sections": len(sections),
            "global_risk": round(global_risk, 3),
            "sections_high_risk": sections_high_risk,
            "eq_peak_db": round(eq_peak, 3),
            "sat_peak_dev": round(sat_peak_dev, 3),
            "motion_peak_dev": round(motion_peak_dev, 3),
            "tp_margin_min_db": round(tp_margin_min, 3),
            "apply_ready": apply_ready,
        },
        "checks": checks,
        "recommendations": recommendations,
        "context": {
            "dynamic_eq": bool(context.get("dynamic_eq", False)),
            "deesser_enabled": bool(context.get("deesser_enabled", False)),
            "stereo_dynamic_enabled": bool(context.get("stereo_dynamic_enabled", False)),
        },
    }


def write_adaptive_shadow_artifacts(
    output_path: pathlib.Path,
    decisions_data: Dict[str, Any],
    context: Dict[str, Any] | None = None,
    force_shadow_mode: bool = False,
) -> Dict[str, pathlib.Path]:
    report = build_adaptive_shadow_report(
        decisions_data=decisions_data,
        context=context,
        force_shadow_mode=force_shadow_mode,
    )
    log_dir = output_path.parent / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    json_path = log_dir / f"{output_path.stem}.adaptive_shadow.json"
    md_path = log_dir / f"{output_path.stem}.adaptive_shadow.md"

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    summary = report.get("summary", {})
    lines = [
        f"# Adaptive Shadow - {output_path.stem}",
        "",
        f"- Mode: `{report.get('mode', 'shadow_only')}`",
        f"- Global risk: {summary.get('global_risk', 0)}",
        f"- Apply ready: {summary.get('apply_ready', False)}",
        f"- Sections: {summary.get('sections', 0)}",
        f"- High risk sections: {summary.get('sections_high_risk', 0)}",
        "",
        "## Recommendations",
    ]
    recs = report.get("recommendations", [])
    if isinstance(recs, list) and recs:
        for rec in recs:
            lines.append(f"- {rec}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append(f"JSON: `{json_path}`")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"json_path": json_path, "md_path": md_path}
