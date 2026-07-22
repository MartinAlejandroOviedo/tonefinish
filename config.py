BAND_CONFIG = [
    ("Subbass (20-60 Hz)", 20, 60, 0.06, 0.40, 0.0),
    ("Bass (60-250 Hz)", 60, 250, 0.04, 0.30, 0.2),
    ("Low-Mid (250-500 Hz)", 250, 500, 0.03, 0.20, 0.7),
    ("Mid (500-2k Hz)", 500, 2000, 0.05, 0.25, 1.0),
    ("High-Mid (2k-6k Hz)", 2000, 6000, 0.04, 0.20, 1.2),
    ("Air (6k-16k Hz)", 6000, 16000, 0.005, 0.08, 1.4),
]

VOICE_BAND = ("Voz (300-3k Hz)", 300, 3000)

# Bandas sensibles a saturación (índices en BAND_CONFIG)
# Incluye bajos que pueden causar distorsión con saturación excesiva
SENSITIVE_BANDS = [0, 1, 4, 5]  # Subbass, Bass, High-Mid, Air

# Headroom de seguridad por banda para prevenir clipping (legacy - usado si MB limiter está off)
# Valores más negativos = más margen de seguridad
BAND_HEADROOM_DB = {
    "Subbass (20-60 Hz)": -2.5,     # Subgraves - evitar distorsión en woofers
    "Bass (60-250 Hz)": -2.0,       # Graves - control de energía
    "Low-Mid (250-500 Hz)": -1.0,   # Cuerpo - leve control
    "Mid (500-2k Hz)": -1.5,        # Frecuencias fundamentales
    "High-Mid (2k-6k Hz)": -3.5,    # Vocales y sibilantes - más control
    "Air (6k-16k Hz)": -5.0,        # Hi-hats y platillos - máximo control
}

# === LIMITADOR BRICKWALL MULTIBANDA ===
# Umbrales por banda (dB) - cada banda tiene su propio techo de volumen
# Valores más negativos = más limitación = más seguro pero menos dinámico
MULTIBAND_LIMITER_DEFAULTS = {
    "Subbass (20-60 Hz)": -3.5,     # Graves profundos - más margen para evitar distorsión
    "Bass (60-250 Hz)": -2.5,       # Graves - balance con margen
    "Low-Mid (250-500 Hz)": -1.5,   # Cuerpo - moderado
    "Mid (500-2k Hz)": -1.5,        # Fundamental - algo más de control
    "High-Mid (2k-6k Hz)": -3.5,    # Presencia/sibilantes - más control
    "Air (6k-16k Hz)": -5.0,        # Brillantes - máximo margen para evitar harshness
}

# Tiempos de ataque y release para el limitador multibanda (ms)
MULTIBAND_LIMITER_ATTACK_MS = 0.5   # Ataque rápido para capturar transientes
MULTIBAND_LIMITER_RELEASE_MS = 50.0  # Release moderado para transparencia

# Límites máximos de saturación por banda (dB)
# Bajos: saturación controlada para evitar distorsión de bocinas
# Altos: muy conservador para evitar harshness
MAX_SATURATION_DRIVE_DB = {
    "Subbass (20-60 Hz)": 6.0,      # Subgraves - muy controlado (distorsión audible)
    "Bass (60-250 Hz)": 10.0,       # Graves - moderado (warmth sin distorsión)
    "Low-Mid (250-500 Hz)": 12.0,   # Cuerpo - algo de saturación para calidez
    "Mid (500-2k Hz)": 15.0,        # Vocales - moderado
    "High-Mid (2k-6k Hz)": 8.0,     # Sibilantes - conservador
    "Air (6k-16k Hz)": 4.0,         # Brillantes - muy conservador
}

BRICKWALL_EXTRA_DB = -0.5
TRANSPARENT_BAND_RANGE_DB = 2.0
DEFAULT_BAND_RANGE_DB = 3.0
TRANSPARENT_MAX_ADJUST_DB = 2.0
DEFAULT_MAX_ADJUST_DB = 4.0

# === MARGEN DE SEGURIDAD PARA TRUE PEAK ===
# FFmpeg no garantiza True Peak exacto debido a inter-sample peaks.
# Este margen se resta del target para garantizar el objetivo real.
# Ejemplo: Si el usuario pide -1.0 dBTP y el margen es 0.5, se procesa a -1.5 dBTP
# para garantizar que el resultado real sea ≤ -1.0 dBTP.
TRUE_PEAK_SAFETY_MARGIN_DB = 0.5  # dB extra de margen

# === CONFIGURACIÓN DE LOUDNORM (EBU R128) ===
# LRA (Loudness Range) controla el rango dinámico objetivo
# - Música: 7-11 LU (mayor dinámica para música)
# - Podcast/Diálogo: 5-7 LU (más consistente para voz)
# - Broadcast: 11-20 LU (estándar EBU R128)
LOUDNORM_LRA_DEFAULT = 11  # LU - Valor por defecto (EBU R128)
LOUDNORM_LRA_MUSIC = 11    # LU - Para música
LOUDNORM_LRA_PODCAST = 5   # LU - Para podcast/voz (más comprimido)
LOUDNORM_LRA_BROADCAST = 20  # LU - Para broadcast (máximo rango dinámico)

# Mínimo LUFS para considerar válido el análisis
# Audio con LUFS más bajo que esto se considera silencio
LUFS_MINIMUM_VALID = -70.0

