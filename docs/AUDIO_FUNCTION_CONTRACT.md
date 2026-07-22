# Contrato de funciones de audio

Este contrato es la fuente canónica de capacidades seleccionables por la IA.
Los nombres de clases, textos de UI y filtros FFmpeg pueden cambiar; los IDs no.

## Identidad

- Plugin: `audio.<plugin>`, por ejemplo `audio.multiband`.
- Función: `audio.<plugin>.<función>`, por ejemplo `audio.multiband.compressor`.
- Banda: `sub_bass`, `bass`, `low_mid`, `mid`, `high_mid` o `air`.

Nunca se deben persistir nombres traducidos de bandas como identidad. Un ID publicado
no se reutiliza para otra función. Los reemplazos se resuelven mediante alias.

## Acción decidida por IA

```json
{
  "function_id": "audio.multiband.compressor",
  "enabled": true,
  "operation": "attenuate",
  "target": "high_mid",
  "params": {
    "threshold_db": -20.0,
    "ratio": 1.5,
    "attack_ms": 3.0,
    "release_ms": 50.0
  },
  "evidence": {
    "band_rms_db": -13.8,
    "crest_factor_db": 6.9
  },
  "reason": "Transientes agresivos entre 2 y 6 kHz",
  "confidence": 0.87
}
```

Antes de compilar un filtro se validan el ID, target, parámetros, rangos,
conflictos y métricas requeridas. Un campo o ID desconocido produce error explícito.

### Intención bidireccional

Toda decisión nueva de IA declara una operación: `cut`, `boost`, `attenuate`,
`expand`, `narrow`, `protect` o `neutral`. El contrato valida que la intención y el
parámetro sean coherentes: `cut` exige ganancia negativa, `boost` positiva,
`narrow` exige `width < 1` y `expand`, `width > 1`.

`evidence` es obligatoria para decisiones de IA y contiene mediciones escalares que
justifican la intervención. Una decisión `neutral` se conserva en
`decision_trace.neutral_decisions`, pero no entra al grafo DSP. Las acciones internas
anteriores al contrato siguen siendo compatibles: su operación se infiere sin cambiar
ni convertir el signo de sus parámetros.

### Presupuestos de la cadena

La Fase 2 evalúa cada acción de manera secuencial mediante tres gobernadores
trazables (no son efectos DSP seleccionables):

- `audio.governor.tonal_budget`: limita cortes y boosts individuales/acumulados.
- `audio.governor.gain_budget`: limita ganancia de salida y makeup acumulados.
- `audio.governor.spectral_overlap`: impide apilar correcciones sobre una banda.

Límites conservadores iniciales: boost tonal individual `+2 dB`, corte individual
`-3 dB`, boost acumulado `+3 dB` y corte acumulado `-6 dB`. Ganancia y makeup usan
los mismos máximos. Un cut requiere `evidence.measured_excess_db`; un boost requiere
`evidence.measured_deficit_db`; toda compensación positiva de ganancia requiere
`evidence.compensation_required_db`.

El gobernador nunca recorta silenciosamente ni invierte valores: acepta la acción
exacta o la rechaza. `decision_trace.budget_report` registra política, contribuciones,
totales, presupuesto restante, acumulación por banda y violaciones.

### EQ dinámica dirigida por evidencia

La Fase 3 incorpora dos funciones DSP seleccionables por ID:

- `audio.dynamic_eq.resonance`: atenúa una resonancia persistente medida.
- `audio.dynamic_eq.motion`: corta o realza suavemente una banda según el signo de
  `gain_db`, para evitar una corrección tonal rígida durante todo el tema.

DeepSeek recibe candidatos extraídos del archivo con frecuencia, exceso espectral y
relación Mid/Side. Una resonancia sólo se acepta si coincide con un candidato local y
su frecuencia cae dentro de la banda declarada. Los scopes `mid` y `side` exigen una
medición Mid/Side coherente; no se permite inferirlos sin evidencia.

