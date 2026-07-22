# Auto-Master Inteligente

## 🎯 Visión General

El sistema **Auto-Master Inteligente** de ToneFinish analiza automáticamente las características del audio y adapta los presets de masterización para obtener resultados óptimos según el contenido.

## ¿Por Qué Es Necesario?

Los presets estáticos no consideran que cada pista es diferente:
- Una pista vocal requiere más de-essing que una instrumental
- Un track EDM con bajos fuertes necesita diferente compresión que jazz acústico
- Audio con agudos fuertes necesita protección extra contra saturación
- Material dinámico requiere compresión más suave que material plano

El sistema inteligente **resuelve esto automáticamente**.

## 🔍 Qué Analiza

### 1. **Presencia de Vocales**
- Analiza banda vocal (300-3kHz)
- Detecta si RMS > -20 dB

**Impacto:**
- ✅ Con vocales → De-esser activado y ajustado
- ❌ Sin vocales → De-esser reducido o desactivado

### 2. **Nivel de Bajos**
- Bandas: Subbass (20-60 Hz) + Bass (60-250 Hz)
- Detecta si promedio > -15 dB

**Impacto:**
- ✅ Bajos fuertes → EQ dinámico activado, control en graves
- ❌ Bajos débiles → Advertencia en presets tipo "Club" o "Energético"

### 3. **Nivel de Agudos**
- Bandas: High-Mid (2k-6kHz) + Air (6k-16kHz)
- Detecta si promedio > -18 dB

**Impacto:**
- ✅ Agudos fuertes → Saturación reducida en High-Mid y Air
- ✅ Activación de limitadores soft-knee
- ⚠️ Advertencias en presets "Vintage" (riesgo de harshness)

### 4. **Rango Dinámico**
- Calcula diferencia entre banda más fuerte y más débil
- Dinámico si > 10 dB de rango

**Impacto:**
- ✅ Dinámico → Compresión glue suave (threshold -2dB, ratio 0.85x)
- ❌ Plano → Compresión glue fuerte (threshold +2dB, ratio 1.15x)

### 5. **Riesgo de Sibilancia**
- Detecta si High-Mid > -10 dB o Air > -12 dB

**Impacto:**
- ⚠️ Riesgo alto → De-esser intensificado (1.3x)
- ✓ Riesgo bajo → De-esser estándar (1.0x)

### 6. **Balance Espectral**
- Calcula desviación estándar entre bandas
- Score 0-100 (100 = perfectamente balanceado)

**Impacto:**
- Score < 50 → Saturación reducida (0.7x drive, 0.8x mix)
- Score > 80 → Saturación aumentada (1.2x drive, 1.1x mix)
- Score < 60 → Advertencia en presets "Cinematográfico" y "Hi-Fi"

### 7. **Detección de Incompatibilidades** ⭐ NUEVO
- Valida si el preset es compatible con el contenido del audio
- Detecta desbalances severos (balance < 30)
- Identifica exceso/falta en bandas específicas

**Impacto:**
- 🚨 **Advertencias de incompatibilidad** (ej: preset "Club" sin bajos fuertes)
- 💡 **Sugerencias de presets alternativos** (3 recomendaciones)
- 🎛️ **Cálculo automático de ajustes de EQ correctivos**
- 📊 **Valores específicos en dB** para cada banda que necesita corrección

### 8. **Movimiento Musical por Bandas (Fase 1 + Fase 2)** ⭐ NUEVO
- Fase 1 (`subtle`): genera movimiento por banda usando energía real (`RMS + picos`), con topes conservadores.
- Fase 2 (`sync`): sincroniza la respuesta dinámica al compás con BPM/pulso estimados.
- En low-end: `Subbass` casi mono y `Bass` con movimiento mínimo para mantener pegada y compatibilidad mono.
- Con vocal dominante: reduce movimiento en `Mid`/`High-Mid` para proteger inteligibilidad.

