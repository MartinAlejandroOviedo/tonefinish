"""Plugins complementarios conservadores controlados por evidencia."""
from typing import Any, Dict, Tuple
from processes.base import BaseProcess, ProcessCategory
from processes.dynamic_eq import DynamicEQProcess

class _ComplementaryBase(BaseProcess):
    @property
    def category(self): return ProcessCategory.MIX
    def get_default_params(self) -> Dict[str, Any]: return {"enabled": True}
    def build_filter(self, input_label: str, **kwargs) -> Tuple[str, str]: return "", input_label

class TransientProcess(_ComplementaryBase):
    @property
    def id(self): return "transient"
    @property
    def name(self): return "Transient Dynamic Control"
    @property
    def description(self): return "Suaviza o recupera ataques medidos"
    @property
    def default_order(self): return 42
    def build_function(self, action, input_label, context, labels):
        action=self.validate_action(action); p=dict(action.params); amount=float(p.get("amount_db",0))
        output=labels.new(action.function_id); attack=float(p.get("attack_ms",10)); release=float(p.get("release_ms",120))
        if amount < 0:
            ratio=1.0+abs(amount)*0.8
            expr=f"acompressor=threshold={float(p.get('threshold_db',-18))}dB:ratio={ratio:.3f}:attack={attack:.2f}:release={release:.2f}:makeup=1"
        else:
            # Expansión ascendente moderada con curva continua; sin makeup global.
            expr=f"compand=attacks={attack/1000:.4f}:decays={release/1000:.4f}:points=-80/-80|-24/-24|0/{amount:.3f}:soft-knee=3:gain=0"
        return f"[{input_label.strip('[]')}]{expr}[{output}]", output

class StereoGuardProcess(_ComplementaryBase):
    @property
    def id(self): return "stereo_guard"
    @property
    def name(self): return "Stereo Correlation Guard"
    @property
    def description(self): return "Corrige ancho sólo cuando la correlación lo permite"
    @property
    def default_order(self): return 44
    def build_function(self, action, input_label, context, labels):
        action=self.validate_action(action); width=float(action.params.get("width",1)); output=labels.new(action.function_id)
        return f"[{input_label.strip('[]')}]stereotools=mlev=1:slev={max(0.015625,width):.6f}[{output}]", output

class LowEndProcess(_ComplementaryBase):
    @property
    def id(self): return "low_end"
    @property
    def name(self): return "Low End Dynamic Balance"
    @property
    def description(self): return "Balance dinámico de graves con ganancia firmada"
    @property
    def default_order(self): return 32
    def build_function(self, action, input_label, context, labels):
        action=self.validate_action(action); p=dict(action.params); gain=float(p.get("gain_db",0))
        expr,mix=DynamicEQProcess._dynamic_expr(p,amount_db=abs(gain),mode="cutabove" if gain<0 else "boostabove")
        output=labels.new(action.function_id); parts=DynamicEQProcess._parallel(input_label.strip("[]"),expr,mix,output,labels,action.function_id)
        return ";".join(parts),output

class SpectralProcess(_ComplementaryBase):
    @property
    def id(self): return "spectral"
    @property
    def name(self): return "Spectral Dynamics"
    @property
    def description(self): return "Reduce dureza amplia o recupera claridad medida"
    @property
    def default_order(self): return 39
    def build_function(self, action, input_label, context, labels):
        action=self.validate_action(action); p=dict(action.params)
        if action.function_id=="audio.spectral.deharsh": amount=-float(p.get("max_reduction_db",1))
        else: amount=float(p.get("max_boost_db",0.5))
        expr,mix=DynamicEQProcess._dynamic_expr(p,amount_db=abs(amount),mode="cutabove" if amount<0 else "boostabove")
        output=labels.new(action.function_id); parts=DynamicEQProcess._parallel(input_label.strip("[]"),expr,mix,output,labels,action.function_id)
        return ";".join(parts),output
