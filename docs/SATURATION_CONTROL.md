# Control de Saturación en Bandas Sensibles

## Problema Identificado

ToneFinish no tenía control adecuado sobre la saturación en las bandas de frecuencia que contienen:
- **Vocales del cantante** (High-Mid: 2kHz-6kHz)
- **Metales/Hi-hats** (Air: 6kHz-16kHz)

La suma de múltiples procesos (compresión dinámica + stereo width + saturación) en estas bandas causaba clipping y distorsión no deseada.

## Soluciones Implementadas

### 1. Limitadores Soft-Knee Por Banda

Se añadieron limitadores suaves específicos para las bandas sensibles:

```python
# En config.py
BAND_HEADROOM_DB = {
    "High-Mid (2k-6k Hz)": -2.0,  # Vocales y sibilantes
    "Air (6k-16k Hz)": -3.0,       # Hi-hats y platillos
}
```

**Beneficios:**
- Previene clipping duro antes de la mezcla final
- Usa ataque rápido (0.5ms) y release moderado (50ms)
- Solo se activa en bandas sensibles

### 2. Límites de Drive de Saturación

Control específico del drive máximo permitido por banda:

```python
MAX_SATURATION_DRIVE_DB = {
    "High-Mid (2k-6k Hz)": 12.0,  # Límite conservador para vocales
    "Air (6k-16k Hz)": 8.0,        # Límite estricto para metales
}
```

**Beneficios:**
- Evita exceso de saturación en frecuencias críticas
- Protege la claridad vocal
- Preserva el detalle de hi-hats sin harshness

### 3. Detección de Saturación en Análisis

La función `analyze_eq_bands()` ahora detecta picos cercanos a 0dB:

```python
if peak_db > -1.0 and label in ("High-Mid (2k-6k Hz)", "Air (6k-16k Hz)"):
    suggestions.append(
        f"{label}: ADVERTENCIA - pico cercano a 0dB ({peak_db:.1f}dB), "
        f"riesgo de saturación!"
    )
```

### 4. Validación de Configuración

Nueva función `validate_saturation_settings()` que:
- Verifica valores de drive vs límites recomendados
- Alerta sobre combinaciones peligrosas de drive + mix
- Informa sobre headroom aplicado automáticamente
- Compara con análisis previo para detectar riesgos

## Uso en la Práctica

### Configuración Recomendada para Vocales

```python
saturation_band_drive_db = {
    "High-Mid (2k-6k Hz)": 6.0,   # Moderado para presencia
    "Air (6k-16k Hz)": 4.0,        # Suave para brillo
}

saturation_band_mix = {
    "High-Mid (2k-6k Hz)": 0.4,   # 40% de mezcla
    "Air (6k-16k Hz)": 0.3,        # 30% de mezcla
}
```

### Configuración Recomendada para Metales

```python
saturation_band_drive_db = {
    "High-Mid (2k-6k Hz)": 3.0,   # Muy suave
    "Air (6k-16k Hz)": 5.0,        # Moderado para cuerpo
}

saturation_band_mix = {
    "High-Mid (2k-6k Hz)": 0.2,   # 20% de mezcla
    "Air (6k-16k Hz)": 0.4,        # 40% de mezcla
}
```

## Parámetros de Control

### `enable_band_limiter` (bool)
- **Default:** `True`
- **Descripción:** Habilita limitadores soft en bandas sensibles
- **Cuándo desactivar:** Solo si quieres saturación extrema intencional

### Headroom Automático

El headroom se aplica automáticamente según `BAND_HEADROOM_DB`:
- **High-Mid:** -2.0 dB (protege vocales)
- **Air:** -3.0 dB (protege metales brillantes)

### Orden de Procesamiento

El limitador se aplica DESPUÉS de:
1. EQ dinámico (compand)
2. Stereo width
3. Band adjust (ganancia manual)
4. Saturación por banda

Pero ANTES de:
- Mezcla de bandas
- Glue compression
- Limitador final

## Casos de Uso

### ✅ Vocal Principal con Saturación Controlada

```python
# Análisis previo detecta RMS alto en High-Mid
band_stats = {"High-Mid (2k-6k Hz)": -8.0}

# Configuración conservadora
normalize_audio(
    ...,
    saturation_per_band=True,
    saturation_band_drive_db={"High-Mid (2k-6k Hz)": 6.0},
    saturation_band_mix={"High-Mid (2k-6k Hz)": 0.35},
    enable_band_limiter=True  # Headroom de -2dB aplicado
)
```

