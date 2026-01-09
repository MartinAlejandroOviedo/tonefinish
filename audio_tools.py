import subprocess
from typing import List


def run_ffmpeg(cmd: List[str], verbose: bool = False) -> subprocess.CompletedProcess[str]:
    """Ejecuta ffmpeg/ffprobe devolviendo stdout y stderr en texto."""
    if verbose:
        print(" ".join(cmd))
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
    )


def ensure_ffmpeg_available() -> None:
    """Verifica que ffmpeg esté instalado y accesible."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SystemExit(
            "ffmpeg no está instalado o no es accesible en el PATH."
        ) from exc


def get_audio_duration(input_path: str) -> float | None:
    """Obtiene la duración total del audio en segundos usando ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    result = run_ffmpeg(cmd, verbose=False)
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def get_audio_sample_rate(input_path: str) -> float | None:
    """Obtiene el sample rate del audio usando ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    result = run_ffmpeg(cmd, verbose=False)
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def extract_loudnorm_stats(output: str) -> dict[str, float]:
    """Obtiene el bloque JSON de loudnorm desde stderr/stdout."""
    import json
    import re

    match = re.search(r"\{\s*\"input_i\"[\s\S]*?\}", output)
    if not match:
        raise ValueError("No se encontró el bloque JSON de loudnorm en la salida de ffmpeg.")
    stats_raw = json.loads(match.group(0))
    stats: dict[str, float] = {}
    for key, value in stats_raw.items():
        try:
            stats[key] = float(value)
        except (TypeError, ValueError):
            continue
    return stats
