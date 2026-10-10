"""Minimal MP3 frame tools (no FFmpeg): exact duration, silent frames, joining clips.

edge-tts returns constant-bitrate MPEG audio without tags, so clips with the same format
can be joined frame by frame. A frame whose side info and main data are all zero decodes
to silence, which gives exact pauses between scenes.
"""
from __future__ import annotations

from dataclasses import dataclass

# bitrate tables (kbps), index 1..14
_BITRATES = {
    (1, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],  # MPEG-1 Layer III
    (2, 3): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],      # MPEG-2/2.5 Layer III
}
_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}  # by version bits


@dataclass(frozen=True)
class FrameHeader:
    raw: bytes
    version_bits: int
    sample_rate: int
    bitrate: int
    padding: int
    samples: int
    length: int

    @property
    def format_key(self) -> tuple[int, int, int, int]:
        return (self.version_bits, self.sample_rate, self.bitrate, self.raw[3] >> 6)  # + channel mode


def _parse_header(b: bytes, i: int) -> FrameHeader | None:
    if i + 4 > len(b) or b[i] != 0xFF or (b[i + 1] & 0xE0) != 0xE0:
        return None
    version_bits = (b[i + 1] >> 3) & 0x3
    layer_bits = (b[i + 1] >> 1) & 0x3
    if version_bits == 1 or layer_bits != 1:  # reserved version, or not Layer III
        return None
    br_idx, sr_idx = b[i + 2] >> 4, (b[i + 2] >> 2) & 0x3
    if br_idx in (0, 15) or sr_idx == 3:
        return None
    mpeg1 = version_bits == 3
    bitrate = _BITRATES[(1 if mpeg1 else 2, 3)][br_idx] * 1000
    sample_rate = _SAMPLE_RATES[version_bits][sr_idx]
    padding = (b[i + 2] >> 1) & 0x1
    samples = 1152 if mpeg1 else 576
    length = (144 if mpeg1 else 72) * bitrate // sample_rate + padding
    return FrameHeader(bytes(b[i : i + 4]), version_bits, sample_rate, bitrate, padding, samples, length)


def _skip_id3(b: bytes) -> int:
    if b[:3] == b"ID3" and len(b) >= 10:
        size = (b[6] << 21) | (b[7] << 14) | (b[8] << 7) | b[9]
        return 10 + size
    return 0


def frames(b: bytes) -> list[tuple[int, FrameHeader]]:
    out = []
    i = _skip_id3(b)
    while i < len(b):
        h = _parse_header(b, i)
        if h is None:
            i += 1  # resync
            continue
        out.append((i, h))
        i += h.length
    return out


def duration(b: bytes) -> float:
    return sum(h.samples / h.sample_rate for _, h in frames(b))


def first_header(b: bytes) -> FrameHeader:
    fr = frames(b)
    if not fr:
        raise ValueError("No MP3 frames found")
    return fr[0][1]


def silence(template: FrameHeader, seconds: float) -> bytes:
    """Silent frames in the same format as template (no padding, no CRC)."""
    h = bytearray(template.raw)
    h[1] |= 0x01         # protection bit = 1 -> no CRC
    h[2] &= ~0x02 & 0xFF  # padding = 0
    length = (144 if template.version_bits == 3 else 72) * template.bitrate // template.sample_rate
    frame = bytes(h) + bytes(length - 4)
    count = max(0, round(seconds * template.sample_rate / template.samples))
    return frame * count


def frame_seconds(template: FrameHeader) -> float:
    return template.samples / template.sample_rate


def strip_to_frames(b: bytes) -> bytes:
    """Only the audio frames (drops tags or junk) so clips can be concatenated."""
    return b"".join(b[i : i + h.length] for i, h in frames(b))
