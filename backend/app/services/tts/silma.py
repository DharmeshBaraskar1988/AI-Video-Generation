"""SILMA TTS (open Arabic voice model, optional custom voice). Not installed in the POC."""
from __future__ import annotations

from pathlib import Path

from .base import SynthesisResult, TTSError


class SilmaTTS:
    name = "silma"

    def synthesize(self, text: str, voice: str, rate: str, out_path: Path) -> SynthesisResult:
        raise TTSError(
            "SILMA voice engine is not installed. Switch the voice engine to 'edge' in Admin, "
            "or install SILMA TTS and implement this engine (custom voices need a consent record)."
        )
