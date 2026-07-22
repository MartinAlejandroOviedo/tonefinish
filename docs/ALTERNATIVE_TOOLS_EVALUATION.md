# Evaluación de Herramientas Alternativas para ToneFinish

## Estado de Implementación

### ✅ Implementado (v1.5.1+)

1. **Módulo `alternative_tools.py`**
   - Detección automática de herramientas disponibles (SoX, Carla, Pedalboard, etc.)
   - Análisis de loudness para dos pasadas reales
   - Función `build_loudnorm_two_pass()` para normalización precisa
   - Funciones de procesamiento con Pedalboard (EQ, compresión)
   - Recomendaciones de instalación

2. **Normalización de Dos Pasadas Real**
   - Parámetro `two_pass_normalize=True` en `normalize_audio()`
   - Procesa primero a archivo temporal sin loudnorm
   - Analiza estadísticas reales del audio preprocesado
   - Aplica loudnorm con estadísticas medidas (máxima precisión)

3. **Margen de Seguridad para True Peak** ⭐ NUEVO
   - `TRUE_PEAK_SAFETY_MARGIN_DB = 0.5` en `config.py`
   - Compensa limitaciones de FFmpeg con inter-sample peaks
   - Si el usuario pide -1.0 dBTP, se procesa a -1.5 dBTP
   - Garantiza que el resultado real sea ≤ target

4. **SoX para Resampling de Alta Calidad**
   - Detección automática de SoX
   - Fallback a FFmpeg si no está disponible

### Cómo Activar

```python
# En la llamada a normalize_audio():
result = normalize_audio(
    input_path,
    output_path,
    stats,
    target_lufs=-14.0,
    true_peak=-1.5,
    # ... otros parámetros ...
    two_pass_normalize=True,  # ← Activar para máxima precisión
)
```

---

## Problema Identificado

FFmpeg tiene limitaciones en:
1. **True Peak Limiting** - `alimiter` no es tan preciso para inter-sample peaks
2. **Loudnorm en modo linear** - Requiere dos pasadas reales, no siempre preciso con preproceso
3. **Upsampling** - Puede generar picos inter-sample después de procesamiento

## Herramientas Candidatas (awesome-linuxaudio)

### 1. SoX (Swiss Army Knife) ⭐⭐⭐⭐⭐
**Instalación:** `sudo apt install sox libsox-fmt-all`

**Uso recomendado:**
- **Resampling de alta calidad** (mejor que aresample de FFmpeg)
- **Normalización** 
- **Filtros de audio**

```bash
# Resampling con SoX (muy alta calidad)
sox input.wav output.wav rate -v -H 96000

# Normalización con headroom
sox input.wav output.wav gain -n -1

# Limiter (aunque básico)
sox input.wav output.wav compand 0.01,0.3 -60,-60,-30,-30,0,-3 0 -3
```

**Integración en ToneFinish:**
```python
import subprocess

def resample_with_sox(input_path: str, output_path: str, sample_rate: int = 96000) -> bool:
    """Resample usando SoX para máxima calidad."""
    cmd = [
        'sox', input_path, output_path,
        'rate', '-v', '-H', str(sample_rate)  # Very high quality
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0
```

---

### 2. ebumeter (Medición EBU R128) ⭐⭐⭐⭐⭐
**Instalación:** `sudo apt install ebumeter`

**Uso:** Medición precisa de LUFS/True Peak según EBU R128

```bash
# Analizar archivo
ebumeter -r archivo.wav
```

**Nota:** Es GUI, para CLI usar `ffmpeg -i input.wav -af loudnorm=print_format=json -f null -`

---

### 3. Linux Studio Plugins (LSP) ⭐⭐⭐⭐⭐
**Instalación:** `sudo apt install lsp-plugins`

Incluye:
- **lsp-plugins-limiter-stereo** - Limiter con true-peak lookahead
- **lsp-plugins-compressor-stereo** - Compresor profesional
- **lsp-plugins-loud-comp-stereo** - Compensación de loudness

**Problema:** Son plugins LV2/VST, requieren host como Carla o integración directa.

