"""Orquestador único del grafo DSP basado en function_id."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from processes import registry as process_registry
from processes.catalog import function_registry
from processes.contracts import AudioFunctionAction, AudioProcessContext, FilterLabelFactory
from processes.budgets import (
    DEFAULT_BUDGET_POLICY, HEADROOM_GOVERNOR_ID, estimate_effective_band_boosts,
)


@dataclass(frozen=True)
class CompiledAudioGraph:
    filter_chain: str
    output_label: str
    applied_actions: tuple[AudioFunctionAction, ...]


class AudioProcessOrchestrator:
    """Valida acciones, localiza su plugin y compila un único grafo secuencial."""

    def __init__(self) -> None:
        self._plugins = {plugin.plugin_id: plugin for plugin in process_registry}

    def compile(
        self,
        actions: Iterable[AudioFunctionAction],
        context: AudioProcessContext,
        input_label: str = "0:a",
    ) -> CompiledAudioGraph:
        validated = function_registry.validate_plan(actions)
        headroom = estimate_effective_band_boosts(validated)
        limit = float(DEFAULT_BUDGET_POLICY["effective_band_boost_max_db"])
        exceeded = {
            band: value for band, value in headroom["effective_boost_by_band_db"].items()
            if value > limit + 1e-9
        }
        if exceeded:
            details = ", ".join(f"{band}={value:.2f}dB" for band, value in exceeded.items())
            raise ValueError(
                f"{HEADROOM_GOVERNOR_ID}: boost efectivo acumulado excedido "
                f"(límite={limit:.2f}dB; {details})"
            )
        labels = FilterLabelFactory()
        parts: list[str] = []
        current = input_label
        applied: list[AudioFunctionAction] = []
        index = 0
        while index < len(validated):
            action = validated[index]
            if not action.enabled:
                index += 1
                continue
            spec = function_registry.get(action.function_id)
            plugin = self._plugins.get(spec.plugin_id)
            if plugin is None:
                raise RuntimeError(f"No hay plugin para {spec.plugin_id}")
            batch = [action]
            if hasattr(plugin, "build_functions"):
                cursor = index + 1
                while cursor < len(validated):
                    candidate = validated[cursor]
                    candidate_spec = function_registry.get(candidate.function_id)
                    if not candidate.enabled or candidate_spec.plugin_id != spec.plugin_id:
                        break
                    batch.append(candidate)
                    cursor += 1
                chain, output = plugin.build_functions(batch, current, context, labels)
                index = cursor
            else:
                chain, output = plugin.build_function(action, current, context, labels)
                index += 1
            if not chain:
                continue
            parts.append(chain)
            current = output
            applied.extend(batch)
        return CompiledAudioGraph(";".join(parts), current, tuple(applied))


orchestrator = AudioProcessOrchestrator()


LEGACY_BAND_IDS = {
    "Subbass (20-60 Hz)": "sub_bass", "Bass (60-250 Hz)": "bass",
    "Low-Mid (250-500 Hz)": "low_mid", "Mid (500-2k Hz)": "mid",
    "High-Mid (2k-6k Hz)": "high_mid", "Air (6k-16k Hz)": "air",
    "sub_bass": "sub_bass", "bass": "bass", "low_mid": "low_mid",
    "mid": "mid", "high_mid": "high_mid", "air": "air",
}


def _band_id(label: str) -> str | None:
    return LEGACY_BAND_IDS.get(label)


def migrate_legacy_preprocess_config(**cfg) -> list[AudioFunctionAction]:
    """Convierte la API histórica de build_preprocess_chain al contrato canónico."""
    groups: dict[str, list[AudioFunctionAction]] = {
        key: [] for key in ("repair", "deesser", "tone_eq", "multiband", "saturation", "glue")
    }
    if cfg.get("repair_enabled", True):
        for fid, key in (
            ("audio.repair.denoise", "noise_reduction_level"),
            ("audio.repair.declip", "declip_level"),
            ("audio.repair.declick", "declick_level"),
            ("audio.repair.pink_noise_compensation", "pink_noise_level"),
        ):
            level = str(cfg.get(key, "Off"))
            if level.lower() not in ("off", "apagado"):
                groups["repair"].append(AudioFunctionAction(fid, params={"level": level}))

    if cfg.get("mix_enabled", True):
        if cfg.get("deesser"):
            groups["deesser"].append(AudioFunctionAction(
                "audio.deesser.sibilance_reduction",
                params={"frequency_hz": float(cfg.get("deesser_freq_hz", 6000.0)),
                        "intensity": min(1.5, max(0.0, float(cfg.get("deesser_intensity", 1.0))))},
            ))
        tone_values = (
            ("sub_bass", 45.0, cfg.get("sub_bass_db", 0.0), "low_shelf"),
            ("bass", 120.0, cfg.get("tone_low_db", 0.0), "low_shelf"),
            ("low_mid", 500.0, cfg.get("low_mid_db", 0.0), "peaking"),
            ("mid", 1000.0, cfg.get("tone_mid_db", 0.0), "peaking"),
            ("high_mid", 6000.0, cfg.get("high_mid_db", 0.0), "peaking"),
            ("high_mid", 8000.0, cfg.get("tone_high_db", 0.0), "high_shelf"),
            ("air", 12000.0, cfg.get("air_db", 0.0), "high_shelf"),
        )
        for band, frequency, gain, filter_type in tone_values:
            if abs(float(gain)) > 0.001:
                groups["tone_eq"].append(AudioFunctionAction(
                    "audio.tone_eq.band", target=band,
                    params={"frequency_hz": frequency, "gain_db": float(gain), "q": 0.707, "filter_type": filter_type},
                ))
        if abs(float(cfg.get("tone_tilt_db", 0.0))) > 0.001:
            groups["tone_eq"].append(AudioFunctionAction(
                "audio.tone_eq.tilt", params={"gain_db": float(cfg["tone_tilt_db"]), "pivot_hz": 1000.0}
            ))

        band_stats = cfg.get("band_stats") or {}
        if cfg.get("dynamic_eq"):
            if not band_stats:
                raise ValueError("dynamic_eq requiere band_stats")
            for label, rms in band_stats.items():
                band = _band_id(label)
                if band:
                    groups["multiband"].append(AudioFunctionAction(
                        "audio.multiband.compressor", target=band,
                        params={"threshold_db": min(0.0, float(rms) + float(cfg.get("band_range_db", 3.0))),
                                "ratio": 2.0, "attack_ms": 20.0, "release_ms": 120.0,
                                "knee_db": 4.0, "makeup_db": 0.0},
                    ))
        for label, gain in (cfg.get("band_adjust_db") or {}).items():
            band = _band_id(label)
            if band and abs(float(gain)) > 0.001:
                groups["multiband"].append(AudioFunctionAction("audio.multiband.eq", target=band, params={"gain_db": max(-6.0, min(6.0, float(gain))) }))
        for label, width in (cfg.get("band_widths") or {}).items():
            band = _band_id(label)
            if band and abs(float(width) - 1.0) > 0.001:
                groups["multiband"].append(AudioFunctionAction("audio.multiband.stereo_width", target=band, params={"width": max(0.0, min(2.5, float(width))) }))
        if cfg.get("stereo_width") and not cfg.get("band_widths"):
            default_widths = {
                "sub_bass": 0.15, "bass": 0.4, "low_mid": 0.7,
                "mid": 1.0, "high_mid": 1.2, "air": 1.4,
            }
            for band, width in default_widths.items():
                groups["multiband"].append(AudioFunctionAction("audio.multiband.stereo_width", target=band, params={"width": width}))
        if cfg.get("stereo_dynamic"):
            per_band_mix = list(cfg.get("stereo_dynamic_band_mix") or [])
            default_mix = max(0.0, min(1.0, float(cfg.get("stereo_dynamic_mix", 0.6))))
            for idx, band in enumerate(("sub_bass", "bass", "low_mid", "mid", "high_mid", "air")):
                mix = float(per_band_mix[idx]) if idx < len(per_band_mix) else default_mix
                mix = mix / 100.0 if mix > 1.0 else mix
                groups["multiband"].append(AudioFunctionAction(
                    "audio.multiband.stereo_width", target=band,
                    params={"width": max(0.0, min(2.5, 1.0 - 0.35 * mix))},
                    reason="Migrado desde stereo_dynamic: compresión Side aproximada como control de ancho",
                ))
        if cfg.get("auto_band_gain"):
            for band in ("sub_bass", "bass", "low_mid", "mid", "high_mid", "air"):
                groups["multiband"].append(AudioFunctionAction("audio.multiband.eq", target=band, params={"gain_db": 2.0}))
        if cfg.get("multiband_limiter_enabled"):
            thresholds = cfg.get("multiband_limiter_thresholds") or {
                "sub_bass": -3.5, "bass": -2.5, "low_mid": -1.5,
                "mid": -1.5, "high_mid": -3.5, "air": -5.0,
            }
            for label, ceiling in thresholds.items():
                band = _band_id(label)
                if band:
                    groups["multiband"].append(AudioFunctionAction("audio.multiband.limiter", target=band, params={"ceiling_db": max(-12.0, min(0.0, float(ceiling))), "release_ms": 50.0}))
        if cfg.get("saturation_per_band"):
            drives = cfg.get("saturation_band_drive_db") or {}
            mixes = cfg.get("saturation_band_mix") or {}
            for label in set(drives) | set(mixes):
                band = _band_id(label)
                mix = float(mixes.get(label, 0.0))
                if band and mix > 0:
                    groups["multiband"].append(AudioFunctionAction(
                        "audio.multiband.saturation", target=band,
                        params={"drive_db": max(-24.0, min(24.0, float(drives.get(label, 0.0)))),
                                "mix": max(0.0, min(1.0, mix)), "type": cfg.get("saturation_type", "Tape")},
                    ))
        elif cfg.get("saturation_enabled") and float(cfg.get("saturation_mix", 0.0)) > 0:
            groups["saturation"].append(AudioFunctionAction(
                "audio.saturation.softclip",
                params={"drive_db": max(-24.0, min(24.0, float(cfg.get("saturation_drive_db", 0.0)))),
                        "mix": max(0.0, min(1.0, float(cfg.get("saturation_mix", 0.0)))),
                        "type": cfg.get("saturation_type", "Tape"), "oversampling": 2},
            ))
        if cfg.get("glue_enabled"):
            groups["glue"].append(AudioFunctionAction(
                "audio.glue.bus_compressor", params={
                    "threshold_db": float(cfg.get("glue_threshold_db", -18.0)),
                    "ratio": float(cfg.get("glue_ratio", 1.4)),
                    "attack_ms": float(cfg.get("glue_attack_ms", 20.0)),
                    "release_ms": float(cfg.get("glue_release_ms", 120.0)),
                    "knee_db": float(cfg.get("glue_knee_db", 6.0)),
                    "makeup_db": float(cfg.get("glue_makeup_db", 0.0)),
                },
            ))

    order = cfg.get("process_order") or ["repair", "deesser", "multiband", "tone_eq", "saturation", "glue"]
    normalized_order: list[str] = []
    aliases = {"dynamic_eq": "multiband", "stereo_width": "multiband", "band_adjust": "multiband", "auto_band_gain": "multiband", "stereo_dynamic": "multiband"}
    for key in order:
        key = aliases.get(key, key)
        if key in groups and key not in normalized_order:
            normalized_order.append(key)
    normalized_order.extend(key for key in groups if key not in normalized_order)

    actions: list[AudioFunctionAction] = []
    if cfg.get("autogain_enabled", True):
        actions.append(AudioFunctionAction("audio.autogain.headroom", params={"gain_db": max(-30.0, min(0.0, float(cfg.get("headroom_db", -17.0))))}))
    for group in normalized_order:
        if groups[group]:
            actions.extend(groups[group])
            if cfg.get("autogain_enabled", True):
                actions.append(AudioFunctionAction("audio.autogain.interstage_limiter", params={"ceiling_db": 0.0, "attack_ms": 1.0, "release_ms": 50.0}))
    if cfg.get("autogain_enabled", True):
        actions.append(AudioFunctionAction("audio.autogain.final_peak", params={"ceiling_db": -3.0}))
    return actions


def migrate_legacy_registry_state(
    state: Mapping[str, object],
    band_stats: Mapping[str, float] | None = None,
) -> list[AudioFunctionAction]:
    """Migra el formato serializado por ProcessRegistry.to_dict()."""
    stored = state.get("processes", {})
    if not isinstance(stored, Mapping):
        raise ValueError("Estado legacy inválido: processes debe ser un objeto")
    cfg: dict[str, object] = {
        "band_stats": dict(band_stats or {}), "dynamic_eq": False,
        "stereo_width": False, "deesser": False,
        "process_order": list(state.get("order", []) or []),
    }
    for process_id, raw in stored.items():
        if not isinstance(raw, Mapping) or not raw.get("enabled", True):
            continue
        params = raw.get("params", {})
        if not isinstance(params, Mapping):
            continue
        if process_id == "repair":
            cfg.update({
                "noise_reduction_level": params.get("noise_level", "Off"),
                "declip_level": params.get("declip_level", "Off"),
                "declick_level": params.get("declick_level", "Off"),
                "pink_noise_level": params.get("pink_noise_level", "Off"),
            })
        elif process_id == "deesser":
            cfg.update({"deesser": params.get("enabled", False),
                        "deesser_freq_hz": params.get("frequency_hz", 6000.0),
                        "deesser_intensity": params.get("intensity", 1.0)})
        elif process_id == "tone_eq":
            cfg.update(params)
            cfg["tone_low_db"] = params.get("bass_db", 0.0)
            cfg["tone_mid_db"] = params.get("mid_db", 0.0)
        elif process_id == "multiband":
            cfg.update(params)
        elif process_id == "saturation":
            cfg.update({"saturation_enabled": params.get("saturation_enabled", False),
                        "saturation_type": params.get("saturation_type", "Tape"),
                        "saturation_drive_db": params.get("drive_db", 0.0),
                        "saturation_mix": params.get("mix", 0.0)})
        elif process_id == "glue":
            cfg["glue_enabled"] = params.get("glue_enabled", False)
            defaults = {"threshold_db": -18.0, "ratio": 1.4, "attack_ms": 20.0,
                        "release_ms": 120.0, "knee_db": 6.0, "makeup_db": 0.0}
            for key, default in defaults.items():
                cfg[f"glue_{key}"] = params.get(key, default)
        elif process_id == "autogain":
            cfg.update({"autogain_enabled": params.get("autogain_enabled", True),
                        "headroom_db": params.get("headroom_db", -17.0)})

    actions = migrate_legacy_preprocess_config(**cfg)
    loudness = stored.get("loudness")
    if isinstance(loudness, Mapping) and loudness.get("enabled", True):
        params = loudness.get("params", {})
        if isinstance(params, Mapping):
            actions.append(AudioFunctionAction("audio.loudness.normalize", params={
                "target_lufs": params.get("target_lufs", -14.0),
                "true_peak_db": params.get("true_peak", -1.0),
                "lra": params.get("lra", 11.0), "dual_mono": params.get("dual_mono", False),
            }))
    limiter = stored.get("master_limiter")
    if isinstance(limiter, Mapping) and limiter.get("enabled", True):
        params = limiter.get("params", {})
        if isinstance(params, Mapping) and params.get("enabled", True):
            actions.append(AudioFunctionAction("audio.limiter.true_peak", params={
                "ceiling_db": params.get("ceiling_db", -1.0),
                "release_ms": params.get("release_ms", 150.0),
                "lookahead_ms": params.get("lookahead_ms", 5.0),
                "mode": params.get("mode", "transparent"),
                "oversampling": 4 if params.get("enable_oversampling", True) else 1,
            }))
    return actions
