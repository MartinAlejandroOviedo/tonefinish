# DEPRECATED: v2.0.0: De-esser global reemplazado por per-band compression en multiband.
# Este archivo se conserva para compatibilidad con versiones anteriores.

from __future__ import annotations

import pathlib

from audio_tools import get_audio_sample_rate


def _level_key(level: str) -> str:
    return level.strip().lower()


def _level_impact(level: str, base: float, medium: float, high: float) -> float:
    key = _level_key(level)
    if key in ("off", "apagado"):
        return 0.0
    if key == "leve":
        return base
    if key == "medio":
        return medium
    if key == "alto":
        return high
    return base


def resolve_deesser_intensity(
    noise_level: str,
    declick_level: str,
    budget_db: float = 2.0,
) -> float:
    """Reduce la intensidad del de-esser si hay otras reducciones activas."""
    noise_impact = _level_impact(noise_level, base=0.8, medium=1.4, high=2.0)
    declick_impact = _level_impact(declick_level, base=1.0, medium=1.6, high=2.2)
    used = noise_impact + declick_impact
    remaining = max(0.0, budget_db - used)
    if budget_db <= 0:
        return 1.0
    intensity = remaining / budget_db
    return max(0.1, min(0.75, intensity))


def build_deesser_filter(
    input_path: pathlib.Path,
    target_hz: float = 6000.0,
    intensity: float = 1.0,
) -> str:
    """Construye un filtro de de-esser con frecuencia normalizada 0-1."""
    intensity = max(0.1, min(0.75, intensity))
    i_val = 0.35 * intensity
    s_val = 0.35 * intensity
    sample_rate = get_audio_sample_rate(str(input_path))
    if not sample_rate:
        return f"deesser=i={i_val:.2f}:m=0.5:f=0.5:s={s_val:.2f}"
    nyquist = sample_rate / 2.0
    normalized = max(0.0, min(1.0, target_hz / nyquist))
    return f"deesser=i={i_val:.2f}:m=0.5:f={normalized:.4f}:s={s_val:.2f}"