---

### 4. zam-plugins (zamaximizer) ⭐⭐⭐⭐
**Instalación:** `sudo apt install zam-plugins`

- **zamulimiter** - Limiter con lookahead true-peak
- **zamaximizer** - Maximizer/limiter

**Problema:** Son plugins LV2, requieren host.

---

### 5. Carla (Plugin Host) ⭐⭐⭐⭐
**Instalación:** `sudo apt install carla`

**Uso:** Permite ejecutar plugins LV2/VST desde línea de comandos

```bash
# Procesar archivo con plugins LV2
carla-single lv2 http://lsp-plug.in/plugins/lv2/limiter_stereo input.wav -o output.wav
```

---

### 6. lamb-rs (Lookahead Limiter) ⭐⭐⭐⭐⭐
**Repo:** https://github.com/magnetophon/lamb-rs

Limiter lookahead muy transparente, diseñado para preservar el carácter del audio.

**Problema:** Necesita compilación o disponible como plugin LV2.

---

### 7. LoudMax (Closed Source) ⭐⭐⭐⭐
**Web:** https://loudmax.blogspot.com/

Limiter brickwall con lookahead, muy transparente. Gratuito pero no open source.

---

## Comparativa de Precisión

| Herramienta | True Peak | LUFS | Transparencia | CLI Nativo | Python |
|-------------|-----------|------|---------------|------------|--------|
| FFmpeg alimiter | ⭐⭐⭐ | - | ⭐⭐⭐ | ✅ | ❌ |
| FFmpeg loudnorm | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | ❌ |
| SoX | ⭐⭐⭐ | - | ⭐⭐⭐⭐⭐ | ✅ | ❌ |
| LSP Limiter | ⭐⭐⭐⭐⭐ | - | ⭐⭐⭐⭐⭐ | ❌ (LV2) | via VST3 |
| zam-plugins | ⭐⭐⭐⭐ | - | ⭐⭐⭐⭐ | ❌ (LV2) | via VST3 |
| lamb-rs | ⭐⭐⭐⭐⭐ | - | ⭐⭐⭐⭐⭐ | ❌ (LV2) | via VST3 |
| **Pedalboard Limiter** | ⭐⭐ | - | ⭐⭐⭐⭐ | ❌ | ✅ |
| **Pedalboard + LSP VST3** | ⭐⭐⭐⭐⭐ | - | ⭐⭐⭐⭐⭐ | ❌ | ✅ |

---

## Estrategia Recomendada

### Opción A: Mantener solo herramientas CLI (Más Simple)

1. **Usar SoX para resampling** en lugar de aresample de FFmpeg
2. **Mantener FFmpeg para el resto** pero con ajustes:
   - `loudnorm` siempre con `linear=false` cuando hay preproceso
   - `alimiter` con configuración más agresiva (attack=0.01)
   - Añadir margen extra al target (-16 LUFS para conseguir -14)

```python
# Pipeline híbrido
def process_hybrid(input_path, output_path, settings):
    temp_file = "/tmp/processed.wav"
    
    # 1. FFmpeg para filtros principales (EQ, compresor, etc.)
    run_ffmpeg_processing(input_path, temp_file, settings)
    
    # 2. SoX para resampling final de alta calidad
    sox_resample(temp_file, output_path, settings.sample_rate)
```

### Opción B: Integrar Plugins LV2 via Carla (Más Preciso)

1. **Usar Carla-single** para ejecutar plugins LV2 desde CLI
2. **LSP Limiter** para true-peak preciso
3. **ebumeter** para verificación

```python
def apply_lsp_limiter(input_path, output_path, ceiling_db=-1.5):
    """Aplicar LSP Limiter via Carla."""
    cmd = [
        'carla-single', 'lv2',
        'http://lsp-plug.in/plugins/lv2/limiter_stereo',
        input_path, '-o', output_path,
        # Configuración del plugin
        f'--param=ceiling:{ceiling_db}'
    ]
    subprocess.run(cmd, check=True)
```

### Opción C: Procesamiento en Dos Pasadas Real (Más Confiable)

