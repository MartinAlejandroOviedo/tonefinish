"""
Análisis de espectro de frecuencias para mejorar decisiones automáticas.

Este módulo genera visualizaciones del espectro y extrae características
detalladas para optimizar la configuración de presets.
"""

from __future__ import annotations

import subprocess
import json
import pathlib
import time
from typing import Dict, List, Tuple, Optional, Any

import numpy as np

try:
    import cupy as cp  # type: ignore
    CUPY_AVAILABLE = True
except Exception:
    cp = None  # type: ignore
    CUPY_AVAILABLE = False


def _normalize_backend(backend: str | None) -> str:
    normalized = (backend or "auto").strip().lower()
    if normalized in {"gpu", "cuda"}:
        return "gpu"
    if normalized in {"cpu", "numpy"}:
        return "cpu"
    return "auto"


def _gpu_backend_available() -> bool:
    return CUPY_AVAILABLE


def _hardware_gpu_available() -> bool:
    try:
        from resource_monitor import ResourceMonitor

        return ResourceMonitor().has_gpu()
    except Exception:
        return False


def _extract_segment(
    input_path: pathlib.Path,
    duration: float,
    verbose: bool,
) -> tuple[np.ndarray, int]:
    """Extrae un segmento mono a 44.1 kHz para análisis espectral."""
    probe_cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        str(input_path),
    ]

    if verbose:
        print(f"$ {' '.join(probe_cmd)}")

    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    probe_data = json.loads(result.stdout)
    total_duration = float(probe_data["format"]["duration"])

    start_time = max(0, (total_duration / 2.0) - (duration / 2.0))

    extract_cmd = [
        "ffmpeg",
        "-v",
        "quiet",
        "-ss",
        str(start_time),
        "-t",
        str(duration),
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "44100",
        "-f",
        "f32le",
        "-",
    ]

    if verbose:
        print(f"$ {' '.join(extract_cmd)}")

    result = subprocess.run(extract_cmd, capture_output=True)
    audio_data = np.frombuffer(result.stdout, dtype=np.float32)
    if len(audio_data) == 0:
        raise ValueError("No se pudo extraer datos de audio")
    return audio_data, 44100


def _compute_spectrum_cpu(
    audio_data: np.ndarray,
    sample_rate: int,
) -> tuple[np.ndarray, np.ndarray, list[tuple[float, float]], float, float, float]:
    n = len(audio_data)
    fft = np.fft.rfft(audio_data)
    frequencies = np.fft.rfftfreq(n, 1 / sample_rate)
    magnitudes = 20 * np.log10(np.abs(fft) + 1e-10)
    magnitudes = magnitudes - np.max(magnitudes)
    peaks = _detect_peaks(frequencies, magnitudes)
    power = np.abs(fft) ** 2
    spectral_centroid = float(np.sum(frequencies * power) / np.sum(power))
    cumulative_power = np.cumsum(power)
    total_power = cumulative_power[-1]
    rolloff_idx = np.where(cumulative_power >= 0.85 * total_power)[0][0]
    spectral_rolloff = float(frequencies[rolloff_idx])
    geometric_mean = float(np.exp(np.mean(np.log(np.abs(fft) + 1e-10))))
    arithmetic_mean = float(np.mean(np.abs(fft)))
    spectral_flatness = float(geometric_mean / (arithmetic_mean + 1e-10))
    return frequencies, magnitudes, peaks, spectral_centroid, spectral_rolloff, spectral_flatness