**Resultado:** Presencia vocal con calidez sin harshness ni clipping.

### ✅ Hi-Hats Brillantes sin Distorsión

```python
# Configuración para metales
normalize_audio(
    ...,
    saturation_per_band=True,
    saturation_band_drive_db={"Air (6k-16k Hz)": 5.0},
    saturation_band_mix={"Air (6k-16k Hz)": 0.4},
    enable_band_limiter=True  # Headroom de -3dB aplicado
)
```

**Resultado:** Brillo y presencia sin sibilancia excesiva.

### ❌ Configuración Problemática (evitar)

```python
# ADVERTENCIA: Esto causará saturación excesiva
normalize_audio(
    ...,
    saturation_per_band=True,
    saturation_band_drive_db={"High-Mid (2k-6k Hz)": 20.0},  # Excede límite
    saturation_band_mix={"High-Mid (2k-6k Hz)": 0.9},         # Mix muy alto
    enable_band_limiter=False  # Sin protección
)
```

**Problema:** Drive excede MAX_SATURATION_DRIVE_DB (12.0), mix demasiado alto, sin limitador.

## Monitoreo y Diagnóstico

### Advertencias del Validador

El sistema genera advertencias automáticas:

```
⚠️ High-Mid (2k-6k Hz): Drive de saturación (15.0dB) excede el límite 
   recomendado (12.0dB). Se aplicará limitador de seguridad.

⚠️ Air (6k-16k Hz): Combinación alta de drive (10.0dB) y mix (80%) 
   puede causar saturación. Considera reducir uno de los valores.

ℹ️ High-Mid (2k-6k Hz): Se aplicará headroom de seguridad de -2.0dB 
   para prevenir clipping.
```

### Análisis de Picos

El análisis de bandas ahora reporta:

```
High-Mid (2k-6k Hz): ADVERTENCIA - pico cercano a 0dB (-0.3dB), 
riesgo de saturación!
```

## Filtros ffmpeg Generados

### Con Limitador de Banda (ejemplo High-Mid)

```bash
[b4]highpass=f=2000,lowpass=f=6000,
compand=...,
stereotools=mlev=1:slev=1.2,
volume=-2.0dB,
alimiter=limit=0.7943:attack=0.5:release=50,  # <- Limitador añadido
asplit=2[c4b][c4d]
```

### Drive Limitado por MAX_SATURATION_DRIVE_DB

```python
# Antes: drive_db = 20.0 (sin límite)
# Ahora: drive_db = 12.0 (limitado para High-Mid)
```

## Comparación Antes/Después

| Aspecto | Antes | Después |
|---------|-------|---------|
| **Control de saturación** | ❌ Sin límites por banda | ✅ Límites específicos por banda |
| **Prevención de clipping** | ❌ Solo limitador final | ✅ Limitador soft por banda sensible |
| **Headroom** | ❌ No considerado | ✅ -2dB (vocales), -3dB (metales) |
| **Detección de riesgos** | ❌ Solo análisis básico | ✅ Validación con advertencias |
| **Suma de procesos** | ❌ Saturación acumulativa | ✅ Control individual + limitador |

## Notas Técnicas

### Algoritmo del Limitador

```
limit_linear = 10^(headroom_db / 20.0)
alimiter=limit={limit_linear}:attack=0.5:release=50
```

- **Attack:** 0.5ms (muy rápido, captura transientes)
- **Release:** 50ms (rápido pero musical)
- **Tipo:** Soft-knee (preserva dinámica)

### Integración con Cadena de Procesamiento

El limitador se inserta en la posición óptima:

```
Input → Highpass → Lowpass → Compand → Stereo Width → 
Volume Adjust → [LIMITER] → Saturation → Mix
```

Esto asegura que todos los procesos acumulativos estén controlados antes de la saturación.

## Recomendaciones Finales

1. **Siempre analiza primero:** Usa el análisis de bandas para conocer el contenido
2. **Empieza conservador:** Valores bajos de drive y mix, luego incrementa
3. **Monitorea advertencias:** Presta atención a las validaciones del sistema
4. **Usa headroom:** Mantén `enable_band_limiter=True` por defecto
5. **A/B testing:** Compara con/sin limitadores para tu material

## Actualización de Versión

Estas mejoras se integran en la versión **1.1.0** de ToneFinish.

**Compatibilidad:** Totalmente retrocompatible. Los parámetros nuevos tienen defaults seguros.
