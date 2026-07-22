## 4.2.1 (2026-07-21)

### 🧠 Auto-Master IA
- **NUEVO:** Contrato canónico por función con `function_id`, parámetros validados, razones y confianza.
- **NUEVO:** Intención bidireccional `cut|boost|attenuate|expand|narrow|protect|neutral`.
- **NUEVO:** Evidencia medible obligatoria para cada decisión de DeepSeek.
- **NUEVO:** Validación cruzada entre operación y signo; un boost negativo o cut positivo se rechaza.
- **NUEVO:** Decisiones neutrales trazables que no ingresan al grafo DSP.
- **MEJORADO:** Auditoría final con operación, evidencia y resumen de cortes/boosts/protecciones ejecutados.
- **NUEVO:** Gobernadores canónicos de presupuesto tonal, ganancia y solapamiento espectral.
- **NUEVO:** Límites individuales y acumulados que no pueden eludirse dividiendo una corrección.
- **NUEVO:** Evidencia semántica obligatoria: exceso para cuts, déficit para boosts y necesidad para makeup.
- **NUEVO:** `decision_trace.budget_report` con uso, remanente, contribuciones y rechazos por banda.
- **NUEVO:** EQ dinámica por IDs `audio.dynamic_eq.resonance` y `audio.dynamic_eq.motion`.
- **NUEVO:** Detección local de resonancias y relación Mid/Side entregada a DeepSeek como evidencia autorizada.
- **NUEVO:** Validación de frecuencia, banda, exceso espectral y scope Mid/Side antes de ejecutar una decisión.
- **MEJORADO:** Movimientos dinámicos firmados, incluidos valores sub-1 dB mediante mezcla seca/procesada.
- **NUEVO:** Procesamiento vocal sin stems con IDs `audio.vocal.resonance_suppressor` y `audio.vocal.center_naturalizer`.
- **NUEVO:** Confianza vocal central calculada localmente y exigida antes de autorizar cualquier proceso vocal.
- **NUEVO:** Supresión dinámica sólo sobre Mid, limitada a `-2,5 dB`, con resonancia 1,8–8 kHz confirmada.
- **NUEVO:** Naturalizador Mid paralelo para cuerpo, dureza y aire; cada adición/corte exige evidencia específica.
- **PROTECCIÓN:** Side intacto, sin vibrato/chorus automático y rechazo ante presencia vocal incierta.
- **NUEVO:** Cinco plugins complementarios: transientes, correlación estéreo, balance dinámico de graves, de-harsh y recuperación de opacidad.
- **NUEVO:** Métricas locales de crest transiente, correlación, balance grave, dureza y déficit de aire para autorizar decisiones.
- **PROTECCIÓN:** Expansión estéreo sólo con correlación `>=0,70`; estrechamiento sólo ante correlación negativa.
- **MEJORADO:** Graves y claridad admiten cortes/realces firmados dentro del presupuesto tonal y con evidencia coincidente.
- **NUEVO:** Render temporal MTS real por secciones, con automatizaciones firmadas y rampas de 150–500 ms.
- **NUEVO:** Correcciones adaptativas limitadas a `±0,8 dB`, identificadas como `audio.dynamic_eq.motion`.
- **NUEVO:** Render transaccional sobre temporal, recalibración LUFS/True Peak y publicación sólo tras `adaptive_guard`.
- **NUEVO:** `adaptive_render.json/.md` y resumen integrado en `.ai_master.json` con acciones realmente ejecutadas.
- **MEJORADO:** Rollout adaptativo predeterminado al 100% ahora que existe render real; sigue sujeto a shadow y guardia estricta.
- **PROTECCIÓN:** Fallback automático conserva el master estático ante error de render, medición o validación.
- **NUEVO:** Certificación reproducible de los 36 IDs mediante `scripts/certify_audio_catalog.py`.
- **NUEVO:** Comparador A/B con duración, delta RMS/nivel, correlación, pico y muestras clippeadas.
- **NUEVO:** Huella SHA-256 por acción ejecutada, incluyendo parámetros, operación y evidencia.
- **MEJORADO:** Tolerancia final de auditoría endurecida de `0,60` a `0,30 LU`.
- **VALIDADO:** Todos los IDs tienen implementación registrada y rechazo de parámetros fuera de rango.
- **VALIDADO:** Mid/Side conserva fase, duración y headroom sin clipping en prueba A/B real.
- **FIX:** Extracciones binarias de análisis usan `-` para stdout; evita que wrappers creen o sobrescriban un archivo literal `pipe:1`.
- **FIX:** Análisis combinado bandas/voz ahora expone y mapea una salida FFmpeg real; elimina el error `filtergraph has zero outputs`.
- **FIX:** Métricas `volumedetect` ordenadas por ID de filtro, no por el orden inverso del log FFmpeg.
- **FIX:** Caché de análisis versionado; invalida entradas legacy o con las seis bandas en piso.
- **FIX:** Evidencia `loudness_stats` anidada se aplana, mientras LUFS/TP se reemplazan por medición local autoritativa.
- **FIX:** Shadow y guardia comparten autorización efectiva; el render informa el motivo exacto cuando no se aplica.
- **FIX:** Resultado de análisis batch convertido a campos nombrados; evita desempaquetar cuatro métricas en tres variables y caer a bandas vacías.
- **FIX:** Publicación adaptativa compatible con `/tmp` y destino en filesystems distintos: copia a temporal hermano y reemplazo atómico local.
- **NUEVO:** Auditoría de acciones planeadas y ejecutadas, huellas de catálogo/fuente y orden efectivo.
- **MEJORADO:** DeepSeek decide por tema; sin tokens o ante rechazo se usa exclusivamente `SUNO Clásico`.
- **ELIMINADO:** Modo manual y fallback heurístico legacy en la ruta de decisión IA.

