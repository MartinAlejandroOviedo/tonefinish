import pathlib
import re
from typing import Dict, Tuple

from audio_tools import extract_loudnorm_stats, get_audio_duration, get_audio_mono_samples, get_audio_info, run_ffmpeg
from config import VOICE_BAND, BAND_CONFIG, BAND_HEADROOM_DB, MAX_SATURATION_DRIVE_DB, LOUDNORM_LRA_DEFAULT

# LUFS mínimo para considerar válido el análisis
# Audio con LUFS más bajo que esto se considera silencio o corrupto
LUFS_MINIMUM_VALID = -70.0


def is_audio_valid(input_path: pathlib.Path, verbose: bool = False) -> Tuple[bool, str]:
    """
    Valida que el archivo de audio no sea silencio o esté corrupto.
    
    Args:
        input_path: Ruta al archivo de audio
        verbose: Mostrar output detallado
        
    Returns:
        Tuple[bool, str]: (es_válido, mensaje_error)
    """
    try:
        # Verificar tamaño del archivo primero (archivos de 0 bytes)
        file_size = input_path.stat().st_size
        if file_size == 0:
            return False, "Archivo vacío (0 bytes)"
        if file_size < 1024:  # Menos de 1KB
            return False, f"Archivo demasiado pequeño ({file_size} bytes)"
        
        # Obtener info básica del archivo
        audio_info = get_audio_info(str(input_path))
        
        # Verificar duración
        duration = audio_info.get('duration')
        if duration is None or duration <= 0:
            return False, "El archivo no tiene duración válida o está corrupto"
        
        # Hacer análisis rápido de LUFS
        channels = audio_info.get('channels', 2)
        dual_mono = "true" if channels == 1 else "false"
        
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(input_path),
            "-af",
            f"loudnorm=I=-16:LRA=11:TP=-1:dual_mono={dual_mono}:print_format=json",
            "-f",
            "null",
            "-",
        ]
        result = run_ffmpeg(cmd, verbose=verbose)
        
        if result.returncode != 0:
            return False, f"Error al analizar el archivo: {result.stderr[:200]}"
        
        # Extraer LUFS del análisis
        stats = extract_loudnorm_stats(result.stderr + result.stdout)
        input_i = stats.get('input_i', float('-inf'))
        
        # Verificar si es silencio
        if input_i == float('-inf') or input_i < LUFS_MINIMUM_VALID:
            return False, f"El archivo parece ser silencio o tener audio inválido (LUFS: {input_i})"
        
        return True, ""
        
    except Exception as e:
        return False, f"Error al validar audio: {str(e)}"


def analyze_audio(
    input_path: pathlib.Path,
    target_lufs: float,
    true_peak: float,
    verbose: bool,
    lra: int | None = None,
) -> Tuple[Dict[str, float], str]:
    """
    Ejecuta la primera pasada de loudnorm para obtener estadísticos.
    
    Args:
        input_path: Ruta al archivo de audio
        target_lufs: LUFS objetivo
        true_peak: True peak máximo
        verbose: Mostrar output detallado
        lra: Loudness Range objetivo (LU). Si None, usa LOUDNORM_LRA_DEFAULT
        
    Returns:
        Tuple con stats del audio y stderr de FFmpeg
    """
    if lra is None:
        lra = LOUDNORM_LRA_DEFAULT
    
    # Detectar si es mono para usar dual_mono
    audio_info = get_audio_info(str(input_path))
    channels = audio_info.get('channels', 2)
    dual_mono = "true" if channels == 1 else "false"
    
    filter_args = f"loudnorm=I={target_lufs}:LRA={lra}:TP={true_peak}:dual_mono={dual_mono}:print_format=json"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-af",
        filter_args,
        "-f",
        "null",
        "-",
    ]
    result = run_ffmpeg(cmd, verbose=verbose)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg falló en análisis: {result.stderr.strip()}")
    stats = extract_loudnorm_stats(result.stderr + result.stdout)
    return stats, result.stderr


def analyze_audio_with_filter(
    input_path: pathlib.Path,
    target_lufs: float,
    true_peak: float,
    filter_chain: str,
    filter_output: str,
    verbose: bool,
    lra: int | None = None,
) -> Tuple[Dict[str, float], str]:
    """
    Análisis loudnorm aplicando un pre-proceso antes de medir.
    
    Args:
        input_path: Ruta al archivo de audio
        target_lufs: LUFS objetivo
        true_peak: True peak máximo
        filter_chain: Cadena de filtros FFmpeg a aplicar antes
        filter_output: Etiqueta de salida del filter_chain
        verbose: Mostrar output detallado
        lra: Loudness Range objetivo (LU). Si None, usa LOUDNORM_LRA_DEFAULT
        
    Returns:
        Tuple con stats del audio y stderr de FFmpeg
    """
    if lra is None:
        lra = LOUDNORM_LRA_DEFAULT
    
    # Detectar si es mono para usar dual_mono
    audio_info = get_audio_info(str(input_path))
    channels = audio_info.get('channels', 2)
    dual_mono = "true" if channels == 1 else "false"
    
    filter_args = f"loudnorm=I={target_lufs}:LRA={lra}:TP={true_peak}:dual_mono={dual_mono}:print_format=json"
    filter_complex = f"{filter_chain};[{filter_output}]{filter_args}[out]"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-f",
        "null",
        "-",
    ]
    result = run_ffmpeg(cmd, verbose=verbose)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg falló en análisis con pre-proceso: {result.stderr.strip()}")
    stats = extract_loudnorm_stats(result.stderr + result.stdout)
    return stats, result.stderr


