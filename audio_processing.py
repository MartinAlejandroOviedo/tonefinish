import pathlib
from typing import Dict, Tuple

from audio_tools import get_audio_duration, get_audio_sample_rate, run_ffmpeg
from config import (
    BAND_CONFIG,
    BRICKWALL_EXTRA_DB,
    DEFAULT_BAND_RANGE_DB,
    DEFAULT_MAX_ADJUST_DB,
    M4A_BITRATE,
    MP3_BITRATE,
    TRANSPARENT_BAND_RANGE_DB,
    TRANSPARENT_MAX_ADJUST_DB,
)


def build_deesser_filter(input_path: pathlib.Path, target_hz: float = 6000.0) -> str:
    """Construye un filtro de de-esser con frecuencia normalizada 0-1."""
    sample_rate = get_audio_sample_rate(str(input_path))
    if not sample_rate:
        return "deesser=i=0.5:m=0.5:f=0.5:s=0.5"
    nyquist = sample_rate / 2.0
    normalized = max(0.0, min(1.0, target_hz / nyquist))
    return f"deesser=i=0.5:m=0.5:f={normalized:.4f}:s=0.5"


def build_multiband_filter(
    band_stats: Dict[str, float] | None,
    apply_dynamic_eq: bool,
    apply_stereo_width: bool,
    input_label: str,
    band_range_db: float = DEFAULT_BAND_RANGE_DB,
    max_adjust_db: float = DEFAULT_MAX_ADJUST_DB,
) -> Tuple[str, str]:
    """Crea un filtergraph multibanda con compand y/o stereo width por banda."""
    split_labels = [f"b{i}" for i in range(len(BAND_CONFIG))]
    band_outputs = [f"c{i}" for i in range(len(BAND_CONFIG))]

    split = f"[{input_label}]asplit={len(BAND_CONFIG)}" + "".join(f"[{label}]" for label in split_labels)
    parts = [split]

    for idx, (label, low_hz, high_hz, attack_s, release_s, width) in enumerate(BAND_CONFIG):
        band_chain = f"[{split_labels[idx]}]highpass=f={low_hz},lowpass=f={high_hz}"

        if apply_dynamic_eq:
            if band_stats is None:
                raise RuntimeError("No hay análisis por bandas disponible para control dinámico.")
            rms = band_stats.get(label)
            if rms is None:
                raise RuntimeError(f"No hay RMS para la banda {label}.")

            low_thr = max(rms - band_range_db, -90.0)
            high_thr = min(rms + band_range_db, 0.0)

            points = (
                f"-90/{-90.0 + max_adjust_db:.2f}"
                f"|{low_thr:.2f}/{low_thr:.2f}"
                f"|{high_thr:.2f}/{high_thr:.2f}"
                f"|0/{-max_adjust_db:.2f}"
            )
            band_chain += f",compand=attacks={attack_s}:decays={release_s}:points={points}"

        if apply_stereo_width:
            width_clamped = max(0.015625, min(64.0, width))
            band_chain += f",stereotools=mlev=1:slev={width_clamped:.2f}"

        band_chain += f"[{band_outputs[idx]}]"
        parts.append(band_chain)

    mix_label = "mb"
    mix = "".join(f"[{label}]" for label in band_outputs) + f"amix=inputs={len(BAND_CONFIG)}:normalize=0[{mix_label}]"
    parts.append(mix)

    return ";".join(parts), mix_label


def build_glue_filter(
    threshold_db: float,
    ratio: float,
    attack_ms: float,
    release_ms: float,
    makeup_db: float,
) -> str:
    """Construye un filtro de compresion suave tipo glue."""
    attack_s = max(0.001, attack_ms / 1000.0)
    release_s = max(0.005, release_ms / 1000.0)
    makeup_linear = 10 ** (makeup_db / 20.0)
    makeup_linear = max(1.0, min(64.0, makeup_linear))
    return (
        "acompressor="
        f"threshold={threshold_db:.2f}dB:"
        f"ratio={ratio:.2f}:"
        f"attack={attack_s:.3f}:"
        f"release={release_s:.3f}:"
        f"makeup={makeup_linear:.2f}"
    )


