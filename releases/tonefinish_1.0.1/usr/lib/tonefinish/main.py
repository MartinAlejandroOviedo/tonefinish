#!/usr/bin/env python3
"""Entry point para lanzar la interfaz gráfica de normalización."""

import sys

from ui_app import run_gui


def main() -> int:
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
