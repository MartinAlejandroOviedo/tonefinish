"""Auditoría reproducible de decisiones y resultados del procesamiento de audio."""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
from typing import Any, Mapping, Sequence

from .catalog import function_registry
from .contracts import AudioFunctionAction


TAIL_FUNCTION_IDS = frozenset({
    "audio.repair.trim_silence", "audio.saturation.hard_clip",
    "audio.autogain.output_gain", "audio.loudness.normalize",
    "audio.loudness.fade_in", "audio.loudness.fade_out", "audio.limiter.true_peak",
})


def fingerprint_audio_source(path: str | pathlib.Path) -> str:
    """Huella del contenido; no depende del nombre ni de la fecha del archivo."""
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def verify_audio_source(path: str | pathlib.Path, expected_fingerprint: str) -> str:
    actual = fingerprint_audio_source(path)
    if actual != expected_fingerprint:
        raise ValueError(
            "El audio cambió después del análisis IA; la estrategia vinculada no se ejecutará"
        )
    return actual


def catalog_fingerprint() -> str:
    payload = json.dumps(
        function_registry.to_dict(), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def effective_execution_actions(
    actions: Sequence[Mapping[str, Any] | AudioFunctionAction],
) -> list[AudioFunctionAction]:
    """Devuelve el orden efectivo de las etapas usado por audio_processing."""
    canonical = [
        item if isinstance(item, AudioFunctionAction) else AudioFunctionAction.from_dict(item)
        for item in actions
    ]
    enabled = [function_registry.validate(item) for item in canonical if item.enabled]
    preprocess = [item for item in enabled if item.function_id not in TAIL_FUNCTION_IDS]
    tail = [
        item for item in enabled
        if item.function_id in TAIL_FUNCTION_IDS
        and item.function_id != "audio.limiter.true_peak"
    ]
    limiter = [item for item in enabled if item.function_id == "audio.limiter.true_peak"]
    return [*preprocess, *tail, *limiter]


def _metric(stats: Mapping[str, Any], *names: str) -> float | None:
    for name in names:
        try:
            value = float(stats[name])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return None


def build_execution_audit(
    actions: Sequence[Mapping[str, Any] | AudioFunctionAction], *,
    before_stats: Mapping[str, Any], after_stats: Mapping[str, Any],
    target_lufs: float, true_peak: float,
    loudness_tolerance_lu: float = 0.3, peak_tolerance_db: float = 0.2,
) -> dict[str, Any]:
    """Compara el render con sus objetivos y documenta cada función ejecutada."""
    validated = effective_execution_actions(actions)
    before_lufs = _metric(before_stats, "input_i", "output_i")
    before_peak = _metric(before_stats, "input_tp", "output_tp")
    after_lufs = _metric(after_stats, "output_i", "input_i")
    after_peak = _metric(after_stats, "output_tp", "input_tp")

    if after_lufs is None:
        loudness_check = {"passed": False, "error": "métrica ausente"}
    else:
        error_lu = after_lufs - float(target_lufs)
        loudness_check = {
            "target_lufs": float(target_lufs), "measured_lufs": after_lufs,
            "error_lu": round(error_lu, 3),
            "passed": abs(error_lu) <= loudness_tolerance_lu,
            "tolerance_lu": loudness_tolerance_lu,
        }
    if after_peak is None:
        peak_check = {"passed": False, "error": "métrica ausente"}
    else:
        overshoot = after_peak - float(true_peak)
        peak_check = {
            "ceiling_db": float(true_peak), "measured_db": after_peak,
            "overshoot_db": round(overshoot, 3),
            "passed": overshoot <= peak_tolerance_db,
            "tolerance_db": peak_tolerance_db,
        }
    checks = {"loudness": loudness_check, "true_peak": peak_check}
    passed = all(bool(item.get("passed")) for item in checks.values())
    operation_summary = {
        operation: sum(1 for action in validated if action.operation == operation)
        for operation in ("cut", "boost", "attenuate", "expand", "narrow", "protect")
    }
    return {
        "status": "passed" if passed else "warning",
        "catalog_fingerprint": catalog_fingerprint(),
        "targets": {"lufs": float(target_lufs), "true_peak_db": float(true_peak)},
        "before": {"lufs": before_lufs, "true_peak_db": before_peak},
        "after": {"lufs": after_lufs, "true_peak_db": after_peak},
        "checks": checks,
        "operation_summary": operation_summary,
        "action_results": [
            {
                "index": index, "function_id": action.function_id,
                "target": action.target, "status": "executed",
                "operation": action.operation, "evidence": dict(action.evidence),
                "params": dict(action.params),
                "action_fingerprint": "sha256:" + hashlib.sha256(
                    json.dumps(action.to_dict(), sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "reason": action.reason, "confidence": action.confidence,
            }
            for index, action in enumerate(validated)
        ],
    }
