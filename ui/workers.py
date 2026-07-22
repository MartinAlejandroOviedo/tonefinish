from __future__ import annotations

import pathlib
import math
import re
import os
import shutil
import tempfile
import time
import threading
import json
import copy
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any, Callable, Dict, Optional, Tuple, NamedTuple

from logic_backend import (
    analyze_audio,
    analyze_audio_with_filter,
    analyze_eq_bands,
    analyze_eq_and_voice,
    analyze_voice_band,
    evaluate_mix,
    format_analysis_summary,
    write_analysis_toml,
    apply_output_gain,
    build_preprocess_chain,
    ensure_output_path,
    normalize_audio,
    resolve_repair_levels,
)
from analysis_mts import write_mts_artifacts
from adaptive_rollout_phase8 import (
    build_rollout_report,
    collect_rollout_item,
    write_rollout_report,
)
from adaptive_rollout_safety import get_rollout_flags
from auto_master_intelligence import AudioCharacteristics
from output_naming import mastered_output_stem
from audio_tools import clear_audio_info_cache
from logic_backend import (
    analyze_audio_for_automaster,
    analyze_batch_for_automaster,
    adapt_preset_to_audio,
    update_saturation_budgets_for_batch,
    spasm_batch_start,
    spasm_batch_status,
    spasm_batch_cancel,
    get_runtime_resource_info,
    cancel_running_ffmpeg_processes,
    ensure_ffmpeg_available,
    extract_loudnorm_stats,
    get_audio_info,
    get_processing_limits,
)
from cache import get_cached_analysis, save_analysis_cache
from config import (
    DEFAULT_BAND_RANGE_DB,
    DEFAULT_MAX_ADJUST_DB,
    TRANSPARENT_BAND_RANGE_DB,
    TRANSPARENT_MAX_ADJUST_DB,
    TRUE_PEAK_SAFETY_MARGIN_DB,
)
from resource_monitor import ResourceMonitor
from ui.qt_compat import QObject, Signal


# Tipo para resultados de pre-análisis batch
BatchAnalysisResult = Dict[str, Tuple[
    Dict[str, float],  # band_stats
    Optional[float],   # voice_rms
    Dict[str, float],  # raw_stats
]]

class SingleFileAnalysis(NamedTuple):
    path: pathlib.Path
    raw_stats: Dict[str, float]
    band_stats: Dict[str, float]
    voice_rms: Optional[float]


def _build_runtime_resource_info() -> Dict[str, Any]:
    try:
        info = get_runtime_resource_info()
        if isinstance(info, dict):
            return info
    except Exception:
        pass

    monitor = ResourceMonitor()
    snapshot = monitor.snapshot()
    gpu_snapshot = monitor.gpu_snapshot()
    return {
        "summary": snapshot.format_summary(),
        "cpu": {
            "cpu_count": snapshot.cpu_count,
            "cpu_percent": snapshot.cpu_percent,
            "memory_percent": snapshot.memory_percent,
            "memory_available_gb": snapshot.memory_available_gb,
            "ffmpeg_processes": snapshot.ffmpeg_processes,
        },
        "gpu": {
            "available": gpu_snapshot is not None,
            "backend": gpu_snapshot.backend if gpu_snapshot else "none",
            "device_count": gpu_snapshot.device_count if gpu_snapshot else 0,
            "name": gpu_snapshot.name if gpu_snapshot else None,
            "driver_version": gpu_snapshot.driver_version if gpu_snapshot else None,
            "utilization_percent": gpu_snapshot.utilization_percent if gpu_snapshot else None,
            "memory_total_mb": gpu_snapshot.memory_total_mb if gpu_snapshot else None,
            "memory_used_mb": gpu_snapshot.memory_used_mb if gpu_snapshot else None,
            "memory_free_mb": gpu_snapshot.memory_free_mb if gpu_snapshot else None,
        },
    }


def _format_runtime_resource_lines(resource_info: Dict[str, Any]) -> list[str]:
    lines = [f"Recursos runtime: {resource_info.get('summary', 'N/A')}"]
    engine_info = resource_info.get("engine")
    if isinstance(engine_info, dict):
        req = engine_info.get("requested_engine", "default")
        resolved = engine_info.get("resolved_backend", "unknown")
        fallback = engine_info.get("spasm_fallback_python_enabled")
        cli = engine_info.get("spasm_cli")
        lines.append(
            "Engine: "
            f"requested={req} | resolved={resolved} | "
            f"fallback_python={'on' if bool(fallback) else 'off'}"
        )
        if cli:
            lines.append(f"Engine CLI: {cli}")
    cpu_info = resource_info.get("cpu")
    if isinstance(cpu_info, dict):
        cpu_count = cpu_info.get("cpu_count")
        cpu_percent = cpu_info.get("cpu_percent")
        memory_percent = cpu_info.get("memory_percent")
        memory_available_gb = cpu_info.get("memory_available_gb")
        ffmpeg_processes = cpu_info.get("ffmpeg_processes")
        cpu_line = ["CPU"]
        if cpu_count is not None:
            cpu_line.append(f"{cpu_count} cores")
        if cpu_percent is not None:
            cpu_line.append(f"{float(cpu_percent):.0f}%")
        if memory_percent is not None:
            cpu_line.append(f"RAM {float(memory_percent):.0f}%")
        if memory_available_gb is not None:
            cpu_line.append(f"RAM libre {float(memory_available_gb):.1f} GB")
        if ffmpeg_processes is not None:
            cpu_line.append(f"FFmpeg {ffmpeg_processes}")
        lines.append(" | ".join(cpu_line))
    gpu_info = resource_info.get("gpu")
    if isinstance(gpu_info, dict):
        gpu_summary = "GPU no disponible"
        if gpu_info.get("available"):
            parts = [f"GPU devices={gpu_info.get('device_count', 'n/a')}"]
            if gpu_info.get("name"):
                parts.append(str(gpu_info["name"]))
            if gpu_info.get("utilization_percent") is not None:
                parts.append(f"GPU {float(gpu_info['utilization_percent']):.0f}%")
            if gpu_info.get("memory_free_mb") is not None:
                parts.append(f"VRAM libre {float(gpu_info['memory_free_mb']):.0f} MB")
            gpu_summary = " | ".join(parts)
        lines.append(f"GPU: {gpu_summary}")
    return lines


def _extract_loudnorm_output_stats(output: str) -> Dict[str, float] | None:
    """Extrae el resumen final `Output ...` de loudnorm desde el log de FFmpeg."""
    patterns = {
        "input_i": r"Output Integrated:\s*(-?(?:\d+(?:\.\d+)?|inf|nan))\s*LUFS",
        "input_tp": r"Output True Peak:\s*(-?(?:\d+(?:\.\d+)?|inf|nan))\s*dBTP",
        "input_lra": r"Output LRA:\s*(-?(?:\d+(?:\.\d+)?|inf|nan))\s*LU",
        "input_thresh": r"Output Threshold:\s*(-?(?:\d+(?:\.\d+)?|inf|nan))\s*LUFS",
        "target_offset": r"Target Offset:\s*(-?(?:\d+(?:\.\d+)?|inf|nan))\s*LU",
    }
    stats: Dict[str, float] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, output, re.IGNORECASE)
        if not match:
            continue
        try:
            stats[key] = float(match.group(1))
        except ValueError:
            continue
    return stats or None