def build_preprocess_chain(
    input_path: pathlib.Path,
    band_stats: Dict[str, float] | None,
    dynamic_eq: bool,
    stereo_width: bool,
    deesser: bool,
    glue_enabled: bool = False,
    glue_threshold_db: float = -18.0,
    glue_ratio: float = 1.6,
    glue_attack_ms: float = 20.0,
    glue_release_ms: float = 120.0,
    glue_makeup_db: float = 0.0,
    band_range_db: float = DEFAULT_BAND_RANGE_DB,
    max_adjust_db: float = DEFAULT_MAX_ADJUST_DB,
) -> Tuple[str, str]:
    """Construye el pre-proceso antes de loudnorm/limiter."""
    filter_chain = ""
    input_label = "0:a"
    if deesser:
        deesser_filter = build_deesser_filter(input_path)
        filter_chain = f"[0:a]{deesser_filter}[des]"
        input_label = "des"

    if dynamic_eq or stereo_width:
        filter_chain_mb, filter_output = build_multiband_filter(
            band_stats=band_stats,
            apply_dynamic_eq=dynamic_eq,
            apply_stereo_width=stereo_width,
            input_label=input_label,
            band_range_db=band_range_db,
            max_adjust_db=max_adjust_db,
        )
        filter_chain = ";".join(part for part in [filter_chain, filter_chain_mb] if part)
        input_label = filter_output

    if glue_enabled:
        glue_filter = build_glue_filter(
            threshold_db=glue_threshold_db,
            ratio=glue_ratio,
            attack_ms=glue_attack_ms,
            release_ms=glue_release_ms,
            makeup_db=glue_makeup_db,
        )
        glue_label = "glue"
        glue_chain = f"[{input_label}]{glue_filter}[{glue_label}]"
        filter_chain = ";".join(part for part in [filter_chain, glue_chain] if part)
        input_label = glue_label

    return filter_chain, input_label


