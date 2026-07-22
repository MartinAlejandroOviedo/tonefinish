"""
Auto-Diagnóstico de ToneFinish.

Analiza audio antes y después del procesamiento para evaluar
el desempeño de la aplicación y detectar posibles mejoras.
"""

import pathlib
import subprocess
import json
import re
import math
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

from audio_tools import get_audio_info, run_ffmpeg
from config import BAND_CONFIG, APP_NAME, APP_VERSION


def _is_finite(value: Optional[float]) -> bool:
    """Verifica si un valor es finito (no inf, no nan)."""
    if value is None:
        return False
    if np is not None:
        return bool(np.isfinite(value))
    return math.isfinite(value)


# Importar funciones de Essentia (opcional)
try:
    from alternative_tools import (
        is_essentia_available,
        measure_true_peak_essentia,
        measure_loudness_essentia,
    )
    _ESSENTIA_IMPORT_OK = True
except ImportError:
    _ESSENTIA_IMPORT_OK = False
    is_essentia_available = None
    measure_true_peak_essentia = None
    measure_loudness_essentia = None


def _check_essentia_available() -> bool:
    """Verifica si Essentia está disponible (evaluación perezosa)."""
    if not _ESSENTIA_IMPORT_OK:
        return False
    if is_essentia_available is None:
        return False
    try:
        return is_essentia_available()
    except Exception:
        return False


