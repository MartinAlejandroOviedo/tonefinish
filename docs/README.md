# ToneFinish Docs

ToneFinish es una aplicacion de audio para analizar, normalizar y finalizar pistas usando un flujo automatico con ffmpeg. El objetivo es lograr niveles estables de loudness (LUFS y True Peak), controlar bandas con procesamiento dinamico por bandas, dosificar la carga del sistema y entregar un reporte tecnico de antes y despues.

## ⚡ Novedades v1.7.4

### ✅ Reparación de material áspero (v1.7.4)
- Flujo documentado para material percibido como "roto" en medios/media-aguda.
- Criterio de diagnóstico para separar clipping duro de dureza espectral.
- Cadena base de rescate con `adeclip` + EQ dinámica + de-esser + limitador suave.

### ✅ Correcciones de estabilización (v1.7.3)
- Guard de `peak_risk` mejorado: valida por tasa/minuto y severidad.
- El MTS para guard se calcula sobre la salida procesada.
- Detección de `peak_risk` con filtro anti-falsos positivos en picos medios aislados.
- Lote en modo secuencial estricto: cada tema cierra ciclo completo antes del siguiente.

### 🧠 Auto-Master con movimiento musical (nuevo, Unreleased)
- Subbass dinámico anti-fatiga (control automático cuando el low-end viene cargado)
- Band Motion Fase 1: movimiento sutil por energía real de bandas
- Band Motion Fase 2: sincronía al compás con BPM/pulso estimados
- Protección vocal y guardrails de mono/estéreo para evitar artefactos
- Fase 5: controles de usuario para perfil (`auto/tight/balanced/airy`) y cantidad (0-150%)
- Fase 6: presets rápidos de movimiento (`Off/Subtle/Musical/Creative`)

### 🧩 Auto-Master adaptativo (Fases 7-8, Unreleased)
- Generación de MTS (métricas temporales por segundo), secciones y eventos por tema.
- Plan de decisiones por sección (`master_decisions`) para ajustes adaptativos trazables.
- Evaluación `shadow` y `guard` con recomendación de modo (`shadow_only` o `apply_candidate`).
- Reporte A/B de rollout en lotes con bucket canario estable por archivo.
- Nuevo Inspector en Resultados para abrir `.mts.json` y ver artefactos relacionados.

### 🧪 Lote por tema
- Deep analysis por archivo antes de procesar cada tema
- Procesamiento secuencial, un tema a la vez
- Validación final liviana basada en loudness y true peak
- Menor carga de CPU, disco y FFmpeg en el análisis del lote

### 🧠 Governor de recursos
- Monitoreo pasivo de CPU, RAM, RAM libre y procesos ffmpeg
- Perfiles estándar por capacidad de máquina
- Selector manual con modo Auto
- Persistencia del perfil por instalación
- Dosificación básica de procesos FFmpeg

### ⚙️ Benchmark espectral
- Benchmark en UI para comparar CPU vs GPU sobre un archivo de audio
- Benchmark por consola con `python3 main.py --benchmark-spectrum archivo.wav`
- Reporte separado de GPU física y backend GPU disponible
- Recomendación automática para decidir si conviene ampliar a `analysis.features`

### 📋 Estados de proceso
- Tarjeta visible de estado en Procesamiento
- Color por etapa de trabajo
- Historial corto de mensajes en la UI
- Historial por lote con tiempos por archivo y por etapa

### 🧪 Lote más estable
- Procesamiento en carpetas temporales por archivo
- Copia del resultado final solo al terminar cada archivo

### 🎚️ Ajustes de mezcla
- Sub bass independiente con valores negativos y positivos
- Stereo width por bandas mantenido
- Stereo dinámico por bandas retirado de la UI
- Saturación mínima como color controlado

## Que hace
- Analiza loudness en dos pasadas (LUFS, LRA, True Peak).
- Normaliza y aplica limitador brickwall.
- Control dinamico por bandas con EQ/compand.
- Control de stereo por bandas (graves mas cerrados, agudos mas abiertos).
- Movimiento musical por bandas con sincronía de tempo (cuando hay BPM confiable).
- Análisis temporal MTS (ventana/hop) para métricas por tramo, eventos y secciones.
- Decisiones adaptativas por sección con artefactos JSON/MD de auditoría.
- Guardrails de rollout para validar LUFS/True Peak/eventos antes de habilitar apply.
- De-esser opcional para reducir sibilancia.
- Glue compression opcional.
- Fades (globales o por archivo).
- Procesamiento por lote secuencial, tema por tema.
- Reporte TOML por archivo con metricas y diagnostico.
- Firma digital en WAV (metadata) con presets guardables.