def normalize_audio(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    stats: Dict[str, float],
    target_lufs: float,
    true_peak: float,
    overwrite: bool,
    verbose: bool,
    dynamic_eq: bool = False,
    band_stats: Dict[str, float] | None = None,
    brickwall: bool = False,
    deesser: bool = False,
    stereo_width: bool = False,
    glue_enabled: bool = False,
    glue_threshold_db: float = -18.0,
    glue_ratio: float = 1.6,
    glue_attack_ms: float = 20.0,
    glue_release_ms: float = 120.0,
    glue_makeup_db: float = 0.0,
    output_sr: int | None = None,
    output_bit_depth: str | None = None,
    output_format: str | None = None,
    metadata: Dict[str, str] | None = None,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    transparent_mode: bool = False,
) -> str:
    """Aplica la segunda pasada de loudnorm con los valores medidos."""
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"El archivo de salida {output_path} ya existe. Usa --overwrite para reemplazarlo.")

    filter_chain = ""
    filter_output = ""
    deesser_filter = build_deesser_filter(input_path)
    if dynamic_eq or stereo_width or deesser:
        band_range = TRANSPARENT_BAND_RANGE_DB if transparent_mode else DEFAULT_BAND_RANGE_DB
        max_adjust = TRANSPARENT_MAX_ADJUST_DB if transparent_mode else DEFAULT_MAX_ADJUST_DB
        filter_chain, filter_output = build_preprocess_chain(
            input_path=input_path,
            band_stats=band_stats,
            dynamic_eq=dynamic_eq,
            stereo_width=stereo_width,
            deesser=deesser,
            glue_enabled=glue_enabled,
            glue_threshold_db=glue_threshold_db,
            glue_ratio=glue_ratio,
            glue_attack_ms=glue_attack_ms,
            glue_release_ms=glue_release_ms,
            glue_makeup_db=glue_makeup_db,
            band_range_db=band_range,
            max_adjust_db=max_adjust,
        )

    loudnorm_filter = (
        f"loudnorm=I={target_lufs}:LRA=11:TP={true_peak}"
        f":measured_I={stats['input_i']}"
        f":measured_LRA={stats['input_lra']}"
        f":measured_TP={stats['input_tp']}"
        f":measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}"
        ":linear=true:print_format=summary"
    )
    limit_db = true_peak + BRICKWALL_EXTRA_DB
    limit_linear = max(0.0625, min(1.0, 10 ** (limit_db / 20.0)))
    limiter_filter = f"alimiter=limit={limit_linear:.6f}:attack=1:release=100"
    fade_filters: list[str] = []
    if fade_in > 0:
        fade_filters.append(f"afade=t=in:ss=0:d={fade_in:.3f}")
    if fade_out > 0:
        duration = get_audio_duration(str(input_path))
        if duration:
            start = max(0.0, duration - fade_out)
            fade_filters.append(f"afade=t=out:st={start:.3f}:d={fade_out:.3f}")

    codec_args: list[str] = []
    if output_sr:
        codec_args.extend(["-ar", str(output_sr)])
    if output_format:
        fmt = output_format.lower()
        if fmt in ("wav",):
            if output_bit_depth == "24":
                codec_args.extend(["-c:a", "pcm_s24le"])
            elif output_bit_depth == "16":
                codec_args.extend(["-c:a", "pcm_s16le"])
        elif fmt in ("aiff", "aif"):
            if output_bit_depth == "24":
                codec_args.extend(["-c:a", "pcm_s24be"])
            elif output_bit_depth == "16":
                codec_args.extend(["-c:a", "pcm_s16be"])
        elif fmt == "flac":
            codec_args.extend(["-c:a", "flac"])
            if output_bit_depth == "16":
                codec_args.extend(["-sample_fmt", "s16"])
            elif output_bit_depth == "24":
                codec_args.extend(["-sample_fmt", "s32"])
        elif fmt == "m4a":
            codec_args.extend(["-c:a", "aac", "-b:a", M4A_BITRATE])
        elif fmt == "mp3":
            codec_args.extend(["-c:a", "libmp3lame", "-b:a", MP3_BITRATE])
    else:
        if output_bit_depth == "24":
            codec_args.extend(["-c:a", "pcm_s24le"])
        elif output_bit_depth == "16":
            codec_args.extend(["-c:a", "pcm_s16le"])

    metadata_args: list[str] = []
    if metadata:
        for key, value in metadata.items():
            if value:
                metadata_args.extend(["-metadata", f"{key}={value}"])

    if filter_chain:
        tail_filters = [loudnorm_filter]
        if brickwall:
            tail_filters.append(limiter_filter)
        tail_filters.extend(fade_filters)
        filter_complex = f"{filter_chain};[{filter_output}]" + ",".join(tail_filters) + "[out]"
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y" if overwrite else "-n",
            "-i",
            str(input_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[out]",
            *metadata_args,
            *codec_args,
            str(output_path),
        ]
    else:
        if deesser:
            loudnorm_filter = f"{deesser_filter},{loudnorm_filter}"
        if brickwall:
            loudnorm_filter = f"{loudnorm_filter},{limiter_filter}"
        if fade_filters:
            loudnorm_filter = f"{loudnorm_filter}," + ",".join(fade_filters)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y" if overwrite else "-n",
            "-i",
            str(input_path),
            "-af",
            loudnorm_filter,
            *metadata_args,
            *codec_args,
            str(output_path),
        ]
    result = run_ffmpeg(cmd, verbose=verbose)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg falló en normalización: {result.stderr.strip()}")
    return result.stderr


def ensure_output_path(output_path: pathlib.Path, output_format: str | None) -> pathlib.Path:
    """Garantiza extensión para salida."""
    if not output_format:
        if output_path.suffix:
            return output_path
        return output_path.with_suffix(".wav")
    ext = output_format.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    if output_path.suffix.lower() != ext:
        return output_path.with_suffix(ext)
    return output_path
