"""
Herramientas alternativas de audio para complementar FFmpeg.

Este módulo proporciona funciones para usar herramientas externas
como SoX, LSP Plugins, Pedalboard, etc. cuando están disponibles, 
con fallback a FFmpeg.
"""
# pyright: reportOptionalCall=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportPrivateImportUsage=false
# pyright: reportAttributeAccessIssue=false

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional, Tuple, List, Any

# Intentar importar pedalboard (opcional)
try:
    import pedalboard  # type: ignore
    from pedalboard import (  # type: ignore
        Pedalboard, Compressor, Gain, Limiter,
        HighpassFilter, LowpassFilter, HighShelfFilter, LowShelfFilter,
        PeakFilter, NoiseGate, Clipping
    )
    from pedalboard.io import AudioFile  # type: ignore
    PEDALBOARD_AVAILABLE = True
except ImportError:
    PEDALBOARD_AVAILABLE = False
    # Dummy variables para evitar errores de tipo
    pedalboard = None  # type: ignore
    Pedalboard = Compressor = Gain = Limiter = None  # type: ignore
    HighpassFilter = LowpassFilter = HighShelfFilter = LowShelfFilter = None  # type: ignore
    PeakFilter = NoiseGate = Clipping = AudioFile = None  # type: ignore

# Intentar importar numpy (requerido para pedalboard)
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None  # type: ignore

# Intentar importar essentia (opcional - para verificación de True Peak)
try:
    import essentia.standard as essentia_std  # type: ignore
    ESSENTIA_AVAILABLE = True
except ImportError:
    ESSENTIA_AVAILABLE = False
    essentia_std = None  # type: ignore

# Intentar importar soundfile (opcional - para I/O eficiente)
try:
    import soundfile as sf  # type: ignore
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False
    sf = None  # type: ignore


@dataclass
class LoudnessStats:
    """Estadísticas de loudness medidas."""
    input_i: float  # Integrated LUFS
    input_tp: float  # True Peak dBTP
    input_lra: float  # Loudness Range
    input_thresh: float  # Threshold
    target_offset: float  # Offset calculado


def is_tool_available(tool_name: str) -> bool:
    """Verificar si una herramienta está disponible en el sistema."""
    return shutil.which(tool_name) is not None


def get_available_tools() -> dict:
    """Obtener diccionario de herramientas disponibles."""
    tools = {
        'ffmpeg': is_tool_available('ffmpeg'),
        'sox': is_tool_available('sox'),
        'carla-single': is_tool_available('carla-single'),
        'ebumeter': is_tool_available('ebumeter'),
        'pedalboard': PEDALBOARD_AVAILABLE,
        'essentia': ESSENTIA_AVAILABLE,
        'soundfile': SOUNDFILE_AVAILABLE,
    }
    return tools


def is_pedalboard_available() -> bool:
    """Verificar si pedalboard está disponible."""
    return PEDALBOARD_AVAILABLE and NUMPY_AVAILABLE


def analyze_loudness_ffmpeg(input_path: str) -> Optional[LoudnessStats]:
    """
    Analizar loudness de un archivo usando FFmpeg.
    
    Esta es la primera pasada de un proceso de dos pasadas para
    obtener estadísticas reales del audio.
    """
    cmd = [
        'ffmpeg', '-hide_banner', '-i', input_path,
        '-af', 'loudnorm=print_format=json',
        '-f', 'null', '-'
    ]
    
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=120
        )
        
        # El JSON está en stderr de FFmpeg
        output = result.stderr
        
        # Buscar el bloque JSON
        json_start = output.rfind('{')
        json_end = output.rfind('}') + 1
        
        if json_start == -1 or json_end <= json_start:
            print(f"[DEBUG] No se encontró JSON en la salida de loudnorm")
            return None
            
        json_str = output[json_start:json_end]
        data = json.loads(json_str)
        
        return LoudnessStats(
            input_i=float(data.get('input_i', -24)),
            input_tp=float(data.get('input_tp', -1)),
            input_lra=float(data.get('input_lra', 7)),
            input_thresh=float(data.get('input_thresh', -30)),
            target_offset=float(data.get('target_offset', 0))
        )
        
    except subprocess.TimeoutExpired:
        print("[ERROR] Timeout al analizar loudness")
        return None
    except json.JSONDecodeError as e:
        print(f"[ERROR] Error parseando JSON de loudnorm: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Error analizando loudness: {e}")
        return None


