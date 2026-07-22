from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Tuple


def _f(value: Any, default: float = -120.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _confidence(raw: float) -> float:
    return round(max(0.2, min(0.99, raw)), 2)


def detect_events_from_timeline(
    timeline: List[Dict[str, Any]],
    hop_s: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, int], List[Dict[str, Any]]]:
    """
    Detecta eventos sobre timeline MTS.

    Returns:
      - events: eventos agregados por tramo
      - event_counts: conteo por tipo
      - frame_events: flags por frame (t, type, severity, confidence)
    """
    frame_events: List[Dict[str, Any]] = []

    for point in timeline:
        t = _f(point.get("t"), 0.0)
        peak_db = _f(point.get("peak_db"))
        rms_db = _f(point.get("rms_db"))
        crest_db = _f(point.get("crest_db"), 0.0)
        bands = point.get("bands", {}) if isinstance(point.get("bands"), dict) else {}
        high_mid = _f(bands.get("high_mid_2k_6k_hz"))
        air = _f(bands.get("air_6k_16k_hz"))
        mid = _f(bands.get("mid_500_2k_hz"))
        bass = _f(bands.get("bass_60_250_hz"))
        sub = _f(bands.get("subbass_20_60_hz"))

        # Evita falsos positivos por picos aislados de material dinámico:
        # para riesgo "medio" pedimos además contexto de energía/dinámica.
        if peak_db > -1.0:
            frame_events.append(
                {"t": round(t, 3), "type": "peak_risk", "severity": "high", "confidence": _confidence(0.95)}
            )
        elif peak_db > -2.0 and (rms_db > -15.0 or crest_db < 14.0):
            frame_events.append(
                {"t": round(t, 3), "type": "peak_risk", "severity": "medium", "confidence": _confidence(0.78)}
            )

        harsh_delta = max(high_mid - mid, air - mid)
        if harsh_delta > 4.0:
            frame_events.append(
                {"t": round(t, 3), "type": "harshness_risk", "severity": "high", "confidence": _confidence(0.85)}
            )
        elif harsh_delta > 2.8:
            frame_events.append(
                {"t": round(t, 3), "type": "harshness_risk", "severity": "medium", "confidence": _confidence(0.7)}
            )

        if sub < -28.0 and bass < -24.0:
            frame_events.append(
                {"t": round(t, 3), "type": "low_end_weak", "severity": "medium", "confidence": _confidence(0.72)}
            )
        elif sub > -14.0 and bass > -12.0:
            frame_events.append(
                {"t": round(t, 3), "type": "low_end_hot", "severity": "medium", "confidence": _confidence(0.74)}
            )

        if crest_db < 4.0 and rms_db > -16.0:
            frame_events.append(
                {"t": round(t, 3), "type": "dynamic_flat", "severity": "low", "confidence": _confidence(0.6)}
            )

    events = _aggregate_frame_events(frame_events, hop_s=hop_s)
    event_counts = dict(Counter(ev["type"] for ev in events))
    return events, event_counts, frame_events


def _aggregate_frame_events(
    frame_events: List[Dict[str, Any]],
    hop_s: float,
) -> List[Dict[str, Any]]:
    if not frame_events:
        return []

    ordered = sorted(frame_events, key=lambda e: (str(e.get("type", "")), float(e.get("t", 0.0))))
    merged: List[Dict[str, Any]] = []
    tol = max(0.001, hop_s * 1.6)

    for ev in ordered:
        ev_type = str(ev.get("type", "unknown"))
        t = _f(ev.get("t"), 0.0)
        severity = str(ev.get("severity", "low"))
        conf = _f(ev.get("confidence"), 0.5)
        if not merged:
            merged.append(
                {
                    "type": ev_type,
                    "severity": severity,
                    "start_s": round(t, 3),
                    "end_s": round(t, 3),
                    "confidence": conf,
                    "samples": 1,
                }
            )
            continue

        last = merged[-1]
        if (
            str(last.get("type")) == ev_type
            and (t - _f(last.get("end_s"), 0.0)) <= tol
        ):
            last["end_s"] = round(t, 3)
            last["samples"] = int(last.get("samples", 1)) + 1
            last["confidence"] = round(
                (
                    (_f(last.get("confidence"), 0.5) * (int(last["samples"]) - 1))
                    + conf
                )
                / int(last["samples"]),
                2,
            )
            sev_rank = {"low": 1, "medium": 2, "high": 3}
            if sev_rank.get(severity, 1) > sev_rank.get(str(last.get("severity", "low")), 1):
                last["severity"] = severity
        else:
            merged.append(
                {
                    "type": ev_type,
                    "severity": severity,
                    "start_s": round(t, 3),
                    "end_s": round(t, 3),
                    "confidence": conf,
                    "samples": 1,
                }
            )

    for item in merged:
        duration = max(0.0, _f(item.get("end_s"), 0.0) - _f(item.get("start_s"), 0.0) + hop_s)
        item["duration_s"] = round(duration, 3)

    merged.sort(key=lambda e: _f(e.get("start_s"), 0.0))
    return merged
