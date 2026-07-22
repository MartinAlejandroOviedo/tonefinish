# Release Notes v1.7.3

## Resumen
Esta versión estabiliza la lógica adaptativa del Auto-Master en producción real de lotes: guard más robusto, menos falsos positivos y ejecución estrictamente tema por tema.

## Novedades principales

### 1) Guard de picos más inteligente
- `peak_risk` ahora se evalúa por **tasa por minuto** y **severidad**.
- Se reduce el bloqueo por picos aislados que no representan riesgo real sostenido.

### 2) MTS post-proceso para validación
- El MTS usado por guard se calcula sobre el **audio ya procesado**.
- La validación queda alineada con el resultado final real, no con el input crudo.

### 3) Menos falsos positivos en detección de peak_risk
- El detector de `peak_risk` medio ahora exige contexto de energía/dinámica (`RMS/crest`).

### 4) Lote secuencial estricto
- Cada tema se procesa de punta a punta antes de iniciar el siguiente:
  - análisis
  - render
  - validación
  - MTS + decisions + shadow + guard

### 5) Empaquetado Debian actualizado
- El script `packaging/build_deb.sh` incluye todos los módulos nuevos del flujo adaptativo.

## Resultado observado en logs recientes
- Lote `Master2028`: `guard_ok=8/8`, `apply_ready=8/8`.
- Mejora frente al lote anterior con bloqueos por `peak_risk`.

## Documentación relacionada
- `docs/ADAPTIVE_MASTER_WORKFLOW.md`
- `docs/CHANGELOG.md`
- `docs/README.md`
