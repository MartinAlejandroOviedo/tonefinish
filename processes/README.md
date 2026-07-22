# Arquitectura Modular de Procesos - ToneFinish

## Estructura de Archivos

```
processes/
├── __init__.py          # Exportaciones públicas y orchestrator global
├── base.py              # Clases base (BaseProcess, ProcessRegistry, ProcessCategory)
├── orchestrator.py      # Orquestador de cadena de procesos
├── repair.py            # Reparación (noise, declip, declick, pink noise)
├── deesser.py           # De-esser (sibilantes)
├── tone_eq.py           # Ecualizador tonal (bass, mid, treble, tilt)
├── multiband.py         # Procesamiento multibanda (EQ dinámico, stereo, saturación)
├── saturation.py        # Saturación global
├── stereo_dynamic.py    # Control dinámico M/S
├── glue.py              # Compresión glue
├── autogain.py          # Sistema AutoGain (headroom, limiters, normalización)
└── loudness.py          # Mastering (loudnorm, limiter, fades)
```

## Clases Base

### ProcessCategory (Enum)
Categorías para organización en la GUI:
- `REPAIR`: Reparación (noise, declip, declick)
- `MIX`: Mezcla (deesser, EQ, saturación, stereo, glue)
- `MASTER`: Mastering (autogain, loudness)
- `OPTIONS`: Opciones generales

### BaseProcess (Abstract)
Clase base para todos los procesos. Propiedades:
- `id`: Identificador único ("repair", "deesser", etc.)
- `name`: Nombre para GUI ("Reparación", "De-Esser", etc.)
- `description`: Descripción del proceso
- `category`: ProcessCategory
- `enabled`: True/False
- `order`: Orden en la cadena (10, 20, 30...)
- `config`: ProcessConfig con parámetros

Métodos:
- `build_filter(input_label, **kwargs)`: Construye filtro ffmpeg
- `get_params() / set_params()`: Gestión de parámetros
- `reset_to_defaults()`: Reset a valores por defecto

### ProcessRegistry
Registro de procesos:
- `register(process)`: Registrar proceso
- `get(id)`: Obtener proceso por ID
- `get_all()`: Todos los procesos en orden
- `get_by_category(category)`: Por categoría
- `set_order(list)`: Cambiar orden
- `enable(id, bool)`: Habilitar/deshabilitar
- `enable_category(category, bool)`: Por categoría

## Uso Básico

### Importar el Orquestador
```python
from processes import orchestrator

# Construir cadena de filtros
filter_chain, output_label = orchestrator.build_filter_chain(
    input_path=path,
    band_stats=stats,
    repair_enabled=True,
    mix_enabled=True,
    autogain_enabled=True,
    # Parámetros específicos
    noise_reduction_level="Leve",
    deesser=True,
    deesser_freq_hz=6000.0,
    saturation_enabled=True,
    saturation_mix=0.3,
    glue_enabled=True,
)
```

### Gestionar Procesos Individuales
```python
# Habilitar/deshabilitar
orchestrator.set_process_enabled("saturation", False)

# Obtener proceso
repair = orchestrator.get_process("repair")
repair.set_param("noise_level", "Medio")

# Cambiar orden
orchestrator.set_process_order([
    "repair", "multiband", "deesser", "tone_eq", 
    "saturation", "stereo_dynamic", "glue", "autogain"
])

# Por categoría
orchestrator.set_category_enabled(ProcessCategory.REPAIR, True)
```

### Usar Procesos Directamente
```python
from processes import RepairProcess, DeesserProcess

# Crear instancia
repair = RepairProcess()
repair.enabled = True
repair.set_params({
    "noise_level": "Medio",
    "declip_level": "Leve",
})

# Construir filtro
chain, label = repair.build_filter(
    input_label="0:a",
    noise_level="Medio",
)
```

## Procesos Disponibles