LOUDNESS_PRESETS = {
    "Manual": None,
    "Spotify (-14 LUFS / -1.0 dBTP)": (-14.0, -1.0),
    "YouTube (-14 LUFS / -1.0 dBTP)": (-14.0, -1.0),
    "Apple Music (-16 LUFS / -1.0 dBTP)": (-16.0, -1.0),
    "Amazon Music (-14 LUFS / -1.0 dBTP)": (-14.0, -1.0),
    "Tidal (-14 LUFS / -1.0 dBTP)": (-14.0, -1.0),
    "Deezer (-14 LUFS / -1.0 dBTP)": (-14.0, -1.0),
    "SoundCloud (-14 LUFS / -1.0 dBTP)": (-14.0, -1.0),
    "Podcast (-16 LUFS / -1.0 dBTP)": (-16.0, -1.0),
    "Broadcast EBU R128 (-23 LUFS / -2.0 dBTP)": (-23.0, -2.0),
}

OUTPUT_PRESETS = {
    "Manual": None,
    "Studio Max (96 kHz / 24-bit)": (96000, "24"),
    "Hi-Res (48 kHz / 24-bit)": (48000, "24"),
    "Tidal (48 kHz / 24-bit)": (48000, "24"),
    "Apple Music (48 kHz / 24-bit)": (48000, "24"),
    "Spotify (44.1 kHz / 16-bit)": (44100, "16"),
    "YouTube Music (44.1 kHz / 16-bit)": (44100, "16"),
    "SoundCloud (44.1 kHz / 16-bit)": (44100, "16"),
}

INPUT_FORMATS = [".wav", ".aiff", ".aif", ".flac"]
OUTPUT_FORMATS = ["wav", "aiff", "flac", "m4a", "mp3"]
MP3_BITRATE = "320k"
M4A_BITRATE = "256k"

APP_NAME = "ToneFinish"
APP_VENDOR = "SABE software"

def _load_version() -> str:
    try:
        from pathlib import Path
        version_path = Path(__file__).resolve().parent / "VERSION"
        if version_path.exists():
            return version_path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return "0.0.0"

APP_VERSION = _load_version()

# === SISTEMA DE LICENCIAMIENTO ===
LICENSE_TYPE_FREE = "free"
LICENSE_TYPE_PREMIUM = "premium"

def _get_license_path():
    """Retorna la ruta al archivo de licencia"""
    try:
        from pathlib import Path
        config_dir = Path.home() / ".tonefinish"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "license.json"
    except Exception:
        return None

def _load_license_type() -> str:
    """Carga el tipo de licencia desde el archivo de configuración"""
    try:
        import json
        license_path = _get_license_path()
        if license_path and license_path.exists():
            data = json.loads(license_path.read_text(encoding="utf-8"))
            license_type = data.get("type", LICENSE_TYPE_FREE)
            if license_type in (LICENSE_TYPE_FREE, LICENSE_TYPE_PREMIUM):
                return license_type
    except Exception:
        pass
    return LICENSE_TYPE_FREE

def save_license_type(license_type: str) -> bool:
    """Guarda el tipo de licencia en el archivo de configuración"""
    try:
        import json
        license_path = _get_license_path()
        if license_path:
            data = {"type": license_type, "version": APP_VERSION}
            license_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
    except Exception:
        pass
    return False


def _get_resource_profile_path():
    """Retorna la ruta al archivo de perfil de recursos."""
    try:
        from pathlib import Path
        config_dir = Path.home() / ".tonefinish"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "resource_profile.json"
    except Exception:
        return None


def load_resource_profile_name() -> str | None:
    """Carga el perfil de recursos persistido para esta instalación."""
    try:
        import json

        profile_path = _get_resource_profile_path()
        if profile_path and profile_path.exists():
            data = json.loads(profile_path.read_text(encoding="utf-8"))
            profile_name = data.get("profile_name")
            if isinstance(profile_name, str) and profile_name.strip():
                return profile_name.strip()
    except Exception:
        pass
    return None


def save_resource_profile_name(profile_name: str) -> bool:
    """Guarda el perfil de recursos persistido para esta instalación."""
    try:
        import json

        profile_path = _get_resource_profile_path()
        if profile_path:
            data = {"profile_name": profile_name, "version": APP_VERSION}
            profile_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
    except Exception:
        pass
    return False


def clear_resource_profile_name() -> bool:
    """Elimina el perfil de recursos persistido."""
    try:
        profile_path = _get_resource_profile_path()
        if profile_path and profile_path.exists():
            profile_path.unlink()
            return True
    except Exception:
        pass
    return False

LICENSE_TYPE = _load_license_type()

def is_premium() -> bool:
    """Verifica si la licencia actual es Premium"""
    return LICENSE_TYPE == LICENSE_TYPE_PREMIUM

def get_license_display_name() -> str:
    """Retorna el nombre de visualización de la licencia"""
    return "ToneFinish Premium" if is_premium() else "ToneFinish Free"

def _logo_path() -> str:
    try:
        from pathlib import Path
        local = Path(__file__).resolve().parent / "assets" / "tonefinish.svg"
        if local.exists():
            return str(local)
        system = Path("/usr/share/icons/hicolor/scalable/apps/tonefinish.svg")
        if system.exists():
            return str(system)
    except Exception:
        pass
    return "assets/tonefinish.svg"

LOGO_PATH = _logo_path()


# ── API Keys persistence ──

def _get_api_keys_path():
    try:
        from pathlib import Path
        d = Path.home() / ".tonefinish"
        d.mkdir(parents=True, exist_ok=True)
        return d / "api_keys.json"
    except Exception:
        return None


def load_api_keys() -> dict:
    try:
        import json
        p = _get_api_keys_path()
        if p and p.exists():
            return json.loads(p.read_text("utf-8"))
    except Exception:
        pass
    return {}


def save_api_keys(keys: dict) -> bool:
    try:
        import json
        p = _get_api_keys_path()
        if p:
            p.write_text(json.dumps(keys, indent=2), "utf-8")
            return True
    except Exception:
        pass
    return False