def _extract_last_rms_level(output: str) -> float | None:
    overall_matches = re.findall(
        r"Overall\.RMS[_ ]level(?:\s*dB)?\s*[:=]\s*(-?(?:\d+(?:\.\d+)?|inf|nan))",
        output,
        re.IGNORECASE,
    )
    for value in reversed(overall_matches):
        norm = value.lower()
        if norm in {"inf", "-inf", "nan"}:
            continue
        try:
            return float(value)
        except ValueError:
            continue

    matches = re.findall(
        r"(?:Overall\.)?RMS[_ ]level(?:\s*dB)?\s*[:=]\s*(-?(?:\d+(?:\.\d+)?|inf|nan))",
        output,
        re.IGNORECASE,
    )
    for value in reversed(matches):
        norm = value.lower()
        if norm in {"inf", "-inf", "nan"}:
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return None


def analyze_eq_bands(
    input_path: pathlib.Path,
    verbose: bool,
    band_range_db: float,
) -> Tuple[Dict[str, float], list[str]]:
    """
    Analiza RMS por bandas y genera sugerencias básicas.

    Prioriza robustez de medición sobre velocidad: usa `volumedetect`
    por banda y toma los valores reales reportados por logs de ffmpeg.
    """
    results: Dict[str, float] = {}
    peak_levels: Dict[str, float] = {}

    mean_pattern = re.compile(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB")
    max_pattern = re.compile(r"max_volume:\s*(-?\d+\.?\d*)\s*dB")

    for label, low_hz, high_hz, _attack, _release, _width in BAND_CONFIG:
        band_filter = f"highpass=f={low_hz},lowpass=f={high_hz},volumedetect"
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(input_path),
            "-af",
            band_filter,
            "-f",
            "null",
            "-",
        ]
        result = run_ffmpeg(cmd, verbose=verbose)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg falló en análisis de banda {label}: {result.stderr.strip()}")

        output = result.stderr + result.stdout
        mean_match = mean_pattern.search(output)
        max_match = max_pattern.search(output)

        # Valor principal para balance tonal: mean_volume por banda.
        if mean_match:
            try:
                rms_level = float(mean_match.group(1))
                results[label] = max(-80.0, rms_level)
            except ValueError:
                results[label] = -80.0
        elif max_match:
            # Fallback conservador: si no hay mean, usar max para no dejar banda vacía.
            try:
                results[label] = max(-80.0, float(max_match.group(1)))
            except ValueError:
                results[label] = -80.0
        else:
            results[label] = -80.0

        if max_match:
            try:
                peak_levels[label] = float(max_match.group(1))
            except ValueError:
                pass

    suggestions: list[str] = []
    if results:
        avg = sum(results.values()) / len(results)
        for label, rms_level in results.items():
            # Advertir sobre posible saturación en bandas sensibles
            peak_db = peak_levels.get(label, -100.0)
            if peak_db > -1.0 and label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"):
                suggestions.append(f"{label}: ADVERTENCIA - pico cercano a 0dB ({peak_db:.1f}dB), riesgo de saturación!")
            elif rms_level > avg + band_range_db:
                suggestions.append(f"{label}: posible exceso; considera bajar ~2-3 dB.")
            elif rms_level < avg - band_range_db:
                if label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)") and peak_db > -3.0:
                    continue
                suggestions.append(f"{label}: posible falta; considera subir ~2-3 dB.")
    
    return results, suggestions


def analyze_voice_band(input_path: pathlib.Path, verbose: bool) -> float | None:
    label, low_hz, high_hz = VOICE_BAND
    band_filter = f"highpass=f={low_hz},lowpass=f={high_hz},astats=metadata=1:reset=1"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-af",
        band_filter,
        "-f",
        "null",
        "-",
    ]
    result = run_ffmpeg(cmd, verbose=verbose)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg falló en análisis de banda vocal ({label}): {result.stderr.strip()}")
    return _extract_last_rms_level(result.stderr + result.stdout)