1. **Primera pasada:** Analizar audio procesado (sin normalización)
2. **Segunda pasada:** Aplicar loudnorm con estadísticas reales

```python
def two_pass_loudnorm(input_path, output_path, target_lufs=-14.0):
    """Normalización real de dos pasadas."""
    
    # Paso 1: Obtener estadísticas reales
    stats = analyze_with_ffmpeg(input_path)
    
    # Paso 2: Aplicar loudnorm con estadísticas medidas
    ffmpeg_cmd = [
        'ffmpeg', '-i', input_path,
        '-af', f'loudnorm=I={target_lufs}:TP=-1.5:LRA=11:'
               f'measured_I={stats["input_i"]}:'
               f'measured_TP={stats["input_tp"]}:'
               f'measured_LRA={stats["input_lra"]}:'
               f'measured_thresh={stats["input_thresh"]}:'
               f'offset={stats["target_offset"]}:'
               f'linear=true:print_format=summary',
        output_path
    ]
    subprocess.run(ffmpeg_cmd, check=True)
```

---

## Integración Propuesta para ToneFinish

### Fase 1: Mejoras Inmediatas (Sin dependencias nuevas)

1. ✅ Implementar loudnorm en dos pasadas real
2. ✅ Ajustar alimiter con attack más rápido
3. ✅ Añadir margen de seguridad al target LUFS

### Fase 2: Integrar SoX (Dependencia mínima)

1. Añadir SoX como dependencia opcional
2. Usar SoX para resampling cuando esté disponible
3. Fallback a FFmpeg si no está instalado

```python
def get_resampler():
    """Detectar mejor resampler disponible."""
    if shutil.which('sox'):
        return 'sox'
    return 'ffmpeg'
```

### Fase 3: Integrar LV2 Plugins (Dependencia mayor)

1. Añadir Carla como dependencia opcional
2. Usar LSP Limiter para casos críticos
3. Fallback a FFmpeg si no está disponible

---

## Dependencias Recomendadas

### Mínimas (ya instaladas típicamente)
```bash
sudo apt install ffmpeg
```

### Recomendadas
```bash
sudo apt install sox libsox-fmt-all
```

### Avanzadas (para máxima calidad)
```bash
sudo apt install sox libsox-fmt-all lsp-plugins carla
```

---

## Conclusión

Para ToneFinish, la **Opción A + Opción C** es la más práctica:

1. **SoX para resampling** - Mejor calidad, CLI nativo
2. **Loudnorm en dos pasadas real** - Más preciso
3. **Mantener FFmpeg** para el resto del procesamiento

Esto minimiza dependencias mientras mejora significativamente la precisión.

---

## 9. Evaluación de Librerías Python Adicionales

### Tabla Resumen

| Librería | Instalación | True Peak | Loudnorm | Velocidad | Valor para ToneFinish |
|----------|-------------|-----------|----------|-----------|----------------------|
| **pydub** | `pip install pydub` | ❌ Usa FFmpeg | ❌ Usa FFmpeg | Media | ❌ Sin valor añadido |
| **librosa** | `pip install librosa` | ❌ Solo análisis | ❌ | Lenta | ⚠️ Análisis espectral |
| **scipy** | `pip install scipy` | ⚠️ Manual | ❌ | Rápida | ⚠️ Filtros DSP |
| **soundfile** | `pip install soundfile` | ❌ Solo I/O | ❌ | Muy rápida | ✅ Base para DSP |
| **essentia** | `pip install essentia` | ✅ **TruePeakDetector** | ✅ **LoudnessEBUR128** | Rápida | ⭐⭐⭐⭐⭐ **MUY ÚTIL** |
| **aubio** | `pip install aubio` | ❌ Solo análisis | ❌ | Rápida | ❌ No relevante |
| **sounddevice** | `pip install sounddevice` | ❌ Tiempo real | ❌ | N/A | ❌ No relevante |

### Análisis Detallado

