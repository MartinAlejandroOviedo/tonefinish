from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on", "si", "sí"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _env_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(low, min(high, value))


def get_rollout_flags() -> Dict[str, Any]:
    """
    Feature flags de rollout adaptativo (Fase 7).
    Defaults seguros:
    - adaptive_master_enabled: ON para análisis/guardia
    - adaptive_shadow_enabled: ON
    - adaptive_guard_strict: ON
    - adaptive_rollout_percent: 100 (render real disponible; la guardia sigue siendo obligatoria)
    """
    return {
        "adaptive_master_enabled": _env_bool("TONEFINISH_ADAPTIVE_MASTER_ENABLED", True),
        "adaptive_shadow_enabled": _env_bool("TONEFINISH_ADAPTIVE_SHADOW_ENABLED", True),
        "adaptive_guard_strict": _env_bool("TONEFINISH_ADAPTIVE_GUARD_STRICT", True),
        "adaptive_rollout_percent": _env_int("TONEFINISH_ADAPTIVE_ROLLOUT_PERCENT", 100, 0, 100),
    }


def build_adaptive_guard_report(
    *,
    target_lufs: float | None,
    true_peak_target: float | None,
    pre_stats: Dict[str, Any] | None,
    post_stats: Dict[str, Any] | None,
    mts_data: Dict[str, Any] | None,
    shadow_data: Dict[str, Any] | None,
    flags: Dict[str, bool],
) -> Dict[str, Any]:
    pre_stats = pre_stats or {}
    post_stats = post_stats or {}
    mts_data = mts_data or {}
    shadow_data = shadow_data or {}

    strict = bool(flags.get("adaptive_guard_strict", True))
    checks: list[Dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    # 1) LUFS post contra target
    if target_lufs is not None and post_stats:
        post_i = _f(post_stats.get("input_i"), 0.0)
        lufs_delta = abs(post_i - float(target_lufs))
        ok_lufs = lufs_delta <= (0.30 if strict else 0.45)
        checks.append(
            {"check": "lufs_match", "ok": ok_lufs, "value": round(post_i, 3), "delta": round(lufs_delta, 3)}
        )
        if not ok_lufs:
            blockers.append(f"LUFS fuera de tolerancia ({lufs_delta:.2f} LU).")
    else:
        warnings.append("No hay métricas suficientes de LUFS para validación completa.")

    # 2) True Peak post
    if true_peak_target is not None and post_stats:
        post_tp = _f(post_stats.get("input_tp"), -99.0)
        tp_limit = float(true_peak_target) + (0.10 if strict else 0.20)
        ok_tp = post_tp <= tp_limit
        checks.append(
            {"check": "true_peak_limit", "ok": ok_tp, "value": round(post_tp, 3), "limit": round(tp_limit, 3)}
        )
        if not ok_tp:
            blockers.append(f"True Peak sobre límite ({post_tp:.2f} dBTP > {tp_limit:.2f} dBTP).")
    else:
        warnings.append("No hay métricas de true peak para validación completa.")

    # 3) Riesgo de clipping/eventos críticos desde MTS
    event_counts = {}
    if isinstance(mts_data.get("summary"), dict):
        event_counts = mts_data["summary"].get("event_counts", {}) or {}
    peak_events = _i(event_counts.get("peak_risk", 0)) if isinstance(event_counts, dict) else 0
    source = mts_data.get("source", {}) if isinstance(mts_data.get("source"), dict) else {}
    duration_s = max(1.0, _f(source.get("duration_seconds"), 0.0))
    minutes = max(1.0 / 60.0, duration_s / 60.0)
    events = mts_data.get("events", []) if isinstance(mts_data.get("events"), list) else []
    sev_weight = {"low": 0.6, "medium": 1.0, "high": 2.0}
    weighted_peak_units = 0.0
    high_peak_units = 0.0
    for event in events:
        if not isinstance(event, dict) or str(event.get("type", "")) != "peak_risk":
            continue
        severity = str(event.get("severity", "medium")).lower()
        samples = max(1, _i(event.get("samples"), 1))
        weight = sev_weight.get(severity, 1.0)
        # Normaliza bursts largos para que la métrica represente eventos, no muestras crudas.
        burst_units = max(1.0, min(8.0, float(samples) / 2048.0))
        weighted_peak_units += weight * burst_units
        if severity == "high":
            high_peak_units += burst_units

    # Fallback cuando no hay lista de eventos detallada.
    if weighted_peak_units <= 0.0 and peak_events > 0:
        weighted_peak_units = float(peak_events)

    peak_risk_rate_per_min = weighted_peak_units / minutes
    peak_risk_rate_limit = 12.0 if strict else 16.0
    high_peak_limit = 8.0 if strict else 10.0
    ok_peak_events = (peak_risk_rate_per_min <= peak_risk_rate_limit) and (high_peak_units <= high_peak_limit)
    checks.append(
        {
            "check": "peak_risk_events",
            "ok": ok_peak_events,
            "value": peak_events,
            "rate_per_min": round(peak_risk_rate_per_min, 3),
            "rate_limit": peak_risk_rate_limit,
            "high_units": round(high_peak_units, 3),
            "high_limit": high_peak_limit,
        }
    )
    if not ok_peak_events:
        blockers.append(
            "Riesgo de picos elevado en MTS "
            f"(events={peak_events}, rate={peak_risk_rate_per_min:.2f}/min, high={high_peak_units})."
        )

    # 4) Drift estéreo: si no hay métrica explícita, advertir.
    stereo_drift = None
    if isinstance(shadow_data.get("context"), dict):
        stereo_drift = shadow_data["context"].get("stereo_drift")
    if stereo_drift is None:
        checks.append({"check": "stereo_drift", "ok": True, "value": "not_measured"})
        warnings.append("Drift estéreo no medido en esta fase (informativo).")
    else:
        drift_val = abs(_f(stereo_drift, 0.0))
        ok_drift = drift_val <= (0.08 if strict else 0.12)
        checks.append({"check": "stereo_drift", "ok": ok_drift, "value": round(drift_val, 4)})
        if not ok_drift:
            blockers.append(f"Drift estéreo elevado ({drift_val:.3f}).")

    shadow_ready = bool(
        shadow_data.get("mode") == "apply_candidate"
        and isinstance(shadow_data.get("summary"), dict)
        and shadow_data["summary"].get("apply_ready") is True
    )
    checks.append({"check": "shadow_apply_ready", "ok": shadow_ready,
                   "value": shadow_data.get("mode", "missing")})
    if not shadow_ready:
        blockers.append("Adaptive shadow no autorizó apply_candidate.")

    shadow_mode = not bool(flags.get("adaptive_master_enabled", False))
    overall_ok = len(blockers) == 0
    recommended_mode = "shadow_only"
    if overall_ok and not shadow_mode:
        recommended_mode = "apply_candidate"

    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "flags": flags,
        "shadow_mode_forced": shadow_mode,
        "overall_ok": overall_ok,
        "recommended_mode": recommended_mode,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
    }