def build_loudnorm_two_pass(
    stats: LoudnessStats,
    target_lufs: float = -14.0,
    target_tp: float = -1.5,
    target_lra: float = 11.0
) -> str:
    """
    Construir filtro loudnorm con estadísticas medidas (segunda pasada).
    
    linear=true calcula automáticamente el offset como target - measured_I.
    No pasamos offset explícito para evitar duplicar la ganancia.
    """
    return (
        f"loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}:"
        f"measured_I={stats.input_i}:"
        f"measured_TP={stats.input_tp}:"
        f"measured_LRA={stats.input_lra}:"
        f"measured_thresh={stats.input_thresh}:"
        f"offset=0:"
        f"linear=true:print_format=summary"
    )


def resample_with_sox(
    input_path: str, 
    output_path: str, 
    sample_rate: int,
    quality: str = 'very-high'
) -> bool:
    """
    Resample audio usando SoX (mayor calidad que FFmpeg aresample).
    
    Args:
        input_path: Archivo de entrada
        output_path: Archivo de salida
        sample_rate: Frecuencia de muestreo objetivo
        quality: 'low', 'medium', 'high', 'very-high'
    
    Returns:
        True si tuvo éxito
    """
    if not is_tool_available('sox'):
        print("[WARN] SoX no disponible, usando FFmpeg para resampling")
        return False
    
    quality_flags = {
        'low': ['-q'],
        'medium': ['-m'],
        'high': ['-h'],
        'very-high': ['-v', '-H'],  # -v = very high, -H = steep filter
    }
    
    flags = quality_flags.get(quality, ['-v', '-H'])
    
    cmd = ['sox', input_path, output_path, 'rate'] + flags + [str(sample_rate)]
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        return result.returncode == 0
    except Exception as e:
        print(f"[ERROR] SoX resample falló: {e}")
        return False


def normalize_with_sox(
    input_path: str,
    output_path: str,
    headroom_db: float = -1.0
) -> bool:
    """
    Normalizar audio usando SoX.
    
    Args:
        input_path: Archivo de entrada
        output_path: Archivo de salida
        headroom_db: Nivel máximo en dB (ej: -1.0 para -1 dB headroom)
    
    Returns:
        True si tuvo éxito
    """
    if not is_tool_available('sox'):
        return False
    
    # 'gain -n' normaliza al pico, luego aplicamos headroom
    cmd = ['sox', input_path, output_path, 'gain', '-n', str(headroom_db)]
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        return result.returncode == 0
    except Exception as e:
        print(f"[ERROR] SoX normalize falló: {e}")
        return False


