# SpASM Migration Matrix (Finisher)

Fecha: 2026-05-20

Objetivo: migrar la lógica usada por el GUI Python hacia CLI SpASM, manteniendo compatibilidad por etapas.

## Estado global
- GUI: Python (estable, no migrar)
- Capa de integración: `logic_backend.py` (activa)
- CLI actual:
  - `scripts/finisher_spasm_cli` (protocolo `call --json`)
  - `spasm_cli/finisher_cli_core.spasm` (núcleo SpASM)
- Fallback actual: `FINISHER_SPASM_FALLBACK_PYTHON=1` (recomendado durante migración)

## Métodos en uso real (extraído de `ui/workers.py`)

| Método | Uso principal | Frecuencia en workers | Riesgo | Estado CLI SpASM | Prioridad |
|---|---|---:|---|---|---:|
| `ensure_output_path` | resolver extensión/salida | media | bajo | `spasm` | P0 |
| `resolve_repair_levels` | decisiones de reparación | alta | bajo | implementado (CLI) | P1 |
| `evaluate_mix` | rating pre/post | alta | bajo | implementado (CLI) | P1 |
| `format_analysis_summary` | texto resumen | alta | bajo | implementado (CLI) | P1 |
| `write_analysis_toml` | reporte análisis | media | medio | implementado (CLI) | P1 |
| `analyze_audio` | métrica loudness base | muy alta | alto | implementado (CLI) | P2 |
| `analyze_eq_bands` | bandas y sugerencias | alta | alto | implementado (CLI) | P2 |
| `analyze_voice_band` | vocal RMS | alta | alto | implementado (CLI) | P2 |
| `analyze_audio_with_filter` | análisis con pre-chain | media | alto | implementado (CLI) | P2 |
| `build_preprocess_chain` | construir filtros | alta | alto | implementado (CLI) | P2 |
| `apply_output_gain` | calibración iterativa | media | alto | implementado (CLI) | P3 |
| `normalize_audio` | render/master final | muy alta | crítico | implementado (CLI) | P3 |
| `analyze_audio_for_automaster` | Auto-Master single | media | alto | implementado (CLI) | P4 |
| `adapt_preset_to_audio` | preset dinámico | media | medio | implementado (CLI) | P4 |
| `analyze_batch_for_automaster` | Auto-Master batch | media | alto | implementado (CLI) | P4 |
| `update_saturation_budgets_for_batch` | ajuste saturación lote | media | medio | implementado (CLI) | P4 |

## Plan por fases

### Fase 0: Contrato + observabilidad (1-2 días)
- Congelar contrato JSON de `call --json`.
- Agregar `protocol_version` y `request_id` en request/response.
- Log estructurado por método (duración, exit, backend real: `spasm|python_fallback`).
- Criterio de salida:
  - CLI responde formato estable para todos los métodos (aunque sea `not_implemented`).

### Fase 1: Métodos seguros de bajo riesgo (2-3 días)
- Implementar en SpASM:
  - `resolve_repair_levels`
  - `evaluate_mix`
  - `format_analysis_summary`
  - `write_analysis_toml`
- Apagar fallback por método al validar paridad.
- Criterio de salida:
  - tests unitarios + snapshots de texto/TOML pasando.

### Fase 2: Núcleo de análisis (4-7 días)
- Implementar en SpASM wrapper/orquestación de:
  - `analyze_audio`
  - `analyze_eq_bands`
  - `analyze_voice_band`
  - `analyze_audio_with_filter`
  - `build_preprocess_chain`
- En esta fase, si SpASM no puede hacer parseo complejo internamente, usar estrategia híbrida SpASM->subproceso controlado con contrato explícito.
- Criterio de salida:
  - paridad en métricas: LUFS/TP/LRA/RMS con tolerancias definidas.

### Fase 3: Procesamiento de salida (5-8 días)
- Implementar:
  - `normalize_audio`
  - `apply_output_gain`
- Enfoque: primero equivalencia funcional, luego tuning de performance.
- Criterio de salida:
  - regresión de audio aceptable en fixtures + batch estable.

### Fase 4: Auto-Master (4-6 días)
- Implementar:
  - `analyze_audio_for_automaster`
  - `adapt_preset_to_audio`
  - `analyze_batch_for_automaster`
  - `update_saturation_budgets_for_batch`
- Criterio de salida:
  - recomendaciones y perfiles comparables con baseline Python.

### Fase 5: Cierre (2-3 días)
- Poner `FINISHER_SPASM_FALLBACK_PYTHON=0` en pruebas de release.
- Remover rutas Python ya reemplazadas (solo cuando esté validado).
- Actualizar documentación operativa.
- Criterio de salida:
  - flujo GUI completo operando vía CLI SpASM sin fallback.

## Orden recomendado de implementación (concreto)
1. `resolve_repair_levels`
2. `evaluate_mix`
3. `format_analysis_summary`
4. `write_analysis_toml`
5. `analyze_audio`
6. `analyze_eq_bands`
7. `analyze_voice_band`
8. `build_preprocess_chain`
9. `analyze_audio_with_filter`
10. `normalize_audio`
11. `apply_output_gain`
12. Auto-Master batch/single

## Riesgos y mitigaciones
- Riesgo: diferencias numéricas FFmpeg/parseo
  - Mitigación: tolerancias por métrica + fixtures fijos.
- Riesgo: CLI inestable por parsing JSON
  - Mitigación: validación temprana + errores determinísticos.
- Riesgo: latencia por múltiples procesos
  - Mitigación: pooling/caching y consolidación de llamadas.
- Riesgo: bloqueo de GUI por llamada larga
  - Mitigación: mantener workers asíncronos y timeouts por método.

## Checklist operativo por método
- [ ] contrato request/response definido
- [ ] implementación SpASM
- [ ] tests unitarios método
- [ ] tests integración desde `logic_backend.py`
- [ ] paridad contra baseline Python
- [ ] fallback desactivado para ese método

## Nota de implementación Fase 1
- `resolve_repair_levels` y `evaluate_mix`: ejecutan en `spasm_cli/finisher_cli_core.spasm` (sin fallback Python interno en esos métodos).
- `format_analysis_summary` y `write_analysis_toml`: resueltos en `scripts/finisher_spasm_cli` para asegurar paridad de salida con GUI actual.
