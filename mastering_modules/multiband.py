from __future__ import annotations

import math
from typing import Dict, Tuple

from config import (
    BAND_CONFIG,
    BAND_HEADROOM_DB,
    MAX_SATURATION_DRIVE_DB,
    MULTIBAND_LIMITER_ATTACK_MS,
    MULTIBAND_LIMITER_DEFAULTS,
    MULTIBAND_LIMITER_RELEASE_MS,
    DEFAULT_BAND_RANGE_DB,
    DEFAULT_MAX_ADJUST_DB,
)

MIN_ALIMITER_ATTACK_MS = 1.0
MIN_ALIMITER_RELEASE_MS = 10.0
SENSITIVE_BAND_NAMES = {"High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"}
MAX_SENSITIVE_MIX = 0.35
SENSITIVE_DRIVE_SCALE = 0.6

# Sesgo anti-fatiga para control dinámico por bandas.
# > 1.0 = más atenuación cuando la banda está alta.
DYNAMIC_EQ_CUT_BIAS = {
    "Subbass (20-60 Hz)": 1.12,      # un poco menos de sub grave
    "Bass (60-250 Hz)": 1.00,
    "Low-Mid (250-500 Hz)": 0.98,
    "Mid (500-2k Hz)": 0.90,         # protegemos el cuerpo/voz
    "High-Mid (2k-6k Hz)": 1.30,     # presencia menos agresiva
    "Air (6k-16k Hz)": 1.45,         # brillo más controlado
}


def _clamp_alimiter_times(attack_ms: float, release_ms: float) -> tuple[float, float]:
    return max(MIN_ALIMITER_ATTACK_MS, attack_ms), max(MIN_ALIMITER_RELEASE_MS, release_ms)


def resolve_saturation_type(saturation_type: str) -> str:
    sat_key = saturation_type.strip().lower()
    if sat_key in ("tape", "soft clip", "soft"):
        return "tanh"
    if sat_key in ("tube", "valve"):
        return "atan"
    return "tanh"


