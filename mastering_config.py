from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


def _is_nonzero(value: float, epsilon: float = 0.001) -> bool:
    return abs(value) > epsilon


def _has_nonzero_map(values: Dict[str, float] | None, epsilon: float = 0.001) -> bool:
    if not values:
        return False
    return any(abs(v) > epsilon for v in values.values())


@dataclass(frozen=True)
class MasteringConfig:
    dynamic_eq: bool = False
    stereo_width: bool = False
    deesser: bool = False
    saturation_enabled: bool = False
    saturation_per_band: bool = False
    glue_enabled: bool = False
    stereo_dynamic: bool = False
    auto_band_gain: bool = False
    tone_low_db: float = 0.0
    tone_mid_db: float = 0.0
    tone_high_db: float = 0.0
    tone_tilt_db: float = 0.0
    band_adjust_db: Dict[str, float] | None = None
    band_widths: Dict[str, float] | None = None
    noise_reduction_level: str = "Off"
    declip_level: str = "Off"
    declick_level: str = "Off"
    pink_noise_level: str = "Off"
    repair_enabled: bool = True
    mix_enabled: bool = True

    def needs_preprocess(self) -> bool:
        if self._has_repair_processing():
            return True
        return self._has_mix_or_master_preprocessing()

    def _has_repair_processing(self) -> bool:
        if not self.repair_enabled:
            return False
        return any(
            level != "Off"
            for level in (
                self.noise_reduction_level,
                self.declip_level,
                self.declick_level,
                self.pink_noise_level,
            )
        )

    def _has_mix_or_master_preprocessing(self) -> bool:
        if not self.mix_enabled:
            return False
        return (
            self.dynamic_eq
            or self.stereo_width
            or self.deesser
            or self.saturation_enabled
            or self.saturation_per_band
            or self.stereo_dynamic
            or self.glue_enabled
            or self.auto_band_gain
            or _is_nonzero(self.tone_low_db)
            or _is_nonzero(self.tone_mid_db)
            or _is_nonzero(self.tone_high_db)
            or _is_nonzero(self.tone_tilt_db)
            or _has_nonzero_map(self.band_adjust_db)
            or _has_nonzero_map(self.band_widths)
        )