### 🔊 Procesamiento y validación
- **FIX:** Recalibración LUFS/True Peak con hasta cuatro iteraciones conservadoras y medición realimentada.
- **FIX:** `alimiter` usa `level=false`, evitando que la compensación automática aumente el volumen.
- **FIX:** Runtime SpASM propagado a todos los subprocesos del skill FFmpeg.
- **FIX:** CLI SpASM sin dependencia obligatoria de `rg`; ahora valida el código de salida real.
- **FIX:** Generación completa de shadow, guard y validación adaptativa.
- **VALIDADO:** Master de referencia a `-15.50 LUFS`, True Peak seguro y estado `PASS`.

### 🖥️ Interfaz y archivos
- **MEJORADO:** Texto blanco para la interfaz oscura.
- **MEJORADO:** Salidas nombradas como `Artista - canción`.
- **MEJORADO:** Flujo Auto-Master secuencial por tema, exclusivamente IA/SUNO.

### 📦 Empaquetado Debian
- **ACTUALIZADO:** Versión `4.2.1`.
- **FIX:** Inclusión de `output_naming.py` y módulos del orquestador canónico.
- **FIX:** Detección portable de `spasm`, sin depender de rutas personales.
- **NUEVO:** Dependencias `spasm` y `spasm-skill-ffmpeg-subset` declaradas en el paquete.
- **NUEVO:** Constructor Debian alternativo con `ar`/`tar` cuando `dpkg-deb` no está disponible.

## 4.0.0 (2026-07-14)

### 🎸 Bandcamp IA — Generación de textos
- **NUEVO:** Tab "🧠 Contexto IA" con prompts SUNO, letras y metadatos.
- **NUEVO:** Tab "🎸 Bandcamp" con generación automática de textos para formularios.
- **NUEVO:** Módulo `bandcamp_bok.py` (376 líneas) — orquestador de generación.
- **NUEVO:** Soporte NVIDIA NIM API (`nvapi-...`) + DeepSeek API (`sk-...`).
- **NUEVO:** Generación de letras con IA (`🤖 Generar letra con IA`).
- **NUEVO:** Persistencia de API keys en `~/.tonefinish/api_keys.json`.
- **NUEVO:** Extracción de título desde archivo .wav.
- **NUEVO:** Copiar todo al portapapeles para pegar en Bandcamp.
- **NUEVO:** Precio sugerido basado en análisis (LUFS + LRA).

### 🧹 Limpieza de código
- **REFACTOR:** `bandcamp_bok.py` extrae toda la lógica de generación de `ui_app.py` (-150 líneas).
- **REFACTOR:** `call_ai()` unifica NVIDIA + DeepSeek con fallback a templates.

### 🛠️ Mejoras
- **FIX:** `audio_tools.py` — auto-limpieza de `/tmp` si < 100MB libres.
- **FIX:** `audio_tools.py` — retry automático en error "No space left on device".
- **FIX:** Compilador SpASM — soporte `float` (fixed-point ×100), `dict`, `print_float`.
- **FIX:** `finisher_adapt.spasm` — 6 métodos (health, adapt_preset, evaluate_mix, resolve_repair, classify_profile, compute_autogain).
- **FIX:** Indentación en métodos de Bandcamp.

### 📦 Empaquetado
- **FIX:** `bandcamp_bok.py` agregado a `build_deb.sh`.
- **FIX:** `FINISHER_FFMPEG_BIN` removido de `.profile` → auto-detecta `ffmpeg-spasm`.


## 1.7.37 (2026-05-27)

### 🛡️ Robustez Hybrid + FFmpeg
- **MEJORADO:** En modo `hybrid`, `normalize_audio` ahora hace fallback automático a Python si falla SpASM CLI.
- **MEJORADO:** Si FFmpeg falla por runtime `ffmpeg-spasm`, el motor reintenta automáticamente con `ffmpeg.real-spasm-backup` cuando está disponible.
- **MEJORADO:** Flujo de fades (`fade in/out`) estable incluso cuando hay fallback de backend.

### 🎚️ Control de Saturación Acumulada
- **NUEVO:** Guard-rail de riesgo acumulado por suma de procesos (EQ, saturación, stereo dynamic, glue, etc.) con atenuación preventiva automática antes de loudnorm final.
- **MEJORADO:** En material de baja LRA, AutoGain ya no se desactiva; pasa a modo conservador para mantener protección anti-clipping.

### 🎧 Auto-Master SUNO Clean (Conservador)
- **MEJORADO:** Ajuste anti-fatiga aplicado solo al preset `SUNO Clean (Mastering conservador)`:
  - reduce `High-Mid` y `Air` por defecto,
  - controla levemente `Subbass`,
  - mantiene `Mid` estable para preservar cuerpo/voz.
- **MEJORADO:** Activación explícita de dinámica por bandas en ese preset para sostener el perfil conservador en escuchas largas.

### 🔊 Stereo Dinámico por Bandas
- **CORREGIDO:** Activación efectiva de `stereo_dynamic_per_band` cuando hay mezcla por banda definida.
- **CORREGIDO:** Normalización de valores de mezcla por banda (acepta 0..1 y también 0..100).

# Changelog

## Unreleased

### 🧠 Auto-Master: Movimiento Musical por Bandas (Fase 1 + Fase 2)
- **NUEVO:** `Subbass dinámico (anti-fatiga)` con detección de low-end caliente por RMS/picos.
- **NUEVO:** Control automático de low-end cuando viene cargado:
  - umbrales más estrictos del limitador multibanda en `Subbass` y `Bass`
  - reducción de saturación por banda en graves
  - estabilización estéreo de graves (sub casi mono, bass con movimiento mínimo)
- **NUEVO:** `Band Motion Fase 1 (subtle)`:
  - modulación sutil por energía real de bandas (`RMS + peak`)
  - límites conservadores por banda para evitar bombeo y fatiga
  - protección vocal en `Mid` / `High-Mid` cuando la voz domina
