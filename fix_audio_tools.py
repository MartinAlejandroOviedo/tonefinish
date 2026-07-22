#!/usr/bin/env python3
"""Utilidad para corregir type hints y firmas en audio_tools.py."""

from __future__ import annotations

import argparse
import pathlib
import re
from typing import Any


def apply_fixes(target: pathlib.Path, dry_run: bool = False) -> dict[str, Any]:
    content = target.read_text(encoding="utf-8")
    original = content
    changes: list[str] = []

    old_import = "from typing import Dict, List, Optional"
    new_import = "from typing import Dict, List, Optional, Any, Tuple"
    if old_import in content and new_import not in content:
        content = content.replace(old_import, new_import)
        changes.append("imports")

    old_signature = "-> Dict[str, Optional[float | int | str]]:"
    new_signature = "-> Dict[str, Any]:"
    if old_signature in content:
        content = content.replace(old_signature, new_signature)
        changes.append("get_audio_info_return_type")

    pattern_duration = r"def get_audio_duration\(input_path: str\) -> float \| None:"
    if re.search(pattern_duration, content):
        old_duration = """def get_audio_duration(input_path: str) -> float | None:
    \"\"\"Obtiene la duración total del audio en segundos (usa caché optimizada).\"\"\"
    info = get_audio_info(input_path)
    return info.get('duration')"""

        new_duration = """def get_audio_duration(input_path: str) -> float | None:
    \"\"\"Obtiene la duración total del audio en segundos (usa caché optimizada).\"\"\"
    info = get_audio_info(input_path)
    duration = info.get('duration')
    if isinstance(duration, (int, float)):
        return float(duration)
    return None"""

        if old_duration in content:
            content = content.replace(old_duration, new_duration)
            changes.append("get_audio_duration")

    pattern_sr = r"def get_audio_sample_rate\(input_path: str\) -> float \| None:"
    if re.search(pattern_sr, content):
        old_sr = """def get_audio_sample_rate(input_path: str) -> float | None:
    \"\"\"Obtiene el sample rate del audio (usa caché optimizada).\"\"\"
    info = get_audio_info(input_path)
    sr = info.get('sample_rate')
    return float(sr) if sr else None"""

        new_sr = """def get_audio_sample_rate(input_path: str) -> float | None:
    \"\"\"Obtiene el sample rate del audio (usa caché optimizada).\"\"\"
    info = get_audio_info(input_path)
    sr = info.get('sample_rate')
    if isinstance(sr, (int, float)):
        return float(sr)
    return None"""

        if old_sr in content:
            content = content.replace(old_sr, new_sr)
            changes.append("get_audio_sample_rate")

    changed = content != original
    if changed and not dry_run:
        target.write_text(content, encoding="utf-8")

    return {
        "target": str(target),
        "changed": changed,
        "dry_run": dry_run,
        "changes": changes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Corrige type hints en audio_tools.py")
    parser.add_argument("--target", default="audio_tools.py", help="Ruta de archivo objetivo")
    parser.add_argument("--dry-run", action="store_true", help="No escribe cambios")
    args = parser.parse_args()

    target = pathlib.Path(args.target)
    if not target.exists():
        raise SystemExit(f"No existe: {target}")

    result = apply_fixes(target=target, dry_run=args.dry_run)
    if result["changed"]:
        mode = "(dry-run)" if args.dry_run else ""
        print(f"✅ {target} actualizado {mode}".strip())
        for item in result["changes"]:
            print(f"- {item}")
    else:
        print("ℹ️ Sin cambios: archivo ya está actualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
