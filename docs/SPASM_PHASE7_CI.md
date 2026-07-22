# Fase 7 en CI

Este proyecto ejecuta el gate de Fase 7 en GitHub Actions con el workflow:

- `.github/workflows/spasm-phase7-gate.yml`

## Jobs
- `phase7-gate-adapter`:
  - usa `scripts/spasm_cli_adapter`
  - valida compatibilidad general del contrato CLI
  - artifact: `spasm-phase7-report-adapter`
- `phase7-gate-strict`:
  - usa `scripts/finisher_spasm_cli`
  - corre con `FINISHER_SPASM_FALLBACK_PYTHON=0`
  - artifact: `spasm-phase7-report-strict`

## Qué valida
- `scripts/spasm_cli_smoke.sh`
- Benchmark externo removido (usar métricas de runtime del lote)
- generación de `log/spasm_phase7_report.json`

## Notas de CI
- El job `adapter` evita dependencia de binario SpASM externo.
- El job `strict` valida la ruta operativa final del proyecto.
- Se instala `ffmpeg` por `apt`.
- El reporte JSON se publica como artifact (uno por job).

## Ejecución local equivalente
```bash
export FINISHER_SPASM_CLI=./scripts/spasm_cli_adapter
# Gate operativo: ejecutar lote smoke y validar JSON/TOML generados.
```
