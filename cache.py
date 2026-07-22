"""
Sistema de caché para análisis de audio.

Evita re-analizar archivos que ya fueron procesados anteriormente.
El caché se basa en un hash rápido del archivo (primeros 1MB + tamaño).
"""

import hashlib
import json
import pathlib
from typing import Any, Dict, Optional

# Directorio de caché
CACHE_DIR = pathlib.Path.home() / ".tonefinish" / "cache"
CACHE_SCHEMA_VERSION = 2

def _valid_band_stats(values: Any) -> bool:
    """Rechaza resultados legacy vacíos/silenciosos que contaminarían la decisión IA."""
    if not isinstance(values, dict) or len(values) < 6:
        return False
    try:
        measured = [float(value) for value in values.values()]
    except (TypeError, ValueError):
        return False
    return any(value > -69.0 for value in measured)


def _compute_file_hash(file_path: pathlib.Path, chunk_size: int = 1024 * 1024) -> str:
    """
    Calcula un hash rápido del archivo basado en:
    - Primeros 1MB del contenido
    - Tamaño total del archivo
    
    Es rápido incluso para archivos grandes y detecta cambios efectivamente.
    """
    hasher = hashlib.md5()
    file_size = file_path.stat().st_size
    
    # Incluir tamaño en el hash
    hasher.update(str(file_size).encode())
    
    # Leer solo el primer chunk
    with open(file_path, 'rb') as f:
        chunk = f.read(chunk_size)
        hasher.update(chunk)
        
        # Si el archivo es grande, también leer un chunk del medio y del final
        if file_size > chunk_size * 3:
            # Chunk del medio
            f.seek(file_size // 2)
            hasher.update(f.read(chunk_size))
            # Chunk del final
            f.seek(max(0, file_size - chunk_size))
            hasher.update(f.read(chunk_size))
    
    return hasher.hexdigest()


def _get_cache_path(file_hash: str) -> pathlib.Path:
    """Obtiene la ruta del archivo de caché para un hash dado."""
    return CACHE_DIR / f"{file_hash}.json"


def get_cached_analysis(file_path: pathlib.Path) -> Optional[Dict[str, Any]]:
    """
    Busca análisis en caché para un archivo.
    
    Retorna None si no hay caché o si está corrupto.
    Retorna dict con: {
        'stats': {...},
        'band_stats': {...},
        'suggestions': [...],
        'voice_rms': float,
        'audio_info': {...}
    }
    """
    if not file_path.exists():
        return None
    
    try:
        file_hash = _compute_file_hash(file_path)
        cache_path = _get_cache_path(file_hash)
        
        if not cache_path.exists():
            return None
        
        with open(cache_path, 'r', encoding='utf-8') as f:
            cached = json.load(f)
        
        # Verificar que el caché tiene los campos necesarios
        if (cached.get('schema_version') != CACHE_SCHEMA_VERSION
                or 'stats' not in cached or not _valid_band_stats(cached.get('band_stats'))):
            return None
        
        return cached
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def save_analysis_cache(
    file_path: pathlib.Path,
    stats: Dict[str, float],
    band_stats: Dict[str, float],
    suggestions: list[str],
    voice_rms: Optional[float],
    audio_info: Optional[Dict] = None,
) -> bool:
    """
    Guarda el análisis en caché.
    
    Retorna True si se guardó correctamente, False en caso de error.
    """
    if not file_path.exists():
        return False
    
    try:
        # Asegurar que el directorio de caché existe
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        file_hash = _compute_file_hash(file_path)
        cache_path = _get_cache_path(file_hash)
        
        cache_data = {
            'schema_version': CACHE_SCHEMA_VERSION,
            'file_name': file_path.name,
            'stats': stats,
            'band_stats': band_stats,
            'suggestions': suggestions,
            'voice_rms': voice_rms,
            'audio_info': audio_info or {},
        }
        
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)
        
        return True
    except (OSError, TypeError):
        return False


def clear_cache() -> int:
    """
    Limpia todo el caché de análisis.
    
    Retorna el número de archivos eliminados.
    """
    if not CACHE_DIR.exists():
        return 0
    
    count = 0
    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            cache_file.unlink()
            count += 1
        except OSError:
            pass
    
    return count


def get_cache_size() -> tuple[int, int]:
    """
    Obtiene estadísticas del caché.
    
    Retorna: (número de archivos, tamaño total en bytes)
    """
    if not CACHE_DIR.exists():
        return 0, 0
    
    count = 0
    total_size = 0
    
    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            count += 1
            total_size += cache_file.stat().st_size
        except OSError:
            pass
    
    return count, total_size


def invalidate_cache(file_path: pathlib.Path) -> bool:
    """
    Invalida el caché para un archivo específico.
    
    Retorna True si se eliminó el caché, False si no existía.
    """
    if not file_path.exists():
        return False
    
    try:
        file_hash = _compute_file_hash(file_path)
        cache_path = _get_cache_path(file_hash)
        
        if cache_path.exists():
            cache_path.unlink()
            return True
        return False
    except OSError:
        return False
