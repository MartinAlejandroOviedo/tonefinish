# DEPRECATED: v2.0.0: Limiter global reemplazado por per-band alimiter en multiband.
# Este archivo se conserva para compatibilidad con versiones anteriores.

from __future__ import annotations

MIN_ALIMITER_ATTACK_MS = 1.0
MIN_ALIMITER_RELEASE_MS = 10.0


def _clamp_alimiter_times(attack_ms: float, release_ms: float) -> tuple[float, float]:
    return max(MIN_ALIMITER_ATTACK_MS, attack_ms), max(MIN_ALIMITER_RELEASE_MS, release_ms)


def build_master_limiter_filter(
    mode: str = "transparent",
    ceiling_db: float = -1.0,
    release_ms: float = 150.0,
    lookahead_ms: float = 5.0,
    input_sr: int | None = None,
    enable_oversampling: bool = True,
) -> str:
    """Construye el filtro de Master Limiter según el modo."""
    ceiling_db = max(-3.0, min(0.0, ceiling_db))
    release_ms = max(10.0, min(1000.0, release_ms))

    mode_params = {
        "transparent": {"attack": 0.5, "release_mult": 1.0, "threshold_offset": 0.0},
        "musical": {"attack": 1.0, "release_mult": 1.3, "threshold_offset": -0.3},
        "aggressive": {"attack": 0.2, "release_mult": 0.7, "threshold_offset": -0.5},
    }

    params = mode_params.get(mode, mode_params["transparent"])
    attack_ms, release_adjusted = _clamp_alimiter_times(
        params["attack"], release_ms * params["release_mult"]
    )
    limit_linear = 10 ** (ceiling_db / 20.0)
    filter_parts: list[str] = []

    if enable_oversampling and input_sr and input_sr > 0:
        oversampled_sr = min(input_sr * 2, 192000)
        if oversampled_sr != input_sr:
            filter_parts.append(f"aresample={oversampled_sr}:resampler=soxr:precision=33")

    filter_parts.append(
        f"alimiter=limit={limit_linear:.6f}:"
        f"attack={attack_ms:.2f}:"
        f"release={release_adjusted:.2f}:"
        f"level_in=1.0:"
        f"level_out=1.0"
    )

    if enable_oversampling and input_sr and input_sr > 0:
        oversampled_sr = min(input_sr * 2, 192000)
        if oversampled_sr != input_sr:
            filter_parts.append(f"aresample={input_sr}:resampler=soxr:precision=33")

    return ",".join(filter_parts)