def analyze_eq_and_voice(
    input_path: pathlib.Path,
    verbose: bool,
    band_range_db: float,
) -> Tuple[Dict[str, float], list[str], float | None]:
    """
    Analiza bandas EQ + banda vocal en una sola invocación de FFmpeg.

    Reduce pasadas respecto a `analyze_eq_bands()` + `analyze_voice_band()`.
    """
    results: Dict[str, float] = {}
    peak_levels: Dict[str, float] = {}

    # [0:a]asplit=7 -> 6 bandas de EQ + 1 rama vocal
    split_labels = [f"b{i}" for i in range(len(BAND_CONFIG))]
    voice_label = "bv"
    filter_parts = [
        f"[0:a]asplit={len(split_labels) + 1}"
        + "".join(f"[{label}]" for label in split_labels)
        + f"[{voice_label}]"
    ]

    for idx, (_label, low_hz, high_hz, *_rest) in enumerate(BAND_CONFIG):
        src = split_labels[idx]
        # Mantener la medición compatible con la ruta histórica.
        filter_parts.append(
            f"[{src}]highpass=f={low_hz},lowpass=f={high_hz},volumedetect,anullsink"
        )

    # Rama vocal (RMS con astats)
    _voice_name, voice_low_hz, voice_high_hz = VOICE_BAND
    filter_parts.append(
        f"[{voice_label}]highpass=f={voice_low_hz},lowpass=f={voice_high_hz},"
        "volumedetect[analysis_out]"
    )

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[analysis_out]",
        "-f",
        "null",
        "-",
    ]
    result = run_ffmpeg(cmd, verbose=verbose)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg falló en análisis combinado de bandas/voz: {result.stderr.strip()}")

    output = result.stderr + result.stdout
    mean_pattern = re.compile(r"Parsed_volumedetect_(\d+).*mean_volume:\s*(-?\d+\.?\d*)\s*dB")
    max_pattern = re.compile(r"Parsed_volumedetect_(\d+).*max_volume:\s*(-?\d+\.?\d*)\s*dB")
    means_by_filter = {int(m.group(1)): float(m.group(2)) for m in mean_pattern.finditer(output)}
    peaks_by_filter = {int(m.group(1)): float(m.group(2)) for m in max_pattern.finditer(output)}
    filter_ids = sorted(means_by_filter)
    mean_values = [means_by_filter[index] for index in filter_ids]
    max_values = [peaks_by_filter.get(index, -100.0) for index in filter_ids]

    for idx, (label, _low_hz, _high_hz, *_rest) in enumerate(BAND_CONFIG):
        if idx < len(mean_values):
            results[label] = max(-80.0, mean_values[idx])
        elif idx < len(max_values):
            results[label] = max(-80.0, max_values[idx])
        else:
            results[label] = -80.0
        if idx < len(max_values):
            peak_levels[label] = max_values[idx]

    voice_rms = mean_values[len(BAND_CONFIG)] if len(mean_values) > len(BAND_CONFIG) else None

    suggestions: list[str] = []
    if results:
        avg = sum(results.values()) / len(results)
        for label, rms_level in results.items():
            peak_db = peak_levels.get(label, -100.0)
            if peak_db > -1.0 and label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"):
                suggestions.append(f"{label}: ADVERTENCIA - pico cercano a 0dB ({peak_db:.1f}dB), riesgo de saturación!")
            elif rms_level > avg + band_range_db:
                suggestions.append(f"{label}: posible exceso; considera bajar ~2-3 dB.")
            elif rms_level < avg - band_range_db:
                if label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)") and peak_db > -3.0:
                    continue
                suggestions.append(f"{label}: posible falta; considera subir ~2-3 dB.")

    return results, suggestions, voice_rms


def compute_spectrum(
    input_path: pathlib.Path,
    sample_rate: int = 22050,
    max_seconds: int = 30,
) -> tuple[list[float], list[float]] | None:
    """Calcula espectro con FFT simple para visualización."""
    try:
        import numpy as np
    except Exception:
        return None
    samples = get_audio_mono_samples(str(input_path), sample_rate=sample_rate, max_seconds=max_seconds)
    if not samples:
        return None
    data = np.array(samples, dtype=np.float32)
    if data.size < 2048:
        return None
    window_size = min(16384, data.size)
    segment = data[:window_size]
    window = np.hanning(window_size)
    windowed = segment * window
    spectrum = np.fft.rfft(windowed)
    freqs = np.fft.rfftfreq(window_size, 1.0 / sample_rate)
    mags = np.abs(spectrum)
    mags_db = 20 * np.log10(np.maximum(mags, 1e-9))
    return freqs.tolist(), mags_db.tolist()