- **NUEVO:** `Band Motion Fase 2` sincronizado al compás:
  - estimación liviana de `BPM` + claridad de pulso (autocorrelación de onsets)
  - sincronía musical en la respuesta dinámica (`attack/release`) y densidad de movimiento
  - fallback seguro si no hay BPM confiable
- **NUEVO:** `Band Motion Fase 3` (feedback adaptativo):
  - controlador de riesgo en tiempo de análisis (`THD`, `true peak`, `LRA`, `crest`, low-end y voz)
  - atenuación automática cuando sube riesgo de fatiga/artefactos
  - micro-empuje musical cuando el riesgo es bajo y el pulso es confiable
- **NUEVO:** `Band Motion Fase 4` (coreografía contextual):
  - perfil macro automático `tight | balanced | airy` según tempo, dinámica, voz y low-end
  - ajuste final de `stereo_dynamic_mix` y mezclas por banda según contexto musical
  - guardrails por ancho estéreo para evitar sobreapertura
- **NUEVO:** `Band Motion Fase 5` (control de usuario):
  - nuevo control de `perfil` (`auto`, `tight`, `balanced`, `airy`) en la UI de Auto-Master
  - nuevo control de `cantidad` (0-150%) para dosificar movimiento global
  - aplicado en flujo de audio único y lote
  - persistencia en presets de mastering (`master.auto.motion_*`)
- **NUEVO:** `Band Motion Fase 6` (presets rápidos):
  - selector directo `Off`, `Subtle`, `Musical`, `Creative`, `Custom`
  - sincroniza automáticamente perfil + cantidad
  - cambios inmediatos en Auto-Master para iterar por escucha
- **NUEVO:** `AudioCharacteristics` incorpora `tempo_info` (`bpm`, `confidence`, `pulse_clarity`, `source`).
- **MEJORADO:** En lotes, el tempo se unifica por mediana para decisiones más estables entre temas.

### 🧩 Auto-Master Adaptativo (Fase 7 + Fase 8)
- **NUEVO:** Pipeline de artefactos adaptativos por tema:
  - `*.mts.json|md` (análisis temporal por tramo)
  - `*.master_decisions.json|md` (plan por sección)
  - `*.adaptive_shadow.json|md` (riesgo y `apply_ready`)
  - `*.adaptive_guard.json|md` (validación y recomendación de modo)
- **NUEVO:** Feature flags de rollout:
  - `TONEFINISH_ADAPTIVE_MASTER_ENABLED` (default OFF)
  - `TONEFINISH_ADAPTIVE_SHADOW_ENABLED` (default ON)
  - `TONEFINISH_ADAPTIVE_GUARD_STRICT` (default ON)
  - `TONEFINISH_ADAPTIVE_ROLLOUT_PERCENT` (0-100, default 0)
- **NUEVO:** Fase 8 A/B para lotes con bucket canario estable por archivo y reporte:
  - `batch_rollout_YYYYMMDD_HHMMSS.json|md`
  - resumen de `canary`, `guard_ok`, `apply_ready`, `enable_apply`
- **NUEVO:** Inspector en Resultados para cargar `*.mts.json` y visualizar MTS + decisiones + shadow + guard.
- **MEJORADO:** El procesamiento principal de lote sigue secuencial (tema a tema), con MTS en cola controlada para evitar picos de carga.

### 📚 Documentación
- **NUEVO:** `docs/ADAPTIVE_MASTER_WORKFLOW.md` con especificación de flujo Fases 1-8.
- **MEJORADO:** `docs/README.md` actualizado con artefactos, flags, Inspector y criterio operativo actual.

## 1.7.8 (2026-05-20)

### 📦 Empaquetado Debian
- **ACTUALIZADO:** Versión de paquete a `1.7.8`.
- **GENERADO:** Nuevo paquete `releases/tonefinish_1.7.8.deb`.
- **ACTUALIZADO:** Enlace `releases/tonefinish_latest.deb` apuntando a `1.7.8`.

## 1.7.7 (2026-05-20)

### 🚦 Orquestación CLI y Prioridades
- **NUEVO:** `CliBatchWorker` en GUI para ejecutar lote como job remoto (`batch_start/status/cancel`) vía CLI.
- **NUEVO:** Runner dedicado de jobs: `scripts/spasm_batch_job_runner.py`.
- **NUEVO:** Prioridad de peticiones en CLI con cupos separados (`audio` vs `low-priority`) para proteger throughput de audio bajo alta concurrencia.
- **NUEVO:** Métricas de cola en `batch_status`: `queued_at`, `started_at`, `queue_wait_ms`, `status_age_ms`.

### 🔌 Backend CLI expandido
- **NUEVO:** Métodos CLI para utilidades de runtime: `get_runtime_resource_info`, `ensure_ffmpeg_available`, `get_processing_limits`, `get_audio_info`, `extract_loudnorm_stats`, `cancel_running_ffmpeg_processes`.
- **NUEVO:** Integración en `logic_backend` para enrutar esas utilidades por CLI en modo SpASM (con fallback local seguro).
- **NUEVO:** Método CLI `fix_audio_tools` + refactor de `fix_audio_tools.py` a utilidad reusable (`apply_fixes` + `--dry-run`).

### 🖥️ Monitor de recursos
- **MEJORADO:** Detección de GPU física también por `drm` (`/dev/dri`) y `lspci` cuando no hay `nvidia-smi`.
- **MEJORADO:** `ui/workers.py` obtiene estado de recursos por backend CLI cuando `FINISHER_LOGIC_BACKEND=spasm`.

### 🧰 Estabilidad de procesamiento
- **CORREGIDO:** Preservación de códigos de salida negativos de FFmpeg (abortos por señal) en `audio_tools.py`.
- **MEJORADO:** Fallbacks adicionales ante `Assertion ... ffmpeg_filter.c` en normalización para evitar caída total del lote.

