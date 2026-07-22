#!/usr/bin/env python3
"""Entry point para lanzar la interfaz gráfica o benchmarks puntuales."""

import argparse
import pathlib
import sys

from runtime_reproducibility import check_runtime_reproducibility


def _format_benchmark_output(result: dict) -> str:
    lines = [
        "Benchmark de espectro:",
        f"GPU física: {'sí' if result.get('gpu_hardware_available') else 'no'}",
        f"Backend GPU: {'sí' if result.get('gpu_backend_available') else 'no'}",
        f"CPU promedio: {result.get('cpu_avg_seconds', 0.0):.3f} s",
    ]
    gpu_avg = result.get("gpu_avg_seconds")
    if gpu_avg is not None:
        lines.append(f"GPU promedio: {gpu_avg:.3f} s")
    speedup = result.get("speedup")
    if speedup is not None:
        lines.append(f"Speedup GPU/CPU: {speedup:.2f}x")
    lines.append(f"Recomendación: {result.get('recommended_next_stage', 'cpu_only')}")
    if result.get("recommended_next_stage") == "analysis.features":
        lines.append("Siguiente paso: probar features en GPU.")
    elif result.get("recommended_next_stage") == "analysis.spectrum":
        lines.append("Siguiente paso: mantener el espectro como candidato GPU.")
    elif result.get("recommended_next_stage") == "gpu_backend_missing":
        lines.append("Siguiente paso: instalar o habilitar el backend GPU.")
    else:
        lines.append("Siguiente paso: permanecer en CPU-only.")
    return "\n".join(lines)


def _run_spectrum_benchmark(path: pathlib.Path, duration: float, runs: int) -> int:
    from spectrum_analyzer import benchmark_spectrum_fft

    if not path.exists():
        print(f"Error: el archivo no existe: {path}", file=sys.stderr)
        return 2

    result = benchmark_spectrum_fft(path, duration=duration, verbose=False, runs=runs)
    print(_format_benchmark_output(result))
    return 0


def main() -> int:
    repro = check_runtime_reproducibility()
    if repro.warnings:
        print("Aviso de reproducibilidad:", file=sys.stderr)
        for item in repro.warnings:
            print(f"- {item}", file=sys.stderr)

    parser = argparse.ArgumentParser(description="Finisher audio mastering")
    parser.add_argument(
        "--benchmark-spectrum",
        metavar="PATH",
        help="Ejecuta el benchmark CPU vs GPU del análisis espectral sobre un archivo.",
    )
    parser.add_argument(
        "--benchmark-duration",
        type=float,
        default=10.0,
        help="Duración en segundos del fragmento usado por el benchmark espectral.",
    )
    parser.add_argument(
        "--benchmark-runs",
        type=int,
        default=3,
        help="Cantidad de corridas por backend para el benchmark espectral.",
    )
    args = parser.parse_args()

    if args.benchmark_spectrum:
        return _run_spectrum_benchmark(
            pathlib.Path(args.benchmark_spectrum),
            duration=args.benchmark_duration,
            runs=args.benchmark_runs,
        )

    from ui_app import run_gui

    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