def _calibration_safe_mode_enabled() -> bool:
    raw = (os.getenv("TONEFINISH_CALIBRATION_SAFE_MODE", "0") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _needs_severe_recalibration(
    *,
    post_stats: Dict[str, float],
    target_lufs: float,
    true_peak: float,
) -> bool:
    """
    Criterio de calidad para habilitar recalibración post-render.
    """
    tp_target_effective = true_peak - TRUE_PEAK_SAFETY_MARGIN_DB
    lufs_error = abs(float(post_stats.get("input_i", 0.0)) - target_lufs)
    tp_error = float(post_stats.get("input_tp", 0.0)) - tp_target_effective
    return lufs_error > 0.30 or tp_error > 0.20


def _calibrate_output_from_logs(
    *,
    output_path: pathlib.Path,
    initial_stats: Dict[str, float],
    target_lufs: float,
    true_peak: float,
    limiter_ceiling_db: float | None,
    limiter_release_ms: float | None,
    output_sr: int | None,
    output_bit_depth: str | None,
    output_format: str | None,
    metadata: Dict[str, str] | None,
    verbose: bool,
    emit_status: Callable[[str], None] | None = None,
) -> Tuple[Dict[str, float], str]:
    """Corrige LUFS/TP con realimentación basada en medición post-render."""
    # Calibración adaptativa: FFmpeg puede no obedecer 1:1 el ajuste pedido.
    # Se permite una segunda pasada para compensar ese desvío real medido.
    # Dos pasadas estabilizan mejor LUFS/TP cuando la primera corrección queda corta.
    # Hasta cuatro pasos acotados permiten corregir renders muy desviados sin
    # aplicar de una vez una ganancia agresiva (p. ej. 3.9 LU requiere tres
    # pasos con el límite conservador actual de 1.5 dB).
    max_iterations = 4
    lufs_tolerance = 0.20
    true_peak_tolerance = 0.15
    min_step_db = 0.08
    tp_target_effective = true_peak - TRUE_PEAK_SAFETY_MARGIN_DB
    stats = initial_stats
    log_lines: list[str] = []
    # Respuesta esperada del sistema: ~1 dB aplicado -> ~1 dB medido.
    # Se actualiza con la respuesta observada para compensar "desobediencia".
    gain_response = 1.0

    for attempt in range(1, max_iterations + 1):
        measured_lufs = float(stats.get("input_i", float("nan")))
        measured_tp = float(stats.get("input_tp", float("nan")))
        if not (math.isfinite(measured_lufs) and math.isfinite(measured_tp)):
            break

        delta_lufs = target_lufs - measured_lufs
        tp_headroom = tp_target_effective - measured_tp
        needs_lufs = abs(delta_lufs) > lufs_tolerance
        needs_tp = measured_tp > (tp_target_effective + true_peak_tolerance)
        if not needs_lufs and not needs_tp:
            break

        max_step_db = 0.85
        if abs(delta_lufs) > 3.0 or measured_tp > (tp_target_effective + 0.5):
            max_step_db = 1.5
        if abs(delta_lufs) > 5.0:
            max_step_db = 2.0
        if abs(delta_lufs) > 8.0:
            max_step_db = 2.5

        if needs_tp and not needs_lufs:
            gain_db = tp_headroom
        else:
            gain_db = delta_lufs
            if gain_db > 0:
                gain_db = min(gain_db, tp_headroom)
            if needs_tp:
                gain_db = min(gain_db, tp_headroom)
        if abs(gain_response) > 0.05:
            gain_db = gain_db / gain_response
        gain_db = max(-max_step_db, min(max_step_db, gain_db))
        if abs(gain_db) < min_step_db:
            if needs_tp:
                gain_db = -min_step_db
            else:
                break

        if emit_status:
            emit_status(
                f"Calibrando salida ({attempt}/{max_iterations}): "
                f"{gain_db:+.2f} dB, LUFS {measured_lufs:.2f}, TP {measured_tp:.2f} dBTP"
            )

        temp_path = output_path.with_name(f"{output_path.stem}.cal{attempt}{output_path.suffix}")
        apply_output_gain(
            input_path=output_path,
            output_path=temp_path,
            gain_db=gain_db,
            true_peak=true_peak,
            limiter_ceiling_db=limiter_ceiling_db,
            limiter_release_ms=limiter_release_ms,
            output_sr=output_sr,
            output_bit_depth=output_bit_depth,
            output_format=output_format,
            metadata=metadata,
            overwrite=True,
            verbose=verbose,
        )
        temp_path.replace(output_path)
        stats, _ = analyze_audio(output_path, target_lufs, true_peak, verbose=False)
        new_lufs = float(stats.get("input_i", float("nan")))
        new_tp = float(stats.get("input_tp", float("nan")))
        if (
            math.isfinite(new_lufs)
            and abs(gain_db) >= min_step_db
            and math.isfinite(measured_lufs)
        ):
            observed_response = (new_lufs - measured_lufs) / gain_db
            # Evitar valores extremos por ruido de medición.
            observed_response = max(0.35, min(1.65, observed_response))
            gain_response = 0.5 * gain_response + 0.5 * observed_response
        log_lines.append(
            "Calibracion "
            f"{attempt}: gain={gain_db:+.2f} dB | "
            f"LUFS {measured_lufs:.2f}->{new_lufs:.2f} | "
            f"TP {measured_tp:.2f}->{new_tp:.2f} dBTP | "
            f"resp={gain_response:.2f}"
        )

    return stats, "\n".join(log_lines)


def _verify_worker_ai_source(worker: Any, input_path: pathlib.Path) -> None:
    expected = getattr(worker, "_ai_source_fingerprint", None)
    actions = getattr(worker, "_ai_audio_actions", None)
    if expected and actions:
        from processes.audit import verify_audio_source

        verify_audio_source(input_path, str(expected))


def _build_preprocess_kwargs(
    worker: Any,
    *,
    input_path: pathlib.Path,
    band_stats: Dict[str, float] | None,
    dynamic_eq: bool,
    noise_level: str,
    declip_level: str,
    declick_level: str,
    band_range_db: float,
    max_adjust_db: float,
) -> Dict[str, Any]:
    _verify_worker_ai_source(worker, input_path)
    return {
        "input_path": input_path,
        "band_stats": band_stats,
        "dynamic_eq": dynamic_eq,
        "stereo_width": worker.stereo_width,
        "deesser": worker.deesser,
        "deesser_freq_hz": worker.deesser_freq_hz,
        "deesser_intensity": worker.deesser_intensity,
        "tone_low_db": worker.tone_low_db,
        "sub_bass_db": worker.sub_bass_db,
        "tone_mid_db": worker.tone_mid_db,
        "tone_high_db": worker.tone_high_db,
        "tone_tilt_db": worker.tone_tilt_db,
        "band_adjust_db": worker.band_adjust_db,
        "band_widths": worker.band_widths,
        "auto_band_gain": worker.auto_band_gain,
        "saturation_enabled": worker.saturation_enabled,
        "saturation_per_band": worker.saturation_per_band,
        "saturation_type": worker.saturation_type,
        "saturation_drive_db": worker.saturation_drive_db,
        "saturation_mix": worker.saturation_mix,
        "saturation_band_drive_db": worker.saturation_band_drive_db,
        "saturation_band_mix": worker.saturation_band_mix,
        "process_order": getattr(worker, "_auto_process_order", None) or worker.process_order,
        "stereo_dynamic": worker.stereo_dynamic,
        "stereo_dynamic_band_mix": worker.stereo_dynamic_band_mix,
        "stereo_dynamic_threshold_db": worker.stereo_dynamic_threshold_db,
        "stereo_dynamic_ratio": worker.stereo_dynamic_ratio,
        "stereo_dynamic_attack_ms": worker.stereo_dynamic_attack_ms,
        "stereo_dynamic_release_ms": worker.stereo_dynamic_release_ms,
        "stereo_dynamic_mix": worker.stereo_dynamic_mix,
        "noise_reduction_level": noise_level,
        "declip_level": declip_level,
        "declick_level": declick_level,
        "pink_noise_level": worker.pink_noise_level,
        "glue_enabled": worker.glue_enabled,
        "glue_threshold_db": worker.glue_threshold_db,
        "glue_ratio": worker.glue_ratio,
        "glue_attack_ms": worker.glue_attack_ms,
        "glue_release_ms": worker.glue_release_ms,
        "glue_makeup_db": worker.glue_makeup_db,
        "band_range_db": band_range_db,
        "max_adjust_db": max_adjust_db,
        "headroom_db": worker.headroom_db,
        "autogain_maxgain": worker.autogain_maxgain,
        "repair_enabled": worker.repair_enabled,
        "mix_enabled": worker.mix_enabled,
        "autogain_enabled": worker.autogain_enabled,
        "multiband_limiter_enabled": worker.multiband_limiter_enabled,
        "multiband_limiter_thresholds": worker.multiband_limiter_thresholds,
        "audio_actions": getattr(worker, "_ai_audio_actions", None),
    }


def _build_normalize_kwargs(
    worker: Any,
    *,
    input_path: pathlib.Path,
    dynamic_eq: bool,
    band_stats: Dict[str, float] | None,
    output_format: str | None,
    noise_level: str,
    declip_level: str,
    declick_level: str,
    fade_in: float,
    fade_out: float,
    master_enabled: bool | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> Dict[str, Any]:
    _verify_worker_ai_source(worker, input_path)
    raw_band_mix = list(worker.stereo_dynamic_band_mix or [])
    normalized_band_mix = [
        (float(v) / 100.0) if float(v) > 1.0 else float(v)
        for v in raw_band_mix
    ]
    stereo_dynamic_per_band = any(v > 0.0 for v in normalized_band_mix)

    return {
        "dynamic_eq": dynamic_eq,
        "band_stats": band_stats,
        "master_limiter_enabled": worker.master_limiter_enabled,
        "master_limiter_mode": worker.master_limiter_mode,
        "master_limiter_ceiling_db": worker.master_limiter_ceiling_db,
        "master_limiter_release_ms": worker.master_limiter_release_ms,
        "master_limiter_lookahead_ms": worker.master_limiter_lookahead_ms,
        "output_sr": worker.output_sr,
        "output_bit_depth": worker.output_bit_depth,
        "output_format": output_format,
        "stereo_width": worker.stereo_width,
        "deesser": worker.deesser,
        "deesser_freq_hz": worker.deesser_freq_hz,
        "deesser_intensity": worker.deesser_intensity,
        "tone_low_db": worker.tone_low_db,
        "sub_bass_db": worker.sub_bass_db,
        "tone_mid_db": worker.tone_mid_db,
        "tone_high_db": worker.tone_high_db,
        "tone_tilt_db": worker.tone_tilt_db,
        "band_adjust_db": worker.band_adjust_db,
        "band_widths": worker.band_widths,
        "auto_band_gain": worker.auto_band_gain,
        "saturation_enabled": worker.saturation_enabled,
        "saturation_per_band": worker.saturation_per_band,
        "saturation_type": worker.saturation_type,
        "saturation_drive_db": worker.saturation_drive_db,
        "saturation_mix": worker.saturation_mix,
        "saturation_band_drive_db": worker.saturation_band_drive_db,
        "saturation_band_mix": worker.saturation_band_mix,
        "process_order": getattr(worker, "_auto_process_order", None) or worker.process_order,
        "stereo_dynamic": worker.stereo_dynamic,
        "stereo_dynamic_per_band": stereo_dynamic_per_band,
        "stereo_dynamic_band_mix": normalized_band_mix,
        "stereo_dynamic_threshold_db": worker.stereo_dynamic_threshold_db,
        "stereo_dynamic_ratio": worker.stereo_dynamic_ratio,
        "stereo_dynamic_attack_ms": worker.stereo_dynamic_attack_ms,
        "stereo_dynamic_release_ms": worker.stereo_dynamic_release_ms,
        "stereo_dynamic_mix": worker.stereo_dynamic_mix,
        "glue_enabled": worker.glue_enabled,
        "glue_threshold_db": worker.glue_threshold_db,
        "glue_ratio": worker.glue_ratio,
        "glue_attack_ms": worker.glue_attack_ms,
        "glue_release_ms": worker.glue_release_ms,
        "glue_makeup_db": worker.glue_makeup_db,
        "limiter_ceiling_db": worker.limiter_ceiling_db,
        "limiter_release_ms": worker.limiter_release_ms,
        "metadata": worker.metadata,
        "noise_reduction_level": noise_level,
        "declip_level": declip_level,
        "declick_level": declick_level,
        "pink_noise_level": worker.pink_noise_level,
        "fade_in": fade_in,
        "fade_out": fade_out,
        "transparent_mode": worker.transparent_mode,
        "headroom_db": worker.headroom_db,
        "autogain_maxgain": worker.autogain_maxgain,
        "repair_enabled": worker.repair_enabled,
        "mix_enabled": worker.mix_enabled,
        "master_enabled": worker.master_enabled if master_enabled is None else master_enabled,
        "autogain_enabled": worker.autogain_enabled,
        "multiband_limiter_enabled": worker.multiband_limiter_enabled,
        "multiband_limiter_thresholds": worker.multiband_limiter_thresholds,
        "progress_callback": progress_callback,
        "audio_actions": getattr(worker, "_ai_audio_actions", None),
    }


class AnalyzeWorker(QObject):
    progress = Signal(str, int, int)
    finished = Signal(dict, dict, list, object, str)
    error = Signal(str)

    def __init__(
        self,
        input_path: pathlib.Path,
        target_lufs: float,
        true_peak: float,
        verbose: bool,
        transparent_mode: bool,
        use_cache: bool = True,  # Nueva opción para usar caché
    ) -> None:
        super().__init__()
        self.input_path = input_path
        self.target_lufs = target_lufs
        self.true_peak = true_peak
        self.verbose = verbose
        self.transparent_mode = transparent_mode
        self.use_cache = use_cache

    def run(self) -> None:
        try:
            ensure_ffmpeg_available()
            self.progress.emit("Preparando análisis...", 0, 4)
            band_range = TRANSPARENT_BAND_RANGE_DB if self.transparent_mode else DEFAULT_BAND_RANGE_DB
            resource_info = _build_runtime_resource_info()
            resource_lines = _format_runtime_resource_lines(resource_info)
            
            # Intentar obtener análisis del caché
            if self.use_cache:
                cached = get_cached_analysis(self.input_path)
                if cached:
                    self.progress.emit("Caché encontrado: recalculando métricas...", 1, 4)
                    # Caché encontrado - usar datos guardados
                    # Pero necesitamos re-ejecutar analyze_audio para obtener stats
                    # ya que depende de target_lufs y true_peak actuales
                    stats, log = analyze_audio(
                        self.input_path, 
                        self.target_lufs, 
                        self.true_peak, 
                        verbose=self.verbose
                    )
                    log = "\n".join([*resource_lines, log]) if log else "\n".join(resource_lines)
                    # Usar band_stats y voice_rms del caché (estos no cambian)
                    band_stats = cached.get('band_stats', {})
                    suggestions = cached.get('suggestions', [])
                    voice_rms = cached.get('voice_rms')
                    self.progress.emit("Análisis completado.", 4, 4)
                    self.finished.emit(stats, band_stats, suggestions, voice_rms, log)
                    return
            
            # Sin caché - análisis completo
            self.progress.emit("Analizando loudness...", 1, 4)
            stats, log = analyze_audio(
                self.input_path, 
                self.target_lufs, 
                self.true_peak, 
                verbose=self.verbose
            )
            log = "\n".join([*resource_lines, log]) if log else "\n".join(resource_lines)
            self.progress.emit("Analizando bandas EQ y vocal...", 2, 4)
            band_stats, suggestions, voice_rms = analyze_eq_and_voice(
                self.input_path,
                verbose=self.verbose,
                band_range_db=band_range,
            )
            
            # Guardar en caché para futuras consultas
            if self.use_cache:
                self.progress.emit("Guardando resultados...", 4, 4)
                audio_info = get_audio_info(str(self.input_path))
                save_analysis_cache(
                    self.input_path,
                    stats,
                    band_stats,
                    suggestions,
                    voice_rms,
                    audio_info,
                )
            
            self.progress.emit("Análisis completado.", 4, 4)
            self.finished.emit(stats, band_stats, suggestions, voice_rms, log)
        except Exception as exc:
            self.error.emit(str(exc))


class AutoMasterAnalysisWorker(QObject):
    progress = Signal(str, int, int)
    finished = Signal(object, object, object)
    error = Signal(str)

    def __init__(self, input_path: pathlib.Path, verbose: bool = False) -> None:
        super().__init__()
        self.input_path = input_path
        self.verbose = verbose
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()
        cancel_running_ffmpeg_processes()

    def run(self) -> None:
        try:
            if self._cancel_event.is_set():
                self.error.emit("Proceso cancelado por el usuario.")
                return
            ensure_ffmpeg_available()
            self.progress.emit("Preparando Auto-Master...", 0, 3)
            self.progress.emit("Analizando contenido...", 1, 3)
            characteristics, recommendations, spectrum_data = analyze_audio_for_automaster(
                input_path=self.input_path,
                verbose=self.verbose,
                use_spectrum=True,
                full_analysis=True,
            )
            if self._cancel_event.is_set():
                self.error.emit("Proceso cancelado por el usuario.")
                return
            self.progress.emit("Adaptando preset...", 2, 3)
            self.progress.emit("Auto-Master completado.", 3, 3)
            self.finished.emit(characteristics, recommendations, spectrum_data)
        except Exception as exc:
            self.error.emit(str(exc))


class BatchAutoMasterWorker(QObject):
    progress = Signal(str, int, int)
    finished = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        files: list[pathlib.Path],
        style: str,
        target_lufs: float,
        true_peak: float,
        verbose: bool = False,
        use_spectrum: bool = False,
        max_files_to_analyze: int = 5,
        minimal_lra_threshold: float = 4.5,
        minimal_crest_threshold: float = 8.5,
        motion_profile_preference: str = "auto",
        motion_amount: float = 1.0,
        block_mode: bool = False,
        ia_providers: list | None = None,
    ) -> None:
        super().__init__()
        self.files = files
        self.style = style
        self.target_lufs = target_lufs
        self.true_peak = true_peak
        self.verbose = verbose
        self.use_spectrum = use_spectrum
        self.max_files_to_analyze = max_files_to_analyze
        self.minimal_lra_threshold = minimal_lra_threshold
        self.minimal_crest_threshold = minimal_crest_threshold
        self.motion_profile_preference = motion_profile_preference
        self.motion_amount = motion_amount
        self.block_mode = block_mode
        self.ia_providers = ia_providers
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()
        cancel_running_ffmpeg_processes()

    def run(self) -> None:
        try:
            if self._cancel_event.is_set():
                self.error.emit("Proceso cancelado por el usuario.")
                return
            ensure_ffmpeg_available()

            def progress_callback(idx: int, total: int, name: str) -> None:
                if self._cancel_event.is_set():
                    raise RuntimeError("Proceso cancelado por el usuario.")
                self.progress.emit(f"Analizando: {name}", idx, total)

            merged_chars, recommendations, individual_results = analyze_batch_for_automaster(
                files=self.files,
                verbose=self.verbose,
                use_spectrum=self.use_spectrum,
                max_files_to_analyze=self.max_files_to_analyze,
                progress_callback=progress_callback,
            )
            if self._cancel_event.is_set():
                self.error.emit("Proceso cancelado por el usuario.")
                return
            adjustments = adapt_preset_to_audio(
                self.style,
                merged_chars,
                minimal_lra_threshold=self.minimal_lra_threshold,
                minimal_crest_threshold=self.minimal_crest_threshold,
                motion_profile_preference=self.motion_profile_preference,
                motion_amount=self.motion_amount,
                block_mode=self.block_mode,
                ia_providers=self.ia_providers,
                target_lufs=self.target_lufs,
                true_peak=self.true_peak,
            )
            individual_results = update_saturation_budgets_for_batch(individual_results, adjustments)
            self.finished.emit(
                {
                    "merged_chars": merged_chars,
                    "recommendations": recommendations,
                    "individual_results": individual_results,
                    "adjustments": adjustments,
                }
            )
        except Exception as exc:
            self.error.emit(str(exc))


class MTSAnalysisWorker(QObject):
    """
    Worker dedicado para análisis temporal MTS.
    No altera audio; solo genera artefactos de diagnóstico.
    """

    progress = Signal(str, int, int)
    finished = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        tasks: list[tuple[pathlib.Path, pathlib.Path]],
    ) -> None:
        super().__init__()
        self.tasks = tasks

    def run(self) -> None:
        try:
            total = len(self.tasks)
            if total == 0:
                self.finished.emit([])
                return
            results: list[dict[str, str]] = []
            for idx, (input_path, output_path) in enumerate(self.tasks, start=1):
                self.progress.emit(
                    f"Análisis temporal {idx}/{total}: {input_path.name}",
                    idx,
                    total,
                )
                paths = write_mts_artifacts(
                    input_path=input_path,
                    output_path=output_path,
                )
                results.append(
                    {
                        "input": str(input_path),
                        "output": str(output_path),
                        "mts_json": str(paths["json_path"]),
                        "mts_md": str(paths["md_path"]),
                    }
                )
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