### 📦 Empaquetado Debian
- **ACTUALIZADO:** Versión de paquete a `1.7.7`.
- **GENERADO:** Nuevo paquete `releases/tonefinish_1.7.7.deb`.
- **ACTUALIZADO:** Enlace `releases/tonefinish_latest.deb` apuntando a `1.7.7`.

## 1.7.6 (2026-05-20)

### 🔌 Backend CLI SpASM (GUI en Python)
- **NUEVO:** Capa `logic_backend.py` para desacoplar GUI y lógica de procesos.
- **NUEVO:** Integración por contrato `call --json` para backend externo.
- **NUEVO:** CLI operativo `scripts/finisher_spasm_cli` + núcleo `spasm_cli/finisher_cli_core.spasm`.
- **NUEVO:** Soporte de fallback controlado a Python por método cuando corresponde.
- **MEJORADO:** Preservación de barras de progreso en GUI para flujos con callbacks.

### 🧪 Validación y Operación
- **NUEVO:** Smoke de CLI (`scripts/spasm_cli_smoke.sh`).
- **NUEVO:** Benchmark rápido por método (`scripts/spasm_cli_benchmark.py`).
- **NUEVO:** Gate operativo de fase 7 con reporte JSON (`scripts/spasm_phase7_gate.py`).
- **NUEVO:** Workflow CI con doble job (`adapter` y `strict`) para validar gate en push/PR.

### 📦 Empaquetado Debian
- **ACTUALIZADO:** `packaging/build_deb.sh` incluye `logic_backend.py`, `scripts/` y `spasm_cli/`.
- **ACTUALIZADO:** Versión de paquete a `1.7.6`.
- **GENERADO:** Nuevo paquete `releases/tonefinish_1.7.6.deb`.
- **ACTUALIZADO:** Enlace `releases/tonefinish_latest.deb` apuntando a `1.7.6`.

## 1.7.5 (2026-05-18)

### 📦 Empaquetado Debian
- **ACTUALIZADO:** Versión de paquete a `1.7.5`.
- **GENERADO:** Nuevo paquete `releases/tonefinish_1.7.5.deb`.
- **ACTUALIZADO:** Enlace `releases/tonefinish_latest.deb` apuntando a `1.7.5`.

## 1.7.4 (2026-04-20)

### 🛠️ Rescate de Material con Dureza en Medios
- **DOCUMENTADO:** Flujo práctico para evaluar material que suena "roto" en banda media/media-aguda sin clipping digital evidente.
- **DOCUMENTADO:** Criterio operativo para diferenciar clipping duro vs. harshness espectral usando `astats`, MTS y eventos `harshness_risk`.
- **DOCUMENTADO:** Referencia de cadena de reparación conservadora (`adeclip` + EQ dinámica + de-esser + limitador suave) y ajuste final por RMS objetivo.

### 📦 Empaquetado Debian
- **ACTUALIZADO:** Versión de paquete a `1.7.4` para distribuir la documentación operativa de rescate.

## 1.7.3 (2026-04-19)

### 🛠️ Estabilización de Guard y MTS
- **CORREGIDO:** `adaptive_guard` deja de usar solo conteo absoluto de `peak_risk` y pasa a validar por tasa/minuto ponderada por severidad.
- **CORREGIDO:** Se evitan falsos bloqueos por eventos aislados de `peak_risk` en material dinámico.
- **CORREGIDO:** El MTS usado por guard en flujo de proceso/lote ahora se calcula sobre el audio de salida (post-proceso), no sobre el input.
- **MEJORADO:** Detección de `peak_risk` en eventos frame-level con filtro de contexto (`RMS/crest`) para reducir falsos positivos.

### 🧪 Lote Secuencial Estricto
- **MEJORADO:** En lote, cada tema termina su ciclo completo (análisis, render, validación, MTS/guard/shadow) antes de pasar al siguiente.
- **MEJORADO:** Mensajería de progreso actualizada para reflejar modo secuencial estricto.

### 📦 Empaquetado Debian
- **CORREGIDO:** `build_deb.sh` incluye los nuevos módulos del flujo adaptativo (`analysis_mts`, `event_detection`, `section_detection`, `master_decision_engine`, `adaptive_*`).

## 1.7.1 (2026-03-31)

### 🧪 Lote por tema
- **MEJORADO:** `Auto-Master (Lote)` deja de hacer un preanálisis global de todos los archivos y pasa a analizar cada tema de forma secuencial.
- **MEJORADO:** Cada archivo del lote usa un ciclo independiente de deep analysis, procesamiento y validación final.
- **MEJORADO:** La validación final del lote queda liviana y prioriza métricas de loudness / true peak en lugar de reescanear bandas y voz en todos los temas.
- **CORREGIDO:** Se reduce la carga innecesaria de CPU, disco y FFmpeg durante el análisis del lote.

## 1.7.0 (2026-03-31)

### 🧠 Auto-Master Más Autónomo
- **MEJORADO:** El perfil `Conservador / Normal / Agresivo` ahora decide la cadena final de procesos a partir del análisis previo.
- **CORREGIDO:** La lógica de perfil deja de competir con los presets de estilo y pasa a actuar como decisión final.
- **MEJORADO:** Auto-Master conserva las métricas necesarias para decidir si conviene saltear procesos pesados cuando el material ya viene comprimido.

## 1.6.8 (2026-03-30)

### 📊 Progreso Temprano
- **MEJORADO:** `ProcessWorker` emite un estado inicial inmediato para que la barra de progreso no quede silenciosa durante las primeras lecturas pesadas.
- **MEJORADO:** El arranque de Auto-Master ahora muestra actividad desde el inicio del thread.

## 1.6.7 (2026-03-30)

### 🧯 Auto-Master Sin Reentrada
- **CORREGIDO:** `_apply_auto_master()` ya no se ejecuta dos veces al sincronizar los combos de estilo.
- **MEJORADO:** El resumen de Auto-Master deja de duplicarse y el flujo vuelve a continuar hasta el worker.