def analyze_silence_edges(
    input_path: pathlib.Path,
    noise_db: float = -50.0,
    min_duration: float = 0.3,
) -> tuple[float, float, str]:
    """Detecta silencios inicial/final para sugerir fades.

    Analiza la tendencia de volumen (RMS en 3 puntos + peak) para distinguir
    entre un fade natural del productor y un corte abrupto que necesita fade."""
    import re

    duration = get_audio_duration(str(input_path))
    if duration is None:
        return 0.0, 0.0, "No se pudo obtener duración."
    filter_args = f"silencedetect=noise={noise_db:.1f}dB:d={min_duration:.2f}"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-af",
        filter_args,
        "-f",
        "null",
        "-",
    ]
    result = run_ffmpeg(cmd, verbose=False)
    if result.returncode != 0:
        return 0.0, 0.0, "No se pudo analizar silencios."

    silence_start_re = re.compile(r"silence_start:\s*([\d\.]+)")
    silence_end_re = re.compile(r"silence_end:\s*([\d\.]+)")
    starts = [float(m.group(1)) for m in silence_start_re.finditer(result.stderr)]
    ends = [float(m.group(1)) for m in silence_end_re.finditer(result.stderr)]
    segments: list[tuple[float, float | None]] = []
    end_iter = iter(ends)
    for start in starts:
        end = next(end_iter, None)
        segments.append((start, end))

    lead_duration = 0.0
    tail_duration = 0.0
    for start, end in segments:
        if start <= 0.1 and end is not None:
            lead_duration = max(lead_duration, end - start)
    for start, end in segments:
        if end is None or end >= duration - 0.1:
            tail_duration = max(tail_duration, duration - start)

    def _probe_rms_level(path: str, seek_s: float, probe_dur_s: float = 0.25) -> float | None:
        """Mide RMS medio en una ventana de probe_dur_s a partir de seek_s."""
        try:
            rms_cmd = [
                "ffmpeg", "-hide_banner", "-nostdin",
                "-ss", f"{seek_s:.3f}",
                "-t", f"{probe_dur_s:.3f}",
                "-i", path,
                "-af", "volumedetect",
                "-f", "null", "-",
            ]
            rms_res = run_ffmpeg(rms_cmd, verbose=False)
            mean_match = re.search(r"mean_volume:\s*([-\d\.]+)", rms_res.stderr)
            if mean_match:
                return float(mean_match.group(1))
        except Exception:
            pass
        return None

    def _probe_peak_level(path: str, seek_s: float, probe_dur_s: float = 0.5) -> float | None:
        """Mide peak máximo en una ventana de probe_dur_s a partir de seek_s."""
        try:
            peak_cmd = [
                "ffmpeg", "-hide_banner", "-nostdin",
                "-ss", f"{seek_s:.3f}",
                "-t", f"{probe_dur_s:.3f}",
                "-i", path,
                "-af", "volumedetect",
                "-f", "null", "-",
            ]
            peak_res = run_ffmpeg(peak_cmd, verbose=False)
            peak_match = re.search(r"max_volume:\s*([-\d\.]+)", peak_res.stderr)
            if peak_match:
                return float(peak_match.group(1))
        except Exception:
            pass
        return None

    def _is_hard_transition(path: str, silence_end: float, direction: str) -> tuple[bool, str]:
        """Analiza si la transición antes/después del silencio es abrupta.
        
        direction='before': mide 3 puntos antes del silencio (-2s, -1s, -0.3s)
        direction='after':  mide 3 puntos después del silencio (+0.3s, +0.8s, +1.5s)
        
        Retorna (is_hard, detail_str)."""
        if direction == "before":
            # Puntos hacia atrás desde silence_end
            points = [
                max(0.05, silence_end - 2.0),
                max(0.05, silence_end - 1.0),
                max(0.05, silence_end - 0.3),
            ]
        else:
            # Puntos hacia adelante desde silence_end
            points = [
                min(duration - 0.3, silence_end + 0.3),
                min(duration - 0.3, silence_end + 0.8),
                min(duration - 0.3, silence_end + 1.5),
            ]

        levels: list[float] = []
        for p in points:
            lvl = _probe_rms_level(path, p)
            if lvl is not None:
                levels.append(lvl)

        if len(levels) < 2:
            # No hay suficientes datos — asumimos abrupto por seguridad
            return True, "insufficient_data"

        # Tendencia: comparar primer y último punto
        first = levels[0]
        last = levels[-1]
        trend_db = last - first  # positivo = subiendo, negativo = bajando

        # Peak en el punto más cercano al silencio
        peak_point = points[-1] if direction == "before" else points[0]
        peak = _probe_peak_level(path, peak_point)
        peak_high = peak is not None and peak > -6.0

        if direction == "before":
            # Antes del silencio final: si el volumen está BAJANDO → fade natural
            is_natural_decay = trend_db < -3.0  # cayó más de 3 dB
            is_hard = not is_natural_decay or peak_high
            detail = f"trend={trend_db:+.1f}dB pts={[f'{l:.0f}' for l in levels]} peak={peak}"
        else:
            # Después del silencio inicial: si el volumen está SUBIENDO fuerte → natural
            is_natural_rise = trend_db > 5.0  # subió más de 5 dB (entrada gradual)
            is_hard = not is_natural_rise or peak_high
            detail = f"trend={trend_db:+.1f}dB pts={[f'{l:.0f}' for l in levels]} peak={peak}"

        return is_hard, detail

    fade_in = 0.0
    fade_out = 0.0
    is_hard_start = False
    is_hard_cut = False
    start_detail = ""
    cut_detail = ""

    if lead_duration >= min_duration:
        is_hard_start, start_detail = _is_hard_transition(
            str(input_path), lead_duration, "after"
        )
        if is_hard_start:
            fade_in = max(0.2, min(2.0, lead_duration * 0.6))

    if tail_duration >= min_duration:
        tail_cut_point = duration - tail_duration
        is_hard_cut, cut_detail = _is_hard_transition(
            str(input_path), tail_cut_point, "before"
        )
        if is_hard_cut:
            fade_out = max(0.2, min(3.0, tail_duration * 0.6))

    detail = (
        f"lead={lead_duration:.2f}s tail={tail_duration:.2f}s "
        f"hard_start={is_hard_start}({start_detail}) "
        f"hard_cut={is_hard_cut}({cut_detail})"
    )
    return fade_in, fade_out, detail


def evaluate_mix(stats: Dict[str, float], target_lufs: float, true_peak: float) -> Tuple[str, str]:
    """Genera una evaluación breve y consejos basados en los estadísticos loudnorm."""
    advice_lines: list[str] = []
    score = 100

    input_i = stats.get("input_i", 0.0)
    input_tp = stats.get("input_tp", 0.0)
    input_lra = stats.get("input_lra", 0.0)
    offset = stats.get("target_offset", 0.0)

    delta = input_i - target_lufs
    if abs(delta) <= 1.0:
        advice_lines.append("Nivel integrado cerca del objetivo: OK.")
    elif delta < -3.0:
        advice_lines.append("Muy bajo respecto al objetivo: considera aumentar ganancia o compresión.")
        score -= 20
    elif delta < -1.0:
        advice_lines.append("Bajo: subir leve ganancia o aplicar make-up after compression.")
        score -= 10
    elif delta > 1.0:
        advice_lines.append("Por encima del objetivo: reduce ganancia o aplica un normalizador previo.")
        score -= 15

    if input_tp >= true_peak:
        advice_lines.append("True peak excede o iguala el límite: usar limitador/trimming para evitar clipping.")
        score -= 25
    elif input_tp >= (true_peak - 1.0):
        advice_lines.append("True peak cercano al límite: revisar transientes y aplicar limitador suave.")
        score -= 10

    if input_lra > 10.0:
        advice_lines.append("LRA alto: la mezcla tiene dinámicas amplias; considera compresión multibanda o automatizaciones.")
        score -= 10
    elif input_lra < 4.0:
        advice_lines.append("LRA bajo: la mezcla está muy comprimida; verifica si falta dinámica.")
        score -= 5

    if abs(offset) > 3.0:
        advice_lines.append("Offset recomendado grande: puede necesitar procesamiento significativo; revisar ganancia/processing chain.")
        score -= 10

    if score >= 85:
        rating = "Bueno"
    elif score >= 65:
        rating = "Aceptable"
    else:
        rating = "Necesita trabajo"

    advice = "\n".join(advice_lines) if advice_lines else "Sin recomendaciones específicas; parece estar bien balanceado."
    return rating, advice