class NormalizeWorker(QObject):
    progress = Signal(str, int, int)
    finished = Signal(str, str)
    error = Signal(str)
    processing_progress = Signal(float, str)

    def __init__(
        self,
        input_path: pathlib.Path,
        output_path: pathlib.Path,
        stats: Dict[str, float],
        band_stats: Dict[str, float] | None,
        target_lufs: float,
        true_peak: float,
        overwrite: bool,
        verbose: bool,
        dynamic_eq: bool,
        master_limiter_enabled: bool,
        master_limiter_mode: str,
        master_limiter_ceiling_db: float,
        master_limiter_release_ms: float,
        master_limiter_lookahead_ms: float,
        output_sr: int | None,
        output_bit_depth: str | None,
        output_format: str | None,
        stereo_width: bool,
        deesser: bool,
        deesser_freq_hz: float,
        deesser_intensity: float,
        tone_low_db: float,
        sub_bass_db: float,
        tone_mid_db: float,
        tone_high_db: float,
        tone_tilt_db: float,
        band_adjust_db: Dict[str, float],
        band_widths: Dict[str, float],
        auto_band_gain: bool,
        saturation_enabled: bool,
        saturation_per_band: bool,
        saturation_type: str,
        saturation_drive_db: float,
        saturation_mix: float,
        saturation_band_drive_db: Dict[str, float],
        saturation_band_mix: Dict[str, float],
        process_order: list[str],
        stereo_dynamic: bool,
        stereo_dynamic_band_mix: list[float],
        stereo_dynamic_threshold_db: float,
        stereo_dynamic_ratio: float,
        stereo_dynamic_attack_ms: float,
        stereo_dynamic_release_ms: float,
        stereo_dynamic_mix: float,
        glue_enabled: bool,
        glue_threshold_db: float,
        glue_ratio: float,
        glue_attack_ms: float,
        glue_release_ms: float,
        glue_makeup_db: float,
        limiter_ceiling_db: float | None,
        limiter_release_ms: float | None,
        metadata: Dict[str, str] | None,
        fade_in: float,
        fade_out: float,
        transparent_mode: bool,
        noise_reduction_level: str,
        declip_level: str,
        declick_level: str,
        pink_noise_level: str = "Off",
        repair_enabled: bool = True,
        mix_enabled: bool = True,
        master_enabled: bool = True,
        autogain_enabled: bool = True,
        autogain_maxgain: float | None = None,
        multiband_limiter_enabled: bool = False,
        multiband_limiter_thresholds: Dict[str, float] | None = None,
    ) -> None:
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.stats = stats
        self.band_stats = band_stats
        self.target_lufs = target_lufs
        self.true_peak = true_peak
        self.overwrite = overwrite
        self.verbose = verbose
        self.dynamic_eq = dynamic_eq
        self.master_limiter_enabled = master_limiter_enabled
        self.master_limiter_mode = master_limiter_mode
        self.master_limiter_ceiling_db = master_limiter_ceiling_db
        self.master_limiter_release_ms = master_limiter_release_ms
        self.master_limiter_lookahead_ms = master_limiter_lookahead_ms
        self.output_sr = output_sr
        self.output_bit_depth = output_bit_depth
        self.output_format = output_format
        self.stereo_width = stereo_width
        self.deesser = deesser
        self.deesser_freq_hz = deesser_freq_hz
        self.deesser_intensity = deesser_intensity
        self.tone_low_db = tone_low_db
        self.sub_bass_db = sub_bass_db
        self.tone_mid_db = tone_mid_db
        self.tone_high_db = tone_high_db
        self.tone_tilt_db = tone_tilt_db
        self.band_adjust_db = band_adjust_db
        self.band_widths = band_widths
        self.auto_band_gain = auto_band_gain
        self.saturation_enabled = saturation_enabled
        self.saturation_per_band = saturation_per_band
        self.saturation_type = saturation_type
        self.saturation_drive_db = saturation_drive_db
        self.saturation_mix = saturation_mix
        self.saturation_band_drive_db = saturation_band_drive_db
        self.saturation_band_mix = saturation_band_mix
        self.process_order = process_order
        self.stereo_dynamic = stereo_dynamic
        self.stereo_dynamic_band_mix = stereo_dynamic_band_mix
        self.stereo_dynamic_threshold_db = stereo_dynamic_threshold_db
        self.stereo_dynamic_ratio = stereo_dynamic_ratio
        self.stereo_dynamic_attack_ms = stereo_dynamic_attack_ms
        self.stereo_dynamic_release_ms = stereo_dynamic_release_ms
        self.stereo_dynamic_mix = stereo_dynamic_mix
        self.glue_enabled = glue_enabled
        self.glue_threshold_db = glue_threshold_db
        self.glue_ratio = glue_ratio
        self.glue_attack_ms = glue_attack_ms
        self.glue_release_ms = glue_release_ms
        self.glue_makeup_db = glue_makeup_db
        self.limiter_ceiling_db = limiter_ceiling_db
        self.limiter_release_ms = limiter_release_ms
        self.metadata = metadata
        self.fade_in = fade_in
        self.fade_out = fade_out
        self.transparent_mode = transparent_mode
        self.noise_reduction_level = noise_reduction_level
        self.declip_level = declip_level
        self.declick_level = declick_level
        self.pink_noise_level = pink_noise_level
        self.repair_enabled = repair_enabled
        self.mix_enabled = mix_enabled
        self.master_enabled = master_enabled
        self.autogain_enabled = autogain_enabled
        self.multiband_limiter_enabled = multiband_limiter_enabled
        self.multiband_limiter_thresholds = multiband_limiter_thresholds
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()
        cancel_running_ffmpeg_processes()

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise RuntimeError("Proceso cancelado por el usuario.")

    def run(self) -> None:
        try:
            self._raise_if_cancelled()
            ensure_ffmpeg_available()
            self.progress.emit("Preparando normalización...", 0, 3)
            effective_master_enabled = True
            if not self.master_enabled:
                self.progress.emit(
                    "Aviso: 'Mastering habilitado' estaba en OFF. Se fuerza ON para render de salida.",
                    0,
                    3,
                )
            noise_level, declip_level, declick_level = resolve_repair_levels(
                self.stats, self.noise_reduction_level, self.declip_level, self.declick_level
            )
            self.progress.emit("Construyendo cadena de proceso...", 1, 3)
            def on_ffmpeg_progress(percent: float, time_str: str) -> None:
                self._raise_if_cancelled()
                self.processing_progress.emit(percent, time_str)
            normalize_kwargs = _build_normalize_kwargs(
                self,
                input_path=self.input_path,
                dynamic_eq=self.dynamic_eq,
                band_stats=self.band_stats,
                output_format=self.output_format,
                noise_level=noise_level,
                declip_level=declip_level,
                declick_level=declick_level,
                fade_in=self.fade_in,
                fade_out=self.fade_out,
                master_enabled=effective_master_enabled,
                progress_callback=on_ffmpeg_progress,
            )
            self.progress.emit("Normalizando audio...", 2, 3)
            self._raise_if_cancelled()
            log = normalize_audio(
                input_path=self.input_path,
                output_path=self.output_path,
                stats=self.stats,
                target_lufs=self.target_lufs,
                true_peak=self.true_peak,
                overwrite=self.overwrite,
                verbose=self.verbose,
                **normalize_kwargs,
            )
            self._raise_if_cancelled()
            self.progress.emit("Finalizando...", 3, 3)
            self.finished.emit(log, str(self.output_path))
        except Exception as exc:
            self.error.emit(str(exc))


