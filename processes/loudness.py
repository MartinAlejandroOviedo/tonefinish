"""
Proceso de Loudness/Mastering.

Incluye:
- Loudnorm (normalización EBU R128)
- Brickwall Limiter
- Fade In/Out
"""

from typing import Any, Dict, Tuple

from processes.base import BaseProcess, ProcessCategory
from config import LOUDNORM_LRA_DEFAULT


class LoudnessProcess(BaseProcess):
    """
    Proceso final de mastering.
    
    Funciones:
    - Loudnorm: Normalización a LUFS target (EBU R128)
    - Limiter: Brickwall limiter para proteger picos
    - Fades: Fade in/out
    """
    
    @property
    def id(self) -> str:
        return "loudness"
    
    @property
    def name(self) -> str:
        return "Loudness"
    
    @property
    def description(self) -> str:
        return "Normalización de loudness (LUFS), limiter y fades"
    
    @property
    def category(self) -> ProcessCategory:
        return ProcessCategory.MASTER
    
    @property
    def default_order(self) -> int:
        return 90  # Último en la cadena
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "target_lufs": -14.0,           # Target LUFS
            "true_peak": -1.0,              # True peak límite
            "lra": LOUDNORM_LRA_DEFAULT,    # Loudness Range (LU)
            "dual_mono": False,             # True si audio es mono (medición EBU correcta)
            "brickwall": False,             # Habilitar brickwall limiter
            "limiter_ceiling_db": None,     # Ceiling del limiter (None = true_peak - 0.5)
            "limiter_release_ms": 100.0,    # Release del limiter
            "fade_in": 0.0,                 # Fade in en segundos
            "fade_out": 0.0,                # Fade out en segundos
        }
    
    def build_loudnorm_filter(
        self,
        stats: Dict[str, float],
        **kwargs
    ) -> str:
        """
        Construye el filtro loudnorm con valores medidos.
        
        Args:
            stats: Estadísticas del audio (input_i, input_lra, input_tp, etc.)
            **kwargs: Parámetros adicionales (target_lufs, true_peak, lra, dual_mono)
            
        Returns:
            str: Filtro loudnorm
        """
        target_lufs = kwargs.get("target_lufs", self.get_param("target_lufs", -14.0))
        true_peak = kwargs.get("true_peak", self.get_param("true_peak", -1.0))
        lra = kwargs.get("lra", self.get_param("lra", LOUDNORM_LRA_DEFAULT))
        dual_mono = kwargs.get("dual_mono", self.get_param("dual_mono", False))
        dual_mono_str = "true" if dual_mono else "false"
        
        return (
            f"loudnorm=I={target_lufs}:LRA={lra}:TP={true_peak}:dual_mono={dual_mono_str}"
            f":measured_I={stats['input_i']}"
            f":measured_LRA={stats['input_lra']}"
            f":measured_TP={stats['input_tp']}"
            f":measured_thresh={stats['input_thresh']}"
            f":offset={stats['target_offset']}"
            ":linear=true:print_format=summary"
        )
    
    def build_limiter_filter(
        self,
        **kwargs
    ) -> str:
        """
        Construye el filtro brickwall limiter.
        
        Args:
            **kwargs: Parámetros adicionales
            
        Returns:
            str: Filtro limiter
        """
        true_peak = kwargs.get("true_peak", self.get_param("true_peak", -1.0))
        limiter_ceiling_db = kwargs.get("limiter_ceiling_db", self.get_param("limiter_ceiling_db", None))
        limiter_release_ms = kwargs.get("limiter_release_ms", self.get_param("limiter_release_ms", 100.0))
        
        # Ceiling por defecto: true_peak - 0.5dB
        BRICKWALL_EXTRA_DB = -0.5
        limit_db = true_peak + BRICKWALL_EXTRA_DB
        if limiter_ceiling_db is not None:
            limit_db = limiter_ceiling_db
        
        limit_linear = max(0.0625, min(1.0, 10 ** (limit_db / 20.0)))
        
        return f"alimiter=limit={limit_linear:.6f}:attack=1:release={limiter_release_ms:.0f}:level=false:latency=true"
    
    def build_fade_filters(
        self,
        duration: float | None,
        **kwargs
    ) -> list[str]:
        """
        Construye filtros de fade in/out.
        
        Args:
            duration: Duración del audio en segundos
            **kwargs: Parámetros adicionales
            
        Returns:
            list[str]: Lista de filtros fade
        """
        fade_in = kwargs.get("fade_in", self.get_param("fade_in", 0.0))
        fade_out = kwargs.get("fade_out", self.get_param("fade_out", 0.0))
        
        filters = []
        
        if fade_in > 0:
            filters.append(f"afade=t=in:ss=0:d={fade_in:.3f}")
        
        if fade_out > 0 and duration:
            start = max(0.0, duration - fade_out)
            filters.append(f"afade=t=out:st={start:.3f}:d={fade_out:.3f}")
        
        return filters
    
    def build_filter(
        self,
        input_label: str,
        stats: Dict[str, float] | None = None,
        duration: float | None = None,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye la cadena completa de loudness/mastering.
        
        Args:
            input_label: Etiqueta de entrada
            stats: Estadísticas del audio para loudnorm
            duration: Duración del audio para fades
            **kwargs: Parámetros adicionales
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
        """
        if not self.enabled:
            return "", input_label
        
        brickwall = kwargs.get("brickwall", self.get_param("brickwall", False))
        
        filters = []
        
        # Loudnorm
        if stats:
            filters.append(self.build_loudnorm_filter(stats, **kwargs))
        
        # Limiter
        if brickwall:
            filters.append(self.build_limiter_filter(**kwargs))
        
        # Fades
        fade_filters = self.build_fade_filters(duration, **kwargs)
        filters.extend(fade_filters)
        
        if not filters:
            return "", input_label
        
        output_label = "out"
        filter_chain = f"[{input_label}]" + ",".join(filters) + f"[{output_label}]"
        
        return filter_chain, output_label

    def build_function(self, action, input_label, context, labels):
        action = self.validate_action(action)
        p = action.params
        fid = action.function_id
        if fid == "audio.loudness.normalize":
            stats = context.analysis.get("loudness_stats")
            if isinstance(stats, dict):
                expr = self.build_loudnorm_filter(
                    stats, target_lufs=p.get("target_lufs", -14.0),
                    true_peak=p.get("true_peak_db", -1.0), lra=p.get("lra", 11.0),
                    dual_mono=p.get("dual_mono", False),
                )
            else:
                dual_mono = "true" if p.get("dual_mono", False) else "false"
                expr = (
                    f"loudnorm=I={p.get('target_lufs', -14.0)}:LRA={p.get('lra', 11.0)}:"
                    f"TP={p.get('true_peak_db', -1.0)}:dual_mono={dual_mono}:linear=false"
                )
        elif fid == "audio.loudness.fade_in":
            expr = f"afade=t=in:ss=0:d={p.get('duration_seconds', 0.0):.3f}"
        else:
            duration = context.duration
            if duration is None:
                raise ValueError("audio.loudness.fade_out requiere duración")
            fade = float(p.get("duration_seconds", 0.0))
            expr = f"afade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.3f}"
        output = labels.new(fid)
        return f"[{input_label}]{expr}[{output}]", output
