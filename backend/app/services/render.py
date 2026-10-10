"""Render pipeline: props JSON -> Remotion MP4 (voice) -> FFmpeg music mix with ducking.

All external tools are called with argument lists (no shell). Paths come from pathlib.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from ..config import settings
from . import jobcontrol, joblog
from .app_settings import get_setting
from .narration import audio_paths
from .props import build_props
from .quarters import QuarterFile

log = logging.getLogger(__name__)

FPS = 30
PUBLIC_RENDERS = settings.video_dir / "public" / "renders"
VIDEOS_DIR = settings.outputs_dir / "videos"
PROGRESS_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class RenderError(RuntimeError):
    pass


# ---------- tools ----------

def find_ffmpeg(name: str = "ffmpeg") -> str:
    """ffmpeg/ffprobe from PATH, FFMPEG_DIR, or the winget install folder (PATH may be stale)."""
    found = shutil.which(name)
    if found:
        return found
    candidates = []
    if os.getenv("FFMPEG_DIR"):
        candidates.append(Path(os.environ["FFMPEG_DIR"]) / f"{name}.exe")
    winget = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget.exists():
        candidates += sorted(winget.glob(f"Gyan.FFmpeg*/*/bin/{name}.exe"), reverse=True)
    for c in candidates:
        if c.exists():
            return str(c)
    raise RenderError(f"{name} not found. Install FFmpeg (winget install Gyan.FFmpeg) and open a new terminal.")


def find_browser() -> str | None:
    """Browser for Remotion. None = Remotion's own chrome-headless-shell (downloaded once, ~3.5x faster
    than Edge here). Set REMOTION_BROWSER to use another Chromium browser."""
    return os.getenv("REMOTION_BROWSER") or None


def npx() -> str:
    found = shutil.which("npx")
    if not found:
        raise RenderError("npx not found. Install Node.js 20+.")
    return found


def remotion_cmd() -> list[str]:
    """node + the local Remotion CLI. Skips npx.CMD, whose cmd.exe wrapper can exit silently on Windows."""
    cli = Path(settings.video_dir) / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    node = shutil.which("node")
    if node and cli.exists():
        return [node, str(cli)]
    return [npx(), "remotion"]


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [find_ffmpeg("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return round(float(json.loads(out.stdout)["format"]["duration"]), 3)


# ---------- music ----------

def music_track() -> Path | None:
    name = get_setting("music_track")
    if not name:
        return None
    path = Path(name) if Path(name).is_absolute() else settings.music_dir / Path(name).name
    return path if path.exists() else None


def music_credit(track: Path | None) -> str | None:
    """Credit line for the track from data/music/LICENSES.txt (needed for CC BY tracks)."""
    lic = settings.music_dir / "LICENSES.txt"
    if not track or not lic.exists():
        return None
    blocks = lic.read_text(encoding="utf-8").split("\n\n")
    for block in blocks:
        fields = dict(line.split(":", 1) for line in block.splitlines() if ":" in line)
        if fields.get("file", "").strip() == track.name and "credit" in fields:
            return "Music: " + fields["credit"].strip()
    return None


# ---------- steps ----------

def prepare_props(video_id: str, lang: str, script: dict[str, Any], qf: QuarterFile) -> Path:
    """Copy the narration into video/public/renders and write outputs/videos/{id}_{lang}.props.json."""
    mp3, words = audio_paths(video_id, lang)
    if not mp3.exists() or not words.exists():
        raise RenderError(f"No {lang} narration for {video_id}; run TTS first")
    PUBLIC_RENDERS.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(mp3, PUBLIC_RENDERS / mp3.name)
    narration = json.loads(words.read_text(encoding="utf-8"))
    props = build_props(
        script, lang, narration, qf,
        audio_src=f"renders/{mp3.name}",
        digits=get_setting("arabic_digits"),
        captions=bool(get_setting("captions")),
    )
    props["musicCredit"] = music_credit(music_track())
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    path = VIDEOS_DIR / f"{video_id}_{lang}.props.json"
    path.write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def remotion_render(
    composition: str, props_path: Path, out_path: Path, on_progress: Callable[[int, int], None] | None = None
) -> None:
    """npx remotion render src/index.ts <composition> <out> --props=<json> (run in video/)."""
    args = [*remotion_cmd(), "render", "src/index.ts", composition, str(out_path), f"--props={props_path}",
            f"--concurrency={max(1, (os.cpu_count() or 4) // 2)}", "--log=info"]
    browser = find_browser()
    if browser:
        args.append(f"--browser-executable={browser}")
    log.info("Rendering %s -> %s", composition, out_path.name)
    joblog.write(f"$ {subprocess.list2cmdline(args)}  (cwd {settings.video_dir})")
    jobcontrol.check()
    proc = subprocess.Popen(
        args, cwd=settings.video_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    stop = jobcontrol.stop_event()
    if stop is not None:
        threading.Thread(target=_kill_on_stop, args=(proc, stop), daemon=True).start()
    tail: list[str] = []
    last = -1
    assert proc.stdout is not None
    for line in proc.stdout:  # universal newlines also splits progress bars on \r
        line = ANSI_RE.sub("", line).strip()
        if not line:
            continue
        tail = (tail + [line])[-25:]
        m = PROGRESS_RE.search(line) if ("Render" in line or "frames" in line.lower()) else None
        if m:
            done, total = int(m.group(1)), int(m.group(2))
            pct = int(done * 100 / max(total, 1))
            if pct != last:
                if pct // 10 != last // 10:  # progress goes to the job log in 10% steps only
                    joblog.write(f"  remotion: {line}")
                last = pct
                if on_progress:
                    on_progress(done, total)
        else:
            joblog.write(f"  remotion: {line}")
    code = proc.wait()
    joblog.write(f"  remotion exited with code {code}; output exists: {out_path.exists()}")
    if stop is not None and stop.is_set():
        out_path.unlink(missing_ok=True)  # a half-written MP4
        raise jobcontrol.JobStopped()
    if code != 0 or not out_path.exists():
        detail = "\n".join(tail[-12:]) or "(no output)"
        raise RenderError(f"Remotion render failed for {composition} (exit code {code}):\n{detail}")


def _kill_on_stop(proc: subprocess.Popen, stop: threading.Event) -> None:
    """Kill the render (and the Chrome processes it started) when the job is stopped."""
    while proc.poll() is None:
        if stop.wait(0.5):
            joblog.write("  stopping remotion render")
            if os.name == "nt":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
            else:
                proc.kill()
            return


def _duck_graph(volume: float, duration: float) -> str:
    """FFmpeg filter: input 0 = voice, input 1 = looped music at `volume`, ducked under the voice."""
    fade_out_start = max(0.0, duration - 3.0)
    return (
        f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={volume},"
        f"afade=t=in:d=1.5,afade=t=out:st={fade_out_start}:d=3[music];"
        "[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[voice][key];"
        "[music][key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=450[ducked];"
        "[voice][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
    )


def preview_mix(voice_mp3: Path, out: Path, track: Path | None, volume: float) -> None:
    """Audio-only preview for the audio review: narration + music exactly as the video will mix it."""
    if not track:
        shutil.copyfile(voice_mp3, out)
        return
    duration = probe_duration(voice_mp3)
    args = [find_ffmpeg(), "-y", "-v", "error", "-i", str(voice_mp3), "-stream_loop", "-1", "-i", str(track),
            "-filter_complex", _duck_graph(volume, duration), "-map", "[aout]",
            "-c:a", "libmp3lame", "-b:a", "160k", "-t", str(duration), str(out)]
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RenderError(f"FFmpeg preview mix failed (exit code {proc.returncode}):\n{proc.stderr.strip()[-800:]}")


def mix_music(video_in: Path, out: Path, track: Path | None, volume: float) -> None:
    """Voice from the render + looped music at `volume`, ducked under the voice (sidechain)."""
    ffmpeg = find_ffmpeg()
    if not track:
        shutil.copyfile(video_in, out)
        return
    duration = probe_duration(video_in)
    graph = _duck_graph(volume, duration)
    args = [ffmpeg, "-y", "-v", "error", "-i", str(video_in), "-stream_loop", "-1", "-i", str(track),
            "-filter_complex", graph, "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", str(duration), str(out)]
    joblog.write(f"$ {subprocess.list2cmdline(args)}")
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        joblog.write(f"  ffmpeg exited with code {proc.returncode}:\n{proc.stderr}")
        raise RenderError(f"FFmpeg music mix failed (exit code {proc.returncode}):\n{proc.stderr.strip()[-800:]}")


def make_poster(video: Path, at_seconds: float, out: Path) -> None:
    subprocess.run(
        [find_ffmpeg(), "-y", "-v", "error", "-ss", str(at_seconds), "-i", str(video), "-frames:v", "1",
         "-vf", "scale=960:-2", "-q:v", "3", str(out)],
        check=True, capture_output=True,
    )


def _vtt_time(t: float) -> str:
    h, rem = divmod(max(0.0, t), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def write_vtt(video_id: str, lang: str, out: Path) -> None:
    """WebVTT captions from the narration word timings (lines of up to 9 words)."""
    _, words_path = audio_paths(video_id, lang)
    words = json.loads(words_path.read_text(encoding="utf-8"))["words"]
    cues, cur = [], []
    for i, w in enumerate(words):
        gap = w["start"] - words[i - 1]["end"] if i else 0
        if cur and (len(cur) >= 9 or gap > 0.45 or re.search(r"[.!?؟،,;؛]$", cur[-1]["text"])):
            cues.append(cur)
            cur = []
        cur.append(w)
    if cur:
        cues.append(cur)
    lines = ["WEBVTT", ""]
    for n, cue in enumerate(cues, 1):
        lines += [str(n), f"{_vtt_time(cue[0]['start'])} --> {_vtt_time(cue[-1]['end'])}",
                  " ".join(w["text"] for w in cue), ""]
    out.write_text("\n".join(lines), encoding="utf-8")


def rel(path: Path) -> str:
    return path.relative_to(settings.outputs_dir).as_posix()
