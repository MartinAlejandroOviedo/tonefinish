"""EQ dinámica reactiva para resonancias y movimiento tonal conservador."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from processes.base import BaseProcess, ProcessCategory


class DynamicEQProcess(BaseProcess):
    @property
    def id(self) -> str:
        return "dynamic_eq"

    @property
    def name(self) -> str:
        return "Dynamic EQ"

    @property
    def description(self) -> str:
        return "Corrección y movimiento tonal reactivos, con ámbito Stereo/Mid/Side"

    @property
    def category(self) -> ProcessCategory:
        return ProcessCategory.MIX

    @property
    def default_order(self) -> int:
        return 35

    def get_default_params(self) -> Dict[str, Any]:
        return {"enabled": True}

    def build_filter(self, input_label: str, **kwargs) -> Tuple[str, str]:
        return "", input_label

    @staticmethod
    def _dynamic_expr(params: Dict[str, Any], *, amount_db: float, mode: str) -> tuple[str, float]:
        frequency = float(params.get("frequency_hz", 3000.0))
        q = float(params.get("q", 2.0))
        threshold_db = float(params.get("threshold_db", -24.0))
        threshold = max(0.000001, min(100.0, 10 ** (threshold_db / 20.0)))
        attack = float(params.get("attack_ms", 20.0))
        release = float(params.get("release_ms", 180.0))
        ratio = float(params.get("ratio", 2.0))
        native_range = max(1.0, abs(amount_db))
        wet_mix = min(1.0, abs(amount_db))
        filter_type = str(params.get("filter_type", "bell"))
        expr = (
            "adynamicequalizer="
            f"threshold={threshold:.8f}:dfrequency={frequency:.2f}:dqfactor={q:.4f}:"
            f"tfrequency={frequency:.2f}:tqfactor={q:.4f}:attack={attack:.2f}:"
            f"release={release:.2f}:ratio={ratio:.3f}:range={native_range:.3f}:"
            f"mode={mode}:dftype=bandpass:tftype={filter_type}:auto=off:precision=double"
        )
        return expr, wet_mix

    @staticmethod
    def _parallel(
        source: str, expr: str, wet_mix: float, output: str, labels,
        function_id: str,
    ) -> list[str]:
        if wet_mix >= 0.999999:
            return [f"[{source}]{expr}[{output}]"]
        dry = labels.new(function_id, "dry")
        wet = labels.new(function_id, "wet")
        processed = labels.new(function_id, "processed")
        return [
            f"[{source}]asplit=2[{dry}][{wet}]",
            f"[{wet}]{expr}[{processed}]",
            f"[{dry}][{processed}]amix=inputs=2:weights={1.0-wet_mix:.6f} {wet_mix:.6f}:normalize=0[{output}]",
        ]

    def build_function(self, action, input_label, context, labels):
        action = self.validate_action(action)
        params = dict(action.params)
        if action.function_id == "audio.dynamic_eq.resonance":
            amount_db = float(params.get("max_reduction_db", 2.0))
            mode = "cutabove"
        else:
            gain_db = float(params.get("gain_db", 0.0))
            amount_db = abs(gain_db)
            mode = "cutabove" if gain_db < 0.0 else "boostabove"

        expr, wet_mix = self._dynamic_expr(params, amount_db=amount_db, mode=mode)
        scope = str(params.get("scope", "stereo"))
        output = labels.new(action.function_id)
        input_name = input_label.strip("[]")
        if scope == "stereo":
            parts = self._parallel(input_name, expr, wet_mix, output, labels, action.function_id)
            return ";".join(parts), output

        ms = labels.new(action.function_id, "ms")
        mid = labels.new(action.function_id, "mid")
        side = labels.new(action.function_id, "side")
        selected = mid if scope == "mid" else side
        untouched = side if scope == "mid" else mid
        processed = labels.new(action.function_id, f"{scope}_processed")
        joined = labels.new(action.function_id, "ms_joined")
        parts = [
            f"[{input_name}]stereotools=mode=lr>ms[{ms}]",
            f"[{ms}]channelsplit=channel_layout=stereo[{mid}][{side}]",
        ]
        parts.extend(self._parallel(selected, expr, wet_mix, processed, labels, action.function_id))
        if scope == "mid":
            parts.append(f"[{processed}][{untouched}]join=inputs=2:channel_layout=stereo[{joined}]")
        else:
            parts.append(f"[{untouched}][{processed}]join=inputs=2:channel_layout=stereo[{joined}]")
        parts.append(f"[{joined}]stereotools=mode=ms>lr[{output}]")
        return ";".join(parts), output