class ProcessWorker(QObject):
    finished = Signal(dict, dict, list, object, str, str, object, object, object, object, object, object, object)
    error = Signal(str)
    progress = Signal(str, int, int)
    processing_progress = Signal(float, str)  # percent, time_str - progreso detallado de FFmpeg

    def __init__(
        self,
        input_path: pathlib.Path,
        output_path: pathlib.Path,
        target_lufs: float,
        true_peak: float,
        overwrite: bool,
        verbose: bool,
        dynamic_eq: bool,
        master_limiter_enabled: bool,
        master_limiter_mode: str,
        master_limiter_ceiling_db: float,
        master_limiter_release_ms: float,
        master_limiter_lookahead_ms: float,
        analyze_only: bool,
        output_sr: int | None,
        output_bit_depth: str | None,
        output_format: str | None,
        stereo_width: bool,
        loudness_preset: str,
        output_preset: str,
        deesser: bool,
        deesser_freq_hz: float,
        deesser_intensity: float,
        tone_low_db: float,
        sub_bass_db: float,
        tone_mid_db: float,
        tone_high_db: float,
        tone_tilt_db: float,
        band_adjust_db: Dict[str, float],
        band_widths: Dict[str, float],
        auto_band_gain: bool,
        saturation_enabled: bool,
        saturation_per_band: bool,
        saturation_type: str,
        saturation_drive_db: float,
        saturation_mix: float,
        saturation_band_drive_db: Dict[str, float],
        saturation_band_mix: Dict[str, float],
        process_order: list[str],
        stereo_dynamic: bool,
        stereo_dynamic_band_mix: list[float],
        stereo_dynamic_threshold_db: float,
        stereo_dynamic_ratio: float,
        stereo_dynamic_attack_ms: float,
        stereo_dynamic_release_ms: float,
        stereo_dynamic_mix: float,
        glue_enabled: bool,
        glue_threshold_db: float,
        glue_ratio: float,
        glue_attack_ms: float,
        glue_release_ms: float,
        glue_makeup_db: float,
        limiter_ceiling_db: float | None,
        limiter_release_ms: float | None,
        metadata: Dict[str, str] | None,
        fade_in: float,
        fade_out: float,
        transparent_mode: bool,
        headroom_db: float,
        noise_reduction_level: str,
        declip_level: str,
        declick_level: str,
        pink_noise_level: str = "Off",
        repair_enabled: bool = True,
        mix_enabled: bool = True,
        master_enabled: bool = True,
        autogain_enabled: bool = True,
        autogain_maxgain: float | None = None,
        multiband_limiter_enabled: bool = False,
        multiband_limiter_thresholds: Dict[str, float] | None = None,
        pre_analysis_stats: Dict[str, float] | None = None,
        pre_analysis_band_stats: Dict[str, float] | None = None,
        pre_analysis_voice_rms: float | None = None,
    ) -> None:
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.target_lufs = target_lufs
        self.true_peak = true_peak
        self.overwrite = overwrite
        self.verbose = verbose
        self.dynamic_eq = dynamic_eq
        self.master_limiter_enabled = master_limiter_enabled
        # Back-compat: "brickwall" era el nombre histórico del limitador maestro.
        self.brickwall = master_limiter_enabled
        self.master_limiter_mode = master_limiter_mode
        self.master_limiter_ceiling_db = master_limiter_ceiling_db
        self.master_limiter_release_ms = master_limiter_release_ms
        self.master_limiter_lookahead_ms = master_limiter_lookahead_ms
        self.analyze_only = analyze_only
        self.output_sr = output_sr
        self.output_bit_depth = output_bit_depth
        self.output_format = output_format
        self.stereo_width = stereo_width
        self.loudness_preset = loudness_preset
        self.output_preset = output_preset
        self.deesser = deesser
        self.deesser_freq_hz = deesser_freq_hz
        self.deesser_intensity = deesser_intensity
        self.tone_low_db = tone_low_db
        self.sub_bass_db = sub_bass_db
        self.tone_mid_db = tone_mid_db
        self.tone_high_db = tone_high_db
        self.tone_tilt_db = tone_tilt_db
        self.band_adjust_db = band_adjust_db
        self.band_widths = band_widths
        self.auto_band_gain = auto_band_gain
        self.saturation_enabled = saturation_enabled
        self.saturation_per_band = saturation_per_band
        self.saturation_type = saturation_type
        self.saturation_drive_db = saturation_drive_db
        self.saturation_mix = saturation_mix
        self.saturation_band_drive_db = saturation_band_drive_db
        self.saturation_band_mix = saturation_band_mix
        self.process_order = process_order
        self.stereo_dynamic = stereo_dynamic
        self.stereo_dynamic_band_mix = stereo_dynamic_band_mix
        self.stereo_dynamic_threshold_db = stereo_dynamic_threshold_db
        self.stereo_dynamic_ratio = stereo_dynamic_ratio
        self.stereo_dynamic_attack_ms = stereo_dynamic_attack_ms
        self.stereo_dynamic_release_ms = stereo_dynamic_release_ms
        self.stereo_dynamic_mix = stereo_dynamic_mix
        self.glue_enabled = glue_enabled
        self.glue_threshold_db = glue_threshold_db
        self.glue_ratio = glue_ratio
        self.glue_attack_ms = glue_attack_ms
        self.glue_release_ms = glue_release_ms
        self.glue_makeup_db = glue_makeup_db
        self.limiter_ceiling_db = limiter_ceiling_db
        self.limiter_release_ms = limiter_release_ms
        self.metadata = metadata
        self.fade_in = fade_in
        self.fade_out = fade_out
        self.transparent_mode = transparent_mode
        self.headroom_db = headroom_db
        self.autogain_maxgain = autogain_maxgain
        self.noise_reduction_level = noise_reduction_level
        self.declip_level = declip_level
        self.declick_level = declick_level
        self.pink_noise_level = pink_noise_level
        self.repair_enabled = repair_enabled
        self.mix_enabled = mix_enabled
        self.master_enabled = master_enabled
        self.autogain_enabled = autogain_enabled
        self.autogain_maxgain = autogain_maxgain
        self.multiband_limiter_enabled = multiband_limiter_enabled
        self.multiband_limiter_thresholds = multiband_limiter_thresholds
        self.pre_analysis_stats = pre_analysis_stats
        self.pre_analysis_band_stats = pre_analysis_band_stats
        self.pre_analysis_voice_rms = pre_analysis_voice_rms
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()
        cancel_running_ffmpeg_processes()

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise RuntimeError("Proceso cancelado por el usuario.")

    def run(self) -> None:
        try:
            self._raise_if_cancelled()
            ensure_ffmpeg_available()
            step_idx = 0
            total_steps = 0

            def emit_step(message: str) -> None:
                nonlocal step_idx
                step_idx += 1
                self.progress.emit(message, step_idx, total_steps)

            def emit_status(message: str) -> None:
                self.progress.emit(message, step_idx, total_steps)

            emit_status("Preparando auto-master...")
            resource_info = _build_runtime_resource_info()
            resource_lines = _format_runtime_resource_lines(resource_info)

            band_range = TRANSPARENT_BAND_RANGE_DB if self.transparent_mode else DEFAULT_BAND_RANGE_DB
            max_adjust = TRANSPARENT_MAX_ADJUST_DB if self.transparent_mode else DEFAULT_MAX_ADJUST_DB

            if self.pre_analysis_band_stats is not None:
                band_stats = self.pre_analysis_band_stats
                suggestions = []
                emit_status("Usando análisis inteligente previo...")
            else:
                self._raise_if_cancelled()
                band_stats, suggestions, voice_rms = analyze_eq_and_voice(
                    self.input_path,
                    verbose=self.verbose,
                    band_range_db=band_range,
                )

            if self.pre_analysis_voice_rms is not None:
                voice_rms = self.pre_analysis_voice_rms
            elif self.pre_analysis_band_stats is not None:
                self._raise_if_cancelled()
                voice_rms = analyze_voice_band(self.input_path, verbose=self.verbose)

            warning = ""
            dynamic_eq = self.dynamic_eq
            if dynamic_eq and not band_stats:
                dynamic_eq = False
                warning = (
                    "Aviso: no se pudo calcular RMS por bandas; "
                    "se desactiva el control dinámico por bandas.\n"
                )

            if self.pre_analysis_stats is not None:
                raw_stats = self.pre_analysis_stats
            else:
                self._raise_if_cancelled()
                raw_stats, _raw_log = analyze_audio(
                    self.input_path,
                    self.target_lufs,
                    self.true_peak,
                    verbose=False,
                )
            noise_level, declip_level, declick_level = resolve_repair_levels(
                raw_stats, self.noise_reduction_level, self.declip_level, self.declick_level
            )
            tone_active = any(
                abs(val) > 0.001 for val in (self.tone_low_db, self.tone_mid_db, self.tone_high_db, self.tone_tilt_db)
            )
            band_adjust_active = any(abs(val) > 0.001 for val in self.band_adjust_db.values())
            saturation_active = self.saturation_enabled and self.saturation_mix > 0.0
            repair_active = any(
                level.strip().lower() not in ("off", "apagado")
                for level in (noise_level, declip_level, declick_level)
            )
            process_steps: list[tuple[str, str]] = [
                ("repair", "Reparación"),
                ("deesser", "De-Esser"),
                ("tone_eq", "Tone EQ"),
                ("dynamic_eq", "EQ dinámica"),
                ("stereo_width", "Stereo width"),
                ("band_adjust", "Band adjust"),
                ("saturation", "Saturación"),
                ("stereo_dynamic", "Stereo dinámico"),
                ("glue", "Glue"),
                ("auto_band_gain", "Auto-gain bandas"),
            ]
            enabled_map = {
                "repair": repair_active,
                "deesser": self.deesser,
                "tone_eq": tone_active,
                "dynamic_eq": dynamic_eq,
                "stereo_width": self.stereo_width,
                "band_adjust": band_adjust_active,
                "saturation": saturation_active,
                "stereo_dynamic": self.stereo_dynamic,
                "glue": self.glue_enabled,
                "auto_band_gain": self.auto_band_gain,
            }
            order = self.process_order or [key for key, _label in process_steps]
            ordered_steps: list[str] = []
            for key in order:
                if key in enabled_map and enabled_map[key]:
                    ordered_steps.append(key)
            for key, _label in process_steps:
                if key not in ordered_steps and enabled_map.get(key):
                    ordered_steps.append(key)

            total_steps = 2 + len(ordered_steps) + (1 if not self.analyze_only else 0) + 1
            emit_step("Analizando bandas EQ...")
            emit_step("Analizando banda vocal...")
            total_procs = len(ordered_steps)
            proc_idx = 0
            for key in ordered_steps:
                proc_idx += 1
                label = dict(process_steps).get(key, key)
                emit_step(f"Proceso {proc_idx}/{total_procs}: {label}")
            emit_step("Calibrando loudness con pre-proceso...")
            self._raise_if_cancelled()
            preprocess_kwargs = _build_preprocess_kwargs(
                self,
                input_path=self.input_path,
                band_stats=band_stats,
                dynamic_eq=dynamic_eq,
                noise_level=noise_level,
                declip_level=declip_level,
                declick_level=declick_level,
                band_range_db=band_range,
                max_adjust_db=max_adjust,
            )
            pre_chain, pre_output = build_preprocess_chain(**preprocess_kwargs)
            if pre_chain:
                self._raise_if_cancelled()
                stats, log = analyze_audio_with_filter(
                    input_path=self.input_path,
                    target_lufs=self.target_lufs,
                    true_peak=self.true_peak,
                    filter_chain=pre_chain,
                    filter_output=pre_output,
                    verbose=self.verbose,
                )
            else:
                self._raise_if_cancelled()
                stats, log = analyze_audio(self.input_path, self.target_lufs, self.true_peak, verbose=self.verbose)

            normalize_log = ""
            output_path = None
            pre_rating, pre_advice = evaluate_mix(stats, self.target_lufs, self.true_peak)
            pre_summary = format_analysis_summary(
                "Antes del proceso",
                stats,
                band_stats,
                voice_rms,
                self.target_lufs,
                self.true_peak,
            )
            if not self.analyze_only:
                emit_step("Procesando y normalizando audio...")
                effective_master_enabled = True
                if not self.master_enabled:
                    emit_status("Aviso: 'Mastering habilitado' estaba en OFF. Se fuerza ON para render de salida.")
                
                # Callback para progreso detallado de FFmpeg
                def on_ffmpeg_progress(percent: float, time_str: str) -> None:
                    self._raise_if_cancelled()
                    self.processing_progress.emit(percent, time_str)
                normalize_kwargs = _build_normalize_kwargs(
                    self,
                    input_path=self.input_path,
                    dynamic_eq=dynamic_eq,
                    band_stats=band_stats,
                    output_format=self.output_format,
                    noise_level=noise_level,
                    declip_level=declip_level,
                    declick_level=declick_level,
                    fade_in=self.fade_in,
                    fade_out=self.fade_out,
                    master_enabled=effective_master_enabled,
                    progress_callback=on_ffmpeg_progress,
                )
                normalize_log = normalize_audio(
                    input_path=self.input_path,
                    output_path=self.output_path,
                    stats=stats,
                    target_lufs=self.target_lufs,
                    true_peak=self.true_peak,
                    overwrite=self.overwrite,
                    verbose=self.verbose,
                    **normalize_kwargs,
                )
                self._raise_if_cancelled()
                if warning:
                    normalize_log = warning + normalize_log
                emit_step("Re-analizando salida...")
                post_stats = _extract_loudnorm_output_stats(normalize_log)
                if post_stats is None:
                    try:
                        post_stats = extract_loudnorm_stats(normalize_log)
                    except Exception:
                        post_stats = None
                if post_stats is None:
                    post_stats, _post_log = analyze_audio(
                        self.output_path, self.target_lufs, self.true_peak, verbose=False
                    )

                severe_recalibration = _needs_severe_recalibration(
                    post_stats=post_stats,
                    target_lufs=self.target_lufs,
                    true_peak=self.true_peak,
                )
                # Ruta corta por defecto:
                # - corrección única obligatoria para desvíos grandes
                # - modo seguro opcional para forzar recalibración siempre
                needs_calibration = severe_recalibration or _calibration_safe_mode_enabled()
                if needs_calibration:
                    post_stats, calibration_log = _calibrate_output_from_logs(
                        output_path=self.output_path,
                        initial_stats=post_stats,
                        target_lufs=self.target_lufs,
                        true_peak=self.true_peak,
                        limiter_ceiling_db=self.limiter_ceiling_db,
                        limiter_release_ms=self.limiter_release_ms,
                        output_sr=self.output_sr,
                        output_bit_depth=self.output_bit_depth,
                        output_format=self.output_format,
                        metadata=self.metadata,
                        verbose=self.verbose,
                        emit_status=emit_status,
                    )
                    if calibration_log:
                        normalize_log = "\n".join(
                            part for part in [normalize_log.strip(), calibration_log] if part
                        )
                post_band_stats, _post_suggestions, post_voice_rms = analyze_eq_and_voice(
                    self.output_path,
                    verbose=False,
                    band_range_db=band_range,
                )
                post_rating, post_advice = evaluate_mix(post_stats, self.target_lufs, self.true_peak)
                post_summary = format_analysis_summary(
                    "Despues del proceso",
                    post_stats,
                    post_band_stats,
                    post_voice_rms,
                    self.target_lufs,
                    self.true_peak,
                )
                normalize_log = "\n".join(
                    part for part in [normalize_log.strip(), *resource_lines, pre_summary, post_summary] if part
                )
                output_path = str(self.output_path)
                toml_path = write_analysis_toml(
                    output_path=self.output_path,
                    target_lufs=self.target_lufs,
                    true_peak=self.true_peak,
                    loudness_preset=self.loudness_preset,
                    output_preset=self.output_preset,
                    output_sr=self.output_sr,
                    output_bit_depth=self.output_bit_depth,
                    output_format=self.output_format,
                    dynamic_eq=dynamic_eq,
                    stereo_width=self.stereo_width,
                    brickwall=self.brickwall,
                    analyze_only=self.analyze_only,
                    deesser=self.deesser,
                    fade_in=self.fade_in,
                    fade_out=self.fade_out,
                    signature=self.metadata,
                    before_stats=stats,
                    before_band=band_stats,
                    before_voice=voice_rms,
                    after_stats=post_stats,
                    after_band=post_band_stats,
                    after_voice=post_voice_rms,
                    before_rating=pre_rating,
                    before_advice=pre_advice,
                    after_rating=post_rating,
                    after_advice=post_advice,
                    resource_info=resource_info,
                )
                try:
                    emit_step("Generando log temporal MTS...")
                    mts_paths = write_mts_artifacts(
                        input_path=self.output_path,
                        output_path=self.output_path,
                        validation_context={
                            "target_lufs": self.target_lufs,
                            "true_peak_target": self.true_peak,
                            "pre_stats": stats,
                            "post_stats": post_stats,
                            "dynamic_eq": dynamic_eq,
                            "deesser_enabled": self.deesser,
                            "stereo_dynamic_enabled": self.stereo_dynamic,
                            "stereo_dynamic_mix": self.stereo_dynamic_mix,
                            "stereo_dynamic_band_mix": self.stereo_dynamic_band_mix,
                            "multiband_limiter_enabled": self.multiband_limiter_enabled,
                            "multiband_limiter_thresholds": self.multiband_limiter_thresholds,
                            "saturation_enabled": self.saturation_enabled,
                            "saturation_per_band": self.saturation_per_band,
                            "saturation_mix": self.saturation_mix,
                            "saturation_drive_db": self.saturation_drive_db,
                            "saturation_band_mix": self.saturation_band_mix,
                            "saturation_band_drive_db": self.saturation_band_drive_db,
                        },
                    )
                    normalize_log = "\n".join(
                        part
                        for part in [
                            normalize_log.strip(),
                            f"MTS JSON -> {mts_paths['json_path']}",
                            f"MTS Resumen -> {mts_paths['md_path']}",
                            f"Master Decisions JSON -> {mts_paths.get('decisions_json_path', '')}",
                            f"Master Decisions Resumen -> {mts_paths.get('decisions_md_path', '')}",
                            f"Adaptive Shadow JSON -> {mts_paths.get('shadow_json_path', '')}",
                            f"Adaptive Shadow Resumen -> {mts_paths.get('shadow_md_path', '')}",
                            f"Adaptive Guard JSON -> {mts_paths.get('guard_json_path', '')}",
                            f"Adaptive Guard Resumen -> {mts_paths.get('guard_md_path', '')}",
                            f"Adaptive Render JSON -> {mts_paths.get('adaptive_render_json_path', '')}",
                            f"Adaptive Render Resumen -> {mts_paths.get('adaptive_render_md_path', '')}",
                            f"Master Validation JSON -> {mts_paths.get('validation_json_path', '')}",
                            f"Master Validation Resumen -> {mts_paths.get('validation_md_path', '')}",
                        ]
                        if part
                    )
                except Exception as mts_exc:
                    normalize_log = "\n".join(
                        part
                        for part in [
                            normalize_log.strip(),
                            f"Aviso MTS: {mts_exc}",
                        ]
                        if part
                    )
            else:
                post_stats = None
                post_voice_rms = None
                post_rating = None
                toml_path = write_analysis_toml(
                    output_path=self.output_path,
                    target_lufs=self.target_lufs,
                    true_peak=self.true_peak,
                    loudness_preset=self.loudness_preset,
                    output_preset=self.output_preset,
                    output_sr=self.output_sr,
                    output_bit_depth=self.output_bit_depth,
                    output_format=self.output_format,
                    dynamic_eq=dynamic_eq,
                    stereo_width=self.stereo_width,
                    brickwall=self.brickwall,
                    analyze_only=self.analyze_only,
                    deesser=self.deesser,
                    fade_in=self.fade_in,
                    fade_out=self.fade_out,
                    signature=self.metadata,
                    before_stats=stats,
                    before_band=band_stats,
                    before_voice=voice_rms,
                    after_stats=None,
                    after_band=None,
                    after_voice=None,
                    before_rating=pre_rating,
                    before_advice=pre_advice,
                    after_rating=None,
                    after_advice=None,
                )
                try:
                    emit_step("Generando log temporal MTS...")
                    mts_paths = write_mts_artifacts(
                        input_path=self.input_path,
                        output_path=self.output_path,
                        validation_context={
                            "target_lufs": self.target_lufs,
                            "true_peak_target": self.true_peak,
                            "pre_stats": stats,
                            "post_stats": None,
                            "dynamic_eq": dynamic_eq,
                            "deesser_enabled": self.deesser,
                            "stereo_dynamic_enabled": self.stereo_dynamic,
                            "stereo_dynamic_mix": self.stereo_dynamic_mix,
                            "stereo_dynamic_band_mix": self.stereo_dynamic_band_mix,
                            "multiband_limiter_enabled": self.multiband_limiter_enabled,
                            "multiband_limiter_thresholds": self.multiband_limiter_thresholds,
                            "saturation_enabled": self.saturation_enabled,
                            "saturation_per_band": self.saturation_per_band,
                            "saturation_mix": self.saturation_mix,
                            "saturation_drive_db": self.saturation_drive_db,
                            "saturation_band_mix": self.saturation_band_mix,
                            "saturation_band_drive_db": self.saturation_band_drive_db,
                        },
                    )
                    log = "\n".join(
                        part
                        for part in [
                            log.strip(),
                            f"MTS JSON -> {mts_paths['json_path']}",
                            f"MTS Resumen -> {mts_paths['md_path']}",
                            f"Master Decisions JSON -> {mts_paths.get('decisions_json_path', '')}",
                            f"Master Decisions Resumen -> {mts_paths.get('decisions_md_path', '')}",
                            f"Adaptive Shadow JSON -> {mts_paths.get('shadow_json_path', '')}",
                            f"Adaptive Shadow Resumen -> {mts_paths.get('shadow_md_path', '')}",
                            f"Adaptive Guard JSON -> {mts_paths.get('guard_json_path', '')}",
                            f"Adaptive Guard Resumen -> {mts_paths.get('guard_md_path', '')}",
                            f"Adaptive Render JSON -> {mts_paths.get('adaptive_render_json_path', '')}",
                            f"Adaptive Render Resumen -> {mts_paths.get('adaptive_render_md_path', '')}",
                            f"Master Validation JSON -> {mts_paths.get('validation_json_path', '')}",
                            f"Master Validation Resumen -> {mts_paths.get('validation_md_path', '')}",
                        ]
                        if part
                    )
                except Exception as mts_exc:
                    log = "\n".join(
                        part
                        for part in [
                            log.strip(),
                            f"Aviso MTS: {mts_exc}",
                        ]
                        if part
                    )
            self.finished.emit(
                stats,
                band_stats,
                suggestions,
                voice_rms,
                log,
                normalize_log,
                output_path,
                toml_path,
                post_stats,
                post_voice_rms,
                post_band_stats,
                pre_rating,
                post_rating,
            )
        except Exception as exc:
            # Limpiar archivo de salida si existe y está vacío o corrupto
            if not self.analyze_only and self.output_path.exists():
                try:
                    if self.output_path.stat().st_size == 0:
                        self.output_path.unlink()
                except Exception:
                    pass
            self.error.emit(str(exc))


