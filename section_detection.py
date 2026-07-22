from __future__ import annotations

from typing import Any, Dict, List


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def detect_sections_from_timeline(
    timeline: List[Dict[str, Any]],
    min_section_s: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Segmenta timeline en secciones musicales aproximadas.
    Heurística liviana para observabilidad (Fase 3).
    """
    if not timeline:
        return []

    times = [_f(p.get("t"), 0.0) for p in timeline]
    rms = [_f(p.get("rms_db"), -120.0) for p in timeline]
    hi = [_f((p.get("bands") or {}).get("high_mid_2k_6k_hz"), -120.0) for p in timeline]
    lo = [_f((p.get("bands") or {}).get("bass_60_250_hz"), -120.0) for p in timeline]

    if len(times) == 1:
        return [
            {
                "start_s": 0.0,
                "end_s": round(times[0], 3),
                "label": "single",
                "confidence": 0.5,
                "energy_db": round(rms[0], 2),
            }
        ]

    hop = max(0.1, times[1] - times[0])
    min_frames = max(3, int(min_section_s / hop))

    median_rms = sorted(rms)[len(rms) // 2]
    boundaries = [0]

    for i in range(1, len(rms)):
        dr = abs(rms[i] - rms[i - 1])
        ds = abs((hi[i] - lo[i]) - (hi[i - 1] - lo[i - 1]))
        if dr > 2.8 or ds > 3.2:
            if (i - boundaries[-1]) >= min_frames:
                boundaries.append(i)

    if boundaries[-1] != len(rms) - 1:
        boundaries.append(len(rms) - 1)

    sections: List[Dict[str, Any]] = []
    for idx in range(len(boundaries) - 1):
        a = boundaries[idx]
        b = boundaries[idx + 1]
        if b <= a:
            continue
        start_s = times[a]
        end_s = times[b]
        energy = sum(rms[a:b + 1]) / max(1, (b - a + 1))
        brightness = sum((hi[j] - lo[j]) for j in range(a, b + 1)) / max(1, (b - a + 1))
        pos = (start_s + end_s) * 0.5 / max(1e-9, times[-1])

        if idx == 0 and energy < median_rms - 1.5:
            label = "intro"
            conf = 0.78
        elif idx == (len(boundaries) - 2) and energy < median_rms - 1.0:
            label = "outro"
            conf = 0.78
        elif energy > median_rms + 1.8:
            label = "drop" if brightness > 1.0 else "chorus"
            conf = 0.72
        elif energy < median_rms - 1.2:
            label = "breakdown" if pos > 0.25 and pos < 0.85 else "verse"
            conf = 0.64
        else:
            label = "build" if brightness > 0.8 else "verse"
            conf = 0.6

        sections.append(
            {
                "start_s": round(start_s, 3),
                "end_s": round(end_s, 3),
                "duration_s": round(max(0.0, end_s - start_s + hop), 3),
                "label": label,
                "confidence": round(conf, 2),
                "energy_db": round(energy, 2),
                "brightness_delta_db": round(brightness, 2),
            }
        )

    # Coalesce tiny sections into previous to avoid over-segmentation
    compact: List[Dict[str, Any]] = []
    for section in sections:
        if compact and _f(section.get("duration_s"), 0.0) < min_section_s * 0.6:
            prev = compact[-1]
            prev["end_s"] = section["end_s"]
            prev["duration_s"] = round(_f(prev.get("duration_s"), 0.0) + _f(section.get("duration_s"), 0.0), 3)
            prev["confidence"] = round((_f(prev.get("confidence"), 0.5) + _f(section.get("confidence"), 0.5)) / 2.0, 2)
            prev["label"] = prev["label"] if prev["label"] != "verse" else section["label"]
        else:
            compact.append(section)

    return compact