def _compute_spectrum_gpu(
    audio_data: np.ndarray,
    sample_rate: int,
) -> tuple[np.ndarray, np.ndarray, list[tuple[float, float]], float, float, float]:
    if not CUPY_AVAILABLE or cp is None:
        return _compute_spectrum_cpu(audio_data, sample_rate)

    gpu_audio = cp.asarray(audio_data)
    n = int(gpu_audio.shape[0])
    fft = cp.fft.rfft(gpu_audio)
    frequencies = cp.fft.rfftfreq(n, 1 / sample_rate)
    magnitudes = 20 * cp.log10(cp.abs(fft) + 1e-10)
    magnitudes = magnitudes - cp.max(magnitudes)

    freq_np = cp.asnumpy(frequencies)
    mag_np = cp.asnumpy(magnitudes)
    peaks = _detect_peaks(freq_np, mag_np)

    power = cp.abs(fft) ** 2
    spectral_centroid = float(cp.sum(frequencies * power) / cp.sum(power))
    cumulative_power = cp.cumsum(power)
    total_power = cumulative_power[-1]
    rolloff_idx = int(cp.argmax(cumulative_power >= (0.85 * total_power)))
    spectral_rolloff = float(freq_np[rolloff_idx])
    geometric_mean = float(cp.exp(cp.mean(cp.log(cp.abs(fft) + 1e-10))))
    arithmetic_mean = float(cp.mean(cp.abs(fft)))
    spectral_flatness = float(geometric_mean / (arithmetic_mean + 1e-10))
    return freq_np, mag_np, peaks, spectral_centroid, spectral_rolloff, spectral_flatness


def _detect_peaks(frequencies: np.ndarray, magnitudes: np.ndarray) -> list[tuple[float, float]]:
    peaks = []
    threshold = -20.0
    min_separation = 100
    for i in range(1, len(magnitudes) - 1):
        if magnitudes[i] > threshold:
            if magnitudes[i] > magnitudes[i - 1] and magnitudes[i] > magnitudes[i + 1]:
                if not peaks or abs(frequencies[i] - peaks[-1][0]) > min_separation:
                    peaks.append((float(frequencies[i]), float(magnitudes[i])))
    peaks.sort(key=lambda x: x[1], reverse=True)
    return peaks[:10]


def analyze_spectrum_fft(
    input_path: pathlib.Path,
    duration: float = 10.0,
    verbose: bool = False,
    backend: str = "auto",
) -> Dict[str, Any]:
    """
    Analiza el espectro de frecuencias usando FFT.
    
    Args:
        input_path: Ruta al archivo de audio
        duration: Duración a analizar en segundos (desde el centro)
        verbose: Mostrar comandos
        backend: "auto", "cpu" o "gpu"
        
    Returns:
        Diccionario con datos del espectro:
        - frequencies: Array de frecuencias (Hz)
        - magnitudes: Array de magnitudes (dB)
        - peaks: Frecuencias con picos prominentes
        - spectral_centroid: Centro espectral en Hz
        - spectral_rolloff: Frecuencia de rolloff 85%
        - spectral_flatness: Planitud espectral (0-1)
    """
    backend = _normalize_backend(backend)
    audio_data, sample_rate = _extract_segment(input_path, duration, verbose)
    if backend == "gpu" and not _gpu_backend_available():
        backend = "cpu"

    if backend == "gpu":
        frequencies, magnitudes, peaks, spectral_centroid, spectral_rolloff, spectral_flatness = _compute_spectrum_gpu(
            audio_data, sample_rate
        )
    else:
        frequencies, magnitudes, peaks, spectral_centroid, spectral_rolloff, spectral_flatness = _compute_spectrum_cpu(
            audio_data, sample_rate
        )

    return {
        "frequencies": frequencies.tolist(),
        "magnitudes": magnitudes.tolist(),
        "peaks": peaks,
        "spectral_centroid": float(spectral_centroid),
        "spectral_rolloff": float(spectral_rolloff),
        "spectral_flatness": float(spectral_flatness),
        "sample_rate": sample_rate,
        "duration_analyzed": duration
    }


