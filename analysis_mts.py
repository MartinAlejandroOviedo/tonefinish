from __future__ import annotations

import json
import hashlib
import math
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, List

from adaptive_rollout_safety import (
    get_rollout_flags,
    write_adaptive_guard_artifacts,
)
from audio_tools import get_audio_duration, get_audio_mono_samples
from adaptive_master_shadow import write_adaptive_shadow_artifacts
from adaptive_master_renderer import discard_adaptive_candidate, render_adaptive_candidate, publish_adaptive_candidate
from config import BAND_CONFIG
from event_detection import detect_events_from_timeline
from master_decision_engine import write_master_decisions_artifacts
from section_detection import detect_sections_from_timeline

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except Exception:
    np = None  # type: ignore
    NUMPY_AVAILABLE = False


def _to_db(value: float, floor: float = -120.0) -> float:
    if value <= 1e-12:
        return floor
    return max(floor, 20.0 * math.log10(value))


def _safe_name(label: str) -> str:
    return (
        label.lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("/", "_")
    )


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _round_opt(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _build_band_overlap_risk(validation_context: Dict[str, Any]) -> Dict[str, Any]:
    bands = [
        "Subbass (20-60 Hz)",
        "Bass (60-250 Hz)",
        "Low-Mid (250-500 Hz)",
        "Mid (500-2k Hz)",
        "High-Mid (2k-6k Hz)",
        "Air (6k-16k Hz)",
    ]
    score_by_band = {b: 0.0 for b in bands}
    contributors: Dict[str, list[str]] = {b: [] for b in bands}

    def add(band: str, amount: float, source: str) -> None:
        if band not in score_by_band:
            return
        score_by_band[band] += float(amount)
        contributors[band].append(source)

    if bool(validation_context.get("dynamic_eq", False)):
        for b in bands:
            add(b, 0.8, "dynamic_eq")

    if bool(validation_context.get("deesser_enabled", False)):
        add("High-Mid (2k-6k Hz)", 0.8, "deesser")
        add("Air (6k-16k Hz)", 0.8, "deesser")

    if bool(validation_context.get("stereo_dynamic_enabled", False)):
        stereo_mix = _as_float(validation_context.get("stereo_dynamic_mix")) or 0.4
        per_band_mix = validation_context.get("stereo_dynamic_band_mix") if isinstance(validation_context.get("stereo_dynamic_band_mix"), dict) else {}
        for b in bands:
            mix_val = _as_float(per_band_mix.get(b)) if isinstance(per_band_mix, dict) else None
            add(b, max(0.2, float(mix_val if mix_val is not None else stereo_mix)), "stereo_dynamic")

    if bool(validation_context.get("multiband_limiter_enabled", False)):
        thresholds = validation_context.get("multiband_limiter_thresholds") if isinstance(validation_context.get("multiband_limiter_thresholds"), dict) else {}
        if thresholds:
            for b, thr in thresholds.items():
                thr_f = _as_float(thr)
                if thr_f is None:
                    continue
                add(b, 0.9 if thr_f > -2.0 else 0.6, "multiband_limiter")
        else:
            for b in bands:
                add(b, 0.6, "multiband_limiter")

    if bool(validation_context.get("saturation_enabled", False)):
        sat_mix = (_as_float(validation_context.get("saturation_mix")) or 0.0) / 100.0
        sat_drive = _as_float(validation_context.get("saturation_drive_db")) or 0.0
        sat_amount = max(0.0, sat_mix * (1.0 + abs(sat_drive) / 6.0))
        if bool(validation_context.get("saturation_per_band", False)):
            band_mix = validation_context.get("saturation_band_mix") if isinstance(validation_context.get("saturation_band_mix"), dict) else {}
            band_drive = validation_context.get("saturation_band_drive_db") if isinstance(validation_context.get("saturation_band_drive_db"), dict) else {}
            for b in bands:
                bm = (_as_float(band_mix.get(b)) or 0.0) / 100.0
                bd = _as_float(band_drive.get(b)) or 0.0
                amount = max(0.0, bm * (1.0 + abs(bd) / 6.0))
                if amount > 0.0:
                    add(b, amount, "saturation_band")
        elif sat_amount > 0.0:
            for b in bands:
                add(b, sat_amount, "saturation_global")

    max_band = max(score_by_band.items(), key=lambda kv: kv[1])
    risky_bands = {b: round(v, 3) for b, v in score_by_band.items() if v >= 2.0}
    return {
        "score_by_band": {b: round(v, 3) for b, v in score_by_band.items()},
        "contributors_by_band": contributors,
        "max_band": {"band": max_band[0], "score": round(max_band[1], 3)},
        "risky_bands": risky_bands,
        "overlap_ok": len(risky_bands) == 0,
    }


def _build_master_validation_report(
    *,
    output_path: pathlib.Path,
    validation_context: Dict[str, Any],
    mts_data: Dict[str, Any],
) -> Dict[str, Any]:
    target_lufs = _as_float(validation_context.get("target_lufs"))
    target_tp = _as_float(validation_context.get("true_peak_target"))
    pre_stats = validation_context.get("pre_stats") if isinstance(validation_context.get("pre_stats"), dict) else {}
    post_stats = validation_context.get("post_stats") if isinstance(validation_context.get("post_stats"), dict) else {}

    in_lufs = _as_float(pre_stats.get("input_i"))
    in_tp = _as_float(pre_stats.get("input_tp"))
    in_lra = _as_float(pre_stats.get("input_lra"))
    out_lufs = _as_float(post_stats.get("input_i"))
    out_tp = _as_float(post_stats.get("input_tp"))
    out_lra = _as_float(post_stats.get("input_lra"))

    lufs_error = abs(out_lufs - target_lufs) if out_lufs is not None and target_lufs is not None else None
    tp_overshoot = (out_tp - target_tp) if out_tp is not None and target_tp is not None else None

    events = mts_data.get("events", [])
    peak_events = [ev for ev in events if isinstance(ev, dict) and ev.get("type") == "peak_risk"] if isinstance(events, list) else []
    sev_weight = {"low": 0.6, "medium": 1.0, "high": 2.0}
    weighted_peak_units = 0.0
    high_units = 0.0
    for ev in peak_events:
        sev = str(ev.get("severity", "medium")).lower()
        samples = max(1, int(ev.get("samples", 1) or 1))
        # Normaliza bursts por tamaño para evitar inflar riesgo por conteo de samples.
        burst_units = max(1.0, min(8.0, float(samples) / 2048.0))
        weighted_peak_units += sev_weight.get(sev, 1.0) * burst_units
        if sev == "high":
            high_units += burst_units
    duration_s = _as_float((mts_data.get("source") or {}).get("duration_seconds")) or 0.0
    minutes = max(1.0 / 60.0, duration_s / 60.0) if duration_s > 0 else (1.0 / 60.0)
    peak_rate_per_min = weighted_peak_units / minutes
    peak_rate_limit = 12.0
    high_peak_limit = 8.0

    overlap = _build_band_overlap_risk(validation_context)
    checks = {
        "lufs_error_ok": bool(lufs_error is not None and lufs_error <= 0.30),
        "true_peak_ok": bool(tp_overshoot is not None and tp_overshoot <= 0.20),
        "lra_sane": bool(out_lra is not None and out_lra >= 2.0),
        "peak_risk_rate_ok": bool((peak_rate_per_min <= peak_rate_limit) and (high_units <= high_peak_limit)),
        "band_overlap_ok": bool(overlap.get("overlap_ok", True)),
    }
    hard_ok = bool(checks["lufs_error_ok"] and checks["true_peak_ok"] and checks["lra_sane"])
    risk_ok = bool(checks["peak_risk_rate_ok"])
    overlap_ok = bool(checks["band_overlap_ok"])
    overall_ok = hard_ok and risk_ok and overlap_ok
    if hard_ok and (not risk_ok or not overlap_ok):
        status = "WARN"
    elif overall_ok:
        status = "PASS"
    else:
        status = "FAIL"

    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_file": str(output_path),
        "input_metrics": {
            "lufs_i": _round_opt(in_lufs, 2),
            "true_peak_dbtp": _round_opt(in_tp, 2),
            "lra_lu": _round_opt(in_lra, 2),
        },
        "targets": {
            "lufs_i_target": _round_opt(target_lufs, 2),
            "true_peak_target_dbtp": _round_opt(target_tp, 2),
        },
        "output_metrics": {
            "lufs_i": _round_opt(out_lufs, 2),
            "true_peak_dbtp": _round_opt(out_tp, 2),
            "lra_lu": _round_opt(out_lra, 2),
        },
        "deltas": {
            "lufs_error_abs": _round_opt(lufs_error, 3),
            "true_peak_overshoot_db": _round_opt(tp_overshoot, 3),
        },
        "risk": {
            "peak_risk_events": len(peak_events),
            "peak_risk_rate_per_min": round(peak_rate_per_min, 2),
            "peak_risk_high_units": round(high_units, 2),
            "peak_risk_weighted_units": round(weighted_peak_units, 2),
            "band_overlap": overlap,
        },
        "decision_context": {
            "dynamic_eq": bool(validation_context.get("dynamic_eq", False)),
            "deesser_enabled": bool(validation_context.get("deesser_enabled", False)),
            "stereo_dynamic_enabled": bool(validation_context.get("stereo_dynamic_enabled", False)),
        },
        "acceptance": {
            "criteria": {
                "lufs_error_abs_max": 0.30,
                "true_peak_overshoot_db_max": 0.20,
                "lra_min_lu": 2.0,
                "peak_risk_rate_per_min_max": peak_rate_limit,
                "peak_risk_high_units_max": high_peak_limit,
                "band_overlap_score_max_per_band": 2.0,
            },
            "checks": checks,
            "overall_ok": overall_ok,
            "status": status,
        },
    }


