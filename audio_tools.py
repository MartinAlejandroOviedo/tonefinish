import json
import os
import shutil
import time
import subprocess
import threading
from array import array
from typing import Dict, List, Optional, Any, Tuple


# Caché en memoria para evitar llamadas repetidas a FFprobe en la misma sesión
_audio_info_cache: Dict[str, Dict] = {}


def _read_int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


_CPU_COUNT = max(1, os.cpu_count() or 1)
_DEFAULT_MAX_FFMPEG_PROCS = max(1, min(3, (_CPU_COUNT + 1) // 2))
_MAX_FFMPEG_PROCS = _read_int_env(
    "TONEFINISH_MAX_FFMPEG_PROCS",
    _DEFAULT_MAX_FFMPEG_PROCS,
    1,
    8,
)
_DEFAULT_FFMPEG_THREADS = max(1, min(4, _CPU_COUNT // _MAX_FFMPEG_PROCS))
_FFMPEG_THREADS = _read_int_env(
    "TONEFINISH_FFMPEG_THREADS",
    _DEFAULT_FFMPEG_THREADS,
    1,
    max(1, _CPU_COUNT),
)
_FFMPEG_SEMAPHORE = threading.BoundedSemaphore(_MAX_FFMPEG_PROCS)
_RUNNING_FFMPEG_PROCS: set[subprocess.Popen[str]] = set()
_RUNNING_FFMPEG_LOCK = threading.Lock()
_FFMPEG_RETRY_ATTEMPTS = _read_int_env("TONEFINISH_FFMPEG_RETRY_ATTEMPTS", 2, 0, 5)
_FFMPEG_RETRY_BASE_DELAY_SEC = max(
    0.0,
    min(2.0, float(os.getenv("TONEFINISH_FFMPEG_RETRY_BASE_DELAY_SEC", "0.35") or "0.35")),
)
_FFMPEG_BIN = os.getenv("FINISHER_FFMPEG_BIN", "").strip()
if not _FFMPEG_BIN:
    import shutil
    _ffmpeg_spasm_path = shutil.which("ffmpeg-spasm")
    _FFMPEG_BIN = _ffmpeg_spasm_path if _ffmpeg_spasm_path else "ffmpeg"
_FFPROBE_BIN_ENV = os.getenv("FINISHER_FFPROBE_BIN", "").strip()
if _FFPROBE_BIN_ENV:
    _FFPROBE_BIN = _FFPROBE_BIN_ENV
else:
    _ffmpeg_base = os.path.basename(_FFMPEG_BIN)
    if _ffmpeg_base in ("ffmpeg", "ffmpeg-spasm"):
        _FFPROBE_BIN = os.path.join(os.path.dirname(_FFMPEG_BIN), "ffprobe") if os.path.dirname(_FFMPEG_BIN) else "ffprobe"
    else:
        _FFPROBE_BIN = "ffprobe"


def _fallback_ffmpeg_bin() -> str | None:
    """Retorna un binario ffmpeg alternativo estable, si existe."""
    candidates = [
        "/usr/bin/ffmpeg.real-spasm-backup",
        "/usr/local/bin/ffmpeg.real-spasm-backup",
        "/usr/bin/ffmpeg",
        shutil.which("ffmpeg"),
    ]
    current = os.path.realpath(_FFMPEG_BIN)
    for cand in candidates:
        if not cand:
            continue
        try:
            resolved = os.path.realpath(cand)
        except Exception:
            resolved = cand
        if resolved and resolved != current and os.path.exists(resolved):
            return resolved
    return None


def _is_spasm_executor_error(stderr: str) -> bool:
    text = (stderr or "").lower()
    return (
        "ffmpeg-spasm:" in text
        or "native spasm" in text
        or "spasm wav af chain executor failed" in text
    )


def _rerun_with_fallback_ffmpeg(
    completed: subprocess.CompletedProcess[str],
    *,
    verbose: bool,
    optimize: bool,
) -> subprocess.CompletedProcess[str]:
    if completed.returncode == 0 or not _is_spasm_executor_error(completed.stderr):
        return completed
    alt_ffmpeg = _fallback_ffmpeg_bin()
    if not alt_ffmpeg:
        return completed
    retry_cmd = list(completed.args)
    if not retry_cmd:
        return completed
    retry_cmd[0] = alt_ffmpeg
    if verbose:
        print("Retry ffmpeg fallback:", " ".join(retry_cmd))
    return subprocess.run(
        retry_cmd,
        text=True,
        capture_output=True,
        check=False,
    )


def _is_transient_resource_error(stderr: str) -> bool:
    text = (stderr or "").lower()
    patterns = (
        "resource temporarily unavailable",
        "cannot allocate memory",
        "out of memory",
        "device or resource busy",
        "too many open files",
        "pthread_create failed",
        "temporarily unavailable",
        "no space left on device",
        "error writing trailer",
    )
    return any(p in text for p in patterns)


def _run_with_ffmpeg_retries(cmd: List[str]) -> subprocess.CompletedProcess[str]:
    max_tries = max(1, _FFMPEG_RETRY_ATTEMPTS + 1)
    last: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, max_tries + 1):
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        with _RUNNING_FFMPEG_LOCK:
            _RUNNING_FFMPEG_PROCS.add(process)
        try:
            stdout, stderr = process.communicate()
        finally:
            with _RUNNING_FFMPEG_LOCK:
                _RUNNING_FFMPEG_PROCS.discard(process)
        result = subprocess.CompletedProcess(
            args=cmd,
            # Preserve negative return codes (e.g. SIGABRT=-6, SIGSEGV=-11).
            # Using `or 0` masks fatal ffmpeg crashes as success.
            returncode=process.returncode if process.returncode is not None else 1,
            stdout=stdout or "",
            stderr=stderr or "",
        )
        last = result
        if result.returncode == 0:
            return result
        if "no space left on device" in (result.stderr or "").lower():
            _ensure_tmp_space(min_free_mb=500)  # clean more aggressively
        if attempt >= max_tries or not _is_transient_resource_error(result.stderr):
            return result
        time.sleep(_FFMPEG_RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1)))
    return last if last is not None else subprocess.CompletedProcess(cmd, 1, "", "")


def cancel_running_ffmpeg_processes() -> int:
    """Intenta terminar procesos ffmpeg activos y retorna cuántos fueron señalados."""
    with _RUNNING_FFMPEG_LOCK:
        procs = list(_RUNNING_FFMPEG_PROCS)
    cancelled = 0
    for proc in procs:
        if proc.poll() is not None:
            continue
        cancelled += 1
        try:
            proc.terminate()
        except Exception:
            pass
    if cancelled > 0:
        time.sleep(0.8)
    for proc in procs:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
    return cancelled


def get_processing_limits() -> Dict[str, int]:
    """Retorna límites efectivos de recursos para procesamiento."""
    return {
        "cpu_count": _CPU_COUNT,
        "max_ffmpeg_processes": _MAX_FFMPEG_PROCS,
        "ffmpeg_threads_per_process": _FFMPEG_THREADS,
    }


def set_processing_limits(max_ffmpeg_processes: int | None = None, ffmpeg_threads_per_process: int | None = None) -> Dict[str, int]:
    """Ajusta límites globales de FFmpeg para la sesión actual."""
    global _MAX_FFMPEG_PROCS, _FFMPEG_THREADS, _FFMPEG_SEMAPHORE

    new_max_procs = _MAX_FFMPEG_PROCS if max_ffmpeg_processes is None else max(1, min(8, int(max_ffmpeg_processes)))
    new_threads = _FFMPEG_THREADS if ffmpeg_threads_per_process is None else max(1, min(max(1, _CPU_COUNT), int(ffmpeg_threads_per_process)))

    _MAX_FFMPEG_PROCS = new_max_procs
    _FFMPEG_THREADS = new_threads
    _FFMPEG_SEMAPHORE = threading.BoundedSemaphore(_MAX_FFMPEG_PROCS)
    return get_processing_limits()


def _prepare_ffmpeg_cmd(cmd: List[str], optimize: bool) -> List[str]:
    if not cmd:
        return cmd
    if cmd[0] == "ffmpeg":
        cmd = [_FFMPEG_BIN, *cmd[1:]]
    elif cmd[0] == "ffprobe":
        cmd = [_FFPROBE_BIN, *cmd[1:]]
    if not optimize or cmd[0] != _FFMPEG_BIN:
        return cmd
    if "-threads" in cmd:
        return cmd
    return [cmd[0], "-threads", str(_FFMPEG_THREADS), *cmd[1:]]


def get_audio_info(input_path: str, use_cache: bool = True) -> Dict[str, Any]:
    """
    Obtiene toda la información del archivo de audio en UNA sola llamada a FFprobe.
    
    Retorna: {
        'duration': float,      # Duración en segundos
        'sample_rate': int,     # Sample rate en Hz
        'channels': int,        # Número de canales
        'bit_depth': int,       # Bits por sample (si disponible)
        'codec': str,           # Codec de audio
        'format': str,          # Formato contenedor
        'bitrate': int,         # Bitrate en bps (si disponible)
    }
    """
    # Verificar caché
    if use_cache and input_path in _audio_info_cache:
        return _audio_info_cache[input_path]
    
    cmd = [
        _FFPROBE_BIN,
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate,channels,bits_per_sample,codec_name:format=duration,format_name,bit_rate",
        "-of", "json",
        input_path,
    ]
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    
    info: Dict[str, Optional[float | int | str]] = {
        'duration': None,
        'sample_rate': None,
        'channels': None,
        'bit_depth': None,
        'codec': None,
        'format': None,
        'bitrate': None,
    }
    
    if result.returncode != 0:
        return info
    
    try:
        data = json.loads(result.stdout)
        
        # Extraer info del stream
        if 'streams' in data and data['streams']:
            stream = data['streams'][0]
            if 'sample_rate' in stream:
                info['sample_rate'] = int(stream['sample_rate'])
            if 'channels' in stream:
                info['channels'] = int(stream['channels'])
            if 'bits_per_sample' in stream and stream['bits_per_sample']:
                info['bit_depth'] = int(stream['bits_per_sample'])
            if 'codec_name' in stream:
                info['codec'] = stream['codec_name']
        
        # Extraer info del formato
        if 'format' in data:
            fmt = data['format']
            if 'duration' in fmt:
                info['duration'] = float(fmt['duration'])
            if 'format_name' in fmt:
                info['format'] = fmt['format_name']
            if 'bit_rate' in fmt and fmt['bit_rate']:
                info['bitrate'] = int(fmt['bit_rate'])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        pass
    
    # Guardar en caché
    if use_cache:
        _audio_info_cache[input_path] = info
    
    return info


def clear_audio_info_cache() -> None:
    """Limpia el caché de información de audio."""
    global _audio_info_cache
    _audio_info_cache.clear()


def _ensure_tmp_space(min_free_mb: int = 100) -> None:
    """Limpia archivos temporales WAV en /tmp si el espacio libre es bajo."""
    try:
        stat = os.statvfs("/tmp")
        free_mb = (stat.f_bavail * stat.f_frsize) // (1024 * 1024)
        if free_mb >= min_free_mb:
            return
    except OSError:
        return

    import glob as _glob
    import time as _time

    now = _time.time()
    # Limpiar WAVs temporales más viejos que 5 minutos
    patterns = ["/tmp/tmp*.wav", "/tmp/tonefinish*.wav", "/tmp/finisher*.wav"]
    removed = 0
    for pat in patterns:
        for f in _glob.glob(pat):
            try:
                if now - os.path.getmtime(f) > 300:
                    os.remove(f)
                    removed += 1
            except OSError:
                pass
    if removed:
        pass  # silent cleanup


def run_ffmpeg(cmd: List[str], verbose: bool = False, optimize: bool = True) -> subprocess.CompletedProcess[str]:
    """
    Ejecuta ffmpeg/ffprobe devolviendo stdout y stderr en texto.
    
    Args:
        cmd: Comando FFmpeg/FFprobe a ejecutar
        verbose: Si True, imprime el comando
        optimize: Si True, agrega flags de optimización automáticamente
    """
    _ensure_tmp_space()
    cmd = _prepare_ffmpeg_cmd(cmd, optimize)
    
    if verbose:
        print(" ".join(cmd))
    if cmd and cmd[0] == _FFMPEG_BIN:
        _FFMPEG_SEMAPHORE.acquire()
        try:
            result = _run_with_ffmpeg_retries(cmd)
        finally:
            _FFMPEG_SEMAPHORE.release()
        return _rerun_with_fallback_ffmpeg(result, verbose=verbose, optimize=optimize)

    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
    )