def apply_limiter_sox(
    input_path: str,
    output_path: str,
    threshold_db: float = -1.0,
    attack_ms: float = 0.1,
    release_ms: float = 100.0
) -> bool:
    """
    Aplicar limiter usando SoX compand.
    
    Nota: SoX compand no es un true-peak limiter, pero puede
    servir como capa adicional de protección.
    """
    if not is_tool_available('sox'):
        return False
    
    # Configurar compand como limiter
    attack_s = attack_ms / 1000.0
    release_s = release_ms / 1000.0
    
    # Formato: attack,decay soft-knee:threshold:ratio
    # Para limiter usamos ratio infinito (represado por threshold alto)
    transfer = f"-90,-90,{threshold_db},{threshold_db}"
    
    cmd = [
        'sox', input_path, output_path,
        'compand', f'{attack_s},{release_s}', transfer, '0', str(threshold_db)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        return result.returncode == 0
    except Exception as e:
        print(f"[ERROR] SoX limiter falló: {e}")
        return False


def get_best_resampler() -> str:
    """Obtener el mejor resampler disponible."""
    if is_tool_available('sox'):
        return 'sox'
    return 'ffmpeg'


def get_best_limiter() -> str:
    """Obtener el mejor limiter disponible."""
    # Por ahora solo FFmpeg, pero preparado para expansión
    if is_tool_available('carla-single'):
        # Podría usar LSP Limiter via Carla
        return 'lsp'
    return 'ffmpeg'


# =============================================================================
# FUNCIONES DE PEDALBOARD
# =============================================================================

def process_with_pedalboard(
    input_path: str,
    output_path: str,
    highpass_hz: float = 0,
    lowpass_hz: float = 0,
    compress_threshold: float = 0,
    compress_ratio: float = 1.0,
    compress_attack_ms: float = 10.0,
    compress_release_ms: float = 100.0,
    makeup_gain_db: float = 0,
    noise_gate_threshold: float = -100,
) -> bool:
    """
    Procesa audio usando Pedalboard (más rápido que FFmpeg para algunos filtros).
    
    NOTA: No incluye True Peak limiting - usar FFmpeg loudnorm después.
    
    Args:
        input_path: Archivo de entrada
        output_path: Archivo de salida
        highpass_hz: Frecuencia de corte highpass (0 = desactivado)
        lowpass_hz: Frecuencia de corte lowpass (0 = desactivado)
        compress_threshold: Threshold del compresor en dB (0 = desactivado)
        compress_ratio: Ratio de compresión (1.0 = sin compresión)
        compress_attack_ms: Attack del compresor en ms
        compress_release_ms: Release del compresor en ms
        makeup_gain_db: Ganancia de maquillaje en dB (0 = sin ganancia)
        noise_gate_threshold: Threshold del noise gate en dB (-100 = desactivado)
    
    Returns:
        True si tuvo éxito
    """
    if not is_pedalboard_available():
        print("[WARN] Pedalboard no disponible")
        return False
    
    try:
        # Leer audio
        with AudioFile(input_path) as f:
            audio = f.read(f.frames)
            sample_rate = f.samplerate
            num_channels = f.num_channels
        
        # Construir cadena de procesamiento
        effects: List = []
        
        # Noise Gate (primero)
        if noise_gate_threshold > -100:
            effects.append(NoiseGate(threshold_db=noise_gate_threshold))
        
        # Highpass filter
        if highpass_hz > 0:
            effects.append(HighpassFilter(cutoff_frequency_hz=highpass_hz))
        
        # Lowpass filter
        if lowpass_hz > 0 and lowpass_hz < sample_rate / 2:
            effects.append(LowpassFilter(cutoff_frequency_hz=lowpass_hz))
        
        # Compresor
        if compress_ratio > 1.0:
            effects.append(Compressor(
                threshold_db=compress_threshold,
                ratio=compress_ratio,
                attack_ms=compress_attack_ms,
                release_ms=compress_release_ms,
            ))
        
        # Makeup gain
        if abs(makeup_gain_db) > 0.1:
            effects.append(Gain(gain_db=makeup_gain_db))
        
        if not effects:
            # Sin efectos, solo copiar
            import shutil
            shutil.copy2(input_path, output_path)
            return True
        
        # Crear cadena y procesar
        board = Pedalboard(effects)
        processed = board(audio, sample_rate)
        
        # Guardar
        with AudioFile(output_path, 'w', sample_rate, num_channels) as f:
            f.write(processed)
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Pedalboard processing failed: {e}")
        return False


def apply_eq_pedalboard(
    input_path: str,
    output_path: str,
    low_shelf_gain_db: float = 0,
    low_shelf_freq: float = 100,
    high_shelf_gain_db: float = 0,
    high_shelf_freq: float = 8000,
    peak_gains: Optional[List[Tuple[float, float, float]]] = None,
) -> bool:
    """
    Aplicar EQ usando Pedalboard.
    
    Args:
        input_path: Archivo de entrada
        output_path: Archivo de salida
        low_shelf_gain_db: Ganancia del shelf bajo en dB
        low_shelf_freq: Frecuencia del shelf bajo en Hz
        high_shelf_gain_db: Ganancia del shelf alto en dB
        high_shelf_freq: Frecuencia del shelf alto en Hz
        peak_gains: Lista de (freq_hz, gain_db, q) para bandas paramétricas
    
    Returns:
        True si tuvo éxito
    """
    if not is_pedalboard_available():
        return False
    
    try:
        with AudioFile(input_path) as f:
            audio = f.read(f.frames)
            sample_rate = f.samplerate
            num_channels = f.num_channels
        
        effects: List = []
        
        # Low shelf
        if abs(low_shelf_gain_db) > 0.1:
            effects.append(LowShelfFilter(
                cutoff_frequency_hz=low_shelf_freq,
                gain_db=low_shelf_gain_db,
            ))
        
        # High shelf
        if abs(high_shelf_gain_db) > 0.1:
            effects.append(HighShelfFilter(
                cutoff_frequency_hz=high_shelf_freq,
                gain_db=high_shelf_gain_db,
            ))
        
        # Peak filters (paramétrico)
        if peak_gains:
            for freq, gain, q in peak_gains:
                if abs(gain) > 0.1:
                    effects.append(PeakFilter(
                        cutoff_frequency_hz=freq,
                        gain_db=gain,
                        q=q,
                    ))
        
        if not effects:
            import shutil
            shutil.copy2(input_path, output_path)
            return True
        
        board = Pedalboard(effects)
        processed = board(audio, sample_rate)
        
        with AudioFile(output_path, 'w', sample_rate, num_channels) as f:
            f.write(processed)
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Pedalboard EQ failed: {e}")
        return False


def load_vst3_plugin(plugin_path: str) -> Optional[object]:
    """
    Cargar un plugin VST3 usando Pedalboard.
    
    Args:
        plugin_path: Ruta al archivo .vst3
    
    Returns:
        Objeto del plugin o None si falla
    """
    if not is_pedalboard_available():
        return None
    
    try:
        from pedalboard import load_plugin
        plugin = load_plugin(plugin_path)
        return plugin
    except Exception as e:
        print(f"[ERROR] Failed to load VST3 plugin: {e}")
        return None


def list_vst3_plugins(search_paths: Optional[List[str]] = None) -> List[str]:
    """
    Listar plugins VST3 disponibles en el sistema.
    
    Returns:
        Lista de rutas a plugins VST3 encontrados
    """
    if search_paths is None:
        search_paths = [
            '/usr/lib/vst3',
            '/usr/local/lib/vst3',
            os.path.expanduser('~/.vst3'),
        ]
    
    plugins = []
    for path in search_paths:
        if os.path.exists(path):
            for item in os.listdir(path):
                if item.endswith('.vst3'):
                    plugins.append(os.path.join(path, item))
    
    return plugins


def get_pedalboard_info() -> dict:
    """
    Obtener información sobre Pedalboard y plugins disponibles.
    
    Returns:
        Diccionario con información
    """
    info = {
        'available': is_pedalboard_available(),
        'version': None,
        'builtin_plugins': [],
        'vst3_plugins': [],
    }
    
    if is_pedalboard_available():
        info['version'] = getattr(pedalboard, '__version__', 'unknown')
        # Listar plugins incluidos
        info['builtin_plugins'] = [
            'Compressor', 'Limiter', 'Gain', 'NoiseGate',
            'HighpassFilter', 'LowpassFilter', 
            'HighShelfFilter', 'LowShelfFilter', 'PeakFilter',
            'Chorus', 'Delay', 'Distortion', 'Phaser', 'Reverb',
            'Clipping', 'Bitcrush', 'Convolution', 'Resample',
        ]
        info['vst3_plugins'] = list_vst3_plugins()
    
    return info


class AudioToolchain:
    """
    Cadena de herramientas de audio que selecciona automáticamente
    las mejores herramientas disponibles.
    """
    
    def __init__(self):
        self.tools = get_available_tools()
        self.resampler = get_best_resampler()
        self.limiter = get_best_limiter()
        self.pedalboard_info = get_pedalboard_info()
        
    def log_available_tools(self) -> str:
        """Generar log de herramientas disponibles."""
        lines = ["=== Herramientas de Audio ==="]
        for tool, available in self.tools.items():
            status = "✓" if available else "✗"
            lines.append(f"  {status} {tool}")
        lines.append(f"  Resampler preferido: {self.resampler}")
        lines.append(f"  Limiter preferido: {self.limiter}")
        
        if self.pedalboard_info['available']:
            lines.append(f"  Pedalboard versión: {self.pedalboard_info['version']}")
            if self.pedalboard_info['vst3_plugins']:
                lines.append(f"  VST3 plugins: {len(self.pedalboard_info['vst3_plugins'])}")
        
        return "\n".join(lines)
    
    def resample(
        self, 
        input_path: str, 
        output_path: str, 
        sample_rate: int
    ) -> bool:
        """Resample usando la mejor herramienta disponible."""
        if self.resampler == 'sox':
            success = resample_with_sox(input_path, output_path, sample_rate)
            if success:
                return True
            print("[WARN] SoX falló, intentando con FFmpeg")
        
        # Fallback a FFmpeg
        cmd = [
            'ffmpeg', '-hide_banner', '-y',
            '-i', input_path,
            '-af', f'aresample=resampler=soxr:precision=33:osr={sample_rate}',
            output_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            return result.returncode == 0
        except Exception:
            return False
    
    def two_pass_normalize(
        self,
        input_path: str,
        output_path: str,
        target_lufs: float = -14.0,
        target_tp: float = -1.5,
        target_lra: float = 11.0
    ) -> Tuple[bool, Optional[LoudnessStats]]:
        """
        Normalización de dos pasadas para máxima precisión.
        
        Returns:
            Tuple de (éxito, estadísticas medidas)
        """
        # Pasada 1: Analizar
        print("[INFO] Pasada 1: Analizando loudness...")
        stats = analyze_loudness_ffmpeg(input_path)
        
        if not stats:
            print("[WARN] No se pudieron obtener estadísticas, usando loudnorm estándar")
            # Fallback a loudnorm de una pasada
            cmd = [
                'ffmpeg', '-hide_banner', '-y',
                '-i', input_path,
                '-af', f'loudnorm=I={target_lufs}:TP={target_tp}:LRA={target_lra}',
                output_path
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                return result.returncode == 0, None
            except Exception:
                return False, None
        
        print(f"[INFO] Estadísticas medidas: LUFS={stats.input_i:.1f}, TP={stats.input_tp:.1f}")
        
        # Pasada 2: Aplicar con estadísticas medidas
        print("[INFO] Pasada 2: Aplicando normalización precisa...")
        loudnorm_filter = build_loudnorm_two_pass(
            stats, target_lufs, target_tp, target_lra
        )
        
        cmd = [
            'ffmpeg', '-hide_banner', '-y',
            '-i', input_path,
            '-af', loudnorm_filter,
            output_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            return result.returncode == 0, stats
        except Exception as e:
            print(f"[ERROR] Normalización falló: {e}")
            return False, stats


def install_recommendations() -> str:
    """Generar recomendaciones de instalación."""
    tools = get_available_tools()
    
    recommendations = []
    
    if not tools['sox']:
        recommendations.append(
            "SoX (resampling de alta calidad):\n"
            "  sudo apt install sox libsox-fmt-all"
        )
    
    if not tools['carla-single']:
        recommendations.append(
            "Carla + LSP Plugins (limiters profesionales):\n"
            "  sudo apt install carla lsp-plugins-vst3"
        )
    
    if not tools.get('pedalboard', False):
        recommendations.append(
            "Pedalboard (procesamiento Python rápido + VST3):\n"
            "  pip install pedalboard"
        )
    
    if not tools.get('essentia', False):
        recommendations.append(
            "Essentia (verificación True Peak + análisis LUFS):\n"
            "  pip install essentia"
        )
    
    if not tools.get('soundfile', False):
        recommendations.append(
            "SoundFile (I/O de audio eficiente):\n"
            "  pip install soundfile"
        )
    
    if not recommendations:
        return "✓ Todas las herramientas recomendadas están instaladas"
    
    return "Herramientas recomendadas para mejorar la calidad:\n\n" + "\n\n".join(recommendations)


# =============================================================================
# ESSENTIA: Verificación de True Peak y Loudness
# =============================================================================

def is_essentia_available() -> bool:
    """Verificar si essentia está disponible."""
    return ESSENTIA_AVAILABLE


def measure_true_peak_essentia(
    input_path: str,
    oversampling_factor: int = 4,
) -> Optional[float]:
    """
    Medir True Peak usando Essentia (más preciso que sample peak).
    
    Args:
        input_path: Ruta al archivo de audio
        oversampling_factor: Factor de oversampling (4 es estándar ITU-R BS.1770)
    
    Returns:
        True Peak en dBTP, o None si falla
    """
    if not ESSENTIA_AVAILABLE or not NUMPY_AVAILABLE:
        return None
    
    try:
        # Cargar audio (mono para análisis)
        loader = essentia_std.MonoLoader(filename=input_path)
        audio = loader()
        
        # Obtener sample rate del archivo
        info = essentia_std.MetadataReader(filename=input_path)()
        sample_rate = int(info[10]) if info[10] else 44100
        
        # Detectar True Peak
        tpd = essentia_std.TruePeakDetector(
            sampleRate=sample_rate,
            oversamplingFactor=oversampling_factor,
            quality=1
        )
        _, upsampled = tpd(audio)
        
        # Calcular True Peak en dB
        true_peak_linear = float(np.max(np.abs(upsampled)))
        if true_peak_linear > 0:
            true_peak_db = 20 * np.log10(true_peak_linear)
        else:
            true_peak_db = -float('inf')
        
        return true_peak_db
    
    except Exception as e:
        print(f"[Essentia] Error midiendo True Peak: {e}")
        return None


def measure_loudness_essentia(
    input_path: str,
) -> Optional[Tuple[float, float]]:
    """
    Medir Loudness EBU R128 usando Essentia.
    
    Args:
        input_path: Ruta al archivo de audio
    
    Returns:
        Tupla (integrated_lufs, loudness_range) o None si falla
    """
    if not ESSENTIA_AVAILABLE:
        return None
    
    try:
        # Cargar audio (stereo para loudness)
        loader = essentia_std.AudioLoader(filename=input_path)
        audio, sample_rate, channels, md5, bitrate, codec = loader()
        
        # Medir loudness
        loudness = essentia_std.LoudnessEBUR128(
            sampleRate=sample_rate,
            startAtZero=True
        )
        momentary, short_term, integrated, lra = loudness(audio)
        
        # Validar resultados (evitar inf o valores inválidos)
        if not np.isfinite(integrated) or integrated < -100 or integrated > 10:
            return None
        if not np.isfinite(lra) or lra < 0 or lra > 50:
            lra = 0.0
        
        return (float(integrated), float(lra))
    
    except Exception as e:
        print(f"[Essentia] Error midiendo loudness: {e}")
        return None


def verify_true_peak(
    audio_path: str,
    target_true_peak: float,
    tolerance: float = 0.1,
) -> Tuple[bool, float, str]:
    """
    Verificar que el True Peak del audio no exceda el objetivo.
    
    Args:
        audio_path: Ruta al archivo procesado
        target_true_peak: True Peak objetivo (ej: -1.0 dBTP)
        tolerance: Tolerancia permitida (ej: 0.1 dB)
    
    Returns:
        Tupla (cumple_objetivo, true_peak_medido, mensaje)
    """
    # Intentar con Essentia primero (más preciso)
    if ESSENTIA_AVAILABLE:
        measured_tp = measure_true_peak_essentia(audio_path)
        method = "Essentia"
    else:
        # Fallback a FFmpeg
        measured_tp = _measure_true_peak_ffmpeg(audio_path)
        method = "FFmpeg"
    
    if measured_tp is None:
        return (False, 0.0, "Error midiendo True Peak")
    
    passes = measured_tp <= (target_true_peak + tolerance)
    
    if passes:
        msg = f"✅ True Peak OK: {measured_tp:+.2f} dBTP ≤ {target_true_peak:+.1f} dBTP ({method})"
    else:
        excess = measured_tp - target_true_peak
        msg = f"⚠️ True Peak EXCEDE: {measured_tp:+.2f} dBTP > {target_true_peak:+.1f} dBTP (+{excess:.2f} dB) ({method})"
    
    return (passes, measured_tp, msg)


def _measure_true_peak_ffmpeg(input_path: str) -> Optional[float]:
    """Medir True Peak usando FFmpeg ebur128 (fallback)."""
    import re
    
    cmd = [
        'ffmpeg', '-hide_banner', '-i', input_path,
        '-af', 'ebur128=peak=true', '-f', 'null', '-'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        # Buscar en el Summary
        output = result.stderr
        tp_match = re.search(r'Peak:\s*([-+]?\d+\.?\d*)\s*dBFS', output)
        if tp_match:
            return float(tp_match.group(1))
    except Exception:
        pass
    
    return None


# Instancia global para uso fácil
toolchain = AudioToolchain()


if __name__ == "__main__":
    # Test
    print(toolchain.log_available_tools())
    print()
    print(install_recommendations())
