"""FastAPI entry point: uvicorn backend.app.main:app --reload --port 8000 (run from repo root)."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import documents, qa, quarters, scripts, settings as settings_api, stock, videos
from .config import settings
from .db import init_db
from .services import joblog

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
joblog.install()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="D-Storify POC", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/outputs", StaticFiles(directory=settings.outputs_dir), name="outputs")
# source PDFs, so citations can open the cited page (/files/documents/x.pdf#page=4)
app.mount("/files/documents", StaticFiles(directory=settings.documents_dir), name="documents")
app.mount("/files/music", StaticFiles(directory=settings.music_dir), name="music")

app.include_router(quarters.router)
app.include_router(scripts.router)
app.include_router(videos.router)
app.include_router(documents.router)
app.include_router(qa.router)
app.include_router(stock.router)
app.include_router(settings_api.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_model": (settings.openai_model if settings.llm_provider == "openai" else settings.gemini_model) or None,
        "llm_key_set": bool(settings.openai_api_key if settings.llm_provider == "openai" else settings.gemini_api_key),
        "tts_engine": settings.tts_engine,
    }


@app.get("/api/brand")
def brand() -> dict:
    return json.loads((settings.brand_dir / "brand.json").read_text(encoding="utf-8"))
