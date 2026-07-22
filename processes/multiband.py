"""
Proceso Multiband EQ/Compressor.

Procesamiento multibanda con:
- Dynamic EQ (compand)
- Stereo Width por banda
- Ajuste de ganancia por banda
- Saturación por banda
"""

import math
from typing import Any, Dict, List, Tuple

from processes.base import BaseProcess, ProcessCategory


# Configuración de bandas por defecto
DEFAULT_BAND_CONFIG = [
    ("Subbass (20-60 Hz)", 20, 60, 0.06, 0.40, 0.0),
    ("Bass (60-250 Hz)", 60, 250, 0.04, 0.30, 0.4),
    ("Low-Mid (250-500 Hz)", 250, 500, 0.03, 0.20, 0.7),
    ("Mid (500-2k Hz)", 500, 2000, 0.02, 0.15, 1.0),
    ("High-Mid (2k-6k Hz)", 2000, 6000, 0.01, 0.12, 1.2),
    ("Air (6k-16k Hz)", 6000, 16000, 0.005, 0.08, 1.4),
]

# Bandas sensibles
DEFAULT_BAND_HEADROOM_DB = {
    "High-Mid (2k-6k Hz)": -2.0,
    "Air (6k-16k Hz)": -3.0,
}

DEFAULT_MAX_SATURATION_DRIVE_DB = {
    "High-Mid (2k-6k Hz)": 12.0,
    "Air (6k-16k Hz)": 8.0,
}