def analyze_dynamic_eq_evidence(
    input_path: pathlib.Path,
    duration: float = 8.0,
) -> Dict[str, Any]:
    """Extrae resonancias persistentes y predominio Mid/Side para decisiones IA."""
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(input_path),
    ], capture_output=True, text=True, check=False)
    total_duration = float((probe.stdout or "0").strip() or 0.0)
    start = max(0.0, total_duration * 0.5 - duration * 0.5)
    extract = subprocess.run([
        "ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}",
        "-i", str(input_path), "-ac", "2", "-ar", "44100", "-f", "f32le", "-",
    ], capture_output=True, check=False)
    if extract.returncode != 0:
        raise RuntimeError("No se pudo extraer audio para evidencia de EQ dinámica")
    stereo = np.frombuffer(extract.stdout, dtype=np.float32)
    if stereo.size < 8192:
        raise ValueError("Audio insuficiente para evidencia de EQ dinámica")
    stereo = stereo[: stereo.size - (stereo.size % 2)].reshape(-1, 2)
    mid = (stereo[:, 0] + stereo[:, 1]) * 0.5
    side = (stereo[:, 0] - stereo[:, 1]) * 0.5
    mid_rms = float(np.sqrt(np.mean(mid * mid) + 1e-12))
    side_rms = float(np.sqrt(np.mean(side * side) + 1e-12))
    mid_side_ratio = mid_rms / max(1e-12, mid_rms + side_rms)

    frame_size = 8192
    hop = 4096
    window = np.hanning(frame_size).astype(np.float32)
    spectra = []
    for offset in range(0, max(1, len(mid) - frame_size + 1), hop):
        frame = mid[offset:offset + frame_size]
        if frame.size != frame_size:
            break
        spectra.append(20.0 * np.log10(np.abs(np.fft.rfft(frame * window)) + 1e-9))
    if not spectra:
        raise ValueError("No se pudieron calcular ventanas espectrales")
    averaged = np.median(np.stack(spectra), axis=0)
    frequencies = np.fft.rfftfreq(frame_size, 1.0 / 44100.0)
    candidates: list[Dict[str, Any]] = []
    for index in range(2, len(averaged) - 2):
        frequency = float(frequencies[index])
        if frequency < 200.0 or frequency > 16000.0:
            continue
        if not (averaged[index] > averaged[index - 1] and averaged[index] >= averaged[index + 1]):
            continue
        outer_hz = max(120.0, frequency * 0.08)
        inner_hz = max(30.0, frequency * 0.012)
        neighborhood = (
            (frequencies >= frequency - outer_hz)
            & (frequencies <= frequency + outer_hz)
            & ((frequencies < frequency - inner_hz) | (frequencies > frequency + inner_hz))
        )
        if not np.any(neighborhood):
            continue
        local_floor = float(np.median(averaged[neighborhood]))
        prominence = float(averaged[index] - local_floor)
        if prominence < 3.0:
            continue
        band = (
            "bass" if frequency < 250.0 else "low_mid" if frequency < 500.0
            else "mid" if frequency < 2000.0 else "high_mid" if frequency < 6000.0
            else "air"
        )
        candidates.append({
            "frequency_hz": round(frequency, 1), "target": band,
            "measured_excess_db": round(prominence, 2),
            "mid_side_ratio": round(mid_side_ratio, 3),
        })
    candidates.sort(key=lambda item: item["measured_excess_db"], reverse=True)
    selected: list[Dict[str, Any]] = []
    for candidate in candidates:
        if any(abs(candidate["frequency_hz"] - prior["frequency_hz"]) < 120.0 for prior in selected):
            continue
        selected.append(candidate)
        if len(selected) >= 8:
            break
    left, right = stereo[:, 0], stereo[:, 1]
    denominator = float(np.sqrt(np.sum(left * left) * np.sum(right * right)) + 1e-12)
    stereo_correlation = float(np.sum(left * right) / denominator)
    peak = float(np.max(np.abs(stereo)) + 1e-12)
    rms = float(np.sqrt(np.mean(stereo * stereo) + 1e-12))
    transient_crest_db = float(20.0 * np.log10(peak / rms))
    def band_level(low: float, high: float) -> float:
        mask = (frequencies >= low) & (frequencies < high)
        return float(np.median(averaged[mask])) if np.any(mask) else -120.0
    low_level = band_level(45.0, 220.0)
    reference_level = band_level(250.0, 2000.0)
    harsh_level = band_level(2500.0, 6000.0)
    air_level = band_level(7000.0, 14000.0)
    low_mid_ratio = float(np.sqrt(np.mean(mid * mid)+1e-12) /
                          (np.sqrt(np.mean(mid * mid)+1e-12)+np.sqrt(np.mean(side * side)+1e-12)))
    return {
        "analysis_duration_seconds": min(duration, total_duration),
        "mid_side_ratio": round(mid_side_ratio, 3),
        "vocal_center_confidence": round(min(1.0, max(0.0,
            (mid_side_ratio - 0.45) / 0.45
            + (0.15 if any(1800.0 <= item["frequency_hz"] <= 8000.0 for item in selected) else 0.0)
        )), 3),
        "stereo_correlation": round(stereo_correlation, 4),
        "transient_crest_db": round(transient_crest_db, 2),
        "low_end_level_db": round(low_level - reference_level, 2),
        "low_end_mid_ratio": round(low_mid_ratio, 3),
        "harshness_excess_db": round(max(0.0, harsh_level - reference_level - 2.0), 2),
        "dullness_deficit_db": round(max(0.0, reference_level - air_level - 10.0), 2),
        "resonance_candidates": selected,
    }


