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


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _event_counts_in_section(
    events: List[Dict[str, Any]],
    start_s: float,
    end_s: float,
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for ev in events:
        ev_start = _f(ev.get("start_s"), _f(ev.get("t"), 0.0))
        ev_end = _f(ev.get("end_s"), ev_start)
        if _overlap(start_s, end_s, ev_start, ev_end) <= 0.0:
            continue
        ev_type = str(ev.get("type", "unknown"))
        counts[ev_type] = counts.get(ev_type, 0) + 1
    return counts


def _base_actions_for_label(label: str) -> Dict[str, Any]:
    if label == "intro":
        return {
            "eq": {"subbass_db": 0.10, "bass_db": 0.05, "mid_db": 0.00, "high_mid_db": -0.5, "air_db": -0.8},
            "deesser_intensity_delta": 0.00,
            "saturation_mix_mult": 0.96,
            "stereo_motion_amount_mult": 0.92,
            "multiband_low_end_tightness": 0.55,
            "limiter_tp_margin_db": 0.00,
        }
    if label in ("drop", "chorus"):
        return {
            "eq": {"subbass_db": 0.25, "bass_db": 0.20, "mid_db": -0.05, "high_mid_db": -0.8, "air_db": -1.0},
            "deesser_intensity_delta": 0.02,
            "saturation_mix_mult": 1.03,
            "stereo_motion_amount_mult": 1.00,
            "multiband_low_end_tightness": 0.68,
            "limiter_tp_margin_db": -0.05,
        }
    if label in ("breakdown", "verse"):
        return {
            "eq": {"subbass_db": 0.05, "bass_db": 0.05, "mid_db": 0.03, "high_mid_db": -0.6, "air_db": -0.8},
            "deesser_intensity_delta": 0.01,
            "saturation_mix_mult": 0.98,
            "stereo_motion_amount_mult": 0.96,
            "multiband_low_end_tightness": 0.60,
            "limiter_tp_margin_db": 0.00,
        }
    if label == "outro":
        return {
            "eq": {"subbass_db": 0.00, "bass_db": 0.02, "mid_db": 0.00, "high_mid_db": -0.4, "air_db": -0.6},
            "deesser_intensity_delta": 0.00,
            "saturation_mix_mult": 0.94,
            "stereo_motion_amount_mult": 0.90,
            "multiband_low_end_tightness": 0.58,
            "limiter_tp_margin_db": 0.00,
        }
    # build / fallback
    return {
        "eq": {"subbass_db": 0.12, "bass_db": 0.08, "mid_db": 0.00, "high_mid_db": -0.06, "air_db": -0.04},
        "deesser_intensity_delta": 0.01,
        "saturation_mix_mult": 1.00,
        "stereo_motion_amount_mult": 0.98,
        "multiband_low_end_tightness": 0.62,
        "limiter_tp_margin_db": 0.00,
    }


def build_master_decisions(
    mts_data: Dict[str, Any],
    strategy: str = "adaptive_v1",
    global_adjustments: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    sections = mts_data.get("sections", [])
    events = mts_data.get("events", [])
    summary = mts_data.get("summary", {})
    source = mts_data.get("source", {})
    if not isinstance(sections, list):
        sections = []
    if not isinstance(events, list):
        events = []

    # Extract gap-based EQ from global adjustments (v2.0.0)
    gap_eq: Dict[str, float] = {}
    if global_adjustments and isinstance(global_adjustments.get("eq_adjustments"), dict):
        gap_eq = {k: float(v) for k, v in global_adjustments["eq_adjustments"].items()}

    # Map band names: auto_master 6-band → decisions 5-band
    BAND_MAP_DIRECT = {
        "Subbass (20-60 Hz)": "subbass_db",
        "Bass (60-250 Hz)": "bass_db",
        "High-Mid (2k-6k Hz)": "high_mid_db",
        "Air (6k-16k Hz)": "air_db",
    }

    section_decisions: List[Dict[str, Any]] = []
    use_gap = bool(gap_eq)

    for idx, sec in enumerate(sections, start=1):
        label = str(sec.get("label", "section"))
        start_s = _f(sec.get("start_s"), 0.0)
        end_s = _f(sec.get("end_s"), start_s)
        sec_events = _event_counts_in_section(events, start_s, end_s)
        base = _base_actions_for_label(label)

        # If gap-based EQ is available, override base profile with calculated corrections
        if use_gap:
            eq = {}
            for band_full, db_key in BAND_MAP_DIRECT.items():
                eq[db_key] = gap_eq.get(band_full, 0.0)
            # mid_db = average of Low-Mid and Mid
            lm = gap_eq.get("Low-Mid (250-500 Hz)", 0.0)
            md = gap_eq.get("Mid (500-2k Hz)", 0.0)
            nonzero = [v for v in (lm, md) if v != 0.0]
            eq["mid_db"] = sum(nonzero) / len(nonzero) if nonzero else 0.0
        else:
            eq = dict(base["eq"])
        deesser_delta = _f(base.get("deesser_intensity_delta"), 0.0)
        sat_mult = _f(base.get("saturation_mix_mult"), 1.0)
        motion_mult = _f(base.get("stereo_motion_amount_mult"), 1.0)
        low_end_tight = _f(base.get("multiband_low_end_tightness"), 0.6)
        tp_margin = _f(base.get("limiter_tp_margin_db"), 0.0)
        rationale: List[str] = [f"base_profile={label}"]

        harsh = int(sec_events.get("harshness_risk", 0))
        if harsh > 0:
            eq["high_mid_db"] = round(_f(eq.get("high_mid_db"), 0.0) - 1.0, 3)
            eq["air_db"] = round(_f(eq.get("air_db"), 0.0) - 1.5, 3)
            deesser_delta = round(deesser_delta + 0.08, 3)
            sat_mult = round(max(0.85, sat_mult - 0.06), 3)
            rationale.append("event=harshness_risk -> soften highs + de-ess up")

        low_weak = int(sec_events.get("low_end_weak", 0))
        if low_weak > 0:
            eq["subbass_db"] = round(_f(eq.get("subbass_db"), 0.0) + 0.20, 3)
            eq["bass_db"] = round(_f(eq.get("bass_db"), 0.0) + 0.16, 3)
            low_end_tight = round(max(0.52, low_end_tight - 0.05), 3)
            rationale.append("event=low_end_weak -> reinforce kick/bass")

        low_hot = int(sec_events.get("low_end_hot", 0))
        if low_hot > 0:
            eq["subbass_db"] = round(_f(eq.get("subbass_db"), 0.0) - 0.18, 3)
            eq["bass_db"] = round(_f(eq.get("bass_db"), 0.0) - 0.14, 3)
            low_end_tight = round(min(0.82, low_end_tight + 0.08), 3)
            sat_mult = round(max(0.86, sat_mult - 0.03), 3)
            rationale.append("event=low_end_hot -> tighten low-end")

        peak_risk = int(sec_events.get("peak_risk", 0))
        if peak_risk > 0:
            tp_margin = round(tp_margin - 0.08, 3)
            sat_mult = round(max(0.86, sat_mult - 0.02), 3)
            rationale.append("event=peak_risk -> stricter TP margin")

        flat = int(sec_events.get("dynamic_flat", 0))
        if flat > 0 and low_hot == 0:
            motion_mult = round(min(1.06, motion_mult + 0.03), 3)
            rationale.append("event=dynamic_flat -> micro motion boost")

        decision = {
            "section_id": idx,
            "label": label,
            "start_s": round(start_s, 3),
            "end_s": round(end_s, 3),
            "duration_s": round(max(0.0, end_s - start_s), 3),
            "confidence": _f(sec.get("confidence"), 0.6),
            "events": sec_events,
            "actions": {
                "eq_db": {
                    # Gap-based: clamp amplio ±3.0; modo fijo: ±1.5
                    k: round(_clamp(_f(v), -3.0 if use_gap else -1.5, 3.0 if use_gap else 1.5), 3)
                    for k, v in eq.items()
                },
                "deesser_intensity_delta": round(_clamp(deesser_delta, -0.08, 0.12), 3),
                "saturation_mix_mult": round(_clamp(sat_mult, 0.84, 1.08), 3),
                "stereo_motion_amount_mult": round(_clamp(motion_mult, 0.84, 1.08), 3),
                "multiband_low_end_tightness": round(_clamp(low_end_tight, 0.45, 0.90), 3),
                "limiter_tp_margin_db": round(_clamp(tp_margin, -0.25, 0.10), 3),
            },
            "guards": {
                "max_eq_step_db": 0.30,
                "max_param_delta_per_transition": 0.10,
                "smoothing_ms": 180.0,
            },
            "rationale": rationale,
        }
        section_decisions.append(decision)

    global_policy = {
        "strategy": "gap-based_v2" if use_gap else strategy,
        "fallback_mode": "static_master",
        "safety": {
            "tp_max_dbtp": -1.5,
            "max_eq_abs_db": 1.5,
            "max_sat_mix_mult": 1.15,
            "min_sat_mix_mult": 0.80,
        },
    }

    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "path": source.get("path"),
            "duration_seconds": source.get("duration_seconds"),
            "analysis_frames": summary.get("frames"),
            "sections_count": len(section_decisions),
            "event_counts": summary.get("event_counts", {}),
        },
        "global_policy": global_policy,
        "section_decisions": section_decisions,
    }