def run_ffmpeg_with_progress(
    cmd: List[str],
    duration_seconds: float,
    progress_callback=None,
    verbose: bool = False,
    optimize: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Ejecuta FFmpeg con reporte de progreso en tiempo real (CORREGIDO v2 - MÁS ROBUSTO).
    
    Parsea la salida de FFmpeg para extraer el tiempo procesado y calcular
    el porcentaje de progreso.
    
    Args:
        cmd: Comando FFmpeg a ejecutar
        duration_seconds: Duración total del archivo en segundos
        progress_callback: Función callback(percent: float, time_str: str) para reportar progreso
        verbose: Si True, imprime el comando
        optimize: Si True, agrega flags de optimización
        
    Returns:
        CompletedProcess con stdout y stderr combinados
    """
    import re
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from io import StringIO
    
    if not cmd or (cmd[0] not in {"ffmpeg", _FFMPEG_BIN}):
        return run_ffmpeg(cmd, verbose, optimize)
    
    cmd = _prepare_ffmpeg_cmd(cmd, optimize)
    
    # Agregar -progress pipe:1
    progress_cmd = cmd.copy()
    if "-progress" not in progress_cmd:
        insert_pos = 1
        for i, arg in enumerate(progress_cmd):
            if arg in ("-hide_banner", "-nostdin"):
                insert_pos = i + 1
        progress_cmd.insert(insert_pos, "-progress")
        progress_cmd.insert(insert_pos + 1, "pipe:1")
        progress_cmd.insert(insert_pos + 2, "-stats_period")
        progress_cmd.insert(insert_pos + 3, "0.5")
    
    if verbose:
        print(" ".join(progress_cmd))
    
    max_tries = max(1, _FFMPEG_RETRY_ATTEMPTS + 1)
    for attempt in range(1, max_tries + 1):
        process: subprocess.Popen[str] | None = None
        _FFMPEG_SEMAPHORE.acquire()
        try:
            process = subprocess.Popen(
                progress_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            with _RUNNING_FFMPEG_LOCK:
                _RUNNING_FFMPEG_PROCS.add(process)

            stderr_output = StringIO()
            stdout_output = StringIO()
            time_pattern = re.compile(r"out_time_us=(\d+)")
            last_percent = [0.0]

            def read_stderr():
                try:
                    if process.stderr is not None:
                        for line in process.stderr:
                            if line:
                                stderr_output.write(line)
                except Exception as e:
                    stderr_output.write(f"Error leyendo stderr: {e}\n")

            def read_stdout_with_progress():
                try:
                    if process.stdout is not None:
                        for line in process.stdout:
                            if line:
                                stdout_output.write(line)
                                match = time_pattern.search(line)
                                if match and duration_seconds > 0:
                                    try:
                                        time_us = int(match.group(1))
                                        time_seconds = time_us / 1_000_000.0
                                        percent = min(100.0, (time_seconds / duration_seconds) * 100.0)
                                        if progress_callback and abs(percent - last_percent[0]) >= 1.0:
                                            mins = int(time_seconds // 60)
                                            secs = int(time_seconds % 60)
                                            time_str = f"{mins:02d}:{secs:02d}"
                                            progress_callback(percent, time_str)
                                            last_percent[0] = percent
                                    except (ValueError, ZeroDivisionError):
                                        pass
                except Exception as e:
                    stdout_output.write(f"Error leyendo stdout: {e}\n")

            with ThreadPoolExecutor(max_workers=2) as executor:
                stderr_future = executor.submit(read_stderr)
                stdout_future = executor.submit(read_stdout_with_progress)
                try:
                    for future in as_completed([stderr_future, stdout_future], timeout=3600):
                        future.result()
                except Exception as e:
                    try:
                        process.terminate()
                        process.wait(timeout=5)
                    except Exception:
                        try:
                            process.kill()
                        except Exception:
                            pass
                    raise RuntimeError(f"Error procesando streams FFmpeg: {e}") from e

            try:
                returncode = process.wait(timeout=3600)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except Exception:
                    pass
                raise TimeoutError("FFmpeg timeout (>1 hora)")
        finally:
            if process is not None:
                with _RUNNING_FFMPEG_LOCK:
                    _RUNNING_FFMPEG_PROCS.discard(process)
            _FFMPEG_SEMAPHORE.release()

        completed = subprocess.CompletedProcess(
            args=progress_cmd,
            returncode=returncode,
            stdout=stdout_output.getvalue(),
            stderr=stderr_output.getvalue(),
        )
        if completed.returncode == 0:
            if progress_callback:
                progress_callback(100.0, "Completado")
            return completed

        fallback_completed = _rerun_with_fallback_ffmpeg(
            completed,
            verbose=verbose,
            optimize=optimize,
        )
        if fallback_completed.returncode == 0:
            if progress_callback:
                progress_callback(100.0, "Completado")
            return fallback_completed

        if attempt < max_tries and _is_transient_resource_error(completed.stderr):
            time.sleep(_FFMPEG_RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1)))
            continue
        return fallback_completed

    raise RuntimeError("FFmpeg falló tras reintentos.")


def ensure_ffmpeg_available() -> None:
    """Verifica que ffmpeg esté instalado y accesible."""
    try:
        subprocess.run(
            [_FFMPEG_BIN, "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(
            f"{_FFMPEG_BIN} no está instalado o no es accesible."
        ) from exc


def get_audio_duration(input_path: str) -> float | None:
    """Obtiene la duración total del audio en segundos (usa caché optimizada)."""
    info = get_audio_info(input_path)
    duration = info.get('duration')
    if isinstance(duration, (int, float)):
        return float(duration)
    return None


def get_audio_sample_rate(input_path: str) -> float | None:
    """Obtiene el sample rate del audio (usa caché optimizada)."""
    info = get_audio_info(input_path)
    sr = info.get('sample_rate')
    if isinstance(sr, (int, float)):
        return float(sr)
    return None


def extract_loudnorm_stats(output: str) -> dict[str, float]:
    """
    Obtiene el bloque JSON de loudnorm desde stderr/stdout.
    
    Valida los valores para detectar audio problemático (silencio, clipping extremo).
    """
    import json
    import math
    import re

    matches = list(re.finditer(r"\{\s*\"input_i\"[\s\S]*?\}", output))
    if not matches:
        raise ValueError("No se encontró el bloque JSON de loudnorm en la salida de ffmpeg.")
    stats_raw = json.loads(matches[-1].group(0))
    stats: dict[str, float] = {}
    for key, value in stats_raw.items():
        try:
            val = float(value)
            # Reemplazar -inf con un valor muy bajo pero usable
            if math.isinf(val) and val < 0:
                val = -70.0  # -70 LUFS es prácticamente silencio
            # Reemplazar +inf o nan con valores seguros
            elif math.isinf(val) or math.isnan(val):
                if key == "input_tp":
                    val = 0.0  # True peak máximo
                elif key == "input_i":
                    val = -70.0  # Silencio
                else:
                    val = 0.0
            stats[key] = val
        except (TypeError, ValueError):
            continue
    
    # Validar campos críticos
    if "input_i" not in stats:
        stats["input_i"] = -23.0  # Valor por defecto EBU R128
    if "input_tp" not in stats:
        stats["input_tp"] = -1.0
    if "input_lra" not in stats:
        stats["input_lra"] = 7.0  # LRA típico
    if "input_thresh" not in stats:
        stats["input_thresh"] = stats["input_i"] - 10.0
    if "target_offset" not in stats:
        stats["target_offset"] = 0.0
        
    return stats


def get_waveform_samples(
    input_path: str,
    sample_rate: int = 200,
    max_points: int = 3000,
    max_seconds: int = 45,
) -> tuple[list[float], float] | None:
    """Devuelve muestras de amplitud y el sample rate efectivo para dibujar la forma de onda."""
    preview_seconds = max(5, int(os.getenv("TONEFINISH_WAVEFORM_PREVIEW_SECONDS", str(max_seconds))))
    cmd = [
        _FFMPEG_BIN,
        "-v",
        "error",
        "-nostdin",
        "-i",
        input_path,
        "-t",
        str(preview_seconds),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=max(15, preview_seconds + 10),
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    samples = array("f")
    samples.frombytes(result.stdout)
    if not samples:
        return None
    data = samples.tolist()
    step = 1
    if len(data) > max_points:
        step = max(1, len(data) // max_points)
        data = data[::step]
    effective_rate = sample_rate / step
    return data, effective_rate


def get_audio_mono_samples(
    input_path: str,
    sample_rate: int = 22050,
    max_seconds: int = 30,
) -> list[float] | None:
    """Devuelve muestras mono en float32 para análisis espectral."""
    cmd = [
        _FFMPEG_BIN,
        "-v",
        "error",
        "-nostdin",
        "-i",
        input_path,
        "-t",
        str(max_seconds),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "-",
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0 or not result.stdout:
        return None
    samples = array("f")
    samples.frombytes(result.stdout)
    if not samples:
        return None
    return samples.tolist()