#### 1. pydub ❌ No Recomendado
- **Descripción**: Wrapper de alto nivel para FFmpeg
- **Problema**: No añade nada que FFmpeg no tenga
- **Uso típico**: Edición básica (cortar, unir, normalizar)
- **Veredicto**: Redundante con nuestra implementación actual

#### 2. librosa ⚠️ Uso Limitado
- **Descripción**: Análisis musical y espectrogramas
- **Fortalezas**: MFCCs, espectrogramas, análisis de tempo
- **Limitaciones**: No tiene compresor/limitador, lenta
- **Posible uso**: Análisis de espectro para visualización
- **Veredicto**: No resuelve puntos flojos, pero útil para análisis futuro

#### 3. scipy ⚠️ Potencial para DSP Custom
- **Descripción**: Procesamiento de señales científico
- **Fortalezas**: Filtros FIR/IIR, convolución, diseño de EQ
- **Posible uso**: Implementar True Peak limiter custom con oversampling
- **Veredicto**: Requiere mucho desarrollo propio

```python
# Ejemplo: Filtro IIR con scipy
from scipy.signal import butter, sosfilt

def butter_highpass(cutoff, fs, order=5):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    sos = butter(order, normal_cutoff, btype='high', output='sos')
    return sos

def highpass_filter(data, cutoff, fs, order=5):
    sos = butter_highpass(cutoff, fs, order=order)
    return sosfilt(sos, data)
```

#### 4. soundfile ✅ Útil como Base
- **Descripción**: Lectura/escritura de WAV/FLAC eficiente
- **Fortalezas**: Muy rápida, arrays NumPy nativos
- **Posible uso**: Base para procesamiento DSP propio
- **Veredicto**: Complementa bien a otras librerías

#### 5. essentia ⭐⭐⭐⭐⭐ MUY RECOMENDADO
- **Descripción**: Framework avanzado de análisis y procesamiento musical
- **Desarrollado por**: Music Technology Group (UPF Barcelona)
- **Usado por**: Spotify, Waves, LANDR, KORG, Plex

**Algoritmos Relevantes:**

| Algoritmo | Descripción | Uso en ToneFinish |
|-----------|-------------|-------------------|
| `TruePeakDetector` | Detector de True Peak (inter-sample) | ⭐ **Verificación de True Peak** |
| `LoudnessEBUR128` | Medición EBU R128 completa | ⭐ **Análisis LUFS preciso** |
| `ClickDetector` | Detecta clicks/pops | Análisis de calidad |
| `SaturationDetector` | Detecta regiones saturadas | Análisis de clipping |
| `HumDetector` | Detecta ruido de línea (50/60Hz) | Análisis de calidad |
| `GapsDetector` | Detecta silencios/cortes | Análisis de calidad |
| `ReplayGain` | Cálculo de ReplayGain | Normalización |

**Ejemplo de uso:**
```python
import essentia
import essentia.standard as es

# Cargar audio
loader = es.MonoLoader(filename='audio.wav')
audio = loader()

# Medir True Peak (¡lo que necesitamos!)
true_peak_detector = es.TruePeakDetector()
true_peak, peaks = true_peak_detector(audio)
print(f"True Peak: {true_peak} dB")

# Medir Loudness EBU R128
loudness = es.LoudnessEBUR128(startAtZero=True)
momentary, shortterm, integrated, range_ = loudness(audio)
print(f"Integrated LUFS: {integrated} LUFS")
```

**Veredicto**: Essentia es la librería más prometedora. Tiene:
- ✅ TruePeakDetector nativo
- ✅ LoudnessEBUR128 nativo
- ✅ Usada en producción por empresas como LANDR (mastering automático)
- ✅ Optimizada en C++ con bindings Python

#### 6. aubio ❌ No Relevante
- **Descripción**: Detección de pitch, beats, onset
- **Uso típico**: Análisis rítmico y melódico
- **Veredicto**: No resuelve nuestros puntos flojos

#### 7. sounddevice ❌ No Relevante
- **Descripción**: Captura y reproducción en tiempo real
- **Uso típico**: Aplicaciones de audio en vivo
- **Veredicto**: No aplicable a procesamiento de archivos