## Flujo general
1) Selecciona un archivo o una carpeta (lote).
2) Elige preset de LUFS o modo manual.
3) Opcional: ajusta procesos (dinamica por bandas, limiter, stereo width, de-esser).
4) Ejecuta "Procesar audio" o "Procesar lote".
5) Re-analiza la salida y muestra resultados antes/despues.

## Pestañas principales
- Inicio: modo de trabajo y resumen rapido.
- Audio / Lote: seleccion de archivos.
- Presets: LUFS, True Peak y salida.
- Procesos: parametros de procesado.
- Ondas: forma de onda interactiva y fades por archivo.
- Firma Digital: metadata obligatoria y presets.
- Resultados: tablas y logs.
- Inspector (en Resultados): vista de MTS + decisiones + shadow + guard por tema.
- About: creditos.

## Fades por archivo
En la pestaña Ondas podes ajustar Fade in/out por tema. Si no hay override, se usa el valor global del formulario.

## Reportes
Cada salida genera un reporte TOML en la carpeta `log/` dentro de la carpeta de salida. Incluye:
- Settings usados.
- Metricas before/after.
- Diagnostico y recomendaciones.
- Firma digital aplicada.

Adicionalmente, el flujo adaptativo escribe:
- `<tema>.mts.json` y `<tema>.mts.md`
- `<tema>.master_decisions.json` y `<tema>.master_decisions.md`
- `<tema>.adaptive_shadow.json` y `<tema>.adaptive_shadow.md`
- `<tema>.adaptive_guard.json` y `<tema>.adaptive_guard.md`
- `batch_rollout_YYYYMMDD_HHMMSS.json` y `.md` (solo en lote)

Todos se guardan en `log/`.

## Flujo adaptativo y criterio actual
1) El procesamiento de audio del lote es secuencial: tema por tema.
2) El análisis temporal MTS se encola con 1 worker dedicado para no saturar CPU.
3) `master_decisions` calcula acciones por sección (no aplica audio por sí solo).
4) `adaptive_shadow` estima riesgo global y `apply_ready`.
5) `adaptive_guard` valida resultado técnico (LUFS/TP/eventos) y recomienda modo.
6) En Fase 8, el reporte A/B decide `enable_apply` por canary, sin forzar cambios de audio en esta etapa.

## Feature Flags (rollout adaptativo)
- `TONEFINISH_ADAPTIVE_MASTER_ENABLED` (default `false`): habilita candidatos a apply en lógica de rollout.
- `TONEFINISH_ADAPTIVE_SHADOW_ENABLED` (default `true`): flag reservado para control de shadow (hoy informativo).
- `TONEFINISH_ADAPTIVE_GUARD_STRICT` (default `true`): tolerancias más estrictas en guard.
- `TONEFINISH_ADAPTIVE_ROLLOUT_PERCENT` (default `0`, rango `0-100`): porcentaje canario en lote.

## Notas tecnicas
- `docs/BATCH_PERFORMANCE.md` - Comparacion del lote por tema con resultados observados.
- `docs/ADAPTIVE_MASTER_WORKFLOW.md` - Flujo detallado Fases 1-8, artefactos y rollout.
- `docs/REPAIR_HARSHNESS_WORKFLOW.md` - Protocolo de rescate para material con dureza en medios/media-aguda.
- `python3 main.py --benchmark-spectrum archivo.wav` - Prueba rápida para medir CPU vs GPU en el espectro.

## Requisitos
- Debian Trixie o similar.
- Python 3.9+
- ffmpeg en el PATH.
- pyqtgraph (opcional, solo para waveform interactiva).

## Instalacion (Debian)
1) Construir paquete:
   - `./packaging/build_deb.sh`
2) Instalar:
   - `sudo apt install ./releases/tonefinish_<version>.deb`

El paquete crea un entorno virtual en `/usr/lib/tonefinish/.venv` e instala dependencias con pip.

## Notas de calidad
El diagnostico "Necesita trabajo" es tecnico: indica que la salida no cumple con el objetivo de LUFS, true-peak o dinamica.