def build_multiband_filter(
    band_stats: Dict[str, float] | None,
    band_peaks: Dict[str, float] | None = None,
    apply_dynamic_eq: bool = False,
    apply_stereo_width: bool = False,
    input_label: str = "in",
    band_range_db: float = DEFAULT_BAND_RANGE_DB,
    max_adjust_db: float = DEFAULT_MAX_ADJUST_DB,
    band_adjust_db: Dict[str, float] | None = None,
    band_widths: Dict[str, float] | None = None,
    auto_band_gain: bool = False,
    saturation_per_band: bool = False,
    saturation_band_drive_db: Dict[str, float] | None = None,
    saturation_band_mix: Dict[str, float] | None = None,
    saturation_type: str = "Tape",
    enable_band_limiter: bool = True,
    multiband_limiter_enabled: bool = False,
    multiband_limiter_thresholds: Dict[str, float] | None = None,
    # === v2.0.0: COMPRESIÓN POR BANDA ===
    band_compression: Dict[str, Dict[str, float]] | None = None,
    # === v2.0.0: REPARACIÓN POR BANDA ===
    band_repair: Dict[str, Dict[str, str]] | None = None,
) -> Tuple[str, str]:
    split_labels = [f"b{i}" for i in range(len(BAND_CONFIG))]
    band_outputs = [f"c{i}" for i in range(len(BAND_CONFIG))]

    split = f"[{input_label}]asplit={len(BAND_CONFIG)}" + "".join(f"[{label}]" for label in split_labels)
    parts = [split]
    sat_filter = resolve_saturation_type(saturation_type)
    mb_thresholds = multiband_limiter_thresholds or MULTIBAND_LIMITER_DEFAULTS.copy()
    # Auto-calcular compresión por banda si no se pasó explícitamente
    # Usa el crest por banda (peak - RMS) para decidir cuánta compresión necesita
    if band_compression is None and band_stats:
        band_compression = {}
        for label, low_hz, high_hz, attack_s, release_s, width in BAND_CONFIG:
            rms = band_stats.get(label, -50.0)
            # Crest real por banda desde band_peaks, o estimado
            if band_peaks and label in band_peaks:
                crest_band = band_peaks[label] - rms
            else:
                crest_band = 10.0  # default moderate dynamics
            crest_band = max(2.0, crest_band)
            # Threshold: RMS + margen para atrapar picos
            threshold_db = rms + max(3.0, min(12.0, crest_band * 0.6))
            # Ratio basado en crest: más dinámico → más compresión
            if crest_band > 20:
                ratio = 3.0
            elif crest_band > 12:
                ratio = 2.0
            elif crest_band > 8:
                ratio = 1.5
            else:
                ratio = 1.2  # ya comprimido → apenas tocar
            
            # Ataque/liberación por frecuencia
            if high_hz >= 2000:
                atk, rel = 3.0, 50.0   # agudos: rápido
            elif high_hz >= 500:
                atk, rel = 8.0, 80.0   # medios: moderado
            else:
                atk, rel = 15.0, 120.0  # graves: lento
            
            band_compression[label] = {
                "threshold_db": round(threshold_db, 1),
                "ratio": round(ratio, 1),
                "attack_ms": round(atk, 1),
                "release_ms": round(rel, 1),
                "knee_db": 4.0,
                "makeup_db": 0.0,
            }
    has_band_comp = bool(band_compression)
    process_density = sum(
        1
        for flag in (
            apply_dynamic_eq or has_band_comp,
            apply_stereo_width,
            saturation_per_band,
            auto_band_gain,
            bool(band_adjust_db and any(abs(v) > 0.001 for v in band_adjust_db.values())),
        )
        if flag
    )

    for idx, (label, low_hz, high_hz, attack_s, release_s, width) in enumerate(BAND_CONFIG):
        band_chain = f"[{split_labels[idx]}]highpass=f={low_hz},lowpass=f={high_hz}"

        # === REPARACIÓN POR BANDA (v2.0.0: denoise/declip/declick por frecuencia) ===
        if band_repair and label in band_repair:
            repair = band_repair[label]
            declip_lvl = (repair.get("declip") or "Off").strip().lower()
            declick_lvl = (repair.get("declick") or "Off").strip().lower()
            denoise_lvl = (repair.get("denoise") or "Off").strip().lower()
            
            if declip_lvl not in ("off", "apagado", ""):
                band_chain += ",adeclip"
            
            if declick_lvl not in ("off", "apagado", ""):
                a_val = {"leve": "0.15", "medio": "0.28", "alto": "0.45"}.get(declick_lvl, "0.25")
                band_chain += f",adeclick=a={a_val}"
            
            if denoise_lvl not in ("off", "apagado", ""):
                nr_val = {"leve": "2", "medio": "6", "alto": "10"}.get(denoise_lvl, "3")
                nf_val = {"leve": "-22", "medio": "-28", "alto": "-32"}.get(denoise_lvl, "-24")
                band_chain += f",afftdn=nr={nr_val}:nf={nf_val}"

        if has_band_comp and label in band_compression:
            comp = band_compression[label]
            thr = comp.get("threshold_db", -18.0)
            ratio = comp.get("ratio", 2.0)
            atk = max(1.0, comp.get("attack_ms", 10.0))
            rel = max(10.0, comp.get("release_ms", 80.0))
            knee = comp.get("knee_db", 4.0)
            mkup = comp.get("makeup_db", 0.0)
            band_chain += (
                f",acompressor=threshold={thr:.2f}dB:ratio={ratio:.1f}"
                f":attack={atk:.1f}:release={rel:.1f}"
                f":knee={knee:.1f}:makeup={mkup:.1f}:detection=peak"
            )
        elif apply_dynamic_eq:
            if band_stats is None:
                raise RuntimeError("No hay análisis por bandas disponible para control dinámico.")
            rms = band_stats.get(label)
            if rms is None:
                raise RuntimeError(f"No hay RMS para la banda {label}.")

            low_thr = max(rms - band_range_db, -90.0)
            high_thr = min(rms + band_range_db, 0.0)
            if high_thr <= low_thr:
                high_thr = min(0.0, low_thr + 0.5)

            band_chain += (
                f",acompressor=threshold={high_thr:.2f}dB:ratio=2.0:attack={attack_s}:"
                f"release={release_s}:knee=4.0:makeup=0.0:detection=peak"
            )

        if apply_stereo_width:
            if band_widths and label in band_widths:
                width = band_widths[label]
            width_clamped = max(0.015625, min(64.0, width))
            band_chain += f",stereotools=mlev=1:slev={width_clamped:.2f}"

        if band_adjust_db:
            adjust_db = band_adjust_db.get(label, 0.0)
            if abs(adjust_db) > 0.001:
                band_chain += f",volume={adjust_db:.2f}dB"

        if multiband_limiter_enabled:
            threshold_db = mb_thresholds.get(label, -2.0)
            limit_linear = 10 ** (threshold_db / 20.0)
            attack_ms, release_ms = _clamp_alimiter_times(
                MULTIBAND_LIMITER_ATTACK_MS, MULTIBAND_LIMITER_RELEASE_MS
            )
            band_chain += f",alimiter=limit={limit_linear:.6f}:attack={attack_ms}:release={release_ms}"
        elif enable_band_limiter and label in BAND_HEADROOM_DB:
            headroom_db = BAND_HEADROOM_DB[label]
            limit_linear = 10 ** (headroom_db / 20.0)
            attack_ms, release_ms = _clamp_alimiter_times(1.0, 50.0)
            band_chain += f",alimiter=limit={limit_linear:.6f}:attack={attack_ms}:release={release_ms}"

        out_label = band_outputs[idx]
        if saturation_per_band:
            drive_db = 0.0
            mix = 0.0
            if saturation_band_drive_db and label in saturation_band_drive_db:
                drive_db = saturation_band_drive_db.get(label, 0.0)
            if saturation_band_mix and label in saturation_band_mix:
                mix = saturation_band_mix.get(label, 0.0)
            mix = max(0.0, min(1.0, mix))
            if label in SENSITIVE_BAND_NAMES:
                mix = min(MAX_SENSITIVE_MIX, mix)
            if mix > 0.0:
                max_drive = MAX_SATURATION_DRIVE_DB.get(label, 24.0)
                if label in SENSITIVE_BAND_NAMES:
                    max_drive = min(max_drive, 6.0)
                    drive_db *= SENSITIVE_DRIVE_SCALE
                drive_db = max(-24.0, min(max_drive, drive_db))
                dry = 1.0 - mix
                base_label = f"{band_outputs[idx]}b"
                dry_label = f"{band_outputs[idx]}d"
                wet_label = f"{band_outputs[idx]}w"
                wet_proc = f"{band_outputs[idx]}p"
                sat_out = f"{band_outputs[idx]}s"
                clip_filter = f"asoftclip=type={sat_filter}:threshold=1:output=1"
                parts.append(f"{band_chain}[{base_label}]")
                parts.append(f"[{base_label}]asplit=2[{dry_label}][{wet_label}]")
                parts.append(f"[{wet_label}]volume={drive_db:.2f}dB,{clip_filter}[{wet_proc}]")
                parts.append(f"[{dry_label}][{wet_proc}]amix=inputs=2:weights={dry:.2f} {mix:.2f}[{sat_out}]")
                if label in BAND_HEADROOM_DB:
                    headroom_db = BAND_HEADROOM_DB[label]
                    limit_linear = 10 ** (headroom_db / 20.0)
                    attack_ms, release_ms = _clamp_alimiter_times(1.0, 40.0)
                    parts.append(
                        f"[{sat_out}]alimiter=limit={limit_linear:.6f}:attack={attack_ms}:release={release_ms}[{out_label}]"
                    )
                else:
                    parts.append(f"[{sat_out}]anull[{out_label}]")
                continue
        parts.append(f"{band_chain}[{out_label}]")

    mix_label = "mb"
    normalize_flag = 1 if auto_band_gain else 0
    mix = (
        "".join(f"[{label}]" for label in band_outputs)
        + f"amix=inputs={len(BAND_CONFIG)}:normalize={normalize_flag}[{mix_label}]"
    )
    parts.append(mix)

    post_mix_limiter_label = "mbl"
    attack_ms, release_ms = _clamp_alimiter_times(1.0, 50.0)
    parts.append(
        f"[{mix_label}]alimiter=limit=0.95:attack={attack_ms}:release={release_ms}:level=false[{post_mix_limiter_label}]"
    )
    mix_label = post_mix_limiter_label

    if process_density >= 4:
        density_label = "mbd"
        parts.append(f"[{mix_label}]volume=-2.0dB[{density_label}]")
        mix_label = density_label
    elif process_density >= 3:
        density_label = "mbd"
        parts.append(f"[{mix_label}]volume=-1.0dB[{density_label}]")
        mix_label = density_label

    if auto_band_gain:
        gain_db = min(4.5, 20.0 * math.log10(len(BAND_CONFIG)))
        gain_label = "mbg"
        parts.append(f"[{mix_label}]volume={gain_db:.2f}dB[{gain_label}]")
        mix_label = gain_label
        post_gain_limiter_label = "mbgl"
        attack_ms, release_ms = _clamp_alimiter_times(1.0, 80.0)
        parts.append(
            f"[{mix_label}]alimiter=limit=0.98:attack={attack_ms}:release={release_ms}:level=false[{post_gain_limiter_label}]"
        )
        mix_label = post_gain_limiter_label

    return ";".join(parts), mix_label
