# Fase 6 - Hardening y Release

Fecha: 2026-05-20

## Objetivo
Cerrar migración con foco en estabilidad operativa, observabilidad y rollback seguro.

## Endurecimiento aplicado
- Timeout configurable en backend CLI (`FINISHER_SPASM_TIMEOUT_SEC`).
- Smoke test rápido de métodos críticos: `scripts/spasm_cli_smoke.sh`.
- Benchmark integrado en el pipeline principal (script externo removido).

## Variables de entorno recomendadas (producción)
```bash
export FINISHER_LOGIC_BACKEND=spasm
export FINISHER_SPASM_CLI=/home/martin/Documentos/GitHub/finisher/scripts/finisher_spasm_cli
export FINISHER_SPASM_FALLBACK_PYTHON=0
export FINISHER_SPASM_TIMEOUT_SEC=600
```

## Validación pre-release
```bash
./scripts/spasm_cli_smoke.sh
# Benchmark por método: usar métricas de runtime/log del lote.
python3 main.py
```

## Rollback inmediato
Si hay falla crítica en producción:
```bash
export FINISHER_LOGIC_BACKEND=python
export FINISHER_SPASM_FALLBACK_PYTHON=1
```

## Criterios de aceptación
- Smoke OK.
- Flujo GUI: analizar/procesar/lote/auto-master sin errores críticos.
- Benchmark estable (sin degradación severa entre corridas).
- Rollback validado.