def benchmark_spectrum_fft(
    input_path: pathlib.Path,
    duration: float = 10.0,
    verbose: bool = False,
    runs: int = 3,
) -> Dict[str, Any]:
    """Compara CPU vs GPU para el análisis espectral si GPU está disponible."""
    hardware_available = _hardware_gpu_available()
    backend_available = _gpu_backend_available()
    results: Dict[str, Any] = {
        "cpu_seconds": [],
        "gpu_seconds": [],
        "gpu_hardware_available": hardware_available,
        "gpu_backend_available": backend_available,
        "gpu_available": hardware_available and backend_available,
    }

    for _ in range(max(1, runs)):
        start = time.perf_counter()
        analyze_spectrum_fft(input_path, duration=duration, verbose=verbose, backend="cpu")
        results["cpu_seconds"].append(time.perf_counter() - start)

    if results["gpu_available"]:
        for _ in range(max(1, runs)):
            start = time.perf_counter()
            analyze_spectrum_fft(input_path, duration=duration, verbose=verbose, backend="gpu")
            results["gpu_seconds"].append(time.perf_counter() - start)

    cpu_avg = sum(results["cpu_seconds"]) / len(results["cpu_seconds"])
    results["cpu_avg_seconds"] = cpu_avg
    if results["gpu_seconds"]:
        gpu_avg = sum(results["gpu_seconds"]) / len(results["gpu_seconds"])
        results["gpu_avg_seconds"] = gpu_avg
        results["speedup"] = cpu_avg / gpu_avg if gpu_avg > 0 else None
    else:
        results["gpu_avg_seconds"] = None
        results["speedup"] = None

    speedup = results.get("speedup")
    if not hardware_available:
        results["recommended_next_stage"] = "cpu_only"
    elif not backend_available:
        results["recommended_next_stage"] = "gpu_backend_missing"
    elif isinstance(speedup, (int, float)):
        if speedup >= 1.25:
            results["recommended_next_stage"] = "analysis.features"
        else:
            results["recommended_next_stage"] = "analysis.spectrum"
    else:
        results["recommended_next_stage"] = "cpu_only"
    return results


