# ToneFinish

![ToneFinish](assets/tonefinish.svg)

ToneFinish es una aplicación de audio para analizar, normalizar y finalizar pistas mediante DeepSeek, el runtime SpASM y su skill FFmpeg.

## ⚡ Novedades v4.2.1

### 🧠 Auto-Master canónico y auditable
- ✅ DeepSeek decide la cadena por tema usando IDs estables de funciones de audio.
- ✅ Si la IA no tiene tokens o no responde, se utiliza exclusivamente `SUNO Clásico`.
- ✅ Los reportes incluyen `audio_actions`, `decision_trace`, orden efectivo, acciones ejecutadas y auditoría.
- ✅ Cada acción declara si corta, realza, atenúa, estrecha, expande o protege, junto con evidencia medible.
- ✅ El contrato impide que la IA etiquete un valor negativo como boost o uno positivo como corte.
- ✅ Presupuestos globales impiden acumulaciones de EQ, makeup y ganancia, incluso sobre una misma banda.
- ✅ EQ dinámica con IDs estables para controlar resonancias o dar movimiento tonal sin fijar una EQ rígida en todo el tema.
- ✅ DeepSeek sólo puede aplicarla cuando el análisis local confirma frecuencia, exceso y ubicación Mid/Side.
- ✅ Procesamiento vocal sin stems: supresor de resonancias y naturalizador central con IDs propios.
- ✅ La voz estimada debe superar un umbral de confianza; Side queda intacto y no se agrega vibrato artificial.
- ✅ Control complementario de transientes, fase estéreo, graves, dureza y opacidad mediante cinco IDs auditables.
- ✅ La expansión estéreo y los realces espectrales quedan bloqueados si las mediciones locales no los justifican.
- ✅ Las decisiones MTS por sección ahora llegan al audio con movimientos máximos de ±0,8 dB y rampas suaves.
- ✅ El candidato adaptativo se publica sólo después de recalibrar y aprobar LUFS/True Peak; si falla, queda el master estático.
- ✅ Certificación reproducible de los 36 IDs y comparación A/B de integridad por plugin.
- ✅ Auditoría estricta a ±0,30 LU, con parámetros y huella SHA-256 de cada acción ejecutada.
- ✅ El master final se realimenta hasta cumplir loudness y true peak dentro de tolerancia.

### 🎛️ SpASM y seguridad de señal
- ✅ Procesamiento mediante el skill `ffmpeg-spasm`, con descubrimiento portable del runtime `spasm`.
- ✅ Limitadores sin compensación automática de nivel (`level=false`) para evitar incrementos involuntarios.
- ✅ Validación adaptativa `PASS` y fallback seguro al master estático cuando una guardia bloquea el candidato.

### 📦 Empaquetado
- ✅ Paquete Debian con dependencias explícitas de SpASM y el skill FFmpeg.
- ✅ Inclusión de todos los módulos del contrato canónico y del nombrado `Artista - canción`.
- ✅ Interfaz oscura con texto blanco y flujo exclusivamente automático.

### 🧩 Auto-Master adaptativo estabilizado (nuevo)
- ✅ Guard de `peak_risk` por densidad/severidad (no solo conteo absoluto)
- ✅ MTS de validación sobre audio procesado (post), no sobre input crudo
- ✅ Menos falsos positivos en detección de picos aislados
- ✅ Lote en modo secuencial estricto tema por tema (incluido MTS)
- ✅ Rollout con `guard_ok` estable en lote completo (8/8 en pruebas recientes)

### 🧪 Lote Por Tema
- ✅ **Deep analysis por archivo** antes de procesar cada tema
- ✅ **Procesamiento secuencial**: un tema a la vez hasta terminar la cola
- ✅ **Fast validation final** con loudness / true peak, sin re-escaneo pesado global
- ✅ **Menos carga** de CPU, disco y FFmpeg durante el análisis del lote

### 🧠 Governor de Recursos y Telemetría
- ✅ **Monitoreo pasivo** de CPU, RAM, memoria libre y procesos `ffmpeg`
- ✅ **Perfiles estándar** de máquina: Baja, Media, Alta y Muy alta
- ✅ **Selector manual** de perfil con opción `Auto`
- ✅ **Persistencia por instalación** del perfil elegido
- ✅ **Dosificación básica** de procesos FFmpeg según el perfil activo

### ⚙️ Benchmark Espectral
- ✅ **Benchmark por UI** para comparar CPU vs GPU en el análisis espectral
- ✅ **Benchmark por consola** con `python3 main.py --benchmark-spectrum archivo.wav`
- ✅ **Reporte honesto**: diferencia GPU física y backend GPU disponible
- ✅ **Recomendación automática** para decidir si conviene ampliar a `analysis.features`

