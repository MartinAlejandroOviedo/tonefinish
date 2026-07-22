from __future__ import annotations

from typing import Dict, Tuple


def _level_key(level: str) -> str:
    return level.strip().lower()


def build_repair_chain(
    input_label: str,
    noise_level: str,
    declip_level: str,
    declick_level: str,
    pink_noise_level: str = "Off",
) -> Tuple[str, str]:
    """Construye filtros de repair (noise/clip/click/pink) antes del resto."""
    parts = []
    current = input_label

    def add_filter(filter_expr: str, label: str) -> None:
        nonlocal current
        parts.append(f"[{current}]{filter_expr}[{label}]")
        current = label

    level = _level_key(declip_level)
    if level not in ("off", "apagado"):
        add_filter("adeclip", "dc")

    level = _level_key(declick_level)
    if level not in ("off", "apagado"):
        if level == "leve":
            add_filter("adeclick=a=0.15", "dk")
        elif level == "medio":
            add_filter("adeclick=a=0.28", "dk")
        elif level == "alto":
            add_filter("adeclick=a=0.45", "dk")
        else:
            add_filter("adeclick", "dk")

    level = _level_key(noise_level)
    if level not in ("off", "apagado"):
        if level == "leve":
            add_filter("afftdn=nr=2:nf=-22", "nr")
        elif level == "medio":
            add_filter("afftdn=nr=6:nf=-28", "nr")
        elif level == "alto":
            add_filter("afftdn=nr=10:nf=-32", "nr")
        else:
            add_filter("afftdn=nr=3:nf=-24", "nr")

    level = _level_key(pink_noise_level)
    if level not in ("off", "apagado"):
        # Pink noise correction: un solo low-shelf con pendiente suave
        # Reemplaza los 3 high-shelf encadenados que eran una aproximación imprecisa
        if level == "leve":
            add_filter("equalizer=f=500:width_type=h:width=1000:g=-1.5:t=l", "pk")
        elif level == "medio":
            add_filter("equalizer=f=500:width_type=h:width=1000:g=-3.0:t=l", "pk")
        elif level == "alto":
            add_filter("equalizer=f=500:width_type=h:width=1000:g=-5.0:t=l", "pk")

    return ";".join(parts), current


def resolve_repair_levels(
    stats: Dict[str, float] | None,
    noise_level: str,
    declip_level: str,
    declick_level: str,
) -> Tuple[str, str, str]:
    """Resuelve niveles Auto a niveles concretos según el análisis."""
    if stats is None:
        return noise_level, declip_level, declick_level

    input_tp = stats.get("input_tp", 0.0)
    input_thresh = stats.get("input_thresh", -50.0)

    def resolve_noise(level: str) -> str:
        if _level_key(level) != "auto":
            return level
        return "Leve" if input_thresh > -20.0 else "Off"

    def resolve_declip(level: str) -> str:
        if _level_key(level) != "auto":
            return level
        return "Leve" if input_tp >= -0.1 else "Off"

    def resolve_declick(level: str) -> str:
        if _level_key(level) != "auto":
            return level
        return "Leve" if input_tp >= -0.05 else "Off"

    return resolve_noise(noise_level), resolve_declip(declip_level), resolve_declick(declick_level)
