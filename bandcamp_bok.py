"""
BoK: Bandcamp Body of Knowledge — Generador de textos para formularios Bandcamp.

Usa DeepSeek API (si hay key) o templates locales para generar:
- Título del álbum/track
- Tags / géneros
- Mensaje de lanzamiento (notificación a seguidores)
- Descripción / About
- Créditos
- Precio sugerido

Contexto esperado:
    {
        "artist": "O-M-A",
        "label": "Detected Records Argentina",
        "title": "Nombre del track",
        "suno_prompt": "synthwave, dark, 120bpm...",
        "lyrics": "Letra completa...",
        "notes": "Notas adicionales...",
        "analysis": {  # del auto-master
            "processing_profile": "Normal",
            "lra": 5.7,
            "crest_factor": 9.2,
            "lufs": -13.0,
        }
    }
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, Optional


# ── Templates por defecto ──

DEFAULT_CREDITS = """Artista: {artist}
Producido, mezclado y masterizado por Martin Alejandro Oviedo
en Detected Records Home Studio, Argentina.
Sello: {label}
Procesado con SABE Software / ToneFinish.
Arte de tapa generado con IA."""

DEFAULT_RELEASE_MSG = """Gracias por acompañarme en este viaje sonoro.
"{title}" es una pieza muy especial para mí.
Cada track fue creado con pasión y dedicación en mi home studio.
Espero que lo disfruten y lo compartan con quien crean que le pueda gustar."""

GENRE_KEYWORDS = [
    "synthwave", "techno", "house", "electronic", "ambient", "minimal",
    "dark", "melodic", "progressive", "deep", "acid", "rock", "pop",
    "jazz", "folk", "trap", "hip-hop", "industrial", "experimental",
    "lo-fi", "vaporwave", "EBM", "trance", "drum and bass", "breakbeat",
]

MOOD_KEYWORDS = [
    "dark", "light", "fire", "neon", "night", "dream", "love", "dance",
    "bass", "pulse", "wave", "heart", "shadow", "storm", "ice", "void",
]

PRICE_RANGES = {
    "album": (7.00, 12.00),
    "ep": (4.00, 7.00),
    "track": (1.00, 3.00),
}


class BandcampTexts:
    """Contenedor de todos los textos generados para Bandcamp."""

    def __init__(self) -> None:
        self.title: str = ""
        self.tags: str = ""
        self.release_msg: str = ""
        self.description: str = ""
        self.credits: str = ""
        self.price: float = 9.00
        self.catalog: str = "DR-001"
        self.release_date: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "tags": self.tags,
            "release_msg": self.release_msg,
            "description": self.description,
            "credits": self.credits,
            "price": "%.2f" % self.price,
            "catalog": self.catalog,
            "release_date": self.release_date,
        }


# ── API ──

NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


def _call_api(
    url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.8,
) -> Optional[str]:
    """Llama a una API compatible con OpenAI chat/completions."""
    data = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            return str(body["choices"][0]["message"]["content"]).strip()
    except Exception:
        return None


def call_deepseek(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.8,
) -> Optional[str]:
    """Llama a DeepSeek API. Retorna texto o None si falla."""
    if not api_key.startswith("sk-"):
        return None
    return _call_api(DEEPSEEK_API_URL, api_key, "deepseek-chat", system_prompt, user_prompt, max_tokens, temperature)


def call_nvidia(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.8,
) -> Optional[str]:
    """Llama a NVIDIA NIM API. Retorna texto o None si falla."""
    if not api_key.startswith("nvapi-"):
        return None
    return _call_api(NVIDIA_API_URL, api_key, "nvidia/llama-3.1-nemotron-70b-instruct", system_prompt, user_prompt, max_tokens, temperature)


def call_ai_multi(
    providers: list[dict],
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1024,
    temperature: float = 0.8,
) -> Optional[str]:
    """Prueba múltiples proveedores en orden. Retorna el primer resultado exitoso."""
    for p in providers:
        if not p.get("enabled", True):
            continue
        result = _call_api(
            p["url"], p["key"], p["model"],
            system_prompt, user_prompt, max_tokens, temperature
        )
        if result:
            return result
    return None


def build_providers(
    nvidia_key: str = "",
    nvidia_on: bool = False,
    deepseek_key: str = "",
    deepseek_on: bool = False,
    custom_url: str = "",
    custom_key: str = "",
    custom_model: str = "",
    custom_on: bool = False,
) -> list[dict]:
    """Construye lista de proveedores activos."""
    providers = []
    if nvidia_on and nvidia_key.startswith("nvapi-"):
        providers.append({"url": NVIDIA_API_URL, "key": nvidia_key, "model": "nvidia/llama-3.1-nemotron-70b-instruct", "enabled": True})
    if deepseek_on and deepseek_key.startswith("sk-"):
        providers.append({"url": DEEPSEEK_API_URL, "key": deepseek_key, "model": "deepseek-chat", "enabled": True})
    if custom_on and custom_key and custom_url:
        providers.append({"url": custom_url, "key": custom_key, "model": custom_model or "gpt-4o-mini", "enabled": True})
    return providers


# ── Generadores individuales ──

def generate_tags(context: Dict[str, Any], providers: list | None = None) -> str:
    """Genera tags desde el prompt SUNO o DeepSeek."""
    prompt = str(context.get("suno_prompt", "")).lower()
    if not prompt:
        return "electronic, experimental"

    # Local: extraer keywords del prompt
    tags = [kw for kw in GENRE_KEYWORDS if kw in prompt]
    if not tags:
        tags = ["electronic"]

    # DeepSeek
    if providers:
        ai = call_ai_multi(providers,
            "Eres un curador musical. Responde SOLO con 5-8 tags/generos separados por "
            "coma, en ingles. Basate en el prompt de creacion. Nada mas.",
            "Prompt: %s\nTags:" % prompt,
            max_tokens=100,
            temperature=0.5,
        )
        if ai:
            return ai

    return ", ".join(tags[:8])


def generate_description(context: Dict[str, Any], providers: list | None = None) -> str:
    """Genera la descripción/about para Bandcamp."""
    prompt = str(context.get("suno_prompt", ""))
    title = str(context.get("title", ""))
    artist = str(context.get("artist", "O-M-A"))
    label = str(context.get("label", "Detected Records Argentina"))
    lyrics = str(context.get("lyrics", ""))
    notes = str(context.get("notes", ""))

    if api_key and prompt:
        user = "Prompt SUNO: %s\nArtista: %s\nTitulo: %s\nSello: %s" % (
            prompt[:300], artist, title, label
        )
        if lyrics:
            user += "\nTiene letra original."
        if notes:
            user += "\nNotas: %s" % notes[:200]

        ai = call_ai_multi(providers,
            "Eres un artista escribiendo la descripcion de tu album/track para "
            "Bandcamp. Escribe en espanol, 1-2 parrafos. Menciona el genero, "
            "el proceso creativo, y la experiencia sonora. Estilo profesional pero cercano.",
            user + "\n\nEscribe la descripcion:",
            max_tokens=600,
        )
        if ai:
            return ai

    # Template fallback
    parts = []
    if prompt:
        parts.append("Creado con inteligencia artificial (SUNO).")
        parts.append('Prompt: "%s"' % prompt[:200])
    if lyrics:
        parts.append("Incluye letra original.")
    if notes:
        parts.append(notes[:300])
    if not parts:
        mood = [kw for kw in MOOD_KEYWORDS if kw in prompt.lower()]
        mood_word = mood[0] if mood else "sonoro"
        parts.append(
            "Una pieza electrónica que explora territorios %s. "
            "Producida íntegramente en Argentina por %s para %s." % (
                mood_word + "s", artist, label
            )
        )
    return "\n\n".join(parts)


def generate_release_msg(context: Dict[str, Any], providers: list | None = None) -> str:
    """Genera el mensaje de lanzamiento para seguidores."""
    title = str(context.get("title", ""))
    artist = str(context.get("artist", "O-M-A"))
    prompt = str(context.get("suno_prompt", ""))

    if api_key and title:
        ai = call_ai_multi(providers,
            "Eres un musico independiente. Escribe un mensaje corto y personal "
            "(max 800 caracteres) para tus seguidores de Bandcamp anunciando "
            "este lanzamiento. En espanol, calido y autentico.",
            "Artista: %s\nTrack: %s\nPrompt: %s\n\nMensaje:" % (
                artist, title, prompt[:200]
            ),
            max_tokens=400,
            temperature=0.9,
        )
        if ai:
            return ai[:1000]

    return DEFAULT_RELEASE_MSG.format(title=title)


def generate_credits(context: Dict[str, Any]) -> str:
    """Genera los créditos."""
    return DEFAULT_CREDITS.format(
        artist=str(context.get("artist", "O-M-A")),
        label=str(context.get("label", "Detected Records Argentina")),
    )


def suggest_price(context: Dict[str, Any]) -> float:
    """Sugiere precio según tipo de release."""
    analysis = context.get("analysis", {})
    lra = float(analysis.get("lra", 5.0)) if isinstance(analysis, dict) else 5.0
    lufs = float(analysis.get("lufs", -14.0)) if isinstance(analysis, dict) else -14.0

    # Track suelto
    if lufs > -12:
        return 1.50  # ya está fuerte, track individual
    elif lra > 8:
        return 2.00  # dinámico, más valor
    return 9.00  # default álbum


# ── Orquestador principal ──

def generate_all(context: Dict[str, Any], providers: list | None = None) -> BandcampTexts:
    """Genera todos los textos Bandcamp desde el contexto completo.

    Args:
        context: Dict con artist, label, title, suno_prompt, lyrics, notes, analysis
        api_key: DeepSeek API key (opcional, usa templates si no hay)

    Returns:
        BandcampTexts con todos los campos completos
    """
    texts = BandcampTexts()

    texts.title = str(context.get("title", ""))
    texts.tags = generate_tags(context, api_key)
    texts.description = generate_description(context, api_key)
    texts.release_msg = generate_release_msg(context, api_key)
    texts.credits = generate_credits(context)
    texts.price = suggest_price(context)

    return texts


def generate_lyrics(context: Dict[str, Any], providers: list | None = None) -> str:
    """Genera letra de canción desde el contexto."""
    title = str(context.get("title", ""))
    prompt = str(context.get("suno_prompt", ""))
    artist = str(context.get("artist", "O-M-A"))

    if api_key and prompt:
        ai = call_ai_multi(providers,
            "Eres un compositor de musica electronica. Escribe letras originales "
            "en espanol, estilo poetico y ritmico. Solo la letra, sin notas ni "
            "acotaciones. 2-3 estrofas + coro. Usa el prompt musical y el titulo.",
            "Prompt: %s\nTitulo: %s\nArtista: %s\n\nEscribe la letra:" % (
                prompt, title or "sin titulo", artist
            ),
            max_tokens=800,
            temperature=0.9,
        )
        if ai:
            return ai

    # Template fallback
    keywords = [kw for kw in MOOD_KEYWORDS if kw in prompt.lower()]
    if not keywords:
        keywords = ["dream", "light", "fire"]

    verses = [
        "En la %s de la %s" % (keywords[0], keywords[-1]),
        "donde el %s se vuelve verdad" % keywords[0],
        "",
        "Bajo el %s electrico" % keywords[0],
        "tu %s me hace vibrar" % (keywords[1] if len(keywords) > 1 else "voz"),
        "",
    ]
    if len(keywords) > 2:
        verses += [
            "Como un %s en la oscuridad" % keywords[2],
            "que nunca deja de brillar",
            "",
        ]
    verses += [
        "(Coro)",
        title or "Sin titulo",
        "somos %s en la ciudad" % keywords[0],
        "",
        "El ritmo no para",
        "el %s nos lleva" % keywords[-1],
        "hasta el amanecer",
    ]
    return "\n".join(verses)
