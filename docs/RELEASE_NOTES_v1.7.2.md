# Release Notes v1.7.2

## Resumen
Esta versión consolida la evolución del motor de movimiento musical en Auto-Master con seis fases: desde control anti-fatiga de subgraves hasta presets rápidos de uso en producción.

## Novedades principales

### 1) Subbass dinámico anti-fatiga
- Detección de low-end cargado por RMS/picos.
- Control más estricto en `Subbass`/`Bass` cuando hace falta.
- Menos saturación en graves para reducir fatiga.

### 2) Band Motion Fase 1 (subtle)
- Movimiento por banda basado en energía real (`RMS + peak`).
- Topes conservadores para evitar bombeo.
- Low-end casi mono por seguridad.

### 3) Band Motion Fase 2 (sync)
- Estimación liviana de BPM/pulso (sin dependencias nuevas).
- Sincronía musical de respuesta dinámica (attack/release + densidad).
- Fallback seguro si no hay tempo confiable.

### 4) Band Motion Fase 3 (feedback)
- Autoajuste por riesgo: `THD`, true peak, LRA, crest, low-end y voz.
- Atenúa movimiento cuando sube riesgo.
- Micro-empuje cuando el material lo soporta.

### 5) Band Motion Fase 4 (contextual)
- Perfil macro automático: `tight`, `balanced`, `airy`.
- Decisión según tempo, dinámica, low-end, voz y ancho estéreo.
- Guardrails para evitar sobreapertura.

### 6) Band Motion Fase 5 (control de usuario)
- Controles directos en Auto-Master:
  - Perfil: `auto/tight/balanced/airy`
  - Cantidad: `0-150%`
- Funciona en audio único y lote.
- Persistencia en presets.

### 7) Band Motion Fase 6 (presets rápidos)
- Presets de uso rápido: `Off`, `Subtle`, `Musical`, `Creative`, `Custom`.
- Sincronización automática con perfil/cantidad.
- Reconfiguración inmediata para iteración por escucha.

## Compatibilidad
- Mantiene flujo existente de Auto-Master.
- Sin dependencias nuevas requeridas para BPM/pulso.

## Documentación relacionada
- `docs/AUTO_MASTER_INTELLIGENCE.md`
- `docs/CHANGELOG.md` (sección `Unreleased`)
- `docs/README.md`