def build_mts_analysis(
    input_path: pathlib.Path,
    window_s: float = 1.0,
    hop_s: float = 1.0,
    sample_rate: int = 32000,
    max_seconds: int = 1800,
) -> Dict[str, Any]:
    """
    Genera serie temporal MTS (Music Time Series) de un archivo de audio.
    No modifica audio ni parámetros de mastering; solo observabilidad.
    """
    if not NUMPY_AVAILABLE:
        raise RuntimeError("MTS requiere numpy disponible en el entorno.")

    duration = get_audio_duration(str(input_path))
    if duration is None or duration <= 0:
        raise RuntimeError("No se pudo obtener duración válida del audio.")

    analyze_seconds = int(min(max_seconds, math.ceil(duration) + 1))
    samples = get_audio_mono_samples(
        str(input_path),
        sample_rate=sample_rate,
        max_seconds=analyze_seconds,
    )
    if not samples:
        raise RuntimeError("No se pudieron obtener muestras de audio para MTS.")

    data = np.array(samples, dtype=np.float32)
    frame_len = max(256, int(window_s * sample_rate))
    hop_len = max(128, int(hop_s * sample_rate))
    if data.size < frame_len:
        padded = np.zeros(frame_len, dtype=np.float32)
        padded[: data.size] = data
        data = padded

    freqs = np.fft.rfftfreq(frame_len, d=1.0 / sample_rate)
    band_bins: Dict[str, np.ndarray] = {}
    for label, low_hz, high_hz, *_ in BAND_CONFIG:
        lo = float(low_hz)
        hi = float(min(high_hz, sample_rate / 2.0))
        mask = np.where((freqs >= lo) & (freqs < hi))[0]
        if mask.size == 0:
            mask = np.array([min(len(freqs) - 1, max(0, int((lo + hi) * 0.5)))], dtype=np.int64)
        band_bins[label] = mask

    timeline: List[Dict[str, Any]] = []
    window = np.hanning(frame_len).astype(np.float32)
    floor = 1e-9
    i = 0
    while i < data.size:
        frame = data[i : i + frame_len]
        if frame.size < frame_len:
            padded = np.zeros(frame_len, dtype=np.float32)
            padded[: frame.size] = frame
            frame = padded

        timestamp_s = i / float(sample_rate)
        rms = float(np.sqrt(np.mean(frame * frame) + floor))
        peak = float(np.max(np.abs(frame)) + floor)
        crest = 20.0 * math.log10(max(1e-9, peak / max(rms, 1e-9)))
        spectrum = np.fft.rfft(frame * window)
        mag = np.abs(spectrum) + floor

        band_db: Dict[str, float] = {}
        for label, *_ in BAND_CONFIG:
            band_mag = float(np.mean(mag[band_bins[label]]))
            band_db[_safe_name(label)] = round(_to_db(band_mag), 2)

        point: Dict[str, Any] = {
            "t": round(timestamp_s, 3),
            "rms_db": round(_to_db(rms), 2),
            "peak_db": round(_to_db(peak), 2),
            "crest_db": round(crest, 2),
            "bands": band_db,
        }
        timeline.append(point)
        i += hop_len

    if not timeline:
        raise RuntimeError("MTS sin datos temporales.")

    rms_values = [float(p["rms_db"]) for p in timeline]
    peak_values = [float(p["peak_db"]) for p in timeline]
    crest_values = [float(p["crest_db"]) for p in timeline]
    analyzed_seconds = float(timeline[-1]["t"]) if timeline else 0.0

    hop_seconds = hop_len / float(sample_rate)
    events, event_counts, frame_events = detect_events_from_timeline(
        timeline=timeline,
        hop_s=hop_seconds,
    )
    sections = detect_sections_from_timeline(timeline=timeline)

    if frame_events:
        frame_by_t: Dict[float, List[Dict[str, Any]]] = {}
        for ev in frame_events:
            t_val = round(float(ev.get("t", 0.0)), 3)
            frame_by_t.setdefault(t_val, []).append(ev)
        for point in timeline:
            t_val = round(float(point.get("t", 0.0)), 3)
            if t_val in frame_by_t:
                point["events"] = frame_by_t[t_val]

    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": str(input_path),
            "duration_seconds": round(float(duration), 3),
            "sample_rate_hz": sample_rate,
            "window_seconds": float(window_s),
            "hop_seconds": float(hop_s),
            "analysis_seconds": round(analyzed_seconds, 3),
            "truncated": bool(duration > max_seconds),
        },
        "summary": {
            "frames": len(timeline),
            "rms_avg_db": round(sum(rms_values) / len(rms_values), 2),
            "rms_min_db": round(min(rms_values), 2),
            "rms_max_db": round(max(rms_values), 2),
            "peak_max_db": round(max(peak_values), 2),
            "crest_avg_db": round(sum(crest_values) / len(crest_values), 2),
            "event_counts": event_counts,
            "sections_count": len(sections),
        },
        "timeline": timeline,
        "sections": sections,
        "events": events,
    }


