# Sistema de Licenciamiento Free/Premium

## Resumen

ToneFinish ahora cuenta con un sistema de licenciamiento que divide la aplicación en dos versiones:
- **Free**: Solo modos Auto-Master (configuración automática)
- **Premium**: Acceso completo a todos los modos (Manual, Solo analizar, etc.)

## Cambios Implementados

### 1. Sistema de Licenciamiento (`config.py`)

Se agregaron las siguientes funciones y constantes:

- `LICENSE_TYPE_FREE` y `LICENSE_TYPE_PREMIUM`: Constantes para tipos de licencia
- `_load_license_type()`: Carga el tipo de licencia desde `~/.tonefinish/license.json`
- `save_license_type(license_type: str)`: Guarda el tipo de licencia
- `is_premium()`: Verifica si la licencia actual es Premium
- `get_license_display_name()`: Retorna "ToneFinish Free" o "ToneFinish Premium"

### 2. Interfaz de Usuario (`ui_app.py`)

**Combo de Modos:**
- En modo **Free**: Solo muestra "Auto-Master (Audio)" y "Auto-Master (Lote)"
- En modo **Premium**: Muestra todos los modos (Manual, Audio único, Lote, Auto-Master Audio/Lote, Solo analizar)
- Tooltip explicativo según la licencia

**Botones de Acción:**
- En modo **Free**: Solo muestra botones de procesamiento (oculta Analizar y Normalizar)
- En modo **Premium**: Todos los botones disponibles según el modo

**Tabs:**
- En modo **Free**: Tab "Procesamiento" (manual) permanentemente oculto
- En modo **Premium**: Todos los tabs accesibles

### 3. Tabs de Información (`ui/tabs_new.py`)

**Tab Inicio (`build_start_tab_new`):**
- Muestra indicador visual del tipo de licencia (color verde para Premium, naranja para Free)
- Ayuda contextual diferente según la licencia
- Mensaje informativo en Free sobre actualización a Premium

**Tab Acerca de (`build_about_tab_new`):**
- Muestra el tipo de licencia con color distintivo
- En modo **Free**:
  - Lista de características Premium bloqueadas
  - Botón temporal "Activar Premium (Dev)" para desarrollo/testing
  - Información sobre cómo actualizar

## Archivo de Licencia

La licencia se almacena en: `~/.tonefinish/license.json`

Estructura:
```json
{
  "type": "free",  // o "premium"
  "version": "1.5.0"
}
```

## Activación de Premium (Temporal)

Para desarrollo y testing, se incluye un botón en el tab "Acerca de" que permite activar Premium.
Al activar, se solicita reiniciar la aplicación.

**Para activar Premium manualmente:**
```python
from config import save_license_type, LICENSE_TYPE_PREMIUM
save_license_type(LICENSE_TYPE_PREMIUM)
# Reiniciar la aplicación
```

## Características por Versión

### ToneFinish Free ✓
- ✅ Auto-Master (Audio) - Procesamiento inteligente de archivo único
- ✅ Auto-Master (Lote) - Procesamiento inteligente de múltiples archivos
- ✅ Configuración automática de parámetros
- ✅ Firma digital
- ✅ Múltiples formatos de salida
- ❌ Modo Manual (control de parámetros)
- ❌ Modo Solo Analizar
- ❌ Acceso a tab Procesamiento

### ToneFinish Premium 🌟
- ✅ **Todos los modos de Free**
- ✅ Modo Manual con control total
- ✅ Modo Solo Analizar (sin escritura)
- ✅ Procesamiento por archivo único
- ✅ Modo Lote manual
- ✅ Acceso completo a parámetros de procesamiento
- ✅ Control avanzado de saturación, EQ, dinámica
- ✅ Botones de análisis individual

## Flujo de Usuario

### Primera Ejecución (Free por defecto)
1. La app inicia en modo Free
2. Solo muestra modos Auto-Master
3. Tab de inicio muestra "ToneFinish Free"
4. Usuario puede ver información de Premium en "Acerca de"

### Actualización a Premium
1. Usuario hace clic en "Activar Premium (Dev)" en tab Acerca de
2. Se guarda la licencia en `~/.tonefinish/license.json`
3. Se solicita reiniciar la aplicación
4. Al reiniciar, todos los modos están disponibles

## Notas para Producción

El botón "Activar Premium (Dev)" es temporal para desarrollo. Para producción, se debe:

1. **Opción A - Código de Activación:**
   - Añadir campo de entrada para código de licencia
   - Validar código contra servidor o algoritmo
   - Guardar licencia al validar

2. **Opción B - Archivo de Licencia:**
   - Usuario descarga archivo `.license` después de comprar
   - Importar archivo desde la UI
   - Validar firma del archivo

3. **Opción C - Validación Online:**
   - Login con email/usuario
   - Validar licencia contra servidor
   - Cache local con renovación periódica

4. **Opción D - Builds Separados:**
   - Compilar versiones Free y Premium por separado
   - Sin sistema de activación interno

## Mantenimiento

Para agregar más restricciones por licencia en el futuro:

```python
from config import is_premium

# En cualquier parte del código
if not is_premium():
    # Funcionalidad bloqueada en Free
    show_premium_upgrade_message()
    return

# Funcionalidad Premium
do_advanced_thing()
```

## Testing

Para probar ambos modos:

```bash
# Modo Free (por defecto)
python main.py

# Para activar Premium desde código:
python -c "from config import save_license_type, LICENSE_TYPE_PREMIUM; save_license_type(LICENSE_TYPE_PREMIUM)"
python main.py

# Para volver a Free:
python -c "from config import save_license_type, LICENSE_TYPE_FREE; save_license_type(LICENSE_TYPE_FREE)"
python main.py

# O eliminar el archivo:
rm ~/.tonefinish/license.json
```
