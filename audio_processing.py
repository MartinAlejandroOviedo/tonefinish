import math
import os
import pathlib
import tempfile
from typing import Callable, Dict, Optional, Tuple

from audio_tools import get_audio_duration, get_audio_info, run_ffmpeg, run_ffmpeg_with_progress, _FFMPEG_BIN
from alternative_tools import analyze_loudness_ffmpeg, toolchain
from filter_graph_builder import FilterGraphBuilder
from mastering_config import MasteringConfig
from processes.contracts import AudioFunctionAction, AudioProcessContext
from processes.audit import TAIL_FUNCTION_IDS
from processes.orchestrator import migrate_legacy_preprocess_config, orchestrator
from mastering_modules.repair import (
    resolve_repair_levels as module_resolve_repair_levels,
)
from config import (
    BRICKWALL_EXTRA_DB,
    DEFAULT_BAND_RANGE_DB,
    DEFAULT_MAX_ADJUST_DB,
    M4A_BITRATE,
    MP3_BITRATE,
    TRANSPARENT_BAND_RANGE_DB,
    TRANSPARENT_MAX_ADJUST_DB,
    TRUE_PEAK_SAFETY_MARGIN_DB,
)

def _resolve_ffmpeg_target_compensation(
    *,
    target_lufs: float,
    true_peak: float,
    stats: Dict[str, float],
) -> tuple[float, float]:
    """
    Compensa la diferencia típica entre target solicitado y target realmente logrado por FFmpeg.

    Retorna:
      - target_lufs_compensated
      - true_peak_compensated
    """
    lufs_comp_db = float(os.getenv("TONEFINISH_FFMPEG_LUFS_COMP_DB", "0.0") or "0.0")
    tp_comp_db = float(os.getenv("TONEFINISH_FFMPEG_TP_COMP_DB", "0.0") or "0.0")

    input_lra = float(stats.get("input_lra", float("nan")))
    input_tp = float(stats.get("input_tp", float("nan")))

    # Material muy denso suele empujar más el techo real al final; agregamos margen.
    if math.isfinite(input_lra) and input_lra <= 4.5:
        tp_comp_db += 0.10
    if math.isfinite(input_lra) and input_lra <= 3.5:
        tp_comp_db += 0.05

    # Si llega con picos muy altos, reforzamos compensación de TP.
    if math.isfinite(input_tp) and input_tp >= -2.0:
        tp_comp_db += 0.10

    # Límites de seguridad para no sobrecompensar.
    lufs_comp_db = max(-0.60, min(0.60, lufs_comp_db))
    tp_comp_db = max(0.0, min(0.90, tp_comp_db))

    return target_lufs + lufs_comp_db, true_peak - tp_comp_db


def _is_ffmpeg_filter_assertion(stderr_text: str) -> bool:
    text = (stderr_text or "").lower()
    return (
        ("assertion best_input >= 0 failed" in text and "ffmpeg_filter.c" in text)
        or ("ffmpeg_filter.c" in text and "assertion" in text and "failed" in text)
    )


def _with_safe_filter_threading(cmd: list[str]) -> list[str]:
    if not cmd or cmd[0] != "ffmpeg":
        return cmd
    if "-filter_threads" in cmd or "-filter_complex_threads" in cmd:
        return cmd
    patched = cmd.copy()
    patched[1:1] = ["-filter_threads", "1", "-filter_complex_threads", "1"]
    return patched


def _with_safe_filter_threading_if_needed(cmd: list[str]) -> list[str]:
    if "-filter_complex" not in cmd:
        return cmd
    return _with_safe_filter_threading(cmd)


def resolve_repair_levels(
    stats: Dict[str, float] | None,
    noise_level: str,
    declip_level: str,
    declick_level: str,
) -> Tuple[str, str, str]:
    return module_resolve_repair_levels(
        stats=stats,
        noise_level=noise_level,
        declip_level=declip_level,
        declick_level=declick_level,
    )


