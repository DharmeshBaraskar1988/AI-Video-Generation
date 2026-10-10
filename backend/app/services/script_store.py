"""Read and write scripts: outputs/scripts/{video_id}.json plus the Script table."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session

from ..config import settings
from ..db import Script, engine


def script_path(video_id: str):
    return settings.outputs_dir / "scripts" / f"{video_id}.json"


def save_script(content: dict[str, Any]) -> None:
    video_id = content["video_id"]
    script_path(video_id).write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    with Session(engine) as s:
        row = s.get(Script, video_id) or Script(video_id=video_id, quarter=content["quarter"])
        row.quarter = content["quarter"]
        row.status = content["status"]
        row.target_seconds = content["target_seconds"]
        row.content = content
        row.updated_at = datetime.now(timezone.utc)
        s.add(row)
        s.commit()


def load_script(video_id: str) -> dict[str, Any] | None:
    with Session(engine) as s:
        row = s.get(Script, video_id)
        return dict(row.content) if row else None
