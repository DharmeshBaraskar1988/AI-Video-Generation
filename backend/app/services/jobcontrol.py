"""Stop and restart video jobs.

Each job runs in one background thread per video. A stop is cooperative: the video graph checks it
before every step, and long waits (LLM rate limit / retry back-off, TTS per scene, the Remotion
process) check it too, so a stop takes effect within a second or two. The only thing that cannot be
cut short is an LLM request already in flight; the stop lands as soon as it returns.

The step that was stopped has no checkpoint write, so resuming re-runs exactly that step.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from . import joblog

_lock = threading.Lock()
_threads: dict[str, threading.Thread] = {}
_stops: dict[str, threading.Event] = {}


class JobStopped(Exception):
    """Raised inside a job when the user pressed Stop."""

    def __init__(self) -> None:
        super().__init__("Stopped by user")


class JobBusy(Exception):
    """A thread for this video is still alive (running, or finishing the step it was stopped in)."""


def is_active(video_id: str) -> bool:
    t = _threads.get(video_id)
    return bool(t and t.is_alive())


def stop_requested(video_id: str) -> bool:
    ev = _stops.get(video_id)
    return bool(ev and ev.is_set() and is_active(video_id))


def launch(video_id: str, target: Callable[..., Any], *args: Any) -> None:
    """Run `target(*args)` in a background thread with a fresh stop signal for this video."""
    with _lock:
        if is_active(video_id):
            raise JobBusy(f"A job for {video_id} is still running; stop it and wait for it to end first")
        _stops[video_id] = threading.Event()
        thread = threading.Thread(target=target, args=args, daemon=True, name=f"video-{video_id}")
        _threads[video_id] = thread
    thread.start()


def request_stop(video_id: str) -> bool:
    """Signal the job to stop. False when no thread is running for it (e.g. after a server restart)."""
    ev = _stops.get(video_id)
    if not ev or not is_active(video_id):
        return False
    ev.set()
    joblog.write("!! Stop requested by user", video_id)
    return True


def stop_event(video_id: str | None = None) -> threading.Event | None:
    video_id = video_id or joblog.current_job.get()
    return _stops.get(video_id) if video_id else None


def check(video_id: str | None = None) -> None:
    """Raise JobStopped if the current job (or `video_id`) was asked to stop. No-op outside a job."""
    ev = stop_event(video_id)
    if ev and ev.is_set():
        raise JobStopped()


def sleep(seconds: float) -> None:
    """time.sleep that wakes up early (and raises JobStopped) when the job is stopped."""
    ev = stop_event()
    if ev is None:
        time.sleep(seconds)
        return
    ev.wait(seconds)
    check()
