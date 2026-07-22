from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import json
from typing import Any

from audio_analysis import (
    analyze_audio as _py_analyze_audio,
    analyze_audio_with_filter as _py_analyze_audio_with_filter,
    analyze_eq_bands as _py_analyze_eq_bands,
    analyze_eq_and_voice as _py_analyze_eq_and_voice,
    analyze_voice_band as _py_analyze_voice_band,
    evaluate_mix as _py_evaluate_mix,
    format_analysis_summary as _py_format_analysis_summary,
    write_analysis_toml as _py_write_analysis_toml,
)
from audio_tools import (
    cancel_running_ffmpeg_processes as _py_cancel_running_ffmpeg_processes,
    ensure_ffmpeg_available as _py_ensure_ffmpeg_available,
    extract_loudnorm_stats as _py_extract_loudnorm_stats,
    get_audio_info as _py_get_audio_info,
    get_processing_limits as _py_get_processing_limits,
)
from audio_processing import (
    apply_output_gain as _py_apply_output_gain,
    build_preprocess_chain as _py_build_preprocess_chain,
    ensure_output_path as _py_ensure_output_path,
    normalize_audio as _py_normalize_audio,
    resolve_repair_levels as _py_resolve_repair_levels,
)
from auto_master_intelligence import (
    analyze_audio_for_automaster as _py_analyze_audio_for_automaster,
    analyze_batch_for_automaster as _py_analyze_batch_for_automaster,
    adapt_preset_to_audio as _py_adapt_preset_to_audio,
    update_saturation_budgets_for_batch as _py_update_saturation_budgets_for_batch,
)

_active_spasm_proc: subprocess.Popen[str] | None = None


def _kill_proc_tree(pid: int) -> None:
    """Mata el proceso y todos sus hijos recursivamente."""
    try:
        import psutil
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except ImportError:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def cancel_active_spasm_call() -> bool:
    """Cancela la llamada SpASM en curso. Retorna True si había algo que cancelar."""
    global _active_spasm_proc
    proc = _active_spasm_proc
    if proc is not None and proc.poll() is None:
        _kill_proc_tree(proc.pid)
        _active_spasm_proc = None
        return True
    return False


def _audio_engine_mode() -> str:
    """
    Compatibilidad de configuración:
    - FINISHER_AUDIO_ENGINE=python|spasm|hybrid (preferido para usuario final)
    - FINISHER_LOGIC_BACKEND=python|spasm (legacy interno)
    """
    raw_engine = os.getenv("FINISHER_AUDIO_ENGINE", "").strip().lower()
    if raw_engine in {"python", "spasm", "hybrid"}:
        return raw_engine
    # Default operativo: híbrido (SpASM + fallback Python).
    return "hybrid"


def _backend_mode() -> str:
    engine = _audio_engine_mode()
    if engine == "python":
        return "python"
    if engine in {"spasm", "hybrid"}:
        return "spasm"
    # Objetivo de migración: SpASM como backend por defecto.
    return os.getenv("FINISHER_LOGIC_BACKEND", "spasm").strip().lower()


def _spasm_cli() -> str:
    default_cli = pathlib.Path(__file__).resolve().parent / "scripts" / "finisher_spasm_cli"
    return os.getenv("FINISHER_SPASM_CLI", str(default_cli))


def _spasm_fallback_python_enabled() -> bool:
    if _audio_engine_mode() == "hybrid":
        return True
    # Por defecto NO fallback a Python para evitar rutas legacy silenciosas.
    raw = os.getenv("FINISHER_SPASM_FALLBACK_PYTHON", "0").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def get_audio_engine_diagnostics() -> dict[str, Any]:
    requested = _audio_engine_mode()
    resolved_backend = _backend_mode()
    return {
        "requested_engine": requested,
        "resolved_backend": resolved_backend,
        "hybrid_active": requested == "hybrid",
        "spasm_fallback_python_enabled": _spasm_fallback_python_enabled(),
        "spasm_cli": _spasm_cli(),
        "ffmpeg_bin": os.getenv("FINISHER_FFMPEG_BIN") or _FFMPEG_BIN,
        "ffprobe_bin": os.getenv("FINISHER_FFPROBE_BIN", "ffprobe"),
    }