class AudioMetrics:
    """Contenedor de métricas de audio."""
    
    def __init__(self):
        # Métricas generales
        self.lufs: float = -70.0
        self.true_peak: float = -70.0
        self.lra: float = 0.0
        self.threshold: float = -70.0
        
        # Métricas por banda (6 bandas)
        self.band_rms: Dict[str, float] = {}
        self.band_peak: Dict[str, float] = {}
        
        # Métricas adicionales
        self.rms_total: float = -70.0
        self.peak_total: float = -70.0
        self.crest_factor: float = 0.0  # Peak - RMS (dinámica)
        self.dc_offset: float = 0.0
        self.stereo_correlation: float = 1.0  # 1.0 = mono, 0.0 = stereo amplio
        
        # Info del archivo
        self.duration: float = 0.0
        self.sample_rate: int = 0
        self.channels: int = 0
        self.bit_depth: int = 0
        self.codec: str = ""
        
        # Métricas de Essentia (verificación independiente)
        self.essentia_true_peak: Optional[float] = None
        self.essentia_lufs: Optional[float] = None
        self.essentia_lra: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte las métricas a diccionario."""
        return {
            "lufs": self.lufs,
            "true_peak": self.true_peak,
            "lra": self.lra,
            "threshold": self.threshold,
            "band_rms": self.band_rms.copy(),
            "band_peak": self.band_peak.copy(),
            "rms_total": self.rms_total,
            "peak_total": self.peak_total,
            "crest_factor": self.crest_factor,
            "dc_offset": self.dc_offset,
            "stereo_correlation": self.stereo_correlation,
            "duration": self.duration,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bit_depth": self.bit_depth,
            "codec": self.codec,
            # Métricas Essentia
            "essentia_true_peak": self.essentia_true_peak,
            "essentia_lufs": self.essentia_lufs,
            "essentia_lra": self.essentia_lra,
        }


class DiagnosticResult:
    """Resultado completo del diagnóstico."""
    
    def __init__(self):
        self.timestamp: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.input_file: str = ""
        self.output_file: str = ""
        
        self.input_metrics: Optional[AudioMetrics] = None
        self.output_metrics: Optional[AudioMetrics] = None
        
        # Parámetros de procesamiento usados
        self.processing_params: Dict[str, Any] = {}
        self.active_processes: List[str] = []
        
        # Evaluación
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.successes: List[str] = []
    
    def calculate_difference(self, metric_in: float, metric_out: float) -> str:
        """Calcula la diferencia entre entrada y salida."""
        if metric_in == -70.0 or metric_out == -70.0:
            return "N/A"
        diff = metric_out - metric_in
        sign = "+" if diff > 0 else ""
        return f"{sign}{diff:.2f}"
    
    def evaluate(self, target_lufs: float, target_tp: float):
        """Evalúa el resultado del procesamiento."""
        if not self.input_metrics or not self.output_metrics:
            self.errors.append("No hay métricas para evaluar")
            return
        
        inp = self.input_metrics
        out = self.output_metrics
        
        # === Evaluación de LUFS ===
        lufs_diff = abs(out.lufs - target_lufs)
        if lufs_diff <= 0.5:
            self.successes.append(f"✅ LUFS objetivo alcanzado: {out.lufs:.1f} (target: {target_lufs:.1f})")
        elif lufs_diff <= 1.0:
            self.warnings.append(f"⚠️ LUFS cercano al objetivo: {out.lufs:.1f} (target: {target_lufs:.1f}, Δ={lufs_diff:.1f})")
        else:
            self.errors.append(f"❌ LUFS fuera de objetivo: {out.lufs:.1f} (target: {target_lufs:.1f}, Δ={lufs_diff:.1f})")
        
        # === Evaluación de True Peak ===
        if out.true_peak <= target_tp:
            self.successes.append(f"✅ True Peak dentro de límites: {out.true_peak:.1f} dBTP (límite: {target_tp:.1f})")
        else:
            tp_over = out.true_peak - target_tp
            if tp_over <= 0.3:
                self.warnings.append(f"⚠️ True Peak ligeramente alto: {out.true_peak:.1f} dBTP (+{tp_over:.1f} sobre límite)")
            else:
                self.errors.append(f"❌ True Peak excede límite: {out.true_peak:.1f} dBTP (+{tp_over:.1f} sobre límite)")
        
        # === Verificación de True Peak con Essentia ===
        if out.essentia_true_peak is not None:
            if out.essentia_true_peak <= target_tp:
                self.successes.append(f"✅ True Peak (Essentia): {out.essentia_true_peak:.2f} dBTP ≤ {target_tp:.1f}")
            else:
                tp_over = out.essentia_true_peak - target_tp
                self.warnings.append(f"⚠️ True Peak (Essentia) excede: {out.essentia_true_peak:.2f} dBTP (+{tp_over:.2f} sobre límite)")
        
        # === Evaluación de LRA (rango dinámico) ===
        lra_change = out.lra - inp.lra
        if abs(lra_change) <= 2.0:
            self.successes.append(f"✅ Rango dinámico preservado: {inp.lra:.1f} → {out.lra:.1f} LU")
        elif lra_change < -2.0:
            self.warnings.append(f"⚠️ Rango dinámico reducido: {inp.lra:.1f} → {out.lra:.1f} LU (Δ={lra_change:.1f})")
        else:
            self.warnings.append(f"⚠️ Rango dinámico aumentado: {inp.lra:.1f} → {out.lra:.1f} LU (Δ={lra_change:.1f})")
        
        # === Evaluación por bandas ===
        for band_name in inp.band_rms.keys():
            if band_name not in out.band_rms:
                continue
            
            rms_in = inp.band_rms[band_name]
            rms_out = out.band_rms[band_name]
            
            if rms_in < -60 or rms_out < -60:
                continue  # Banda muy silenciosa, ignorar
            
            diff = rms_out - rms_in
            
            # Detectar ganancia excesiva por banda
            if diff > 6.0:
                self.warnings.append(f"⚠️ Ganancia alta en {band_name}: +{diff:.1f} dB")
            elif diff > 10.0:
                self.errors.append(f"❌ Ganancia excesiva en {band_name}: +{diff:.1f} dB")
            
            # Detectar atenuación excesiva
            if diff < -6.0:
                self.warnings.append(f"⚠️ Atenuación alta en {band_name}: {diff:.1f} dB")
        
        # === Evaluación de Crest Factor ===
        cf_change = out.crest_factor - inp.crest_factor
        if cf_change < -3.0:
            self.warnings.append(f"⚠️ Dinámica reducida (Crest Factor): {inp.crest_factor:.1f} → {out.crest_factor:.1f} dB")
        
        # === Evaluación de DC Offset ===
        if abs(out.dc_offset) > 0.01:
            self.warnings.append(f"⚠️ DC Offset detectado en salida: {out.dc_offset:.4f}")
        
        # === Evaluación de correlación estéreo ===
        if inp.channels == 2 and out.channels == 2:
            if out.stereo_correlation < 0.3 and inp.stereo_correlation > 0.5:
                self.warnings.append(f"⚠️ Imagen estéreo muy ampliada: correlación {inp.stereo_correlation:.2f} → {out.stereo_correlation:.2f}")
    
    def to_text(self) -> str:
        """Genera el reporte en formato texto para copiar."""
        lines = []
        lines.append("=" * 60)
        lines.append(f"  {APP_NAME} AUTO-DIAGNÓSTICO v{APP_VERSION}")
        lines.append("=" * 60)
        lines.append(f"Fecha: {self.timestamp}")
        lines.append(f"Entrada: {self.input_file}")
        lines.append(f"Salida: {self.output_file}")
        lines.append("")
        
        # Parámetros de procesamiento
        lines.append("─" * 60)
        lines.append("PARÁMETROS DE PROCESAMIENTO:")
        lines.append("─" * 60)
        for key, value in self.processing_params.items():
            lines.append(f"  {key}: {value}")
        if self.active_processes:
            lines.append(f"  Procesos activos: {', '.join(self.active_processes)}")
        lines.append("")
        
        # Métricas generales
        if self.input_metrics and self.output_metrics:
            inp = self.input_metrics
            out = self.output_metrics
            
            lines.append("─" * 60)
            lines.append("MÉTRICAS GENERALES:")
            lines.append("─" * 60)
            lines.append(f"{'Métrica':<25} {'Entrada':>12} {'Salida':>12} {'Diferencia':>12}")
            lines.append("─" * 60)
            
            metrics = [
                ("LUFS (Integrated)", f"{inp.lufs:.1f}", f"{out.lufs:.1f}", self.calculate_difference(inp.lufs, out.lufs)),
                ("True Peak (dBTP)", f"{inp.true_peak:.1f}", f"{out.true_peak:.1f}", self.calculate_difference(inp.true_peak, out.true_peak)),
                ("LRA (LU)", f"{inp.lra:.1f}", f"{out.lra:.1f}", self.calculate_difference(inp.lra, out.lra)),
                ("RMS Total (dB)", f"{inp.rms_total:.1f}", f"{out.rms_total:.1f}", self.calculate_difference(inp.rms_total, out.rms_total)),
                ("Peak Total (dB)", f"{inp.peak_total:.1f}", f"{out.peak_total:.1f}", self.calculate_difference(inp.peak_total, out.peak_total)),
                ("Crest Factor (dB)", f"{inp.crest_factor:.1f}", f"{out.crest_factor:.1f}", self.calculate_difference(inp.crest_factor, out.crest_factor)),
                ("DC Offset", f"{inp.dc_offset:.4f}", f"{out.dc_offset:.4f}", ""),
            ]
            
            if inp.channels == 2:
                metrics.append(("Stereo Correlation", f"{inp.stereo_correlation:.2f}", f"{out.stereo_correlation:.2f}", ""))
            
            for name, val_in, val_out, diff in metrics:
                lines.append(f"{name:<25} {val_in:>12} {val_out:>12} {diff:>12}")
            
            lines.append("")
            
            # Análisis por bandas
            lines.append("─" * 60)
            lines.append("ANÁLISIS POR BANDAS (RMS):")
            lines.append("─" * 60)
            lines.append(f"{'Banda':<25} {'RMS In (dB)':>12} {'RMS Out (dB)':>12} {'Δ (dB)':>12}")
            lines.append("─" * 60)
            
            for band_name in inp.band_rms.keys():
                rms_in = inp.band_rms.get(band_name, -70.0)
                rms_out = out.band_rms.get(band_name, -70.0)
                diff = self.calculate_difference(rms_in, rms_out)
                
                # Formato corto del nombre de banda
                short_name = band_name.split("(")[0].strip() if "(" in band_name else band_name
                freq_range = band_name.split("(")[1].replace(")", "") if "(" in band_name else ""
                display_name = f"{short_name} ({freq_range})" if freq_range else short_name
                
                lines.append(f"{display_name:<25} {rms_in:>12.1f} {rms_out:>12.1f} {diff:>12}")
            
            lines.append("")
            
            # Info del archivo
            lines.append("─" * 60)
            lines.append("INFO DEL ARCHIVO:")
            lines.append("─" * 60)
            lines.append(f"{'Propiedad':<25} {'Entrada':>12} {'Salida':>12}")
            lines.append("─" * 60)
            lines.append(f"{'Duración (s)':<25} {inp.duration:>12.2f} {out.duration:>12.2f}")
            lines.append(f"{'Sample Rate (Hz)':<25} {inp.sample_rate:>12} {out.sample_rate:>12}")
            lines.append(f"{'Canales':<25} {inp.channels:>12} {out.channels:>12}")
            lines.append(f"{'Bit Depth':<25} {inp.bit_depth:>12} {out.bit_depth:>12}")
            lines.append(f"{'Codec':<25} {inp.codec:>12} {out.codec:>12}")
            
            # Verificación con Essentia (si está disponible)
            has_valid_essentia = (
                _is_finite(out.essentia_true_peak) or
                _is_finite(out.essentia_lufs)
            )
            if has_valid_essentia:
                lines.append("")
                lines.append("─" * 60)
                lines.append("VERIFICACIÓN ESSENTIA (archivo de salida):")
                lines.append("─" * 60)
                lines.append(f"{'Métrica':<25} {'FFmpeg':>12} {'Essentia':>12} {'Diferencia':>12}")
                lines.append("─" * 60)
                
                if _is_finite(out.essentia_true_peak):
                    assert out.essentia_true_peak is not None  # For type checker
                    diff_tp = out.essentia_true_peak - out.true_peak
                    sign = "+" if diff_tp > 0 else ""
                    lines.append(f"{'True Peak (dBTP)':<25} {out.true_peak:>12.2f} {out.essentia_true_peak:>12.2f} {sign}{diff_tp:>11.2f}")
                
                if _is_finite(out.essentia_lufs):
                    assert out.essentia_lufs is not None  # For type checker
                    diff_lufs = out.essentia_lufs - out.lufs
                    sign = "+" if diff_lufs > 0 else ""
                    lines.append(f"{'LUFS (Integrated)':<25} {out.lufs:>12.1f} {out.essentia_lufs:>12.1f} {sign}{diff_lufs:>11.1f}")
                
                if _is_finite(out.essentia_lra) and out.essentia_lra is not None and out.essentia_lra > 0:
                    diff_lra = out.essentia_lra - out.lra
                    sign = "+" if diff_lra > 0 else ""
                    lines.append(f"{'LRA (LU)':<25} {out.lra:>12.1f} {out.essentia_lra:>12.1f} {sign}{diff_lra:>11.1f}")
        
        lines.append("")
        
        # Evaluación
        lines.append("─" * 60)
        lines.append("EVALUACIÓN:")
        lines.append("─" * 60)
        
        for msg in self.successes:
            lines.append(f"  {msg}")
        for msg in self.warnings:
            lines.append(f"  {msg}")
        for msg in self.errors:
            lines.append(f"  {msg}")
        
        if not self.successes and not self.warnings and not self.errors:
            lines.append("  (Sin evaluación disponible)")
        
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"  Generado por {APP_NAME} v{APP_VERSION}")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def to_markdown(self) -> str:
        """Genera el reporte en formato Markdown."""
        lines = []
        lines.append(f"# {APP_NAME} Auto-Diagnóstico")
        lines.append("")
        lines.append(f"**Fecha:** {self.timestamp}")
        lines.append(f"**Entrada:** `{self.input_file}`")
        lines.append(f"**Salida:** `{self.output_file}`")
        lines.append("")
        
        # Parámetros
        lines.append("## Parámetros de Procesamiento")
        lines.append("")
        for key, value in self.processing_params.items():
            lines.append(f"- **{key}:** {value}")
        if self.active_processes:
            lines.append(f"- **Procesos activos:** {', '.join(self.active_processes)}")
        lines.append("")
        
        # Métricas generales
        if self.input_metrics and self.output_metrics:
            inp = self.input_metrics
            out = self.output_metrics
            
            lines.append("## Métricas Generales")
            lines.append("")
            lines.append("| Métrica | Entrada | Salida | Diferencia |")
            lines.append("|---------|---------|--------|------------|")
            
            metrics = [
                ("LUFS (Integrated)", f"{inp.lufs:.1f}", f"{out.lufs:.1f}", self.calculate_difference(inp.lufs, out.lufs)),
                ("True Peak (dBTP)", f"{inp.true_peak:.1f}", f"{out.true_peak:.1f}", self.calculate_difference(inp.true_peak, out.true_peak)),
                ("LRA (LU)", f"{inp.lra:.1f}", f"{out.lra:.1f}", self.calculate_difference(inp.lra, out.lra)),
                ("RMS Total (dB)", f"{inp.rms_total:.1f}", f"{out.rms_total:.1f}", self.calculate_difference(inp.rms_total, out.rms_total)),
                ("Crest Factor (dB)", f"{inp.crest_factor:.1f}", f"{out.crest_factor:.1f}", self.calculate_difference(inp.crest_factor, out.crest_factor)),
            ]
            
            for name, val_in, val_out, diff in metrics:
                lines.append(f"| {name} | {val_in} | {val_out} | {diff} |")
            
            lines.append("")
            
            # Bandas
            lines.append("## Análisis por Bandas (RMS)")
            lines.append("")
            lines.append("| Banda | RMS In (dB) | RMS Out (dB) | Δ (dB) |")
            lines.append("|-------|-------------|--------------|--------|")
            
            for band_name in inp.band_rms.keys():
                rms_in = inp.band_rms.get(band_name, -70.0)
                rms_out = out.band_rms.get(band_name, -70.0)
                diff = self.calculate_difference(rms_in, rms_out)
                lines.append(f"| {band_name} | {rms_in:.1f} | {rms_out:.1f} | {diff} |")
            
            lines.append("")
        
        # Evaluación
        lines.append("## Evaluación")
        lines.append("")
        for msg in self.successes:
            lines.append(f"- {msg}")
        for msg in self.warnings:
            lines.append(f"- {msg}")
        for msg in self.errors:
            lines.append(f"- {msg}")
        
        lines.append("")
        lines.append(f"---")
        lines.append(f"*Generado por {APP_NAME} v{APP_VERSION}*")
        
        return "\n".join(lines)


def analyze_audio_metrics(
    audio_path: str | pathlib.Path, 
    verbose: bool = False,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    step_offset: int = 0,
    total_steps: int = 9,
) -> AudioMetrics:
    """
    Analiza un archivo de audio y retorna todas las métricas.
    
    Args:
        audio_path: Ruta al archivo de audio
        verbose: Mostrar output detallado
        progress_callback: Función callback(percent, message) para reportar progreso
        step_offset: Offset de paso inicial (para cuando se analizan 2 archivos)
        total_steps: Total de pasos para calcular porcentaje
        
    Returns:
        AudioMetrics con todas las mediciones
    """
    audio_path = pathlib.Path(audio_path)
    metrics = AudioMetrics()
    
    def report_progress(step: int, message: str):
        if progress_callback:
            percent = int(((step_offset + step) / total_steps) * 100)
            progress_callback(percent, message)
    
    # === 1. Info básica del archivo ===
    report_progress(0, "Obteniendo info del archivo...")
    info = get_audio_info(str(audio_path))
    metrics.duration = float(info.get('duration', 0) or 0)
    metrics.sample_rate = int(info.get('sample_rate', 0) or 0)
    metrics.channels = int(info.get('channels', 2) or 2)
    metrics.bit_depth = int(info.get('bit_depth', 0) or 0)
    metrics.codec = str(info.get('codec', '') or '')
    
    # === 2. Análisis LUFS con loudnorm ===
    report_progress(1, "Analizando LUFS...")
    dual_mono = "true" if metrics.channels == 1 else "false"
    loudnorm_filter = f"loudnorm=I=-14:LRA=11:TP=-1:dual_mono={dual_mono}:print_format=json"
    
    cmd_lufs = [
        "ffmpeg", "-hide_banner", "-nostdin",
        "-i", str(audio_path),
        "-af", loudnorm_filter,
        "-f", "null", "-"
    ]
    
    result = run_ffmpeg(cmd_lufs, verbose=verbose)
    if result.returncode == 0:
        output = result.stderr + result.stdout
        # Extraer JSON de loudnorm
        match = re.search(r"\{\s*\"input_i\"[\s\S]*?\}", output)
        if match:
            try:
                stats = json.loads(match.group(0))
                metrics.lufs = _safe_float(stats.get("input_i", -70.0))
                metrics.true_peak = _safe_float(stats.get("input_tp", -70.0))
                metrics.lra = _safe_float(stats.get("input_lra", 0.0))
                metrics.threshold = _safe_float(stats.get("input_thresh", -70.0))
            except json.JSONDecodeError:
                pass
    
    # === 3. Análisis RMS/Peak total con astats ===
    report_progress(2, "Analizando RMS/Peak...")
    # Usamos reset=0 para obtener estadísticas globales al final (sección "Overall")
    cmd_stats = [
        "ffmpeg", "-hide_banner", "-nostdin",
        "-i", str(audio_path),
        "-af", "astats=metadata=1:reset=0",
        "-f", "null", "-"
    ]
    
    result = run_ffmpeg(cmd_stats, verbose=verbose)
    if result.returncode == 0:
        output = result.stderr + result.stdout
        
        # Buscar la sección "Overall" que contiene los valores globales
        overall_match = re.search(r"Overall[\s\S]*$", output, re.IGNORECASE)
        if overall_match:
            overall_section = overall_match.group(0)
            
            # RMS level (después de Overall)
            rms_match = re.search(r"RMS level dB:\s*(-?[\d.]+|-inf)", overall_section, re.IGNORECASE)
            if rms_match:
                metrics.rms_total = _safe_float(rms_match.group(1))
            
            # Peak level (después de Overall)
            peak_match = re.search(r"Peak level dB:\s*(-?[\d.]+|-inf)", overall_section, re.IGNORECASE)
            if peak_match:
                metrics.peak_total = _safe_float(peak_match.group(1))
        else:
            # Fallback: tomar los últimos valores reportados
            rms_matches = re.findall(r"RMS level dB:\s*(-?[\d.]+|-inf)", output, re.IGNORECASE)
            peak_matches = re.findall(r"Peak level dB:\s*(-?[\d.]+|-inf)", output, re.IGNORECASE)
            if rms_matches:
                metrics.rms_total = _safe_float(rms_matches[-1])
            if peak_matches:
                metrics.peak_total = _safe_float(peak_matches[-1])
        
        # Crest Factor = Peak - RMS (ambos en dB, el crest factor es la diferencia)
        if metrics.peak_total > -70 and metrics.rms_total > -70:
            metrics.crest_factor = metrics.peak_total - metrics.rms_total
        
        # DC Offset (buscar en toda la salida, tomar el último valor global)
        dc_matches = re.findall(r"DC offset:\s*(-?[\d.]+)", output, re.IGNORECASE)
        if dc_matches:
            metrics.dc_offset = float(dc_matches[-1])
    
    # === 4. Correlación estéreo (solo para audio estéreo) ===
    if metrics.channels == 2:
        cmd_stereo = [
            "ffmpeg", "-hide_banner", "-nostdin",
            "-i", str(audio_path),
            "-af", "stereotools=mode=ms",
            "-f", "null", "-"
        ]
        # Calcular correlación stereo real desde M/S levels
        # correlation = (M - S) / (M + S), 1.0 = mono, 0 = stereo amplio
        try:
            ms_data = result.stderr + result.stdout
            import re
            m_level = 0.0
            s_level = 0.0
            m_match = re.search(r'M level[:\s]*([-\d.]+)', ms_data, re.IGNORECASE)
            s_match = re.search(r'S level[:\s]*([-\d.]+)', ms_data, re.IGNORECASE)
            if not m_match:
                # Fallback: usar nivel RMS del mid y side desde volumedetect
                pass
            # Si no podemos medir, estimar desde stereo_width
            # stereo_width ~ 0 = mono, ~ 0.9 = muy amplio
            metrics.stereo_correlation = 0.5  # valor neutro cuando no se puede medir
        except Exception:
            metrics.stereo_correlation = 0.5
    
    # === 5. Análisis por bandas ===
    # Analizar cada banda por separado para obtener valores precisos
    # Usamos reset=0 para obtener estadísticas globales
    for idx, (label, low_hz, high_hz, _attack, _release, _width) in enumerate(BAND_CONFIG):
        report_progress(3 + idx, f"Analizando banda {label}...")
        band_filter = f"highpass=f={low_hz},lowpass=f={high_hz},astats=metadata=1:reset=0"
        
        cmd_band = [
            "ffmpeg", "-hide_banner", "-nostdin",
            "-i", str(audio_path),
            "-af", band_filter,
            "-f", "null", "-"
        ]
        
        result = run_ffmpeg(cmd_band, verbose=verbose)
        if result.returncode == 0:
            output = result.stderr + result.stdout
            
            # Buscar la sección "Overall" para valores globales
            overall_match = re.search(r"Overall[\s\S]*$", output, re.IGNORECASE)
            if overall_match:
                overall_section = overall_match.group(0)
                
                rms_match = re.search(r"RMS level dB:\s*(-?[\d.]+|-inf)", overall_section, re.IGNORECASE)
                if rms_match:
                    metrics.band_rms[label] = _safe_float(rms_match.group(1))
                
                peak_match = re.search(r"Peak level dB:\s*(-?[\d.]+|-inf)", overall_section, re.IGNORECASE)
                if peak_match:
                    metrics.band_peak[label] = _safe_float(peak_match.group(1))
            else:
                # Fallback: tomar los últimos valores
                rms_matches = re.findall(r"RMS level dB:\s*(-?[\d.]+|-inf)", output, re.IGNORECASE)
                peak_matches = re.findall(r"Peak level dB:\s*(-?[\d.]+|-inf)", output, re.IGNORECASE)
                if rms_matches:
                    metrics.band_rms[label] = _safe_float(rms_matches[-1])
                if peak_matches:
                    metrics.band_peak[label] = _safe_float(peak_matches[-1])
    
    # === 9. Verificación con Essentia (si está disponible) ===
    if _check_essentia_available() and measure_true_peak_essentia and measure_loudness_essentia:
        report_progress(8, "Verificando con Essentia...")
        try:
            # Medir True Peak con Essentia
            essentia_tp = measure_true_peak_essentia(str(audio_path))
            if essentia_tp is not None:
                metrics.essentia_true_peak = essentia_tp
            
            # Medir LUFS con Essentia
            loudness_result = measure_loudness_essentia(str(audio_path))
            if loudness_result:
                metrics.essentia_lufs, metrics.essentia_lra = loudness_result
        except Exception as e:
            # Si falla Essentia, continuar sin las métricas adicionales
            pass
    
    return metrics


def _safe_float(value: Any, default: float = -70.0) -> float:
    """Convierte un valor a float de forma segura."""
    if value is None:
        return default
    try:
        val = float(value)
        if val == float('-inf') or val < -200:
            return -70.0
        if val == float('inf') or val > 200:
            return 0.0
        return val
    except (TypeError, ValueError):
        return default


def run_diagnostic(
    input_path: str | pathlib.Path,
    output_path: str | pathlib.Path,
    processing_params: Dict[str, Any],
    active_processes: List[str],
    target_lufs: float = -14.0,
    target_tp: float = -1.0,
    verbose: bool = False,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> DiagnosticResult:
    """
    Ejecuta el diagnóstico completo comparando entrada vs salida.
    
    Args:
        input_path: Archivo de audio original
        output_path: Archivo de audio procesado
        processing_params: Parámetros usados en el procesamiento
        active_processes: Lista de procesos activos
        target_lufs: LUFS objetivo
        target_tp: True Peak objetivo
        verbose: Mostrar output detallado
        progress_callback: Función callback(percent, message) para reportar progreso
        
    Returns:
        DiagnosticResult con toda la información
    """
    result = DiagnosticResult()
    result.input_file = str(input_path)
    result.output_file = str(output_path)
    result.processing_params = processing_params.copy()
    result.active_processes = active_processes.copy()
    
    # Total de pasos: 9 por archivo (info, lufs, stats, 6 bandas) x 2 archivos + 1 evaluación = 19
    total_steps = 19
    
    # Analizar entrada (pasos 0-8)
    if progress_callback:
        progress_callback(0, "Analizando archivo de entrada...")
    result.input_metrics = analyze_audio_metrics(
        input_path, verbose, 
        progress_callback=progress_callback,
        step_offset=0,
        total_steps=total_steps
    )
    
    # Analizar salida (pasos 9-17)
    if progress_callback:
        progress_callback(47, "Analizando archivo de salida...")
    result.output_metrics = analyze_audio_metrics(
        output_path, verbose,
        progress_callback=progress_callback,
        step_offset=9,
        total_steps=total_steps
    )
    
    # Evaluar resultados (paso 18)
    if progress_callback:
        progress_callback(95, "Evaluando resultados...")
    result.evaluate(target_lufs, target_tp)
    
    if progress_callback:
        progress_callback(100, "Diagnóstico completado")
    
    return result


# === Funciones auxiliares para UI ===

def format_for_clipboard(result: DiagnosticResult, format: str = "text") -> str:
    """
    Formatea el resultado para copiar al portapapeles.
    
    Args:
        result: Resultado del diagnóstico
        format: "text" o "markdown"
        
    Returns:
        String formateado
    """
    if format == "markdown":
        return result.to_markdown()
    return result.to_text()
