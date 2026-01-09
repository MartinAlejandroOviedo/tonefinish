import pathlib
import re
from typing import Dict, Tuple

from audio_tools import extract_loudnorm_stats, run_ffmpeg
from config import VOICE_BAND, BAND_CONFIG


def analyze_audio(input_path: pathlib.Path, target_lufs: float, true_peak: float, verbose: bool) -> Tuple[Dict[str, float], str]:
    """Ejecuta la primera pasada de loudnorm para obtener estadísticos."""
    filter_args = f"loudnorm=I={target_lufs}:LRA=11:TP={true_peak}:print_format=json"
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
) -> Tuple[Dict[str, float], str]:
    """Análisis loudnorm aplicando un pre-proceso antes de medir."""
    filter_args = f"loudnorm=I={target_lufs}:LRA=11:TP={true_peak}:print_format=json"
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
    matches = re.findall(r"Overall\.RMS_level:\s*(-?[\d\.]+)", output)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def analyze_eq_bands(
    input_path: pathlib.Path,
    verbose: bool,
    band_range_db: float,
) -> Tuple[Dict[str, float], list[str]]:
    """Analiza RMS por bandas y genera sugerencias básicas."""
    results: Dict[str, float] = {}
    for label, low_hz, high_hz, _attack, _release, _width in BAND_CONFIG:
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
            raise RuntimeError(f"ffmpeg falló en análisis de bandas ({label}): {result.stderr.strip()}")
        rms_level = _extract_last_rms_level(result.stderr + result.stdout)
        if rms_level is None:
            continue
        results[label] = rms_level

    suggestions: list[str] = []
    if results:
        avg = sum(results.values()) / len(results)
        for label, rms_level in results.items():
            if rms_level > avg + band_range_db:
                suggestions.append(f"{label}: posible exceso; considera bajar ~2-3 dB.")
            elif rms_level < avg - band_range_db:
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
) -> pathlib.Path:
    toml_path = output_path.with_suffix(".toml")

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

    lines.extend(render_block("before", before_stats, before_band, before_voice, before_rating, before_advice))
    if after_stats is not None and after_band is not None and after_rating is not None and after_advice is not None:
        lines.extend(render_block("after", after_stats, after_band, after_voice, after_rating, after_advice))

    toml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return toml_path