def build_preprocess_chain(
    input_path: pathlib.Path,
    band_stats: Dict[str, float] | None,
    dynamic_eq: bool,
    stereo_width: bool,
    deesser: bool,
    **kwargs,
) -> Tuple[str, str]:
    """Construye el preproceso exclusivamente mediante el catálogo de plugins.

    La firma histórica se conserva como adaptador de configuración; ningún filtro
    DSP se implementa en esta función.
    """
    config = dict(kwargs)
    config.update({
        "input_path": input_path, "band_stats": band_stats,
        "dynamic_eq": dynamic_eq, "stereo_width": stereo_width,
        "deesser": deesser,
    })
    raw_ai_actions = config.get("audio_actions")
    if isinstance(raw_ai_actions, list):
        all_actions = [
            item if isinstance(item, AudioFunctionAction) else AudioFunctionAction.from_dict(item)
            for item in raw_ai_actions
        ]
        tail_ids = {
            "audio.repair.trim_silence", "audio.saturation.hard_clip",
            "audio.autogain.output_gain", "audio.loudness.normalize",
            "audio.loudness.fade_in", "audio.loudness.fade_out", "audio.limiter.true_peak",
        }
        actions = [action for action in all_actions if action.function_id not in tail_ids]
    else:
        actions = migrate_legacy_preprocess_config(**config)
    info = get_audio_info(str(input_path))
    sample_rate = int(info.get("sample_rate") or 48000)
    channels = int(info.get("channels") or 2)
    duration = info.get("duration")
    analysis = {
        "band_rms": band_stats or {}, "sample_rate": sample_rate,
        "duration": duration,
    }
    context = AudioProcessContext(
        audio_id=str(input_path), sample_rate=sample_rate, channels=channels,
        duration=float(duration) if isinstance(duration, (int, float)) else None,
        analysis=analysis,
    )
    graph = orchestrator.compile(actions, context)
    return graph.filter_chain, graph.output_label


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
    master_limiter_enabled: bool = False,
    master_limiter_mode: str = "transparent",
    master_limiter_ceiling_db: float = -1.0,
    master_limiter_release_ms: float = 150.0,
    master_limiter_lookahead_ms: float = 5.0,
    deesser: bool = False,
    deesser_freq_hz: float = 6000.0,
    deesser_intensity: float = 1.0,
    tone_low_db: float = 0.0,
    sub_bass_db: float = 0.0,
    tone_mid_db: float = 0.0,
    tone_high_db: float = 0.0,
    tone_tilt_db: float = 0.0,
    band_adjust_db: Dict[str, float] | None = None,
    band_widths: Dict[str, float] | None = None,
    auto_band_gain: bool = False,
    saturation_enabled: bool = False,
    saturation_per_band: bool = False,
    saturation_type: str = "Tape",
    saturation_drive_db: float = 0.0,
    saturation_mix: float = 0.0,
    saturation_band_drive_db: Dict[str, float] | None = None,
    saturation_band_mix: Dict[str, float] | None = None,
    process_order: list[str] | None = None,
    stereo_width: bool = False,
    stereo_dynamic: bool = False,
    stereo_dynamic_per_band: bool = False,
    stereo_dynamic_band_mix: list[float] | None = None,
    stereo_dynamic_threshold_db: float = -24.0,
    stereo_dynamic_ratio: float = 1.6,
    stereo_dynamic_attack_ms: float = 20.0,
    stereo_dynamic_release_ms: float = 150.0,
    stereo_dynamic_mix: float = 0.6,
    noise_reduction_level: str = "Off",
    declip_level: str = "Off",
    declick_level: str = "Off",
    pink_noise_level: str = "Off",
    glue_enabled: bool = False,
    glue_threshold_db: float = -18.0,
    glue_ratio: float = 1.4,
    glue_attack_ms: float = 20.0,
    glue_release_ms: float = 120.0,
    glue_knee_db: float = 6.0,
    glue_makeup_db: float = 0.0,
    headroom_db: float = -17.0,
    output_sr: int | None = None,
    output_bit_depth: str | None = None,
    output_format: str | None = None,
    metadata: Dict[str, str] | None = None,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    auto_fade_cap: bool = True,
    trim_edge_silence: bool = False,
    transparent_mode: bool = False,
    limiter_ceiling_db: float | None = None,
    limiter_release_ms: float | None = None,
    repair_enabled: bool = True,
    mix_enabled: bool = True,
    master_enabled: bool = True,
    autogain_enabled: bool = True,
    autogain_maxgain: float | None = None,
    multiband_limiter_enabled: bool = False,
    multiband_limiter_thresholds: Dict[str, float] | None = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    two_pass_normalize: bool = False,
    enable_clipper: bool = False,
    clipper_ceiling_db: float = -1.5,
    audio_actions: list[Dict[str, object]] | None = None,
) -> str:
    """Normaliza y procesa usando exclusivamente acciones del catálogo DSP."""
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"El archivo de salida {output_path} ya existe. Usa --overwrite para reemplazarlo."
        )

    measured_input_lra = float(stats.get("input_lra", float("nan")))
    if autogain_enabled and math.isfinite(measured_input_lra) and measured_input_lra <= 4.5:
        if autogain_maxgain is None:
            autogain_maxgain = 1.4
        else:
            autogain_maxgain = min(float(autogain_maxgain), 1.4)

    # === COMPENSACIÓN FEED-FORWARD DE TARGETS FFmpeg ===
    # Ajusta los targets solicitados para acercar el resultado real al esperado.
    compensated_target_lufs, compensated_true_peak = _resolve_ffmpeg_target_compensation(
        target_lufs=target_lufs,
        true_peak=true_peak,
        stats=stats,
    )

    # === APLICAR MARGEN DE SEGURIDAD PARA TRUE PEAK ===
    # FFmpeg no garantiza True Peak exacto debido a inter-sample peaks.
    # Restamos el margen para garantizar que el resultado real sea <= target.
    effective_true_peak = compensated_true_peak - TRUE_PEAK_SAFETY_MARGIN_DB

    filter_chain = ""
    filter_output = ""
    processing_cfg = MasteringConfig(
        dynamic_eq=dynamic_eq,
        stereo_width=stereo_width,
        deesser=deesser,
        saturation_enabled=saturation_enabled,
        saturation_per_band=saturation_per_band,
        stereo_dynamic=stereo_dynamic,
        glue_enabled=glue_enabled,
        auto_band_gain=auto_band_gain,
        tone_low_db=tone_low_db,
        tone_mid_db=tone_mid_db,
        tone_high_db=tone_high_db,
        tone_tilt_db=tone_tilt_db,
        band_adjust_db=band_adjust_db,
        band_widths=band_widths,
        noise_reduction_level=noise_reduction_level,
        declip_level=declip_level,
        declick_level=declick_level,
        pink_noise_level=pink_noise_level,
        repair_enabled=repair_enabled,
        mix_enabled=mix_enabled,
    )
    # === AUTO-AJUSTE DE HEADROOM PARA FUENTES MUY BAJAS ===
    # Si la fuente está muy por debajo del target, reducimos el headroom
    # para no enterrar la señal en el ruido de piso antes de procesar.
    source_lufs = float(stats.get("input_i", 0.0))
    if math.isfinite(source_lufs) and source_lufs < -25.0:
        gap = target_lufs - source_lufs
        if gap > 20.0:
            effective_headroom_db = -8.0
        elif gap > 12.0:
            effective_headroom_db = -12.0
        elif gap > 8.0:
            effective_headroom_db = -15.0
        else:
            effective_headroom_db = headroom_db
    else:
        effective_headroom_db = headroom_db

    ai_actions = [AudioFunctionAction.from_dict(item) for item in audio_actions] if audio_actions else []
    ai_preprocess_ids = {
        action.function_id for action in ai_actions
        if action.function_id not in TAIL_FUNCTION_IDS
    }
    preprocess_needed = bool(ai_preprocess_ids) or processing_cfg.needs_preprocess()
    master_loudness_stats: Dict[str, float] | None = None if preprocess_needed else stats
    if preprocess_needed:
        band_range = TRANSPARENT_BAND_RANGE_DB if transparent_mode else DEFAULT_BAND_RANGE_DB
        max_adjust = TRANSPARENT_MAX_ADJUST_DB if transparent_mode else DEFAULT_MAX_ADJUST_DB
        filter_chain, filter_output = build_preprocess_chain(
            input_path=input_path,
            band_stats=band_stats,
            dynamic_eq=dynamic_eq,
            stereo_width=stereo_width,
            deesser=deesser,
            deesser_freq_hz=deesser_freq_hz,
            deesser_intensity=deesser_intensity,
            tone_low_db=tone_low_db,
            sub_bass_db=sub_bass_db,
            tone_mid_db=tone_mid_db,
            tone_high_db=tone_high_db,
            tone_tilt_db=tone_tilt_db,
            band_adjust_db=band_adjust_db,
            band_widths=band_widths,
            auto_band_gain=auto_band_gain,
            saturation_enabled=saturation_enabled,
            saturation_per_band=saturation_per_band,
            saturation_type=saturation_type,
            saturation_drive_db=saturation_drive_db,
            saturation_mix=saturation_mix,
            saturation_band_drive_db=saturation_band_drive_db,
            saturation_band_mix=saturation_band_mix,
            process_order=process_order,
            stereo_dynamic=stereo_dynamic,
            stereo_dynamic_per_band=stereo_dynamic_per_band,
            stereo_dynamic_band_mix=stereo_dynamic_band_mix,
            stereo_dynamic_threshold_db=stereo_dynamic_threshold_db,
            stereo_dynamic_ratio=stereo_dynamic_ratio,
            stereo_dynamic_attack_ms=stereo_dynamic_attack_ms,
            stereo_dynamic_release_ms=stereo_dynamic_release_ms,
            stereo_dynamic_mix=stereo_dynamic_mix,
            noise_reduction_level=noise_reduction_level,
            declip_level=declip_level,
            declick_level=declick_level,
            pink_noise_level=pink_noise_level,
            glue_enabled=glue_enabled,
            glue_threshold_db=glue_threshold_db,
            glue_ratio=glue_ratio,
            glue_attack_ms=glue_attack_ms,
            glue_release_ms=glue_release_ms,
            glue_knee_db=glue_knee_db,
            glue_makeup_db=glue_makeup_db,
            band_range_db=band_range,
            max_adjust_db=max_adjust,
            headroom_db=effective_headroom_db,
            repair_enabled=repair_enabled,
            mix_enabled=mix_enabled,
            autogain_enabled=autogain_enabled,
            autogain_maxgain=autogain_maxgain,
            multiband_limiter_enabled=multiband_limiter_enabled,
            multiband_limiter_thresholds=multiband_limiter_thresholds,
            audio_actions=audio_actions,
        )

    # Fase A performance:
    # Activamos two-pass automático cuando el audio tiene poca dinámica
    # o los picos están cerca del límite. Esto da mediciones precisas
    # después del preproceso.
    if preprocess_needed and not two_pass_normalize:
        measured_input_tp = float(stats.get("input_tp", float("nan")))
        measured_input_lra = float(stats.get("input_lra", float("nan")))
        near_tp_limit = math.isfinite(measured_input_tp) and measured_input_tp > -6.0
        low_dynamic = math.isfinite(measured_input_lra) and measured_input_lra <= 6.0
        conservative_gain = autogain_maxgain is not None and float(autogain_maxgain) <= 3.0
        # Forzar two-pass cuando la fuente está muy lejos del target (>15 LU)
        # El modo single-pass no logra corregir gaps grandes.
        far_from_target = math.isfinite(source_lufs) and (target_lufs - source_lufs) > 15.0
        if low_dynamic or near_tp_limit or conservative_gain or far_from_target:
            two_pass_normalize = True

    # Si hay preproceso significativo, los stats originales ya no son válidos
    # porque saturación, glue, etc. cambian el nivel.
    if preprocess_needed:
        if two_pass_normalize:
            # Modo de dos pasadas REAL: procesar a temporal, analizar, luego normalizar
            # Esto es más lento pero mucho más preciso
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = pathlib.Path(tmp.name)
            
            try:
                # Pasada 1: Aplicar preproceso a archivo temporal (sin loudnorm)
                tmp_filter_complex = FilterGraphBuilder.preprocess_to_output(filter_chain, filter_output)
                tmp_cmd = [
                    _FFMPEG_BIN, "-hide_banner", "-nostdin", "-y",
                    "-i", str(input_path),
                    "-filter_complex", tmp_filter_complex,
                    "-map", "[out]",
                    "-c:a", "pcm_f32le",
                    str(tmp_path),
                ]
                tmp_cmd = _with_safe_filter_threading_if_needed(tmp_cmd)
                tmp_result = run_ffmpeg(tmp_cmd, verbose=verbose)
                if tmp_result.returncode != 0 and _is_ffmpeg_filter_assertion(tmp_result.stderr):
                    tmp_cmd_safe = _with_safe_filter_threading(tmp_cmd)
                    tmp_result = run_ffmpeg(tmp_cmd_safe, verbose=verbose)
                if tmp_result.returncode != 0:
                    raise RuntimeError(f"Pasada 1 falló: {tmp_result.stderr.strip()}")
                
                # Analizar el audio preprocesado
                measured_stats = analyze_loudness_ffmpeg(str(tmp_path))
                
                if measured_stats:
                    master_loudness_stats = measured_stats
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
    
    effective_fade_in = fade_in
    effective_fade_out = fade_out
    if auto_fade_cap and (fade_in > 0 or fade_out > 0):
        try:
            from audio_analysis import analyze_silence_edges
            auto_in, auto_out, _detail = analyze_silence_edges(str(input_path))
            if fade_in > 0 and auto_in > 0:
                effective_fade_in = min(fade_in, auto_in)
            if fade_out > 0 and auto_out > 0:
                effective_fade_out = min(fade_out, auto_out)
        except Exception:
            pass

    fade_filters: list[str] = []
    if effective_fade_in > 0:
        fade_filters.append(f"afade=t=in:ss=0:d={effective_fade_in:.3f}")
    if effective_fade_out > 0:
        duration = get_audio_duration(str(input_path))
        if duration:
            start = max(0.0, duration - effective_fade_out)
            fade_filters.append(f"afade=t=out:st={start:.3f}:d={effective_fade_out:.3f}")
    codec_args = _build_codec_args(output_sr, output_bit_depth, output_format)
    metadata_args = _build_metadata_args(metadata)

    # Si master_enabled=False, solo aplicamos los filtros de preprocess (si hay)
    if not master_enabled:
        if filter_chain:
            # Solo aplicar preprocess, sin loudnorm/limiter/fades
            filter_complex = FilterGraphBuilder.preprocess_to_output(filter_chain, filter_output)
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
            cmd = _with_safe_filter_threading_if_needed(cmd)
        else:
            # Sin preprocess ni master, solo copiar/convertir
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-y" if overwrite else "-n",
                "-i",
                str(input_path),
                *metadata_args,
                *codec_args,
                str(output_path),
            ]
        result = run_ffmpeg(cmd, verbose=verbose)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg falló: {result.stderr.strip()}")
        return result.stderr

    info = get_audio_info(str(input_path))
    input_sr = int(info.get("sample_rate") or 48000)
    input_channels = int(info.get("channels") or 2)
    input_duration = info.get("duration")
    master_context = AudioProcessContext(
        audio_id=str(input_path), sample_rate=input_sr, channels=input_channels,
        duration=float(input_duration) if isinstance(input_duration, (int, float)) else None,
        analysis={"loudness_stats": master_loudness_stats} if master_loudness_stats else {},
    )
    master_actions = [action for action in ai_actions if action.function_id in TAIL_FUNCTION_IDS]
    normalized_master_actions: list[AudioFunctionAction] = []
    for action in master_actions:
        params = dict(action.params)
        if action.function_id == "audio.loudness.normalize":
            params["target_lufs"] = compensated_target_lufs
            params["true_peak_db"] = min(float(params.get("true_peak_db", effective_true_peak)), effective_true_peak)
        normalized_master_actions.append(AudioFunctionAction(
            action.function_id, action.enabled, params, action.target,
            action.reason, action.confidence, action.operation, action.evidence,
        ))
    master_actions = normalized_master_actions
    if not master_actions:
        master_actions = [AudioFunctionAction(
            "audio.loudness.normalize",
            params={"target_lufs": compensated_target_lufs, "true_peak_db": effective_true_peak,
                    "lra": 11.0, "dual_mono": input_channels == 1},
        )]
        if effective_fade_in > 0:
            master_actions.append(AudioFunctionAction(
                "audio.loudness.fade_in", params={"duration_seconds": effective_fade_in}
            ))
        if effective_fade_out > 0:
            master_actions.append(AudioFunctionAction(
                "audio.loudness.fade_out", params={"duration_seconds": effective_fade_out}
            ))

    graph_parts = [filter_chain] if filter_chain else []
    current_label = filter_output if filter_chain else "0:a"
    if trim_edge_silence and not any(a.function_id == "audio.repair.trim_silence" for a in master_actions):
        trim_graph = orchestrator.compile([AudioFunctionAction(
            "audio.repair.trim_silence", params={
                "start_threshold_db": -50.0, "start_duration_seconds": 0.3,
                "end_threshold_db": -45.0, "end_duration_seconds": 1.5,
            },
        )], master_context, current_label)
        graph_parts.append(trim_graph.filter_chain)
        current_label = trim_graph.output_label
    # El limiter se compila después del resampling para mantener el ceiling real.
    limiter_actions = [a for a in master_actions if a.function_id == "audio.limiter.true_peak"]
    pre_limiter_actions = [a for a in master_actions if a.function_id != "audio.limiter.true_peak"]
    master_graph = orchestrator.compile(pre_limiter_actions, master_context, current_label)
    if master_graph.filter_chain:
        graph_parts.append(master_graph.filter_chain)
        current_label = master_graph.output_label

    if enable_clipper and not any(a.function_id == "audio.saturation.hard_clip" for a in master_actions):
        clip_graph = orchestrator.compile([AudioFunctionAction(
            "audio.saturation.hard_clip", params={"ceiling_db": clipper_ceiling_db},
        )], master_context, current_label)
        graph_parts.append(clip_graph.filter_chain)
        current_label = clip_graph.output_label
    if output_sr:
        graph_parts.append(f"[{current_label}]aresample={output_sr}[resampled]")
        current_label = "resampled"

    if limiter_actions or master_limiter_enabled:
        safe_ceiling = min(
            effective_true_peak,
            master_limiter_ceiling_db if master_limiter_ceiling_db is not None else effective_true_peak,
        )
        limiter_context = AudioProcessContext(
            audio_id=str(input_path), sample_rate=int(output_sr or input_sr),
            channels=input_channels, duration=master_context.duration,
            analysis={"true_peak": stats.get("input_tp"), "sample_rate": int(output_sr or input_sr)},
        )
        effective_limiter_actions = [AudioFunctionAction(
            action.function_id, action.enabled,
            {**dict(action.params), "ceiling_db": min(float(action.params.get("ceiling_db", safe_ceiling)), safe_ceiling)},
            action.target, action.reason, action.confidence, action.operation, action.evidence,
        ) for action in limiter_actions] or [AudioFunctionAction(
            "audio.limiter.true_peak", params={
                "ceiling_db": safe_ceiling, "release_ms": master_limiter_release_ms,
                "lookahead_ms": master_limiter_lookahead_ms, "mode": master_limiter_mode,
                "oversampling": 4,
            },
        )]
        limiter_graph = orchestrator.compile(effective_limiter_actions, limiter_context, current_label)
        graph_parts.append(limiter_graph.filter_chain)
        current_label = limiter_graph.output_label

    graph_parts.append(f"[{current_label}]anull[out]")
    filter_complex = ";".join(part for part in graph_parts if part)
    codec_args_final = []
    skip_next = False
    for arg in codec_args:
        if skip_next:
            skip_next = False
            continue
        if output_sr and arg == "-ar":
            skip_next = True
            continue
        codec_args_final.append(arg)
    cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-y" if overwrite else "-n",
        "-i", str(input_path), "-filter_complex", filter_complex, "-map", "[out]",
        *metadata_args, *codec_args_final, str(output_path),
    ]
    cmd = _with_safe_filter_threading_if_needed(cmd)
    cmd_str = " ".join(cmd)
    # Usar run_ffmpeg_with_progress si hay callback, sino run_ffmpeg normal
    if progress_callback:
        duration = get_audio_duration(str(input_path))
        if duration and duration > 0:
            result = run_ffmpeg_with_progress(cmd, duration, progress_callback, verbose=verbose)
        else:
            result = run_ffmpeg(cmd, verbose=verbose)
    else:
        result = run_ffmpeg(cmd, verbose=verbose)
    
    if result.returncode != 0 and _is_ffmpeg_filter_assertion(result.stderr):
        retry_cmd = _with_safe_filter_threading(cmd)
        result = run_ffmpeg(retry_cmd, verbose=verbose)

    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg falló en normalización:\n"
            f"CMD: {cmd_str}\n"
            f"{result.stderr.strip()}"
        )
    return result.stderr


