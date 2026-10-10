from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..config import settings
from ..db import Video, engine
from ..services import jobcontrol
from ..services.script_store import load_script
from .scripts import _video_view

router = APIRouter(prefix="/api/videos", tags=["videos"])
log = logging.getLogger(__name__)

# Steps whose results are the rendered video; reset when the video files are deleted.
RENDER_NODES = ("build_props", "render_en", "render_ar", "mix_audio", "index_script")


def _has_video(v: Video) -> bool:
    return any(k.startswith("video_") or k == "notebooklm" for k in (v.files or {}))


class PublishBody(BaseModel):
    published: bool


@router.get("")
def list_videos(published: bool | None = None) -> list[dict]:
    """Videos with at least one rendered language (newest first); `published` filters."""
    with Session(engine) as s:
        videos = s.exec(select(Video).order_by(Video.updated_at.desc())).all()
        return [
            _video_view(v) for v in videos
            if _has_video(v) and (published is None or bool(v.published) == published)
        ]


@router.get("/{video_id}")
def get_video(video_id: str) -> dict:
    with Session(engine) as s:
        video = s.get(Video, video_id)
        if not video:
            raise HTTPException(404, f"No video '{video_id}'")
        view = _video_view(video)
    script = load_script(video_id)
    return {
        "job": view,
        "script": {k: script[k] for k in ("video_id", "quarter", "company_name_en", "company_name_ar", "demo", "derived", "status")}
        if script else None,
    }


@router.post("/{video_id}/publish")
def publish(video_id: str, body: PublishBody) -> dict:
    """Publish or unpublish a finished video."""
    with Session(engine) as s:
        video = s.get(Video, video_id)
        if not video:
            raise HTTPException(404, f"No video '{video_id}'")
        if body.published and not _has_video(video):
            raise HTTPException(409, "There is no rendered video to publish yet")
        video.published = body.published
        video.published_at = datetime.now(timezone.utc) if body.published else None
        s.add(video)
        s.commit()
        return _video_view(video)


@router.delete("/{video_id}")
def delete_video(video_id: str) -> dict:
    """Delete the rendered videos (EN, AR, social cuts, posters, captions, NotebookLM import).
    The script and narration are kept, so the video can be rendered again."""
    with Session(engine) as s:
        video = s.get(Video, video_id)
        if not video:
            raise HTTPException(404, f"No video '{video_id}'")
        if jobcontrol.is_active(video_id):
            raise HTTPException(409, "This job is still running; stop it first, then delete the video")
        removed = 0
        videos_dir = settings.outputs_dir / "videos"
        for path in [*videos_dir.glob(f"{video_id}_*"), *videos_dir.glob(f"{video_id}.*")]:
            if path.is_file():
                path.unlink(missing_ok=True)
                removed += 1
        video.files = {k: v for k, v in (video.files or {}).items() if not (k.startswith("video_") or k == "notebooklm")}
        video.node_status = {k: v for k, v in (video.node_status or {}).items() if k not in RENDER_NODES}
        video.published = False
        video.published_at = None
        video.updated_at = datetime.now(timezone.utc)
        s.add(video)
        s.commit()
    log.info("Deleted rendered videos of %s (%d files)", video_id, removed)
    return {"video_id": video_id, "deleted": True, "files_removed": removed}
