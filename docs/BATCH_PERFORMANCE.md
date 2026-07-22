# Batch Performance Note

Fecha: 2026-03-31

## Contexto

Se compararon cinco archivos procesados con el flujo nuevo de `Auto-Master (Lote)`, donde cada tema entra de forma secuencial con deep analysis propio y validación final liviana.

## Archivos revisados

- `Return to your roots (Melodic Techno MIx)_processed.toml`
- `Return to your roots () Club Mix_processed.toml`
- `Return to your roots (House Tribal Mix)_processed.toml`
- `Return to your roots (Main Mix)_processed.toml`
- `Return to your roots (Tribal Tech Mix)_processed.toml`

## Resultados observados

Promedios del lote:

- `I`: `-19.89 LUFS` -> `-11.77 LUFS`
- `TP`: `-6.12 dBTP` -> `-0.90 dBTP`
- `LRA`: `6.38 LU` -> `5.32 LU`

Lectura técnica:

- El flujo nuevo fue más fluido y evitó el costo de un preanálisis global.
- La ganancia final quedó más agresiva en algunos temas y empujó varios archivos cerca del techo.
- Dos archivos quedaron en estado `Bueno`.
- Tres archivos quedaron en estado `Necesita trabajo` por exceso de nivel o true peak demasiado cercano al límite.

## Observación por archivo

- `Melodic Techno MIx`: `-19.45` -> `-10.17 LUFS`, `-6.35` -> `-0.16 dBTP`
- `Club Mix`: `-20.30` -> `-10.13 LUFS`, `-6.05` -> `-0.30 dBTP`
- `House Tribal Mix`: `-19.59` -> `-10.14 LUFS`, `-6.02` -> `-0.03 dBTP`
- `Main Mix`: `-20.54` -> `-14.20 LUFS`, `-5.94` -> `-2.00 dBTP`
- `Tribal Tech Mix`: `-19.58` -> `-14.20 LUFS`, `-6.24` -> `-2.00 dBTP`

## Conclusión

La arquitectura por tema funciona mejor para rendimiento y sensación de fluidez. El siguiente ajuste útil no es volver al análisis global, sino bajar un poco la agresividad de la calibración final en lote para que los temas más densos no terminen tan cerca de `0 dBTP`.