def apply_output_gain(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    gain_db: float,
    true_peak: float,
    limiter_ceiling_db: float | None = None,
    limiter_release_ms: float | None = None,
    output_sr: int | None = None,
    output_bit_depth: str | None = None,
    output_format: str | None = None,
    metadata: Dict[str, str] | None = None,
    overwrite: bool = False,
    verbose: bool = False,
) -> str:
    """Aplica ganancia y límite final mediante el orquestador de plugins."""
    codec_args = _build_codec_args(output_sr, output_bit_depth, output_format)
    metadata_args = _build_metadata_args(metadata)
    limit_db = true_peak + BRICKWALL_EXTRA_DB
    if limiter_ceiling_db is not None:
        limit_db = min(limiter_ceiling_db, limit_db)
    release_ms = limiter_release_ms if limiter_release_ms is not None else 100.0
    info = get_audio_info(str(input_path))
    sample_rate = int(output_sr or info.get("sample_rate") or 48000)
    channels = int(info.get("channels") or 2)
    context = AudioProcessContext(
        str(input_path), sample_rate, channels,
        analysis={"true_peak": true_peak, "sample_rate": sample_rate},
    )
    graph = orchestrator.compile([
        AudioFunctionAction("audio.autogain.output_gain", params={"gain_db": max(-24.0, min(24.0, gain_db))}),
        AudioFunctionAction("audio.limiter.true_peak", params={
            "ceiling_db": max(-9.0, min(0.0, limit_db)), "release_ms": release_ms,
            "lookahead_ms": 5.0, "mode": "transparent", "oversampling": 4,
        }),
    ], context)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-y" if overwrite else "-n",
        "-i",
        str(input_path),
        "-filter_complex", graph.filter_chain,
        "-map", f"[{graph.output_label}]",
        *metadata_args,
        *codec_args,
        str(output_path),
    ]
    result = run_ffmpeg(cmd, verbose=verbose)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg falló en ajuste de ganancia: {result.stderr.strip()}")
    return result.stderr


def _build_codec_args(
    output_sr: int | None,
    output_bit_depth: str | None,
    output_format: str | None,
) -> list[str]:
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
    return codec_args


def _build_metadata_args(metadata: Dict[str, str] | None) -> list[str]:
    metadata_args: list[str] = []
    if metadata:
        for key, value in metadata.items():
            if value:
                metadata_args.extend(["-metadata", f"{key}={value}"])
    return metadata_args


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