**Impacto:**
- ✅ Más sensación de vida y movimiento sin paneo agresivo.
- ✅ Menor fatiga en graves por control dinámico anti-exceso.
- ✅ Respuesta más musical por sincronía al tempo cuando el BPM es confiable.
- ✅ Fallback seguro: si no hay tempo confiable, mantiene el modo sutil por energía.

### 9. **Feedback Adaptativo (Fase 3)** ⭐ NUEVO
- Evalúa riesgo de artefactos/fatiga con señales combinadas:
  - `THD` estimado del presupuesto de saturación
  - `True Peak` de entrada
  - `LRA` y `Crest Factor`
  - estado de low-end (`Subbass/Bass hot`)
  - presencia vocal dominante
- Aplica corrección automática de movimiento:
  - riesgo alto/medio: reduce `stereo_dynamic_mix` y mezcla por bandas
  - riesgo bajo + pulso confiable: habilita micro-empuje musical controlado

**Resultado esperado:**
- más consistencia entre temas
- menos fatiga en masters densos
- más movimiento en material que lo soporta sin romper seguridad

### 10. **Coreografía Contextual (Fase 4)** ⭐ NUEVO
- Aplica un perfil musical macro sobre el resultado de Fase 1-3:
  - `tight`: prioriza pegada y estabilidad (menos apertura)
  - `balanced`: equilibrio general
  - `airy`: prioriza aire y apertura en material dinámico
- La elección usa señales de contexto:
  - tempo y confianza de pulso
  - estado del low-end
  - LRA/crest factor
  - presencia vocal
  - ancho estéreo actual

**Impacto:**
- evita que todos los temas “se muevan igual”
- mejora coherencia entre géneros/estilos
- mantiene seguridad estéreo con guardrails por ancho

### 11. **Control de Usuario (Fase 5)** ⭐ NUEVO
- La UI de Auto-Master expone dos controles directos:
  - `Perfil de movimiento`: `Auto`, `Tight`, `Balanced`, `Airy`
  - `Cantidad de movimiento`: `0%` a `150%`
- El control aplica en:
  - Auto-Master de audio único
  - Auto-Master de lote
- `0%` desactiva el movimiento dinámico (Band Motion).
- Los valores se guardan en presets de mastering para reutilización.

### 12. **Presets Rápidos (Fase 6)** ⭐ NUEVO
- Presets directos en UI para iteración por oído:
  - `Off`: movimiento desactivado
  - `Subtle`: movimiento mínimo y estable
  - `Musical`: ajuste recomendado general
  - `Creative`: mayor apertura y expresividad
  - `Custom`: aparece al editar perfil/cantidad manualmente
- Los presets sincronizan automáticamente `perfil` + `cantidad`.

## ⚙️ Cómo Funciona

### Flujo de Trabajo

```
1. Usuario selecciona archivo de entrada
                ↓
2. Marca "Análisis Inteligente" en Auto-Master
                ↓
3. Selecciona preset base (Ej: "Cinta (Tape)")
                ↓
4. Click en "Auto-configurar"
                ↓
5. Sistema analiza audio (bandas + vocales)
                ↓
6. Calcula características (vocales, bajos, agudos, etc.)
                ↓
7. Adapta preset según características
                ↓
8. Aplica multiplicadores y ajustes
                ↓
9. Muestra análisis y decisiones en panel
```

### Multiplicadores Aplicados

| Parámetro | Rango | Cuando se Aplica |
|-----------|-------|------------------|
| De-esser Intensity | 0.6x - 1.3x | Según vocales y sibilancia |
| Saturation Drive | 0.7x - 1.2x | Según balance espectral |
| Saturation Mix | 0.8x - 1.1x | Según balance espectral |
| Glue Threshold | -2dB a +2dB | Según rango dinámico |
| Glue Ratio | 0.85x - 1.15x | Según rango dinámico |
| Band Saturation (High-Mid) | 0.6x drive, 0.7x mix | Si agudos fuertes |
| Band Saturation (Air) | 0.5x drive, 0.6x mix | Si agudos fuertes |