## 1.6.6 (2026-03-30)

### 🎯 Auto-Master Basado en Logs Reales
- **MEJORADO:** La calibración final usa el último JSON real de `loudnorm` emitido por FFmpeg durante el render.
- **MEJORADO:** `extract_loudnorm_stats()` toma el bloque más reciente del log para evitar mediciones previas desalineadas.
- **CORREGIDO:** Se reduce el riesgo de que Auto-Master empuje la salida a `-13 LUFS` cuando el audio ya entra cerca de `-14 LUFS`.

## 1.6.5 (2026-03-30)

### 🎚️ Auto-Master Conservador
- **MEJORADO:** `SUNO Clean` y perfiles cercanos reducen el empuje inicial cuando el audio ya viene cerca del target.
- **MEJORADO:** AutoGain limita la ganancia máxima final (`dynaudnorm_maxgain`) en material cercano a `-14 LUFS` y con baja dinámica.
- **CORREGIDO:** El flujo de `Auto-Master (Audio)` vuelve a aceptar el control de ganancia máximo sin romper la masterización de un solo archivo.

## 1.6.2 (2026-03-30)

### 🧠 Governor de Recursos
- **NUEVO:** Monitoreo pasivo de CPU, RAM, RAM libre y procesos `ffmpeg`.
- **NUEVO:** Perfiles estándar de máquina con selector manual y modo `Auto`.
- **NUEVO:** Persistencia por instalación del perfil elegido.
- **MEJORADO:** Dosificación básica de FFmpeg según perfil activo.

### 📊 Telemetría y Estados
- **NUEVO:** Tarjeta visible de estado en el panel de Procesamiento.
- **NUEVO:** Color por etapa para distinguir análisis, render, validación y finalización.
- **NUEVO:** Historial corto de mensajes en la UI.
- **NUEVO:** Historial estructurado por lote con tiempos por archivo y por etapa.

### 🧪 Cola y Temporales
- **MEJORADO:** Procesamiento secuencial de lote para reducir saturación del sistema.
- **MEJORADO:** Uso de carpetas temporales por archivo y copia final al destino solo al completar.

### 🎚️ Limpieza de UI y Flujo
- **ELIMINADO:** `stereo_dynamic_per_band` de la interfaz y de presets visibles.
- **MEJORADO:** `sub_bass` con rango negativo/positivo.
- **MEJORADO:** Panel de mezcla más limpio y con menos opciones experimentales.

## 1.6.1 (2026-03-17)

### 🎚️ Calibración por Logs Reales
- **MEJORADO:** Corrección final de salida con realimentación basada en métricas post-proceso (`LUFS` y `True Peak`) en lugar de un único ajuste estático.
- **NUEVO:** Iteraciones conservadoras de ajuste de ganancia para reducir error acumulado y evitar sobrecorrecciones.
- **NUEVO:** La calibración final se aplica tanto en flujo individual como en procesamiento por lote.

### 📊 Análisis de Bandas Más Robusto
- **MEJORADO:** `analyze_eq_bands()` ahora usa `volumedetect` por banda para priorizar datos medidos de logs reales de ffmpeg.
- **CORREGIDO:** Se evita el caso de `after.bands = -80.00` por parseo no representativo de `astats`.

### 🛡️ Control Conservador de Metales (Hi-Hats/Shakers)
- **NUEVO:** Protector específico de metales en Auto-Master inteligente para banda alta (`High-Mid`/`Air`).
- **NUEVO:** Recorte adicional leve en 2k-16k cuando la zona alta llega caliente.
- **NUEVO:** Saturación mínima forzada en bandas altas para reducir harshness.
- **NUEVO:** Umbrales más estrictos de limitador multibanda en `High-Mid` y `Air` según picos medidos.
- **MEJORADO:** Integración vocal más contenida para evitar protagonismo excesivo sin perder claridad.

### ⚙️ Estabilidad de Recursos
- **NUEVO:** Cola global de ejecución para ffmpeg (límite de procesos concurrentes).
- **MEJORADO:** Control de `threads` por proceso para evitar saturación de CPU/RAM.
- **NUEVO:** Variables de entorno para ajuste fino: `TONEFINISH_MAX_FFMPEG_PROCS`, `TONEFINISH_FFMPEG_THREADS`.

### 📦 Empaquetado Debian
- **MEJORADO:** Script `build_deb.sh` incluye módulos requeridos por la versión actual:
  - `mastering_modules/`
  - `filter_graph_builder.py`
  - `mastering_config.py`

## 1.5.0 (2026-01-20)

### 🛡️ Control Avanzado de Saturación Post-Proceso

#### Nuevo Proceso: SaturationLimiterProcess
- **NUEVO:** Proceso de orden 75 (entre Glue y AutoGain)
- **NUEVO:** Compresión multibanda selectiva en 6 bandas de frecuencia
- **NUEVO:** Protección extra para High-Mid (2k-6k Hz) y Air (6k-16k Hz)
- **NUEVO:** Modos de operación: `musical` (suave/cálido) y `transparent` (preciso/limpio)
- **NUEVO:** Control de THD (Total Harmonic Distortion) objetivo: 1-10%
- **NUEVO:** Parámetros configurables: ratio, attack, release, knee
- **NUEVO:** Detección y compresión selectiva solo en bandas saturadas

#### AutoGain Mejorado
- **NUEVO:** Control adaptativo de volumen pre-dynaudnorm
- **NUEVO:** Compensación automática basada en THD detectado
- **NUEVO:** Fórmula: -0.5dB por cada 2% de exceso de THD
- **NUEVO:** Parámetros: `adaptive_saturation_control`, `saturation_compensation_db`
- **NUEVO:** Ajuste dinámico de `final_peak_db` según saturación detectada
- **MEJORADO:** Límites de seguridad: compensación entre -6dB y -0.5dB