def get_spectrum_characteristics(spectrum_data: Dict) -> Dict[str, Any]:
    """
    Extrae características interpretables del espectro para Auto-Master.
    
    Args:
        spectrum_data: Datos del analyze_spectrum_fft
        
    Returns:
        Características del espectro:
        - has_sub_bass: Hay energía significativa < 60 Hz
        - has_bass_punch: Pico prominente en 60-250 Hz
        - has_muddy_mids: Exceso en 250-500 Hz
        - has_vocal_clarity: Energía balanceada en 1-4 kHz
        - has_air: Presencia en > 10 kHz
        - is_bright: Centro espectral > 2 kHz
        - is_warm: Centro espectral < 1 kHz
        - needs_deess: Picos excesivos en 5-8 kHz
    """
    peaks = spectrum_data["peaks"]
    centroid = spectrum_data["spectral_centroid"]
    rolloff = spectrum_data["spectral_rolloff"]
    flatness = spectrum_data["spectral_flatness"]
    
    # Analizar distribución de picos por bandas
    sub_bass_peaks = [p for p in peaks if 20 <= p[0] <= 60]
    bass_peaks = [p for p in peaks if 60 <= p[0] <= 250]
    low_mid_peaks = [p for p in peaks if 250 <= p[0] <= 500]
    mid_peaks = [p for p in peaks if 500 <= p[0] <= 2000]
    high_mid_peaks = [p for p in peaks if 2000 <= p[0] <= 6000]
    air_peaks = [p for p in peaks if 6000 <= p[0] <= 16000]
    ultra_high_peaks = [p for p in peaks if p[0] > 10000]
    
    # Detectar características
    has_sub_bass = len(sub_bass_peaks) > 0
    has_bass_punch = len(bass_peaks) > 0 and any(p[1] > -15 for p in bass_peaks)
    has_muddy_mids = len(low_mid_peaks) > 1  # Múltiples picos = muddy
    has_vocal_clarity = len(mid_peaks) > 0 and len(high_mid_peaks) > 0
    has_air = len(ultra_high_peaks) > 0
    is_bright = centroid > 2000
    is_warm = centroid < 1000
    needs_deess = any(5000 <= p[0] <= 8000 and p[1] > -10 for p in peaks)
    
    return {
        "has_sub_bass": has_sub_bass,
        "has_bass_punch": has_bass_punch,
        "has_muddy_mids": has_muddy_mids,
        "has_vocal_clarity": has_vocal_clarity,
        "has_air": has_air,
        "is_bright": is_bright,
        "is_warm": is_warm,
        "needs_deess": needs_deess,
        "spectral_centroid": centroid,
        "spectral_rolloff": rolloff,
        "spectral_flatness": flatness,
        "peak_count_by_band": {
            "Sub Bass (20-60 Hz)": len(sub_bass_peaks),
            "Bass (60-250 Hz)": len(bass_peaks),
            "Low-Mid (250-500 Hz)": len(low_mid_peaks),
            "Mid (500-2k Hz)": len(mid_peaks),
            "High-Mid (2-6k Hz)": len(high_mid_peaks),
            "Air (6-16k Hz)": len(air_peaks),
        }
    }


def generate_spectrum_plot_data(
    spectrum_data: Dict,
    freq_range: Tuple[float, float] = (20, 20000)
) -> Tuple[List[float], List[float]]:
    """
    Prepara datos para graficar el espectro.
    
    Args:
        spectrum_data: Datos del analyze_spectrum_fft
        freq_range: Rango de frecuencias a mostrar (Hz)
        
    Returns:
        (frequencies, magnitudes) filtradas por rango
    """
    frequencies = np.array(spectrum_data["frequencies"])
    magnitudes = np.array(spectrum_data["magnitudes"])
    
    # Filtrar por rango
    mask = (frequencies >= freq_range[0]) & (frequencies <= freq_range[1])
    filtered_freqs = frequencies[mask]
    filtered_mags = magnitudes[mask]
    
    return filtered_freqs.tolist(), filtered_mags.tolist()


def recommend_preset_from_spectrum(characteristics: Dict) -> str:
    """
    Recomienda un preset basado en características del espectro.
    
    Args:
        characteristics: Resultado de get_spectrum_characteristics
        
    Returns:
        Nombre del preset recomendado
    """
    # Lógica de recomendación basada en espectro
    if characteristics["has_bass_punch"] and characteristics["has_air"]:
        if characteristics["needs_deess"]:
            return "Fuego (Trap, Reguetón, Hip-Hop)"
        else:
            return "Empuje (EDM, Dubstep, Bass Music)"
    
    elif characteristics["has_vocal_clarity"]:
        if characteristics["is_bright"]:
            return "Claridad (Clásica, R&B, Cantautor)"
        elif characteristics["is_warm"]:
            return "Cinta (Jazz, Alternativa, Indie)"
        else:
            return "Universal (Rock, Pop, Electrónica)"
    
    elif characteristics["has_air"] and characteristics["spectral_flatness"] > 0.3:
        return "Espacial (Ambient, Experimental)"
    
    elif characteristics["is_warm"] and not characteristics["has_bass_punch"]:
        return "Natural (Acústico, Jazz, Folk)"
    
    elif characteristics["has_muddy_mids"]:
        return "Cinemático (Orquestal, Soundtrack)"
    
    else:
        return "Universal (Rock, Pop, Electrónica)"