def write_adaptive_guard_artifacts(
    *,
    output_path: pathlib.Path,
    target_lufs: float | None,
    true_peak_target: float | None,
    pre_stats: Dict[str, Any] | None,
    post_stats: Dict[str, Any] | None,
    mts_data: Dict[str, Any] | None,
    shadow_data: Dict[str, Any] | None,
    flags: Dict[str, bool],
) -> Dict[str, pathlib.Path]:
    report = build_adaptive_guard_report(
        target_lufs=target_lufs,
        true_peak_target=true_peak_target,
        pre_stats=pre_stats,
        post_stats=post_stats,
        mts_data=mts_data,
        shadow_data=shadow_data,
        flags=flags,
    )
    log_dir = output_path.parent / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    json_path = log_dir / f"{output_path.stem}.adaptive_guard.json"
    md_path = log_dir / f"{output_path.stem}.adaptive_guard.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# Adaptive Guard - {output_path.stem}",
        "",
        f"- Overall OK: {report.get('overall_ok')}",
        f"- Recommended mode: `{report.get('recommended_mode', 'shadow_only')}`",
        f"- Shadow forced: {report.get('shadow_mode_forced')}",
        "",
        "## Blockers",
    ]
    blockers = report.get("blockers", [])
    if isinstance(blockers, list) and blockers:
        for item in blockers:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Warnings")
    warnings = report.get("warnings", [])
    if isinstance(warnings, list) and warnings:
        for item in warnings:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append(f"JSON: `{json_path}`")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"json_path": json_path, "md_path": md_path}
