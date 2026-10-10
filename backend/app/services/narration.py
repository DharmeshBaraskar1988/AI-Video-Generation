"""Narrate an approved script: one MP3 per language plus a word-timing JSON.

Each scene is synthesised separately, then the clips are joined with a short silence
between scenes. Word offsets are shifted onto the joined timeline, and each scene's
start/end comes from its first/last word.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from ..config import settings
from . import factcheck as fc
from . import jobcontrol
from .app_settings import get_setting, voice_rate
from .tts import mp3
from .tts.base import TTSError, get_engine

log = logging.getLogger(__name__)

PAUSE_SECONDS = 0.6


def audio_paths(video_id: str, lang: str) -> tuple[Path, Path]:
    audio_dir = settings.outputs_dir / "audio"
    return audio_dir / f"{video_id}_{lang}.mp3", audio_dir / f"{video_id}_{lang}_words.json"


def check_timings(words: list[dict[str, Any]], duration: float) -> list[str]:
    issues = []
    for prev, cur in zip(words, words[1:]):
        if cur["start"] < prev["start"] or cur["start"] < prev["end"] - 0.05:
            issues.append(f"word '{cur['text']}' at {cur['start']}s starts before '{prev['text']}' ends")
    if any(w["end"] < w["start"] for w in words):
        issues.append("a word ends before it starts")
    if words and abs(duration - words[-1]["end"]) > 1.0:
        issues.append(f"last word ends at {words[-1]['end']}s but audio is {duration:.2f}s long")
    if not words:
        issues.append("no word timings returned")
    return issues


def narrate(
    video_id: str, lang: str, scenes: list[dict[str, Any]], placeholders: dict[str, Any], rate: str | None = None
) -> dict[str, Any]:
    """`rate` overrides the admin speaking speed (used to fit a narration under the 3-minute maximum)."""
    engine_name = get_setting("voice_engine")
    engine = get_engine(engine_name)
    voice = get_setting(f"voice_{lang}")
    rate = rate or voice_rate(lang)
    digits = get_setting("arabic_digits")

    out_mp3, out_words = audio_paths(video_id, lang)
    tmp = out_mp3.parent / f"tmp_{video_id}_{lang}"
    tmp.mkdir(parents=True, exist_ok=True)

    parts: list[bytes] = []
    words: list[dict[str, Any]] = []
    scene_times: list[dict[str, Any]] = []
    cursor = 0.0
    template: mp3.FrameHeader | None = None

    try:
        for idx, scene in enumerate(scenes):
            jobcontrol.check()
            text = fc.fill(scene[lang], placeholders, lang, digits)
            result = engine.synthesize(text, voice, rate, tmp / f"{scene['id']}.mp3")
            clip = mp3.strip_to_frames(result.audio_path.read_bytes())
            header = mp3.first_header(clip)
            if template is None:
                template = header
            elif header.format_key != template.format_key:
                raise TTSError(f"Scene {scene['id']} audio format differs from the first scene; cannot join")

            if idx > 0:
                pause = mp3.silence(template, PAUSE_SECONDS)
                parts.append(pause)
                cursor += mp3.duration(pause)

            clip_seconds = mp3.duration(clip)
            scene_words = [
                {"text": w.text, "start": round(cursor + w.start, 3), "end": round(cursor + w.end, 3), "scene": scene["id"]}
                for w in result.words
            ]
            scene_times.append(
                {
                    "id": scene["id"],
                    "type": scene["type"],
                    "start": scene_words[0]["start"] if scene_words else round(cursor, 3),
                    "end": scene_words[-1]["end"] if scene_words else round(cursor + clip_seconds, 3),
                    "audio_start": round(cursor, 3),
                    "audio_end": round(cursor + clip_seconds, 3),
                    "text": text,
                }
            )
            words.extend(scene_words)
            parts.append(clip)
            cursor += clip_seconds
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    audio = b"".join(parts)
    out_mp3.write_bytes(audio)
    duration = round(mp3.duration(audio), 3)
    issues = check_timings(words, duration)
    length_ok = fc.MIN_VIDEO_SECONDS <= duration <= fc.MAX_VIDEO_SECONDS
    if not length_ok:
        log.warning(
            "Narration for %s %s is %.0fs, outside %s-%ss", video_id, lang, duration, fc.MIN_VIDEO_SECONDS, fc.MAX_VIDEO_SECONDS
        )
    if issues:
        log.warning("Word timing issues for %s %s: %s", video_id, lang, issues)

    data = {
        "video_id": video_id,
        "language": lang,
        "engine": engine_name,
        "voice": voice,
        "rate": rate,
        "duration": duration,
        "pause_seconds": PAUSE_SECONDS,
        "scenes": scene_times,
        "words": words,
        "checks": {"ok": not issues, "issues": issues, "length_ok": length_ok},
    }
    out_words.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    rel = lambda p: p.relative_to(settings.outputs_dir).as_posix()  # noqa: E731
    return {
        "audio": rel(out_mp3),
        "words": rel(out_words),
        "duration": duration,
        "voice": voice,
        "engine": engine_name,
        "rate": rate,
        "timings_ok": not issues,
        "length_ok": length_ok,
    }
