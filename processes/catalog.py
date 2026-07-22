"""Catálogo canónico de funciones de audio seleccionables por la IA."""

from __future__ import annotations

from typing import Dict, Tuple

from processes.contracts import (
    AudioFunctionRegistry, AudioFunctionSpec, BAND_IDS, ParameterSpec,
)


def _f(default: float, minimum: float, maximum: float, description: str = "") -> ParameterSpec:
    return ParameterSpec("float", default, minimum, maximum, description=description)


def _b(default: bool = False) -> ParameterSpec:
    return ParameterSpec("bool", default)


def _choice(default: str, *choices: str) -> ParameterSpec:
    return ParameterSpec("str", default, choices=tuple(choices))


def _spec(function_id: str, plugin: str, name: str, description: str,
          params: Dict[str, ParameterSpec] | None = None, *, bands: bool = False,
          conflicts: Tuple[str, ...] = (), analysis: Tuple[str, ...] = ()) -> AudioFunctionSpec:
    return AudioFunctionSpec(
        function_id=function_id, plugin_id=f"audio.{plugin}", name=name,
        description=description, parameters=params or {},
        supported_targets=BAND_IDS if bands else (), conflicts_with=conflicts,
        requires_analysis=analysis,
    )


FUNCTION_SPECS = (
    _spec("audio.repair.denoise", "repair", "Reducción de ruido", "Reduce ruido estacionario.", {
        "level": _choice("Off", "Off", "Leve", "Medio", "Alto", "Auto")}, analysis=("noise_floor_db",)),
    _spec("audio.repair.declip", "repair", "Declip", "Repara muestras recortadas.", {
        "level": _choice("Off", "Off", "Leve", "Medio", "Alto", "Auto")}, analysis=("clipping", "true_peak")),
    _spec("audio.repair.declick", "repair", "Declick", "Reduce clicks y pops.", {
        "level": _choice("Off", "Off", "Leve", "Medio", "Alto", "Auto")}, analysis=("impulsive_noise",)),
    _spec("audio.repair.pink_noise_compensation", "repair", "Compensación de ruido rosa", "Compensa una pendiente espectral de ruido rosa.", {
        "level": _choice("Off", "Off", "Leve", "Medio", "Alto")}, analysis=("spectrum",)),
    _spec("audio.repair.trim_silence", "repair", "Recorte de silencio", "Recorta silencios largos de los bordes.", {
        "start_threshold_db": _f(-50.0, -90.0, -10.0), "start_duration_seconds": _f(0.3, 0.0, 10.0),
        "end_threshold_db": _f(-45.0, -90.0, -10.0), "end_duration_seconds": _f(1.5, 0.0, 30.0)}),

    _spec("audio.tone_eq.high_pass", "tone_eq", "Filtro pasa-altos", "Elimina contenido bajo la frecuencia elegida.", {
        "frequency_hz": _f(30.0, 10.0, 1000.0), "poles": ParameterSpec("int", 2, 1, 2)}),
    _spec("audio.tone_eq.low_pass", "tone_eq", "Filtro pasa-bajos", "Elimina contenido sobre la frecuencia elegida.", {
        "frequency_hz": _f(18000.0, 1000.0, 40000.0), "poles": ParameterSpec("int", 2, 1, 2)}),
    _spec("audio.tone_eq.band", "tone_eq", "Banda de EQ", "Ajuste paramétrico o shelf sobre una banda estable.", {
        "frequency_hz": _f(1000.0, 10.0, 40000.0), "gain_db": _f(0.0, -12.0, 12.0),
        "q": _f(1.0, 0.1, 10.0), "filter_type": _choice("peaking", "peaking", "low_shelf", "high_shelf")},
        bands=True, analysis=("spectrum", "band_rms")),
    _spec("audio.tone_eq.tilt", "tone_eq", "Tilt EQ", "Inclina el balance tonal completo.", {
        "gain_db": _f(0.0, -6.0, 6.0), "pivot_hz": _f(1000.0, 100.0, 10000.0)}, analysis=("spectrum",)),

    _spec("audio.dynamic_eq.resonance", "dynamic_eq", "Supresión dinámica de resonancia",
        "Atenúa una resonancia solo cuando supera el umbral medido.", {
        "frequency_hz": _f(3000.0, 20.0, 20000.0), "q": _f(3.0, 0.3, 20.0),
        "threshold_db": _f(-24.0, -80.0, 0.0),
        "max_reduction_db": _f(2.0, 0.1, 6.0), "ratio": _f(2.0, 1.0, 12.0),
        "attack_ms": _f(15.0, 0.1, 500.0), "release_ms": _f(180.0, 5.0, 2000.0),
        "scope": _choice("stereo", "stereo", "mid", "side"),
        "filter_type": _choice("bell", "bell", "lowshelf", "highshelf")},
        bands=True, analysis=("spectrum", "band_rms")),
    _spec("audio.dynamic_eq.motion", "dynamic_eq", "Movimiento tonal dinámico",
        "Realza o recorta suavemente una zona según su energía instantánea.", {
        "frequency_hz": _f(3000.0, 20.0, 20000.0), "q": _f(0.8, 0.3, 6.0),
        "threshold_db": _f(-30.0, -80.0, 0.0), "gain_db": _f(0.0, -2.0, 2.0),
        "ratio": _f(1.5, 1.0, 6.0), "attack_ms": _f(80.0, 5.0, 1000.0),
        "release_ms": _f(350.0, 20.0, 3000.0),
        "scope": _choice("stereo", "stereo", "mid", "side"),
        "filter_type": _choice("bell", "bell", "lowshelf", "highshelf")},
        bands=True, analysis=("spectrum", "band_rms")),

    _spec("audio.vocal.resonance_suppressor", "vocal", "Supresor de resonancias vocales",
        "Reduce dinámicamente resonancias centrales compatibles con una voz.", {
        "frequency_hz": _f(3500.0, 1800.0, 8000.0), "q": _f(3.5, 0.8, 12.0),
        "threshold_db": _f(-28.0, -80.0, 0.0), "max_reduction_db": _f(1.5, 0.1, 2.5),
        "ratio": _f(2.0, 1.0, 8.0), "attack_ms": _f(18.0, 2.0, 100.0),
        "release_ms": _f(180.0, 30.0, 1000.0), "filter_type": _choice("bell", "bell")},
        analysis=("vocal_center", "spectrum")),
    _spec("audio.vocal.center_naturalizer", "vocal", "Naturalizador vocal central",
        "Restaura cuerpo y suaviza dureza/aire artificial sólo sobre Mid.", {
        "body_frequency_hz": _f(300.0, 180.0, 450.0), "body_gain_db": _f(0.0, 0.0, 1.5),
        "harshness_frequency_hz": _f(3500.0, 2500.0, 5000.0),
        "harshness_reduction_db": _f(0.0, 0.0, 2.5),
        "air_frequency_hz": _f(8500.0, 6000.0, 14000.0),
        "air_reduction_db": _f(0.0, 0.0, 2.0), "mix": _f(0.25, 0.05, 0.4)},
        analysis=("vocal_center", "spectrum")),

    _spec("audio.transient.dynamic_control", "transient", "Control dinámico de transientes", "Suaviza o recupera ataques medidos.", {
        "amount_db": _f(0.0, -2.0, 1.5), "threshold_db": _f(-18.0, -40.0, -3.0),
        "attack_ms": _f(10.0, 0.5, 80.0), "release_ms": _f(120.0, 20.0, 600.0)}, analysis=("transient_crest_db",)),
    _spec("audio.stereo.correlation_guard", "stereo_guard", "Guardia de correlación estéreo", "Corrige ancho según correlación medida.", {
        "width": _f(1.0, 0.5, 1.2)}, analysis=("stereo_correlation",)),
    _spec("audio.low_end.dynamic_balance", "low_end", "Balance dinámico de graves", "Reduce o refuerza graves medidos.", {
        "frequency_hz": _f(100.0, 45.0, 220.0), "q": _f(0.7, 0.3, 2.0), "threshold_db": _f(-28.0, -60.0, -3.0),
        "gain_db": _f(0.0, -2.5, 1.5), "ratio": _f(1.5, 1.0, 5.0), "attack_ms": _f(60.0, 10.0, 300.0),
        "release_ms": _f(300.0, 80.0, 1200.0), "filter_type": _choice("lowshelf", "lowshelf")}, analysis=("low_end_level_db", "low_end_mid_ratio")),
    _spec("audio.spectral.deharsh", "spectral", "De-harsh dinámico", "Reduce dureza espectral amplia.", {
        "frequency_hz": _f(3800.0, 2200.0, 7000.0), "q": _f(0.8, 0.3, 2.0), "threshold_db": _f(-28.0, -60.0, -3.0),
        "max_reduction_db": _f(1.0, 0.1, 2.5), "ratio": _f(1.5, 1.0, 5.0), "attack_ms": _f(30.0, 5.0, 200.0),
        "release_ms": _f(220.0, 40.0, 1200.0), "filter_type": _choice("bell", "bell")}, analysis=("harshness_excess_db",)),
    _spec("audio.spectral.dullness_recovery", "spectral", "Recuperación de claridad", "Realce dinámico limitado ante opacidad medida.", {
        "frequency_hz": _f(8500.0, 5000.0, 14000.0), "q": _f(0.7, 0.3, 2.0), "threshold_db": _f(-35.0, -70.0, -3.0),
        "max_boost_db": _f(0.5, 0.1, 1.5), "ratio": _f(1.4, 1.0, 4.0), "attack_ms": _f(80.0, 10.0, 400.0),
        "release_ms": _f(400.0, 80.0, 1600.0), "filter_type": _choice("highshelf", "highshelf")}, analysis=("dullness_deficit_db",)),

    _spec("audio.multiband.eq", "multiband", "Ganancia multibanda", "Ajusta una banda del procesador multibanda.", {
        "gain_db": _f(0.0, -6.0, 6.0)}, bands=True, analysis=("band_rms",)),
    _spec("audio.multiband.stereo_width", "multiband", "Ancho estéreo multibanda", "Ajusta el ancho estéreo de una banda.", {
        "width": _f(1.0, 0.0, 2.5)}, bands=True, analysis=("stereo_width", "band_rms")),
    _spec("audio.multiband.compressor", "multiband", "Compresor multibanda", "Controla la dinámica de una banda.", {
        "threshold_db": _f(-18.0, -60.0, 0.0), "ratio": _f(1.2, 1.0, 20.0),
        "attack_ms": _f(10.0, 0.1, 500.0), "release_ms": _f(100.0, 5.0, 3000.0),
        "knee_db": _f(4.0, 0.0, 20.0), "makeup_db": _f(0.0, -12.0, 12.0)},
        bands=True, analysis=("band_rms", "band_peak", "crest_factor")),
    _spec("audio.multiband.limiter", "multiband", "Limitador multibanda", "Limita picos de una banda.", {
        "ceiling_db": _f(-3.0, -12.0, 0.0), "release_ms": _f(50.0, 5.0, 1000.0)},
        bands=True, analysis=("band_peak",)),
    _spec("audio.multiband.saturation", "multiband", "Saturación multibanda", "Añade armónicos a una banda.", {
        "drive_db": _f(0.0, -24.0, 24.0), "mix": _f(0.0, 0.0, 1.0),
        "type": _choice("Tape", "Tape", "Tube")}, bands=True, analysis=("band_rms", "band_peak")),

    _spec("audio.saturation.softclip", "saturation", "Saturación softclip", "Saturación global con mezcla paralela.", {
        "drive_db": _f(0.0, -24.0, 24.0), "mix": _f(0.0, 0.0, 1.0),
        "type": _choice("Tape", "Tape", "Tube"), "oversampling": ParameterSpec("int", 2, 1, 4)},
        conflicts=("audio.saturation.exciter",), analysis=("lufs", "true_peak", "crest_factor")),
    _spec("audio.saturation.exciter", "saturation", "Exciter", "Añade armónicos en altas frecuencias.", {
        "frequency_hz": _f(8000.0, 1000.0, 20000.0), "amount": _f(2.0, 0.0, 10.0),
        "mix": _f(0.0, 0.0, 1.0)}, conflicts=("audio.saturation.softclip",), analysis=("spectrum",)),
    _spec("audio.saturation.hard_clip", "saturation", "Hard clipper", "Recorta picos antes del limitador final.", {
        "ceiling_db": _f(-1.5, -12.0, 0.0)}),

    _spec("audio.deesser.sibilance_reduction", "deesser", "Reducción de sibilancia", "Reduce energía sibilante preservando el resto.", {
        "frequency_hz": _f(6000.0, 3000.0, 12000.0), "intensity": _f(0.7, 0.0, 1.5)},
        analysis=("sibilance", "sample_rate")),
    _spec("audio.glue.bus_compressor", "glue", "Glue compressor", "Compresión suave del bus final.", {
        "threshold_db": _f(-18.0, -40.0, 0.0), "ratio": _f(1.4, 1.0, 4.0),
        "attack_ms": _f(20.0, 1.0, 100.0), "release_ms": _f(120.0, 10.0, 500.0),
        "knee_db": _f(6.0, 0.0, 10.0), "makeup_db": _f(0.0, -12.0, 12.0)},
        analysis=("lufs", "crest_factor", "lra")),

    _spec("audio.autogain.headroom", "autogain", "Headroom", "Reserva margen antes del procesamiento.", {
        "gain_db": _f(-17.0, -30.0, 0.0)}, analysis=("true_peak", "lufs")),
    _spec("audio.autogain.output_gain", "autogain", "Ganancia de salida", "Ajusta ganancia positiva o negativa de salida.", {
        "gain_db": _f(0.0, -24.0, 24.0)}),
    _spec("audio.autogain.interstage_limiter", "autogain", "Limitador entre etapas", "Protege el nivel interno entre plugins.", {
        "ceiling_db": _f(0.0, -12.0, 0.0), "attack_ms": _f(1.0, 0.1, 80.0),
        "release_ms": _f(50.0, 1.0, 8000.0)}),
    _spec("audio.autogain.final_peak", "autogain", "Control de pico final", "Controla el pico antes de loudness.", {
        "ceiling_db": _f(-3.0, -12.0, 0.0)}),

    _spec("audio.loudness.normalize", "loudness", "Normalización de loudness", "Normaliza según EBU R128.", {
        "target_lufs": _f(-14.0, -70.0, -5.0), "true_peak_db": _f(-1.0, -9.0, 0.0),
        "lra": _f(11.0, 1.0, 50.0), "dual_mono": _b(False)}, analysis=("loudness_stats",)),
    _spec("audio.loudness.fade_in", "loudness", "Fade in", "Aplica entrada gradual.", {
        "duration_seconds": _f(0.0, 0.0, 600.0)}),
    _spec("audio.loudness.fade_out", "loudness", "Fade out", "Aplica salida gradual.", {
        "duration_seconds": _f(0.0, 0.0, 600.0)}, analysis=("duration",)),
    _spec("audio.limiter.true_peak", "master_limiter", "Limitador True Peak", "Protección final de picos inter-sample.", {
        "ceiling_db": _f(-1.0, -9.0, 0.0), "release_ms": _f(150.0, 10.0, 1000.0),
        "lookahead_ms": _f(5.0, 0.1, 20.0), "mode": _choice("transparent", "transparent", "musical", "aggressive"),
        "oversampling": ParameterSpec("int", 4, choices=(1, 2, 4))},
        analysis=("true_peak", "sample_rate")),
)