#### Auto Master Intelligence Extendido
- **NUEVO:** Función `_calculate_saturation_budget()`: estima THD total
- **NUEVO:** Considera: saturación global, por banda, glue compression, desbalance, agudos
- **NUEVO:** Activación automática si THD > 3% (modo musical con compensación)
- **NUEVO:** Activación automática si THD 2-3% (modo transparent sutil)
- **NUEVO:** Función `update_saturation_budgets_for_batch()`: análisis individual
- **NUEVO:** Reporte detallado de fuentes contribuyendo al THD
- **NUEVO:** Niveles de riesgo: "low", "medium", "high"

#### Controles UI
- **NUEVO:** Checkbox: "Control de saturación final"
- **NUEVO:** SpinBox: "THD Objetivo" (1-10%, default 3.0%)
- **NUEVO:** ComboBox: Modo de reducción (musical/transparent)
- **NUEVO:** Checkbox: "Control adaptativo de volumen"
- **NUEVO:** Tooltips explicativos en todos los controles
- **NUEVO:** Integración en tab "Color → Saturación"

#### Batch Processing Mejorado
- **NUEVO:** Análisis de saturación individual por archivo
- **NUEVO:** Reporte de THD por archivo en formato tabla
- **NUEVO:** Ejemplo: "archivo.wav: THD 4.1% (medium)"
- **NUEVO:** Guardado de métricas THD en log JSONL
- **NUEVO:** Ajustes unificados con presupuestos individualizados
- **MEJORADO:** `analyze_batch_for_automaster()` retorna saturation_budget por archivo

#### Documentación
- **NUEVO:** docs/SATURATION_CONTROL_POST_PROCESS.md (guía completa)
- **NUEVO:** Explicación detallada de cada componente
- **NUEVO:** Flujos de procesamiento individual y batch
- **NUEVO:** Configuraciones recomendadas por género musical
- **NUEVO:** Métricas de rendimiento (+5-8% tiempo de procesamiento)
- **NUEVO:** Referencias técnicas de cálculos THD
- **NUEVO:** Tests sugeridos y casos de uso
- **NUEVO:** Debugging y diagnóstico de logs

#### Impacto en Rendimiento
- **OPTIMIZADO:** SaturationLimiter solo activo cuando se detecta riesgo
- **OPTIMIZADO:** Análisis de saturación en lotes limitado a 5 archivos
- **OPTIMIZADO:** Cálculo de presupuesto es matemático (instantáneo)
- **RESULTADO:** +5-8% tiempo total cuando activo, 0% cuando inactivo

### 🎯 Mejoras en Cadena de Procesamiento

#### Orden Final de Procesos
```
Headroom (-17dB) → Repair → Deesser → Tone EQ → Multiband
→ Saturation → Stereo Dynamic → Glue
→ 🆕 SaturationLimiter (75) → AutoGain (80) → Loudness (90)
```

### 📊 Ventajas del Sistema
- ✅ Prevención proactiva de saturación antes de que ocurra
- ✅ Control quirúrgico solo en bandas problemáticas
- ✅ Preservación de carácter musical vs transparencia
- ✅ Automatización inteligente basada en análisis
- ✅ Soporte completo para procesamiento por lotes
- ✅ Overhead mínimo en rendimiento

---

## 1.4.0 (2026-01-19)

### 🎯 Modos Auto-Master (Audio/Lote)
- **NUEVO:** Modo "Auto-Master (Audio)" - Flujo simplificado para archivo único
- **NUEVO:** Modo "Auto-Master (Lote)" - Flujo simplificado para procesamiento en lote
- **NUEVO:** Auto-aplicación de configuración al seleccionar modos Auto-Master
- **NUEVO:** Navegación automática al tab Auto-Master al cambiar de modo
- **NUEVO:** Ocultación automática del tab Procesamiento en modos Auto-Master
- **MEJORADO:** Combo de modos ahora incluye 6 opciones: Manual, Audio único, Lote, Auto-Master (Audio), Auto-Master (Lote), Solo analizar

### 🎧 Presets Electrónica - Discoteca
- **NUEVO:** 8 presets de música electrónica para Auto-Master:
  - 🎧 Techno (Oscuro, Industrial)
  - 🎧 House (Deep, Tech, Progressive)
  - 🎧 Trance (Uplifting, Psytrance)
  - 🎧 Big Room (Festival, Mainstage)
  - 🎧 Drum & Bass (Liquid, Neuro)
  - 🎧 Hardstyle (Hardcore, Gabber)
  - 🎧 Minimal (Micro, Dub Techno)
  - 🎧 Disco (Nu-Disco, Funky)
- **MEJORADO:** Cada preset con configuración específica de loudness, EQ, saturación y limitador

### 📊 Tab Resultados Rediseñado
- **NUEVO:** Vista unificada sin sub-tabs (antes 6 tabs → ahora 0)
- **NUEVO:** Espectro de frecuencias siempre visible y prominente
- **NUEVO:** Secciones colapsables: Lote, Log, Detalles
- **NUEVO:** Métricas Antes/Después + Input en panel compacto
- **NUEVO:** Sugerencias integradas bajo métricas
- **MEJORADO:** Mensaje placeholder centrado con span de celdas
- **MEJORADO:** Sección Lote se expande automáticamente en modo Lote

### 🎛️ Tab Auto-Master + Preview Unificado
- **NUEVO:** Tab dedicada "🎯 Auto-Master" con selector de estilo
- **NUEVO:** Combo de estilos sincronizado entre tabs
- **NUEVO:** Panel de notas de análisis integrado
- **NUEVO:** Controles de preview A/B (Original/Procesado)
- **NUEVO:** Forma de onda comparativa

### 🔗 Sincronización Cadena de Procesos
- **NUEVO:** Widget visual de cadena de procesos con estado (✓/✗)
- **NUEVO:** Actualización automática al cambiar checkboxes de procesos
- **NUEVO:** Indicadores visuales verde/gris para procesos activos/inactivos