def format_analysis_summary(
    label: str,
    stats: Dict[str, float],
    band_stats: Dict[str, float],
    voice_rms: float | None,
    target_lufs: float,
    true_peak: float,
) -> str:
    lines = [f"{label}:"]
    lines.append(f"  Input I (LUFS): {stats.get('input_i', 0):.2f}")
    lines.append(f"  Input TP (dBTP): {stats.get('input_tp', 0):.2f}")
    lines.append(f"  Input LRA (LU): {stats.get('input_lra', 0):.2f}")
    if voice_rms is not None:
        lines.append(f"  {VOICE_BAND[0]}: {voice_rms:.2f} dB")
    if band_stats:
        lines.append("  Bandas (RMS dB):")
        for band_label, value in band_stats.items():
            lines.append(f"    {band_label}: {value:.2f}")
    rating, advice = evaluate_mix(stats, target_lufs, true_peak)
    lines.append(f"  Evaluación: {rating}")
    lines.append(f"  Consejos: {advice}")
    return "\n".join(lines)


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"")


def write_analysis_toml(
    output_path: pathlib.Path,
    target_lufs: float,
    true_peak: float,
    loudness_preset: str,
    output_preset: str,
    output_sr: int | None,
    output_bit_depth: str | None,
    output_format: str | None,
    dynamic_eq: bool,
    stereo_width: bool,
    brickwall: bool,
    analyze_only: bool,
    deesser: bool,
    fade_in: float,
    fade_out: float,
    signature: Dict[str, str] | None,
    before_stats: Dict[str, float],
    before_band: Dict[str, float],
    before_voice: float | None,
    after_stats: Dict[str, float] | None,
    after_band: Dict[str, float] | None,
    after_voice: float | None,
    before_rating: str,
    before_advice: str,
    after_rating: str | None,
    after_advice: str | None,
    resource_info: Dict[str, object] | None = None,
    ai_master_info: Dict[str, object] | None = None,
) -> pathlib.Path:
    log_dir = output_path.parent / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    toml_path = log_dir / f"{output_path.stem}.toml"

    def render_block(
        prefix: str,
        stats: Dict[str, float],
        band: Dict[str, float],
        voice: float | None,
        rating: str,
        advice: str,
    ) -> list[str]:
        lines = [f"[{prefix}]"]
        lines.append(f'input_i = {stats.get("input_i", 0.0):.2f}')
        lines.append(f'input_tp = {stats.get("input_tp", 0.0):.2f}')
        lines.append(f'input_lra = {stats.get("input_lra", 0.0):.2f}')
        lines.append(f'input_thresh = {stats.get("input_thresh", 0.0):.2f}')
        lines.append(f'target_offset = {stats.get("target_offset", 0.0):.2f}')
        if voice is not None:
            lines.append(f'voice_rms = {voice:.2f}')
        lines.append(f'rating = "{_toml_escape(rating)}"')
        lines.append(f'advice = "{_toml_escape(advice)}"')
        if band:
            lines.append(f"[{prefix}.bands]")
            for key, value in band.items():
                key_norm = key.replace(" ", "_").replace("-", "_").replace("(", "").replace(")", "").replace("/", "_")
                lines.append(f'{key_norm} = {value:.2f}')
        return lines

    lines: list[str] = []
    lines.append("[settings]")
    lines.append(f'loudness_preset = "{_toml_escape(loudness_preset)}"')
    lines.append(f'output_preset = "{_toml_escape(output_preset)}"')
    if output_format is not None:
        lines.append(f'output_format = "{_toml_escape(output_format)}"')
    lines.append(f'target_lufs = {target_lufs:.2f}')
    lines.append(f'true_peak = {true_peak:.2f}')
    lines.append(f'dynamic_eq = {"true" if dynamic_eq else "false"}')
    lines.append(f'stereo_width = {"true" if stereo_width else "false"}')
    lines.append(f'brickwall = {"true" if brickwall else "false"}')
    lines.append(f'deesser = {"true" if deesser else "false"}')
    lines.append(f'fade_in = {fade_in:.2f}')
    lines.append(f'fade_out = {fade_out:.2f}')
    lines.append(f'analyze_only = {"true" if analyze_only else "false"}')
    if output_sr is not None:
        lines.append(f'output_sample_rate = {output_sr}')
    if output_bit_depth is not None:
        lines.append(f'output_bit_depth = "{_toml_escape(output_bit_depth)}"')
    if signature:
        lines.append("[signature]")
        for key, value in signature.items():
            if value:
                lines.append(f'{key} = "{_toml_escape(value)}"')

    if resource_info:
        lines.append("[resources]")
        resource_summary = resource_info.get("summary")
        if isinstance(resource_summary, str) and resource_summary:
            lines.append(f'resource_summary = "{_toml_escape(resource_summary)}"')
        cpu_snapshot = resource_info.get("cpu")
        if isinstance(cpu_snapshot, dict):
            lines.append("[resources.cpu]")
            for key in ("cpu_count", "cpu_percent", "memory_percent", "memory_available_gb", "ffmpeg_processes"):
                value = cpu_snapshot.get(key)
                if value is None:
                    continue
                if isinstance(value, float):
                    lines.append(f"{key} = {value:.2f}")
                else:
                    lines.append(f"{key} = {value}")
        gpu_snapshot = resource_info.get("gpu")
        if isinstance(gpu_snapshot, dict):
            lines.append("[resources.gpu]")
            for key in (
                "backend",
                "device_count",
                "name",
                "driver_version",
                "utilization_percent",
                "memory_total_mb",
                "memory_used_mb",
                "memory_free_mb",
                "available",
            ):
                value = gpu_snapshot.get(key)
                if value is None:
                    continue
                if isinstance(value, str):
                    lines.append(f'{key} = "{_toml_escape(value)}"')
                elif isinstance(value, float):
                    lines.append(f"{key} = {value:.2f}")
                elif isinstance(value, bool):
                    lines.append(f"{key} = {'true' if value else 'false'}")
                else:
                    lines.append(f"{key} = {value}")

    if ai_master_info:
        lines.append("[ai_master]")
        for key in (
            "enabled",
            "status",
            "provider",
            "model",
            "used_ai_strategy",
            "fallback_reason",
            "diagnosis",
            "strategy_json",
        ):
            value = ai_master_info.get(key)
            if value is None:
                continue
            if isinstance(value, bool):
                lines.append(f"{key} = {'true' if value else 'false'}")
            elif isinstance(value, (int, float)):
                lines.append(f"{key} = {value}")
            else:
                lines.append(f'{key} = "{_toml_escape(str(value))}"')
        notes = ai_master_info.get("notes")
        if isinstance(notes, list) and notes:
            lines.append("[ai_master.notes]")
            for idx, note in enumerate(notes, start=1):
                lines.append(f'note_{idx} = "{_toml_escape(str(note))}"')

    lines.extend(render_block("before", before_stats, before_band, before_voice, before_rating, before_advice))
    if after_stats is not None and after_band is not None and after_rating is not None and after_advice is not None:
        lines.extend(render_block("after", after_stats, after_band, after_voice, after_rating, after_advice))

    toml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return toml_path


