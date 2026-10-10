"""Settings loaded from the repo-root .env. Relative paths resolve against the repo root."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


def _sqlite_url(url: str) -> str:
    prefix = "sqlite:///"
    if url.startswith(prefix):
        db_path = _path(url[len(prefix):])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return prefix + db_path.as_posix()
    return url


class Settings:
    # Language model: "gemini" (free tier) or "openai". In gemini mode OpenAI is used automatically
    # once every Gemini model has run out of its daily quota (if OPENAI_API_KEY is set).
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "")
    gemini_max_rpm: int = int(os.getenv("GEMINI_MAX_RPM", "8"))
    # Used in order when a model's free daily quota runs out (each model has its own quota)
    gemini_fallback_models: list[str] = [
        m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()
    ]

    # Embeddings
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
    chroma_dir: Path = _path(os.getenv("CHROMA_DIR", "backend/app/store/chroma"))

    # Voice
    tts_engine: str = os.getenv("TTS_ENGINE", "edge")
    voice_en: str = os.getenv("VOICE_EN", "en-US-GuyNeural")
    voice_ar: str = os.getenv("VOICE_AR", "ar-QA-MoazNeural")
    voice_rate: str = os.getenv("VOICE_RATE", "+0%")

    # Video
    video_target_seconds: int = int(os.getenv("VIDEO_TARGET_SECONDS", "150"))
    music_track: Path = _path(os.getenv("MUSIC_TRACK", "data/music/calm_corporate.mp3"))
    music_volume: float = float(os.getenv("MUSIC_VOLUME", "0.12"))

    # Stock data
    stock_source: str = os.getenv("STOCK_SOURCE", "yfinance")
    oanor_api_key: str = os.getenv("OANOR_API_KEY", "")
    stock_cache_seconds: int = int(os.getenv("STOCK_CACHE_SECONDS", "60"))

    # App
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    database_url: str = _sqlite_url(os.getenv("DATABASE_URL", "sqlite:///backend/app/store/dstorify.db"))

    # Folders
    data_dir: Path = ROOT / "data"
    quarters_dir: Path = ROOT / "data" / "quarters"
    documents_dir: Path = ROOT / "data" / "documents"
    brand_dir: Path = ROOT / "data" / "brand"
    music_dir: Path = ROOT / "data" / "music"
    outputs_dir: Path = ROOT / "outputs"
    video_dir: Path = ROOT / "video"
    prompts_dir: Path = Path(__file__).resolve().parent / "prompts"
    store_dir: Path = Path(__file__).resolve().parent / "store"


settings = Settings()

settings.store_dir.mkdir(parents=True, exist_ok=True)
for _d in ("audio", "videos", "scripts", "voice_test"):
    (settings.outputs_dir / _d).mkdir(parents=True, exist_ok=True)
