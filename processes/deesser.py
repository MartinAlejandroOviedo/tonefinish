# DEPRECATED: v2.0.0: De-esser global reemplazado por EQ + compresión en bandas agudas del multiband.
# Este archivo se conserva para compatibilidad con versiones anteriores.

"""
Proceso De-Esser.

Reduce las frecuencias sibilantes (s, sh, ch) del audio.
"""

from typing import Any, Dict, Tuple

from processes.base import BaseProcess, ProcessCategory


class DeesserProcess(BaseProcess):
    """
    De-esser para reducir sibilancias.
    
    Usa el filtro deesser de ffmpeg con frecuencia y intensidad configurables.
    La frecuencia se normaliza automáticamente según el sample rate.
    """
    
    @property
    def id(self) -> str:
        return "deesser"
    
    @property
    def name(self) -> str:
        return "De-Esser"
    
    @property
    def description(self) -> str:
        return "Reduce frecuencias sibilantes (s, sh, ch)"
    
    @property
    def category(self) -> ProcessCategory:
        return ProcessCategory.MIX
    
    @property
    def default_order(self) -> int:
        return 20  # Después de repair
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "enabled": False,           # De-esser deshabilitado por defecto
            "frequency_hz": 6000.0,     # Frecuencia objetivo (típico: 4000-8000 Hz)
            "intensity": 1.0,           # Intensidad (0.2-1.0)
        }
    
    def build_filter(
        self,
        input_label: str,
        sample_rate: int = 44100,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye el filtro de-esser.
        
        Args:
            input_label: Etiqueta de entrada
            sample_rate: Sample rate del audio para normalizar frecuencia
            **kwargs: Parámetros adicionales
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
        """
        # Verificar si proceso interno está habilitado
        process_enabled = kwargs.get("enabled", self.get_param("enabled", False))
        
        if not self.enabled or not process_enabled:
            return "", input_label
        
        # Obtener parámetros
        frequency_hz = kwargs.get("frequency_hz", self.get_param("frequency_hz", 6000.0))
        intensity = kwargs.get("intensity", self.get_param("intensity", 1.0))
        
        # Clampar intensidad
        intensity = max(0.0, min(1.5, intensity))
        i_val = min(1.0, intensity / 1.5)
        s_val = min(1.0, intensity / 1.5)
        
        # Normalizar frecuencia al rango 0-1 basado en Nyquist
        if sample_rate:
            nyquist = sample_rate / 2.0
            normalized_freq = max(0.0, min(1.0, frequency_hz / nyquist))
        else:
            normalized_freq = 0.5  # Default si no hay sample rate
        
        deesser_filter = f"deesser=i={i_val:.2f}:m=0.5:f={normalized_freq:.4f}:s={s_val:.2f}"
        
        output_label = "des"
        filter_chain = f"[{input_label}]{deesser_filter}[{output_label}]"
        
        return filter_chain, output_label

    def build_function(self, action, input_label, context, labels):
        action = self.validate_action(action)
        frequency = min(float(action.params.get("frequency_hz", 6000.0)), context.sample_rate * 0.499)
        normalized = frequency / (context.sample_rate / 2.0)
        intensity = float(action.params.get("intensity", 0.7)) / 1.5
        expr = f"deesser=i={intensity:.4f}:m=0.5:f={normalized:.6f}:s={intensity:.4f}"
        output = labels.new(action.function_id)
        return f"[{input_label}]{expr}[{output}]", output
    
    def resolve_intensity(
        self,
        noise_level: str,
        declick_level: str,
        base_intensity: float = 1.0,
        budget_db: float = 2.5,
    ) -> float:
        """
        Reduce la intensidad del de-esser si hay otras reducciones activas.
        
        Evita que se aplique demasiada reducción en conjunto.
        
        Args:
            noise_level: Nivel de reducción de ruido activo
            declick_level: Nivel de declick activo
            base_intensity: Intensidad base del de-esser
            budget_db: Presupuesto de reducción total
            
        Returns:
            Intensidad ajustada (0.2-1.0)
        """
        def level_impact(level: str, base: float, medium: float, high: float) -> float:
            key = level.strip().lower()
            if key in ("off", "apagado"):
                return 0.0
            if key == "leve":
                return base
            if key == "medio":
                return medium
            if key == "alto":
                return high
            return base
        
        noise_impact = level_impact(noise_level, base=0.6, medium=1.2, high=1.8)
        declick_impact = level_impact(declick_level, base=0.9, medium=1.5, high=2.1)
        
        used = noise_impact + declick_impact
        remaining = max(0.0, budget_db - used)
        
        if budget_db <= 0:
            return base_intensity
        
        intensity = remaining / budget_db
        return max(0.2, min(1.0, intensity * base_intensity))
