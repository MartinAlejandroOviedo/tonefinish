"""
Proceso de Reparación de Audio.

Incluye:
- Reducción de ruido (afftdn)
- Declip (adeclip)
- Declick (adeclick)
- Reducción de Pink Noise (highshelf)
"""

from typing import Any, Dict, Tuple

from processes.base import BaseProcess, ProcessCategory


class RepairProcess(BaseProcess):
    """
    Proceso de reparación que elimina artefactos del audio.
    
    Funciones:
    - Reducción de ruido: Elimina ruido de fondo
    - Declip: Repara audio con clipping
    - Declick: Elimina clicks y pops
    - Pink Noise: Compensa ruido rosa (-3dB/octava)
    """
    
    @property
    def id(self) -> str:
        return "repair"
    
    @property
    def name(self) -> str:
        return "Reparación"
    
    @property
    def description(self) -> str:
        return "Reducción de ruido, declip, declick y compensación de pink noise"
    
    @property
    def category(self) -> ProcessCategory:
        return ProcessCategory.REPAIR
    
    @property
    def default_order(self) -> int:
        return 10  # Primero en la cadena
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "noise_level": "Off",       # Off, Leve, Medio, Alto, Auto
            "declip_level": "Off",      # Off, Leve, Medio, Alto, Auto
            "declick_level": "Off",     # Off, Leve, Medio, Alto, Auto  
            "pink_noise_level": "Off",  # Off, Leve, Medio, Alto
        }
    
    def _level_key(self, level: str) -> str:
        """Normaliza el nivel a minúsculas."""
        return level.strip().lower()
    
    def build_filter(
        self,
        input_label: str,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye la cadena de filtros de reparación.
        
        Args:
            input_label: Etiqueta de entrada del flujo
            **kwargs: Parámetros adicionales (pueden sobreescribir self.params)
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
        """
        if not self.enabled:
            return "", input_label
        
        # Obtener parámetros (kwargs tienen prioridad)
        noise_level = kwargs.get("noise_level", self.get_param("noise_level", "Off"))
        declip_level = kwargs.get("declip_level", self.get_param("declip_level", "Off"))
        declick_level = kwargs.get("declick_level", self.get_param("declick_level", "Off"))
        pink_noise_level = kwargs.get("pink_noise_level", self.get_param("pink_noise_level", "Off"))
        
        parts = []
        current = input_label
        filter_index = 0
        
        def add_filter(filter_expr: str, suffix: str) -> None:
            nonlocal current, filter_index
            filter_index += 1
            label = f"rp{filter_index}{suffix}"
            parts.append(f"[{current}]{filter_expr}[{label}]")
            current = label
        
        # Declip
        level = self._level_key(declip_level)
        if level not in ("off", "apagado"):
            add_filter("adeclip", "dc")
        
        # Declick
        level = self._level_key(declick_level)
        if level not in ("off", "apagado"):
            if level == "leve":
                add_filter("adeclick=t=2.0", "dk")
            elif level == "medio":
                add_filter("adeclick=t=1.5", "dk")
            elif level == "alto":
                add_filter("adeclick=t=1.1", "dk")
            else:
                add_filter("adeclick", "dk")
        
        # Noise reduction
        level = self._level_key(noise_level)
        if level not in ("off", "apagado"):
            if level == "leve":
                add_filter("afftdn=nr=4:nf=-25", "nr")
            elif level == "medio":
                add_filter("afftdn=nr=12:nf=-35", "nr")
            elif level == "alto":
                add_filter("afftdn=nr=18:nf=-40", "nr")
            else:
                add_filter("afftdn=nr=6:nf=-30", "nr")
        
        # Pink noise reduction
        # Compensa curva -3dB/octava con highshelf progresivo
        level = self._level_key(pink_noise_level)
        if level not in ("off", "apagado"):
            if level == "leve":
                add_filter("highshelf=f=100:g=-1.5:t=s,highshelf=f=300:g=-1:t=s", "pk")
            elif level == "medio":
                add_filter("highshelf=f=100:g=-3:t=s,highshelf=f=300:g=-2:t=s", "pk")
            elif level == "alto":
                add_filter("highshelf=f=100:g=-4.5:t=s,highshelf=f=300:g=-3:t=s,highshelf=f=1000:g=-1.5:t=s", "pk")
        
        return ";".join(parts), current

    def build_function(self, action, input_label, context, labels):
        action = self.validate_action(action)
        fid = action.function_id
        if fid == "audio.repair.trim_silence":
            p = action.params
            expr = (
                f"silenceremove=start_periods=1:start_duration={p.get('start_duration_seconds', 0.3):.2f}:"
                f"start_threshold={p.get('start_threshold_db', -50.0):.1f}dB,areverse,"
                f"silenceremove=start_periods=1:start_duration={p.get('end_duration_seconds', 1.5):.2f}:"
                f"start_threshold={p.get('end_threshold_db', -45.0):.1f}dB,areverse"
            )
            output = labels.new(fid)
            return f"[{input_label}]{expr}[{output}]", output
        level = self._level_key(str(action.params.get("level", "Off")))
        if not action.enabled or level in ("off", "apagado"):
            return "", input_label
        if level == "auto":
            analysis = context.analysis
            needed = {
                "audio.repair.denoise": float(analysis.get("noise_floor_db", -80.0)) > -55.0,
                "audio.repair.declip": bool(analysis.get("clipping", False)),
                "audio.repair.declick": bool(analysis.get("impulsive_noise", False)),
            }.get(fid, False)
            if not needed:
                return "", input_label
            level = "leve"
        if fid == "audio.repair.declip":
            expr = "adeclip"
        elif fid == "audio.repair.declick":
            threshold = {"leve": 2.0, "medio": 1.5, "alto": 1.1}.get(level, 2.0)
            expr = f"adeclick=t={threshold:.2f}"
        elif fid == "audio.repair.denoise":
            nr, nf = {"leve": (4, -25), "medio": (12, -35), "alto": (18, -40)}.get(level, (6, -30))
            expr = f"afftdn=nr={nr}:nf={nf}"
        else:
            gain = {"leve": -1.5, "medio": -3.0, "alto": -4.5}.get(level, -1.5)
            expr = f"highshelf=f=100:width_type=s:width=1:g={gain:.2f}"
        output = labels.new(fid)
        return f"[{input_label}]{expr}[{output}]", output
    
    def resolve_auto_levels(
        self,
        stats: Dict[str, float] | None,
    ) -> Dict[str, str]:
        """
        Resuelve niveles 'Auto' a niveles concretos según el análisis.
        
        Args:
            stats: Estadísticas del audio (input_tp, input_thresh, etc.)
            
        Returns:
            Dict con los niveles resueltos
        """
        noise = self.get_param("noise_level", "Off")
        declip = self.get_param("declip_level", "Off")
        declick = self.get_param("declick_level", "Off")
        
        if stats is None:
            return {
                "noise_level": noise,
                "declip_level": declip,
                "declick_level": declick,
            }
        
        input_tp = stats.get("input_tp", 0.0)
        input_thresh = stats.get("input_thresh", -50.0)
        
        # Resolver Auto
        if self._level_key(noise) == "auto":
            noise = "Leve" if input_thresh > -25.0 else "Off"
        
        if self._level_key(declip) == "auto":
            declip = "Leve" if input_tp >= -0.3 else "Off"
        
        if self._level_key(declick) == "auto":
            declick = "Leve" if input_tp >= -0.2 else "Off"
        
        return {
            "noise_level": noise,
            "declip_level": declip,
            "declick_level": declick,
        }
