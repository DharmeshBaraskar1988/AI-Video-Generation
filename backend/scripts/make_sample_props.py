"""Build video/sample.props.json (EN) and video/sample_ar.props.json (AR) for Remotion Studio.

Narrates a script (default: the Q2 2026 demo, approved or not) into video/public/sample/
without touching that script's job. Run from the repo root:
    backend\\.venv\\Scripts\\python -m backend.scripts.make_sample_props [video_id]
"""
from __future__ import annotations

import json
import shutil
import sys

from backend.app.config import ROOT, settings
from backend.app.services.app_settings import get_setting
from backend.app.services.narration import audio_paths, narrate
from backend.app.services.props import build_props
from backend.app.services.quarters import get_quarter
from backend.app.services.script_store import load_script


def main(video_id: str = "iqcd-q2-2026") -> None:
    script = load_script(video_id)
    if not script:
        raise SystemExit(f"No script '{video_id}'. Generate it from the dashboard first.")
    qf, _ = get_quarter(script["company"], script["quarter"])
    sample_dir = ROOT / "video" / "public" / "sample"
    sample_dir.mkdir(parents=True, exist_ok=True)

    for lang, name in (("en", "sample.props.json"), ("ar", "sample_ar.props.json")):
        tmp_id = f"sample-{video_id}"
        narrate(tmp_id, lang, script["scenes"], script["placeholders"])
        mp3_path, words_path = audio_paths(tmp_id, lang)
        shutil.move(mp3_path, sample_dir / f"{lang}.mp3")
        narration = json.loads(words_path.read_text(encoding="utf-8"))
        words_path.unlink()
        props = build_props(
            script, lang, narration, qf, audio_src=f"sample/{lang}.mp3",
            digits=get_setting("arabic_digits"), captions=bool(get_setting("captions")),
        )
        (ROOT / "video" / name).write_text(json.dumps(props, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{name}: {props['durationSeconds']}s, {len(props['scenes'])} scenes, {len(props['words'])} words")
    print("audio in", sample_dir.relative_to(settings.outputs_dir.parent))


if __name__ == "__main__":
    main(*sys.argv[1:])