def write_master_decisions_artifacts(
    output_path: pathlib.Path,
    mts_data: Dict[str, Any],
    strategy: str = "adaptive_v1",
    global_adjustments: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    decisions = build_master_decisions(mts_data=mts_data, strategy=strategy, global_adjustments=global_adjustments)
    log_dir = output_path.parent / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    json_path = log_dir / f"{output_path.stem}.master_decisions.json"
    md_path = log_dir / f"{output_path.stem}.master_decisions.md"

    json_path.write_text(
        json.dumps(decisions, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        f"# Master Decisions - {output_path.stem}",
        "",
        f"- Strategy: `{decisions.get('global_policy', {}).get('strategy', 'adaptive_v1')}`",
        f"- Sections: {len(decisions.get('section_decisions', []))}",
        "",
        "## Section Decisions",
    ]
    for sec in decisions.get("section_decisions", []):
        actions = sec.get("actions", {})
        lines.append(
            "- "
            f"{sec.get('label', 'section')} "
            f"[{sec.get('start_s', 0)}s - {sec.get('end_s', 0)}s] "
            f"eq={actions.get('eq_db', {})} "
            f"deesser_delta={actions.get('deesser_intensity_delta', 0)} "
            f"sat_mult={actions.get('saturation_mix_mult', 1)}"
        )

    lines.append("")
    lines.append(f"JSON: `{json_path}`")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"json_path": json_path, "md_path": md_path, "data": decisions}
