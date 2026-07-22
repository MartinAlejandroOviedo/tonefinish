"""
Limitador Maestro Final - Unificado.

Reemplaza master_limiter + brickwall con un limitador True Peak compliant.
Este es el último proceso antes de la salida final.
"""

from typing import Any, Dict, Tuple

from processes.base import BaseProcess, ProcessCategory


class MasterLimiterProcess(BaseProcess):
    """
    Limitador maestro final con True Peak limiting.
    
    Características:
    - True Peak limiting (ISP - Inter-Sample Peak detection)
    - Lookahead configurable
    - Modos: transparent, musical, aggressive
    - Reemplaza master_limiter + brickwall
    
    Este es el último proceso de la cadena, garantiza:
    - No clipping en True Peak
    - Protección contra ISP (Inter-Sample Peaks)
    - Loudness final objetivo
    """
    
    @property
    def id(self) -> str:
        return "master_limiter"
    
    @property
    def name(self) -> str:
        return "Master Limiter"
    
    @property
    def description(self) -> str:
        return "Limitador maestro final con True Peak limiting"
    
    @property
    def category(self) -> ProcessCategory:
        return ProcessCategory.MASTER
    
    @property
    def default_order(self) -> int:
        return 85  # Después de AutoGain (80), antes de Loudness (90)
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "enabled": True,                    # Limitador maestro siempre activo por seguridad
            "mode": "transparent",              # transparent, musical, aggressive
            "ceiling_db": -1.0,                 # True Peak ceiling (-3.0 a 0.0 dB)
            "release_ms": 150.0,                # Release time (10 - 1000 ms)
            "lookahead_ms": 5.0,                # Lookahead (0.1 - 20 ms)
            "enable_oversampling": True,        # Oversampling para True Peak detection
        }
    
    def _get_mode_params(self, mode: str) -> Dict[str, float]:
        """
        Obtiene parámetros según el modo seleccionado.
        
        Returns:
            Dict con attack, release_mult, threshold_offset
        """
        modes = {
            "transparent": {
                "attack": 1.0,          # Attack rápido pero suave (mínimo 1.0ms)
                "release_mult": 1.0,    # Release normal
                "threshold_offset": 0.0,  # Sin offset
            },
            "musical": {
                "attack": 1.5,          # Attack más lento
                "release_mult": 1.3,    # Release más lento (más pump)
                "threshold_offset": -0.3,  # Threshold ligeramente más bajo
            },
            "aggressive": {
                "attack": 1.0,          # Attack rápido (mínimo 1.0ms para FFmpeg)
                "release_mult": 0.7,    # Release más rápido
                "threshold_offset": -0.5,  # Threshold más bajo (más limiting)
            },
        }
        return modes.get(mode, modes["transparent"])
    
    def build_filter(
        self,
        input_label: str,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye el filtro de limitador maestro.
        
        Usa alimiter de FFmpeg con parámetros optimizados para True Peak.
        
        Args:
            input_label: Etiqueta de entrada
            **kwargs: Parámetros adicionales
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
        """
        if not self.enabled:
            return "", input_label
        
        # Obtener parámetros
        enabled = kwargs.get("enabled", self.get_param("enabled", True))
        if not enabled:
            return "", input_label
        
        mode = kwargs.get("mode", self.get_param("mode", "transparent"))
        ceiling_db = kwargs.get("ceiling_db", self.get_param("ceiling_db", -1.0))
        release_ms = kwargs.get("release_ms", self.get_param("release_ms", 150.0))
        lookahead_ms = kwargs.get("lookahead_ms", self.get_param("lookahead_ms", 5.0))
        enable_oversampling = kwargs.get("enable_oversampling", self.get_param("enable_oversampling", True))
        sample_rate = kwargs.get("sample_rate")  # opcional (Hz)
        
        # Clampar valores
        ceiling_db = max(-3.0, min(0.0, ceiling_db))
        release_ms = max(10.0, min(1000.0, release_ms))
        lookahead_ms = max(0.1, min(20.0, lookahead_ms))
        
        # Obtener parámetros del modo
        mode_params = self._get_mode_params(mode)
        attack_ms = max(1.0, mode_params["attack"])  # Mínimo 1.0ms para evitar errores de FFmpeg
        release_adjusted = release_ms * mode_params["release_mult"]
        
        # El modo modifica la ganancia previa y, por tanto, cuánto trabaja el limitador.
        input_gain_db = -mode_params["threshold_offset"]
        
        # Convertir ceiling y threshold a valores lineales para alimiter
        limit_linear = 10 ** (ceiling_db / 20.0)
        
        # Labels
        limiter_label = "mlim"
        
        # Construir filtro alimiter
        # alimiter parámetros:
        # - limit: nivel máximo de salida (linear)
        # - attack: tiempo de attack en ms
        # - release: tiempo de release en ms
        # - level_in: ganancia de entrada (1.0 = 0dB)
        # - level_out: ganancia de salida (1.0 = 0dB)
        
        # Para True Peak detection, usamos oversampling
        filter_chain = f"[{input_label}]"
        
        if enable_oversampling and isinstance(sample_rate, int) and sample_rate > 0:
            # Oversampling x2 (resampling real). Nota: aresample no soporta "factor" (p.ej. osr=2);
            # osr es sample rate en Hz.
            oversampled_sr = min(sample_rate * 2, 192000)
            if oversampled_sr != sample_rate:
                filter_chain += f"aresample={oversampled_sr},"
        
        # Aplicar limitador
        filter_chain += (
            f"volume={input_gain_db:.2f}dB,alimiter="
            f"limit={limit_linear:.6f}:"
            f"attack={max(0.1, min(80.0, lookahead_ms)):.2f}:"
            f"release={release_adjusted:.2f}:"
            f"level_in=1.0:"
            f"level_out=1.0:level=false:latency=true"
        )
        
        if enable_oversampling and isinstance(sample_rate, int) and sample_rate > 0:
            oversampled_sr = min(sample_rate * 2, 192000)
            if oversampled_sr != sample_rate:
                # Volver al sample rate original si se oversampleó
                filter_chain += f",aresample={sample_rate}"
        
        filter_chain += f"[{limiter_label}]"
        
        return filter_chain, limiter_label

    def build_function(self, action, input_label, context, labels):
        action = self.validate_action(action)
        p = action.params
        factor = int(p.get("oversampling", 4))
        oversampled = min(context.sample_rate * factor, 192000)
        limit = 10 ** (float(p.get("ceiling_db", -1.0)) / 20.0)
        mode = str(p.get("mode", "transparent"))
        mode_params = self._get_mode_params(mode)
        release = float(p.get("release_ms", 150.0)) * mode_params["release_mult"]
        lookahead = float(p.get("lookahead_ms", 5.0))
        parts = []
        if oversampled != context.sample_rate:
            parts.append(f"aresample={oversampled}")
        parts.extend((
            f"volume={-mode_params['threshold_offset']:.2f}dB",
            f"alimiter=limit={limit:.6f}:attack={lookahead:.2f}:release={release:.2f}:level=false:latency=true",
        ))
        if oversampled != context.sample_rate:
            parts.append(f"aresample={context.sample_rate}")
        output = labels.new(action.function_id)
        return f"[{input_label}]" + ",".join(parts) + f"[{output}]", output
    
    def is_needed(self, **kwargs) -> bool:
        """
        El limitador maestro está siempre activo por seguridad.
        Es la última línea de defensa contra clipping.
        """
        enabled = kwargs.get("enabled", self.get_param("enabled", True))
        return enabled