### Recomendación Final

**Instalar Essentia** para:
1. **Verificación de True Peak** - Usar `TruePeakDetector` para validar el resultado de FFmpeg
2. **Análisis LUFS preciso** - Usar `LoudnessEBUR128` como segunda verificación
3. **Análisis de calidad** - Detectar clicks, saturación, hum, etc.

```bash
# Instalación
pip install essentia soundfile
```

### ✅ Resultados de Pruebas (2026-01-21)

**Test: Señal 12kHz @ 44.1kHz (caso peor para inter-sample peaks)**

| Métrica | Essentia | FFmpeg | Diferencia |
|---------|----------|--------|------------|
| True Peak | +0.06 dBTP | +0.20 dBTP | 0.14 dB |
| LUFS | -11.9 LUFS | -12.0 LUFS | 0.1 LU |

**Conclusión:** Essentia y FFmpeg dan resultados muy similares (< 0.2 dB).
Essentia detecta inter-sample peaks correctamente (+0.51 dB sobre sample peak).

### Funciones Implementadas en `alternative_tools.py`

```python
from alternative_tools import (
    is_essentia_available,        # Verificar disponibilidad
    measure_true_peak_essentia,   # Medir True Peak con oversampling
    measure_loudness_essentia,    # Medir LUFS + LRA
    verify_true_peak,             # Verificar vs objetivo
)

# Ejemplo de uso
tp = measure_true_peak_essentia("audio.wav")  # Returns: +0.06 dBTP

passes, measured, msg = verify_true_peak("audio.wav", target_true_peak=-1.0)
# Returns: (False, 0.06, "⚠️ True Peak EXCEDE: +0.06 dBTP > -1.0 dBTP")
```

**Estrategia híbrida implementada:**
```
Audio → [FFmpeg: Procesamiento + loudnorm] → [Essentia: Verificación True Peak/LUFS]
                                                        ↓
                                              Si True Peak > target:
                                              → Reprocesar con margen extra
```

---

## 10. Pedalboard (Spotify)

**Instalación:** `pip install pedalboard`

Librería Python de Spotify para procesamiento de audio. Muy rápida (300x más que pySoX), thread-safe, y puede cargar plugins VST3.

### Plugins Incluidos

| Plugin | Uso | ¿True Peak? |
|--------|-----|-------------|
| `Limiter` | Brickwall limiter | ❌ Solo sample peak |
| `Compressor` | Compresor dinámico | - |
| `Gain` | Ajuste de ganancia | - |
| `HighpassFilter` | Filtro pasa-altos | - |
| `LowpassFilter` | Filtro pasa-bajos | - |
| `HighShelfFilter` | EQ tipo shelf | - |
| `LowShelfFilter` | EQ tipo shelf | - |
| `PeakFilter` | EQ paramétrico | - |
| `Clipping` | Hard/soft clipping | - |
| `NoiseGate` | Noise gate | - |
| `Reverb` | Reverberación | - |
| `Chorus` | Efecto chorus | - |
| `Delay` | Delay digital | - |
| `Phaser` | Efecto phaser | - |
| `Distortion` | Distorsión | - |
| `Resample` | Cambio de sample rate | - |

### Evaluación del Limiter

```python
from pedalboard import Limiter
import numpy as np

# Parámetros disponibles
limiter = Limiter(threshold_db=-1.5, release_ms=50)
# NO tiene: attack_ms, lookahead, true-peak

# Resultado de pruebas:
# Audio original 12kHz sine @ -0.1dB sample → True Peak: +0.4 dBTP
# Después de Limiter(threshold=-1.5dB)    → True Peak: +0.5 dBTP ⚠️
# 
# CONCLUSIÓN: El Limiter de Pedalboard es SAMPLE PEAK, no True Peak.
# NO es adecuado para mastering broadcast donde se requiere True Peak ≤ -1dBTP
```

### Carga de Plugins VST3

La ventaja principal de Pedalboard es que puede cargar plugins VST3 externos:

