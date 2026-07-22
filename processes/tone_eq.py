"""
Proceso Tone EQ — Ecualizador paramétrico profesional.

6 bandas paramétricas con Q independiente + HPF + LPF.
Reemplaza el viejo EQ de 3 bandas fijas (bass/treble/mid).
"""

from typing import Any, Dict, Tuple

from processes.base import BaseProcess, ProcessCategory


class ToneEQProcess(BaseProcess):
    """Ecualizador paramétrico de 6 bandas con HPF/LPF."""

    @property
    def id(self) -> str:
        return "tone_eq"

    @property
    def name(self) -> str:
        return "Tone EQ"

    @property
    def description(self) -> str:
        return "Ecualizador paramétrico 6 bandas + HPF/LPF"

    @property
    def category(self) -> ProcessCategory:
        return ProcessCategory.MIX

    @property
    def default_order(self) -> int:
        return 30

    def get_default_params(self) -> Dict[str, Any]:
        return {
            # 6 bandas paramétricas: (label, freq_default, q_default, gain_default)
            "sub_bass_db": 0.0,       # Sub-bass 45 Hz, shelf_low
            "sub_bass_freq": 45.0,
            "sub_bass_q": 0.7,
            "bass_db": 0.0,           # Bass 120 Hz, shelf_low
            "bass_freq": 120.0,
            "bass_q": 0.7,
            "low_mid_db": 0.0,        # Low-Mid 500 Hz, peak
            "low_mid_freq": 500.0,
            "low_mid_q": 1.0,
            "mid_db": 0.0,            # Mid 2000 Hz, peak
            "mid_freq": 2000.0,
            "mid_q": 1.0,
            "high_mid_db": 0.0,       # High-Mid 6000 Hz, peak
            "high_mid_freq": 6000.0,
            "high_mid_q": 1.0,
            "air_db": 0.0,            # Air 12000 Hz, shelf_high
            "air_freq": 12000.0,
            "air_q": 0.7,
            "tilt_db": 0.0,           # Tilt (-6 a +6 dB, inclina el espectro)
            "hpf_enabled": False,     # High-pass filter
            "hpf_freq": 30.0,         # HPF frequency
            "lpf_enabled": False,     # Low-pass filter  
            "lpf_freq": 18000.0,      # LPF frequency
        }

    def build_filter(
        self,
        input_label: str,
        **kwargs
    ) -> Tuple[str, str]:
        if not self.enabled:
            return "", input_label

        # Obtener parámetros con defaults
        p = lambda k, d: kwargs.get(k, self.get_param(k, d))

        bands = [
            # (db_key, freq_key, q_key, filter_type, label)
            ("sub_bass_db", "sub_bass_freq", "sub_bass_q", "lowshelf", "sub"),
            ("bass_db", "bass_freq", "bass_q", "lowshelf", "bass"),
            ("low_mid_db", "low_mid_freq", "low_mid_q", "peaking", "lm"),
            ("mid_db", "mid_freq", "mid_q", "peaking", "mid"),
            ("high_mid_db", "high_mid_freq", "high_mid_q", "peaking", "hm"),
            ("air_db", "air_freq", "air_q", "highshelf", "air"),
        ]

        tilt_db = p("tilt_db", 0.0)
        hpf_enabled = p("hpf_enabled", False)
        hpf_freq = p("hpf_freq", 30.0)
        lpf_enabled = p("lpf_enabled", False)
        lpf_freq = p("lpf_freq", 18000.0)

        # Verificar si hay cambios
        has_eq = any(abs(p(db_k, 0.0)) > 0.01 for db_k, _, _, _, _ in bands)
        has_tilt = abs(tilt_db) > 0.01
        if not (has_eq or has_tilt or hpf_enabled or lpf_enabled):
            return "", input_label

        parts = []

        # HPF (high-pass = low cut)
        if hpf_enabled and hpf_freq > 0:
            parts.append(f"highpass=f={hpf_freq:.0f}")

        # LPF (low-pass = high cut)
        if lpf_enabled and lpf_freq > 0:
            parts.append(f"lowpass=f={lpf_freq:.0f}")

        # Bandas paramétricas
        for db_key, freq_key, q_key, ftype, _label in bands:
            gain = p(db_key, 0.0)

            # Aplicar tilt: mitad a graves, mitad a agudos
            if ftype == "lowshelf":
                gain -= tilt_db * 0.5
            elif ftype == "highshelf":
                gain += tilt_db * 0.5

            if abs(gain) > 0.01:
                freq = p(freq_key, 500.0)
                q_val = p(q_key, 1.0)
                filter_name = {"lowshelf": "lowshelf", "highshelf": "highshelf"}.get(ftype, "equalizer")
                parts.append(f"{filter_name}=f={freq:.0f}:width_type=q:width={max(0.1, q_val):.3f}:g={gain:.2f}")

        if not parts:
            return "", input_label

        output_label = "tone"
        filter_chain = f"[{input_label}]" + ",".join(parts) + f"[{output_label}]"
        return filter_chain, output_label

    def build_function(self, action, input_label, context, labels):
        action = self.validate_action(action)
        p = action.params
        fid = action.function_id
        if fid == "audio.tone_eq.high_pass":
            expr = f"highpass=f={p.get('frequency_hz', 30.0):.2f}:poles={p.get('poles', 2)}"
        elif fid == "audio.tone_eq.low_pass":
            freq = min(float(p.get("frequency_hz", 18000.0)), context.sample_rate * 0.499)
            expr = f"lowpass=f={freq:.2f}:poles={p.get('poles', 2)}"
        elif fid == "audio.tone_eq.tilt":
            gain = float(p.get("gain_db", 0.0))
            pivot = float(p.get("pivot_hz", 1000.0))
            expr = f"lowshelf=f={pivot:.2f}:width_type=q:width=0.707:g={-gain / 2:.2f},highshelf=f={pivot:.2f}:width_type=q:width=0.707:g={gain / 2:.2f}"
        else:
            freq = min(float(p.get("frequency_hz", 1000.0)), context.sample_rate * 0.499)
            q_val = float(p.get("q", 1.0))
            gain = float(p.get("gain_db", 0.0))
            filter_name = {"low_shelf": "lowshelf", "high_shelf": "highshelf"}.get(p.get("filter_type"), "equalizer")
            expr = f"{filter_name}=f={freq:.2f}:width_type=q:width={q_val:.3f}:g={gain:.2f}"
        output = labels.new(fid, action.target or "out")
        return f"[{input_label}]{expr}[{output}]", output

    def has_changes(self) -> bool:
        p = lambda k, d: self.get_param(k, d)
        bands = ["sub_bass_db", "bass_db", "low_mid_db", "mid_db", "high_mid_db", "air_db"]
        return (
            any(abs(p(k, 0.0)) > 0.01 for k in bands)
            or abs(p("tilt_db", 0.0)) > 0.01
            or p("hpf_enabled", False)
            or p("lpf_enabled", False)
        )