### Sincronía al Compás (Fase 2)
- Estimación de tempo: autocorrelación de onsets sobre una ventana corta (sin dependencias nuevas).
- Rango de BPM objetivo: 72-180 BPM.
- La sincronía no automatiza parámetros por frame: ajusta **tiempos dinámicos** y **densidad de movimiento** para estabilidad.

Reglas base:
- `attack` ≈ 1/12 de beat (acotado).
- `release` ≈ 2/3 de beat (acotado).
- `1/8` sugerido para BPM bajos, `1/16` para BPM altos.

## 📊 Ejemplos Prácticos

### Caso 1: Pista Vocal con Sibilancia

**Análisis:**
```
Vocales: ✓ Sí (RMS: -10.5 dB)
Agudos fuertes: ✓ Sí (High-Mid: -8.5 dB)
Riesgo sibilancia: ⚠ Sí
Balance: 48/100
```

**Preset seleccionado:** Cinta (Tape)

**Ajustes aplicados:**
- De-esser: 1.30x (intensificado)
- Saturación Drive: 0.70x (reducido por desbalance)
- Saturación Mix: 0.80x (reducido por desbalance)
- High-Mid saturación: 0.6x drive, 0.7x mix
- Air saturación: 0.5x drive, 0.6x mix
- Glue threshold: -2dB (suavizado, audio dinámico)

**Resultado:** Vocales presentes sin harshness ni saturación excesiva.

### Caso 2: EDM con Bajos y Hi-Hats Fuertes

**Análisis:**
```
Vocales: ✗ No
Bajos fuertes: ✓ Sí (Bass: -10.0 dB)
Agudos fuertes: ✓ Sí (Air: -7.5 dB)
Riesgo sibilancia: ⚠ Sí
Balance: 50/100
```

**Preset seleccionado:** Club

**Ajustes aplicados:**
- De-esser: 0.60x (reducido, sin vocales)
- Saturación Drive: 1.0x (mantiene impacto)
- High-Mid saturación: 0.6x drive, 0.7x mix (protección)
- Air saturación: 0.5x drive, 0.6x mix (protección hi-hats)
- EQ dinámico: Activado (control de bajos)

**Resultado:** Punch en bajos, brillo en hi-hats sin distorsión.

### Caso 3: Jazz Balanceado

**Análisis:**
```
Vocales: ✓ Sí (RMS: -15.0 dB)
Balance: 71/100 (bueno)
Dinámico: ✗ No (comprimido)
```

**Preset seleccionado:** Hi-Fi

**Ajustes aplicados:**
- De-esser: 1.0x (estándar)
- Saturación: Sin cambios (buen balance)
- Glue threshold: +2dB (más agresivo para dar vida)
- Glue ratio: 1.15x (más compresión)

**Resultado:** Audio plano cobra vida sin perder transparencia.

### Caso 4: Incompatibilidad Detectada ⭐ NUEVO

**Análisis:**
```
Vocales: ✗ No
Bajos fuertes: ✗ No (Bass: -22.0 dB, Subbass: -30.0 dB)
Agudos fuertes: ✓ Sí (High-Mid: -7.5 dB, Air: -9.0 dB)
Balance: 15/100 (crítico - muy desbalanceado)
```

**Preset seleccionado:** Club (requiere bajos fuertes)

**El sistema detecta INCOMPATIBILIDAD y advierte:**