def write_mts_artifacts(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    window_s: float = 1.0,
    hop_s: float = 1.0,
    sample_rate: int = 32000,
    validation_context: Dict[str, Any] | None = None,
) -> Dict[str, pathlib.Path]:
    """
    Escribe artefactos MTS en el directorio `log` asociado al `output_path`.
    """
    mts = build_mts_analysis(
        input_path=input_path,
        window_s=window_s,
        hop_s=hop_s,
        sample_rate=sample_rate,
    )
    log_dir = output_path.parent / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    json_path = log_dir / f"{output_path.stem}.mts.json"
    md_path = log_dir / f"{output_path.stem}.mts.md"

    json_path.write_text(
        json.dumps(mts, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    summary = mts.get("summary", {})
    source = mts.get("source", {})
    event_counts = summary.get("event_counts", {})
    lines = [
        f"# MTS - {output_path.stem}",
        "",
        f"- Source: `{source.get('path', '')}`",
        f"- Duration (s): {source.get('duration_seconds', 0)}",
        f"- Analysis window/hop: {source.get('window_seconds', 1.0)}s / {source.get('hop_seconds', 1.0)}s",
        f"- Frames: {summary.get('frames', 0)}",
        f"- RMS avg/min/max (dB): {summary.get('rms_avg_db', 0)} / {summary.get('rms_min_db', 0)} / {summary.get('rms_max_db', 0)}",
        f"- Peak max (dB): {summary.get('peak_max_db', 0)}",
        f"- Crest avg (dB): {summary.get('crest_avg_db', 0)}",
        f"- Sections: {summary.get('sections_count', 0)}",
        "",
        "## Sections",
    ]
    sections = mts.get("sections", [])
    if isinstance(sections, list) and sections:
        for sec in sections:
            lines.append(
                "- "
                f"{sec.get('label', 'section')} "
                f"[{sec.get('start_s', 0)}s - {sec.get('end_s', 0)}s] "
                f"(conf {sec.get('confidence', 0)})"
            )
    else:
        lines.append("- none")
    lines.extend([
        "",
        "## Event Counts",
    ])
    if isinstance(event_counts, dict) and event_counts:
        for key, value in sorted(event_counts.items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append(f"JSON: `{json_path}`")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    flags = get_rollout_flags()
    global_adjustments = None
    if isinstance(validation_context, dict):
        global_adjustments = validation_context.get("global_adjustments")
    decisions_paths = write_master_decisions_artifacts(
        output_path=output_path,
        mts_data=mts,
        global_adjustments=global_adjustments,
    )
    shadow_paths = write_adaptive_shadow_artifacts(
        output_path=output_path,
        decisions_data=decisions_paths.get("data", {}),
        context=(validation_context or {}),
        force_shadow_mode=not bool(flags.get("adaptive_master_enabled", False)),
    )
    try:
        shadow_data = json.loads(shadow_paths["json_path"].read_text(encoding="utf-8"))
    except Exception:
        shadow_data = {}
    adaptive_report: Dict[str, Any] = {
        "status": "not_applied", "reason": "shadow_guard_not_ready",
        "executed_automations": [], "fallback": "static_master",
    }
    rollout_percent = int(flags.get("adaptive_rollout_percent", 100) or 0)
    rollout_bucket = int(hashlib.sha256(str(output_path.resolve()).encode()).hexdigest()[:8], 16) % 100
    selected_for_rollout = rollout_bucket < rollout_percent
    if not bool(flags.get("adaptive_master_enabled", False)):
        adaptive_report["reason"] = "adaptive_master_disabled"
    elif not selected_for_rollout:
        adaptive_report["reason"] = "not_selected_for_rollout"
    elif shadow_data.get("mode") != "apply_candidate":
        adaptive_report["reason"] = "shadow_not_apply_ready"
    if (bool(flags.get("adaptive_master_enabled", False))
            and selected_for_rollout
            and shadow_data.get("mode") == "apply_candidate"):
        target = _as_float((validation_context or {}).get("target_lufs"))
        tp_target = _as_float((validation_context or {}).get("true_peak_target"))
        if target is not None and tp_target is not None:
            adaptive_report = render_adaptive_candidate(
                output_path, decisions_paths.get("data", {}), target, tp_target)
    candidate_stats = adaptive_report.get("post_stats") if adaptive_report.get("status") == "candidate_ready" else None
    guard_paths = write_adaptive_guard_artifacts(
        output_path=output_path,
        target_lufs=validation_context.get("target_lufs") if isinstance(validation_context, dict) else None,
        true_peak_target=validation_context.get("true_peak_target") if isinstance(validation_context, dict) else None,
        pre_stats=validation_context.get("pre_stats") if isinstance(validation_context, dict) else None,
        post_stats=candidate_stats or (validation_context.get("post_stats") if isinstance(validation_context, dict) else None),
        mts_data=mts,
        shadow_data=shadow_data,
        flags=flags,
    )
    try:
        guard_data = json.loads(guard_paths["json_path"].read_text(encoding="utf-8"))
    except Exception:
        guard_data = {"overall_ok": False, "blockers": ["No se pudo leer la guardia adaptativa"]}
    if adaptive_report.get("status") == "candidate_ready":
        if guard_data.get("overall_ok") and publish_adaptive_candidate(output_path, adaptive_report):
            if isinstance(validation_context, dict):
                validation_context["post_stats"] = adaptive_report.get("post_stats")
        else:
            adaptive_report["status"] = "fallback_static"
            adaptive_report["reason"] = "; ".join(guard_data.get("blockers") or ["adaptive_guard_rejected"])
            discard_adaptive_candidate(adaptive_report)
            adaptive_report.pop("candidate_path", None)
            adaptive_report.pop("temporary_dir", None)
    adaptive_report["guard_overall_ok"] = bool(guard_data.get("overall_ok"))
    adaptive_report["shadow_mode"] = shadow_data.get("mode", "shadow_only")
    adaptive_report["rollout_percent"] = rollout_percent
    adaptive_report["rollout_bucket"] = rollout_bucket
    adaptive_report["selected_for_rollout"] = selected_for_rollout
    adaptive_json_path = log_dir / f"{output_path.stem}.adaptive_render.json"
    adaptive_md_path = log_dir / f"{output_path.stem}.adaptive_render.md"
    adaptive_json_path.write_text(json.dumps(adaptive_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    adaptive_md_path.write_text(
        f"# Adaptive Render - {output_path.stem}\n\n"
        f"- Status: `{adaptive_report.get('status')}`\n"
        f"- Guard OK: {adaptive_report.get('guard_overall_ok')}\n"
        f"- Executed automations: {len(adaptive_report.get('executed_automations') or [])}\n"
        f"- Fallback: `{adaptive_report.get('fallback')}`\n",
        encoding="utf-8",
    )
    ai_audit_path = log_dir / f"{output_path.stem}.ai_master.json"
    if ai_audit_path.is_file():
        try:
            ai_audit = json.loads(ai_audit_path.read_text(encoding="utf-8"))
            ai_audit["adaptive_render"] = {
                "status": adaptive_report.get("status"),
                "guard_overall_ok": adaptive_report.get("guard_overall_ok"),
                "executed_automations": adaptive_report.get("executed_automations", []),
                "fallback": adaptive_report.get("fallback"),
            }
            ai_audit_path.write_text(json.dumps(ai_audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass
    report = _build_master_validation_report(
        output_path=output_path,
        validation_context=(validation_context or {}),
        mts_data=mts,
    )
    validation_json_path = log_dir / f"{output_path.stem}.master_validation.json"
    validation_md_path = log_dir / f"{output_path.stem}.master_validation.md"
    validation_json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    md_lines = [
        f"# Master Validation - {output_path.stem}",
        "",
        f"- Status: **{report['acceptance']['status']}**",
        f"- Overall OK: {report['acceptance']['overall_ok']}",
        f"- LUFS out/target: {report['output_metrics']['lufs_i']} / {report['targets']['lufs_i_target']}",
        f"- True Peak out/target: {report['output_metrics']['true_peak_dbtp']} / {report['targets']['true_peak_target_dbtp']}",
        f"- LRA out: {report['output_metrics']['lra_lu']}",
        f"- Peak risk events: {report['risk']['peak_risk_events']}",
        f"- Peak risk rate/min: {report['risk']['peak_risk_rate_per_min']}",
        "",
        "## Checks",
    ]
    for key, ok in (report["acceptance"].get("checks") or {}).items():
        md_lines.append(f"- {key}: {'OK' if ok else 'FAIL'}")
    validation_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {
        "json_path": json_path,
        "md_path": md_path,
        "decisions_json_path": decisions_paths["json_path"],
        "decisions_md_path": decisions_paths["md_path"],
        "shadow_json_path": shadow_paths["json_path"],
        "shadow_md_path": shadow_paths["md_path"],
        "guard_json_path": guard_paths["json_path"],
        "guard_md_path": guard_paths["md_path"],
        "adaptive_render_json_path": adaptive_json_path,
        "adaptive_render_md_path": adaptive_md_path,
        "validation_json_path": validation_json_path,
        "validation_md_path": validation_md_path,
    }
