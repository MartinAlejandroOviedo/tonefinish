"""
Proceso AutoGain.

Sistema de ganancia automática con:
- Limitadores suaves entre procesos para evitar saturación
- Normalización final de pico a -1dB
"""

from typing import Any, Dict, Tuple

from processes.base import BaseProcess, ProcessCategory


class AutoGainProcess(BaseProcess):
    """
    Sistema AutoGain para control de niveles.
    
    Funciones:
    1. Headroom: Reduce el volumen al inicio (-17dB) para evitar saturación
    2. Inter-process Limiters: Limitadores suaves después de cada proceso
    3. Final Peak Normalization: Normaliza el pico final a -1dB
    
    Esto asegura que el audio nunca sature durante el procesamiento
    y tenga un nivel consistente antes de loudnorm.
    """
    
    @property
    def id(self) -> str:
        return "autogain"
    
    @property
    def name(self) -> str:
        return "AutoGain"
    
    @property
    def description(self) -> str:
        return "Control automático de niveles con limitadores y normalización"
    
    @property
    def category(self) -> ProcessCategory:
        return ProcessCategory.MASTER
    
    @property
    def default_order(self) -> int:
        return 80  # Después de todos los procesos de mezcla
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "autogain_enabled": True,       # Habilitar AutoGain
            "headroom_db": -17.0,           # Headroom inicial
            "limiter_limit": 1.0,           # Límite (lineal, 1.0 = 0dB)
            "limiter_attack": 0.1,          # Attack del limitador
            "limiter_release": 50.0,        # Release del limitador
            "final_peak_db": -3.0,          # Pico previo a loudness
            "dynaudnorm_maxgain": 6.0,      # Ganancia máxima de dynaudnorm
            
            # Control adaptativo de saturación
            "adaptive_saturation_control": False,  # Control adaptativo de volumen basado en THD
            "target_crest_factor_db": 12.0,        # Crest factor objetivo (8-18 dB)
            "saturation_compensation_db": 0.0,     # Compensación adicional si detecta saturación
        }
    
    def build_headroom_filter(
        self,
        input_label: str,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye el filtro de headroom inicial.
        
        Reduce el volumen para evitar saturación durante procesamiento.
        
        Args:
            input_label: Etiqueta de entrada
            **kwargs: Parámetros adicionales
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
        """
        if not self.enabled:
            return "", input_label
        
        headroom_db = kwargs.get("headroom_db", self.get_param("headroom_db", -17.0))
        
        output_label = "hr"
        filter_chain = f"[{input_label}]volume={headroom_db:.1f}dB[{output_label}]"
        
        return filter_chain, output_label
    
    def build_limiter_filter(
        self,
        input_label: str,
        stage_name: str,
        limiter_index: int = 0,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye un limitador suave para después de un proceso.
        
        Args:
            input_label: Etiqueta de entrada
            stage_name: Nombre del stage (para logging)
            limiter_index: Índice único para el label
            **kwargs: Parámetros adicionales
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
        """
        autogain_enabled = kwargs.get("autogain_enabled", self.get_param("autogain_enabled", True))
        
        if not self.enabled or not autogain_enabled:
            return "", input_label
        
        limit = kwargs.get("limiter_limit", self.get_param("limiter_limit", 1.0))
        attack = kwargs.get("limiter_attack", self.get_param("limiter_attack", 0.1))
        release = kwargs.get("limiter_release", self.get_param("limiter_release", 50.0))
        
        output_label = f"ag{limiter_index}"
        filter_chain = (
            f"[{input_label}]alimiter=limit={limit:.6f}:"
            f"attack={attack:.1f}:release={release:.0f}:level=false[{output_label}]"
        )
        
        return filter_chain, output_label
    
    def build_final_normalization_filter(
        self,
        input_label: str,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye el filtro de normalización final de pico.
        
        Usa alimiter en vez de dynaudnorm para evitar pumping.
        Solo limita picos, no modifica el nivel RMS.
        """
        autogain_enabled = kwargs.get("autogain_enabled", self.get_param("autogain_enabled", True))
        
        if not self.enabled or not autogain_enabled:
            return "", input_label
        
        final_peak_db = kwargs.get("final_peak_db", self.get_param("final_peak_db", -3.0))
        
        # Convertir dB a lineal
        peak_linear = 10 ** (final_peak_db / 20.0)
        
        output_label = "agfinal"
        # alimiter transparente: solo recorta picos, sin auto-level
        filter_chain = (
            f"[{input_label}]alimiter=limit={peak_linear:.6f}:"
            f"attack=1.0:release=50.0:level=false[{output_label}]"
        )
        
        return filter_chain, output_label

    def build_function(self, action, input_label, context, labels):
        action = self.validate_action(action)
        p = action.params
        fid = action.function_id
        if fid == "audio.autogain.headroom":
            expr = f"volume={p.get('gain_db', -17.0):.2f}dB"
        elif fid == "audio.autogain.output_gain":
            expr = f"volume={p.get('gain_db', 0.0):.2f}dB"
        elif fid == "audio.autogain.interstage_limiter":
            ceiling = 10 ** (float(p.get("ceiling_db", 0.0)) / 20.0)
            expr = (
                f"alimiter=limit={ceiling:.6f}:attack={p.get('attack_ms', 1.0):.2f}:"
                f"release={p.get('release_ms', 50.0):.2f}:level=false:latency=true"
            )
        else:
            ceiling = 10 ** (float(p.get("ceiling_db", -3.0)) / 20.0)
            expr = f"alimiter=limit={ceiling:.6f}:attack=1:release=50:level=false:latency=true"
        output = labels.new(fid)
        return f"[{input_label}]{expr}[{output}]", output
    
    def build_filter(
        self,
        input_label: str,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye la normalización final (solo).
        
        Para el flujo completo, usar los métodos individuales:
        - build_headroom_filter() al inicio
        - build_limiter_filter() después de cada proceso
        - build_final_normalization_filter() al final
        
        Args:
            input_label: Etiqueta de entrada
            **kwargs: Parámetros adicionales
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
        """
        return self.build_final_normalization_filter(input_label, **kwargs)
