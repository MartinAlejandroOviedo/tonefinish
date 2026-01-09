BAND_CONFIG = [
    ("Subbass (20-60 Hz)", 20, 60, 0.06, 0.40, 0.0),
    ("Bass (60-250 Hz)", 60, 250, 0.04, 0.30, 0.4),
    ("Low-Mid (250-500 Hz)", 250, 500, 0.03, 0.20, 0.7),
    ("Mid (500-2k Hz)", 500, 2000, 0.02, 0.15, 1.0),
    ("High-Mid (2k-6k Hz)", 2000, 6000, 0.01, 0.12, 1.2),
    ("Air (6k-16k Hz)", 6000, 16000, 0.005, 0.08, 1.4),
]

VOICE_BAND = ("Voz (300-3k Hz)", 300, 3000)

BRICKWALL_EXTRA_DB = -0.5
TRANSPARENT_BAND_RANGE_DB = 2.0
DEFAULT_BAND_RANGE_DB = 3.0
TRANSPARENT_MAX_ADJUST_DB = 2.0
DEFAULT_MAX_ADJUST_DB = 4.0

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
