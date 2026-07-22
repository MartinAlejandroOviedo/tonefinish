"""
Sistema inteligente de Auto-Master que adapta presets según análisis de audio.

Este módulo analiza las características del audio y ajusta automáticamente
los parámetros de los presets para obtener resultados óptimos.
"""

import pathlib
from typing import Any, Dict, Tuple, List, Optional, Callable

from compute_backend import ComputeBackend
from audio_tools import get_audio_mono_samples
from audio_analysis import (
    analyze_eq_bands,
    analyze_eq_and_voice,
    analyze_voice_band,
    detect_clipping,
    detect_noise_floor,
    detect_stereo_characteristics,
    analyze_silence_edges,
)
from config import BAND_CONFIG, BAND_HEADROOM_DB, MAX_SATURATION_DRIVE_DB, MULTIBAND_LIMITER_DEFAULTS

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except Exception:
    np = None  # type: ignore
    NUMPY_AVAILABLE = False

# Importar análisis de diagnóstico (métricas precisas de LUFS/LRA/True Peak)
try:
    from diagnostics import analyze_audio_metrics, AudioMetrics as DiagnosticMetrics
    DIAGNOSTICS_AVAILABLE = True
except ImportError:
    DIAGNOSTICS_AVAILABLE = False
    analyze_audio_metrics = None  # type: ignore
    DiagnosticMetrics = None  # type: ignore

# Importar análisis de espectro si está disponible
try:
    from spectrum_analyzer import (
        analyze_spectrum_fft,
        get_spectrum_characteristics,
        recommend_preset_from_spectrum
    )
    SPECTRUM_AVAILABLE = True
except ImportError:
    SPECTRUM_AVAILABLE = False
    analyze_spectrum_fft = None  # type: ignore
    get_spectrum_characteristics = None  # type: ignore
    recommend_preset_from_spectrum = None  # type: ignore


class AudioCharacteristics:
    """Características detectadas del audio."""
    
    def __init__(
        self,
        band_stats: Dict[str, float],
        voice_rms: float | None = None,
        clipping_info: dict | None = None,
        noise_info: dict | None = None,
        stereo_info: dict | None = None,
        band_peaks: dict | None = None,
        silence_info: dict | None = None,
        loudness_metrics: dict | None = None,  # Métricas LUFS/LRA/True Peak del diagnóstico
        tempo_info: dict | None = None,  # BPM / pulso estimado
    ):
        self.band_stats = band_stats
        self.voice_rms = voice_rms
        self.clipping_info = clipping_info or {}
        self.noise_info = noise_info or {}
        self.stereo_info = stereo_info or {}
        self.band_peaks = band_peaks or {}
        self.silence_info = silence_info or {}
        self.loudness_metrics = loudness_metrics or {}
        self.tempo_info = tempo_info or {}
        
        # Características derivadas
        self.has_vocals = self._detect_vocals()
        self.has_strong_bass = self._detect_strong_bass()
        self.has_strong_highs = self._detect_strong_highs()
        self.is_dynamic = self._detect_dynamic_range()
        self.needs_deess = self._detect_sibilance_risk()
        self.balance_score = self._calculate_balance()
        
        # Nuevas características
        self.has_clipping = self.clipping_info.get('detected', False)
        self.max_peak_db = self.clipping_info.get('max_peak_db', -100.0)
        self.noise_floor_db = self.noise_info.get('floor_db', -60.0)
        self.noise_category = self.noise_info.get('category', 'Unknown')
        self.is_mono = self.stereo_info.get('is_mono', False)
        self.stereo_width = self.stereo_info.get('stereo_width', 0.5)
        self.stereo_category = self.stereo_info.get('stereo_category', 'Normal')
        self.suggested_fade_in = self.silence_info.get('suggested_fade_in', 0.0)
        self.suggested_fade_out = self.silence_info.get('suggested_fade_out', 0.0)
        
        # === MÉTRICAS PRECISAS DE LOUDNESS (del diagnóstico) ===
        self.lufs: float = self.loudness_metrics.get('lufs', -70.0)
        self.true_peak: float = self.loudness_metrics.get('true_peak', -70.0)
        self.lra: float = self.loudness_metrics.get('lra', 0.0)  # Loudness Range
        self.rms_total: float = self.loudness_metrics.get('rms_total', -70.0)
        self.peak_total: float = self.loudness_metrics.get('peak_total', -70.0)
        self.crest_factor: float = self.loudness_metrics.get('crest_factor', 0.0)
        self.dc_offset: float = self.loudness_metrics.get('dc_offset', 0.0)
        self.tempo_bpm: float | None = self.tempo_info.get('bpm')
        self.tempo_confidence: float = self.tempo_info.get('confidence', 0.0)
        self.pulse_clarity: float = self.tempo_info.get('pulse_clarity', 0.0)
        self.tempo_source: str = self.tempo_info.get('source', 'none')
        
    def _detect_vocals(self) -> bool:
        """Detecta si hay vocales prominentes."""
        if self.voice_rms is None:
            return False
        mid_rms = float(self.band_stats.get("Mid (500-2k Hz)", -100.0))
        # Criterio híbrido:
        # - absoluto: voz claramente presente
        # - relativo: voz no tan alta, pero alineada con energía de medios
        return bool(
            self.voice_rms > -22.0
            or (self.voice_rms > -25.0 and self.voice_rms > (mid_rms - 2.0))
        )
    
    def _detect_strong_bass(self) -> bool:
        """Detecta si hay bajos fuertes."""
        bass_labels = ["Subbass (20-60 Hz)", "Bass (60-250 Hz)"]
        bass_levels = [self.band_stats.get(label, -100.0) for label in bass_labels]
        avg_bass = sum(bass_levels) / len(bass_levels) if bass_levels else -100.0
        return avg_bass > -15.0
    
    def _detect_strong_highs(self) -> bool:
        """Detecta si hay agudos fuertes (hi-hats, platillos)."""
        high_labels = ["High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"]
        high_levels = [self.band_stats.get(label, -100.0) for label in high_labels]
        avg_highs = sum(high_levels) / len(high_levels) if high_levels else -100.0
        return avg_highs > -18.0
    
    def _detect_dynamic_range(self) -> bool:
        """Detecta si el audio tiene buen rango dinámico."""
        if not self.band_stats:
            return False
        levels = list(self.band_stats.values())
        max_level = max(levels)
        min_level = min(levels)
        dynamic_range = max_level - min_level
        # Si hay más de 10 dB de diferencia entre bandas, es dinámico
        return dynamic_range > 10.0
    
    def _detect_sibilance_risk(self) -> bool:
        """Detecta riesgo de sibilancia excesiva."""
        high_mid = self.band_stats.get("High-Mid (2k-6k Hz)", -100.0)
        air = self.band_stats.get("Air (6k-16k Hz)", -100.0)
        # Si High-Mid o Air están muy altos, hay riesgo de sibilancia
        return high_mid > -10.0 or air > -12.0
    
    def _calculate_balance(self) -> float:
        """Calcula score de balance (0-100, 100 es perfectamente balanceado)."""
        if not self.band_stats:
            return 50.0
        levels = list(self.band_stats.values())
        avg = sum(levels) / len(levels)
        variance = sum((level - avg) ** 2 for level in levels) / len(levels)
        std_dev = variance ** 0.5
        # Normalizar: menos desviación = mejor balance
        # std_dev de 0 = 100, std_dev de 10+ = 0
        balance = max(0.0, min(100.0, 100.0 - (std_dev * 10.0)))
        return balance


def _build_band_suggestions_from_stats(
    band_stats: Dict[str, float],
    band_range_db: float,
    band_peaks: Dict[str, float] | None = None,
) -> list[str]:
    """Genera sugerencias de bandas a partir de RMS y picos ya medidos."""
    suggestions: list[str] = []
    if not band_stats:
        return suggestions

    avg = sum(band_stats.values()) / len(band_stats)
    for label, rms_level in band_stats.items():
        peak_db = band_peaks.get(label, -100.0) if band_peaks else -100.0
        if peak_db > -1.0 and label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"):
            suggestions.append(
                f"{label}: ADVERTENCIA - pico cercano a 0dB ({peak_db:.1f}dB), riesgo de saturación!"
            )
        elif rms_level > avg + band_range_db:
            suggestions.append(f"{label}: posible exceso; considera bajar ~2-3 dB.")
        elif rms_level < avg - band_range_db:
            if label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)") and peak_db > -3.0:
                continue
            suggestions.append(f"{label}: posible falta; considera subir ~2-3 dB.")

    return suggestions