def _analyze_single_file_for_batch(
    audio_path: pathlib.Path,
    target_lufs: float,
    true_peak: float,
    band_range_db: float,
    use_cache: bool = True,
) -> SingleFileAnalysis:
    """
    Analiza un archivo individual para el batch.
    Retorna: (path, raw_stats, band_stats, voice_rms)
    
    Esta función está diseñada para ejecutarse en paralelo con ThreadPoolExecutor.
    Usa el caché cuando está disponible.
    """
    # Intentar obtener del caché primero
    if use_cache:
        cached = get_cached_analysis(audio_path)
        if cached:
            # Solo necesitamos re-analizar para obtener raw_stats (depende de target_lufs)
            raw_stats, _ = analyze_audio(audio_path, target_lufs, true_peak, verbose=False)
            return SingleFileAnalysis(
                audio_path,
                raw_stats,
                cached.get('band_stats', {}),
                cached.get('voice_rms'),
            )
    
    # Análisis completo
    raw_stats, _ = analyze_audio(audio_path, target_lufs, true_peak, verbose=False)
    band_stats, _suggestions, voice_rms = analyze_eq_and_voice(
        audio_path,
        verbose=False,
        band_range_db=band_range_db,
    )
    
    # Guardar en caché
    if use_cache:
        audio_info = get_audio_info(str(audio_path))
        save_analysis_cache(audio_path, raw_stats, band_stats, [], voice_rms, audio_info)
    
    return SingleFileAnalysis(audio_path, raw_stats, band_stats, voice_rms)