def validate_saturation_settings(
    band_stats: Dict[str, float] | None,
    saturation_band_drive_db: Dict[str, float] | None,
    saturation_band_mix: Dict[str, float] | None,
) -> list[str]:
    """Valida la configuración de saturación y genera advertencias para bandas sensibles.
    
    Args:
        band_stats: Estadísticas RMS por banda
        saturation_band_drive_db: Drive de saturación por banda
        saturation_band_mix: Mix de saturación por banda
        
    Returns:
        Lista de advertencias/sugerencias sobre la configuración
    """
    warnings: list[str] = []
    
    if not saturation_band_drive_db or not saturation_band_mix:
        return warnings
    
    # Verificar bandas sensibles: High-Mid y Air
    sensitive_bands = ["High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"]
    
    for band_label in sensitive_bands:
        drive_db = saturation_band_drive_db.get(band_label, 0.0)
        mix = saturation_band_mix.get(band_label, 0.0)
        max_drive = MAX_SATURATION_DRIVE_DB.get(band_label, 24.0)
        headroom = BAND_HEADROOM_DB.get(band_label, 0.0)
        
        # Advertir si el drive excede el límite recomendado
        if drive_db > max_drive:
            warnings.append(
                f"⚠️ {band_label}: Drive de saturación ({drive_db:.1f}dB) excede el límite "
                f"recomendado ({max_drive:.1f}dB). Se aplicará limitador de seguridad."
            )
        
        # Advertir si el mix y drive combinados son muy altos
        if mix > 0.7 and drive_db > max_drive * 0.7:
            warnings.append(
                f"⚠️ {band_label}: Combinación alta de drive ({drive_db:.1f}dB) y mix ({mix*100:.0f}%) "
                f"puede causar saturación. Considera reducir uno de los valores."
            )
        
        # Informar sobre headroom aplicado
        if mix > 0.3:
            warnings.append(
                f"ℹ️ {band_label}: Se aplicará headroom de seguridad de {headroom:.1f}dB "
                f"para prevenir clipping."
            )
        
        # Verificar si hay análisis previo y advertir sobre niveles altos
        if band_stats and band_label in band_stats:
            rms = band_stats[band_label]
            if rms > -6.0 and drive_db > 6.0:
                warnings.append(
                    f"⚠️ {band_label}: RMS alto ({rms:.1f}dB) + drive ({drive_db:.1f}dB) "
                    f"aumenta riesgo de saturación. Considera bajar drive o usar EQ previo."
                )
    
    return warnings


# =============================================================================
# NUEVOS ANÁLISIS PARA AUTO-MASTER INTELIGENTE
# =============================================================================

def detect_clipping(
    input_path: pathlib.Path,
    threshold_db: float = -0.1,
    verbose: bool = False,
) -> tuple[bool, float, int]:
    """
    Detecta si hay clipping/distorsión en el audio.
    
    Args:
        input_path: Ruta al archivo de audio
        threshold_db: Umbral para considerar clipping (default -0.1 dBFS)
        verbose: Mostrar comandos ffmpeg
        
    Returns:
        (has_clipping, max_peak_db, clip_count)
    """
    # Usar astats para obtener estadísticas de pico
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-af",
        "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.Peak_level",
        "-f",
        "null",
        "-",
    ]
    result = run_ffmpeg(cmd, verbose=verbose)
    
    # Buscar el pico máximo
    peak_pattern = re.compile(r"lavfi\.astats\.Overall\.Peak_level=(-?\d+\.?\d*)")
    peaks = [float(m.group(1)) for m in peak_pattern.finditer(result.stderr)]
    
    if not peaks:
        # Fallback: usar volumedetect
        cmd_vol = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin", 
            "-i",
            str(input_path),
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]
        result_vol = run_ffmpeg(cmd_vol, verbose=verbose)
        max_vol_pattern = re.compile(r"max_volume:\s*(-?\d+\.?\d*)\s*dB")
        match = max_vol_pattern.search(result_vol.stderr)
        if match:
            max_peak = float(match.group(1))
        else:
            return False, -100.0, 0
    else:
        max_peak = max(peaks)
    
    # Contar cuántos frames superan el umbral
    clip_count = sum(1 for p in peaks if p >= threshold_db) if peaks else (1 if max_peak >= threshold_db else 0)
    has_clipping = max_peak >= threshold_db
    
    return has_clipping, max_peak, clip_count


