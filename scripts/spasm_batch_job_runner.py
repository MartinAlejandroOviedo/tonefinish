#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.workers import BatchWorker  # noqa: E402


def _write_status(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: spasm_batch_job_runner.py <job_id> <payload.json> <status.json>", file=sys.stderr)
        return 2

    job_id = sys.argv[1]
    payload_path = pathlib.Path(sys.argv[2])
    status_path = pathlib.Path(sys.argv[3])
    cancel_path = status_path.with_suffix(".cancel")

    payload = json.loads(payload_path.read_text(encoding="utf-8"))

    files = [pathlib.Path(p) for p in payload["files"]]
    output_dir = pathlib.Path(payload["output_dir"]) if payload.get("output_dir") else None
    checkpoint_path = pathlib.Path(payload["checkpoint_path"]) if payload.get("checkpoint_path") else None

    worker = BatchWorker(
        files=files,
        output_dir=output_dir,
        suffix=payload["suffix"],
        target_lufs=float(payload["target_lufs"]),
        true_peak=float(payload["true_peak"]),
        overwrite=bool(payload["overwrite"]),
        verbose=bool(payload["verbose"]),
        dynamic_eq=bool(payload["dynamic_eq"]),
        master_limiter_enabled=bool(payload["master_limiter_enabled"]),
        master_limiter_mode=str(payload["master_limiter_mode"]),
        master_limiter_ceiling_db=float(payload["master_limiter_ceiling_db"]),
        master_limiter_release_ms=float(payload["master_limiter_release_ms"]),
        master_limiter_lookahead_ms=float(payload["master_limiter_lookahead_ms"]),
        output_sr=payload.get("output_sr"),
        output_bit_depth=payload.get("output_bit_depth"),
        output_format=payload.get("output_format"),
        stereo_width=bool(payload["stereo_width"]),
        loudness_preset=str(payload["loudness_preset"]),
        output_preset=str(payload["output_preset"]),
        deesser=bool(payload["deesser"]),
        deesser_freq_hz=float(payload["deesser_freq_hz"]),
        deesser_intensity=float(payload["deesser_intensity"]),
        tone_low_db=float(payload["tone_low_db"]),
        sub_bass_db=float(payload["sub_bass_db"]),
        tone_mid_db=float(payload["tone_mid_db"]),
        tone_high_db=float(payload["tone_high_db"]),
        tone_tilt_db=float(payload["tone_tilt_db"]),
        band_adjust_db=dict(payload["band_adjust_db"]),
        band_widths=dict(payload["band_widths"]),
        auto_band_gain=bool(payload["auto_band_gain"]),
        saturation_enabled=bool(payload["saturation_enabled"]),
        saturation_per_band=bool(payload["saturation_per_band"]),
        saturation_type=str(payload["saturation_type"]),
        saturation_drive_db=float(payload["saturation_drive_db"]),
        saturation_mix=float(payload["saturation_mix"]),
        saturation_band_drive_db=dict(payload["saturation_band_drive_db"]),
        saturation_band_mix=dict(payload["saturation_band_mix"]),
        process_order=list(payload["process_order"]),
        stereo_dynamic=bool(payload["stereo_dynamic"]),
        stereo_dynamic_band_mix=list(payload["stereo_dynamic_band_mix"]),
        stereo_dynamic_threshold_db=float(payload["stereo_dynamic_threshold_db"]),
        stereo_dynamic_ratio=float(payload["stereo_dynamic_ratio"]),
        stereo_dynamic_attack_ms=float(payload["stereo_dynamic_attack_ms"]),
        stereo_dynamic_release_ms=float(payload["stereo_dynamic_release_ms"]),
        stereo_dynamic_mix=float(payload["stereo_dynamic_mix"]),
        glue_enabled=bool(payload["glue_enabled"]),
        glue_threshold_db=float(payload["glue_threshold_db"]),
        glue_ratio=float(payload["glue_ratio"]),
        glue_attack_ms=float(payload["glue_attack_ms"]),
        glue_release_ms=float(payload["glue_release_ms"]),
        glue_makeup_db=float(payload["glue_makeup_db"]),
        limiter_ceiling_db=float(payload["limiter_ceiling_db"]),
        limiter_release_ms=float(payload["limiter_release_ms"]),
        metadata=dict(payload["metadata"]),
        fade_in=float(payload["fade_in"]),
        fade_out=float(payload["fade_out"]),
        fade_overrides=dict(payload.get("fade_overrides") or {}),
        transparent_mode=bool(payload["transparent_mode"]),
        headroom_db=float(payload["headroom_db"]),
        noise_reduction_level=str(payload["noise_reduction_level"]),
        declip_level=str(payload["declip_level"]),
        declick_level=str(payload["declick_level"]),
        pink_noise_level=str(payload["pink_noise_level"]),
        repair_enabled=bool(payload["repair_enabled"]),
        mix_enabled=bool(payload["mix_enabled"]),
        master_enabled=bool(payload["master_enabled"]),
        autogain_enabled=bool(payload["autogain_enabled"]),
        autogain_maxgain=payload.get("autogain_maxgain"),
        multiband_limiter_enabled=bool(payload["multiband_limiter_enabled"]),
        multiband_limiter_thresholds=dict(payload.get("multiband_limiter_thresholds") or {}),
        mts_enabled=bool(payload.get("mts_enabled", True)),
        checkpoint_path=checkpoint_path,
        resume_completed_files=set(),
        cancel_token_path=cancel_path,
    )

    queued_at: float | None = None
    try:
        if status_path.exists():
            existing = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                maybe_q = existing.get("queued_at")
                if isinstance(maybe_q, (int, float)):
                    queued_at = float(maybe_q)
    except Exception:
        queued_at = None

    started_at = time.time()
    queue_wait_ms = (
        max(0, int((started_at - queued_at) * 1000))
        if isinstance(queued_at, (int, float))
        else None
    )

    state: dict[str, Any] = {
        "job_id": job_id,
        "state": "running",
        "progress": 0.0,
        "message": "Iniciando...",
        "current": 0,
        "total": len(files),
        "queued_at": queued_at,
        "started_at": started_at,
        "queue_wait_ms": queue_wait_ms,
        "updated_at": started_at,
        "result_message": None,
        "results": None,
        "error": None,
    }
    _write_status(status_path, state)

    def on_progress(message: str, current: int, total: int) -> None:
        total_safe = max(1, int(total or 1))
        progress = max(0.0, min(100.0, (float(current) / total_safe) * 100.0))
        state.update(
            {
                "state": "running",
                "progress": progress,
                "message": message,
                "current": int(current),
                "total": int(total),
                "updated_at": time.time(),
            }
        )
        _write_status(status_path, state)

    def on_processing_progress(percent: float, time_str: str) -> None:
        state.update(
            {
                "processing_percent": float(percent),
                "processing_time": time_str,
                "updated_at": time.time(),
            }
        )
        _write_status(status_path, state)

    def on_finished(message: str, results: object) -> None:
        state.update(
            {
                "state": "done",
                "progress": 100.0,
                "message": "Completado",
                "result_message": message,
                "results": results,
                "updated_at": time.time(),
            }
        )
        _write_status(status_path, state)

    def on_error(message: str) -> None:
        final_state = "cancelled" if cancel_path.exists() else "error"
        state.update(
            {
                "state": final_state,
                "error": message,
                "message": message,
                "updated_at": time.time(),
            }
        )
        _write_status(status_path, state)

    worker.progress.connect(on_progress)
    worker.processing_progress.connect(on_processing_progress)
    worker.finished.connect(on_finished)
    worker.error.connect(on_error)

    try:
        worker.run()
    except Exception as exc:
        on_error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
