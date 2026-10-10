"""Admin settings: values in the SQLite Setting table override the .env defaults."""
from __future__ import annotations

from typing import Any

from sqlmodel import Session

from ..config import settings
from ..db import Setting, engine

DEFAULTS: dict[str, Any] = {
    "voice_engine": settings.tts_engine,
    "voice_en": settings.voice_en,
    "voice_ar": settings.voice_ar,
    "voice_rate": settings.voice_rate,
    "voice_rate_en": settings.voice_rate,
    "voice_rate_ar": settings.voice_rate,
    "music_track": settings.music_track.name,
    "music_volume": settings.music_volume,
    "target_seconds": settings.video_target_seconds,
    "languages": ["en", "ar"],
    "captions": True,
    "social_cut": True,
    "require_review": True,
    "require_audio_review": True,  # pause after narration to listen before rendering
    "enforce_length": False,  # when on, block approval/rendering outside 2-3 minutes
    "llm_model": settings.gemini_model,
    "arabic_digits": "western",
}


def get_setting(key: str) -> Any:
    with Session(engine) as s:
        row = s.get(Setting, key)
    return row.value if row is not None else DEFAULTS.get(key)


def all_settings() -> dict[str, Any]:
    return {key: get_setting(key) for key in DEFAULTS}


def voice_rate(lang: str) -> str:
    """Speaking speed for one language, e.g. '+10%'; falls back to the shared voice_rate."""
    return get_setting(f"voice_rate_{lang}") or get_setting("voice_rate") or "+0%"


def save_settings(values: dict[str, Any]) -> dict[str, Any]:
    """Store changed settings (only known keys). Values survive restarts (SQLite)."""
    from datetime import datetime, timezone

    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise KeyError(f"Unknown settings: {sorted(unknown)}")
    with Session(engine) as s:
        for key, value in values.items():
            row = s.get(Setting, key) or Setting(key=key)
            row.value = value
            row.updated_at = datetime.now(timezone.utc)
            s.add(row)
        s.commit()
    return all_settings()
