from __future__ import annotations

import hashlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..config import settings
from ..db import QALog, Video, engine
from ..graphs.qa_graph import ask
from ..services.app_settings import get_setting, voice_rate
from ..services.llm import LLMError
from ..services.tts.base import TTSError, get_engine

router = APIRouter(prefix="/api/qa", tags=["qa"])


class Question(BaseModel):
    video_id: str
    question: str = Field(min_length=2, max_length=500)
    watch_lang: str = "en"  # language of the video on screen, for the timestamp


class SpeakBody(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    lang: str = "en"


@router.post("")
def post_question(q: Question) -> dict:
    with Session(engine) as s:
        if not s.get(Video, q.video_id):
            raise HTTPException(404, f"No video '{q.video_id}'")
    try:
        return ask(q.video_id, q.question, watch_lang=q.watch_lang)
    except LLMError as exc:
        raise HTTPException(503, f"The answer service is unavailable: {exc}") from exc


@router.post("/speak")
def speak(body: SpeakBody) -> dict:
    """Read an answer aloud with the current voice for that language (cached by text + voice)."""
    voice, rate = get_setting(f"voice_{body.lang}"), voice_rate(body.lang)
    key = hashlib.sha256(f"{voice}|{rate}|{body.text}".encode("utf-8")).hexdigest()[:20]
    out = settings.outputs_dir / "audio" / "qa" / f"{key}.mp3"
    if not out.exists():
        try:
            get_engine(get_setting("voice_engine")).synthesize(body.text, voice, rate, out)
        except TTSError as exc:
            raise HTTPException(503, str(exc)) from exc
    return {"audio": out.relative_to(settings.outputs_dir).as_posix(), "voice": voice}


@router.get("/log")
def qa_log(video_id: str | None = None, limit: int = 50) -> list[QALog]:
    with Session(engine) as s:
        stmt = select(QALog).order_by(QALog.created_at.desc()).limit(limit)
        if video_id:
            stmt = stmt.where(QALog.video_id == video_id)
        return list(s.exec(stmt).all())
