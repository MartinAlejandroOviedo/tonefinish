from __future__ import annotations

import json
import pathlib
import re
import subprocess
from audio_tools import _FFMPEG_BIN
import sys
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class RuntimeCheckReport:
    ok: bool
    warnings: List[str]
    info: List[str]


def _read_lock(lock_path: pathlib.Path) -> Dict[str, object]:
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_ffmpeg_versions() -> Dict[str, str]:
    versions: Dict[str, str] = {}
    try:
        res = subprocess.run([_FFMPEG_BIN, "-version"], capture_output=True, text=True, check=False)
    except Exception:
        return versions

    if res.returncode != 0:
        return versions

    lines = (res.stdout or "").splitlines()
    if lines:
        m = re.search(r"ffmpeg version\s+([^\s]+)", lines[0])
        if m:
            full = m.group(1).strip()
            base = full.split("-")[0]
            versions["version"] = base

    for line in lines:
        if line.startswith("libavfilter"):
            m = re.search(r"libavfilter\s+([0-9]+\.\s*[0-9]+\.\s*[0-9]+)", line)
            if m:
                versions["libavfilter"] = m.group(1).replace(" ", "")
            break
    return versions


def _get_installed_packages() -> Dict[str, str]:
    installed: Dict[str, str] = {}
    try:
        if sys.version_info >= (3, 8):
            from importlib import metadata as importlib_metadata
        else:
            import importlib_metadata  # type: ignore

        for dist in importlib_metadata.distributions():
            name = dist.metadata.get("Name")
            version = dist.version
            if name and version:
                installed[name] = version
    except Exception:
        return installed
    return installed


def check_runtime_reproducibility(
    lock_path: pathlib.Path | None = None,
) -> RuntimeCheckReport:
    lock_path = lock_path or (pathlib.Path(__file__).resolve().parent / "runtime_lock.json")
    lock = _read_lock(lock_path)
    warnings: List[str] = []
    info: List[str] = []

    if not lock:
        return RuntimeCheckReport(
            ok=False,
            warnings=[f"No se pudo leer lock reproducible: {lock_path}"],
            info=[],
        )

    expected_ffmpeg = lock.get("ffmpeg", {}) if isinstance(lock.get("ffmpeg"), dict) else {}
    observed_ffmpeg = _get_ffmpeg_versions()
    for key in ("version", "libavfilter"):
        expected = str(expected_ffmpeg.get(key, "")).strip()
        observed = str(observed_ffmpeg.get(key, "")).strip()
        if expected:
            if observed != expected:
                warnings.append(
                    f"FFmpeg {key} distinto (actual={observed or 'n/d'}, esperado={expected})."
                )
            else:
                info.append(f"FFmpeg {key} OK ({observed}).")

    expected_pkgs = lock.get("python_packages", {})
    expected_pkgs = expected_pkgs if isinstance(expected_pkgs, dict) else {}
    observed_pkgs = _get_installed_packages()
    for pkg_name, expected_version_obj in expected_pkgs.items():
        expected_version = str(expected_version_obj).strip()
        observed_version = str(observed_pkgs.get(pkg_name, "")).strip()
        if not observed_version:
            warnings.append(f"Paquete faltante: {pkg_name} (esperado={expected_version}).")
            continue
        if observed_version != expected_version:
            warnings.append(
                f"Paquete {pkg_name} distinto (actual={observed_version}, esperado={expected_version})."
            )
        else:
            info.append(f"{pkg_name} OK ({observed_version}).")

    return RuntimeCheckReport(ok=len(warnings) == 0, warnings=warnings, info=info)

