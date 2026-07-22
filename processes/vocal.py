"""Procesamiento vocal conservador sobre la imagen central de un master estéreo."""
from typing import Any, Dict, Tuple
from processes.base import BaseProcess, ProcessCategory
from processes.dynamic_eq import DynamicEQProcess

class VocalProcess(BaseProcess):
    @property
    def id(self): return "vocal"
    @property
    def name(self): return "Vocal Center"
    @property
    def description(self): return "Suaviza resonancias y timbre metálico estimados en Mid"
    @property
    def category(self): return ProcessCategory.MIX
    @property
    def default_order(self): return 37
    def get_default_params(self) -> Dict[str, Any]: return {"enabled": True}
    def build_filter(self, input_label: str, **kwargs) -> Tuple[str, str]: return "", input_label

    def build_function(self, action, input_label, context, labels):
        action = self.validate_action(action); p = dict(action.params)
        source = input_label.strip("[]")
        ms = labels.new(action.function_id, "ms"); mid = labels.new(action.function_id, "mid")
        side = labels.new(action.function_id, "side"); processed = labels.new(action.function_id, "processed")
        joined = labels.new(action.function_id, "joined"); output = labels.new(action.function_id)
        parts = [f"[{source}]stereotools=mode=lr>ms[{ms}]",
                 f"[{ms}]channelsplit=channel_layout=stereo[{mid}][{side}]"]
        if action.function_id == "audio.vocal.resonance_suppressor":
            expr, amount = DynamicEQProcess._dynamic_expr(
                p, amount_db=float(p.get("max_reduction_db", 1.5)), mode="cutabove")
            parts.extend(DynamicEQProcess._parallel(mid, expr, amount, processed, labels, action.function_id))
        else:
            dry = labels.new(action.function_id, "dry"); wet = labels.new(action.function_id, "wet")
            eq_out = labels.new(action.function_id, "eq"); mix = float(p.get("mix", 0.25))
            chain = (
                f"equalizer=f={float(p.get('body_frequency_hz',300)):.2f}:t=q:w=0.8:g={float(p.get('body_gain_db',0)):.3f},"
                f"equalizer=f={float(p.get('harshness_frequency_hz',3500)):.2f}:t=q:w=1.1:g={-float(p.get('harshness_reduction_db',0)):.3f},"
                f"highshelf=f={float(p.get('air_frequency_hz',8500)):.2f}:g={-float(p.get('air_reduction_db',0)):.3f}")
            parts.extend([f"[{mid}]asplit=2[{dry}][{wet}]", f"[{wet}]{chain}[{eq_out}]",
                          f"[{dry}][{eq_out}]amix=inputs=2:weights={1-mix:.6f} {mix:.6f}:normalize=0[{processed}]"])
        parts.extend([f"[{processed}][{side}]join=inputs=2:channel_layout=stereo[{joined}]",
                      f"[{joined}]stereotools=mode=ms>lr[{output}]"])
        return ";".join(parts), output
