"""Admin settings: voices, music, video options, review switch, model, Arabic digits,
custom voices (consent required) and NotebookLM video import."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session

from ..config import settings
from ..db import Video, engine
from ..services import quarters as quarters_svc
from ..services import render
from ..services.app_settings import DEFAULTS, all_settings, save_settings
from ..services.tts.base import TTSError, get_engine

router = APIRouter(tags=["settings"])

RATE_RE = re.compile(r"^[+-]\d{1,2}%$")
_voices_cache: dict[str, object] = {}
_models_cache: dict[str, object] = {}


class SettingsUpdate(BaseModel):
    """Every field optional: only the ones sent are changed."""
    voice_engine: Literal["edge", "silma"] | None = None
    voice_en: str | None = None
    voice_ar: str | None = None
    voice_rate: str | None = None
    voice_rate_en: str | None = None
    voice_rate_ar: str | None = None
    music_track: str | None = None
    music_volume: float | None = Field(default=None, ge=0, le=1)
    target_seconds: int | None = Field(default=None, ge=120, le=180)
    languages: list[Literal["en", "ar"]] | None = None
    captions: bool | None = None
    social_cut: bool | None = None
    require_review: bool | None = None
    enforce_length: bool | None = None
    require_audio_review: bool | None = None
    llm_model: str | None = None
    arabic_digits: Literal["western", "eastern"] | None = None
    presenter: Literal["auto", "male", "female", "off"] | None = None

    @field_validator("voice_rate", "voice_rate_en", "voice_rate_ar")
    @classmethod
    def _rate(cls, v: str | None) -> str | None:
        if v is not None and not RATE_RE.match(v):
            raise ValueError("speed must look like +10% or -5%")
        return v

    @field_validator("languages")
    @classmethod
    def _langs(cls, v: list[str] | None) -> list[str] | None:
        if v is not None and not v:
            raise ValueError("choose at least one language")
        return v


def _music_tracks() -> list[dict]:
    tracks = []
    for p in sorted(settings.music_dir.glob("*.mp3")):
        tracks.append({"file": p.name, "credit": render.music_credit(p), "size_kb": round(p.stat().st_size / 1024)})
    return tracks


@router.get("/api/settings")
def get_settings() -> dict:
    return {"values": all_settings(), "defaults": DEFAULTS, "music_tracks": _music_tracks(),
            "custom_voices": list_custom_voices()}


@router.put("/api/settings")
def put_settings(body: SettingsUpdate) -> dict:
    values = body.model_dump(exclude_none=True)
    if "music_track" in values and not (settings.music_dir / Path(values["music_track"]).name).exists():
        raise HTTPException(400, f"No music file {values['music_track']} in data/music")
    if values.get("voice_engine") == "silma":
        raise HTTPException(400, "The SILMA engine is not installed in this POC; keep 'edge'.")
    return {"values": save_settings(values)}


# ---------- voices ----------

@router.get("/api/settings/voices")
def voices() -> dict:
    """edge-tts neural voices for English (en-*) and Arabic (ar-*), cached for an hour."""
    if not _voices_cache or time.time() - float(_voices_cache["at"]) > 3600:
        from ..services.tts.edge import list_voices

        try:
            raw = asyncio.run(list_voices())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, f"Could not list voices: {exc}") from exc
        out: dict[str, list] = {"en": [], "ar": []}
        for v in raw:
            locale = v.get("Locale", "")
            lang = locale.split("-")[0]
            if lang in out:
                out[lang].append({"name": v["ShortName"], "locale": locale, "gender": v.get("Gender"),
                                  "label": f"{v['ShortName'].split('-')[-1].replace('Neural', '')} ({locale}, {v.get('Gender', '').lower()})"})
        for lang in out:
            out[lang].sort(key=lambda x: (x["locale"] != ("en-US" if lang == "en" else "ar-QA"), x["locale"], x["name"]))
        _voices_cache.update(at=time.time(), data=out)
    return _voices_cache["data"]  # type: ignore[return-value]


class PreviewBody(BaseModel):
    voice: str
    lang: Literal["en", "ar"]
    rate: str = "+0%"

    @field_validator("rate")
    @classmethod
    def _rate(cls, v: str) -> str:
        if not RATE_RE.match(v):
            raise ValueError("speed must look like +10% or -5%")
        return v


PREVIEW_TEXT = {
    "en": "In the second quarter, revenue came to QR 1.7 billion, and the company recorded a net loss of QR 518 million.",
    "ar": "في الربع الثاني بلغت الإيرادات 1.7 مليار ريال قطري، وسجّلت الشركة صافي خسارة بقيمة 518 مليون ريال قطري.",
}


@router.post("/api/settings/voices/preview")
def preview(body: PreviewBody) -> dict:
    key = hashlib.sha256(f"{body.voice}|{body.rate}|{body.lang}".encode()).hexdigest()[:16]
    out = settings.outputs_dir / "voice_test" / f"preview_{key}.mp3"
    if not out.exists():
        try:
            get_engine("edge").synthesize(PREVIEW_TEXT[body.lang], body.voice, body.rate, out)
        except (TTSError, Exception) as exc:  # noqa: BLE001
            raise HTTPException(400, f"Preview failed for {body.voice}: {exc}") from exc
    return {"audio": out.relative_to(settings.outputs_dir).as_posix()}


# ---------- model ----------

@router.get("/api/settings/models")
def models() -> dict:
    from ..services.llm import _EXHAUSTED, list_models

    if not _models_cache or time.time() - float(_models_cache["at"]) > 3600:
        try:
            _models_cache.update(at=time.time(), data=list_models())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, f"Could not list Gemini models: {exc}") from exc
    now = time.time()
    return {
        "models": _models_cache["data"],
        "fallbacks": settings.gemini_fallback_models,
        "exhausted": {m: round((t - now) / 3600, 1) for m, t in _EXHAUSTED.items() if t > now},
    }


# ---------- music ----------

def _safe_name(name: str, suffix: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem).strip("_").lower() or "file"
    return f"{stem[:60]}{suffix}"


def _probe(path: Path) -> dict:
    out = subprocess.run(
        [render.find_ffmpeg("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type:format=duration,format_name",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise HTTPException(400, "The file could not be read as media")
    return json.loads(out.stdout)


@router.post("/api/settings/music")
async def upload_music(
    file: UploadFile = File(...),
    title: str = Form(...),
    licence: str = Form(..., min_length=3),
    source_url: str = Form(""),
    credit: str = Form(""),
) -> dict:
    """Add a music track. A licence is required; CC BY tracks need a credit line (shown in the video)."""
    if not (file.filename or "").lower().endswith(".mp3"):
        raise HTTPException(400, "Upload an MP3 file")
    name = _safe_name(file.filename or title, ".mp3")
    dest = settings.music_dir / name
    if dest.exists():
        raise HTTPException(409, f"{name} already exists")
    tmp = dest.with_suffix(".upload")
    with tmp.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    info = _probe(tmp)
    if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, "No audio found in the file")
    tmp.rename(dest)
    block = [f"file: {name}", f"title: {title}", f"source: {source_url or 'uploaded in Admin'}", f"licence: {licence}"]
    if credit.strip():
        block.append(f"credit: {credit.strip()}")
    block.append(f"downloaded: {datetime.now(timezone.utc).date().isoformat()}")
    lic = settings.music_dir / "LICENSES.txt"
    with lic.open("a", encoding="utf-8") as fh:
        fh.write("\n\n" + "\n".join(block) + "\n")
    return {"file": name, "duration": float(info["format"]["duration"]), "music_tracks": _music_tracks()}


# ---------- custom voices (stretch: SILMA) ----------

VOICES_DIR = settings.data_dir / "voices"
CONSENT_TEXT = (
    "I confirm that the person whose voice is in this recording has given explicit consent for it to be used "
    "to create a synthetic voice for D-Storify videos, and that the recording is not copied from YouTube or "
    "anyone else's recordings."
)


def list_custom_voices() -> list[dict]:
    out = []
    for consent in sorted(VOICES_DIR.glob("*/consent.json")):
        data = json.loads(consent.read_text(encoding="utf-8"))
        out.append({k: data[k] for k in ("id", "name", "speaker", "language", "created_at")} | {"engine_ready": False})
    return out


@router.post("/api/settings/custom-voices")
async def add_custom_voice(
    name: str = Form(..., min_length=2, max_length=60),
    speaker: str = Form(..., min_length=2, max_length=80),
    language: Literal["en", "ar"] = Form("ar"),
    consent: bool = Form(False),
    clip: UploadFile = File(...),
) -> dict:
    if not consent:
        raise HTTPException(400, "Consent is required: confirm the speaker agreed to this use of their voice.")
    suffix = Path(clip.filename or "").suffix.lower()
    if suffix not in (".wav", ".mp3", ".m4a"):
        raise HTTPException(400, "Upload the reference clip as WAV, MP3 or M4A")
    vid = _safe_name(name, "")
    folder = VOICES_DIR / vid
    if folder.exists():
        raise HTTPException(409, f"A custom voice named {vid} already exists")
    folder.mkdir(parents=True)
    path = folder / f"reference{suffix}"
    with path.open("wb") as fh:
        shutil.copyfileobj(clip.file, fh)
    info = _probe(path)
    duration = float(info.get("format", {}).get("duration", 0))
    if duration < 5:
        shutil.rmtree(folder)
        raise HTTPException(400, "The reference clip should be at least 5 seconds of clear speech")
    (folder / "consent.json").write_text(json.dumps({
        "id": vid, "name": name, "speaker": speaker, "language": language, "clip": path.name,
        "clip_seconds": round(duration, 1), "consent": True, "consent_text": CONSENT_TEXT,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"custom_voices": list_custom_voices(),
            "note": "Saved with consent. Synthesis needs the SILMA engine, which is not installed in this POC."}


# ---------- NotebookLM import ----------

@router.post("/api/quarters/{company}/{period}/notebooklm")
async def import_notebooklm(company: str, period: str, file: UploadFile = File(...)) -> dict:
    """Attach an MP4 made in NotebookLM to a quarter as an alternative video (NotebookLM has no API)."""
    found = quarters_svc.get_quarter(company, period)
    if not found:
        raise HTTPException(404, f"No quarter '{period}' for company '{company}'")
    qf, q = found
    if not (file.filename or "").lower().endswith(".mp4"):
        raise HTTPException(400, "Upload an MP4 file exported from NotebookLM")
    video_id = f"{qf.slug}-{quarters_svc.period_slug(q.period)}"
    dest = render.VIDEOS_DIR / f"{video_id}_notebooklm.mp4"
    tmp = dest.with_suffix(".upload")
    render.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    with tmp.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    info = _probe(tmp)
    if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, "No video stream found in the file")
    tmp.replace(dest)
    duration = round(float(info["format"]["duration"]), 3)
    poster = dest.with_suffix(".jpg")
    render.make_poster(dest, min(5.0, duration / 2), poster)
    entry = {"video": render.rel(dest), "poster": render.rel(poster), "duration": duration,
             "original_name": file.filename, "uploaded_at": datetime.now(timezone.utc).isoformat()}
    with Session(engine) as s:
        video = s.get(Video, video_id) or Video(id=video_id, company=qf.slug, period=q.period, status="imported")
        files = dict(video.files or {})
        files["notebooklm"] = entry
        video.files = files
        video.updated_at = datetime.now(timezone.utc)
        s.add(video)
        s.commit()
    return {"video_id": video_id, "notebooklm": entry}