Ambas funciones usan `adynamicequalizer` real de FFmpeg. Para movimientos menores a
1 dB se mezcla una rama procesada con la señal seca, ya que el filtro nativo no admite
un `range` inferior a 1 dB. Los movimientos firmados participan de los gobernadores
de presupuesto y solapamiento de la Fase 2.

### Procesamiento vocal sin stems

La Fase 4 estima presencia vocal sobre el centro del master estéreo y expone:

- `audio.vocal.resonance_suppressor`: reducción dinámica Mid entre 1,8 y 8 kHz,
  limitada a `-2,5 dB` y vinculada a una resonancia local confirmada.
- `audio.vocal.center_naturalizer`: mezcla paralela Mid para recuperar cuerpo entre
  180–450 Hz y reducir dureza o aire artificial de forma conservadora.

Ambas funciones requieren `vocal_center_confidence >= 0.65`, predominio Mid medido y
evidencia coincidente con el análisis local. El naturalizador exige déficit de cuerpo
para añadir y excesos separados para cortar dureza o aire. La rama Side no se procesa;
no se aplica vibrato, chorus ni separación de stems.

### Plugins complementarios

La Fase 5 añade cinco funciones con autorización basada en métricas locales:

- `audio.transient.dynamic_control`: intensidad firmada para suavizar o recuperar ataques.
- `audio.stereo.correlation_guard`: estrecha ante correlación negativa; sólo expande con correlación `>= 0.70`.
- `audio.low_end.dynamic_balance`: corte o refuerzo dinámico de graves con nivel y relación Mid/Side medidos.
- `audio.spectral.deharsh`: reducción dinámica amplia de dureza confirmada.
- `audio.spectral.dullness_recovery`: recuperación dinámica de claridad, limitada a `+1.5 dB`.

El analizador local entrega crest factor de transientes, correlación, balance de graves,
dureza y déficit de aire. La evidencia declarada debe coincidir con esas mediciones.
Los movimientos tonales entran en los presupuestos acumulados existentes.

### Automatización efectiva por secciones

La Fase 6 convierte las decisiones MTS en audio real. Cada corrección temporal se
registra con `function_id=audio.dynamic_eq.motion`, operación firmada, sección,
inicio/fin, valor solicitado/aplicado y smoothing. Los movimientos se limitan a
`±0.8 dB` y las transiciones a 150–500 ms.

El render es transaccional: se construye en un temporal mediante una rama diferencial
seca/procesada, se recalibra a LUFS/True Peak y se mide antes de publicar. Sólo se
reemplaza el master estático cuando shadow y `adaptive_guard` aprueban; cualquier
error, overshoot o desvío conserva el archivo estático. `adaptive_render.json` indica
`applied`, `fallback_static` o `not_applied` y enumera exactamente las automatizaciones
que llegaron al audio. El mismo resumen se añade a `.ai_master.json`.

### Certificación y comparación A/B

La Fase 7 añade `processes/quality.py` y el comando
`scripts/certify_audio_catalog.py`. La certificación enumera los 36 IDs, comprueba
que su plugin está registrado y que `build_function()` tiene implementación real,
y queda vinculada a la huella SHA-256 del catálogo.

`compare_audio_ab()` decodifica bypass y procesado bajo el mismo formato y mide
duración, RMS diferencial, cambio de nivel, correlación de forma de onda, pico y
muestras clippeadas. Las pruebas cubren ejecución FFmpeg de todos los IDs, valores
firmados y neutros, rangos inválidos, recombinación Mid/Side, fase, headroom y fallback.
La tolerancia final de loudness de `build_execution_audit()` es `0.30 LU`; cada acción
ejecutada conserva parámetros y una huella propia para demostrar decisión–ejecución.

Los análisis de banda guardados en caché llevan versión de esquema. Un caché legacy,
incompleto o con las seis bandas en piso se invalida y se vuelve a medir. El grafo
combinado conserva una salida FFmpeg explícita y asocia cada `volumedetect` por ID de
filtro, porque FFmpeg puede imprimir las ramas en orden inverso.