```python
from pedalboard import load_plugin

# Cargar LSP Limiter (si está instalado como VST3)
# sudo apt install lsp-plugins-vst3
lsp_limiter = load_plugin("/usr/lib/vst3/lsp-limiter-stereo.vst3")

# Ver parámetros disponibles
print(lsp_limiter.parameters)

# Procesar audio
processed = lsp_limiter(audio, sample_rate)
```

### Integración Propuesta para ToneFinish

```python
from pedalboard import Pedalboard, Compressor, Gain, HighpassFilter, LowpassFilter
from pedalboard.io import AudioFile
import numpy as np

def process_with_pedalboard(
    input_path: str,
    output_path: str,
    highpass_hz: float = 30,
    lowpass_hz: float = 16000,
    compress_threshold: float = -20,
    compress_ratio: float = 4,
    makeup_gain: float = 6,
) -> bool:
    """
    Procesa audio usando Pedalboard (más rápido que FFmpeg para algunos filtros).
    
    NOTA: Para True Peak limiting, usar FFmpeg loudnorm después de esto.
    """
    try:
        # Leer audio
        with AudioFile(input_path) as f:
            audio = f.read(f.frames)
            sample_rate = f.samplerate
        
        # Cadena de procesamiento
        board = Pedalboard([
            HighpassFilter(cutoff_frequency_hz=highpass_hz),
            LowpassFilter(cutoff_frequency_hz=lowpass_hz),
            Compressor(
                threshold_db=compress_threshold,
                ratio=compress_ratio,
                attack_ms=10,
                release_ms=100,
            ),
            Gain(gain_db=makeup_gain),
            # NO usar Limiter aquí - no es True Peak
        ])
        
        # Procesar
        processed = board(audio, sample_rate)
        
        # Guardar
        with AudioFile(output_path, 'w', sample_rate, audio.shape[0]) as f:
            f.write(processed)
        
        return True
    except Exception as e:
        print(f"Error con Pedalboard: {e}")
        return False
```

### Cuándo Usar Pedalboard vs FFmpeg

| Tarea | Pedalboard | FFmpeg | Recomendado |
|-------|------------|--------|-------------|
| Compresión | ✅ Rápido | ✅ Flexible | Pedalboard |
| EQ (filtros) | ✅ Rápido | ✅ Flexible | Pedalboard |
| Sample Peak Limit | ✅ | ✅ | Cualquiera |
| **True Peak Limit** | ❌ | ⚠️ alimiter | FFmpeg loudnorm |
| **Loudness norm** | ❌ | ✅ loudnorm | FFmpeg |
| Cargar VST3 | ✅ | ❌ | Pedalboard |
| Reverb/Delay | ✅ | ⚠️ Limitado | Pedalboard |
| Conversión formato | ❌ | ✅ | FFmpeg |

### Conclusión sobre Pedalboard

**Ventajas:**
- ⚡ Muy rápido (300x más rápido que pySoX)
- 🐍 Nativo Python, fácil de integrar
- 🔌 Puede cargar plugins VST3 (acceso a LSP, etc.)
- 💾 Lee/escribe audio directamente sin shell

**Limitaciones:**
- ❌ **El Limiter NO es True Peak** - no sirve para broadcast
- ❌ No tiene loudnorm EBU R128 nativo
- ❌ No convierte formatos de audio

**Recomendación para ToneFinish:**
1. **Usar Pedalboard para:** Compresión, EQ, efectos, y como bridge a plugins VST3
2. **Usar FFmpeg para:** Loudnorm final y True Peak limiting
3. **Híbrido óptimo:** Pedalboard para preproceso → FFmpeg loudnorm para normalización final

---

## Referencias

- [awesome-linuxaudio](https://github.com/nodiscc/awesome-linuxaudio)
- [LSP Plugins](https://lsp-plug.in/)
- [SoX Documentation](http://sox.sourceforge.net/sox.html)
- [EBU R128](https://tech.ebu.ch/loudness)
- [Pedalboard GitHub](https://github.com/spotify/pedalboard)
- [Pedalboard Docs](https://spotify.github.io/pedalboard/)