class BatchWorker(QObject):
    finished = Signal(str, object)
    error = Signal(str)
    progress = Signal(str, int, int)
    processing_progress = Signal(float, str)  # percent, time_str - progreso detallado de FFmpeg

    def __init__(
        self,
        files: list[pathlib.Path],
        output_dir: pathlib.Path | None,
        suffix: str,
        target_lufs: float,
        true_peak: float,
        overwrite: bool,
        verbose: bool,
        dynamic_eq: bool,
        master_limiter_enabled: bool,
        master_limiter_mode: str,
        master_limiter_ceiling_db: float,
        master_limiter_release_ms: float,
        master_limiter_lookahead_ms: float,
        output_sr: int | None,
        output_bit_depth: str | None,
        output_format: str | None,
        stereo_width: bool,
        loudness_preset: str,
        output_preset: str,
        deesser: bool,
        deesser_freq_hz: float,
        deesser_intensity: float,
        tone_low_db: float,
        sub_bass_db: float,
        tone_mid_db: float,
        tone_high_db: float,
        tone_tilt_db: float,
        band_adjust_db: Dict[str, float],
        band_widths: Dict[str, float],
        auto_band_gain: bool,
        saturation_enabled: bool,
        saturation_per_band: bool,
        saturation_type: str,
        saturation_drive_db: float,
        saturation_mix: float,
        saturation_band_drive_db: Dict[str, float],
        saturation_band_mix: Dict[str, float],
        process_order: list[str],
        stereo_dynamic: bool,
        stereo_dynamic_band_mix: list[float],
        stereo_dynamic_threshold_db: float,
        stereo_dynamic_ratio: float,
        stereo_dynamic_attack_ms: float,
        stereo_dynamic_release_ms: float,
        stereo_dynamic_mix: float,
        glue_enabled: bool,
        glue_threshold_db: float,
        glue_ratio: float,
        glue_attack_ms: float,
        glue_release_ms: float,
        glue_makeup_db: float,
        limiter_ceiling_db: float | None,
        limiter_release_ms: float | None,
        metadata: Dict[str, str] | None,
        fade_in: float,
        fade_out: float,
        fade_overrides: Dict[str, tuple[float, float]] | None,
        transparent_mode: bool,
        headroom_db: float,
        noise_reduction_level: str,
        declip_level: str,
        declick_level: str,
        pink_noise_level: str = "Off",
        repair_enabled: bool = True,
        mix_enabled: bool = True,
        master_enabled: bool = True,
        autogain_enabled: bool = True,
        autogain_maxgain: float | None = None,
        multiband_limiter_enabled: bool = False,
        multiband_limiter_thresholds: Dict[str, float] | None = None,
        mts_enabled: bool = True,
        checkpoint_path: pathlib.Path | None = None,
        resume_completed_files: set[str] | None = None,
        cancel_token_path: pathlib.Path | None = None,
        global_adjustments: Dict[str, Any] | None = None,
        ia_providers: list | None = None,
        ia_status: str = "off",
        auto_master_style: str = "SUNO",
        minimal_lra_threshold: float = 4.5,
        minimal_crest_threshold: float = 8.5,
        motion_profile_preference: str = "auto",
        motion_amount: float = 1.0,
        block_mode: bool = False,
    ) -> None:
        super().__init__()
        self.files = files
        self.output_dir = output_dir
        self.suffix = suffix
        self.target_lufs = target_lufs
        self.true_peak = true_peak
        self.overwrite = overwrite
        self.verbose = verbose
        self.dynamic_eq = dynamic_eq
        self.master_limiter_enabled = master_limiter_enabled
        # Back-compat: "brickwall" era el nombre histórico del limitador maestro.
        self.brickwall = master_limiter_enabled
        self.master_limiter_mode = master_limiter_mode
        self.master_limiter_ceiling_db = master_limiter_ceiling_db
        self.master_limiter_release_ms = master_limiter_release_ms
        self.master_limiter_lookahead_ms = master_limiter_lookahead_ms
        self.output_sr = output_sr
        self.output_bit_depth = output_bit_depth
        self.output_format = output_format
        self.stereo_width = stereo_width
        self.loudness_preset = loudness_preset
        self.output_preset = output_preset
        self.deesser = deesser
        self.deesser_freq_hz = deesser_freq_hz
        self.deesser_intensity = deesser_intensity
        self.tone_low_db = tone_low_db
        self.sub_bass_db = sub_bass_db
        self.tone_mid_db = tone_mid_db
        self.tone_high_db = tone_high_db
        self.tone_tilt_db = tone_tilt_db
        self.band_adjust_db = band_adjust_db
        self.band_widths = band_widths
        self.auto_band_gain = auto_band_gain
        self.saturation_enabled = saturation_enabled
        self.saturation_per_band = saturation_per_band
        self.saturation_type = saturation_type
        self.saturation_drive_db = saturation_drive_db
        self.saturation_mix = saturation_mix
        self.saturation_band_drive_db = saturation_band_drive_db
        self.saturation_band_mix = saturation_band_mix
        self.process_order = process_order
        self.stereo_dynamic = stereo_dynamic
        self.stereo_dynamic_band_mix = stereo_dynamic_band_mix
        self.stereo_dynamic_threshold_db = stereo_dynamic_threshold_db
        self.stereo_dynamic_ratio = stereo_dynamic_ratio
        self.stereo_dynamic_attack_ms = stereo_dynamic_attack_ms
        self.stereo_dynamic_release_ms = stereo_dynamic_release_ms
        self.stereo_dynamic_mix = stereo_dynamic_mix
        self.glue_enabled = glue_enabled
        self.glue_threshold_db = glue_threshold_db
        self.glue_ratio = glue_ratio
        self.glue_attack_ms = glue_attack_ms
        self.glue_release_ms = glue_release_ms
        self.glue_makeup_db = glue_makeup_db
        self.limiter_ceiling_db = limiter_ceiling_db
        self.limiter_release_ms = limiter_release_ms
        self.metadata = metadata
        self.fade_in = fade_in
        self.fade_out = fade_out
        self.fade_overrides = fade_overrides or {}
        self.transparent_mode = transparent_mode
        self.headroom_db = headroom_db
        self.autogain_maxgain = autogain_maxgain
        self.noise_reduction_level = noise_reduction_level
        self.declip_level = declip_level
        self.declick_level = declick_level
        self.pink_noise_level = pink_noise_level
        self.repair_enabled = repair_enabled
        self.mix_enabled = mix_enabled
        self.master_enabled = master_enabled
        self.autogain_enabled = autogain_enabled
        self.multiband_limiter_enabled = multiband_limiter_enabled
        self.multiband_limiter_thresholds = multiband_limiter_thresholds
        self.mts_enabled = mts_enabled
        self.checkpoint_path = checkpoint_path
        self.resume_completed_files = resume_completed_files or set()
        self.cancel_token_path = cancel_token_path
        self.global_adjustments = global_adjustments
        self.ia_providers = ia_providers or []
        self.ia_status = ia_status
        self.auto_master_style = auto_master_style
        self.minimal_lra_threshold = minimal_lra_threshold
        self.minimal_crest_threshold = minimal_crest_threshold
        self.motion_profile_preference = motion_profile_preference
        self.motion_amount = motion_amount
        self.block_mode = block_mode
        self._base_auto_tunables = {
            name: copy.deepcopy(getattr(self, name, None))
            for name in (
                "dynamic_eq",
                "band_adjust_db",
                "band_widths",
                "stereo_width",
                "deesser",
                "glue_enabled",
                "headroom_db",
                "multiband_limiter_enabled",
                "multiband_limiter_thresholds",
                "noise_reduction_level",
                "declip_level",
                "declick_level",
                "autogain_maxgain",
            )
        }
        self._cancel_event = threading.Event()

    def _restore_auto_tunables(self) -> None:
        for name, value in self._base_auto_tunables.items():
            setattr(self, name, copy.deepcopy(value))
        if hasattr(self, "_auto_process_order"):
            delattr(self, "_auto_process_order")
        if hasattr(self, "_ai_audio_actions"):
            delattr(self, "_ai_audio_actions")
        if hasattr(self, "_ai_source_fingerprint"):
            delattr(self, "_ai_source_fingerprint")

    def _apply_auto_master_adjustments_for_file(
        self,
        adjustments: Dict[str, Any],
    ) -> None:
        actions = adjustments.get("audio_actions")
        if isinstance(actions, list):
            self._ai_audio_actions = copy.deepcopy(actions)
            fingerprint = adjustments.get("source_fingerprint")
            if fingerprint:
                self._ai_source_fingerprint = str(fingerprint)
        eq_adjustments = adjustments.get("eq_adjustments")
        if isinstance(eq_adjustments, dict) and eq_adjustments:
            if adjustments.get("band_eq_enabled") is False:
                self.band_adjust_db = {}
            else:
                merged_eq = dict(self.band_adjust_db or {})
                for band, value in eq_adjustments.items():
                    try:
                        merged_eq[str(band)] = max(-6.0, min(6.0, float(value)))
                    except (TypeError, ValueError):
                        continue
                self.band_adjust_db = merged_eq
                self.dynamic_eq = bool(adjustments.get("dynamic_eq_enabled", True))

        band_widths = adjustments.get("band_widths")
        if isinstance(band_widths, dict) and band_widths:
            self.band_widths = {
                str(band): max(0.0, min(2.0, float(width)))
                for band, width in band_widths.items()
                if isinstance(width, (int, float))
            }
            if self.band_widths:
                self.stereo_width = True

        if "headroom_db" in adjustments:
            try:
                self.headroom_db = max(-24.0, min(-8.0, float(adjustments["headroom_db"])))
            except (TypeError, ValueError):
                pass

        if "deesser_enabled" in adjustments:
            self.deesser = bool(adjustments.get("deesser_enabled"))
        if "glue_enabled" in adjustments:
            self.glue_enabled = bool(adjustments.get("glue_enabled"))

        if adjustments.get("multiband_limiter_enabled") or adjustments.get("band_limiter_enabled"):
            self.multiband_limiter_enabled = True
        thresholds = adjustments.get("multiband_limiter_thresholds")
        if isinstance(thresholds, dict) and thresholds:
            self.multiband_limiter_thresholds = {
                str(band): float(value)
                for band, value in thresholds.items()
                if isinstance(value, (int, float))
            }

        repair = adjustments.get("repair_settings")
        if isinstance(repair, dict):
            if repair.get("noise_reduction") and repair.get("noise_reduction") != "Off":
                self.noise_reduction_level = str(repair["noise_reduction"])
            if repair.get("declip") and repair.get("declip") != "Off":
                self.declip_level = str(repair["declip"])
            if repair.get("declick") and repair.get("declick") != "Off":
                self.declick_level = str(repair["declick"])

        if "autogain_maxgain" in adjustments:
            try:
                self.autogain_maxgain = float(adjustments["autogain_maxgain"])
            except (TypeError, ValueError):
                pass

        process_order = adjustments.get("process_order")
        if isinstance(process_order, list) and process_order:
            self._auto_process_order = [str(item) for item in process_order]

    def cancel(self) -> None:
        self._cancel_event.set()
        cancel_running_ffmpeg_processes()
        try:
            from logic_backend import cancel_active_spasm_call
            cancel_active_spasm_call()
        except Exception:
            pass

    def _is_cancelled(self) -> bool:
        if self._cancel_event.is_set():
            return True
        if self.cancel_token_path is not None and self.cancel_token_path.exists():
            return True
        return False

    def _save_checkpoint(self, completed_files: list[str]) -> None:
        if self.checkpoint_path is None:
            return
        payload: Dict[str, Any] = {}
        try:
            if self.checkpoint_path.exists():
                with self.checkpoint_path.open("r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                if isinstance(loaded, dict):
                    payload.update(loaded)
        except Exception:
            pass
        payload.update(
            {
                "updated_at": time.time(),
                "completed_files": completed_files,
            }
        )
        try:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with self.checkpoint_path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def run(self) -> None:
        try:
            ensure_ffmpeg_available()
            files = [p for p in self.files if p.exists() and p.is_file()]
            if not files:
                self.error.emit("No se encontraron archivos seleccionados para procesar.")
                return
            completed_files = sorted(set(self.resume_completed_files))
            if self.resume_completed_files:
                files = [p for p in files if str(p.resolve()) not in self.resume_completed_files]
                if not files:
                    self.finished.emit("Lote ya estaba completado según checkpoint.", [])
                    return

            band_range = TRANSPARENT_BAND_RANGE_DB if self.transparent_mode else DEFAULT_BAND_RANGE_DB
            max_adjust = TRANSPARENT_MAX_ADJUST_DB if self.transparent_mode else DEFAULT_MAX_ADJUST_DB

            # Cola simple: un archivo por vez para evitar sobrecarga del sistema.
            limits = get_processing_limits()
            self.progress.emit(
                "Recursos: "
                f"{limits.get('max_ffmpeg_processes', 1)} procesos ffmpeg, "
                f"{limits.get('ffmpeg_threads_per_process', 1)} threads/proceso.",
                0,
                len(files),
            )
            resource_info = _build_runtime_resource_info()
            resource_lines = _format_runtime_resource_lines(resource_info)
            self.progress.emit(" | ".join(resource_lines), 0, len(files))
            effective_master_enabled = True
            if not self.master_enabled:
                self.progress.emit(
                    "Aviso: 'Mastering habilitado' estaba en OFF. Se fuerza ON para render de salida.",
                    0,
                    len(files),
                )

            # Cada archivo se trata como una unidad independiente:
            # deep analysis -> procesamiento -> validación rápida final.
            processed = 0
            results: list[dict] = []
            output_paths_for_rollout: list[pathlib.Path] = []
            mts_total = len(files)
            mts_done = 0
            mts_futures: dict[Future, dict[str, Any]] = {}

            def collect_ready_mts(wait_one: bool = False) -> None:
                nonlocal mts_done
                if not mts_futures:
                    return
                if wait_one:
                    done_set, _ = wait(set(mts_futures.keys()), return_when=FIRST_COMPLETED)
                    done = list(done_set)
                else:
                    done = [future for future in list(mts_futures.keys()) if future.done()]
                for future in done:
                    meta = mts_futures.pop(future)
                    mts_done += 1
                    try:
                        mts_paths = future.result()
                        adaptive_status = "unknown"
                        adaptive_path = mts_paths.get("adaptive_render_json_path")
                        if adaptive_path:
                            try:
                                adaptive_status = json.loads(pathlib.Path(adaptive_path).read_text(encoding="utf-8")).get("status", "unknown")
                            except Exception:
                                adaptive_status = "unreadable"
                        self.progress.emit(
                            (
                                f"Análisis temporal {mts_done}/{mts_total}: {meta['name']} "
                                f"(ok, adaptive={adaptive_status}) -> {mts_paths['json_path'].name}"
                            ),
                            int(meta["idx"]),
                            len(files),
                        )
                    except Exception as mts_exc:
                        self.progress.emit(
                            f"Análisis temporal {mts_done}/{mts_total}: {meta['name']} (aviso: {mts_exc})",
                            int(meta["idx"]),
                            len(files),
                        )

            # Modo secuencial estricto en lote:
            # cada tema debe cerrar su ciclo completo antes del siguiente.
            mts_workers = 0
            mts_executor = (
                ThreadPoolExecutor(max_workers=mts_workers, thread_name_prefix="tonefinish-mts")
                if mts_workers > 0
                else None
            )

            if self.mts_enabled:
                self.progress.emit(
                    "Análisis temporal: modo secuencial estricto activo.",
                    0,
                    len(files),
                )

            for idx, audio_path in enumerate(files, start=1):
                if self._is_cancelled():
                    self.error.emit("Proceso cancelado por el usuario.")
                    return
                collect_ready_mts(wait_one=False)
                file_start = time.perf_counter()
                last_mark = file_start
                stage_timings: list[tuple[str, float]] = []

                def mark(stage_name: str) -> None:
                    nonlocal last_mark
                    now = time.perf_counter()
                    stage_timings.append((stage_name, now - last_mark))
                    last_mark = now

                self.progress.emit(f"Analizando {idx}/{len(files)}: {audio_path.name}", idx, len(files))
                self.progress.emit(" | ".join(resource_lines), idx, len(files))

                try:
                    analysis = _analyze_single_file_for_batch(
                        audio_path,
                        self.target_lufs,
                        self.true_peak,
                        band_range,
                        True,
                    )
                    raw_stats = analysis.raw_stats
                    band_stats = analysis.band_stats
                    voice_rms = analysis.voice_rms
                except Exception:
                    # Si el análisis profundo falla, continuamos con un análisis mínimo
                    # para no frenar todo el lote.
                    raw_stats, _ = analyze_audio(audio_path, self.target_lufs, self.true_peak, verbose=False)
                    band_stats = {}
                    voice_rms = None

                self._restore_auto_tunables()
                ai_master_info: Dict[str, Any] | None = None
                if True:  # IA siempre; sin tokens/credenciales cae en SUNO Clásico.
                    provider = self.ia_providers[0] if self.ia_providers else {}
                    provider_model = str(provider.get("model", ""))
                    self.progress.emit(
                        f"Master asistido por IA ({self.ia_status}): consultando estrategia para {audio_path.name}",
                        idx,
                        len(files),
                    )
                    try:
                        characteristics = AudioCharacteristics(
                            band_stats=band_stats,
                            voice_rms=voice_rms,
                            loudness_metrics={
                                "lufs": float(raw_stats.get("input_i", -70.0)),
                                "true_peak": float(raw_stats.get("input_tp", -70.0)),
                                "lra": float(raw_stats.get("input_lra", 0.0)),
                                "crest_factor": float(raw_stats.get("crest_factor", 0.0)),
                                "rms_total": float(raw_stats.get("input_thresh", -70.0)),
                                "peak_total": float(raw_stats.get("input_tp", -70.0)),
                            },
                        )
                        adjustments = adapt_preset_to_audio(
                            self.auto_master_style,
                            characteristics,
                            minimal_lra_threshold=self.minimal_lra_threshold,
                            minimal_crest_threshold=self.minimal_crest_threshold,
                            motion_profile_preference=self.motion_profile_preference,
                            motion_amount=self.motion_amount,
                            block_mode=self.block_mode,
                            ia_providers=self.ia_providers,
                            target_lufs=self.target_lufs,
                            true_peak=self.true_peak,
                            audio_id=str(audio_path),
                        )
                        self.global_adjustments = adjustments
                        self._apply_auto_master_adjustments_for_file(adjustments)
                        notes = [
                            str(item)
                            for item in adjustments.get("notes", [])
                        ] if isinstance(adjustments.get("notes"), list) else []
                        used_ai_strategy = adjustments.get("strategy_source") == "ai"
                        fallback_reason = str(adjustments.get("fallback_reason", "") or "")
                        if not used_ai_strategy:
                            fallback_reason = fallback_reason or next(
                                (
                                    str(item)
                                    for item in notes
                                    if "IA " in str(item) or str(item).startswith(("⚠", "🛟"))
                                ),
                                "IA no disponible; se usa SUNO Clásico",
                            )
                        ai_master_info = {
                            "enabled": True,
                            "status": "applied" if used_ai_strategy else "fallback",
                            "provider": self.ia_status,
                            "model": provider_model,
                            "used_ai_strategy": used_ai_strategy,
                            "fallback_reason": fallback_reason,
                            "fallback_preset": adjustments.get("fallback_preset"),
                            "strategy_source": adjustments.get("strategy_source"),
                            "diagnosis": adjustments.get("diagnostics", ""),
                            "notes": notes,
                            "adjustments": adjustments,
                            "decision_trace": adjustments.get("decision_trace", {}),
                        }
                        if used_ai_strategy:
                            self.progress.emit(
                                f"Master asistido por IA: estrategia IA aplicada a {audio_path.name}",
                                idx,
                                len(files),
                            )
                        else:
                            note = next(
                                (
                                    str(item)
                                    for item in adjustments.get("notes", [])
                                    if "IA " in str(item) or str(item).startswith("⚠")
                                ),
                                "se usa SUNO Clásico",
                            )
                            self.progress.emit(
                                f"Master asistido por IA: {note}",
                                idx,
                                len(files),
                            )
                    except Exception as exc:
                        self.progress.emit(
                            f"Master asistido por IA: fallo interno ({exc}); se cancela el tema.",
                            idx,
                            len(files),
                        )
                        # Nunca continuar con ajustes manuales/legacy si falla
                        # también la construcción canónica de SUNO Clásico.
                        raise RuntimeError(
                            f"No se pudo construir una estrategia IA/SUNO canónica: {exc}"
                        ) from exc
                out_dir = self.output_dir if self.output_dir else audio_path.parent
                output_base = out_dir / mastered_output_stem(audio_path.stem, self.suffix)
                fmt = self.output_format or audio_path.suffix.lstrip(".")
                output_path = ensure_output_path(output_base, fmt)
                fade_key = str(audio_path)
                fade_in = self.fade_in
                fade_out = self.fade_out
                if fade_key in self.fade_overrides:
                    fade_in, fade_out = self.fade_overrides[fade_key]
                
                noise_level, declip_level, declick_level = resolve_repair_levels(
                    raw_stats, self.noise_reduction_level, self.declip_level, self.declick_level
                )
                dynamic_eq = self.dynamic_eq
                if dynamic_eq and not band_stats:
                    dynamic_eq = False

                self.progress.emit(f"Procesando {idx}/{len(files)}: Construyendo cadena...", idx, len(files))
                preprocess_kwargs = _build_preprocess_kwargs(
                    self,
                    input_path=audio_path,
                    band_stats=band_stats,
                    dynamic_eq=dynamic_eq,
                    noise_level=noise_level,
                    declip_level=declip_level,
                    declick_level=declick_level,
                    band_range_db=band_range,
                    max_adjust_db=max_adjust,
                )
                pre_chain, pre_output = build_preprocess_chain(**preprocess_kwargs)
                with tempfile.TemporaryDirectory(prefix=f"tonefinish_{audio_path.stem}_") as temp_dir:
                    temp_dir_path = pathlib.Path(temp_dir)
                    temp_output_base = temp_dir_path / output_path.name
                    temp_output_path = ensure_output_path(temp_output_base, fmt)

                    if pre_chain:
                        stats, _log = analyze_audio_with_filter(
                            input_path=audio_path,
                            target_lufs=self.target_lufs,
                            true_peak=self.true_peak,
                            filter_chain=pre_chain,
                            filter_output=pre_output,
                            verbose=self.verbose,
                        )
                    else:
                        stats, _log = analyze_audio(
                            audio_path,
                            self.target_lufs,
                            self.true_peak,
                            verbose=self.verbose,
                        )
                    mark("análisis inicial")

                    self.progress.emit("Procesando y normalizando audio...", idx, len(files))

                    # Callback para progreso detallado de FFmpeg
                    def on_ffmpeg_progress(percent: float, time_str: str) -> None:
                        if self._is_cancelled():
                            cancel_running_ffmpeg_processes()
                            raise RuntimeError("Proceso cancelado por el usuario.")
                        self.processing_progress.emit(percent, time_str)

                    normalize_kwargs = _build_normalize_kwargs(
                        self,
                        input_path=audio_path,
                        dynamic_eq=dynamic_eq,
                        band_stats=band_stats,
                        output_format=fmt,
                        noise_level=noise_level,
                        declip_level=declip_level,
                        declick_level=declick_level,
                        fade_in=fade_in,
                        fade_out=fade_out,
                        master_enabled=effective_master_enabled,
                        progress_callback=on_ffmpeg_progress,
                    )
                    normalize_log = ""
                    try:
                        normalize_log = normalize_audio(
                            input_path=audio_path,
                            output_path=temp_output_path,
                            stats=stats,
                            target_lufs=self.target_lufs,
                            true_peak=self.true_peak,
                            overwrite=True,
                            verbose=self.verbose,
                            **normalize_kwargs,
                        )
                    except Exception:
                        if temp_output_path.exists():
                            try:
                                if temp_output_path.stat().st_size == 0:
                                    temp_output_path.unlink()
                            except Exception:
                                pass
                        raise
                    mark("render")

                    self.progress.emit("Validando salida temporal...", idx, len(files))
                    post_stats = _extract_loudnorm_output_stats(normalize_log)
                    if post_stats is None:
                        try:
                            post_stats = extract_loudnorm_stats(normalize_log)
                        except Exception:
                            post_stats = None
                    if post_stats is None:
                        post_stats, _post_log = analyze_audio(
                            temp_output_path, self.target_lufs, self.true_peak, verbose=False
                        )
                    mark("validación")
                    severe_recalibration = _needs_severe_recalibration(
                        post_stats=post_stats,
                        target_lufs=self.target_lufs,
                        true_peak=self.true_peak,
                    )
                    # Ruta corta por defecto:
                    # - corrección única obligatoria para desvíos grandes
                    # - modo seguro opcional para forzar recalibración siempre
                    needs_calibration = severe_recalibration or _calibration_safe_mode_enabled()
                    if needs_calibration:
                        self.progress.emit("Ajustando calibración final...", idx, len(files))
                        post_stats, _calibration_log = _calibrate_output_from_logs(
                            output_path=temp_output_path,
                            initial_stats=post_stats,
                            target_lufs=self.target_lufs,
                            true_peak=self.true_peak,
                            limiter_ceiling_db=self.limiter_ceiling_db,
                            limiter_release_ms=self.limiter_release_ms,
                            output_sr=self.output_sr,
                            output_bit_depth=self.output_bit_depth,
                            output_format=fmt,
                            metadata=self.metadata,
                            verbose=self.verbose,
                            emit_status=lambda msg: self.progress.emit(msg, idx, len(files)),
                        )
                        if _calibration_log:
                            normalize_log = "\n".join(
                                part for part in [normalize_log.strip(), _calibration_log] if part
                            )
                    self.progress.emit("Validando mezcla final...", idx, len(files))
                    pre_rating, pre_advice = evaluate_mix(stats, self.target_lufs, self.true_peak)
                    post_rating, post_advice = evaluate_mix(post_stats, self.target_lufs, self.true_peak)
                    mark("evaluación")

                    self.progress.emit("Copiando resultado final al destino...", idx, len(files))
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(temp_output_path, output_path)
                    mark("copia")

                    self.progress.emit("Escribiendo reporte de análisis...", idx, len(files))
                    if ai_master_info is not None:
                        try:
                            planned = ai_master_info.get("adjustments", {}).get("audio_actions", [])
                            if isinstance(planned, list) and planned:
                                from processes.audit import build_execution_audit, effective_execution_actions

                                trace = ai_master_info.setdefault("decision_trace", {})
                                if isinstance(trace, dict) and isinstance(planned, list):
                                    executed = [
                                        action.to_dict()
                                        for action in effective_execution_actions(planned)
                                    ]
                                    trace["executed_actions"] = executed
                                    trace["final_order"] = [
                                        item.get("function_id") for item in executed
                                        if isinstance(item, dict) and item.get("function_id")
                                    ]
                                    trace["execution_audit"] = build_execution_audit(
                                        executed,
                                        before_stats=stats,
                                        after_stats=post_stats,
                                        target_lufs=self.target_lufs,
                                        true_peak=self.true_peak,
                                    )
                                    if trace["execution_audit"]["status"] != "passed":
                                        self.progress.emit(
                                            f"Control de calidad IA: {audio_path.name} requiere revisión.",
                                            idx,
                                            len(files),
                                        )
                            strategy_json_path = output_path.parent / "log" / f"{output_path.stem}.ai_master.json"
                            strategy_json_path.parent.mkdir(parents=True, exist_ok=True)
                            strategy_json_path.write_text(
                                json.dumps(ai_master_info, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                            ai_master_info["strategy_json"] = strategy_json_path.name
                        except Exception as exc:
                            notes = ai_master_info.setdefault("notes", [])
                            if isinstance(notes, list):
                                notes.append(f"No se pudo escribir JSON IA: {exc}")
                    write_analysis_toml(
                        output_path=output_path,
                        target_lufs=self.target_lufs,
                        true_peak=self.true_peak,
                        loudness_preset=(
                            "IA" if ai_master_info and ai_master_info.get("used_ai_strategy")
                            else "SUNO Clásico"
                        ),
                        output_preset=self.output_preset,
                        output_sr=self.output_sr,
                        output_bit_depth=self.output_bit_depth,
                        output_format=fmt,
                        dynamic_eq=dynamic_eq,
                        stereo_width=self.stereo_width,
                        brickwall=self.brickwall,
                        analyze_only=False,
                        deesser=self.deesser,
                        fade_in=fade_in,
                        fade_out=fade_out,
                        signature=self.metadata,
                        before_stats=stats,
                        before_band=band_stats,
                        before_voice=voice_rms,
                        after_stats=post_stats,
                        after_band={},
                        after_voice=None,
                        before_rating=pre_rating,
                        before_advice=pre_advice,
                        after_rating=post_rating,
                        after_advice=post_advice,
                        resource_info=resource_info,
                        ai_master_info=ai_master_info,
                    )
                    mark("reporte")
                    if self.mts_enabled and mts_executor is not None:
                        self.progress.emit(
                            f"Análisis temporal en cola {idx}/{mts_total}: {audio_path.name}",
                            idx,
                            len(files),
                        )
                        future = mts_executor.submit(
                            write_mts_artifacts,
                            input_path=output_path,
                            output_path=output_path,
                            validation_context={
                                "target_lufs": self.target_lufs,
                                "true_peak_target": self.true_peak,
                                "pre_stats": stats,
                                "post_stats": post_stats,
                                "dynamic_eq": dynamic_eq,
                                "deesser_enabled": self.deesser,
                                "stereo_dynamic_enabled": self.stereo_dynamic,
                                "stereo_dynamic_mix": self.stereo_dynamic_mix,
                                "stereo_dynamic_band_mix": self.stereo_dynamic_band_mix,
                                "multiband_limiter_enabled": self.multiband_limiter_enabled,
                                "multiband_limiter_thresholds": self.multiband_limiter_thresholds,
                                "saturation_enabled": self.saturation_enabled,
                                "saturation_per_band": self.saturation_per_band,
                                "saturation_mix": self.saturation_mix,
                                "saturation_drive_db": self.saturation_drive_db,
                                "saturation_band_mix": self.saturation_band_mix,
                                "saturation_band_drive_db": self.saturation_band_drive_db,
                                "global_adjustments": self.global_adjustments,
                            },
                        )
                        mts_futures[future] = {"idx": idx, "name": audio_path.name}
                        collect_ready_mts(wait_one=False)
                    else:
                        self.progress.emit("Generando log temporal MTS...", idx, len(files))
                        try:
                            write_mts_artifacts(
                                input_path=output_path,
                                output_path=output_path,
                                validation_context={
                                    "target_lufs": self.target_lufs,
                                    "true_peak_target": self.true_peak,
                                    "pre_stats": stats,
                                    "post_stats": post_stats,
                                    "dynamic_eq": dynamic_eq,
                                    "deesser_enabled": self.deesser,
                                    "stereo_dynamic_enabled": self.stereo_dynamic,
                                    "stereo_dynamic_mix": self.stereo_dynamic_mix,
                                    "stereo_dynamic_band_mix": self.stereo_dynamic_band_mix,
                                    "multiband_limiter_enabled": self.multiband_limiter_enabled,
                                    "multiband_limiter_thresholds": self.multiband_limiter_thresholds,
                                    "saturation_enabled": self.saturation_enabled,
                                    "saturation_per_band": self.saturation_per_band,
                                    "saturation_mix": self.saturation_mix,
                                    "saturation_drive_db": self.saturation_drive_db,
                                    "saturation_band_mix": self.saturation_band_mix,
                                    "saturation_band_drive_db": self.saturation_band_drive_db,
                                    "global_adjustments": self.global_adjustments,
                                },
                            )
                            mark("mts")
                        except Exception as mts_exc:
                            self.progress.emit(f"Aviso MTS ({audio_path.name}): {mts_exc}", idx, len(files))
                    self.progress.emit("Archivo finalizado.", idx, len(files))
                    total_seconds = time.perf_counter() - file_start
                results.append(
                    {
                        "file": audio_path.name,
                        "before": stats,
                        "after": post_stats,
                        "before_rating": pre_rating,
                        "after_rating": post_rating,
                        "timings": stage_timings,
                        "total_seconds": total_seconds,
                    }
                )
                output_paths_for_rollout.append(output_path)
                processed += 1
                completed_files.append(str(audio_path.resolve()))
                self._save_checkpoint(completed_files)

            if mts_executor is not None:
                while mts_futures:
                    collect_ready_mts(wait_one=True)
                mts_executor.shutdown(wait=True)
                self.progress.emit(
                    f"Análisis temporal finalizado: {mts_done}/{mts_total} archivos.",
                    len(files),
                    len(files),
                )

            # === FASE 8: REPORTE DE ROLLOUT A/B ===
            try:
                flags = get_rollout_flags()
                rollout_percent = int(flags.get("adaptive_rollout_percent", 0) or 0)
                adaptive_enabled = bool(flags.get("adaptive_master_enabled", False))
                rollout_items = [
                    collect_rollout_item(
                        output_path=out_path,
                        rollout_percent=rollout_percent,
                        adaptive_master_enabled=adaptive_enabled,
                    )
                    for out_path in output_paths_for_rollout
                ]
                rollout_report = build_rollout_report(
                    items=rollout_items,
                    rollout_percent=rollout_percent,
                    adaptive_master_enabled=adaptive_enabled,
                )
                if output_paths_for_rollout:
                    report_dir = output_paths_for_rollout[0].parent / "log"
                    rollout_paths = write_rollout_report(report_dir=report_dir, report=rollout_report)
                    summary = rollout_report.get("summary", {}) if isinstance(rollout_report.get("summary"), dict) else {}
                    self.progress.emit(
                        (
                            "Rollout A/B: "
                            f"canary={summary.get('canary_files', 0)}/{summary.get('total_files', 0)} | "
                            f"guard_ok={summary.get('guard_ok_files', 0)} | "
                            f"apply_ready={summary.get('apply_ready_files', 0)} | "
                            f"enable_apply={summary.get('enable_apply_files', 0)} | "
                            f"reporte={rollout_paths['json_path'].name}"
                        ),
                        len(files),
                        len(files),
                    )
            except Exception as rollout_exc:
                self.progress.emit(
                    f"Aviso Rollout A/B: {rollout_exc}",
                    len(files),
                    len(files),
                )

            self.finished.emit(f"Lote completado: {processed} archivos.", results)
        except Exception as exc:
            try:
                mts_executor_local = locals().get("mts_executor")
                if mts_executor_local is not None:
                    mts_executor_local.shutdown(wait=False)
            except Exception:
                pass
            self.error.emit(str(exc))


class CliBatchWorker(QObject):
    finished = Signal(str, object)
    error = Signal(str)
    progress = Signal(str, int, int)
    processing_progress = Signal(float, str)

    def __init__(self, payload: Dict[str, Any], poll_interval_sec: float = 0.5) -> None:
        super().__init__()
        self.payload = payload
        self.poll_interval_sec = max(0.2, float(poll_interval_sec))
        self._cancel_event = threading.Event()
        self._job_id: str | None = None

    def cancel(self) -> None:
        self._cancel_event.set()
        if self._job_id:
            try:
                spasm_batch_cancel(self._job_id)
            except Exception:
                pass
        cancel_running_ffmpeg_processes()

    def run(self) -> None:
        try:
            started = spasm_batch_start(self.payload)
            self._job_id = str(started.get("job_id", "")).strip()
            if not self._job_id:
                raise RuntimeError("CLI batch_start no devolvió job_id.")

            last_progress = -1.0
            while True:
                if self._cancel_event.is_set():
                    self.cancel()
                    self.error.emit("Proceso cancelado por el usuario.")
                    return

                status = spasm_batch_status(self._job_id)
                state = str(status.get("state", "running"))
                message = str(status.get("message", "Procesando lote..."))
                current = int(status.get("current", 0) or 0)
                total = int(status.get("total", max(1, len(self.payload.get("files", [])))) or 1)
                self.progress.emit(message, current, total)

                p = status.get("processing_percent")
                if isinstance(p, (int, float)):
                    p_float = float(p)
                    if abs(p_float - last_progress) >= 0.5:
                        self.processing_progress.emit(p_float, str(status.get("processing_time", "")))
                        last_progress = p_float

                if state == "done":
                    self.finished.emit(
                        str(status.get("result_message", "Lote completado.")),
                        status.get("results"),
                    )
                    return
                if state == "cancelled":
                    self.error.emit("Proceso cancelado por el usuario.")
                    return
                if state == "error":
                    self.error.emit(str(status.get("error", "Error en job CLI.")))
                    return

                time.sleep(self.poll_interval_sec)
        except Exception as exc:
            self.error.emit(str(exc))