def detect_noise_floor(
    input_path: pathlib.Path,
    sample_duration: float = 2.0,
    verbose: bool = False,
) -> tuple[float, str]:
    """
    Detecta el nivel de ruido de fondo analizando las partes más silenciosas.
    
    Args:
        input_path: Ruta al archivo de audio
        sample_duration: Duración a analizar al inicio/final
        verbose: Mostrar comandos ffmpeg
        
    Returns:
        (noise_floor_db, noise_level_category)
    """
    duration = get_audio_duration(str(input_path))
    if duration is None or duration < 1.0:
        return -60.0, "Unknown"
    
    # Analizar los primeros y últimos segundos buscando el mínimo RMS
    # Usamos silencedetect con diferentes umbrales para estimar el piso de ruido
    noise_levels = []
    
    # Probar con diferentes umbrales de silencio
    for noise_db in [-60, -50, -40, -30]:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(input_path),
            "-af",
            f"silencedetect=noise={noise_db}dB:d=0.1",
            "-f",
            "null",
            "-",
        ]
        result = run_ffmpeg(cmd, verbose=verbose)
        
        # Contar cuántos silencios se detectan
        silence_count = result.stderr.count("silence_start")
        if silence_count > 0:
            noise_levels.append(noise_db)
            break
    
    # Usar volumedetect para obtener referencia RMS
    cmd_vol = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ]
    result_vol = run_ffmpeg(cmd_vol, verbose=verbose)
    
    mean_pattern = re.compile(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB")
    max_pattern = re.compile(r"max_volume:\s*(-?\d+\.?\d*)\s*dB")
    match = mean_pattern.search(result_vol.stderr)
    mean_vol = float(match.group(1)) if match else -30.0
    match_max = max_pattern.search(result_vol.stderr)
    max_vol = float(match_max.group(1)) if match_max else 0.0
    
    # Estimar piso de ruido: si hay silencios detectados, usar el umbral más bajo
    # Si no, estimar desde la dinámica (max - mean)
    if noise_levels:
        noise_floor = float(noise_levels[0])
    else:
        # Sin silencios: el track está comprimido/limitado
        # El piso de ruido está cerca del nivel medio menos la dinámica
        dynamic_range = max_vol - mean_vol
        noise_floor = mean_vol - max(6.0, dynamic_range * 0.7)
    
    # Categorizar el nivel de ruido
    if noise_floor <= -60:
        category = "Excellent"
    elif noise_floor <= -50:
        category = "Good"
    elif noise_floor <= -40:
        category = "Moderate"
    elif noise_floor <= -30:
        category = "High"
    else:
        category = "VeryHigh"
    
    return noise_floor, category


def detect_stereo_characteristics(
    input_path: pathlib.Path,
    verbose: bool = False,
) -> dict:
    """
    Analiza las características stereo del audio.
    
    Returns:
        {
            'is_mono': bool,
            'stereo_width': float (0-1),
            'stereo_category': str ('Mono'|'Narrow'|'Normal'|'Wide'|'VeryWide'),
            'mid_side_ratio': float,
            'correlation': float (-1 a 1)
        }
    """
    # Usar astats para obtener correlación stereo
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-af",
        "astats=metadata=1,ametadata=print:key=lavfi.astats.Overall.DC_offset:key=lavfi.astats.Overall.Flat_factor",
        "-f",
        "null",
        "-",
    ]
    result = run_ffmpeg(cmd, verbose=verbose)
    
    # Usar stereotools para obtener correlación y ancho
    cmd_stereo = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-af",
        "stereotools=mode=lr>ms,astats=metadata=1:reset=1",
        "-f",
        "null",
        "-",
    ]
    result_stereo = run_ffmpeg(cmd_stereo, verbose=verbose)
    
    # Analizar canal L y R para determinar correlación
    try:
        samples = get_audio_mono_samples(str(input_path), max_samples=48000*5)  # 5 segundos
    except Exception:
        samples = None
    
    # Valores por defecto
    is_mono = False
    stereo_width = 0.5
    correlation = 1.0
    
    if samples is not None and len(samples) > 0:
        # Si las muestras son idénticas L/R, es mono
        # Este análisis es aproximado ya que get_audio_mono_samples devuelve mono mixdown
        pass
    
    # Usar volumedetect en canales separados para estimar mono
    cmd_left = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-af",
        "pan=mono|c0=c0,volumedetect",
        "-f",
        "null",
        "-",
    ]
    cmd_right = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-i",
        str(input_path),
        "-af",
        "pan=mono|c0=c1,volumedetect",
        "-f",
        "null",
        "-",
    ]
    
    result_left = run_ffmpeg(cmd_left, verbose=verbose)
    result_right = run_ffmpeg(cmd_right, verbose=verbose)
    
    mean_pattern = re.compile(r"mean_volume:\s*(-?\d+\.?\d*)\s*dB")
    
    match_left = mean_pattern.search(result_left.stderr)
    match_right = mean_pattern.search(result_right.stderr)
    
    left_vol = float(match_left.group(1)) if match_left else -30.0
    right_vol = float(match_right.group(1)) if match_right else -30.0
    
    # Diferencia entre canales
    channel_diff = abs(left_vol - right_vol)
    
    # Si la diferencia es enorme, uno de los canales está vacío
    if channel_diff > 20:
        is_mono = True
        stereo_width = 0.0
        stereo_category = "Mono"
    elif channel_diff < 0.5:
        # Canales muy similares - puede ser mono o stereo centrado
        # Usar análisis M/S para determinar
        cmd_side = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(input_path),
            "-af",
            "stereotools=mode=lr>ms,pan=mono|c0=c1,volumedetect",
            "-f",
            "null",
            "-",
        ]
        result_side = run_ffmpeg(cmd_side, verbose=verbose)
        match_side = mean_pattern.search(result_side.stderr)
        side_vol = float(match_side.group(1)) if match_side else -60.0
        
        # Ratio M/S: más negativo el Side = más mono
        mid_side_diff = (left_vol + right_vol) / 2 - side_vol
        
        if side_vol < -50:
            is_mono = True
            stereo_width = 0.0
            stereo_category = "Mono"
        elif mid_side_diff > 15:
            stereo_width = 0.2
            stereo_category = "Narrow"
        elif mid_side_diff > 8:
            stereo_width = 0.5
            stereo_category = "Normal"
        elif mid_side_diff > 3:
            stereo_width = 0.7
            stereo_category = "Wide"
        else:
            stereo_width = 0.9
            stereo_category = "VeryWide"
    else:
        stereo_width = 0.5
        stereo_category = "Normal"
    
    return {
        'is_mono': is_mono,
        'stereo_width': stereo_width,
        'stereo_category': stereo_category if 'stereo_category' in dir() else 'Normal',
        'left_vol': left_vol,
        'right_vol': right_vol,
        'channel_diff': channel_diff,
    }


