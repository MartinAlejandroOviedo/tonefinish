from __future__ import annotations

from typing import Dict


def build_dynamic_loudnorm_filter(target_lufs: float, true_peak: float) -> str:
    return (
        f"loudnorm=I={target_lufs}:LRA=11:TP={true_peak}"
        ":linear=false:print_format=summary"
    )


def build_linear_loudnorm_filter(stats: Dict[str, float], target_lufs: float, true_peak: float) -> str:
    return (
        f"loudnorm=I={target_lufs}:LRA=11:TP={true_peak}"
        f":measured_I={stats['input_i']}"
        f":measured_LRA={stats['input_lra']}"
        f":measured_TP={stats['input_tp']}"
        f":measured_thresh={stats['input_thresh']}"
        f":offset={stats['target_offset']}"
        ":linear=true:print_format=summary"
    )

