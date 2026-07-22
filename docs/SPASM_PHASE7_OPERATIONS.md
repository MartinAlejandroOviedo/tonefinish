# Fase 7 - Operación Continua

Fecha: 2026-05-20

## Objetivo
Dejar un gate operativo repetible para validar backend SpASM antes de release o despliegue.

## Herramientas
- Smoke: `scripts/spasm_cli_smoke.sh`
- Benchmark/Gate externos removidos; usar logs de lote y reportes `*.mts.json`.

## Ejecución recomendada
```bash
export FINISHER_LOGIC_BACKEND=spasm
export FINISHER_SPASM_CLI=/home/martin/Documentos/GitHub/finisher/scripts/finisher_spasm_cli
export FINISHER_SPASM_FALLBACK_PYTHON=0
export FINISHER_SPASM_TIMEOUT_SEC=600

# Validación operativa: ejecutar lote corto y revisar reportes en `log/`.
```

## Salida
- Reporte JSON en `log/spasm_phase7_report.json` con:
  - estado smoke
  - estado benchmark
  - métricas por método
  - resultado final (`phase7_pass` / `phase7_fail`)

## Política mínima
- Si `phase7_fail`: no publicar release, revisar reporte y corregir.
- Si `phase7_pass`: apto para validación funcional final de GUI.

## Rollback
Si aparece regresión en entorno final:
```bash
export FINISHER_LOGIC_BACKEND=python
export FINISHER_SPASM_FALLBACK_PYTHON=1
```
