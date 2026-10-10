"""Text-to-speech interface. Engines: edge (free, default), silma (stub). Paid engines plug in here later."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol


class TTSError(RuntimeError):
    pass


@dataclass
class WordTiming:
    text: str
    start: float  # seconds
    end: float


@dataclass
class SynthesisResult:
    audio_path: Path
    words: list[WordTiming] = field(default_factory=list)
    duration: float = 0.0

    def words_json(self) -> list[dict]:
        return [asdict(w) for w in self.words]


class TTSEngine(Protocol):
    name: str

    def synthesize(self, text: str, voice: str, rate: str, out_path: Path) -> SynthesisResult:
        """Write MP3 audio to out_path and return per-word timings in seconds."""
        ...


def get_engine(name: str) -> TTSEngine:
    if name == "edge":
        from .edge import EdgeTTS

        return EdgeTTS()
    if name == "silma":
        from .silma import SilmaTTS

        return SilmaTTS()
    raise TTSError(f"Unknown voice engine '{name}'")
