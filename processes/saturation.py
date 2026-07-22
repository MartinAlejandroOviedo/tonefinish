"""
Proceso de Saturación Global.

Añade calidez y armónicos al audio mediante saturación controlada.
"""

from typing import Any, Dict, Tuple

from processes.base import BaseProcess, ProcessCategory


class SaturationProcess(BaseProcess):
    """
    Saturación global para añadir calidez al audio.
    
    Tipos de saturación:
    - Tape (tanh): Suave y cálida
    - Tube (atan): Más agresiva con armónicos
    
    Control de dry/wet para mezclar con señal original.
    """
    
    @property
    def id(self) -> str:
        return "saturation"
    
    @property
    def name(self) -> str:
        return "Saturación"
    
    @property
    def description(self) -> str:
        return "Añade calidez y armónicos mediante saturación"
    
    @property
    def category(self) -> ProcessCategory:
        return ProcessCategory.MIX
    
    @property
    def default_order(self) -> int:
        return 50
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "saturation_enabled": False,    # Si la saturación está activa
            "saturation_type": "Tape",      # Tipo: Tape, Tube, Exciter
            "drive_db": 0.0,                # Drive (-24 a +24 dB)
            "mix": 0.0,                     # Wet mix (0.0 a 1.0)
            "exciter_freq": 8000.0,         # Exciter crossover (Hz)
            "exciter_amount": 2.0,          # Exciter amount (0-10)
        }

    def _resolve_saturation_type(self, saturation_type: str) -> str:
        """Resuelve el tipo de saturación a filtro ffmpeg."""
        sat_key = saturation_type.strip().lower()
        if sat_key in ("tape", "soft clip", "soft"):
            return "tanh"
        if sat_key in ("tube", "valve"):
            return "atan"
        if sat_key in ("exciter", "excite", "air"):
            return "exciter"
        return "tanh"
    
    def build_filter(
        self,
        input_label: str,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye el filtro de saturación global.
        
        Args:
            input_label: Etiqueta de entrada
            **kwargs: Parámetros adicionales
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
        """
        if not self.enabled:
            return "", input_label
        
        # Obtener parámetros
        saturation_enabled = kwargs.get("saturation_enabled", self.get_param("saturation_enabled", False))
        saturation_type = kwargs.get("saturation_type", self.get_param("saturation_type", "Tape"))
        drive_db = kwargs.get("drive_db", self.get_param("drive_db", 0.0))
        mix = kwargs.get("mix", self.get_param("mix", 0.0))
        sample_rate = int(kwargs.get("sample_rate", 48000))
        oversampling = int(kwargs.get("oversampling", 2))
        
        # Verificar si está habilitado y hay wet
        if not saturation_enabled or mix <= 0.0:
            return "", input_label
        
        # Clampar valores
        drive_db = max(-24.0, min(24.0, drive_db))
        mix = max(0.0, min(1.0, mix))
        dry = 1.0 - mix
        
        sat_filter = self._resolve_saturation_type(saturation_type)
        
        # Labels
        sat_label = "sat"
        sat_wet = "satw"
        sat_out = "sato"
        
        if sat_filter == "exciter":
            # Modo Exciter: realce armónico de agudos sin distorsión
            exciter_freq = kwargs.get("exciter_freq", self.get_param("exciter_freq", 8000.0))
            exciter_amount = kwargs.get("exciter_amount", self.get_param("exciter_amount", 2.0))
            exciter_amount = max(0.0, min(10.0, exciter_amount))
            process_filter = f"aexciter=freq={exciter_freq:.0f}:amount={exciter_amount:.1f}"
        else:
            # Modo Saturación: oversampling 2x → asoftclip → downsample
            osr = min(sample_rate * max(1, oversampling), 192000)
            process_filter = (
                f"aresample={osr},"
                f"volume={drive_db:.2f}dB,"
                f"asoftclip=type={sat_filter}:threshold=1:output=1,"
                f"volume={-max(0.0, drive_db):.2f}dB,"
                f"aresample={sample_rate}"
            )
        
        # Cadena con dry/wet
        sat_chain = ";".join([
            f"[{input_label}]asplit=2[{sat_label}][{sat_wet}]",
            f"[{sat_wet}]{process_filter}[{sat_wet}p]",
            f"[{sat_label}][{sat_wet}p]amix=inputs=2:weights={dry:.2f} {mix:.2f}[{sat_out}]",
        ])
        
        return sat_chain, sat_out

    def build_function(self, action, input_label, context, labels):
        action = self.validate_action(action)
        p = action.params
        fid = action.function_id
        if fid == "audio.saturation.hard_clip":
            ceiling = 10 ** (float(p.get("ceiling_db", -1.5)) / 20.0)
            output = labels.new(fid)
            return (
                f"[{input_label}]asoftclip=type=hard:threshold={ceiling:.6f}:output=1[{output}]",
                output,
            )
        dry_label = labels.new(fid, "dry")
        wet_label = labels.new(fid, "wet")
        processed = labels.new(fid, "processed")
        output = labels.new(fid)
        mix = float(p.get("mix", 0.0))
        if fid == "audio.saturation.exciter":
            expr = f"aexciter=freq={p.get('frequency_hz', 8000.0):.2f}:amount={p.get('amount', 2.0):.2f}"
        else:
            drive = float(p.get("drive_db", 0.0))
            factor = int(p.get("oversampling", 2))
            oversampled = min(context.sample_rate * factor, 192000)
            clip_type = self._resolve_saturation_type(str(p.get("type", "Tape")))
            expr = (
                f"aresample={oversampled},volume={drive:.2f}dB,"
                f"asoftclip=type={clip_type}:threshold=1:output=1,"
                f"volume={-max(0.0, drive):.2f}dB,"
                f"aresample={context.sample_rate}"
            )
        chain = ";".join((
            f"[{input_label}]asplit=2[{dry_label}][{wet_label}]",
            f"[{wet_label}]{expr}[{processed}]",
            f"[{dry_label}][{processed}]amix=inputs=2:weights={1.0 - mix:.6f} {mix:.6f}:normalize=0[{output}]",
        ))
        return chain, output