### 📋 Estados de Proceso Más Claros
- ✅ **Tarjeta visible** de estado en el panel de Procesamiento
- ✅ **Color por etapa**: analizando, procesando, validando, finalizado y error
- ✅ **Historial corto** de mensajes dentro de la UI
- ✅ **Historial por lote** con tiempos por archivo y por etapa

### 🧪 Lote Más Estable
- ✅ **Temporales por archivo** fuera de la carpeta de destino
- ✅ **Copia final** solo al terminar cada archivo
- ✅ **Menos saturación** de CPU, disco y procesos

### 🎚️ Ajustes de mezcla más conservadores
- ✅ **Sub bass** independiente con valores negativos y positivos
- ✅ **Stereo width por bandas** mantenido
- ✅ **Stereo dinámico por bandas** retirado de la UI
- ✅ **Saturación mínima** como color controlado

## Highlights
- **Governor de recursos** - Dosifica carga según CPU/RAM y perfil de máquina
- **Telemetría visible** - Muestra estados y historial de proceso
- **Lote por tema** - Deep analysis individual y validación final liviana
- **Control de saturación** - Protección en bandas vocales y de metales
- Loudness en dos pasadas (LUFS, LRA, True Peak)
- Control dinámico por bandas y stereo width
- De-esser adaptativo con control de sibilancia
- Glue compression, limiter brickwall y fades
- Procesamiento por lote con resultados por archivo
- Reportes TOML con diagnóstico y firma digital
- Pestaña Ondas con forma de onda interactiva y fades por archivo

## Créditos
- Desarrollo y dirección técnica: Martín Alejandro Oviedo + Ashriel
- Asistencia técnica y refinamiento: Nico

## Instalación (Debian)
```bash
./packaging/build_deb.sh
sudo apt install ./releases/tonefinish_4.2.1.deb
# o usar el enlace estable:
sudo apt install ./releases/tonefinish_latest.deb
```

El paquete requiere `spasm >= 0.2.10` y `spasm-skill-ffmpeg-subset >= 0.2.10`.

## Documentación
- `docs/README.md` - Documentación general
- `docs/BATCH_PERFORMANCE.md` - Comparación técnica del lote por tema
- `python3 main.py --benchmark-spectrum archivo.wav` - Benchmark CPU vs GPU del espectro
- `docs/AUTO_MASTER_INTELLIGENCE.md` - Sistema inteligente de Auto-Master
- `docs/SATURATION_CONTROL.md` - Control de saturación por banda
- `docs/CHANGELOG.md` - Historial de cambios
- `docs/RELEASE_NOTES_v1.7.3.md` - Notas de versión de estabilización adaptativa

## Reproducibilidad de audio
- `runtime_lock.json` fija versiones esperadas de `ffmpeg` y paquetes críticos.
- `requirements-lock.txt` fija el entorno Python completo recomendado.
- Al iniciar (`python3 main.py`) ToneFinish ahora valida el entorno y avisa si detecta diferencias que puedan afectar el resultado final.
- Para instalar el lock completo:
```bash
python3 -m pip install -r requirements-lock.txt
```

## Backend de lógica (GUI Python + CLI SpASM)
- La interfaz y la estrategia IA se ejecutan en Python.
- SpASM y su skill FFmpeg ejecutan el procesamiento de señal.
- El runtime instalado se descubre automáticamente mediante `PATH`.

Variables de entorno:
```bash
export FINISHER_LOGIC_BACKEND=spasm
export FINISHER_SPASM_CLI=/ruta/a/finisher_spasm_cli
export FINISHER_SPASM_BIN=/ruta/a/spasm
python3 main.py
```

Contrato esperado del CLI SpASM:
- Comando: `"$FINISHER_SPASM_CLI" call --json`
- Entrada stdin: JSON con `method`, `args`, `kwargs`.
- Salida stdout: JSON `{ "ok": true, "result": ... }` o `{ "ok": false, "error": "..." }`.

### CLI SpASM real (núcleo en SpASM)
También podés usar el CLI con núcleo SpASM:

```bash
export FINISHER_LOGIC_BACKEND=spasm
export FINISHER_SPASM_CLI="$PWD/scripts/finisher_spasm_cli"
# 1 (default): métodos no implementados en SpASM caen a Python temporalmente
export FINISHER_SPASM_FALLBACK_PYTHON=1
python3 main.py
```

La selección IA/SUNO permanece en Python para conservar el contrato y los IDs de función. El procesamiento de audio utiliza SpASM; el modo híbrido solo conserva fallback para operaciones no implementadas por el runtime instalado.