```
🚨 ADVERTENCIAS:
  ⚠️ INCOMPATIBILIDAD: Preset 'Club' requiere bajos fuertes,
     pero el audio tiene bajos débiles
  🚨 BALANCE CRÍTICO: 15/100 - Audio muy desbalanceado

💡 PRESETS ALTERNATIVOS SUGERIDOS:
  ✓ Hi-Fi (mejor para audio sin bajos fuertes)
  ✓ Natural (transparente para cualquier contenido)
  ✓ Cinematografico (si tiene buen balance)

🎛️ SUGERENCIAS DE CORRECCIÓN:
  💡 Boost sugerido: Bass +3.0 dB, Subbass +2.5 dB
  💡 RECOMENDACIÓN: Corregir balance con EQ antes de masterizar

📊 AJUSTES DE EQ CALCULADOS:
  Subbass (20-60 Hz): +3.0 dB (compensar falta)
  Bass (60-250 Hz): +3.0 dB (compensar falta)
  Mid (500-2k Hz): -4.8 dB (reducir exceso)
  High-Mid (2k-6k Hz): -5.1 dB (reducir exceso)
  Air (6k-16k Hz): -4.2 dB (reducir exceso)
```

**Resultado:** El usuario es advertido claramente de que debe:
1. Usar un preset alternativo más apropiado
2. Aplicar corrección de EQ antes de masterizar
3. Considerar remezcla si es posible

**Esto evita:** Masterizaciones fallidas con presets incompatibles.

## 🎚️ Uso en la Interfaz

### 1. Activar Análisis Inteligente

```
Tab: Auto-Master
┌─────────────────────────────┐
│ Estilo: [Cinta (Tape)   ▼] │
│ ☑ Análisis Inteligente      │
│ ☐ Habilitar Procesos        │
│ [Auto-configurar]           │
└─────────────────────────────┘
```

### 2. Panel de Resumen

Después de aplicar, verás:

```
Resumen y Análisis:
═══════════════════════════════════
Estilo: Cinta (Tape)

=== ANÁLISIS INTELIGENTE ===
✓ Vocales detectadas (RMS: -10.5 dB)
  Se activará de-esser y protección
  
⚠ Riesgo de sibilancia
  De-esser intenso recomendado
  
Balance espectral: 48/100

  • High-Mid (2k-6k Hz): posible
    exceso; considera bajar ~2-3 dB.

🚨 === ADVERTENCIAS === ⭐ NUEVO
(Solo si hay incompatibilidades detectadas)
  ⚠️ Preset 'Club' requiere bajos fuertes
     pero el audio tiene bajos débiles
  🚨 Balance crítico: 15/100

💡 === PRESETS ALTERNATIVOS === ⭐ NUEVO
(Sugeridos automáticamente)
  ✓ Hi-Fi (mejor para audio sin bajos fuertes)
  ✓ Natural (transparente para cualquier contenido)
  ✓ Cinematografico (si tiene buen balance)

🎛️ === SUGERENCIAS DE EQ === ⭐ NUEVO
(Valores específicos calculados)
  Bass (60-250 Hz): +3.0 dB
  Subbass (20-60 Hz): +2.5 dB
  Mid (500-2k Hz): -4.8 dB

=== AJUSTES AUTOMÁTICOS ===
🎤 De-esser intensificado por
   riesgo de sibilancia
   
⚖️ Saturación reducida por
   desbalance espectral
   
🔒 Saturación reducida en High-Mid
   y Air (agudos fuertes)
   
🎚️ Compresión glue suavizada
   (audio dinámico)

=== CONFIGURACIÓN APLICADA ===
Tape suave, saturación ligera,
compresión leve.
```

## 🔧 Presets y Recomendaciones

### Cinta (Tape)
**Mejor para:** Vocales, baladas, R&B
**Análisis importante:** Agudos (riesgo harshness)
```
✓ Detección de vocales → Ajusta de-esser
⚠ Agudos fuertes → Reduce saturación vintage
```

### Natural
**Mejor para:** Acústico, clásico, voiceover
**Análisis importante:** Balance espectral
```
✓ Balance bueno → Mantiene transparencia
✗ Desbalanceado → Advierte al usuario
```

### Cinematográfico
**Mejor para:** Soundtracks, ambient
**Análisis importante:** Balance + dinámica
```
✓ Balance > 60 → Funciona óptimamente
✓ Dinámico → Preserva espacialidad
⚠ Balance < 60 → Advertencia
```

