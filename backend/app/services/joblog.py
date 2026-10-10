"""Per-video job log: outputs/logs/{video_id}.log.

The video graph sets `current_job` while a node runs; JobLogHandler then copies every log record
from the back end (LLM retries, TTS, render) into that video's file. `write()` adds raw lines such
as Remotion's output, which are too noisy for the console.
"""
from __future__ import annotations

import logging
import threading
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

from ..config import settings

LOG_DIR = settings.outputs_dir / "logs"
current_job: ContextVar[str | None] = ContextVar("current_job", default=None)
_lock = threading.Lock()


def log_path(video_id: str) -> Path:
    return LOG_DIR / f"{video_id}.log"


def write(line: str, video_id: str | None = None) -> None:
    video_id = video_id or current_job.get()
    if not video_id:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _lock, log_path(video_id).open("a", encoding="utf-8") as f:
        for part in line.rstrip().splitlines() or [""]:
            f.write(f"{stamp} {part}\n")


def start(video_id: str, title: str) -> None:
    """Begin a new run section in the log (old runs stay above it)."""
    write(f"===== {title} =====", video_id)


def read(video_id: str, max_lines: int = 400) -> list[str]:
    path = log_path(video_id)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-max_lines:]


class JobLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if not current_job.get():
            return
        try:
            msg = f"{record.levelname} {record.name}: {record.getMessage()}"
            if record.exc_info:
                msg += "\n" + logging.Formatter().formatException(record.exc_info)
            write(msg)
        except Exception:  # never let logging break a job
            self.handleError(record)


def install() -> None:
    root = logging.getLogger()
    if not any(isinstance(h, JobLogHandler) for h in root.handlers):
        root.addHandler(JobLogHandler(level=logging.INFO))
