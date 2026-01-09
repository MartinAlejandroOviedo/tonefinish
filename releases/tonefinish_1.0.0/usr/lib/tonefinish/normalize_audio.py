#!/usr/bin/env python3
"""CLI/GUI entry point for ToneFinish."""

import argparse
import pathlib
import sys

from audio_analysis import analyze_audio
from audio_processing import ensure_output_path, normalize_audio
from audio_tools import ensure_ffmpeg_available
from ui_app import run_gui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analiza y normaliza/limita un archivo WAV al nivel objetivo usando ffmpeg loudnorm (EBU R128).",
    )
    parser.add_argument("input", nargs="?", type=pathlib.Path, help="Ruta del WAV de entrada.")
    parser.add_argument(
        "-o",
        "--output",
        type=pathlib.Path,
        help="Ruta del WAV de salida. Por defecto usa <input>_normalized.wav en la misma carpeta.",
    )
    parser.add_argument(
        "--target",
        type=float,
        default=-14.0,
        help="Objetivo de loudness integrado en LUFS. Ej.: -14 para streaming. (default: -14)",
    )
    parser.add_argument(
        "--true-peak",
        type=float,
        default=-1.5,
        help="Límite de true peak (dBTP). (default: -1.5)",
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Solo analizar, no escribir archivo de salida.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Permitir sobrescribir el archivo de salida si existe.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Muestra los comandos ffmpeg ejecutados.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Lanza la interfaz gráfica (PySide6) en lugar del modo CLI.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.gui or args.input is None:
        return run_gui()

    input_path = args.input
    if not input_path.exists():
        parser.error(f"El archivo de entrada no existe: {input_path}")

    output_path = args.output
    if output_path is None:
        output_path = input_path.with_stem(f"{input_path.stem}_normalized")
    output_format = output_path.suffix.lstrip(".") if output_path.suffix else None
    output_path = ensure_output_path(output_path, output_format)

    ensure_ffmpeg_available()

    print(f"Analizando {input_path} (target {args.target} LUFS, TP {args.true_peak} dBTP)...")
    stats, _log = analyze_audio(input_path, args.target, args.true_peak, verbose=args.verbose)

    print("Resultados de análisis:")
    print(f"  Input I (LUFS): {stats['input_i']}")
    print(f"  Input TP (dBTP): {stats['input_tp']}")
    print(f"  Input LRA (LU): {stats['input_lra']}")
    print(f"  Input Threshold (dB): {stats['input_thresh']}")
    print(f"  Offset recomendado: {stats['target_offset']}")

    if args.analyze_only:
        return 0

    print(f"Normalizando y limitando -> {output_path} ...")
    normalize_audio(
        input_path=input_path,
        output_path=output_path,
        stats=stats,
        target_lufs=args.target,
        true_peak=args.true_peak,
        overwrite=args.overwrite,
        verbose=args.verbose,
        output_format=output_format,
    )
    print("Normalización completada.")
    return 0


if __name__ == "__main__":  # pragma: no cover - ejecución directa
    sys.exit(main())