### 🐛 Correcciones
- **FIX:** Error `_log` no definido → usar `log_view.appendPlainText()`
- **FIX:** Errores Pylance de type hints para `project_tabs` y `process_tabs`
- **FIX:** Widgets duplicados entre tabs (combo de estilos)

## 1.3.0 (2026-01-19)

### 🧠 Auto-Master Inteligente Completo
- **NUEVO:** Detección de clipping con `detect_clipping()` - usa astats/volumedetect
- **NUEVO:** Análisis de piso de ruido con `detect_noise_floor()` - categorízas: Excellent/Good/Moderate/High/VeryHigh
- **NUEVO:** Análisis de características estéreo con `detect_stereo_characteristics()` - mono/stereo, width, balance L/R
- **NUEVO:** Detección de picos por banda con `detect_peak_per_band()` - para limitador multibanda
- **NUEVO:** Análisis de silencios con `analyze_silence_edges()` - sugiere fades óptimos
- **NUEVO:** Función `get_comprehensive_audio_analysis()` - combina todos los análisis
- **MEJORADO:** `AudioCharacteristics` extendida con 10+ nuevas propiedades
- **MEJORADO:** `analyze_audio_for_automaster()` con parámetro `full_analysis=True`
- **MEJORADO:** `adapt_preset_to_audio()` ahora auto-configura:
  - `repair_settings`: declip, noise_reduction, declick
  - `multiband_limiter_enabled` + umbrales por banda
  - `stereo_dynamic_enabled` + mix
  - `suggested_fade_in` / `suggested_fade_out`

### 📦 Auto-Master para Lotes (Batch)
- **NUEVO:** `analyze_batch_for_automaster()` - Analiza múltiples archivos
- **NUEVO:** `_merge_batch_characteristics()` - Combina análisis de forma conservadora
- **NUEVO:** Botón "🧠 Auto-configurar Lote" en UI
- **NUEVO:** Estadísticas de lote: clipping, ruido, stereo, vocales
- **NUEVO:** Callback de progreso durante análisis
- **NUEVO:** Estrategia conservadora: si cualquier archivo tiene problema, se asume para todos

### 🎨 UI Dinámica por Modo de Trabajo
- **NUEVO:** `_configure_project_for_mode()` - Configura subtabs de proyecto
- **NUEVO:** `_configure_processing_for_mode()` - Configura tabs de procesamiento
- **NUEVO:** `_configure_sidebar_for_mode()` - Configura panel lateral
- **MEJORADO:** `_show_tabs_for_mode()` reescrito con lógica por modo
- **Manual**: Todo visible
- **Audio único**: Sin lote, con firma y salida
- **Lote**: Sin audio único, con firma y salida
- **Solo analizar**: Sin procesamiento, solo resultados

### 🎚️ Limitador Multibanda Brickwall
- **NUEVO:** Control de umbral independiente por banda
- **NUEVO:** Checkbox "Limitador Multibanda" en UI
- **NUEVO:** Integración con Auto-Master para configuración automática
- **NUEVO:** Constante `MULTIBAND_LIMITER_DEFAULTS` en config.py

## 1.1.1 (2026-01-17)

### 🔄 Rangos de ganancia simétricos
- Drive de saturación (global y por banda) permite valores negativos para atenuar cuando el análisis lo requiera.
- Makeup del compresor glue admite reducción (valores negativos) para compensar procesos automáticos.

## 1.1.0 (2026-01-14)

### � **NUEVO: Sistema de Preview y Análisis de Espectro**
- **NUEVO:** 🎵 **Sistema de Preview Antes/Después** - Escucha el resultado antes de procesar
- **NUEVO:** 📊 **Análisis de Espectro FFT** - Visualización y análisis detallado de frecuencias
- **NUEVO:** 🎯 **Recomendación Automática de Preset** basada en espectro
- **NUEVO:** Detección de características espectrales:
  - Centro espectral (warm vs bright)
  - Picos de frecuencia prominentes
  - Flatness espectral (ruido vs tonos)
  - Rolloff de frecuencias
- **NUEVO:** Módulo `spectrum_analyzer.py` con análisis FFT avanzado
- **NUEVO:** Módulo `audio_preview.py` para generación y reproducción de previews
- **AÑADIDO:** Dependencias: `numpy`, `matplotlib`

### �🎯 **REDISEÑO DE PRESETS** - Enfoque Orientado a Géneros
- **NUEVO:** Nombres descriptivos basados en características sonoras (inspirado en BandLab)
- **Universal** (Rock, Pop, Electrónica) - Balance tonal dinámico y natural
- **Fuego** (Trap, Reguetón, Hip-Hop) - Bajos impactantes y claridad de rango medio
- **Claridad** (Clásica, R&B, Cantautor) - Agudos prístinos con ligera expansión dinámica
- **Cinta** (Jazz, Alternativa, Indie) - Saturación cálida con dinámica analógica
- **Natural** (Acústico, Jazz, Folk) - Dinámicas equilibradas con compresión suave
- **Espacial** (Ambient, Experimental) - Reverberación atmosférica y amplitud de stereo mejorada
- **Cinemático** (Orquestal, Soundtrack) - Saturación intensa y distorsión armónica
- **Empuje** (EDM, Dubstep, Bass Music) - Bajo enérgico combinado con agudos potenciados

