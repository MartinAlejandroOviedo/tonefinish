"""Reglas únicas para nombrar archivos masterizados."""

from __future__ import annotations

import re


_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_LEGACY_SUFFIXES = ("_processed", "_master", "_final", "_mix", "_normalized")


def sanitize_filename_component(value: str, fallback: str) -> str:
    cleaned = _INVALID_FILENAME_CHARS.sub("-", str(value or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-")
    return cleaned or fallback


def mastered_output_stem(source_stem: str, artist: str = "O-M-A") -> str:
    """Construye `ARTISTA - canción` sin extensión ni sufijos históricos."""
    safe_artist = sanitize_filename_component(artist, "O-M-A")
    title = str(source_stem or "").strip()
    for suffix in _LEGACY_SUFFIXES:
        if title.lower().endswith(suffix):
            title = title[:-len(suffix)].rstrip(" _-")
            break
    prefix = f"{safe_artist} - "
    already_prefixed = title.casefold().startswith(prefix.casefold())
    if already_prefixed:
        title = title[len(prefix):]
    safe_title = sanitize_filename_component(title, "Sin título")
    if already_prefixed and not safe_title.casefold().endswith(" - master"):
        safe_title = f"{safe_title} - Master"
    return f"{safe_artist} - {safe_title}"
