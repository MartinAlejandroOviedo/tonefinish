# ToneFinish Docs

ToneFinish es una aplicacion de audio para analizar, normalizar y finalizar archivos de musica o dialogo usando un flujo automatico basado en ffmpeg. El objetivo es lograr niveles de loudness estables (LUFS y True Peak), controlar bandas con un ecualizador dinamico por bandas, y generar un reporte tecnico de antes y despues.

## Que hace
- Analiza loudness en dos pasadas (LUFS, LRA, True Peak).
- Ajusta con normalizacion y limitador brickwall.
- Control dinamico por bandas con compand.
- Control de stereo por bandas (graves mas cerrados, agudos mas abiertos).
- De-esser opcional para reducir sibilancia.
- Glue compression opcional para dar cohesión.
- Fade in/out opcional.
- Procesamiento por lote con tabla de resultados.
- Reporte TOML por archivo con metrica y diagnostico.
- Firma digital en WAV (metadata) con presets guardables.

## Flujo general
1) Selecciona un archivo o una carpeta (lote).
2) Elige preset de LUFS o modo manual.
3) Opcional: ajusta procesos (dinamica por bandas, limiter, stereo width, de-esser).
4) Ejecuta "Procesar audio" o "Procesar lote".
5) Re-analiza la salida y muestra resultados antes/despues.

## Reportes
Cada salida genera un reporte TOML en la carpeta `log/` dentro de la carpeta de salida. Incluye:
- Settings usados.
- Metricas before/after.
- Diagnostico y recomendaciones.
- Firma digital aplicada.

## Requisitos
- Debian Trixie o similar.
- Python 3.9+
- ffmpeg en el PATH.

## Instalacion (Debian)
1) Construir paquete:
   - `./packaging/build_deb.sh`
2) Instalar:
   - `sudo apt install ./releases/tonefinish_1.0.0.deb`

El paquete crea un entorno virtual en `/usr/lib/tonefinish/.venv` e instala dependencias con pip.

## Notas de calidad
El diagnostico "Necesita trabajo" es tecnico: indica que la salida no cumple con el objetivo de LUFS, true-peak o dinamica.