LEGACY_FUNCTION_ALIASES = {
    "repair": "audio.repair.denoise",
    "deesser": "audio.deesser.sibilance_reduction",
    "tone_eq": "audio.tone_eq.band",
    "dynamic_eq": "audio.multiband.compressor",
    "stereo_width": "audio.multiband.stereo_width",
    "stereo_dynamic": "audio.multiband.stereo_width",
    "saturation": "audio.saturation.softclip",
    "glue": "audio.glue.bus_compressor",
    "autogain": "audio.autogain.final_peak",
    "loudness": "audio.loudness.normalize",
    "limiter": "audio.limiter.true_peak",
    "brickwall": "audio.limiter.true_peak",
    "master_limiter": "audio.limiter.true_peak",
}


function_registry = AudioFunctionRegistry(LEGACY_FUNCTION_ALIASES)
function_registry.register_many(FUNCTION_SPECS)


PLUGIN_ID_BY_PROCESS_ID = {
    "repair": "audio.repair", "deesser": "audio.deesser",
    "tone_eq": "audio.tone_eq", "dynamic_eq": "audio.dynamic_eq", "vocal": "audio.vocal",
    "transient": "audio.transient", "stereo_guard": "audio.stereo_guard", "low_end": "audio.low_end",
    "spectral": "audio.spectral", "multiband": "audio.multiband",
    "saturation": "audio.saturation", "glue": "audio.glue",
    "autogain": "audio.autogain", "loudness": "audio.loudness",
    "master_limiter": "audio.master_limiter",
}
