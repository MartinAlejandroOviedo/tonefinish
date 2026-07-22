"""
Analizador de compresión para telemetría y validación.

Estima el Gain Reduction (GR) esperado de múltiples etapas de compresión
para detectar sobre-compresión. Límite saludable: ~6dB GR total.
"""

from typing import Dict, Any, Tuple


def estimate_compressor_gr(
    threshold_db: float,
    ratio: float,
    input_level_db: float = -12.0
) -> float:
    """
    Estima el Gain Reduction de un compresor estándar.
    
    Args:
        threshold_db: Umbral de compresión
        ratio: Ratio de compresión (1.0 = sin compresión)
        input_level_db: Nivel RMS promedio de entrada (default -12dB)
    
    Returns:
        float: GR estimado en dB (positivo = reducción)
    
    Fórmula: GR = (input_db - threshold_db) * (1 - 1/ratio)
    """
    if ratio <= 1.0 or input_level_db <= threshold_db:
        return 0.0
    
    # Exceso sobre el threshold
    excess_db = input_level_db - threshold_db
    
    # GR = excess * (1 - 1/ratio)
    # Ejemplo: excess=6dB, ratio=2.0 → GR = 6 * (1 - 0.5) = 3dB
    gr = excess_db * (1.0 - 1.0 / ratio)
    
    return max(0.0, gr)


def estimate_dynamic_eq_gr(
    num_bands: int = 5,
    threshold_db: float = -18.0,
    ratio: float = 1.5
) -> float:
    """
    Estima el GR de Dynamic EQ (compand por banda).
    
    Dynamic EQ aplica compresión suave en múltiples bandas,
    pero no todas actúan simultáneamente. Se estima que
    2-3 bandas comprimen a la vez.
    
    Args:
        num_bands: Número de bandas (default 5)
        threshold_db: Threshold por banda
        ratio: Ratio por banda
    
    Returns:
        float: GR estimado en dB
    """
    # Estimar que 2-3 bandas comprimen simultáneamente
    active_bands = min(3, num_bands)
    
    # GR por banda (usando input_level -15dB como típico)
    gr_per_band = estimate_compressor_gr(
        threshold_db=threshold_db,
        ratio=ratio,
        input_level_db=-15.0
    )
    
    # GR total es ~50% del GR individual por banda activa
    # (porque las bandas no se suman linealmente)
    total_gr = gr_per_band * active_bands * 0.5
    
    return max(0.0, total_gr)


def estimate_stereo_dynamic_gr(
    threshold_db: float = -24.0,
    ratio: float = 1.6
) -> float:
    """
    Estima el GR de Stereo Dynamic (compresión M/S del Side).
    
    Solo comprime el canal Side cuando hay exceso de stereo width,
    por lo que el GR es menor que un compresor full-range.
    
    Args:
        threshold_db: Threshold del Side
        ratio: Ratio de compresión
    
    Returns:
        float: GR estimado en dB
    """
    # El Side suele tener 3-6dB menos nivel que Mid
    # Se estima input_level del Side en -18dB
    gr = estimate_compressor_gr(
        threshold_db=threshold_db,
        ratio=ratio,
        input_level_db=-18.0
    )
    
    # Solo afecta al Side (~50% del material)
    return gr * 0.5


def estimate_glue_gr(
    threshold_db: float = -18.0,
    ratio: float = 1.4
) -> float:
    """
    Estima el GR del Glue Compressor.
    
    Args:
        threshold_db: Threshold
        ratio: Ratio
    
    Returns:
        float: GR estimado en dB
    """
    return estimate_compressor_gr(
        threshold_db=threshold_db,
        ratio=ratio,
        input_level_db=-12.0
    )


def estimate_autogain_gr(
    num_stages: int = 2
) -> float:
    """
    Estima el GR de los AutoGain limiters.
    
    AutoGain usa limitadores suaves después de procesos agresivos
    (saturation, etc.). Cada stage aplica ~1-2dB GR.
    
    Args:
        num_stages: Número de etapas AutoGain
    
    Returns:
        float: GR estimado en dB
    """
    gr_per_stage = 1.5  # dB
    return num_stages * gr_per_stage


def calculate_total_gr(params: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    """
    Calcula el Gain Reduction total estimado y el desglose por proceso.
    
    Args:
        params: Diccionario de parámetros de orchestrator
    
    Returns:
        Tuple[float, Dict[str, float]]: (gr_total_db, breakdown)
            - gr_total_db: GR total estimado
            - breakdown: Dict con GR por proceso
    
    Límite saludable: ~6dB GR total
    Sobre-compresión: >8dB GR total
    """
    breakdown = {}
    total_gr = 0.0
    
    # Dynamic EQ
    if params.get("dynamic_eq", False):
        gr = estimate_dynamic_eq_gr(
            num_bands=5,
            threshold_db=params.get("dynamic_eq_threshold_db", -18.0),
            ratio=params.get("dynamic_eq_ratio", 1.5)
        )
        breakdown["dynamic_eq"] = gr
        total_gr += gr
    
    # Stereo Dynamic
    if params.get("stereo_dynamic", False):
        gr = estimate_stereo_dynamic_gr(
            threshold_db=params.get("stereo_dynamic_threshold_db", -24.0),
            ratio=params.get("stereo_dynamic_ratio", 1.6)
        )
        breakdown["stereo_dynamic"] = gr
        total_gr += gr
    
    # Glue Compressor
    if params.get("glue_enabled", False):
        gr = estimate_glue_gr(
            threshold_db=params.get("threshold_db", -18.0),
            ratio=params.get("ratio", 1.4)
        )
        breakdown["glue"] = gr
        total_gr += gr
    
    # AutoGain limiters
    if params.get("autogain_enabled", False):
        # Estimar 2 stages en promedio
        num_stages = 2
        gr = estimate_autogain_gr(num_stages)
        breakdown["autogain_limiters"] = gr
        total_gr += gr
    
    return total_gr, breakdown


def get_compression_assessment(total_gr_db: float) -> str:
    """
    Evalúa el nivel de compresión total.
    
    Args:
        total_gr_db: GR total en dB
    
    Returns:
        str: Evaluación (OK, PRECAUCIÓN, CRÍTICO)
    """
    if total_gr_db <= 6.0:
        return "OK"
    elif total_gr_db <= 8.0:
        return "PRECAUCIÓN"
    else:
        return "CRÍTICO"