def _to_wire(value: Any) -> Any:
    if isinstance(value, pathlib.Path):
        return {"__type__": "path", "value": str(value)}
    if isinstance(value, tuple):
        return {"__type__": "tuple", "value": [_to_wire(v) for v in value]}
    if isinstance(value, list):
        return [_to_wire(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_wire(v) for k, v in value.items()}
    if hasattr(value, "__dict__"):
        return _to_wire(vars(value))
    return value


def _from_wire(value: Any) -> Any:
    if isinstance(value, dict):
        tag = value.get("__type__")
        if tag == "path":
            return pathlib.Path(str(value.get("value", "")))
        if tag == "tuple":
            return tuple(_from_wire(v) for v in value.get("value", []))
        return {k: _from_wire(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_wire(v) for v in value]
    return value


def _call_spasm(method: str, *args: Any, **kwargs: Any) -> Any:
    for val in list(args) + list(kwargs.values()):
        if callable(val):
            raise RuntimeError(
                f"El backend SpASM no soporta callbacks Python para '{method}'."
            )

    req = {
        "method": method,
        "args": [_to_wire(v) for v in args],
        "kwargs": {k: _to_wire(v) for k, v in kwargs.items()},
    }
    cmd = [_spasm_cli(), "call", "--json"]
    timeout_s = float(os.getenv("FINISHER_SPASM_TIMEOUT_SEC", "600").strip() or "600")

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Registrar proceso activo para permitir cancelación desde GUI
    _active_spasm_proc = proc

    try:
        stdout_data, stderr_data = proc.communicate(
            input=json.dumps(req),
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        _kill_proc_tree(proc.pid)
        proc.wait()
        raise RuntimeError(f"Timeout del CLI SpASM ({timeout_s}s) para '{method}'.")
    except KeyboardInterrupt:
        _kill_proc_tree(proc.pid)
        proc.wait()
        raise RuntimeError(f"Cancelado por el usuario: '{method}'.")
    finally:
        _active_spasm_proc = None

    if proc.returncode != 0:
        stderr = (stderr_data or "").strip()
        stdout = (stdout_data or "").strip()
        detail = stderr or stdout or "sin detalle"
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise RuntimeError(
            f"CLI SpASM falló (cmd: {' '.join(cmd)}): {detail}"
        )

    out = (stdout_data or "").strip()
    if not out:
        raise RuntimeError("CLI SpASM devolvió salida vacía.")

    try:
        payload = json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Respuesta JSON inválida del CLI SpASM: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Respuesta del CLI SpASM inválida: se esperaba objeto JSON.")
    if not payload.get("ok", False):
        raise RuntimeError(str(payload.get("error", "Error no especificado del CLI SpASM")))

    return _from_wire(payload.get("result"))


def _dispatch(method: str, py_impl: Any, *args: Any, **kwargs: Any) -> Any:
    if _backend_mode() == "spasm":
        # Mantener UX de progreso en GUI: los callbacks Python (por ejemplo
        # progress_callback en normalize_audio / batch automaster) no se
        # serializan por CLI, así que en esos casos se ejecuta local.
        if any(callable(v) for v in list(args) + list(kwargs.values())):
            return py_impl(*args, **kwargs)
        try:
            return _call_spasm(method, *args, **kwargs)
        except Exception as exc:
            # En modo híbrido priorizamos continuidad operativa: si falla
            # normalize_audio en SpASM, degradamos a implementación Python.
            if _audio_engine_mode() == "hybrid" and method == "normalize_audio":
                return py_impl(*args, **kwargs)
            if _spasm_fallback_python_enabled():
                msg = str(exc).lower()
                if (
                    "no implementado" in msg
                    or "not_supported" in msg
                    or "method_not_supported" in msg
                    or "no soporta callbacks python" in msg
                ):
                    return py_impl(*args, **kwargs)
            raise
    return py_impl(*args, **kwargs)


def analyze_audio(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("analyze_audio", _py_analyze_audio, *args, **kwargs)


def analyze_audio_with_filter(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("analyze_audio_with_filter", _py_analyze_audio_with_filter, *args, **kwargs)


def analyze_eq_bands(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("analyze_eq_bands", _py_analyze_eq_bands, *args, **kwargs)


def analyze_eq_and_voice(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("analyze_eq_and_voice", _py_analyze_eq_and_voice, *args, **kwargs)


def analyze_voice_band(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("analyze_voice_band", _py_analyze_voice_band, *args, **kwargs)


def evaluate_mix(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("evaluate_mix", _py_evaluate_mix, *args, **kwargs)


def format_analysis_summary(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("format_analysis_summary", _py_format_analysis_summary, *args, **kwargs)


def write_analysis_toml(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("write_analysis_toml", _py_write_analysis_toml, *args, **kwargs)


def apply_output_gain(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("apply_output_gain", _py_apply_output_gain, *args, **kwargs)


def build_preprocess_chain(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("build_preprocess_chain", _py_build_preprocess_chain, *args, **kwargs)


def ensure_output_path(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("ensure_output_path", _py_ensure_output_path, *args, **kwargs)


def normalize_audio(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("normalize_audio", _py_normalize_audio, *args, **kwargs)


def resolve_repair_levels(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("resolve_repair_levels", _py_resolve_repair_levels, *args, **kwargs)


def analyze_audio_for_automaster(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("analyze_audio_for_automaster", _py_analyze_audio_for_automaster, *args, **kwargs)


def analyze_batch_for_automaster(*args: Any, **kwargs: Any) -> Any:
    return _dispatch("analyze_batch_for_automaster", _py_analyze_batch_for_automaster, *args, **kwargs)


def adapt_preset_to_audio(*args: Any, **kwargs: Any) -> Any:
    # La selección IA/SUNO y el contrato de function_id viven en Python.
    # SpASM procesa la señal de audio; su implementación CLI de esta función es
    # una heurística legacy que no puede consultar proveedores ni emitir la
    # traza canónica requerida por el orquestador.
    return _py_adapt_preset_to_audio(*args, **kwargs)


def update_saturation_budgets_for_batch(*args: Any, **kwargs: Any) -> Any:
    return _dispatch(
        "update_saturation_budgets_for_batch",
        _py_update_saturation_budgets_for_batch,
        *args,
        **kwargs,
    )


def spasm_batch_start(payload: dict[str, Any]) -> dict[str, Any]:
    return _call_spasm("batch_start", payload)


def spasm_batch_status(job_id: str) -> dict[str, Any]:
    return _call_spasm("batch_status", job_id)


def spasm_batch_cancel(job_id: str) -> bool:
    return bool(_call_spasm("batch_cancel", job_id))


def get_runtime_resource_info() -> dict[str, Any]:
    engine_diag = get_audio_engine_diagnostics()
    if _backend_mode() == "spasm":
        try:
            res = _call_spasm("get_runtime_resource_info")
            if isinstance(res, dict):
                res["engine"] = engine_diag
                return res
        except Exception:
            pass

    from resource_monitor import ResourceMonitor  # import local para evitar ciclos

    monitor = ResourceMonitor()
    snapshot = monitor.snapshot()
    gpu_snapshot = monitor.gpu_snapshot()
    gpu_info: dict[str, Any] = {"available": gpu_snapshot is not None}
    if gpu_snapshot is not None:
        gpu_info.update(
            {
                "backend": gpu_snapshot.backend,
                "device_count": gpu_snapshot.device_count,
                "name": gpu_snapshot.name,
                "driver_version": gpu_snapshot.driver_version,
                "utilization_percent": gpu_snapshot.utilization_percent,
                "memory_total_mb": gpu_snapshot.memory_total_mb,
                "memory_used_mb": gpu_snapshot.memory_used_mb,
                "memory_free_mb": gpu_snapshot.memory_free_mb,
            }
        )
    else:
        gpu_info.update(
            {
                "backend": "none",
                "device_count": 0,
                "name": None,
                "driver_version": None,
                "utilization_percent": None,
                "memory_total_mb": None,
                "memory_used_mb": None,
                "memory_free_mb": None,
            }
        )
    return {
        "summary": snapshot.format_summary(),
        "cpu": {
            "cpu_count": snapshot.cpu_count,
            "cpu_percent": snapshot.cpu_percent,
            "memory_percent": snapshot.memory_percent,
            "memory_available_gb": snapshot.memory_available_gb,
            "ffmpeg_processes": snapshot.ffmpeg_processes,
        },
        "gpu": gpu_info,
        "engine": engine_diag,
    }


def ensure_ffmpeg_available() -> Any:
    if _backend_mode() == "spasm":
        try:
            return _call_spasm("ensure_ffmpeg_available")
        except Exception:
            pass
    return _py_ensure_ffmpeg_available()


def get_processing_limits() -> dict[str, Any]:
    if _backend_mode() == "spasm":
        try:
            res = _call_spasm("get_processing_limits")
            if isinstance(res, dict):
                return res
        except Exception:
            pass
    return _py_get_processing_limits()


def get_audio_info(input_path: str, use_cache: bool = True) -> dict[str, Any]:
    if _backend_mode() == "spasm":
        try:
            res = _call_spasm("get_audio_info", input_path, use_cache)
            if isinstance(res, dict):
                return res
        except Exception:
            pass
    return _py_get_audio_info(input_path, use_cache=use_cache)


def extract_loudnorm_stats(output: str) -> dict[str, float]:
    if _backend_mode() == "spasm":
        try:
            res = _call_spasm("extract_loudnorm_stats", output)
            if isinstance(res, dict):
                return {str(k): float(v) for k, v in res.items()}
        except Exception:
            pass
    return _py_extract_loudnorm_stats(output)


def cancel_running_ffmpeg_processes() -> int:
    if _backend_mode() == "spasm":
        try:
            res = _call_spasm("cancel_running_ffmpeg_processes")
            return int(res)
        except Exception:
            pass
    return int(_py_cancel_running_ffmpeg_processes())


def fix_audio_tools(target: str = "audio_tools.py", dry_run: bool = False) -> dict[str, Any]:
    if _backend_mode() == "spasm":
        res = _call_spasm("fix_audio_tools", target, dry_run)
        if isinstance(res, dict):
            return res
        raise RuntimeError("Respuesta inválida de fix_audio_tools vía CLI.")

    from fix_audio_tools import apply_fixes

    return apply_fixes(pathlib.Path(target), dry_run=dry_run)