### 🧠 Auto-Master Inteligente
- **NUEVO:** Sistema de análisis automático de audio para adaptar presets
- **NUEVO:** Detección de vocales, bajos, agudos, dinámica y balance espectral
- **NUEVO:** Adaptación automática de de-esser según contenido vocal y sibilancia
- **NUEVO:** Ajuste inteligente de saturación según balance y características
- **NUEVO:** Compresión glue adaptativa según rango dinámico del audio
- **NUEVO:** Protección automática de bandas sensibles según análisis
- **NUEVO:** ⭐ **Detección de incompatibilidades preset-contenido** con advertencias críticas
- **NUEVO:** ⭐ **Sugerencias automáticas de presets alternativos** (3 recomendaciones)
- **NUEVO:** ⭐ **Cálculo automático de ajustes de EQ correctivos** con valores específicos en dB
- **NUEVO:** ⭐ **Función `_generate_eq_suggestions()`** para corrección de desbalances severos
- **NUEVO:** 🎚️ **Configuración automática de fades** (fade-in y fade-out) en todos los presets
- **NUEVO:** Panel de resumen con análisis detallado y decisiones aplicadas
- **AÑADIDO:** Checkbox "Análisis Inteligente" en tab Auto-Master
- **AÑADIDO:** Módulo `auto_master_intelligence.py` con lógica de adaptación
- **AÑADIDO:** Clase `AudioCharacteristics` para encapsular análisis
- **AÑADIDO:** Funciones `analyze_audio_for_automaster()` y `adapt_preset_to_audio()`
- **AÑADIDO:** Secciones nuevas en UI: ADVERTENCIAS, PRESETS ALTERNATIVOS, SUGERENCIAS DE EQ
- **AÑADIDO:** Documentación completa en `docs/AUTO_MASTER_INTELLIGENCE.md`
- **AÑADIDO:** Script de demo `test_auto_master_intelligence.py` con caso de incompatibilidad

### 🎯 Control Avanzado de Saturación en Bandas Sensibles
- **NUEVO:** Limitadores soft-knee por banda para prevenir clipping en vocales y metales
- **NUEVO:** Control de drive máximo específico por banda (High-Mid: 12dB, Air: 8dB)
- **NUEVO:** Headroom automático de seguridad (High-Mid: -2dB, Air: -3dB)
- **NUEVO:** Función `validate_saturation_settings()` con advertencias inteligentes
- **MEJORADO:** `analyze_eq_bands()` detecta picos cercanos a 0dB en bandas críticas
- **MEJORADO:** `build_multiband_filter()` con parámetro `enable_band_limiter`
- **AÑADIDO:** Constantes `BAND_HEADROOM_DB` y `MAX_SATURATION_DRIVE_DB` en config.py
- **AÑADIDO:** Documentación completa en `docs/SATURATION_CONTROL.md`
- **AÑADIDO:** Script de prueba `test_saturation_control.py` con ejemplos

### 🔧 Mejoras Técnicas
- Limitador insertado después de EQ dinámico, stereo width y saturación
- Attack rápido (0.5ms) y release musical (50ms) para limitadores de banda
- Protección contra saturación acumulativa en suma de procesos
- Sistema de validación con 3 niveles de advertencia (⚠️ , ℹ️, 🚨)
- Multiplicadores inteligentes aplicados a todos los presets
- Análisis de bandas integrado en flujo de Auto-Master
- Fades optimizados por estilo:
  - **Cinta**: 0.10s / 2.0s (suave y natural)
  - **Natural**: 0.05s / 1.5s (transparente)
  - **Cinematografico**: 0.20s / 3.0s (espacial)
  - **Energetico**: 0.05s / 1.0s (impacto rápido)
  - **Vintage**: 0.15s / 2.5s (clásico)
  - **Loud**: 0.02s / 0.5s (máximo loudness)
  - **Hi-Fi**: 0.08s / 2.0s (detallado)
  - **Club**: 0.05s / 1.0s (punch)

### 📚 Documentación
- Guía completa de uso y configuración recomendada
- Ejemplos para vocales, hi-hats y casos extremos
- Comparativa antes/después con tabla de mejoras
- Casos de uso detallados para cada preset
- Referencias técnicas de funciones y clases

### ⚙️ Cambios Internos
- Importaciones actualizadas en `audio_processing.py` y `audio_analysis.py`
- Bandas sensibles identificadas: índices 4 (High-Mid) y 5 (Air)
- Integración de análisis en `_apply_auto_master()` de ui_app.py
- Retrocompatibilidad total con versiones anteriores

## 1.0.5
- De-esser auto con presupuesto de intervención para evitar saturar agudos.
- Glue compression automatica mas suave (ratio por defecto 1.4).

## 1.0.4
- Nueva pestaña Ondas con forma de onda interactiva y fades por archivo.
- Fades por archivo en lote: override por tema, global por defecto.
- UI modularizada: ui/qt_compat.py, ui/workers.py, ui/tabs.py.
- Dependencia opcional: pyqtgraph (waveform interactiva).
- Auto noise reduction mas conservador (menos agresivo).

## 1.0.3
- Noise/Repair: noise reduction, de-clip, de-click/pop con Auto/Leve/Medio/Alto.
- Auto completo para repair basado en analisis.
- Mejoras de UI: ocultar sub-tabs segun modo y iconos en tabs/botones.

## 1.0.2
- Firma digital con metadata en WAV y presets guardados.
- Tab Firma Digital + validacion obligatoria.
- Glue compression controlable en Procesos.
- Resultados reorganizados en sub-tabs con iconos.
- Progreso global y logs detallados en lote.

## 1.0.1
- Fix: version displayed dynamically in About.
- Firma digital en TOML y presets de firma.
- Glue compression y ajustes de procesos.
- Tabs de resultados reorganizados y progreso global.

## 1.0.0
- GUI completa con modo audio unico y lote.
- Presets de loudness y de salida.
- Analisis y normalizacion en dos pasadas.
- Control dinamico por bandas con stereo width.
- De-esser, limiter brickwall y fades.
- Reportes TOML por archivo y tabla de resultados en lote.
- Paquete .deb con instalacion de dependencias en venv.
- Tab Presets unificado y nuevo tab Firma Digital con campos obligatorios.
- Firma digital inyectada en WAV y guardada en TOML.
- Presets de firma guardados en ~/.tonefinish.
- Glue compression con controles avanzados.
- Barra de progreso global y resultados en sub-tabs.
