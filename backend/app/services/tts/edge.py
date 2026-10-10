"""edge-tts engine (free Microsoft neural voices) with per-word timings."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import edge_tts
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from .. import jobcontrol
from . import mp3
from .base import SynthesisResult, TTSError, WordTiming

log = logging.getLogger(__name__)
TICKS_PER_SECOND = 10_000_000  # edge-tts offsets are in 100 ns units


class EdgeTTS:
    name = "edge"

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=20),
        stop=stop_after_attempt(4),
        before_sleep=before_sleep_log(log, logging.WARNING),
        sleep=jobcontrol.sleep,
        reraise=True,
    )
    def synthesize(self, text: str, voice: str, rate: str, out_path: Path) -> SynthesisResult:
        audio, words = asyncio.run(self._stream(text, voice, rate))
        if not audio:
            raise TTSError(f"edge-tts returned no audio for voice {voice}")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio)
        return SynthesisResult(audio_path=out_path, words=words, duration=mp3.duration(audio))

    @staticmethod
    async def _stream(text: str, voice: str, rate: str) -> tuple[bytes, list[WordTiming]]:
        # edge-tts 7 defaults to sentence boundaries; word boundaries must be requested.
        communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
        chunks: list[bytes] = []
        words: list[WordTiming] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS_PER_SECOND
                words.append(WordTiming(chunk["text"], round(start, 3), round(start + chunk["duration"] / TICKS_PER_SECOND, 3)))
        return b"".join(chunks), words


async def list_voices() -> list[dict]:
    return await edge_tts.list_voices()
