# Auto-Master Adaptativo (Fases 1-8)

Este documento describe el flujo adaptativo actual sin romper el pipeline existente de ToneFinish.

## Objetivo
- Mantener el mastering base estable.
- Agregar inteligencia temporal por secciones/eventos.
- Tomar decisiones trazables por artefactos.
- Desplegar en modo seguro (`shadow` + `guard` + rollout canario).

## Flujo operativo
1) Procesamiento de audio principal (tema por tema).
2) Análisis temporal MTS (ventana/hop) con métricas por tramo.
3) Detección de eventos y segmentación por secciones.
4) Generación de decisiones por sección (`master_decisions`).
5) Evaluación de riesgo en `adaptive_shadow`.
6) Validación técnica en `adaptive_guard`.
7) En lote, resumen A/B de rollout (`batch_rollout_*`).

## Criterio de ejecución en lote
- El procesamiento de audio es secuencial: un archivo a la vez.
- El MTS se procesa con una cola dedicada de 1 worker para no saturar recursos.
- Esto permite mantener estabilidad y, a la vez, adelantar análisis temporal.

## Artefactos por tema
Todos se escriben en la carpeta `log/` del output:
- `<tema>.mts.json` y `<tema>.mts.md`
- `<tema>.master_decisions.json` y `<tema>.master_decisions.md`
- `<tema>.adaptive_shadow.json` y `<tema>.adaptive_shadow.md`
- `<tema>.adaptive_guard.json` y `<tema>.adaptive_guard.md`

En lote también:
- `batch_rollout_YYYYMMDD_HHMMSS.json`
- `batch_rollout_YYYYMMDD_HHMMSS.md`

## Fases 1-8 (resumen)
- Fase 1: movimiento por energía real de bandas.
- Fase 2: sincronía por pulso/BPM estimado.
- Fase 3: feedback adaptativo por riesgo.
- Fase 4: coreografía contextual por perfil macro.
- Fase 5: control de usuario (perfil/cantidad).
- Fase 6: presets rápidos de movimiento.
- Fase 7: guardrails + flags de rollout.
- Fase 8: reporte A/B canario (decisión segura, sin forzar apply global).

## Feature flags
- `TONEFINISH_ADAPTIVE_MASTER_ENABLED` (default: `false`)
- `TONEFINISH_ADAPTIVE_SHADOW_ENABLED` (default: `true`)
- `TONEFINISH_ADAPTIVE_GUARD_STRICT` (default: `true`)
- `TONEFINISH_ADAPTIVE_ROLLOUT_PERCENT` (default: `0`, rango `0-100`)

## Lectura rápida de resultados
1) Revisar `*.adaptive_guard.json`:
- `overall_ok`
- `recommended_mode`
- `blockers` y `warnings`
2) Revisar `*.adaptive_shadow.json`:
- `summary.global_risk`
- `summary.apply_ready`
- `sections_high_risk`
3) Revisar `*.master_decisions.json`:
- cantidad de `section_decisions`
- magnitud de acciones por sección
4) En lote, revisar `batch_rollout_*.json`:
- `canary_files`
- `guard_ok_files`
- `apply_ready_files`
- `enable_apply_files`

## Inspector (UI)
- Pestaña: `Resultados -> Inspector`.
- Entrada principal: ruta a `*.mts.json`.
- Carga automática de artefactos vecinos:
  - `.master_decisions.json`
  - `.adaptive_shadow.json`
  - `.adaptive_guard.json`
- También puede cargar desde una fila del historial.