def detect_peak_per_band(
    input_path: pathlib.Path,
    verbose: bool = False,
) -> dict[str, float]:
    """
    Detecta el pico máximo por cada banda de frecuencia.
    Útil para configurar el limitador multibanda automáticamente.
    
    Returns:
        Dict con el pico máximo (dB) por cada banda
    """
    from config import BAND_CONFIG
    
    peaks = {}
    
    # Construir filtro para analizar todas las bandas en una sola pasada
    filter_parts = []
    for i, (label, low, high, *_) in enumerate(BAND_CONFIG):
        if low == 20:
            band_filter = f"lowpass=f={high}"
        elif high == 16000:
            band_filter = f"highpass=f={low}"
        else:
            band_filter = f"highpass=f={low},lowpass=f={high}"
        filter_parts.append(f"[0:a]{band_filter},volumedetect[b{i}]")
    
    # Ejecutar análisis por banda (secuencial para evitar complejidad)
    for i, (label, low, high, *_) in enumerate(BAND_CONFIG):
        if low == 20:
            band_filter = f"lowpass=f={high}"
        elif high == 16000:
            band_filter = f"highpass=f={low}"
        else:
            band_filter = f"highpass=f={low},lowpass=f={high}"
        
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(input_path),
            "-af",
            f"{band_filter},volumedetect",
            "-f",
            "null",
            "-",
        ]
        result = run_ffmpeg(cmd, verbose=verbose)
        
        max_pattern = re.compile(r"max_volume:\s*(-?\d+\.?\d*)\s*dB")
        match = max_pattern.search(result.stderr)
        
        peaks[label] = float(match.group(1)) if match else -100.0
    
    return peaks


def get_comprehensive_audio_analysis(
    input_path: pathlib.Path,
    verbose: bool = False,
) -> dict:
    """
    Realiza un análisis completo del audio para auto-configuración.
    
    Returns:
        Diccionario con todos los análisis disponibles
    """
    from audio_analysis import analyze_eq_bands, analyze_voice_band
    
    analysis = {
        'path': str(input_path),
        'duration': get_audio_duration(str(input_path)),
    }
    
    # Análisis de bandas y voz (una sola pasada FFmpeg).
    band_stats, band_suggestions, voice_rms = analyze_eq_and_voice(
        input_path=input_path,
        verbose=verbose,
        band_range_db=3.0
    )
    analysis['band_stats'] = band_stats
    analysis['band_suggestions'] = band_suggestions
    analysis['voice_rms'] = voice_rms
    
    # Análisis de clipping
    has_clipping, max_peak, clip_count = detect_clipping(input_path, verbose=verbose)
    analysis['clipping'] = {
        'detected': has_clipping,
        'max_peak_db': max_peak,
        'clip_count': clip_count,
    }
    
    # Análisis de ruido
    noise_floor, noise_category = detect_noise_floor(input_path, verbose=verbose)
    analysis['noise'] = {
        'floor_db': noise_floor,
        'category': noise_category,
    }
    
    # Análisis stereo
    analysis['stereo'] = detect_stereo_characteristics(input_path, verbose=verbose)
    
    # Análisis de picos por banda
    analysis['band_peaks'] = detect_peak_per_band(input_path, verbose=verbose)
    
    # Análisis de silencios para fades
    fade_in, fade_out, fade_detail = analyze_silence_edges(input_path)
    analysis['silence'] = {
        'suggested_fade_in': fade_in,
        'suggested_fade_out': fade_out,
        'detail': fade_detail,
    }
    
    return analysis