class MultibandProcess(BaseProcess):
    """
    Procesador multibanda con EQ dinámico, stereo y saturación.
    
    Divide el audio en 6 bandas y permite:
    - Dynamic EQ: Compresión/expansión adaptativa
    - Stereo Width: Control de imagen estéreo por banda
    - Band Adjust: Ganancia individual por banda
    - Saturation: Saturación por banda
    """
    
    @property
    def id(self) -> str:
        return "multiband"
    
    @property
    def name(self) -> str:
        return "Multiband EQ"
    
    @property
    def description(self) -> str:
        return "EQ dinámico multibanda con control de estéreo y saturación"
    
    @property
    def category(self) -> ProcessCategory:
        return ProcessCategory.MIX
    
    @property
    def default_order(self) -> int:
        return 40
    
    def get_default_params(self) -> Dict[str, Any]:
        return {
            "dynamic_eq": False,        # Habilitar EQ dinámico
            "stereo_width": False,      # Habilitar control de estéreo
            "auto_band_gain": False,    # Compensación automática de ganancia
            "band_range_db": 3.0,       # Rango de compresión
            "max_adjust_db": 4.0,       # Máximo ajuste
            "band_adjust_db": {},       # Dict[label, float] ajustes por banda
            "band_widths": {},          # Dict[label, float] anchos estéreo
            "saturation_per_band": False,   # Saturación por banda
            "saturation_band_drive_db": {}, # Drive por banda
            "saturation_band_mix": {},      # Mix por banda
            "saturation_type": "Tape",      # Tipo: Tape, Tube
            "enable_band_limiter": True,    # Limitador en bandas sensibles
            "band_config": None,            # Custom band config o None para default
            
            # Stereo Dynamic (M/S processing) por banda
            "stereo_dynamic": False,        # Habilitar compresión dinámica M/S
            "stereo_dynamic_threshold_db": -24.0,  # Threshold de compresión del Side
            "stereo_dynamic_ratio": 1.6,    # Ratio de compresión del Side
            "stereo_dynamic_attack_ms": 20.0,  # Attack en ms
            "stereo_dynamic_release_ms": 150.0, # Release en ms
            "stereo_dynamic_mix": 0.6,      # Wet mix de la compresión del Side
            "stereo_dynamic_band_mix": {},  # Dict[label, float] mix por banda (override)
        }
    
    def _get_band_config(self) -> List[Tuple]:
        """Obtiene la configuración de bandas."""
        custom = self.get_param("band_config", None)
        if custom:
            return custom
        return DEFAULT_BAND_CONFIG
    
    def _resolve_saturation_type(self, saturation_type: str) -> str:
        """Resuelve el tipo de saturación a filtro ffmpeg."""
        sat_key = saturation_type.strip().lower()
        if sat_key in ("tape", "soft clip", "soft"):
            return "tanh"
        if sat_key in ("tube", "valve"):
            return "atan"
        return "tanh"
    
    def is_needed(self, **kwargs) -> bool:
        """Verifica si el procesamiento multiband es necesario."""
        dynamic_eq = kwargs.get("dynamic_eq", self.get_param("dynamic_eq", False))
        stereo_width = kwargs.get("stereo_width", self.get_param("stereo_width", False))
        auto_band_gain = kwargs.get("auto_band_gain", self.get_param("auto_band_gain", False))
        saturation_per_band = kwargs.get("saturation_per_band", self.get_param("saturation_per_band", False))
        stereo_dynamic = kwargs.get("stereo_dynamic", self.get_param("stereo_dynamic", False))
        band_adjust_db = kwargs.get("band_adjust_db", self.get_param("band_adjust_db", {}))
        
        apply_band_adjust = band_adjust_db and any(abs(v) > 0.001 for v in band_adjust_db.values())
        
        return dynamic_eq or stereo_width or apply_band_adjust or auto_band_gain or saturation_per_band or stereo_dynamic
    
    def build_filter(
        self,
        input_label: str,
        band_stats: Dict[str, float] | None = None,
        **kwargs
    ) -> Tuple[str, str]:
        """
        Construye el filtro multiband.
        
        Args:
            input_label: Etiqueta de entrada
            band_stats: Estadísticas RMS por banda para Dynamic EQ
            **kwargs: Parámetros adicionales
            
        Returns:
            Tuple[str, str]: (cadena_filtros, etiqueta_salida)
        """
        if not self.enabled:
            return "", input_label
        
        if not self.is_needed(**kwargs):
            return "", input_label
        
        # Obtener parámetros
        dynamic_eq = kwargs.get("dynamic_eq", self.get_param("dynamic_eq", False))
        stereo_width = kwargs.get("stereo_width", self.get_param("stereo_width", False))
        band_range_db = kwargs.get("band_range_db", self.get_param("band_range_db", 3.0))
        max_adjust_db = kwargs.get("max_adjust_db", self.get_param("max_adjust_db", 4.0))
        band_adjust_db = kwargs.get("band_adjust_db", self.get_param("band_adjust_db", {}))
        band_widths = kwargs.get("band_widths", self.get_param("band_widths", {}))
        auto_band_gain = kwargs.get("auto_band_gain", self.get_param("auto_band_gain", False))
        saturation_per_band = kwargs.get("saturation_per_band", self.get_param("saturation_per_band", False))
        saturation_band_drive_db = kwargs.get("saturation_band_drive_db", self.get_param("saturation_band_drive_db", {}))
        saturation_band_mix = kwargs.get("saturation_band_mix", self.get_param("saturation_band_mix", {}))
        saturation_type = kwargs.get("saturation_type", self.get_param("saturation_type", "Tape"))
        enable_band_limiter = kwargs.get("enable_band_limiter", self.get_param("enable_band_limiter", True))
        
        # Stereo Dynamic (M/S processing)
        stereo_dynamic = kwargs.get("stereo_dynamic", self.get_param("stereo_dynamic", False))
        sd_threshold_db = kwargs.get("stereo_dynamic_threshold_db", self.get_param("stereo_dynamic_threshold_db", -24.0))
        sd_ratio = kwargs.get("stereo_dynamic_ratio", self.get_param("stereo_dynamic_ratio", 1.6))
        sd_attack_ms = kwargs.get("stereo_dynamic_attack_ms", self.get_param("stereo_dynamic_attack_ms", 20.0))
        sd_release_ms = kwargs.get("stereo_dynamic_release_ms", self.get_param("stereo_dynamic_release_ms", 150.0))
        sd_mix = kwargs.get("stereo_dynamic_mix", self.get_param("stereo_dynamic_mix", 0.6))
        sd_band_mix = kwargs.get("stereo_dynamic_band_mix", self.get_param("stereo_dynamic_band_mix", {}))
        
        # Convertir tiempos para stereo_dynamic
        sd_attack_s = max(0.01, sd_attack_ms)
        sd_release_s = max(0.01, sd_release_ms)
        
        band_config = self._get_band_config()
        
        split_labels = [f"b{i}" for i in range(len(band_config))]
        band_outputs = [f"c{i}" for i in range(len(band_config))]
        
        split = f"[{input_label}]asplit={len(band_config)}" + "".join(f"[{label}]" for label in split_labels)
        parts = [split]
        
        sat_filter = self._resolve_saturation_type(saturation_type)
        
        for idx, (label, low_hz, high_hz, attack_s, release_s, width) in enumerate(band_config):
            # Usar filtros Butterworth de 2º orden (12dB/oct) aplicados 2 veces
            # para simular Linkwitz-Riley de 24dB/oct (mejor suma de fase)
            # Esto reduce cancelaciones entre bandas adyacentes
            hp_filter = f"highpass=f={low_hz}:poles=2,highpass=f={low_hz}:poles=2"
            lp_filter = f"lowpass=f={high_hz}:poles=2,lowpass=f={high_hz}:poles=2"
            band_chain = f"[{split_labels[idx]}]{hp_filter},{lp_filter}"
            
            # Dynamic EQ
            if dynamic_eq:
                if band_stats is None:
                    raise RuntimeError("No hay análisis por bandas disponible para control dinámico.")
                rms = band_stats.get(label)
                if rms is None:
                    raise RuntimeError(f"No hay RMS para la banda {label}.")
                
                low_thr = max(rms - band_range_db, -90.0)
                high_thr = min(rms + band_range_db, 0.0)
                if high_thr <= low_thr:
                    high_thr = min(0.0, low_thr + 0.5)
                
                band_chain += (
                    f",acompressor=threshold={high_thr:.2f}dB:ratio=2.0:attack={attack_s}:"
                    f"release={release_s}:knee=4.0:makeup=0.0:detection=peak"
                )
            
            # Stereo Width
            if stereo_width:
                if band_widths and label in band_widths:
                    width = band_widths[label]
                width_clamped = max(0.015625, min(64.0, width))
                band_chain += f",stereotools=mlev=1:slev={width_clamped:.2f}"
            
            # Stereo Dynamic (M/S processing)
            if stereo_dynamic:
                # Determinar mix para esta banda
                band_sd_mix = sd_band_mix.get(label, sd_mix) if sd_band_mix else sd_mix
                band_sd_mix = max(0.0, min(1.0, band_sd_mix))
                band_sd_dry = 1.0 - band_sd_mix
                
                if band_sd_mix > 0.0:
                    # Labels temporales para M/S processing
                    ms_in = f"msin{idx}"
                    mid_lbl = f"mid{idx}"
                    side_lbl = f"side{idx}"
                    side_comp = f"sidec{idx}"
                    side_mix = f"sidem{idx}"
                    ms_out = f"msout{idx}"
                    
                    # Guardar lo que llevamos hasta ahora
                    parts.append(f"{band_chain}[{ms_in}]")
                    
                    # Convertir a M/S
                    parts.append(f"[{ms_in}]asplit=2[ms0_{idx}][ms1_{idx}]")
                    parts.append(f"[ms0_{idx}]pan=mono|c0=0.5*FL+0.5*FR[{mid_lbl}]")
                    parts.append(f"[ms1_{idx}]pan=mono|c0=0.5*FL-0.5*FR[{side_lbl}]")
                    
                    # Comprimir el Side
                    parts.append(
                        f"[{side_lbl}]acompressor=threshold={sd_threshold_db:.2f}dB:"
                        f"ratio={sd_ratio:.2f}:"
                        f"attack={sd_attack_s:.3f}:"
                        f"release={sd_release_s:.3f}[{side_comp}]"
                    )
                    
                    # Mix dry/wet del Side
                    parts.append(
                        f"[{side_lbl}][{side_comp}]amix=inputs=2:weights={band_sd_dry:.2f} {band_sd_mix:.2f}[{side_mix}]"
                    )
                    
                    # Recombinar M/S a estéreo
                    parts.append(f"[{mid_lbl}]aformat=channel_layouts=mono[midm{idx}]")
                    parts.append(f"[{side_mix}]aformat=channel_layouts=mono[sidemono{idx}]")
                    parts.append(f"[midm{idx}][sidemono{idx}]join=inputs=2:channel_layout=stereo[msjoin{idx}]")
                    parts.append(f"[msjoin{idx}]pan=stereo|c0=c0+c1|c1=c0-c1[{ms_out}]")
                    
                    # Continuar con el resto del procesamiento desde ms_out
                    band_chain = f"[{ms_out}]"
                else:
                    # Mix es 0, no hacer nada
                    pass
            
            # Band Adjust
            if band_adjust_db:
                adjust_db = band_adjust_db.get(label, 0.0)
                if abs(adjust_db) > 0.001:
                    band_chain += f",volume={adjust_db:.2f}dB"
            
            # Band Limiter para bandas sensibles
            if enable_band_limiter and label in DEFAULT_BAND_HEADROOM_DB:
                headroom_db = DEFAULT_BAND_HEADROOM_DB[label]
                limit_linear = 10 ** (headroom_db / 20.0)
                band_chain += (
                    f",alimiter=limit={limit_linear:.6f}:attack=0.5:release=50:"
                    "level=false:latency=true"
                )
            
            out_label = band_outputs[idx]
            
            # Saturación por banda
            if saturation_per_band:
                drive_db = 0.0
                mix = 0.0
                if saturation_band_drive_db and label in saturation_band_drive_db:
                    drive_db = saturation_band_drive_db.get(label, 0.0)
                if saturation_band_mix and label in saturation_band_mix:
                    mix = saturation_band_mix.get(label, 0.0)
                mix = max(0.0, min(1.0, mix))
                
                if mix > 0.0:
                    max_drive = DEFAULT_MAX_SATURATION_DRIVE_DB.get(label, 24.0)
                    drive_db = max(-24.0, min(max_drive, drive_db))
                    dry = 1.0 - mix
                    base_label = f"{band_outputs[idx]}b"
                    dry_label = f"{band_outputs[idx]}d"
                    wet_label = f"{band_outputs[idx]}w"
                    wet_proc = f"{band_outputs[idx]}p"
                    clip_filter = f"asoftclip=type={sat_filter}:threshold=1:output=1"
                    
                    parts.append(f"{band_chain}[{base_label}]")
                    parts.append(f"[{base_label}]asplit=2[{dry_label}][{wet_label}]")
                    parts.append(f"[{wet_label}]volume={drive_db:.2f}dB,{clip_filter}[{wet_proc}]")
                    parts.append(f"[{dry_label}][{wet_proc}]amix=inputs=2:weights={dry:.2f} {mix:.2f}[{out_label}]")
                    continue
            
            parts.append(f"{band_chain}[{out_label}]")
        
        # Mix de todas las bandas
        mix_label = "mb"
        # IMPORTANTE: amix con normalize=0 suma las señales sin normalizar
        # Esto es correcto para crossover, pero necesitamos compensar
        # porque los filtros HP/LP tienen solapamiento y pérdida
        mix_chain = (
            "".join(f"[{label}]" for label in band_outputs)
            + f"amix=inputs={len(band_config)}:normalize=0[{mix_label}]"
        )
        parts.append(mix_chain)
        
        # Compensación de ganancia para restaurar nivel original
        # Los filtros HP/LP causan ~3-6dB de pérdida por solapamiento imperfecto
        output_label = mix_label
        compensation_db = 4.5  # Compensación aumentada de 3.0 a 4.5 dB
        
        if auto_band_gain:
            # Con auto_band_gain, aplicar compensación reducida pero no cero
            # para restaurar pérdidas de crossover
            compensation_db = 2.0
        
        if compensation_db > 0.1:
            gain_label = "mbg"
            parts.append(f"[{mix_label}]volume={compensation_db:.2f}dB[{gain_label}]")
            output_label = gain_label
        
        return ";".join(parts), output_label

    def build_function(self, action, input_label, context, labels):
        return self.build_functions([action], input_label, context, labels)

    def build_functions(self, actions, input_label, context, labels):
        """Compila todas las acciones multibanda consecutivas con un solo crossover."""
        validated = [self.validate_action(action) for action in actions]
        by_target = {band: [] for band in ("sub_bass", "bass", "low_mid", "mid", "high_mid", "air")}
        for action in validated:
            by_target[action.target].append(action)

        fid = "audio.multiband.chain"
        split_labels = [labels.new(fid, f"split_{idx}") for idx in range(6)]
        band_outputs = [labels.new(fid, f"band_{idx}") for idx in range(6)]
        parts = [f"[{input_label}]asplit=6" + "".join(f"[{label}]" for label in split_labels)]
        band_ids = ("sub_bass", "bass", "low_mid", "mid", "high_mid", "air")

        for idx, band_id in enumerate(band_ids):
            _legacy, low_hz, high_hz, _attack, _release, _width = DEFAULT_BAND_CONFIG[idx]
            crossover = []
            if idx > 0:
                crossover.extend((f"highpass=f={low_hz}:poles=2", f"highpass=f={low_hz}:poles=2"))
            if idx < len(DEFAULT_BAND_CONFIG) - 1:
                high_hz = min(high_hz, context.sample_rate * 0.499)
                crossover.extend((f"lowpass=f={high_hz:.2f}:poles=2", f"lowpass=f={high_hz:.2f}:poles=2"))
            current = labels.new(fid, f"stage_{idx}")
            parts.append(f"[{split_labels[idx]}]" + ",".join(crossover or ["anull"]) + f"[{current}]")

            for action in by_target[band_id]:
                p = action.params
                next_label = labels.new(action.function_id, band_id)
                if action.function_id == "audio.multiband.eq":
                    expr = f"volume={p.get('gain_db', 0.0):.2f}dB"
                    parts.append(f"[{current}]{expr}[{next_label}]")
                elif action.function_id == "audio.multiband.stereo_width":
                    # El contrato usa width=0 para "mono", pero stereotools no
                    # admite slev=0: su mínimo físico es 1/64.
                    width = max(0.015625, min(64.0, float(p.get("width", 1.0))))
                    expr = f"stereotools=mlev=1:slev={width:.6f}"
                    parts.append(f"[{current}]{expr}[{next_label}]")
                elif action.function_id == "audio.multiband.compressor":
                    knee = max(1.0, min(8.0, 10 ** (float(p.get("knee_db", 4.0)) / 20.0)))
                    makeup_db = float(p.get("makeup_db", 0.0))
                    makeup = 10 ** (max(0.0, makeup_db) / 20.0)
                    expr = (
                        f"acompressor=threshold={p.get('threshold_db', -18.0):.2f}dB:"
                        f"ratio={p.get('ratio', 1.2):.2f}:attack={p.get('attack_ms', 10.0):.3f}:"
                        f"release={p.get('release_ms', 100.0):.3f}:knee={knee:.4f}:makeup={makeup:.6f}"
                    )
                    if makeup_db < 0:
                        expr += f",volume={makeup_db:.2f}dB"
                    parts.append(f"[{current}]{expr}[{next_label}]")
                elif action.function_id == "audio.multiband.limiter":
                    limit = 10 ** (float(p.get("ceiling_db", -3.0)) / 20.0)
                    expr = (
                        f"alimiter=limit={limit:.6f}:attack=1:release={p.get('release_ms', 50.0):.2f}:"
                        "level=false:latency=true"
                    )
                    parts.append(f"[{current}]{expr}[{next_label}]")
                else:
                    drive = float(p.get("drive_db", 0.0))
                    mix = float(p.get("mix", 0.0))
                    clip = self._resolve_saturation_type(str(p.get("type", "Tape")))
                    dry = labels.new(action.function_id, f"dry_{band_id}")
                    wet = labels.new(action.function_id, f"wet_{band_id}")
                    processed = labels.new(action.function_id, f"processed_{band_id}")
                    parts.append(f"[{current}]asplit=2[{dry}][{wet}]")
                    parts.append(
                        f"[{wet}]volume={drive:.2f}dB,asoftclip=type={clip}:threshold=1:output=1,"
                        f"volume={-max(0.0, drive):.2f}dB[{processed}]"
                    )
                    parts.append(
                        f"[{dry}][{processed}]amix=inputs=2:weights={1.0 - mix:.6f} {mix:.6f}:"
                        f"normalize=0[{next_label}]"
                    )
                current = next_label
            parts.append(f"[{current}]anull[{band_outputs[idx]}]")

        output = labels.new(fid)
        parts.append("".join(f"[{label}]" for label in band_outputs) + f"amix=inputs=6:normalize=0[{output}]")
        return ";".join(parts), output