### Reparación (repair)
- **noise_level**: Off, Leve, Medio, Alto, Auto
- **declip_level**: Off, Leve, Medio, Alto, Auto
- **declick_level**: Off, Leve, Medio, Alto, Auto
- **pink_noise_level**: Off, Leve, Medio, Alto

### De-Esser (deesser)
- **enabled**: True/False
- **frequency_hz**: 4000-8000 Hz
- **intensity**: 0.2-1.0

### Tone EQ (tone_eq)
- **low_db**: -12 a +12 dB
- **mid_db**: -12 a +12 dB
- **high_db**: -12 a +12 dB
- **tilt_db**: -6 a +6 dB

### Multiband (multiband)
- **dynamic_eq**: True/False
- **stereo_width**: True/False
- **auto_band_gain**: True/False
- **band_adjust_db**: Dict[band_name, float]
- **band_widths**: Dict[band_name, float]
- **saturation_per_band**: True/False
- **saturation_band_drive_db**: Dict[band_name, float]
- **saturation_band_mix**: Dict[band_name, float]

### Saturación (saturation)
- **saturation_enabled**: True/False
- **saturation_type**: "Tape", "Tube"
- **drive_db**: -24 a +24 dB
- **mix**: 0.0-1.0

### Stereo Dynamic (stereo_dynamic)
- **stereo_dynamic**: True/False
- **per_band**: True/False
- **threshold_db**: -40 a 0 dB
- **ratio**: 1.0-4.0
- **attack_ms**: 1-100 ms
- **release_ms**: 10-500 ms
- **mix**: 0.0-1.0

### Glue (glue)
- **glue_enabled**: True/False
- **threshold_db**: -40 a 0 dB
- **ratio**: 1.0-4.0
- **attack_ms**: 1-100 ms
- **release_ms**: 10-500 ms
- **makeup_db**: -12 a +12 dB

### AutoGain (autogain)
- **autogain_enabled**: True/False
- **headroom_db**: Default -17 dB
- **final_peak_db**: Default -1 dB

### Loudness (loudness)
- **target_lufs**: Default -14.0
- **true_peak**: Default -1.0
- **brickwall**: True/False
- **fade_in**: 0+ segundos
- **fade_out**: 0+ segundos

## Flujo de Procesamiento

```
INPUT
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ AUTOGAIN: Headroom (-17dB)                          │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ REPAIR (si repair_enabled)                          │
│   ├── Declip                                        │
│   ├── Declick                                       │
│   ├── Noise Reduction                               │
│   └── Pink Noise Reduction                          │
│   + Limiter                                         │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ MIX (si mix_enabled)                                │
│   ├── De-Esser → Limiter                            │
│   ├── Tone EQ → Limiter                             │
│   ├── Multiband EQ → Limiter                        │
│   ├── Saturation → Limiter                          │
│   ├── Stereo Dynamic → Limiter                      │
│   └── Glue → Limiter                                │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ AUTOGAIN: Final Peak Norm (-1dB)                    │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ MASTER (si master_enabled)                          │
│   ├── Loudnorm (LUFS target)                        │
│   ├── Limiter (brickwall)                           │
│   └── Fades                                         │
└─────────────────────────────────────────────────────┘
  │
  ▼
OUTPUT
```

## Integración con GUI

Para integrar con la GUI, cada proceso expone su información:

```python
from processes import orchestrator

# Generar UI dinámicamente
for process in orchestrator.registry:
    # Crear checkbox para habilitar
    checkbox = QCheckBox(process.name)
    checkbox.setChecked(process.enabled)
    checkbox.toggled.connect(lambda v, p=process: p.enabled = v)
    
    # Agrupar por categoría
    category_layout = layouts[process.category]
    category_layout.addWidget(checkbox)
    
    # Crear controles según parámetros
    for param_name, param_value in process.get_params().items():
        # Crear slider, spinbox, combobox según tipo...
```

## Serialización

```python
# Guardar estado
state = orchestrator.to_dict()
json.dump(state, open("preset.json", "w"))

# Cargar estado
state = json.load(open("preset.json"))
orchestrator.from_dict(state)
```
