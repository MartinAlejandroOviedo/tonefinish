# DEPRECATED: v2.0.0: Glue compression reemplazado por band_compression en multiband por banda.
# Este archivo se conserva para compatibilidad con versiones anteriores.

"""
Proceso Glue Compressor.

Compresión suave tipo "glue" para unificar la mezcla.
"""

from typing import Any, Dict, Tuple

from processes.base import BaseProcess, ProcessCategory


class GlueProcess(BaseProcess):
    """
    Compresión tipo Glue para unificar la mezcla.
    
    Un compresor suave con ratios bajos y tiempos medios
    que "pega" los elementos de la mezcla sin comprimir
    de forma agresiva.
    """
    
    @property
    def id(self) -> str:
        return "glue"
    
    @property
    def name(self) -> str:
        return "Glue Compression"
    
    @property
    def description(self) -> str:
        return "Compresión suave para unificar la mezcla"
    
    @property
    def category(self) -> ProcessCategory:
        return ProcessCategory.MIX
    
    @property
    def default_order(self) -> int:
        return 70
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "glue_enabled": False,      # Habilitar glue
            "threshold_db": -18.0,      # Threshold (-40 a 0 dB)
            "ratio": 1.4,               # Ratio (1.0 a 4.0)
            "attack_ms": 20.0,          # Attack (1 a 100 ms)
            "release_ms": 120.0,        # Release (10 a 500 ms)
            "knee_db": 6.0,             # Knee (0=hard, 2-10=soft)
            "makeup_db": 0.0,           # Makeup gain (-12 a +12 dB)
        }
    
    def build_filter(
        self,
        input_label: str,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye el filtro de glue compression.
        
        Args:
            input_label: Etiqueta de entrada
            **kwargs: Parámetros adicionales
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
        """
        if not self.enabled:
            return "", input_label
        
        # Obtener parámetros
        glue_enabled = kwargs.get("glue_enabled", self.get_param("glue_enabled", False))
        
        if not glue_enabled:
            return "", input_label
        
        threshold_db = kwargs.get("threshold_db", self.get_param("threshold_db", -18.0))
        ratio = kwargs.get("ratio", self.get_param("ratio", 1.4))
        attack_ms = kwargs.get("attack_ms", self.get_param("attack_ms", 20.0))
        release_ms = kwargs.get("release_ms", self.get_param("release_ms", 120.0))
        knee_db = kwargs.get("knee_db", self.get_param("knee_db", 6.0))
        makeup_db = kwargs.get("makeup_db", self.get_param("makeup_db", 0.0))
        
        attack_ms = max(0.01, min(2000.0, attack_ms))
        release_ms = max(0.01, min(9000.0, release_ms))
        knee_linear = max(1.0, min(8.0, 10 ** (knee_db / 20.0)))
        makeup_linear = max(1.0, min(64.0, 10 ** (max(0.0, makeup_db) / 20.0)))
        
        glue_filter = (
            f"acompressor="
            f"threshold={threshold_db:.2f}dB:"
            f"ratio={ratio:.2f}:"
            f"attack={attack_ms:.3f}:"
            f"release={release_ms:.3f}:"
            f"knee={knee_linear:.4f}:"
            f"makeup={makeup_linear:.2f}"
        )
        if makeup_db < 0:
            glue_filter += f",volume={makeup_db:.2f}dB"
        
        output_label = "glue"
        filter_chain = f"[{input_label}]{glue_filter}[{output_label}]"
        
        return filter_chain, output_label

    def build_function(self, action, input_label, context, labels):
        action = self.validate_action(action)
        p = action.params
        makeup_db = float(p.get("makeup_db", 0.0))
        makeup = 10 ** (max(0.0, makeup_db) / 20.0)
        knee = max(1.0, min(8.0, 10 ** (float(p.get("knee_db", 6.0)) / 20.0)))
        expr = (
            f"acompressor=threshold={p.get('threshold_db', -18.0):.2f}dB:"
            f"ratio={p.get('ratio', 1.4):.2f}:attack={p.get('attack_ms', 20.0):.4f}:"
            f"release={p.get('release_ms', 120.0):.4f}:knee={knee:.4f}:"
            f"makeup={makeup:.6f}"
        )
        if makeup_db < 0:
            expr += f",volume={makeup_db:.2f}dB"
        output = labels.new(action.function_id)
        return f"[{input_label}]{expr}[{output}]", output
