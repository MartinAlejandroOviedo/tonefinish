# Normalizador de audio (ffmpeg + Python)

CLI sencilla que analiza un WAV, calcula su loudness y genera una versión normalizada/limitada usando el filtro `loudnorm` de ffmpeg (EBU R128). Útil para dejar el nivel en un estándar típico de streaming/podcast (ej. -14 LUFS, true peak -1.5 dBTP).

## Requisitos
- Python 3.9+
- ffmpeg en el `PATH` (con el filtro `loudnorm`, incluido en builds estándar)
- PySide6 para la interfaz (`pip install -r requirements.txt`)

## Uso rápido
```bash
# Crear entorno y dependencias
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Interfaz gráfica (PySide6)
python3 normalize_audio.py --gui

# Análisis + normalización (sobrescribe salida si existe con --overwrite)
python3 normalize_audio.py input.wav --target -14 --true-peak -1.5 --overwrite

# Solo analizar sin escribir archivo
python3 normalize_audio.py input.wav --analyze-only

# Elegir ruta de salida
python3 normalize_audio.py input.wav -o mezcla_final.wav
```

Parámetros principales:
- `--target`: loudness integrado objetivo en LUFS (default: -14).
- `--true-peak`: límite de true peak en dBTP (default: -1.5).
- `--overwrite`: permite reemplazar el archivo de salida si ya existe.
- `--verbose`: muestra los comandos ffmpeg ejecutados y logs completos.

## Cómo funciona
1) Primera pasada con `loudnorm` en modo de análisis (`print_format=json`) para medir LUFS, LRA, TP y offset recomendado.  
2) Segunda pasada aplicando `loudnorm` con los valores medidos (flujo de dos pasadas estándar) para lograr el objetivo de loudness y limitar el true peak.

Si solo necesitas escanear sin modificar el archivo, usa `--analyze-only`.