def _band_level(characteristics: AudioCharacteristics, label: str, fallback: float = -100.0) -> float:
    return float(characteristics.band_stats.get(label, fallback))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _estimate_tempo_info(
    input_path: pathlib.Path,
    verbose: bool = False,
    sample_rate: int = 2000,
    max_seconds: int = 45,
) -> Dict[str, Any]:
    """
    Estima BPM y claridad de pulso de forma liviana (sin dependencias externas pesadas).
    Usa autocorrelación de envolvente de onsets sobre una ventana limitada.
    """
    if not NUMPY_AVAILABLE:
        return {"source": "none", "reason": "numpy_unavailable", "confidence": 0.0, "pulse_clarity": 0.0}

    samples = get_audio_mono_samples(str(input_path), sample_rate=sample_rate, max_seconds=max_seconds)
    if not samples:
        return {"source": "none", "reason": "no_samples", "confidence": 0.0, "pulse_clarity": 0.0}

    try:
        x = np.asarray(samples, dtype=np.float32)
        if x.size < sample_rate * 5:
            return {"source": "none", "reason": "too_short", "confidence": 0.0, "pulse_clarity": 0.0}

        # Pre-envolvente de energía
        x = x - float(np.mean(x))
        env = np.abs(x)
        win = max(4, int(sample_rate * 0.03))  # ~30ms
        kernel = np.ones(win, dtype=np.float32) / float(win)
        env = np.convolve(env, kernel, mode="same")

        # Downsample temporal para análisis de pulso
        frame_rate = 200.0
        hop = max(1, int(sample_rate / frame_rate))
        n = (env.size // hop) * hop
        if n < hop * 200:
            return {"source": "none", "reason": "insufficient_frames", "confidence": 0.0, "pulse_clarity": 0.0}
        env_ds = env[:n].reshape(-1, hop).mean(axis=1)
        env_ds = env_ds - float(np.mean(env_ds))

        # Onset envelope simple (variación positiva)
        diff = np.diff(env_ds, prepend=env_ds[0])
        onset = np.maximum(diff, 0.0)
        onset = onset / (float(np.max(onset)) + 1e-9)
        if float(np.max(onset)) < 1e-6:
            return {"source": "none", "reason": "flat_onset", "confidence": 0.0, "pulse_clarity": 0.0}

        # Autocorrelación en rango musical de BPM
        ac = np.correlate(onset, onset, mode="full")[onset.size - 1 :]
        ac[0] = 0.0
        bpm_min, bpm_max = 72.0, 180.0
        lag_min = int(frame_rate * 60.0 / bpm_max)
        lag_max = int(frame_rate * 60.0 / bpm_min)
        if lag_max <= lag_min + 2 or lag_max >= ac.size:
            return {"source": "none", "reason": "lag_range_invalid", "confidence": 0.0, "pulse_clarity": 0.0}

        lag_slice = ac[lag_min:lag_max]
        best_rel = int(np.argmax(lag_slice))
        best_lag = lag_min + best_rel
        bpm = float(60.0 * frame_rate / max(best_lag, 1))

        # Confianza: pico contra media del rango + regularidad
        lag_mean = float(np.mean(lag_slice) + 1e-9)
        lag_std = float(np.std(lag_slice) + 1e-9)
        best_peak = float(lag_slice[best_rel])
        peak_score = (best_peak - lag_mean) / lag_std
        confidence = _clamp((peak_score - 0.6) / 3.2, 0.0, 1.0)

        # Claridad de pulso: cuán concentrada está la energía de onsets por beat
        beat_frames = max(1, best_lag)
        first_window = onset[: min(onset.size, beat_frames * 8)]
        phase_idx = int(np.argmax(first_window)) if first_window.size else 0
        phase = float((phase_idx % beat_frames) / beat_frames)
        bins = max(8, beat_frames)
        fold_len = (first_window.size // bins) * bins
        if fold_len >= bins:
            folded = first_window[:fold_len].reshape(-1, bins).mean(axis=0)
            pulse_clarity = _clamp(float(np.max(folded) / (np.mean(folded) + 1e-9) - 1.0) / 2.5, 0.0, 1.0)
        else:
            pulse_clarity = confidence * 0.8

        return {
            "bpm": bpm,
            "confidence": confidence,
            "pulse_clarity": pulse_clarity,
            "phase": phase,
            "beat_frames": beat_frames,
            "source": "autocorr_onset",
        }
    except Exception as e:
        if verbose:
            print(f"⚠️ Estimación de tempo falló: {e}")
        return {"source": "none", "reason": "exception", "confidence": 0.0, "pulse_clarity": 0.0}


def _accumulate_eq_adjustment(
    adjustments: Dict[str, Any],
    label: str,
    delta_db: float,
    min_db: float = -3.0,
    max_db: float = 3.0,
) -> None:
    current = float(adjustments["eq_adjustments"].get(label, 0.0) or 0.0)
    updated = max(min_db, min(max_db, current + delta_db))
    adjustments["eq_adjustments"][label] = updated


def _diagnose_suno_mastering_issues(characteristics: AudioCharacteristics) -> Dict[str, Any]:
    high_mid = _band_level(characteristics, "High-Mid (2k-6k Hz)")
    air = _band_level(characteristics, "Air (6k-16k Hz)")
    mid = _band_level(characteristics, "Mid (500-2k Hz)")
    subbass = _band_level(characteristics, "Subbass (20-60 Hz)")
    bass = _band_level(characteristics, "Bass (60-250 Hz)")
    low_mid = _band_level(characteristics, "Low-Mid (250-500 Hz)")
    voice_rms = float(characteristics.voice_rms) if characteristics.voice_rms is not None else -100.0
    bass_peak = float(characteristics.band_peaks.get("Bass (60-250 Hz)", -100.0))

    hats_metallic = high_mid > -12.5 or air > -13.5
    highs_narrow = (not characteristics.is_mono) and characteristics.stereo_width < 0.32 and hats_metallic
    vocal_thin = characteristics.has_vocals and voice_rms < -18.5
    vocal_metallic = characteristics.has_vocals and (high_mid - mid) > 2.8
    vocal_forward = characteristics.has_vocals and (voice_rms - mid) > 2.2
    sub_weak = subbass < -22.0 or (subbass + 5.0 < bass)
    kick_edge = (
        bass > -10.8
        or ((bass_peak > -1.2) and (bass > -13.5))
        or ((bass - low_mid) > 6.8 and bass > -12.8)
    )

    return {
        "hats_metallic": hats_metallic,
        "highs_narrow": highs_narrow,
        "vocal_thin": vocal_thin,
        "vocal_metallic": vocal_metallic,
        "vocal_forward": vocal_forward,
        "sub_weak": sub_weak,
        "kick_edge": kick_edge,
        "metrics": {
            "high_mid_db": high_mid,
            "air_db": air,
            "mid_db": mid,
            "subbass_db": subbass,
            "bass_db": bass,
            "voice_rms_db": voice_rms,
            "stereo_width": float(characteristics.stereo_width),
            "bass_peak_db": bass_peak,
        },
    }


def classify_processing_profile(
    characteristics: AudioCharacteristics,
    minimal_lra_threshold: float = 4.5,
    minimal_crest_threshold: float = 8.5,
) -> Tuple[str, list[str]]:
    """
    Clasifica el material en Conservador / Normal / Agresivo.

    La decisión se basa en las métricas ya extraídas del análisis:
    LRA, crest factor, clipping, true peak y balance espectral.
    """
    reasons: list[str] = []

    if characteristics.has_clipping:
        reasons.append("clipping detectado")
    if characteristics.lra <= minimal_lra_threshold:
        reasons.append(f"LRA bajo ({characteristics.lra:.1f} LU)")
    if characteristics.crest_factor <= minimal_crest_threshold:
        reasons.append(f"crest bajo ({characteristics.crest_factor:.1f} dB)")
    if characteristics.true_peak >= -1.5:
        reasons.append(f"true peak cercano al límite ({characteristics.true_peak:.1f} dBTP)")
    if characteristics.noise_category in ("High", "VeryHigh"):
        reasons.append(f"ruido {characteristics.noise_category.lower()}")

    # Material con headroom moderado pero balance apenas justo:
    # si además tiene poca dinámica, preferimos no empujar la cadena.
    guarded_conservative = (
        characteristics.lufs <= -16.0
        and characteristics.true_peak <= -6.0
        and characteristics.lra <= 6.5
        and characteristics.balance_score < 70.0
    )
    if guarded_conservative:
        reasons.append(f"balance espectral justo ({characteristics.balance_score:.0f}/100)")
        reasons.append(f"headroom moderado con LRA contenido ({characteristics.lra:.1f} LU)")

    conservative = (
        characteristics.has_clipping
        or characteristics.lra <= minimal_lra_threshold
        or characteristics.crest_factor <= minimal_crest_threshold
        or characteristics.true_peak >= -1.5
        or guarded_conservative
    )
    if conservative:
        if not reasons:
            reasons.append("material sensible al procesamiento")
        return "Conservador", reasons

    aggressive = (
        characteristics.lra >= 8.5
        and characteristics.crest_factor >= 11.0
        and not characteristics.has_clipping
        and characteristics.true_peak <= -3.0
        and characteristics.balance_score >= 40.0
    )
    if aggressive:
        reasons.append(f"LRA amplio ({characteristics.lra:.1f} LU)")
        reasons.append(f"crest con headroom ({characteristics.crest_factor:.1f} dB)")
        return "Agresivo", reasons

    if characteristics.lra >= 6.0:
        reasons.append(f"LRA saludable ({characteristics.lra:.1f} LU)")
    else:
        reasons.append(f"LRA medio ({characteristics.lra:.1f} LU)")
    if characteristics.crest_factor >= 9.0:
        reasons.append(f"crest razonable ({characteristics.crest_factor:.1f} dB)")
    return "Normal", reasons


def analyze_audio_for_automaster(
    input_path: pathlib.Path,
    verbose: bool = False,
    use_spectrum: bool = True,
    full_analysis: bool = True,
) -> Tuple[AudioCharacteristics, List[str], Optional[Dict]]:
    """
    Analiza el audio y retorna características + recomendaciones.
    
    Args:
        input_path: Ruta al archivo de audio
        verbose: Mostrar comandos ffmpeg
        use_spectrum: Realizar análisis de espectro FFT (más preciso pero más lento)
        full_analysis: Realizar análisis completo (clipping, ruido, stereo, picos)
        
    Returns:
        (AudioCharacteristics, lista de recomendaciones, spectrum_data opcional)
    """
    backend = ComputeBackend()
    band_stats: Dict[str, float] = {}
    band_suggestions: list[str] = []
    band_peaks: dict[str, float] = {}
    voice_rms: float | None = None
    clipping_info: dict | None = None
    noise_info: dict | None = None
    stereo_info: dict | None = None
    silence_info: dict | None = None
    loudness_metrics: dict[str, float] = {}
    tempo_info: dict[str, Any] | None = None

    backend_decisions = backend.decide_many(
        [
            "analysis.loudness",
            "analysis.features",
            "analysis.spectrum",
            "analysis.validation",
            "render.mastering",
        ]
    )

    # === ANÁLISIS CORE: una sola ruta de diagnóstico para loudness + bandas ===
    if DIAGNOSTICS_AVAILABLE and analyze_audio_metrics is not None:
        try:
            diag_metrics = analyze_audio_metrics(input_path, verbose=verbose)
            band_stats = dict(diag_metrics.band_rms)
            band_peaks = dict(diag_metrics.band_peak)
            loudness_metrics = {
                'lufs': diag_metrics.lufs,
                'true_peak': diag_metrics.true_peak,
                'lra': diag_metrics.lra,
                'rms_total': diag_metrics.rms_total,
                'peak_total': diag_metrics.peak_total,
                'crest_factor': diag_metrics.crest_factor,
                'dc_offset': diag_metrics.dc_offset,
            }
            band_suggestions = _build_band_suggestions_from_stats(
                band_stats,
                band_range_db=3.0,
                band_peaks=band_peaks,
            )
            if verbose:
                print(
                    f"📊 Métricas de loudness: LUFS={diag_metrics.lufs:.1f}, "
                    f"TP={diag_metrics.true_peak:.1f} dBTP, LRA={diag_metrics.lra:.1f} LU"
                )
                print(
                    "🧠 Backend etapas: "
                    + " | ".join(decision.format_summary() for decision in backend_decisions)
                )
        except Exception as e:
            if verbose:
                print(f"⚠️ Análisis de diagnóstico falló: {e}")

    # Fallback si el diagnóstico no estuvo disponible o no devolvió bandas.
    if not band_stats:
        band_stats, band_suggestions, voice_rms = analyze_eq_and_voice(
            input_path=input_path,
            verbose=verbose,
            band_range_db=3.0,
        )
    else:
        # Si ya tenemos bandas desde diagnóstico, solo analizamos la banda vocal.
        voice_rms = analyze_voice_band(input_path=input_path, verbose=verbose)

    # Análisis de ruido y stereo: ligeros, pero útiles incluso en modo simple.
    noise_floor, noise_category = detect_noise_floor(input_path, verbose=verbose)
    noise_info = {
        'floor_db': noise_floor,
        'category': noise_category,
    }
    stereo_info = detect_stereo_characteristics(input_path, verbose=verbose)
    tempo_info = _estimate_tempo_info(input_path, verbose=verbose)

    # Clipping: en modo completo se mide directamente; en modo simple
    # se infiere a partir de los picos medidos por loudness.
    if full_analysis:
        has_clipping, max_peak, clip_count = detect_clipping(input_path, verbose=verbose)
        clipping_info = {
            'detected': has_clipping,
            'max_peak_db': max_peak,
            'clip_count': clip_count,
        }
        fade_in, fade_out, fade_detail = analyze_silence_edges(input_path)
        silence_info = {
            'suggested_fade_in': fade_in,
            'suggested_fade_out': fade_out,
            'detail': fade_detail,
        }
    else:
        inferred_peak = loudness_metrics.get('peak_total', loudness_metrics.get('true_peak', -70.0))
        clipping_info = {
            'detected': inferred_peak >= -0.1,
            'max_peak_db': inferred_peak,
            'clip_count': 0,
        }
    
    # Análisis de espectro (opcional, más detallado)
    spectrum_data = None
    spectrum_chars = None
    spectrum_decision = backend.decide("analysis.spectrum")
    if verbose and spectrum_decision.backend == "gpu":
        print(f"🧠 Etapa spectrum preparada para GPU: {spectrum_decision.reason}")
    if use_spectrum and SPECTRUM_AVAILABLE:
        try:
            if analyze_spectrum_fft is not None and get_spectrum_characteristics is not None:
                spectrum_data = analyze_spectrum_fft(
                    input_path,
                    duration=10.0,
                    verbose=verbose,
                    backend=spectrum_decision.backend,
                )
                spectrum_chars = get_spectrum_characteristics(spectrum_data)
        except Exception as e:
            if verbose:
                print(f"⚠️ Análisis de espectro falló: {e}")
    
    # Crear características con todos los análisis
    characteristics = AudioCharacteristics(
        band_stats=band_stats,
        voice_rms=voice_rms,
        clipping_info=clipping_info,
        noise_info=noise_info,
        stereo_info=stereo_info,
        band_peaks=band_peaks,
        silence_info=silence_info,
        loudness_metrics=loudness_metrics,
        tempo_info=tempo_info,
    )
    
    # Generar recomendaciones
    recommendations = []
    recommendations.append(
        "🧠 Backend: "
        + ", ".join(
            f"{decision.stage}={decision.backend}"
            + ("(fallback)" if decision.fallback_used else "")
            for decision in backend_decisions
        )
    )
    
    # === MÉTRICAS DE LOUDNESS ===
    if characteristics.lufs > -70.0:
        recommendations.append("📊 === MÉTRICAS DE LOUDNESS ===\n")
        recommendations.append(f"  LUFS: {characteristics.lufs:.1f} dB")
        recommendations.append(f"  True Peak: {characteristics.true_peak:.1f} dBTP")
        recommendations.append(f"  LRA (Rango Dinámico): {characteristics.lra:.1f} LU")
        recommendations.append(f"  RMS Total: {characteristics.rms_total:.1f} dB")
        recommendations.append(f"  Crest Factor: {characteristics.crest_factor:.1f} dB")
        
        # Recomendaciones basadas en LUFS
        if characteristics.lufs > -10.0:
            recommendations.append(f"  ⚠️ Audio MUY ALTO ({characteristics.lufs:.1f} LUFS) - Se aplicará atenuación")
        elif characteristics.lufs > -12.0:
            recommendations.append(f"  ⚠️ Audio alto ({characteristics.lufs:.1f} LUFS) - Limitación cuidadosa")
        elif characteristics.lufs < -20.0:
            recommendations.append(f"  ⚠️ Audio bajo ({characteristics.lufs:.1f} LUFS) - Se aplicará ganancia")
        else:
            recommendations.append(f"  ✓ Nivel de entrada adecuado ({characteristics.lufs:.1f} LUFS)")
        
        # Recomendaciones basadas en LRA
        if characteristics.lra < 4.0:
            recommendations.append(f"  ⚠️ Rango dinámico bajo ({characteristics.lra:.1f} LU) - Audio muy comprimido")
        elif characteristics.lra > 12.0:
            recommendations.append(f"  ⚠️ Rango dinámico alto ({characteristics.lra:.1f} LU) - Puede necesitar compresión")
        else:
            recommendations.append(f"  ✓ Rango dinámico saludable ({characteristics.lra:.1f} LU)")
        
        # Recomendaciones basadas en True Peak
        if characteristics.true_peak > -1.0:
            recommendations.append(f"  ⚠️ True Peak muy alto ({characteristics.true_peak:.1f} dBTP) - Riesgo de clipping")
        elif characteristics.true_peak > -3.0:
            recommendations.append(f"  ⚠️ True Peak alto ({characteristics.true_peak:.1f} dBTP)")
        
        recommendations.append("")
    
    # === NUEVOS ANÁLISIS ===
    if full_analysis:
        recommendations.append("📊 === ANÁLISIS COMPLETO ===\n")
        
        # Clipping
        if characteristics.has_clipping:
            recommendations.append(
                f"🔴 CLIPPING DETECTADO: Pico máximo {characteristics.max_peak_db:.1f} dB\n"
                f"   → Se activará Declip automáticamente"
            )
        else:
            recommendations.append(
                f"✓ Sin clipping (pico máximo: {characteristics.max_peak_db:.1f} dB)"
            )
        
        # Ruido
        if characteristics.noise_category in ("High", "VeryHigh"):
            recommendations.append(
                f"🔴 RUIDO ALTO: Piso de ruido {characteristics.noise_floor_db:.0f} dB ({characteristics.noise_category})\n"
                f"   → Se activará reducción de ruido"
            )
        elif characteristics.noise_category == "Moderate":
            recommendations.append(
                f"⚠️ Ruido moderado: {characteristics.noise_floor_db:.0f} dB\n"
                f"   → Reducción de ruido leve recomendada"
            )
        else:
            recommendations.append(
                f"✓ Ruido bajo: {characteristics.noise_floor_db:.0f} dB ({characteristics.noise_category})"
            )
        
        # Stereo
        if characteristics.is_mono:
            recommendations.append(
                f"ℹ️ Audio MONO detectado\n"
                f"   → Se desactivará Stereo Width (no aplicable)"
            )
        else:
            recommendations.append(
                f"✓ Audio Stereo: {characteristics.stereo_category} (ancho: {characteristics.stereo_width*100:.0f}%)"
            )
            if characteristics.stereo_category == "Narrow":
                recommendations.append(
                    f"   → Se activará Stereo Width para ampliar imagen"
                )
        
        # Fades sugeridos
        if characteristics.suggested_fade_in > 0 or characteristics.suggested_fade_out > 0:
            recommendations.append(
                f"✓ Fades sugeridos: In={characteristics.suggested_fade_in:.2f}s, Out={characteristics.suggested_fade_out:.2f}s"
            )
        
        # Picos por banda (para limitador multibanda)
        if band_peaks:
            hot_bands = [label for label, peak in band_peaks.items() if peak > -3.0]
            if hot_bands:
                recommendations.append(
                    f"⚠️ Bandas con picos altos (> -3dB): {', '.join(hot_bands)}\n"
                    f"   → Se configurará Limitador Multibanda"
                )
        
        recommendations.append("")
    
    # === ANÁLISIS EXISTENTES ===
    if characteristics.has_vocals:
        recommendations.append(
            f"✓ Vocales detectadas (RMS: {voice_rms:.1f} dB) - "
            f"Se activará de-esser y protección de High-Mid"
        )
    else:
        recommendations.append(
            "○ Sin vocales prominentes - De-esser suave o desactivado"
        )
    
    # Agregar información del espectro si está disponible
    if spectrum_chars:
        recommendations.append(f"\n📊 Análisis de Espectro:")
        recommendations.append(
            f"   Centro espectral: {spectrum_chars['spectral_centroid']:.0f} Hz"
        )
        if spectrum_chars['is_bright']:
            recommendations.append("   ✓ Audio brillante - buenos agudos")
        elif spectrum_chars['is_warm']:
            recommendations.append("   ✓ Audio cálido - predominan graves/medios")
        
        if spectrum_chars['has_bass_punch']:
            recommendations.append("   ✓ Punch en bajos detectado")
        if spectrum_chars['has_air']:
            recommendations.append("   ✓ Aire/brillo en frecuencias altas")
        if spectrum_chars['needs_deess']:
            recommendations.append("   ⚠️ Sibilancia detectada - de-esser recomendado")
        if spectrum_chars['has_muddy_mids']:
            recommendations.append("   ⚠️ Medios-bajos turbios - considerar corte en 250-500 Hz")
        
        # Sugerencia de preset basada en espectro
        if recommend_preset_from_spectrum is not None:
            recommended_preset = recommend_preset_from_spectrum(spectrum_chars)
            recommendations.append(f"\n💡 Preset sugerido por espectro: {recommended_preset}")
    
    if characteristics.has_strong_bass:
        bass_rms = band_stats.get("Bass (60-250 Hz)", -100.0)
        recommendations.append(
            f"✓ Bajos fuertes detectados (RMS: {bass_rms:.1f} dB) - "
            f"Se aplicará control en graves"
        )

    if characteristics.tempo_bpm:
        recommendations.append(
            f"🥁 Tempo estimado: {characteristics.tempo_bpm:.1f} BPM "
            f"(conf: {characteristics.tempo_confidence:.2f}, pulso: {characteristics.pulse_clarity:.2f})"
        )
    
    if characteristics.has_strong_highs:
        air_rms = band_stats.get("Air (6k-16k Hz)", -100.0)
        recommendations.append(
            f"✓ Agudos fuertes detectados (RMS: {air_rms:.1f} dB) - "
            f"Se limitará saturación en Air"
        )
    
    if characteristics.is_dynamic:
        recommendations.append(
            "✓ Buen rango dinámico - Se usará compresión suave"
        )
    else:
        recommendations.append(
            "○ Rango dinámico limitado - Se aplicará menos compresión"
        )
    
    if characteristics.needs_deess:
        recommendations.append(
            "⚠ Riesgo de sibilancia - De-esser intenso recomendado"
        )
    
    recommendations.append(
        f"Balance espectral: {characteristics.balance_score:.0f}/100"
    )
    
    # Añadir sugerencias del análisis de bandas
    if band_suggestions:
        recommendations.append("\nSugerencias de bandas:")
        recommendations.extend([f"  • {s}" for s in band_suggestions])
    
    return characteristics, recommendations, spectrum_data



# === PERFIL IDEAL DE MASTERING 2026 ===
# Todos los thresholds de decisión referencian este diccionario.
# Cambiar un valor aquí afecta TODAS las decisiones.

def _calculate_eq_correction(current_db: float, ideal_db: float, 
                              max_cut: float = -3.0, max_boost: float = 2.0,
                              ratio: float = 0.5) -> float:
    """Calcula la corrección de EQ necesaria para cerrar el gap con el ideal.
    
    ratio=0.5 significa que corregimos el 50% del gap (conservador).
    ratio=1.0 sería corrección total (agresivo).
    """
    gap = current_db - ideal_db  # positivo = muy fuerte, negativo = muy débil
    if abs(gap) < 0.5:  # gap insignificante, no tocar
        return 0.0
    correction = -gap * ratio  # negativo si muy fuerte, positivo si débil
    correction = max(max_cut, min(max_boost, correction))
    return round(correction, 1)

MASTERING_IDEAL = {
    "target_lufs": -14.0,        # LUFS integrado (streaming standard)
    "target_tp": -1.5,           # True Peak máximo (dBTP)
    "min_lra_healthy": 5.0,      # LRA mínimo para considerar "saludable" (LU)
    "max_lra_compressed": 4.5,   # LRA bajo → audio ya comprimido → modo conservador
    "min_crest_healthy": 8.5,    # Crest factor mínimo (dB)
    "max_crest_compressed": 8.5, # Crest bajo → audio denso → modo conservador
    "max_tp_near_ceiling": -1.5, # TP cerca del techo → ya está fuerte
    "min_balance_ok": 50.0,      # Balance score mínimo aceptable
    "max_balance_good": 80.0,    # Balance score para considerar "bueno"
    "high_mid_hot_threshold": -12.5,  # High-Mid RMS para detectar hats metálicos
    "air_hot_threshold": -13.5,       # Air RMS para detectar agudos calientes
    "noise_floor_ok": -50.0,     # Piso de ruido aceptable (dB)
    "headroom_gap_far": 15.0,    # Gap LUFS para headroom reducido
    "headroom_gap_mid": 8.0,     # Gap LUFS para headroom medio
    "autogain_gap_far": 12.0,    # Gap LUFS para autogain fuerte
    "autogain_gap_mid": 5.0,     # Gap LUFS para autogain medio
    "sub_weak_threshold": -22.0, # Sub-bass RMS para detectar falta de graves
    "voice_thin_threshold": -18.5, # Voice RMS para detectar voces finas
    "eq_cut_air_default": -0.8,  # Corte default en Air para hats metálicos
    "eq_cut_high_mid_default": -0.6, # Corte default en High-Mid
    "max_eq_boost": 2.0,         # Máximo boost de EQ por banda
    "max_eq_cut": -3.0,          # Máximo corte de EQ por banda
    "saturation_lufs_hot": -10.0,   # LUFS para considerar "caliente" (reducir sat)
    "saturation_lufs_warm": -12.0,  # LUFS para considerar "tibio"
    "saturation_lufs_cold": -20.0,  # LUFS para considerar "frío" (aumentar sat)
    # Niveles ideales por banda (RMS dB) para un master balanceado 2026
    "band_ideal_rms": {
        "Subbass (20-60 Hz)": -18.0,
        "Bass (60-250 Hz)": -14.0,
        "Low-Mid (250-500 Hz)": -16.0,
        "Mid (500-2k Hz)": -15.0,
        "High-Mid (2k-6k Hz)": -16.0,
        "Air (6k-16k Hz)": -18.0,
    },
    # Niveles ideales de peak por banda (dB)
    "band_ideal_peak": {
        "Subbass (20-60 Hz)": -3.0,
        "Bass (60-250 Hz)": -2.0,
        "Low-Mid (250-500 Hz)": -2.5,
        "Mid (500-2k Hz)": -2.5,
        "High-Mid (2k-6k Hz)": -3.0,
        "Air (6k-16k Hz)": -4.0,
    },
}

DEFAULT_AI_FALLBACK_PRESET = "SUNO Clásico"

def adapt_preset_to_audio(
    preset_name: str,
    characteristics: AudioCharacteristics,
    minimal_lra_threshold: float = 4.5,
    minimal_crest_threshold: float = 8.5,
    motion_profile_preference: str = "auto",
    motion_amount: float = 1.0,
    block_mode: bool = False,
    ia_providers: list | None = None,
    target_lufs: float = -15.5,
    true_peak: float = -1.5,
    audio_id: str = "unknown",
) -> Dict[str, Any]:
    """
    Adapta un preset según las características del audio.
    Si hay IA disponible, la IA decide todo. Si no, usa gap-based engine.

    Args:
        preset_name: Nombre del preset base
        characteristics: Características analizadas del audio
        ia_providers: Lista de dicts con url/key/model para IA (opcional)
    """

    ia_fallback_note = ""
    band_stats = dict(characteristics.band_stats) if hasattr(characteristics, 'band_stats') else {}
    band_peaks = dict(characteristics.band_peaks) if hasattr(characteristics, 'band_peaks') else {}
    pre_stats = {"input_i": characteristics.lufs, "input_tp": characteristics.true_peak,
                 "input_lra": characteristics.lra, "crest_factor": characteristics.crest_factor,
                 "input_thresh": getattr(characteristics, 'noise_floor_db', -44)}

    # === INTENTAR IA PRIMERO (v4.1.0) ===
    if ia_providers:
        try:
            from ia_mastering import get_mastering_strategy, load_past_strategies
            # Cargar estrategias pasadas exitosas para que la IA aprenda
            past = load_past_strategies()
            strategy = get_mastering_strategy(
                band_stats, band_peaks, pre_stats, preset_name,
                target_lufs=target_lufs,
                true_peak=true_peak,
                providers=ia_providers,
                voice_rms=getattr(characteristics, 'voice_rms', None),
                stereo_width=getattr(characteristics, 'stereo_width', 0.5),
                stereo_category=getattr(characteristics, 'stereo_category', 'Normal'),
                has_clipping=getattr(characteristics, 'has_clipping', False),
                noise_floor_db=getattr(characteristics, 'noise_floor_db', -60),
                past_examples=past,
                audio_id=audio_id,
            )
            if strategy and isinstance(strategy, dict):
                # Convertir respuesta IA al formato de adjustments
                adjustments = _build_adjustments_from_ia(strategy, characteristics)
                adjustments["strategy_source"] = "ai"
                adjustments["notes"].insert(0, "🧠 Estrategia de mastering generada por IA")
                return adjustments
            ia_fallback_note = "IA agotó tokens o devolvió una respuesta inválida; se usa SUNO Clásico."
        except Exception as exc:
            ia_fallback_note = f"IA rechazada: {exc}; se usa SUNO Clásico."
    else:
        ia_fallback_note = "IA sin tokens o credenciales; se usa SUNO Clásico."

    from ia_mastering import build_suno_classic_strategy
    fallback_strategy = build_suno_classic_strategy(
        audio_id=audio_id, target_lufs=target_lufs, true_peak=true_peak,
        pre_stats=pre_stats, band_stats=band_stats,
        voice_rms=getattr(characteristics, "voice_rms", None),
        fallback_reason=ia_fallback_note,
    )
    adjustments = _build_adjustments_from_ia(fallback_strategy, characteristics)
    adjustments.update({
        "strategy_source": "fallback_suno_classic",
        "fallback_preset": DEFAULT_AI_FALLBACK_PRESET,
        "fallback_reason": ia_fallback_note,
        "processing_profile": DEFAULT_AI_FALLBACK_PRESET,
    })
    adjustments["notes"].insert(0, f"🛟 {ia_fallback_note}")
    return adjustments

    # Único fallback permitido: nunca conservar un ajuste manual ni otro estilo.
    preset_name = DEFAULT_AI_FALLBACK_PRESET
    adjustments = {
        "notes": [],
        "warnings": [],
        "suggestions": [],
        "alternative_presets": [],
        "diagnostics": {},
        "eq_adjustments": {},
        "deesser_intensity_mult": 1.0,
        "saturation_drive_mult": 1.0,
        "saturation_mix_mult": 1.0,
        "glue_threshold_offset": 0.0,
        "glue_ratio_mult": 1.0,
        "band_saturation_adjustments": {},
        "dynamic_eq_enabled": True,
        "stereo_width_enabled": True,
        "glue_enabled": True,
        "deesser_enabled": True,
        "autogain_enabled": True,
        "headroom_db": -17.0,
        "saturation_enabled": True,
        "minimal_processing": False,
        "processing_profile": "Normal",
        "processing_profile_reasons": [],
        "strategy_source": "fallback_suno_classic",
        "fallback_preset": DEFAULT_AI_FALLBACK_PRESET,
        # === KNEE DEL GLUE COMPRESSOR (0=hard, 6=soft, 10=muy soft) ===
        "glue_knee_db": 6.0,
        # === NUEVAS CONFIGURACIONES AUTO ===
        "repair_settings": {
            "noise_reduction": "Off",
            "declip": "Off",
            "declick": "Off",
        },
        "multiband_limiter_enabled": False,
        "multiband_limiter_thresholds": {},
        # === STEREO DYNAMIC (AHORA EN MULTIBAND) ===
        "stereo_dynamic_enabled": False,
        "stereo_dynamic_threshold_db": -24.0,
        "stereo_dynamic_ratio": 1.6,
        "stereo_dynamic_attack_ms": 20.0,
        "stereo_dynamic_release_ms": 150.0,
        "stereo_dynamic_mix": 0.5,
        "stereo_dynamic_band_mix": {},  # Mix específico por banda
        # === STEREO POR BANDA (v2.0.0: reemplaza stereo global) ===
        "band_widths": {},  # Dict[label, float] ancho stereo por banda calculado por gap
        # === COMPRESIÓN POR BANDA (v2.0.0) ===
        "band_compression": {},  # Dict[label, Dict] compresión por banda
        # === REPARACIÓN POR BANDA (v2.0.0) ===
        "band_repair": {},  # Dict[label, Dict] denoise/declip/declick por banda
        # === ENABLES POR CAPA (v2.0.0: control dinámico de cada capa) ===
        "band_eq_enabled": True,          # EQ por banda
        "band_stereo_enabled": True,      # Stereo width por banda
        "band_compression_enabled": True, # Compresión por banda
        "band_limiter_enabled": False,    # Limitador por banda (se activa si peaks altos)
        "band_repair_enabled": False,     # Reparación por banda (se activa si necesita)
        "suggested_fade_in": 0.0,
        "suggested_fade_out": 0.0,
        # === BLOCK MODE (v3.0.0: procesamiento por bloques/secciones) ===
        "block_mode": block_mode,
        "section_adjustments": {},  # Dict[section_label, Dict] ajustes por sección
        # === CONTROL DE SATURACIÓN POST-PROCESO ===
        # === FASE 5: CONTROL DE USUARIO ===
        "motion_profile": "balanced",
        "motion_profile_selected": "auto",
        "motion_amount": 1.0,
    }
    motion_amount = _clamp(float(motion_amount), 0.0, 1.5)
    if ia_fallback_note:
        adjustments["notes"].append(f"⚠ {ia_fallback_note}")
    selected_profile = str(motion_profile_preference or "auto").strip().lower()
    if selected_profile not in {"auto", "tight", "balanced", "airy"}:
        selected_profile = "auto"
    adjustments["motion_profile_selected"] = selected_profile
    adjustments["motion_amount"] = motion_amount

    # === FASE 1: DIAGNÓSTICO ESPECÍFICO PARA MASTERS DE SUNO ===
    suno_diag = _diagnose_suno_mastering_issues(characteristics)
    adjustments["diagnostics"] = suno_diag
    active_flags = [k for k, v in suno_diag.items() if isinstance(v, bool) and v]
    if active_flags:
        adjustments["notes"].append(
            "📋 Diagnóstico Fase 1: " + ", ".join(active_flags)
        )
    
    # === AUTO-CONFIGURAR REPARACIÓN ===
    # Clipping detectado -> Declip (umbral más agresivo para SUNO)
    if characteristics.has_clipping:
        if characteristics.max_peak_db >= -0.1:
            adjustments["repair_settings"]["declip"] = "High"
            adjustments["notes"].append(
                f"🔧 Declip HIGH activado (clipping: {characteristics.max_peak_db:.1f}dB)"
            )
        else:
            adjustments["repair_settings"]["declip"] = "Medium"
            adjustments["notes"].append(
                f"🔧 Declip MEDIUM activado (clipping leve: {characteristics.max_peak_db:.1f}dB)"
            )
    
    # SUNO: agregar declick suave por defecto (artefactos de AI)
    suno_diag = adjustments.get("diagnostics", {})
    if suno_diag.get("hats_metallic") or characteristics.has_clipping:
        if adjustments["repair_settings"]["declick"] == "Off":
            adjustments["repair_settings"]["declick"] = "Low"
            adjustments["notes"].append(
                "🔧 Declick LOW activado (artefactos AI/SUNO detectados)"
            )
    
    # Ruido detectado -> Noise Reduction
    if characteristics.noise_category == "VeryHigh":
        adjustments["repair_settings"]["noise_reduction"] = "High"
        adjustments["notes"].append(
            f"🔧 Reducción de ruido HIGH activada (piso: {characteristics.noise_floor_db:.0f}dB)"
        )
    elif characteristics.noise_category == "High":
        adjustments["repair_settings"]["noise_reduction"] = "Medium"
        adjustments["notes"].append(
            f"🔧 Reducción de ruido MEDIUM activada (piso: {characteristics.noise_floor_db:.0f}dB)"
        )
    elif characteristics.noise_category == "Moderate":
        adjustments["repair_settings"]["noise_reduction"] = "Low"
        adjustments["notes"].append(
            f"🔧 Reducción de ruido LOW activada (piso: {characteristics.noise_floor_db:.0f}dB)"
        )
    
    # === AUTO-CONFIGURAR DE-ESSER ===
    # De-esser: solo si los agudos están POR ENCIMA del ideal
    air_current = _band_level(characteristics, "Air (6k-16k Hz)")
    hm_current = _band_level(characteristics, "High-Mid (2k-6k Hz)")
    air_ideal = MASTERING_IDEAL["band_ideal_rms"]["Air (6k-16k Hz)"]
    hm_ideal = MASTERING_IDEAL["band_ideal_rms"]["High-Mid (2k-6k Hz)"]
    air_gap = air_current - air_ideal
    hm_gap = hm_current - hm_ideal
    
    if air_gap > 3.0 or hm_gap > 3.0:
        # Agudos muy por encima del ideal → de-esser fuerte
        adjustments["deesser_enabled"] = True
        adjustments["deesser_intensity_mult"] = min(1.5, 0.8 + air_gap * 0.1)
        adjustments["notes"].append(
            f"🔧 De-esser AUTO (Air +{air_gap:.0f}dB sobre ideal)"
        )
    elif characteristics.has_vocals and (air_gap > 1.0 or hm_gap > 1.0):
        adjustments["deesser_enabled"] = True
        adjustments["deesser_intensity_mult"] = 0.7
    elif air_gap > 0.5 or hm_gap > 0.5:
        adjustments["deesser_enabled"] = True
        adjustments["deesser_intensity_mult"] = 0.5
    else:
        # Agudos ya en nivel ideal o por debajo → OFF
        adjustments["deesser_enabled"] = False
        adjustments["notes"].append(
            "🔧 De-esser OFF (agudos en nivel ideal)"
        )

    # === AUTO-BALANCE ESPECTRAL (GAP-BASED PARA TODAS LAS BANDAS) ===
    # Siempre evaluar el gap de cada banda vs el ideal, independientemente de SUNO flags.
    band_corrections_applied = 0
    for band_name, ideal_rms in MASTERING_IDEAL["band_ideal_rms"].items():
        current = _band_level(characteristics, band_name)
        if current <= -80.0:  # sin datos, saltar
            continue
        correction = _calculate_eq_correction(current, ideal_rms,
                                               max_cut=-3.0, max_boost=3.0, ratio=0.4)
        if abs(correction) >= 0.2:
            _accumulate_eq_adjustment(adjustments, band_name, correction)
            band_corrections_applied += 1
    adjustments["band_eq_enabled"] = band_corrections_applied > 0
    if band_corrections_applied > 0:
        adjustments["notes"].append(
            "🎚️ Balance espectral gap-based: %d bandas ajustadas vs ideal" % band_corrections_applied
        )
    else:
        adjustments["notes"].append("✓ Balance espectral en rango ideal")

    # === AUTO-CONFIGURAR STEREO POR BANDA (reemplaza stereo global) ===
    # Cada banda recibe su propio ancho stereo calculado por gap vs ideal.
    # Sub/bass tienden a mono (<1.0), medios/agudos a stereo (>1.0).
    band_widths: Dict[str, float] = {}
    for band_name, ideal_rms in MASTERING_IDEAL["band_ideal_rms"].items():
        current = _band_level(characteristics, band_name)
        if current <= -80.0:
            band_widths[band_name] = 1.0
            continue
        gap = current - ideal_rms
        # Bands below ideal → wider (more presence needed)
        # Bands above ideal → narrower (reduce harshness)
        # Base width depends on frequency: lows = narrow, highs = wide
        if "Subbass" in band_name:
            base_width = 0.3  # mono sub
        elif "Bass" in band_name:
            base_width = 0.6  # narrow bass
        elif "Low-Mid" in band_name or "Mid" in band_name:
            base_width = 0.9  # centered mids
        elif "High-Mid" in band_name:
            base_width = 1.1  # slightly wide presence
        else:  # Air
            base_width = 1.3  # wide air

        # Adjust by gap: below ideal → widen, above ideal → narrow
        stereo_correction = -gap * 0.05  # each dB of gap adjusts width by 5%
        width = base_width + stereo_correction
        width = max(0.15, min(2.5, width))  # clamp: minimum 15%, max 250%
        band_widths[band_name] = round(width, 2)

    adjustments["band_widths"] = band_widths
    # Activate stereo width in multiband (per-band), disable global stereo
    adjustments["stereo_width_enabled"] = False  # global off
    adjustments["stereo_dynamic_enabled"] = False  # dynamic off (per-band static replaces it)
    adjustments["notes"].append(
        "🎛️ Stereo por banda: Sub=%.1f Bass=%.1f Mid=%.1f HiMid=%.1f Air=%.1f" % (
            band_widths.get("Subbass (20-60 Hz)", 1.0),
            band_widths.get("Bass (60-250 Hz)", 1.0),
            band_widths.get("Mid (500-2k Hz)", 1.0),
            band_widths.get("High-Mid (2k-6k Hz)", 1.0),
            band_widths.get("Air (6k-16k Hz)", 1.0),
        )
    )
    
    # === VOCAL BAND: más apertura stereo en bandas vocales ===
    if characteristics.has_vocals and not characteristics.is_mono:
        # Aumentar ancho en bandas medias donde residen las vocales
        for vocal_band in ("Low-Mid (250-500 Hz)", "Mid (500-2k Hz)", "High-Mid (2k-6k Hz)"):
            if vocal_band in band_widths:
                band_widths[vocal_band] = round(min(2.0, band_widths[vocal_band] + 0.2), 2)
        adjustments["notes"].append(
            "🎤 Bandas vocales: +0.2 ancho stereo"
        )
    
    # === AUTO-CONFIGURAR COMPRESIÓN POR BANDA (gap-based) ===
    # Usa el crest por banda (peak - RMS) para decidir threshold y ratio
    band_compression: Dict[str, Dict[str, float]] = {}
    if characteristics.band_peaks:
        for band_name, peak in characteristics.band_peaks.items():
            rms = _band_level(characteristics, band_name)
            if rms <= -80.0 or peak <= -80.0:
                continue
            crest = peak - rms
            crest = max(2.0, crest)
            # Threshold = RMS + margen para solo atrapar picos
            threshold_db = rms + max(2.0, min(10.0, crest * 0.5))
            # Ratio según dinámica: más crest → más ratio
            if crest > 18:
                ratio = 3.0
            elif crest > 12:
                ratio = 2.0
            elif crest > 6:
                ratio = 1.5
            else:
                ratio = 1.2  # ya comprimido
            # Attack/release por frecuencia
            if "Air" in band_name or "High-Mid" in band_name:
                atk, rel = 2.0, 40.0
            elif "Subbass" in band_name or "Bass" in band_name:
                atk, rel = 12.0, 100.0
            else:
                atk, rel = 6.0, 60.0
            band_compression[band_name] = {
                "threshold_db": round(threshold_db, 1),
                "ratio": round(ratio, 1),
                "attack_ms": round(atk, 1),
                "release_ms": round(rel, 1),
                "knee_db": 4.0,
                "makeup_db": 0.0,
            }
    adjustments["band_compression"] = band_compression
    if band_compression:
        adjustments["band_compression_enabled"] = True
    else:
        adjustments["band_compression_enabled"] = False
    if band_compression:
        compressed = len(band_compression)
        avg_ratio = sum(c["ratio"] for c in band_compression.values()) / compressed
        adjustments["notes"].append(
            "🗜️ Compresión por banda: %d bandas (ratio avg %.1f:1)" % (compressed, avg_ratio)
        )
    
    # === AUTO-CONFIGURAR REPARACIÓN POR BANDA (v2.0.0) ===
    # Denoise en agudos (donde vive el hiss), declick en bandas con crest alto
    band_repair: Dict[str, Dict[str, str]] = {}
    for band_name, peak in (characteristics.band_peaks or {}).items():
        rms = _band_level(characteristics, band_name)
        if rms <= -80.0:
            continue
        crest = peak - rms
        repair_actions: Dict[str, str] = {}
        
        # Denoise en bandas agudas donde hay hiss (RMS bajo + crest moderado)
        if ("Air" in band_name or "High-Mid" in band_name) and rms < -25.0:
            repair_actions["denoise"] = "Leve" if rms > -35.0 else "Medio"
        
        # Declick si crest es muy alto (>18 dB = transientes fuertes)
        if crest > 18.0:
            repair_actions["declick"] = "Leve" if crest < 25.0 else "Medio"
        
        # Declip si peak cercano a 0
        if peak > -1.0:
            repair_actions["declip"] = "Leve"
        
        if repair_actions:
            band_repair[band_name] = repair_actions
    
    adjustments["band_repair"] = band_repair
    if band_repair:
        adjustments["band_repair_enabled"] = True
    else:
        adjustments["band_repair_enabled"] = False
    if band_repair:
        repaired = len(band_repair)
        denoised = sum(1 for r in band_repair.values() if "denoise" in r)
        declicked = sum(1 for r in band_repair.values() if "declick" in r)
        parts = []
        if denoised: parts.append("%d denoise" % denoised)
        if declicked: parts.append("%d declick" % declicked)
        adjustments["notes"].append(
            "🔬 Reparación por banda: %s" % ", ".join(parts)
        )
    
    # === AUTO-CONFIGURAR LIMITADOR MULTIBANDA: solo picos sobre el ideal ===
    if characteristics.band_peaks:
        mb_enabled = False
        for label, peak in characteristics.band_peaks.items():
            ideal_peak = MASTERING_IDEAL["band_ideal_peak"].get(label, -3.0)
            peak_gap = peak - ideal_peak  # positivo = pico muy alto
            
            if peak_gap > 1.0:  # Pico al menos 1dB sobre el ideal
                mb_enabled = True
                # Umbral = ideal_peak + un pequeño margen
                if label in ("Mid (500-2k Hz)", "High-Mid (2k-6k Hz)"):
                    threshold = ideal_peak - 0.5  # solo recortar lo que excede
                elif label == "Air (6k-16k Hz)":
                    threshold = ideal_peak - 0.3
                else:
                    threshold = ideal_peak - 1.0  # Sub/bass: más control
                threshold = max(-6.0, min(-0.3, threshold))
                adjustments["multiband_limiter_thresholds"][label] = round(threshold, 1)
        
        if mb_enabled:
            adjustments["multiband_limiter_enabled"] = True
            adjustments["band_limiter_enabled"] = True
            adjustments["notes"].append("🔧 Limitador Multibanda: solo bandas con picos sobre ideal")
        else:
            adjustments["band_limiter_enabled"] = False
        adjustments["notes"].append("✓ Picos por banda en rango ideal — sin limitador")
    
    # === AUTO-CONFIGURAR HEADROOM ===
    if characteristics.lufs > -70.0:
        gap = abs(characteristics.lufs - (-14.0))
        if gap > 15.0:
            adjustments["headroom_db"] = -14.0  # fuente muy baja, menos headroom
        elif gap > 8.0:
            adjustments["headroom_db"] = -16.0
        else:
            adjustments["headroom_db"] = -18.0  # fuente cercana al target
        adjustments["notes"].append(
            f"🔧 Headroom AUTO: {adjustments['headroom_db']:.0f} dB (gap: {gap:.0f} LU)"
        )

    # === AUTO-CONFIGURAR FADES ===
    if characteristics.suggested_fade_in > 0:
        adjustments["suggested_fade_in"] = characteristics.suggested_fade_in
    if characteristics.suggested_fade_out > 0:
        adjustments["suggested_fade_out"] = characteristics.suggested_fade_out
    if characteristics.suggested_fade_in > 0 or characteristics.suggested_fade_out > 0:
        adjustments["notes"].append(
            f"🔧 Fades auto: In={characteristics.suggested_fade_in:.2f}s, Out={characteristics.suggested_fade_out:.2f}s"
        )
    
    # === AUTO-CONFIGURAR BASADO EN MÉTRICAS DE LOUDNESS ===
    if characteristics.lufs > -70.0:
        # Agregar campos de ajuste de loudness
        adjustments["loudness_adjustments"] = {}
        
        # Calcular ganancia necesaria para llegar al target (asumiendo -14 LUFS objetivo)
        target_lufs = -14.0  # Este valor debería venir del preset o config
        gain_needed = target_lufs - characteristics.lufs
        adjustments["loudness_adjustments"]["estimated_gain_db"] = gain_needed
        
        # Si el audio está muy alto, reducir saturación para evitar sobre-distorsión
        if characteristics.lufs > -10.0:
            adjustments["saturation_drive_mult"] = 0.5
            adjustments["saturation_mix_mult"] = 0.6
            adjustments["glue_threshold_offset"] = -3.0  # Umbral más alto (menos compresión)
            adjustments["notes"].append(
                f"🔧 Audio muy alto ({characteristics.lufs:.1f} LUFS) - Saturación y compresión reducidas"
            )
        elif characteristics.lufs > -12.0:
            adjustments["saturation_drive_mult"] = 0.7
            adjustments["saturation_mix_mult"] = 0.8
            adjustments["glue_threshold_offset"] = -2.0
            adjustments["notes"].append(
                f"🔧 Audio alto ({characteristics.lufs:.1f} LUFS) - Procesamiento suave"
            )
        elif characteristics.lufs < -20.0:
            # Audio muy bajo: puede aceptar más procesamiento
            adjustments["saturation_drive_mult"] = 1.2
            adjustments["glue_ratio_mult"] = 1.1
            adjustments["notes"].append(
                f"🔧 Audio bajo ({characteristics.lufs:.1f} LUFS) - Más procesamiento permitido"
            )
        
        # Ajustar según rango dinámico (LRA)
        if characteristics.lra < 4.0:
            # Audio ya muy comprimido: reducir compresión adicional
            adjustments["glue_ratio_mult"] *= 0.7
            adjustments["glue_threshold_offset"] += -2.0
            adjustments["warnings"].append(
                f"⚠️ Audio muy comprimido (LRA: {characteristics.lra:.1f} LU) - Compresión mínima"
            )
        elif characteristics.lra > 12.0:
            # Audio con mucha dinámica: puede necesitar más control
            adjustments["glue_ratio_mult"] *= 1.2
            adjustments["notes"].append(
                f"🔧 Rango dinámico amplio (LRA: {characteristics.lra:.1f} LU) - Compresión moderada"
            )
        
        # Crest factor: indica transientes
        if characteristics.crest_factor > 15.0:
            # Muchos transientes: proteger con limitador suave
            adjustments["notes"].append(
                f"🔧 Transientes fuertes (Crest: {characteristics.crest_factor:.1f} dB) - Limitación cuidadosa"
            )
        elif characteristics.crest_factor < 8.0:
            # Audio "aplastado": muy poco headroom
            adjustments["warnings"].append(
                f"⚠️ Audio muy denso (Crest: {characteristics.crest_factor:.1f} dB) - Poco headroom"
            )
        
        # DC Offset: corregir si es significativo
        if abs(characteristics.dc_offset) > 0.01:
            adjustments["notes"].append(
                f"🔧 DC Offset detectado ({characteristics.dc_offset:.4f}) - Se corregirá"
            )
            adjustments["repair_settings"]["dc_offset_correction"] = True

    # === AUTO GLUE: OFF cuando hay compresión por banda (redundante) ===
    lra_for_glue = characteristics.lra if characteristics.lra > 0 else 7.0
    lra_ideal = MASTERING_IDEAL["min_lra_healthy"]  # 5.0 LU
    lra_gap = lra_for_glue - lra_ideal
    
    if band_compression:
        # v2.0.0: compresión por banda reemplaza glue global
        adjustments["glue_enabled"] = False
        adjustments["notes"].append(
            "🔧 Glue OFF — compresión por banda activa (%d bandas)" % len(band_compression)
        )
    elif lra_for_glue < 4.0:
        adjustments["glue_enabled"] = False
        adjustments["notes"].append(
            f"🔧 Glue OFF (LRA {lra_for_glue:.1f} — ya comprimido)"
        )
    elif lra_gap < 0:
        adjustments["glue_ratio_mult"] = max(0.3, 0.5 + lra_gap * 0.1)
        adjustments["notes"].append(
            f"🔧 Glue reducido (LRA {lra_for_glue:.1f}, gap={lra_gap:+.0f} LU vs ideal {lra_ideal})"
        )
    elif lra_gap > 3.0:
        adjustments["glue_ratio_mult"] = 1.1
        adjustments["notes"].append(
            f"🔧 Glue normal (LRA {lra_for_glue:.1f}, buena dinámica)"
        )
    else:
        adjustments["glue_ratio_mult"] = 0.8
        adjustments["notes"].append(
            f"🔧 Glue suave (LRA {lra_for_glue:.1f} — en rango ideal)"
        )

    # === SELECCIÓN INTELIGENTE DE KNEE PARA GLUE ===
    # Hard knee (0-3 dB): transientes fuertes, electrónica, kicks agresivos
    # Soft knee (6-10 dB): pads, texturas, audio ya comprimido, master bus suave
    lra_val = characteristics.lra if characteristics.lra > 0 else 7.0
    crest_val = characteristics.crest_factor if characteristics.crest_factor > 0 else 12.0
    if lra_val < 4.0:
        knee_db = 8.0  # Ya comprimido → knee muy suave para no aplastar más
    elif crest_val > 15.0:
        knee_db = 2.0  # Transientes fuertes → hard knee para control
    elif crest_val > 12.0:
        knee_db = 4.0  # Transientes moderados → knee medio
    elif characteristics.lufs > -12.0:
        knee_db = 3.0  # Audio caliente → más control
    else:
        knee_db = 6.0  # Default: soft knee balanceado
    adjustments["glue_knee_db"] = knee_db
    adjustments["notes"].append(
        f"🎛️ Glue knee: {knee_db:.0f} dB ({'hard' if knee_db <= 3 else 'soft' if knee_db >= 6 else 'medium'} knee)"
    )

    # === v2.0.0: CADENA SIMPLIFICADA (multiband como plugin principal) ===
    process_order = []
    
    # 1. Reparación global primero (denoise/declip/declick pre-multiband)
    needs_repair = (
        adjustments["repair_settings"].get("noise_reduction", "Off") != "Off" or
        adjustments["repair_settings"].get("declip", "Off") != "Off" or
        adjustments["repair_settings"].get("declick", "Off") != "Off"
    )
    if needs_repair:
        process_order.append("repair")
    
    # 2. Tone EQ paramétrico (complementa al multiband: Q, HPF, LPF)
    if (adjustments.get("dynamic_eq_enabled", False) or
        any(abs(v) > 0.1 for v in adjustments.get("eq_adjustments", {}).values())):
        process_order.append("tone_eq")
    
    # 3. MULTIBAND: el plugin principal (EQ + stereo + comp + limit + repair por banda)
    process_order.append("multiband")
    
    # 4. Saturación (color final, opcional)
    if adjustments.get("saturation_enabled", False):
        process_order.append("saturation")
    
    # 5. AutoGain + Brickwall (ganancia final + limitador de seguridad)
    process_order.append("autogain")
    process_order.append("brickwall")
    
    # Plugins obsoletos que YA NO se usan (absorbidos por multiband):
    # - deesser    → reemplazado por EQ + compresión en bandas agudas
    # - stereo_width → reemplazado por band_stereo
    # - stereo_dynamic → reemplazado por band_stereo
    # - glue       → reemplazado por band_compression
    # - master_limiter → reemplazado por band_limiter + brickwall
    
    adjustments["process_order"] = process_order
    adjustments["notes"].append(
        f"🔗 Cadena auto: {' → '.join(process_order)}"
    )
    
    # === SUGERIR TRUE PEAK ÓPTIMO ===
    current_tp = adjustments.get("suggested_true_peak")
    if current_tp is None:
        adjustments["suggested_true_peak"] = -1.5  # Estándar streaming moderno
        adjustments["notes"].append(
            "🎚️ True Peak sugerido: -1.5 dBTP (estándar streaming)"
        )

    # === AUTO-CONFIGURAR AUTOGAIN ===
    if characteristics.lufs > -70.0:
        gap = abs(characteristics.lufs - (-14.0))
        if gap > 12.0:
            adjustments["autogain_enabled"] = True
            adjustments["autogain_maxgain"] = 2.0
            adjustments["notes"].append("🔧 AutoGain ACTIVO (gap grande, necesita boost)")
        elif gap > 5.0:
            adjustments["autogain_enabled"] = True
            adjustments["autogain_maxgain"] = 1.35
            adjustments["notes"].append("🔧 AutoGain ACTIVO (gap moderado)")
        else:
            adjustments["autogain_enabled"] = False
            adjustments["notes"].append("🔧 AutoGain OFF (nivel cercano al target)")

    # === PERFIL GLOBAL DE PROCESAMIENTO ===
    profile, profile_reasons = classify_processing_profile(
        characteristics,
        minimal_lra_threshold=minimal_lra_threshold,
        minimal_crest_threshold=minimal_crest_threshold,
    )
    adjustments["processing_profile"] = profile
    adjustments["processing_profile_reasons"] = profile_reasons
    adjustments["notes"].append(
        f"🎚️ Perfil de procesamiento: {profile} ({'; '.join(profile_reasons)})"
    )
    
    # Detectar incompatibilidades graves
    severe_mismatch = False
    
    # Verificar compatibilidad preset-contenido
    if "Fuego" in preset_name or "Empuje" in preset_name:
        if not characteristics.has_strong_bass:
            severe_mismatch = True
            adjustments["warnings"].append(
                f"⚠️ INCOMPATIBILIDAD: Preset '{preset_name}' requiere bajos fuertes, "
                f"pero el audio tiene bajos débiles"
            )
            adjustments["alternative_presets"].extend([
                "Claridad (mejor para audio sin bajos fuertes)",
                "Natural (transparente para cualquier contenido)",
                "Universal (equilibrado para cualquier género)"
            ])
            # Sugerir ajustes de EQ para corregir
            bass_rms = characteristics.band_stats.get("Bass (60-250 Hz)", -100.0)
            subbass_rms = characteristics.band_stats.get("Subbass (20-60 Hz)", -100.0)
            adjustments["eq_adjustments"]["Bass (60-250 Hz)"] = +3.0 if bass_rms < -18.0 else +2.0
            adjustments["eq_adjustments"]["Subbass (20-60 Hz)"] = +2.5 if subbass_rms < -25.0 else +1.5
            adjustments["suggestions"].append(
                f"💡 Boost sugerido: Bass +{adjustments['eq_adjustments']['Bass (60-250 Hz)']:.1f} dB, "
                f"Subbass +{adjustments['eq_adjustments']['Subbass (20-60 Hz)']:.1f} dB"
            )
    
    if "Espacial" in preset_name or "Claridad" in preset_name:
        if characteristics.balance_score < 50:
            severe_mismatch = True
            adjustments["warnings"].append(
                f"⚠️ INCOMPATIBILIDAD: Preset '{preset_name}' requiere audio balanceado, "
                f"balance actual: {characteristics.balance_score:.0f}/100"
            )
            adjustments["alternative_presets"].extend([
                "Natural (más tolerante a desbalances)",
                "Universal (balance dinámico natural)"
            ])
            # Sugerir correcciones de EQ basadas en el análisis
            adjustments["suggestions"].append(
                "💡 Considera usar EQ dinámico para balancear antes de aplicar el preset"
            )
    
    if "Cinemático" in preset_name or "Cinta" in preset_name:
        if characteristics.has_strong_highs:
            air_rms = characteristics.band_stats.get("Air (6k-16k Hz)", -100.0)
            if air_rms > -12.0:
                adjustments["warnings"].append(
                    f"⚠️ ADVERTENCIA: Agudos muy fuertes ({air_rms:.1f} dB) - "
                    f"La saturación intensa puede añadir harshness"
                )
                adjustments["eq_adjustments"]["Air (6k-16k Hz)"] = -2.0
                adjustments["suggestions"].append(
                    "💡 Considera reducir Air -2dB antes de aplicar saturación"
                )
    
    # Balance espectral crítico
    if characteristics.balance_score < 30:
        adjustments["warnings"].append(
            f"🚨 BALANCE CRÍTICO: {characteristics.balance_score:.0f}/100 - "
            f"Audio muy desbalanceado"
        )
        adjustments["suggestions"].append(
            "💡 RECOMENDACIÓN: Corregir balance con EQ antes de masterizar"
        )
        # Generar sugerencias de EQ específicas
        _generate_eq_suggestions(characteristics, adjustments)
    
    # Ajustar de-esser según vocales y sibilancia
    if characteristics.has_vocals:
        if characteristics.needs_deess:
            adjustments["deesser_intensity_mult"] = 1.3
            adjustments["notes"].append(
                "🎤 De-esser intensificado por riesgo de sibilancia"
            )
        else:
            adjustments["deesser_intensity_mult"] = 1.0
            adjustments["notes"].append(
                "🎤 De-esser estándar para vocales"
            )
    else:
        adjustments["deesser_intensity_mult"] = 0.6
        adjustments["notes"].append(
            "🎵 De-esser reducido (sin vocales prominentes)"
        )
    
    # Ajustar saturación según balance
    if characteristics.balance_score < 50:
        # Audio desbalanceado - reducir saturación para no empeorar
        adjustments["saturation_drive_mult"] = 0.7
        adjustments["saturation_mix_mult"] = 0.8
        adjustments["notes"].append(
            "⚖️ Saturación reducida por desbalance espectral"
        )
    elif characteristics.balance_score > 80:
        # Audio muy balanceado - se puede usar más saturación
        adjustments["saturation_drive_mult"] = 1.2
        adjustments["saturation_mix_mult"] = 1.1
        adjustments["notes"].append(
            "⚖️ Saturación aumentada (buen balance espectral)"
        )

    # === FASE 2: MÓDULOS CONSERVADORES (SIN CREATIVIDAD EXCESIVA) ===
    if suno_diag.get("hats_metallic") or suno_diag.get("highs_narrow"):
        # Gap-based: calcular corrección exacta necesaria
        for band in ["High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"]:
            current = _band_level(characteristics, band)
            ideal = MASTERING_IDEAL["band_ideal_rms"].get(band, -16.0)
            corr = _calculate_eq_correction(current, ideal, max_cut=-3.0, max_boost=1.0, ratio=0.6)
            if abs(corr) > 0.1:
                _accumulate_eq_adjustment(adjustments, band, corr)
        adjustments["notes"].append(
            f"🔧 Hats/agudos: corrección calculada vs ideal (Air={_band_level(characteristics, 'Air (6k-16k Hz)'):.0f}→{MASTERING_IDEAL['band_ideal_rms']['Air (6k-16k Hz)']:.0f} dB)"
        )
        if not characteristics.is_mono:
            adjustments["stereo_dynamic_enabled"] = False  # v2.0.0: band_widths replaces stereo dynamic
            adjustments["stereo_dynamic_threshold_db"] = -22.0
            adjustments["stereo_dynamic_ratio"] = 1.45
            adjustments["stereo_dynamic_attack_ms"] = 25.0
            adjustments["stereo_dynamic_release_ms"] = 180.0
            adjustments["stereo_dynamic_mix"] = max(
                float(adjustments.get("stereo_dynamic_mix", 0.0) or 0.0),
                0.42,
            )
            adjustments["stereo_dynamic_band_mix"].update(
                {
                    "Subbass (20-60 Hz)": 0.00,
                    "Bass (60-250 Hz)": 0.05,
                    "Low-Mid (250-500 Hz)": 0.10,
                    "Mid (500-2k Hz)": 0.15,
                    "High-Mid (2k-6k Hz)": 0.28,
                    "Air (6k-16k Hz)": 0.34,
                }
            )
        adjustments["notes"].append(
            "🧩 Módulo Highs conservador: de-harsh leve + apertura estéreo controlada."
        )

    # Protector específico de metales (hi-hats/shakers):
    # 1) recorte leve adicional en presencia/aire
    # 2) saturación mínima en bandas altas
    # 3) limitador multibanda más estricto en High-Mid/Air
    high_mid_peak = float(characteristics.band_peaks.get("High-Mid (2k-6k Hz)", -100.0))
    air_peak = float(characteristics.band_peaks.get("Air (6k-16k Hz)", -100.0))
    metals_hot = (
        high_mid_peak > -3.8
        or air_peak > -2.6
        or bool(suno_diag.get("hats_metallic"))
    )
    if metals_hot:
        _accumulate_eq_adjustment(adjustments, "High-Mid (2k-6k Hz)", -0.22)
        _accumulate_eq_adjustment(adjustments, "Air (6k-16k Hz)", -0.30)

        adjustments["saturation_drive_mult"] = min(
            float(adjustments.get("saturation_drive_mult", 1.0) or 1.0),
            0.82,
        )
        adjustments["saturation_mix_mult"] = min(
            float(adjustments.get("saturation_mix_mult", 1.0) or 1.0),
            0.80,
        )
        adjustments["band_saturation_adjustments"]["High-Mid (2k-6k Hz)"] = {
            "drive_mult": 0.45,
            "mix_mult": 0.50,
        }
        adjustments["band_saturation_adjustments"]["Air (6k-16k Hz)"] = {
            "drive_mult": 0.30,
            "mix_mult": 0.35,
        }

        adjustments["multiband_limiter_enabled"] = True
        high_mid_thr = min(
            float(adjustments["multiband_limiter_thresholds"].get("High-Mid (2k-6k Hz)", -3.8)),
            -4.4 if high_mid_peak > -3.2 else -4.0,
        )
        air_thr = min(
            float(adjustments["multiband_limiter_thresholds"].get("Air (6k-16k Hz)", -4.2)),
            -4.8 if air_peak > -2.2 else -4.4,
        )
        adjustments["multiband_limiter_thresholds"]["High-Mid (2k-6k Hz)"] = max(-6.0, high_mid_thr)
        adjustments["multiband_limiter_thresholds"]["Air (6k-16k Hz)"] = max(-6.0, air_thr)

        adjustments["notes"].append(
            "🛠️ Protector de metales: recorte leve 2k-16k + saturación mínima + limitador más estricto."
        )

    if characteristics.has_vocals and (suno_diag.get("vocal_thin") or suno_diag.get("vocal_metallic")):
        # Voz con cuerpo, pero más contenida para no dominar la mezcla.
        _accumulate_eq_adjustment(adjustments, "Low-Mid (250-500 Hz)", +0.45)
        _accumulate_eq_adjustment(adjustments, "Mid (500-2k Hz)", +0.15)
        if suno_diag.get("vocal_metallic"):
            _accumulate_eq_adjustment(adjustments, "High-Mid (2k-6k Hz)", -0.55)
            adjustments["deesser_intensity_mult"] = max(
                float(adjustments.get("deesser_intensity_mult", 1.0) or 1.0),
                1.05,
            )
        if not characteristics.is_mono:
            adjustments["stereo_dynamic_enabled"] = False  # v2.0.0: band_widths replaces stereo dynamic
            adjustments["stereo_dynamic_mix"] = max(
                float(adjustments.get("stereo_dynamic_mix", 0.0) or 0.0),
                0.38,
            )
            current_mid_mix = float(adjustments["stereo_dynamic_band_mix"].get("Mid (500-2k Hz)", 0.0) or 0.0)
            adjustments["stereo_dynamic_band_mix"]["Mid (500-2k Hz)"] = max(current_mid_mix, 0.22)
        adjustments["notes"].append(
            "🧩 Módulo Voz conservador: +cuerpo y reducción mínima de timbre metálico."
        )

    if suno_diag.get("vocal_forward"):
        _accumulate_eq_adjustment(adjustments, "Mid (500-2k Hz)", -0.25)
        _accumulate_eq_adjustment(adjustments, "High-Mid (2k-6k Hz)", -0.30)
        adjustments["deesser_intensity_mult"] = min(
            1.12,
            max(float(adjustments.get("deesser_intensity_mult", 1.0) or 1.0), 1.02),
        )
        adjustments["notes"].append(
            "🧩 Voz integrada: presencia vocal levemente atenuada para balancear con la base."
        )

    if suno_diag.get("sub_weak"):
        _accumulate_eq_adjustment(adjustments, "Subbass (20-60 Hz)", +1.0)
        _accumulate_eq_adjustment(adjustments, "Bass (60-250 Hz)", +0.3)
        adjustments["notes"].append(
            "🧩 Módulo Low-End conservador: refuerzo leve de subbass."
        )

    if suno_diag.get("kick_edge"):
        # Si además falta sub, priorizar recuperar pegada antes que recortar.
        if suno_diag.get("sub_weak"):
            _accumulate_eq_adjustment(adjustments, "Bass (60-250 Hz)", +0.25)
            _accumulate_eq_adjustment(adjustments, "Low-Mid (250-500 Hz)", +0.10)
        else:
            _accumulate_eq_adjustment(adjustments, "Bass (60-250 Hz)", -0.25)
            _accumulate_eq_adjustment(adjustments, "Low-Mid (250-500 Hz)", -0.15)
        adjustments["multiband_limiter_enabled"] = True
        bass_target = -2.8 if suno_diag.get("sub_weak") else -3.0
        sub_target = -3.2 if suno_diag.get("sub_weak") else -3.4
        bass_thr = min(float(adjustments["multiband_limiter_thresholds"].get("Bass (60-250 Hz)", -2.5)), bass_target)
        sub_thr = min(float(adjustments["multiband_limiter_thresholds"].get("Subbass (20-60 Hz)", -3.0)), sub_target)
        adjustments["multiband_limiter_thresholds"]["Bass (60-250 Hz)"] = max(-6.0, bass_thr)
        adjustments["multiband_limiter_thresholds"]["Subbass (20-60 Hz)"] = max(-6.0, sub_thr)
        sat_cap = 0.92 if suno_diag.get("sub_weak") else 0.88
        adjustments["saturation_drive_mult"] = min(float(adjustments.get("saturation_drive_mult", 1.0) or 1.0), sat_cap)
        adjustments["saturation_mix_mult"] = min(float(adjustments.get("saturation_mix_mult", 1.0) or 1.0), sat_cap)
        adjustments["notes"].append(
            "🧩 Protector Kick/Bass: control dinámico con preservación de punch."
        )

    # === SUBBASS DINÁMICO (ANTI-FATIGA) ===
    # Evita que el low-end sea constante/aburrido: más control cuando viene "hot",
    # sin apagarlo por completo.
    sub_rms = _band_level(characteristics, "Subbass (20-60 Hz)")
    bass_rms = _band_level(characteristics, "Bass (60-250 Hz)")
    sub_peak = float(characteristics.band_peaks.get("Subbass (20-60 Hz)", -100.0))
    bass_peak = float(characteristics.band_peaks.get("Bass (60-250 Hz)", -100.0))
    sub_hot = sub_rms > -15.2 or (sub_peak > -1.8 and sub_rms > -18.2)
    bass_hot = bass_rms > -12.2 or (bass_peak > -1.6 and bass_rms > -14.0)
    low_end_hot = sub_hot or bass_hot
    low_end_very_hot = (
        sub_rms > -13.5
        or (sub_peak > -0.8 and sub_rms > -15.5)
        or (bass_peak > -0.7 and bass_rms > -11.8)
    )
    kick_punchy = (bass_peak > -1.8 and bass_rms < -12.8) or (bool(suno_diag.get("sub_weak")) and bass_rms < -12.0)
    if low_end_hot:
        adjustments["multiband_limiter_enabled"] = True
        # Umbrales más estrictos para graves cuando se detecta exceso de low-end.
        if kick_punchy:
            sub_target_thr = -3.9 if low_end_very_hot else -3.5
            bass_target_thr = -3.5 if low_end_very_hot else -3.1
        else:
            sub_target_thr = -4.4 if low_end_very_hot else -3.8
            bass_target_thr = -3.9 if low_end_very_hot else -3.4
        current_sub_thr = float(adjustments["multiband_limiter_thresholds"].get("Subbass (20-60 Hz)", -3.2))
        current_bass_thr = float(adjustments["multiband_limiter_thresholds"].get("Bass (60-250 Hz)", -3.0))
        adjustments["multiband_limiter_thresholds"]["Subbass (20-60 Hz)"] = max(
            -6.0, min(current_sub_thr, sub_target_thr)
        )
        adjustments["multiband_limiter_thresholds"]["Bass (60-250 Hz)"] = max(
            -6.0, min(current_bass_thr, bass_target_thr)
        )

        # Estabilizar low-end estéreo: sub casi mono, graves con movimiento mínimo.
        if not characteristics.is_mono:
            adjustments["stereo_dynamic_enabled"] = False  # v2.0.0: band_widths replaces stereo dynamic
            adjustments["stereo_dynamic_threshold_db"] = -21.0 if low_end_very_hot else -20.0
            adjustments["stereo_dynamic_ratio"] = 2.0 if low_end_very_hot else 1.8
            adjustments["stereo_dynamic_attack_ms"] = 12.0
            adjustments["stereo_dynamic_release_ms"] = 220.0
            adjustments["stereo_dynamic_mix"] = max(
                float(adjustments.get("stereo_dynamic_mix", 0.0) or 0.0),
                0.48 if low_end_very_hot else 0.42,
            )
            current_sub_mix = float(adjustments["stereo_dynamic_band_mix"].get("Subbass (20-60 Hz)", 0.0) or 0.0)
            current_bass_mix = float(adjustments["stereo_dynamic_band_mix"].get("Bass (60-250 Hz)", 0.0) or 0.0)
            adjustments["stereo_dynamic_band_mix"]["Subbass (20-60 Hz)"] = min(current_sub_mix, 0.00)
            bass_cap = 0.07 if kick_punchy else 0.05
            adjustments["stereo_dynamic_band_mix"]["Bass (60-250 Hz)"] = min(current_bass_mix, bass_cap)

        # Menos saturación en low-end cuando está excedido.
        sub_sat_prev = adjustments["band_saturation_adjustments"].get("Subbass (20-60 Hz)", {})
        bass_sat_prev = adjustments["band_saturation_adjustments"].get("Bass (60-250 Hz)", {})
        adjustments["band_saturation_adjustments"]["Subbass (20-60 Hz)"] = {
            "drive_mult": min(float(sub_sat_prev.get("drive_mult", 1.0) or 1.0), 0.80),
            "mix_mult": min(float(sub_sat_prev.get("mix_mult", 1.0) or 1.0), 0.75),
        }
        adjustments["band_saturation_adjustments"]["Bass (60-250 Hz)"] = {
            "drive_mult": min(float(bass_sat_prev.get("drive_mult", 1.0) or 1.0), 0.85),
            "mix_mult": min(float(bass_sat_prev.get("mix_mult", 1.0) or 1.0), 0.80),
        }
        if kick_punchy:
            _accumulate_eq_adjustment(adjustments, "Bass (60-250 Hz)", +0.30)
            _accumulate_eq_adjustment(adjustments, "Low-Mid (250-500 Hz)", +0.12)
        adjustments["notes"].append(
            "🧩 Subbass dinámico: low-end auto-controlado para mantener pegada sin fatiga."
        )

    # === FASE 1: BAND MOTION (SUBTLE) ===
    # Objetivo: añadir movimiento percibido y "vida" sin bombeo ni fatiga.
    # Esta fase usa la energía por banda (RMS + picos) para modular el
    # stereo dynamic de forma segura y musical.
    if not characteristics.is_mono:
        band_labels = [label for label, *_ in BAND_CONFIG]
        levels = [_band_level(characteristics, label) for label in band_labels]
        valid_levels = [v for v in levels if v > -99.0]
        if valid_levels:
            avg_level = sum(valid_levels) / len(valid_levels)
            spread_db = max(valid_levels) - min(valid_levels)

            lra_norm = _clamp((float(characteristics.lra) - 4.0) / 8.0, 0.0, 1.0)
            crest_norm = _clamp((float(characteristics.crest_factor) - 8.0) / 6.0, 0.0, 1.0)
            spread_norm = _clamp(spread_db / 14.0, 0.0, 1.0)
            pulse_index = _clamp(0.28 + (0.34 * lra_norm) + (0.24 * crest_norm) + (0.14 * spread_norm), 0.22, 0.92)

            # Topes sutiles por banda (fundamental grave casi mono).
            base_caps = {
                "Subbass (20-60 Hz)": (0.00, 0.02),
                "Bass (60-250 Hz)": (0.03, 0.09),
                "Low-Mid (250-500 Hz)": (0.06, 0.14),
                "Mid (500-2k Hz)": (0.10, 0.20),
                "High-Mid (2k-6k Hz)": (0.12, 0.24),
                "Air (6k-16k Hz)": (0.14, 0.28),
            }

            # Si el low-end viene caliente, cerramos aún más sub/bass.
            if low_end_hot:
                base_caps["Subbass (20-60 Hz)"] = (0.00, 0.00)
                base_caps["Bass (60-250 Hz)"] = (0.02, 0.06)

            # Si hay vocal dominante, proteger zona de inteligibilidad.
            voice_safe = bool(characteristics.has_vocals and (characteristics.voice_rms is not None) and float(characteristics.voice_rms) > -16.5)
            if voice_safe:
                lo_hm, hi_hm = base_caps["High-Mid (2k-6k Hz)"]
                base_caps["High-Mid (2k-6k Hz)"] = (lo_hm, min(hi_hm, 0.20))
                lo_mid, hi_mid = base_caps["Mid (500-2k Hz)"]
                base_caps["Mid (500-2k Hz)"] = (lo_mid, min(hi_mid, 0.18))

            recommended_mix: Dict[str, float] = {}
            for label in band_labels:
                rms = _band_level(characteristics, label)
                peak = float(characteristics.band_peaks.get(label, -100.0))
                rms_norm = _clamp((rms - (avg_level - 6.0)) / 10.0, 0.0, 1.0)
                peak_norm = _clamp((peak + 12.0) / 12.0, 0.0, 1.0)
                band_energy = _clamp((0.65 * rms_norm) + (0.35 * peak_norm), 0.0, 1.0)

                min_mix, max_mix = base_caps[label]
                energy_mix = min_mix + ((max_mix - min_mix) * (0.20 + 0.80 * band_energy) * pulse_index)
                recommended_mix[label] = _clamp(energy_mix, min_mix, max_mix)

            adjustments["stereo_dynamic_enabled"] = False  # v2.0.0: band_widths replaces stereo dynamic

            # Afinación global sutil si el valor sigue en defaults.
            if float(adjustments.get("stereo_dynamic_threshold_db", -24.0)) <= -23.9:
                adjustments["stereo_dynamic_threshold_db"] = -21.5
            if float(adjustments.get("stereo_dynamic_ratio", 1.6)) <= 1.61:
                adjustments["stereo_dynamic_ratio"] = 1.72
            if float(adjustments.get("stereo_dynamic_attack_ms", 20.0)) >= 19.9:
                adjustments["stereo_dynamic_attack_ms"] = 16.0
            if float(adjustments.get("stereo_dynamic_release_ms", 150.0)) <= 150.1:
                adjustments["stereo_dynamic_release_ms"] = 210.0

            current_global_mix = float(adjustments.get("stereo_dynamic_mix", 0.0) or 0.0)
            target_global_mix = _clamp(0.24 + (0.16 * pulse_index), 0.24, 0.40)
            adjustments["stereo_dynamic_mix"] = _clamp(max(current_global_mix, target_global_mix), 0.0, 0.52)

            for label, target_mix in recommended_mix.items():
                current_mix = float(adjustments["stereo_dynamic_band_mix"].get(label, 0.0) or 0.0)
                if label in ("Subbass (20-60 Hz)", "Bass (60-250 Hz)"):
                    # En low-end preferimos el menor de ambos para evitar fatiga y problemas de fase.
                    adjustments["stereo_dynamic_band_mix"][label] = min(current_mix, target_mix) if current_mix > 0.0 else target_mix
                else:
                    # En medios/agudos damos movimiento, respetando topes conservadores.
                    adjustments["stereo_dynamic_band_mix"][label] = max(current_mix, target_mix)

            adjustments["notes"].append(
                f"🕺 Band Motion Fase 1 (subtle): modulación por energía de bandas (pulso={pulse_index:.2f})."
            )

            # === FASE 2: SYNC AL COMPÁS (BPM + PULSO) ===
            # No automatiza por frame, pero sincroniza la "respuesta dinámica"
            # (attack/release + densidad) con la rejilla musical estimada.
            tempo_bpm = float(characteristics.tempo_bpm) if characteristics.tempo_bpm else None
            tempo_conf = float(getattr(characteristics, "tempo_confidence", 0.0) or 0.0)
            pulse_clarity = float(getattr(characteristics, "pulse_clarity", 0.0) or 0.0)
            if tempo_bpm and tempo_conf >= 0.28:
                beat_ms = 60000.0 / max(60.0, min(220.0, tempo_bpm))
                # Respuesta musical suave:
                # ataque ~1/12 beat, release ~2/3 beat.
                attack_sync_ms = _clamp(beat_ms / 12.0, 8.0, 24.0)
                release_sync_ms = _clamp(beat_ms * 0.66, 120.0, 320.0)

                current_attack = float(adjustments.get("stereo_dynamic_attack_ms", 20.0) or 20.0)
                current_release = float(adjustments.get("stereo_dynamic_release_ms", 150.0) or 150.0)
                adjustments["stereo_dynamic_attack_ms"] = round(min(current_attack, attack_sync_ms), 1)
                adjustments["stereo_dynamic_release_ms"] = round(max(current_release, release_sync_ms), 1)

                sync_strength = _clamp(0.78 + (0.18 * tempo_conf) + (0.10 * pulse_clarity), 0.78, 1.0)
                for label in ("Low-Mid (250-500 Hz)", "Mid (500-2k Hz)", "High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"):
                    if label in adjustments["stereo_dynamic_band_mix"]:
                        val = float(adjustments["stereo_dynamic_band_mix"][label])
                        adjustments["stereo_dynamic_band_mix"][label] = _clamp(val * sync_strength, 0.0, 0.34)

                # Densidad de rejilla sugerida: más rápida en BPM altos.
                grid = "1/8" if tempo_bpm < 112.0 else "1/16"
                adjustments["notes"].append(
                    f"🥁 Band Motion Fase 2: sync al compás ({tempo_bpm:.1f} BPM, grid {grid}, conf={tempo_conf:.2f})."
                )
    
    # === PRESUPUESTO DE SATURACIÓN ===
    # Calcular presupuesto total de saturación considerando todos los procesos activos
    saturation_budget = _calculate_saturation_budget(characteristics, adjustments)

    # === FASE 3: FEEDBACK ADAPTATIVO DE MOVIMIENTO ===
    # Ajuste fino automático según riesgo real del material/proceso.
    # Objetivo: mantener "vida" sin fatiga ni artefactos.
    if (not characteristics.is_mono) and bool(adjustments.get("stereo_dynamic_enabled")):
        est_thd = float(saturation_budget.get("estimated_thd", 0.0) or 0.0)
        true_peak = float(getattr(characteristics, "true_peak", -70.0) or -70.0)
        lra_val = float(getattr(characteristics, "lra", 0.0) or 0.0)
        crest_val = float(getattr(characteristics, "crest_factor", 0.0) or 0.0)
        voice_rms = float(characteristics.voice_rms) if characteristics.voice_rms is not None else -100.0
        voice_forward = bool(characteristics.has_vocals and voice_rms > -16.0)

        thd_risk = _clamp((est_thd - 1.8) / 2.4, 0.0, 1.0)
        tp_risk = _clamp((true_peak + 2.2) / 1.8, 0.0, 1.0)  # riesgo crece al acercarse a 0 dBTP
        lra_risk = _clamp((5.0 - lra_val) / 3.5, 0.0, 1.0)   # poco rango dinámico => menos movimiento
        crest_risk = _clamp((9.0 - crest_val) / 3.0, 0.0, 1.0)
        low_risk = 1.0 if low_end_very_hot else (0.55 if low_end_hot else 0.0)
        voice_risk = 0.65 if voice_forward else 0.0

        motion_risk = _clamp(
            (0.34 * thd_risk)
            + (0.20 * tp_risk)
            + (0.16 * lra_risk)
            + (0.14 * crest_risk)
            + (0.10 * low_risk)
            + (0.06 * voice_risk),
            0.0,
            1.0,
        )

        current_mix = float(adjustments.get("stereo_dynamic_mix", 0.0) or 0.0)
        # Control principal: más riesgo => menos movimiento global.
        damp = _clamp(1.0 - (0.48 * motion_risk), 0.56, 1.0)
        new_mix = _clamp(current_mix * damp, 0.0, 0.52)
        adjustments["stereo_dynamic_mix"] = round(new_mix, 3)

        # Si el riesgo es bajo y el pulso está claro, permitir micro-empuje musical.
        tempo_conf = float(getattr(characteristics, "tempo_confidence", 0.0) or 0.0)
        pulse_clarity = float(getattr(characteristics, "pulse_clarity", 0.0) or 0.0)
        can_boost = motion_risk < 0.28 and tempo_conf >= 0.50 and pulse_clarity >= 0.40 and lra_val >= 6.0
        band_boost = 1.06 if can_boost else 1.0

        # Rebalance por banda: low-end más estricto, zona vocal protegida.
        for label, val in list(adjustments["stereo_dynamic_band_mix"].items()):
            mix_val = float(val or 0.0)
            if label == "Subbass (20-60 Hz)":
                mix_val = min(mix_val, 0.00)
            elif label == "Bass (60-250 Hz)":
                mix_val = _clamp(mix_val * _clamp(damp - 0.08, 0.45, 1.0), 0.0, 0.08)
            elif label in ("Mid (500-2k Hz)", "High-Mid (2k-6k Hz)") and voice_forward:
                mix_val = _clamp(mix_val * _clamp(damp - 0.10, 0.40, 1.0), 0.0, 0.26)
            else:
                mix_val = _clamp(mix_val * damp * band_boost, 0.0, 0.34)
            adjustments["stereo_dynamic_band_mix"][label] = round(mix_val, 3)

        if motion_risk >= 0.55:
            adjustments["notes"].append(
                f"🎛️ Band Motion Fase 3: feedback protector activo (riesgo={motion_risk:.2f}) - movimiento atenuado."
            )
        elif can_boost:
            adjustments["notes"].append(
                f"🎛️ Band Motion Fase 3: feedback musical (riesgo={motion_risk:.2f}) - micro-empuje controlado."
            )
        else:
            adjustments["notes"].append(
                f"🎛️ Band Motion Fase 3: feedback estable (riesgo={motion_risk:.2f})."
            )

        # === FASE 4: COREOGRAFÍA CONTEXTUAL (PERFIL MUSICAL) ===
        # Ajuste macro final según contexto musical para evitar resultados "planos".
        # Perfiles:
        # - tight: foco en pegada/estabilidad (electrónica densa, low-end caliente)
        # - balanced: equilibrio general
        # - airy: apertura/aire (material dinámico, vocals claros, low-end controlado)
        tempo_bpm = float(characteristics.tempo_bpm) if characteristics.tempo_bpm else 0.0
        tempo_conf = float(getattr(characteristics, "tempo_confidence", 0.0) or 0.0)
        lra_val = float(getattr(characteristics, "lra", 0.0) or 0.0)
        stereo_width = float(getattr(characteristics, "stereo_width", 0.5) or 0.5)
        has_vocals = bool(characteristics.has_vocals)
        profile_name = "balanced"
        if selected_profile == "auto":
            if low_end_hot or motion_risk >= 0.55 or (tempo_bpm >= 118.0 and tempo_conf >= 0.45 and lra_val < 6.0):
                profile_name = "tight"
            elif (not low_end_hot) and lra_val >= 7.5 and motion_risk <= 0.35 and (tempo_bpm <= 112.0 or tempo_bpm == 0.0):
                profile_name = "airy"
        else:
            profile_name = selected_profile

        if profile_name == "tight":
            adjustments["stereo_dynamic_mix"] = round(_clamp(float(adjustments.get("stereo_dynamic_mix", 0.0)) * 0.92, 0.0, 0.48), 3)
            adjustments["stereo_dynamic_attack_ms"] = round(_clamp(float(adjustments.get("stereo_dynamic_attack_ms", 16.0)) * 0.92, 7.0, 22.0), 1)
            adjustments["stereo_dynamic_release_ms"] = round(_clamp(float(adjustments.get("stereo_dynamic_release_ms", 200.0)) * 0.92, 110.0, 280.0), 1)
            for label in ("Bass (60-250 Hz)", "Low-Mid (250-500 Hz)", "Mid (500-2k Hz)"):
                if label in adjustments["stereo_dynamic_band_mix"]:
                    adjustments["stereo_dynamic_band_mix"][label] = round(
                        _clamp(float(adjustments["stereo_dynamic_band_mix"][label]) * 0.90, 0.0, 0.24 if label == "Mid (500-2k Hz)" else 0.12),
                        3,
                    )
        elif profile_name == "airy":
            adjustments["stereo_dynamic_mix"] = round(_clamp(float(adjustments.get("stereo_dynamic_mix", 0.0)) * 1.05, 0.0, 0.50), 3)
            adjustments["stereo_dynamic_attack_ms"] = round(_clamp(float(adjustments.get("stereo_dynamic_attack_ms", 16.0)) * 1.05, 8.0, 24.0), 1)
            adjustments["stereo_dynamic_release_ms"] = round(_clamp(float(adjustments.get("stereo_dynamic_release_ms", 200.0)) * 1.10, 140.0, 330.0), 1)
            for label in ("Mid (500-2k Hz)", "High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"):
                if label in adjustments["stereo_dynamic_band_mix"]:
                    cap = 0.26 if label == "Mid (500-2k Hz)" else 0.34
                    boost = 1.06 if label != "Mid (500-2k Hz)" else 1.03
                    adjustments["stereo_dynamic_band_mix"][label] = round(
                        _clamp(float(adjustments["stereo_dynamic_band_mix"][label]) * boost, 0.0, cap),
                        3,
                    )
            if has_vocals and "Mid (500-2k Hz)" in adjustments["stereo_dynamic_band_mix"]:
                adjustments["stereo_dynamic_band_mix"]["Mid (500-2k Hz)"] = round(
                    _clamp(float(adjustments["stereo_dynamic_band_mix"]["Mid (500-2k Hz)"]), 0.0, 0.22),
                    3,
                )

        # Guardrail contextual por ancho estéreo existente:
        # si ya está muy ancho, no abrir más; si está angosto, permitir leve extra en altos.
        if stereo_width >= 0.78:
            adjustments["stereo_dynamic_mix"] = round(_clamp(float(adjustments.get("stereo_dynamic_mix", 0.0)) * 0.88, 0.0, 0.45), 3)
        elif stereo_width <= 0.32:
            adjustments["stereo_dynamic_mix"] = round(_clamp(float(adjustments.get("stereo_dynamic_mix", 0.0)) * 1.04, 0.0, 0.50), 3)
            for label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"):
                if label in adjustments["stereo_dynamic_band_mix"]:
                    adjustments["stereo_dynamic_band_mix"][label] = round(
                        _clamp(float(adjustments["stereo_dynamic_band_mix"][label]) * 1.04, 0.0, 0.34),
                        3,
                    )

        # Aplicar cantidad global elegida por el usuario (Fase 5)
        # 0.0 = sin movimiento | 1.0 = base | 1.5 = más expresivo (con topes de seguridad).
        amount_scale = motion_amount
        if amount_scale <= 0.001:
            adjustments["stereo_dynamic_mix"] = 0.0
            for label in list(adjustments["stereo_dynamic_band_mix"].keys()):
                adjustments["stereo_dynamic_band_mix"][label] = 0.0
            adjustments["stereo_dynamic_enabled"] = False
        else:
            mix_cap = 0.50 if profile_name != "tight" else 0.46
            adjustments["stereo_dynamic_mix"] = round(
                _clamp(float(adjustments.get("stereo_dynamic_mix", 0.0)) * amount_scale, 0.0, mix_cap),
                3,
            )
            for label, val in list(adjustments["stereo_dynamic_band_mix"].items()):
                # Low-end se mantiene más restringido incluso con amount alto.
                if label == "Subbass (20-60 Hz)":
                    cap = 0.00
                elif label == "Bass (60-250 Hz)":
                    cap = 0.08 if profile_name != "tight" else 0.06
                elif label == "Mid (500-2k Hz)":
                    cap = 0.27 if profile_name != "tight" else 0.24
                else:
                    cap = 0.34
                adjustments["stereo_dynamic_band_mix"][label] = round(
                    _clamp(float(val) * amount_scale, 0.0, cap),
                    3,
                )

        adjustments["motion_profile"] = profile_name
        if amount_scale <= 0.001:
            adjustments["notes"].append("🧠 Band Motion Fase 5: movimiento desactivado por usuario (amount=0%).")
        else:
            adjustments["notes"].append(
                f"🧠 Band Motion Fase 4/5: perfil '{profile_name}' (selección={selected_profile}) + amount={amount_scale*100:.0f}%."
            )
    
    # Si el presupuesto indica saturación excesiva, activar control
    if saturation_budget["estimated_thd"] > 3.0:
        adjustments["saturation_limiter_enabled"] = True
        adjustments["saturation_target_thd"] = 3.0
        adjustments["saturation_reduction_mode"] = "musical"
        adjustments["adaptive_saturation_control"] = True
        
        # Calcular compensación de volumen necesaria
        # THD > 5% = -1.5dB, THD > 7% = -3dB
        excess_thd = saturation_budget["estimated_thd"] - 3.0
        compensation = -0.5 * (excess_thd / 2.0)  # -0.5dB por cada 2% de exceso
        adjustments["saturation_compensation_db"] = max(-3.0, compensation)
        
        adjustments["notes"].append(
            f"🛡️ Control de saturación activado (THD estimado: {saturation_budget['estimated_thd']:.1f}%)"
        )
        if adjustments["saturation_compensation_db"] < 0:
            adjustments["notes"].append(
                f"🔉 Volumen final reducido {adjustments['saturation_compensation_db']:.1f}dB para compensar saturación"
            )
    elif saturation_budget["estimated_thd"] > 2.0:
        # THD moderado - modo transparente para control sutil
        adjustments["saturation_limiter_enabled"] = True
        adjustments["saturation_target_thd"] = 2.5
        adjustments["saturation_reduction_mode"] = "transparent"
        adjustments["notes"].append(
            f"🛡️ Control de saturación transparente (THD estimado: {saturation_budget['estimated_thd']:.1f}%)"
        )
    
    # Proteger bandas sensibles si hay agudos fuertes
    if characteristics.has_strong_highs:
        hm_prev = adjustments["band_saturation_adjustments"].get("High-Mid (2k-6k Hz)", {})
        air_prev = adjustments["band_saturation_adjustments"].get("Air (6k-16k Hz)", {})
        adjustments["band_saturation_adjustments"]["High-Mid (2k-6k Hz)"] = {
            "drive_mult": min(float(hm_prev.get("drive_mult", 1.0) or 1.0), 0.6),
            "mix_mult": min(float(hm_prev.get("mix_mult", 1.0) or 1.0), 0.7),
        }
        adjustments["band_saturation_adjustments"]["Air (6k-16k Hz)"] = {
            "drive_mult": min(float(air_prev.get("drive_mult", 1.0) or 1.0), 0.5),
            "mix_mult": min(float(air_prev.get("mix_mult", 1.0) or 1.0), 0.6),
        }
        adjustments["notes"].append(
            "🔒 Saturación reducida en High-Mid y Air (agudos fuertes)"
        )
    
    # Ajustar compresión glue según dinámica
    if characteristics.is_dynamic:
        # Audio dinámico - compresión más suave
        adjustments["glue_threshold_offset"] = -2.0  # Threshold más bajo
        adjustments["glue_ratio_mult"] = 0.85
        adjustments["notes"].append(
            "🎚️ Compresión glue suavizada (audio dinámico)"
        )
    else:
        # Audio plano - compresión más agresiva para dar vida
        adjustments["glue_threshold_offset"] = +2.0  # Threshold más alto
        adjustments["glue_ratio_mult"] = 1.15
        adjustments["notes"].append(
            "🎚️ Compresión glue intensificada (audio plano)"
        )
    
    # Ajustar EQ dinámico según bajos
    if characteristics.has_strong_bass:
        bass_rms = characteristics.band_stats.get("Bass (60-250 Hz)", -100.0)
        if bass_rms > -10.0:
            # Bajos muy fuertes - activar control dinámico
            adjustments["dynamic_eq_enabled"] = True
            adjustments["notes"].append(
                f"🔊 EQ dinámico activado (bajos muy fuertes: {bass_rms:.1f} dB)"
            )

    # === MODO DE PROCESAMIENTO MÍNIMO ===
    # Si el material ya viene muy comprimido, evitamos sumar glue/saturación
    # y otros procesos de densidad que tienden a empeorar la compresión.
    already_compressed = profile == "Conservador"
    if already_compressed:
        adjustments["minimal_processing"] = True
        adjustments["minimal_lra_threshold"] = minimal_lra_threshold
        adjustments["minimal_crest_threshold"] = minimal_crest_threshold
        adjustments["glue_enabled"] = False
        adjustments["saturation_enabled"] = False
        adjustments["multiband_limiter_enabled"] = False
        adjustments["stereo_dynamic_enabled"] = False
        if not characteristics.has_strong_bass and not characteristics.has_strong_highs:
            adjustments["dynamic_eq_enabled"] = False
        adjustments["glue_ratio_mult"] = min(float(adjustments.get("glue_ratio_mult", 1.0) or 1.0), 0.65)
        adjustments["saturation_drive_mult"] = min(float(adjustments.get("saturation_drive_mult", 1.0) or 1.0), 0.55)
        adjustments["saturation_mix_mult"] = min(float(adjustments.get("saturation_mix_mult", 1.0) or 1.0), 0.55)
        adjustments["notes"].append(
            f"○ Material ya comprimido (LRA {characteristics.lra:.1f} LU, Crest {characteristics.crest_factor:.1f} dB; umbrales LRA≤{minimal_lra_threshold:.1f}, Crest≤{minimal_crest_threshold:.1f}) - se saltean Glue, Saturación y Stereo dinámico."
        )
        if characteristics.lra <= 3.5:
            adjustments["warnings"].append(
                f"⚠️ Audio muy comprimido (LRA: {characteristics.lra:.1f} LU) - evitar compresión adicional."
            )
    elif profile == "Agresivo":
        adjustments["glue_enabled"] = True
        adjustments["saturation_enabled"] = True
        adjustments["glue_ratio_mult"] = max(float(adjustments.get("glue_ratio_mult", 1.0) or 1.0), 1.08)
        adjustments["saturation_drive_mult"] = max(float(adjustments.get("saturation_drive_mult", 1.0) or 1.0), 1.05)
        adjustments["saturation_mix_mult"] = max(float(adjustments.get("saturation_mix_mult", 1.0) or 1.0), 1.05)
        if characteristics.stereo_category not in ("VeryWide",):
            adjustments["stereo_dynamic_enabled"] = False  # v2.0.0: band_widths replaces stereo dynamic
        adjustments["notes"].append(
            "○ Perfil agresivo: se permite más densidad y movimiento si el material lo soporta."
        )
    
    return adjustments


def _build_adjustments_from_ia(strategy: Dict[str, Any], characteristics: Any) -> Dict[str, Any]:
    """Convierte la respuesta JSON completa de la IA al formato interno de adjustments.
    La IA ahora controla TODOS los plugins: repair, tone_eq, multiband, saturation, glue, deesser, autogain."""
    if isinstance(strategy.get("actions"), list):
        return _build_adjustments_from_ai_actions(strategy)
    
    mb = strategy.get("multiband", {})
    sat = strategy.get("saturation", {})
    glue = strategy.get("glue", {})
    deess = strategy.get("deesser", {})
    repair = strategy.get("repair", {})
    tone = strategy.get("tone_eq", {})
    autogain = strategy.get("autogain", {})

    adjustments = {
        "notes": [strategy.get("diagnosis", "")] + strategy.get("notes", []),
        "warnings": [],
        "suggestions": strategy.get("what_to_fix", []),
        "diagnostics": strategy.get("diagnosis", ""),
        # Multiband EQ
        "eq_adjustments": {
            k: round(float(v.get("eq_db", 0)), 1)
            for k, v in mb.items() if isinstance(v, dict)
        },
        # Stereo
        "band_widths": {
            k: round(float(v.get("stereo_width", 1.0)), 2)
            for k, v in mb.items() if isinstance(v, dict)
        },
        # Compression
        "band_compression": {
            k: {
                "threshold_db": round(float(v.get("comp_threshold_db", -18)), 1),
                "ratio": round(float(v.get("comp_ratio", 1.2)), 1),
                "attack_ms": round(float(v.get("comp_attack_ms", 5)), 1),
                "release_ms": round(float(v.get("comp_release_ms", 60)), 1),
                "knee_db": 4.0, "makeup_db": 0.0,
            }
            for k, v in mb.items() if isinstance(v, dict)
        },
        # Limiter
        "multiband_limiter_enabled": any(
            float(v.get("limiter_threshold_db", 0)) != 0
            for v in mb.values() if isinstance(v, dict)
        ),
        "multiband_limiter_thresholds": {
            k: round(float(v.get("limiter_threshold_db", 0)), 1)
            for k, v in mb.items() if isinstance(v, dict) and float(v.get("limiter_threshold_db", 0)) != 0
        },
        # Repair
        "repair_settings": {
            "noise_reduction": str(repair.get("noise_reduction", "Off")),
            "declip": str(repair.get("declip", "Off")),
            "declick": str(repair.get("declick", "Off")),
        },
        "band_repair": {},
        # Tone EQ
        "tone_low_db": round(float(tone.get("bass_db", 0)), 1),
        "sub_bass_db": round(float(tone.get("sub_bass_db", 0)), 1),
        "tone_mid_db": round(float(tone.get("mid_db", 0)), 1),
        "tone_high_db": round(float(tone.get("high_mid_db", 0)), 1),
        # Saturation
        "saturation_enabled": bool(sat.get("enabled", True)),
        "saturation_drive_mult": round(float(sat.get("drive_db", 1.0)), 1),
        "saturation_mix_mult": round(float(sat.get("mix", 0.3)), 2),
        # Glue
        "glue_enabled": bool(glue.get("enabled", False)),
        "glue_threshold_offset": 0.0,
        "glue_ratio_mult": round(float(glue.get("ratio", 1.4)), 1),
        "glue_knee_db": round(float(glue.get("knee_db", 6)), 1),
        # De-esser
        "deesser_enabled": bool(deess.get("enabled", False)),
        "deesser_intensity_mult": round(float(deess.get("intensity", 0.7)), 1),
        # Headroom + Autogain
        "headroom_db": round(float(strategy.get("headroom_db", -17)), 0),
        "autogain_enabled": bool(autogain.get("enabled", True)),
        # Flags
        "stereo_width_enabled": False,
        "stereo_dynamic_enabled": False,
        "band_eq_enabled": bool(mb),
        "band_stereo_enabled": bool(mb),
        "band_compression_enabled": bool(mb),
        "band_limiter_enabled": adjustments.get("multiband_limiter_enabled", False) if 'adjustments' in dir() else False,
        "band_repair_enabled": False,
        "dynamic_eq_enabled": True,
        # Process
        "process_order": strategy.get("process_order", ["repair", "tone_eq", "multiband", "saturation", "autogain"]),
        "processing_profile": "IA",
        "block_mode": False,
        "section_adjustments": {},
        "suggested_fade_in": 0.0,
        "suggested_fade_out": 0.0,
        "motion_profile": "balanced",
        "motion_profile_selected": "auto",
        "motion_amount": 1.0,
        "band_saturation_adjustments": {},
    }
    # Fix band_limiter_enabled reference
    adjustments["band_limiter_enabled"] = adjustments["multiband_limiter_enabled"]
    return adjustments


def _build_adjustments_from_ai_actions(strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Proyección compatible para UI; audio_actions sigue siendo la fuente canónica."""
    band_labels = {
        "sub_bass": "Subbass (20-60 Hz)", "bass": "Bass (60-250 Hz)",
        "low_mid": "Low-Mid (250-500 Hz)", "mid": "Mid (500-2k Hz)",
        "high_mid": "High-Mid (2k-6k Hz)", "air": "Air (6k-16k Hz)",
    }
    actions = [item for item in strategy.get("actions", []) if isinstance(item, dict)]
    adjustments: Dict[str, Any] = {
        "notes": [strategy.get("diagnosis", "")] + list(strategy.get("notes", [])),
        "warnings": [
            f"Acción IA rechazada: {item.get('error', 'inválida')}"
            for item in strategy.get("decision_trace", {}).get("rejected_actions", [])
        ],
        "suggestions": list(strategy.get("what_to_fix", [])),
        "diagnostics": strategy.get("diagnosis", ""),
        "eq_adjustments": {}, "band_widths": {}, "band_compression": {},
        "multiband_limiter_thresholds": {}, "multiband_limiter_enabled": False,
        "repair_settings": {"noise_reduction": "Off", "declip": "Off", "declick": "Off"},
        "band_repair": {}, "band_saturation_adjustments": {},
        "saturation_enabled": False, "saturation_drive_mult": 1.0,
        "saturation_mix_mult": 0.0, "glue_enabled": False,
        "glue_threshold_offset": 0.0, "glue_ratio_mult": 1.0,
        "glue_knee_db": 6.0, "deesser_enabled": False,
        "deesser_intensity_mult": 1.0, "headroom_db": -17.0,
        "autogain_enabled": True, "dynamic_eq_enabled": False,
        "stereo_width_enabled": False, "stereo_dynamic_enabled": False,
        "band_eq_enabled": False, "band_stereo_enabled": False,
        "band_compression_enabled": False, "band_limiter_enabled": False,
        "band_repair_enabled": False, "processing_profile": "IA",
        "block_mode": False, "section_adjustments": {},
        "suggested_fade_in": 0.0, "suggested_fade_out": 0.0,
        "motion_profile": "balanced", "motion_profile_selected": "auto",
        "motion_amount": 1.0,
        "audio_actions": actions,
        "decision_trace": strategy.get("decision_trace", {}),
        "source_fingerprint": strategy.get("decision_trace", {}).get("source_fingerprint"),
    }
    order: list[str] = []
    for raw in actions:
        fid = str(raw.get("function_id", ""))
        params = raw.get("params", {}) if isinstance(raw.get("params"), dict) else {}
        target = raw.get("target")
        label = band_labels.get(str(target), str(target))
        plugin_key = fid.split(".")[1] if fid.count(".") >= 2 else fid
        if plugin_key not in order:
            order.append(plugin_key)
        if fid == "audio.multiband.eq" and label:
            adjustments["eq_adjustments"][label] = params.get("gain_db", 0.0)
            adjustments["band_eq_enabled"] = True
        elif fid == "audio.multiband.stereo_width" and label:
            adjustments["band_widths"][label] = params.get("width", 1.0)
            adjustments["band_stereo_enabled"] = True
            adjustments["stereo_width_enabled"] = True
        elif fid == "audio.multiband.compressor" and label:
            adjustments["band_compression"][label] = dict(params)
            adjustments["band_compression_enabled"] = True
            adjustments["dynamic_eq_enabled"] = True
        elif fid == "audio.multiband.limiter" and label:
            adjustments["multiband_limiter_thresholds"][label] = params.get("ceiling_db", -3.0)
            adjustments["multiband_limiter_enabled"] = True
            adjustments["band_limiter_enabled"] = True
        elif fid == "audio.multiband.saturation" and label:
            adjustments["band_saturation_adjustments"][label] = dict(params)
        elif fid == "audio.repair.denoise":
            adjustments["repair_settings"]["noise_reduction"] = params.get("level", "Off")
        elif fid == "audio.repair.declip":
            adjustments["repair_settings"]["declip"] = params.get("level", "Off")
        elif fid == "audio.repair.declick":
            adjustments["repair_settings"]["declick"] = params.get("level", "Off")
        elif fid == "audio.saturation.softclip":
            adjustments["saturation_enabled"] = True
            adjustments["saturation_drive_mult"] = params.get("drive_db", 0.0)
            adjustments["saturation_mix_mult"] = params.get("mix", 0.0)
        elif fid == "audio.glue.bus_compressor":
            adjustments["glue_enabled"] = True
            adjustments["glue_ratio_mult"] = params.get("ratio", 1.4)
            adjustments["glue_knee_db"] = params.get("knee_db", 6.0)
        elif fid == "audio.deesser.sibilance_reduction":
            adjustments["deesser_enabled"] = True
            adjustments["deesser_intensity_mult"] = params.get("intensity", 0.7)
        elif fid == "audio.autogain.headroom":
            adjustments["headroom_db"] = params.get("gain_db", -17.0)
        elif fid == "audio.loudness.fade_in":
            adjustments["suggested_fade_in"] = params.get("duration_seconds", 0.0)
        elif fid == "audio.loudness.fade_out":
            adjustments["suggested_fade_out"] = params.get("duration_seconds", 0.0)
    adjustments["process_order"] = order
    return adjustments


def _calculate_saturation_budget(
    characteristics: AudioCharacteristics,
    adjustments: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calcula el presupuesto total de saturación estimando THD acumulado.
    
    Considera:
    - Saturación global activa
    - Saturación por banda
    - Compresión glue (añade armónicos)
    - Balance espectral (desbalance aumenta percepción de saturación)
    
    Args:
        characteristics: Características del audio
        adjustments: Ajustes actuales del preset
        
    Returns:
        Dict con:
        - estimated_thd: THD total estimado en %
        - saturation_sources: Lista de fuentes contribuyendo
        - risk_level: "low", "medium", "high"
    """
    thd_estimate = 0.0
    sources = []
    
    # Base: saturación global
    sat_drive_mult = adjustments.get("saturation_drive_mult", 1.0)
    sat_mix_mult = adjustments.get("saturation_mix_mult", 1.0)
    
    # Cada multiplicador de drive añade ~0.5% THD
    # Cada multiplicador de mix controla cuánto se aplica
    global_thd = (sat_drive_mult - 1.0) * 0.5 * sat_mix_mult
    if global_thd > 0:
        thd_estimate += global_thd
        sources.append(f"Saturación global: +{global_thd:.1f}%")
    
    # Saturación por banda (cada banda contribuye)
    band_adjustments = adjustments.get("band_saturation_adjustments", {})
    for band, adj in band_adjustments.items():
        drive_mult = adj.get("drive_mult", 1.0)
        mix_mult = adj.get("mix_mult", 1.0)
        band_thd = (drive_mult - 1.0) * 0.3 * mix_mult  # Menos impacto que global
        if band_thd > 0:
            thd_estimate += band_thd
            sources.append(f"{band}: +{band_thd:.1f}%")
    
    # Compresión glue (añade armónicos sutiles)
    glue_ratio_mult = adjustments.get("glue_ratio_mult", 1.0)
    if glue_ratio_mult > 1.0:
        glue_thd = (glue_ratio_mult - 1.0) * 0.2
        thd_estimate += glue_thd
        sources.append(f"Glue compression: +{glue_thd:.1f}%")
    
    # Penalización por desbalance espectral
    # Audio desbalanceado + saturación = THD percibido más alto
    if characteristics.balance_score < 50:
        balance_penalty = (50 - characteristics.balance_score) * 0.02
        thd_estimate += balance_penalty
        sources.append(f"Desbalance espectral: +{balance_penalty:.1f}%")
    
    # Penalización por agudos fuertes (más susceptibles a harshness)
    if characteristics.has_strong_highs:
        high_penalty = 0.5
        thd_estimate += high_penalty
        sources.append(f"Agudos fuertes: +{high_penalty:.1f}%")
    
    # Determinar nivel de riesgo
    if thd_estimate < 2.0:
        risk_level = "low"
    elif thd_estimate < 4.0:
        risk_level = "medium"
    else:
        risk_level = "high"
    
    return {
        "estimated_thd": thd_estimate,
        "saturation_sources": sources,
        "risk_level": risk_level,
    }


def _generate_eq_suggestions(
    characteristics: AudioCharacteristics,
    adjustments: Dict[str, Any]
) -> Dict[str, Any]:
    """Genera sugerencias específicas de EQ basadas en el análisis de bandas."""
    if not characteristics.band_stats:
        return adjustments
    
    levels = list(characteristics.band_stats.values())
    avg = sum(levels) / len(levels)
    
    for label, rms in characteristics.band_stats.items():
        deviation = rms - avg
        
        if deviation > 4.0:
            # Banda muy por encima del promedio - aplicar corte (valor negativo)
            suggested_cut = -deviation * 0.6  # Negativo
            suggested_cut = max(-6.0, suggested_cut)  # Limitar a -6 dB máximo de corte
            _accumulate_eq_adjustment(adjustments, label, suggested_cut, min_db=-6.0, max_db=6.0)
            adjustments["suggestions"].append(
                f"   • {label}: {suggested_cut:.1f} dB (reducir exceso)"
            )
        elif deviation < -4.0:
            # Banda muy por debajo del promedio - aplicar boost (valor positivo)
            suggested_boost = -deviation * 0.6  # Positivo (deviation es negativo)
            suggested_boost = min(6.0, suggested_boost)  # Limitar a +6 dB máximo de boost
            _accumulate_eq_adjustment(adjustments, label, suggested_boost, min_db=-6.0, max_db=6.0)
            adjustments["suggestions"].append(
                f"   • {label}: +{suggested_boost:.1f} dB (compensar falta)"
            )
    
    return adjustments


def apply_intelligent_adjustments(
    base_params: Dict[str, float],
    adjustments: Dict[str, Any]
) -> Dict[str, float]:
    """
    Aplica los ajustes inteligentes a los parámetros base.
    
    Args:
        base_params: Parámetros del preset base
        adjustments: Ajustes calculados por adapt_preset_to_audio
        
    Returns:
        Parámetros ajustados
    """
    adjusted = base_params.copy()
    
    # Ajustar de-esser
    if "deesser_intensity" in adjusted:
        adjusted["deesser_intensity"] *= adjustments.get("deesser_intensity_mult", 1.0)
        adjusted["deesser_intensity"] = max(0.2, min(1.0, adjusted["deesser_intensity"]))
    
    # Ajustar saturación global
    if "saturation_drive" in adjusted:
        adjusted["saturation_drive"] *= adjustments.get("saturation_drive_mult", 1.0)
    if "saturation_mix" in adjusted:
        adjusted["saturation_mix"] *= adjustments.get("saturation_mix_mult", 1.0)
    
    # Ajustar glue
    if "glue_threshold" in adjusted:
        adjusted["glue_threshold"] += adjustments.get("glue_threshold_offset", 0.0)
    if "glue_ratio" in adjusted:
        adjusted["glue_ratio"] *= adjustments.get("glue_ratio_mult", 1.0)
    
    return adjusted


# =============================================================================
# FASE 3: ANÁLISIS DE LOTES (BATCH)
# =============================================================================

def analyze_batch_for_automaster(
    files: List[pathlib.Path],
    verbose: bool = False,
    use_spectrum: bool = False,  # Desactivado por defecto para velocidad
    max_files_to_analyze: int = 5,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    calculate_saturation_budget: bool = True,  # Calcular presupuesto de saturación
) -> Tuple[AudioCharacteristics, List[str], Dict[str, Any]]:
    """
    Analiza múltiples archivos de audio y genera una configuración común.
    
    Args:
        files: Lista de archivos a analizar
        verbose: Mostrar comandos ffmpeg
        use_spectrum: Realizar análisis de espectro FFT
        max_files_to_analyze: Máximo de archivos a analizar (para lotes grandes)
        progress_callback: Callback opcional (file_idx, total_files, file_name)
        calculate_saturation_budget: Calcular presupuesto de saturación por archivo
        
    Returns:
        (merged_characteristics, recommendations, individual_results)
    """
    if not files:
        raise ValueError("No hay archivos para analizar")
    
    # Limitar cantidad de archivos para análisis (rendimiento)
    files_to_analyze = files[:max_files_to_analyze]
    
    individual_results: Dict[str, Any] = {}
    recommendations = []
    
    recommendations.append(f"📁 === ANÁLISIS POR TEMA ({len(files_to_analyze)} archivos) ===\n")
    if len(files_to_analyze) < len(files):
        recommendations.append(
            f"ℹ️ Se analizaron {len(files_to_analyze)} de {len(files)} archivos según límite configurado."
        )
    
    # Analizar cada archivo
    all_characteristics: List[AudioCharacteristics] = []
    
    for idx, file_path in enumerate(files_to_analyze):
        if progress_callback:
            progress_callback(idx + 1, len(files_to_analyze), file_path.name)
        
        try:
            chars, _, _ = analyze_audio_for_automaster(
                input_path=file_path,
                verbose=verbose,
                use_spectrum=use_spectrum,
                full_analysis=False,
            )
            all_characteristics.append(chars)
            
            # Guardar características con información adicional
            individual_results[str(file_path)] = {
                "characteristics": chars,
                "saturation_budget": None,  # Se calculará después si es necesario
            }
        except Exception as e:
            recommendations.append(f"⚠️ Error analizando {file_path.name}: {e}")
    
    if not all_characteristics:
        raise RuntimeError("No se pudo analizar ningún archivo")
    
    # Combinar características (promediar/unificar)
    merged = _merge_batch_characteristics(all_characteristics)
    
    # Generar resumen del lote
    recommendations.append(f"\n📊 === RESUMEN DEL LOTE ===")
    
    # Estadísticas de clipping
    clipping_count = sum(1 for c in all_characteristics if c.has_clipping)
    if clipping_count > 0:
        recommendations.append(
            f"🔴 Clipping detectado en {clipping_count}/{len(all_characteristics)} archivos"
        )
    else:
        recommendations.append("✓ Sin clipping en ningún archivo")
    
    # Estadísticas de ruido
    noise_categories = [c.noise_category for c in all_characteristics]
    worst_noise = "Excellent"
    for cat in ["VeryHigh", "High", "Moderate", "Good"]:
        if cat in noise_categories:
            worst_noise = cat
            break
    recommendations.append(f"🔊 Peor nivel de ruido: {worst_noise}")
    
    # Estadísticas de stereo
    mono_count = sum(1 for c in all_characteristics if c.is_mono)
    if mono_count == len(all_characteristics):
        recommendations.append("ℹ️ Todos los archivos son MONO")
    elif mono_count > 0:
        recommendations.append(f"⚠️ {mono_count}/{len(all_characteristics)} archivos son MONO")
    else:
        stereo_cats = [c.stereo_category for c in all_characteristics]
        avg_width = sum(c.stereo_width for c in all_characteristics) / len(all_characteristics)
        recommendations.append(f"🔊 Ancho stereo promedio: {avg_width*100:.0f}%")
    
    # Estadísticas de vocales
    vocal_count = sum(1 for c in all_characteristics if c.has_vocals)
    if vocal_count == len(all_characteristics):
        recommendations.append("🎤 Todos los archivos tienen vocales")
    elif vocal_count > 0:
        recommendations.append(f"🎤 {vocal_count}/{len(all_characteristics)} archivos con vocales")
    else:
        recommendations.append("🎵 Sin vocales prominentes en ningún archivo")
    
    # Balance promedio
    avg_balance = sum(c.balance_score for c in all_characteristics) / len(all_characteristics)
    recommendations.append(f"⚖️ Balance espectral promedio: {avg_balance:.0f}/100")
    
    recommendations.append("\n=== CONFIGURACIÓN RECOMENDADA PARA EL LOTE ===")
    
    return merged, recommendations, individual_results


def _merge_batch_characteristics(
    all_chars: List[AudioCharacteristics]
) -> AudioCharacteristics:
    """
    Combina las características de múltiples archivos en una configuración común.
    Usa estrategia conservadora: si cualquier archivo tiene un problema, se asume para todos.
    """
    if not all_chars:
        raise ValueError("No hay características para combinar")
    
    # Promediar band_stats
    merged_band_stats = {}
    band_labels = list(all_chars[0].band_stats.keys()) if all_chars[0].band_stats else []
    for label in band_labels:
        values = [c.band_stats.get(label, -100.0) for c in all_chars]
        merged_band_stats[label] = sum(values) / len(values)
    
    # Promediar voice_rms (usar máximo para ser conservador con de-esser)
    voice_rms_values = [c.voice_rms for c in all_chars if c.voice_rms is not None]
    merged_voice_rms = max(voice_rms_values) if voice_rms_values else None
    
    # Clipping: si cualquiera tiene, asumir que hay (conservador)
    has_any_clipping = any(c.has_clipping for c in all_chars)
    max_peak = max(c.max_peak_db for c in all_chars)
    clip_count = sum(c.clipping_info.get('clip_count', 0) for c in all_chars)
    
    merged_clipping = {
        'detected': has_any_clipping,
        'max_peak_db': max_peak,
        'clip_count': clip_count,
    }
    
    # Ruido: usar el peor nivel
    noise_floors = [c.noise_floor_db for c in all_chars]
    worst_noise_floor = max(noise_floors)  # Más alto = peor
    noise_categories = [c.noise_category for c in all_chars]
    # Ordenar por severidad
    severity_order = ["Excellent", "Good", "Moderate", "High", "VeryHigh", "Unknown"]
    worst_category = "Excellent"
    for cat in severity_order[::-1]:
        if cat in noise_categories:
            worst_category = cat
            break
    
    merged_noise = {
        'floor_db': worst_noise_floor,
        'category': worst_category,
    }
    
    # Stereo: usar el más restrictivo
    is_any_mono = any(c.is_mono for c in all_chars)
    avg_width = sum(c.stereo_width for c in all_chars) / len(all_chars)
    
    # Determinar categoría promedio
    if is_any_mono:
        merged_stereo_cat = "Mixed"
    elif avg_width < 0.3:
        merged_stereo_cat = "Narrow"
    elif avg_width < 0.6:
        merged_stereo_cat = "Normal"
    elif avg_width < 0.8:
        merged_stereo_cat = "Wide"
    else:
        merged_stereo_cat = "VeryWide"
    
    merged_stereo = {
        'is_mono': is_any_mono,
        'stereo_width': avg_width,
        'stereo_category': merged_stereo_cat,
    }
    
    # Picos por banda: usar máximos
    merged_band_peaks = {}
    for label in band_labels:
        peaks = [c.band_peaks.get(label, -100.0) for c in all_chars if c.band_peaks]
        merged_band_peaks[label] = max(peaks) if peaks else -100.0
    
    # Silencios: promediar
    fade_ins = [c.suggested_fade_in for c in all_chars]
    fade_outs = [c.suggested_fade_out for c in all_chars]
    
    merged_silence = {
        'suggested_fade_in': sum(fade_ins) / len(fade_ins) if fade_ins else 0.0,
        'suggested_fade_out': sum(fade_outs) / len(fade_outs) if fade_outs else 0.0,
        'detail': f"Promedio de {len(all_chars)} archivos",
    }

    # === Loudness metrics (del diagnóstico) ===
    # Estrategia conservadora:
    # - LUFS: usar el más alto (más "loud") para suavizar el preset si algún archivo ya viene caliente.
    # - True Peak: usar el más alto (más cercano a 0).
    # - LRA: usar el más bajo (más comprimido) para evitar sobre-compresión en lote.
    # - Crest factor: usar el más bajo (menos headroom) como señal de densidad.
    loudness_candidates = [c for c in all_chars if getattr(c, "lufs", -70.0) > -70.0]
    merged_loudness: dict | None = None
    if loudness_candidates:
        lufs_max = max(c.lufs for c in loudness_candidates)
        tp_max = max(c.true_peak for c in loudness_candidates)
        lra_min = min(c.lra for c in loudness_candidates)
        rms_max = max(c.rms_total for c in loudness_candidates)
        peak_max = max(c.peak_total for c in loudness_candidates)
        crest_min = min(c.crest_factor for c in loudness_candidates)
        # DC offset: tomar el peor (máximo absoluto)
        dc_worst = max(loudness_candidates, key=lambda c: abs(c.dc_offset)).dc_offset
        merged_loudness = {
            "lufs": lufs_max,
            "true_peak": tp_max,
            "lra": lra_min,
            "rms_total": rms_max,
            "peak_total": peak_max,
            "crest_factor": crest_min,
            "dc_offset": dc_worst,
        }

    tempo_candidates = [c for c in all_chars if getattr(c, "tempo_bpm", None)]
    merged_tempo: dict | None = None
    if tempo_candidates:
        bpms = sorted(float(c.tempo_bpm) for c in tempo_candidates if c.tempo_bpm is not None)
        mid = len(bpms) // 2
        bpm_median = bpms[mid] if len(bpms) % 2 == 1 else (bpms[mid - 1] + bpms[mid]) / 2.0
        conf_avg = sum(float(getattr(c, "tempo_confidence", 0.0)) for c in tempo_candidates) / len(tempo_candidates)
        pulse_avg = sum(float(getattr(c, "pulse_clarity", 0.0)) for c in tempo_candidates) / len(tempo_candidates)
        merged_tempo = {
            "bpm": bpm_median,
            "confidence": conf_avg,
            "pulse_clarity": pulse_avg,
            "source": "batch_median",
        }

    return AudioCharacteristics(
        band_stats=merged_band_stats,
        voice_rms=merged_voice_rms,
        clipping_info=merged_clipping,
        noise_info=merged_noise,
        stereo_info=merged_stereo,
        band_peaks=merged_band_peaks,
        silence_info=merged_silence,
        loudness_metrics=merged_loudness,
        tempo_info=merged_tempo,
    )


def update_saturation_budgets_for_batch(
    individual_results: Dict[str, Any],
    adjustments: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Actualiza los presupuestos de saturación para cada archivo del lote.
    
    Esta función debe llamarse DESPUÉS de adapt_preset_to_audio() para
    calcular el THD estimado con los ajustes aplicados.
    
    Args:
        individual_results: Resultados individuales del análisis
        adjustments: Ajustes del preset adaptado
        
    Returns:
        individual_results actualizado con saturation_budget por archivo
    """
    for file_path, result in individual_results.items():
        chars = result["characteristics"]
        budget = _calculate_saturation_budget(chars, adjustments)
        result["saturation_budget"] = budget
    
    return individual_results