### Energético
**Mejor para:** Pop, rock, EDM vocal
**Análisis importante:** Todos los aspectos
```
✓ Bajos fuertes → Maximiza impacto
✓ Vocales → Protección sibilancia
⚠ Agudos fuertes → Reduce sat. High-Mid
```

### Vintage
**Mejor para:** Retro, lofi, indie
**Análisis importante:** Agudos
```
⚠ Agudos fuertes → Advertencia harshness
✓ Audio suave → Saturación vintage brilla
```

### Loud (Potente)
**Mejor para:** Mastering competitivo
**Análisis importante:** Dinámica
```
✓ Dinámico → Suaviza compresión
✗ Plano → Intensifica para "loudness"
```

### Hi-Fi
**Mejor para:** Audiófilo, high-res
**Análisis importante:** Balance
```
✓ Balance > 80 → Resultados ideales
⚠ Balance < 60 → Advertencia
✓ Dinámico → Preserva micro-dinámica
```

### Club
**Mejor para:** House, techno, bass music
**Análisis importante:** Bajos + agudos
```
✓ Bajos fuertes → Maximiza punch
✓ Sin vocales → Reduce de-esser
⚠ Agudos fuertes → Protege hi-hats
💡 Sin bajos → Sugiere boost
```

## 💡 Consejos de Uso

### ✅ Buenas Prácticas

1. **Siempre activa Análisis Inteligente** para primera pasada
2. **Lee el panel de resumen** para entender las decisiones
3. **Usa las advertencias** como guía para ajustes manuales
4. **Compara A/B** con/sin análisis inteligente

### ⚠️ Limitaciones

- Requiere archivo de entrada válido
- El análisis toma 2-5 segundos extra
- Funciona mejor con mezclas finalizadas
- No reemplaza el oído crítico del ingeniero

### 🎯 Cuándo Desactivarlo

- Ya conoces perfectamente el material
- Quieres un preset "puro" sin ajustes
- Estás haciendo A/B testing de presets
- Trabajas con stems (no mix completo)

## 🚀 Ventajas del Sistema

| Aspecto | Sin Inteligencia | Con Inteligencia |
|---------|------------------|------------------|
| **Saturación vocal** | Puede ser excesiva | Ajustada según contenido |
| **De-esser** | Valor fijo | Adaptado a sibilancia |
| **Compresión** | Estática | Según dinámica |
| **Protección bandas** | Manual | Automática |
| **Compatibilidad preset** | Usuario adivina | Sistema advierte |
| **Velocidad de trabajo** | Varios ajustes | Un click |

## 📚 Referencias Técnicas

### Archivos del Sistema

- **`auto_master_intelligence.py`** - Lógica de análisis y adaptación
- **`ui_app.py`** - Integración en interfaz
- **`audio_analysis.py`** - Análisis de bandas y vocales

### Funciones Clave

```python
# Análisis completo
analyze_audio_for_automaster(input_path) 
  → (AudioCharacteristics, recommendations)

# Adaptación de preset
adapt_preset_to_audio(preset_name, characteristics)
  → adjustments_dict

# Aplicación de ajustes
apply_intelligent_adjustments(base_params, adjustments)
  → adjusted_params
```

### Clase AudioCharacteristics

```python
class AudioCharacteristics:
    band_stats: Dict[str, float]
    voice_rms: float | None
    has_vocals: bool
    has_strong_bass: bool
    has_strong_highs: bool
    is_dynamic: bool
    needs_deess: bool
    balance_score: float  # 0-100
```

## 🔄 Actualización de Versión

Esta funcionalidad se introdujo en **ToneFinish 1.1.0** junto con el control de saturación en bandas sensibles.

**Compatibilidad:** 100% retrocompatible. El checkbox puede desactivarse para usar presets tradicionales.

---

**Ver también:**
- [SATURATION_CONTROL.md](SATURATION_CONTROL.md) - Control de saturación por banda
- [README.md](README.md) - Documentación general
- [CHANGELOG.md](CHANGELOG.md) - Historial de cambios