La evidencia anidada de un proveedor se aplana a escalares, pero LUFS y True Peak de
entrada siempre se sustituyen por mediciones locales con `measurement_source=local_ffmpeg`.
Shadow y guardia deben coincidir en `apply_candidate`; ninguno puede autorizar el
render por separado.

El análisis de lote usa `SingleFileAnalysis` con campos nombrados para impedir que
`raw_stats`, bandas y voz cambien de posición accidentalmente. La publicación del
candidato copia primero a un temporal hermano del destino y luego usa reemplazo
atómico, por lo que funciona aunque `/tmp` y la carpeta de salida estén en discos o
filesystems diferentes.

## Componentes

- `processes/contracts.py`: tipos, validación, contexto y fábrica de labels.
- `processes/catalog.py`: catálogo canónico y alias heredados.
- `BaseProcess.plugin_id`: identidad estable de cada plugin.
- `BaseProcess.function_specs()`: capacidades expuestas por el plugin.
- `BaseProcess.build_function()`: punto de compilación que implementará cada DSP.

La Fase 2 implementó `build_function()` en los nueve plugins registrados. Cada una
de las funciones se ejecuta en una prueba real de FFmpeg y debe conservar sample
rate y cantidad de canales. El método base mantiene `NotImplementedError` para que
un plugin futuro no pueda declarar funciones y omitir su implementación silenciosamente.

## Orquestación

Desde la Fase 3, `AudioProcessOrchestrator` es la única ruta que compila filtros DSP.
`audio_processing.py` conserva sus argumentos históricos, pero los convierte a
`AudioFunctionAction` con `migrate_legacy_preprocess_config()` y no contiene
implementaciones alternativas de EQ, dinámica, reparación, saturación o mastering.

El formato persistido por el antiguo `ProcessRegistry.to_dict()` se convierte con
`migrate_legacy_registry_state()`. Los valores traducidos de bandas se transforman
a IDs estables antes de compilar el grafo.

El catálogo actual contiene 36 funciones. Esto incluye ganancia de salida, recorte
de silencio y hard clipper, que anteriormente estaban implementados directamente
en `audio_processing.py`.

## Decisión IA y auditoría de salida

Desde la Fase 4, la IA recibe el catálogo vivo y responde acciones estructuradas con
`audio_id`, `function_id`, operación, evidencia, parámetros, motivo y confianza. Las acciones desconocidas,
conflictivas o inseguras se rechazan antes del render y quedan en `decision_trace`.

La Fase 5 cierra el circuito después del render. Cada `.ai_master.json` conserva la
huella SHA-256 del catálogo, el orden realmente ejecutado, métricas antes/después y
checks de cumplimiento de LUFS y True Peak. `status=warning` significa que el archivo
se produjo, pero una medición quedó fuera de tolerancia y requiere revisión; nunca se
presenta como éxito silencioso.

La Fase 6 endurece la correspondencia entre decisión y ejecución. Las acciones con
`enabled=false` se rechazan explícitamente, porque omitirlas en silencio falsearía la
traza. El plan efectivo se normaliza según las etapas físicas del pipeline: primero
preproceso, después loudness y por último el limitador True Peak. Tanto
`effective_order` como `executed_actions` reflejan ese orden real; los guardrails de
salida no pueden quedar anulados por el orden propuesto por un proveedor de IA.

La Fase 7 vincula la estrategia al contenido del audio mediante SHA-256. La huella se
calcula al pedir la decisión y se verifica otra vez justo antes de construir el grafo.
Si el archivo fue reemplazado o modificado —aunque conserve el mismo path— la ejecución
se detiene y exige un análisis nuevo. `source_fingerprint` queda guardado junto con
`audio_id`, la huella del catálogo y la auditoría final.

## Fallback sin IA

`SUNO Clásico` también se expresa como acciones canónicas. Si un proveedor agota
tokens, no responde o entrega JSON inválido, el sistema registra el motivo exacto y
genera un plan con los mismos `function_id`, guardrails, orden, huellas y auditoría que
una estrategia remota. No existe una ruta de procesamiento local opaca o manual.
