"""Video graph (LangGraph).

load_quarter -> gather_context -> draft_script -> factcheck -> translate_ar -> factcheck_ar
-> human_review (interrupt) -> tts_en -> tts_ar -> audio_review (interrupt: listen to voice + music)
-> build_props -> render_en -> render_ar -> mix_audio
-> index_script (scene text + start times into the search index for video Q&A)

One LLM call per stage (plus at most one repair call when the fact check fails).
Each node's status is written to the Video row so the UI can show progress.
State is checkpointed in SQLite so a paused review survives a server restart.
"""
from __future__ import annotations

import functools
import json
import logging
import math
import re
import sqlite3
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlmodel import Session

from ..config import settings
from ..db import Video, engine
from ..services import factcheck as fc
from ..services import jobcontrol, joblog
from ..services.app_settings import get_setting
from ..services.llm import get_llm, load_prompt
from ..services import render as rnd
from ..services.narration import narrate
from ..services.quarters import get_quarter
from ..services.script_store import save_script

log = logging.getLogger(__name__)

SCENE_TYPES = ["intro", "kpis", "trend", "drivers", "segments", "outlook", "outro"]
NODES = [
    "load_quarter", "gather_context", "draft_script", "factcheck", "translate_ar", "factcheck_ar",
    "human_review", "tts_en", "tts_ar", "audio_review", "build_props", "render_en", "render_ar", "mix_audio",
    "index_script",
]
FIGURE_RE = re.compile(
    r"(?:QR\s*)?[0-9][0-9.,]*\s*(?:bn|billion|million|m\b|%|percent)?", re.I
)


class VideoState(TypedDict, total=False):
    video_id: str
    company: str
    period: str
    fresh: bool
    quarter: dict[str, Any]
    company_info: dict[str, Any]
    demo: bool
    placeholders: dict[str, Any]
    context: dict[str, Any]
    target_seconds: int
    scenes: list[dict[str, Any]]
    checks: dict[str, Any]
    repairs: list[str]
    review: Any
    audio: dict[str, Any]
    props: dict[str, str]
    renders: dict[str, dict[str, str]]


# ---------- progress tracking ----------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_video(video_id: str, **fields: Any) -> None:
    with Session(engine) as s:
        video = s.get(Video, video_id)
        if not video:
            return
        for k, v in fields.items():
            setattr(video, k, v)
        video.updated_at = datetime.now(timezone.utc)
        s.add(video)
        s.commit()


def _set_node(video_id: str, node: str, **info: Any) -> None:
    with Session(engine) as s:
        video = s.get(Video, video_id)
        if not video:
            return
        status = dict(video.node_status or {})
        status[node] = {**status.get(node, {}), **info}
        video.node_status = status
        video.current_node = node
        video.updated_at = datetime.now(timezone.utc)
        s.add(video)
        s.commit()


def tracked(name: str) -> Callable:
    def deco(fn: Callable[[VideoState], dict]) -> Callable[[VideoState], dict]:
        @functools.wraps(fn)
        def wrapper(state: VideoState) -> dict:
            vid = state["video_id"]
            token = joblog.current_job.set(vid)
            started = time.monotonic()
            joblog.write(f"-> {name} started")
            _set_node(vid, name, status="running", started_at=_now(), finished_at=None, error=None)
            try:
                jobcontrol.check()  # a stop pressed between steps lands here
                result = fn(state)
            except jobcontrol.JobStopped:
                _set_node(vid, name, status="stopped", finished_at=_now(), error=None)
                joblog.write(f"!! {name} stopped after {time.monotonic() - started:.1f}s")
                raise
            except GraphInterrupt:
                _set_node(vid, name, status="waiting")
                joblog.write(f"   {name} waiting for you")
                raise
            except Exception as exc:
                _set_node(vid, name, status="failed", finished_at=_now(), error=str(exc))
                joblog.write(f"xx {name} FAILED after {time.monotonic() - started:.1f}s\n{traceback.format_exc()}")
                raise
            finally:
                joblog.current_job.reset(token)
            _set_node(vid, name, status="done", finished_at=_now())
            joblog.write(f"ok {name} done in {time.monotonic() - started:.1f}s", vid)
            return result

        return wrapper

    return deco


# ---------- helpers ----------

def mask_figures(text: str) -> str:
    """Hide numbers in free-text context so the model cannot copy them."""
    return FIGURE_RE.sub("[figure]", text)


def placeholder_list(placeholders: dict[str, Any], lang: str = "en") -> list[dict[str, Any]]:
    key = "reads_as" if lang == "en" else "reads_as_ar"
    return [
        {"key": k, "meaning": p["label"], key: p[f"display_{lang}"], "derived": p["derived"]}
        for k, p in placeholders.items()
    ]


def default_visual(scene_type: str, keys: list[str], placeholders: dict[str, Any]) -> dict[str, Any]:
    if scene_type == "kpis":
        series = [k for k in ("revenue", "net_result", "eps") if k in placeholders]
        return {"chart": "cards", "series": series}
    if scene_type == "trend":
        return {"chart": "bar", "series": ["history_net_profit"]}
    if scene_type == "segments":
        return {"chart": "donut", "series": [k for k in placeholders if k.startswith("seg_") and k.endswith("_share")]}
    if scene_type == "drivers":
        return {"chart": "bullets", "series": []}
    return {"chart": None, "series": []}


def _issues_by_scene(checks: dict[str, Any], lang: str) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {}
    for s in checks["stray_numbers"]:
        if s["lang"] == lang:
            issues.setdefault(s["scene"], []).append(f"number typed by hand: '{s['text']}'")
    for u in checks["unknown_placeholders"]:
        if u["lang"] == lang:
            issues.setdefault(u["scene"], []).append(f"unknown placeholder: {{{{{u['key']}}}}}")
    if lang == "ar":
        for m in checks.get("placeholder_mismatch", []):
            issues.setdefault(m["scene"], []).append(
                f"placeholders must be exactly {m['en']} (found {m['ar']})"
            )
    return issues


def _repair(state: VideoState, scenes: list[dict[str, Any]], lang: str, issues: dict[str, list[str]]) -> list[dict[str, Any]]:
    """One LLM call to rewrite only the scenes that failed the check."""
    by_id = {s["id"]: s for s in scenes}
    payload = {
        "LANGUAGE": "Arabic" if lang == "ar" else "English",
        "PLACEHOLDERS": placeholder_list(state["placeholders"], lang),
        "SCENES": [
            {
                "id": sid,
                "text": by_id[sid][lang],
                "problems": problems,
                **({"required_placeholders": by_id[sid].get("data_keys", [])} if lang == "ar" else {}),
            }
            for sid, problems in issues.items()
        ],
    }
    out = get_llm().generate_json(
        json.dumps(payload, ensure_ascii=False, indent=1), system=load_prompt("fix_numbers.md"), temperature=0.2
    )
    fixed = {s["id"]: s["text"] for s in out.get("scenes", []) if s.get("id") in by_id and s.get("text")}
    return [{**s, lang: fixed.get(s["id"], s[lang])} for s in scenes]


def _shorten(state: VideoState, scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One LLM call that trims EN and AR together to fit the 3-minute maximum (5% margin)."""
    n = len(scenes)
    payload = {
        "max_words_en": fc.words_for_seconds(fc.MAX_VIDEO_SECONDS * 0.95, "en", n),
        "max_words_ar": fc.words_for_seconds(fc.MAX_VIDEO_SECONDS * 0.95, "ar", n),
        "PLACEHOLDERS": [
            {**en, "reads_as_ar": ar["reads_as_ar"]}
            for en, ar in zip(placeholder_list(state["placeholders"], "en"), placeholder_list(state["placeholders"], "ar"))
        ],
        "SCENES": [{"id": s["id"], "type": s["type"], "en": s["en"], "ar": s["ar"]} for s in scenes],
    }
    out = get_llm().generate_json(
        json.dumps(payload, ensure_ascii=False, indent=1), system=load_prompt("shorten.md"), temperature=0.2,
        cache=not state.get("fresh"),
    )
    short = {s["id"]: s for s in out.get("scenes", []) if s.get("id")}
    return [
        {**s, "en": (short.get(s["id"], {}).get("en") or s["en"]).strip(), "ar": (short.get(s["id"], {}).get("ar") or s["ar"]).strip()}
        for s in scenes
    ]


# ---------- nodes ----------

@tracked("load_quarter")
def load_quarter(state: VideoState) -> dict:
    found = get_quarter(state["company"], state["period"])
    if not found:
        raise ValueError(f"No quarter {state['period']} for {state['company']}")
    qf, q = found
    return {
        "quarter": q.model_dump(),
        "company_info": qf.company.model_dump(),
        "demo": qf.demo,
        "placeholders": fc.build_placeholders(qf, q),
        "target_seconds": min(max(int(get_setting("target_seconds")), fc.MIN_VIDEO_SECONDS), fc.MAX_VIDEO_SECONDS),
        "context": {
            "drivers": qf.narrative_drivers,
            "drivers_period": qf.current_quarter,
            "is_current": q.period == qf.current_quarter,
            "derivation": q.derivation if q.derived else None,
        },
    }


@tracked("gather_context")
def gather_context(state: VideoState) -> dict:
    ctx = state["context"]
    return {
        "context": {
            **ctx,
            "drivers_masked": [mask_figures(d) for d in ctx["drivers"]],
            "derivation_masked": mask_figures(ctx["derivation"]) if ctx.get("derivation") else None,
            "documents": _document_passages(state["company"], state["period"]),
        }
    }


def _document_passages(company: str, period: str, limit: int = 6) -> list[dict[str, Any]]:
    """Relevant passages from the results PDFs, with figures masked (numbers come only from placeholders)."""
    from ..services import rag

    queries = [
        f"reasons for the change in results {period} sales volumes selling prices",
        "segment performance petrochemicals fertilisers steel",
        "outlook strategy liquidity dividend",
    ]
    seen: dict[str, dict[str, Any]] = {}
    try:
        for q in queries:
            for h in rag.search(q, k=4, where=rag.doc_where(company, year=int(period.split()[1]))):
                seen.setdefault(h["id"], h)
    except Exception as exc:  # noqa: BLE001 - the script can be written without the index
        log.warning("Document index unavailable for gather_context: %s", exc)
        return []
    hits = sorted(seen.values(), key=lambda h: -h["score"])[:limit]
    return [
        {"source": f"{h['file']} p.{h['page']}", "section": h["section"], "text": mask_figures(h["text"])[:1200]}
        for h in hits
        if h["type"] == "text"
    ]


@tracked("draft_script")
def draft_script(state: VideoState) -> dict:
    # Both videos must run 2-3 minutes. Arabic narration is ~1.27x longer than the English, so the
    # English aims at 2:00-2:20 and the Arabic then lands at about 2:30-3:00.
    en_max = min(fc.MAX_VIDEO_SECONDS / fc.AR_LENGTH_RATIO, max(state["target_seconds"], fc.MIN_VIDEO_SECONDS))
    min_words = fc.words_for_seconds(fc.MIN_VIDEO_SECONDS, "en", len(SCENE_TYPES))
    max_words = max(min_words + 20, fc.words_for_seconds(en_max, "en", len(SCENE_TYPES)))
    system = load_prompt("script.md").replace("{{min_words}}", str(min_words)).replace("{{max_words}}", str(max_words))
    ctx = state["context"]
    company = state["company_info"]
    payload = {
        "COMPANY": {"name": company["name_en"].replace(" (demo source)", ""), "ticker": company["ticker"], "exchange": company["exchange"]},
        "PLACEHOLDERS": placeholder_list(state["placeholders"]),
        "KEY DRIVERS": ctx["drivers_masked"],
        "NOTES": [n for n in [ctx.get("derivation_masked")] if n]
        + ["[figure] marks a number removed on purpose. Do not guess it; describe it in words or leave it out."]
        + (
            []
            if ctx.get("is_current")
            else [
                f"KEY DRIVERS were written for the latest reporting period ({ctx['drivers_period']}, including the "
                f"year to date), not for {state['period']}. Use only drivers that clearly also applied to "
                f"{state['period']}, keep the drivers scene general, and never present later events as causes."
            ]
        ),
        "DOCUMENT PASSAGES": ctx.get("documents", []),
    }
    out = get_llm().generate_json(
        json.dumps(payload, ensure_ascii=False, indent=1), system=system, temperature=0.5, cache=not state.get("fresh")
    )
    raw = out.get("scenes", []) if isinstance(out, dict) else out
    if not raw:
        raise ValueError("The model returned no scenes")

    ph = state["placeholders"]
    scenes = []
    for i, s in enumerate(raw, start=1):
        stype = s.get("type") if s.get("type") in SCENE_TYPES else SCENE_TYPES[min(i - 1, len(SCENE_TYPES) - 1)]
        en = (s.get("en") or "").strip()
        keys = fc.scene_keys(en, ph)
        visual = default_visual(stype, keys, ph)
        highlight = (s.get("visual") or {}).get("highlight")
        visual["highlight"] = highlight if highlight in ph else (keys[0] if keys else None)
        scenes.append({"id": f"s{i}", "type": stype, "en": en, "ar": "", "data_keys": keys, "visual": visual})
    return {"scenes": scenes, "repairs": []}


@tracked("factcheck")
def factcheck(state: VideoState) -> dict:
    scenes, repairs = state["scenes"], list(state.get("repairs", []))
    checks = fc.check_script(scenes, state["placeholders"], langs=("en",))
    issues = _issues_by_scene(checks, "en")
    if issues:
        log.warning("English script has number issues, repairing: %s", issues)
        scenes = _repair(state, scenes, "en", issues)
        repairs.append(f"en: {sorted(issues)}")
        checks = fc.check_script(scenes, state["placeholders"], langs=("en",))
    for s in scenes:
        s["data_keys"] = fc.scene_keys(s["en"], state["placeholders"])
    return {"scenes": scenes, "checks": checks, "repairs": repairs}


@tracked("translate_ar")
def translate_ar(state: VideoState) -> dict:
    ph = state["placeholders"]
    used = {k for s in state["scenes"] for k in s["data_keys"]}
    payload = {
        "COMPANY": {"name_ar": state["company_info"]["name_ar"]},
        "PLACEHOLDERS": [p for p in placeholder_list(ph, "ar") if p["key"] in used],
        "SCENES": [{"id": s["id"], "type": s["type"], "en": s["en"]} for s in state["scenes"]],
    }
    out = get_llm().generate_json(
        json.dumps(payload, ensure_ascii=False, indent=1), system=load_prompt("translate_ar.md"), temperature=0.2,
        cache=not state.get("fresh"),
    )
    ar = {s["id"]: (s.get("ar") or "").strip() for s in out.get("scenes", [])}
    missing = [s["id"] for s in state["scenes"] if not ar.get(s["id"])]
    if missing:
        raise ValueError(f"Arabic translation is missing scenes {missing}")
    return {"scenes": [{**s, "ar": ar[s["id"]]} for s in state["scenes"]]}


@tracked("factcheck_ar")
def factcheck_ar(state: VideoState) -> dict:
    ph, scenes, repairs = state["placeholders"], state["scenes"], list(state.get("repairs", []))
    langs = ["ar"]
    est = fc.full_checks(scenes, ph, get_setting("arabic_digits"))
    if fc.length_enforced() and max(est["estimated_seconds_en"], est["estimated_seconds_ar"]) > fc.MAX_VIDEO_SECONDS:
        log.warning(
            "Script too long (EN %ss, AR %ss; max %ss), shortening",
            est["estimated_seconds_en"], est["estimated_seconds_ar"], fc.MAX_VIDEO_SECONDS,
        )
        scenes = _shorten(state, scenes)
        after = fc.full_checks(scenes, ph, get_setting("arabic_digits"))
        log.info("Shortened to EN %ss, AR %ss", after["estimated_seconds_en"], after["estimated_seconds_ar"])
        repairs.append(f"shortened: EN {est['estimated_seconds_en']}->{after['estimated_seconds_en']}s, "
                       f"AR {est['estimated_seconds_ar']}->{after['estimated_seconds_ar']}s")
        langs = ["en", "ar"]  # the English changed too, so re-check it
    checks = fc.check_script(scenes, ph)
    for lang in langs:
        issues = _issues_by_scene(checks, lang)
        if issues:
            log.warning("%s script has number issues, repairing: %s", lang, issues)
            scenes = _repair(state, scenes, lang, issues)
            repairs.append(f"{lang}: {sorted(issues)}")
            checks = fc.check_script(scenes, ph)
    for s in scenes:
        s["data_keys"] = fc.scene_keys(s["en"], ph)

    checks = fc.full_checks(scenes, ph, get_setting("arabic_digits"), repairs)

    q = state["quarter"]
    save_script(
        {
            "video_id": state["video_id"],
            "company": state["company"],
            "company_name_en": state["company_info"]["name_en"],
            "company_name_ar": state["company_info"]["name_ar"],
            "quarter": q["period"],
            "derived": q["derived"],
            "demo": state["demo"],
            "status": "draft",
            "target_seconds": state["target_seconds"],
            "model": get_llm().last_model,
            "created_at": _now(),
            "scenes": scenes,
            "placeholders": ph,
            "checks": checks,
        }
    )
    return {"scenes": scenes, "checks": checks, "repairs": repairs}


@tracked("human_review")
def human_review(state: VideoState) -> dict:
    # With "require review" switched off in Admin, a script that passes every check is approved
    # automatically; otherwise the graph pauses until POST /api/scripts/{id}/approve resumes it.
    checks = state.get("checks") or {}
    if not get_setting("require_review") and checks.get("passed") and checks.get("length_ok", True):
        from ..services.script_store import load_script

        script = load_script(state["video_id"])
        script.update(status="approved", approved_at=_now(), auto_approved=True)
        save_script(script)
        return {"review": {"approved": True, "auto": True}, "scenes": state["scenes"]}
    decision = interrupt({"video_id": state["video_id"], "awaiting": "script approval"})
    return {"review": decision, "scenes": decision.get("scenes", state["scenes"])}


def _tts(state: VideoState, lang: str) -> dict:
    audio = dict(state.get("audio") or {})
    if lang not in (get_setting("languages") or ["en", "ar"]):
        audio.pop(lang, None)
        return {"audio": audio}
    info = narrate(state["video_id"], lang, state["scenes"], state["placeholders"])
    if fc.length_enforced() and info["duration"] > fc.MAX_VIDEO_SECONDS:
        info = _narrate_faster(state, lang, info)
    info = {**info, **_music_preview(state["video_id"], lang, info)}
    audio[lang] = info
    with Session(engine) as s:
        video = s.get(Video, state["video_id"])
        files = dict(video.files or {})
        files[f"audio_{lang}"] = info
        video.files = files
        s.add(video)
        s.commit()
    return {"audio": audio}


def _music_preview(video_id: str, lang: str, info: dict[str, Any]) -> dict[str, Any]:
    """Narration + the chosen royalty-free track, mixed as the video will be, for the audio review."""
    track = rnd.music_track()
    volume = float(get_setting("music_volume"))
    voice = settings.outputs_dir / info["audio"]
    out = voice.with_name(f"{video_id}_{lang}_preview.mp3")
    try:
        rnd.preview_mix(voice, out, track, volume)
    except Exception as exc:  # the plain narration is still reviewable
        log.warning("Music preview for %s %s failed: %s", video_id, lang, exc)
        return {"preview": None, "music": track.name if track else None, "music_volume": volume}
    return {"preview": rnd.rel(out), "music": track.name if track else None, "music_volume": volume}


MAX_SPEEDUP_PERCENT = 15  # beyond this the voice sounds rushed; shorten the script instead


def _narrate_faster(state: VideoState, lang: str, info: dict[str, Any]) -> dict[str, Any]:
    """Narration ran over 3:00: re-record once at a slightly faster speaking rate."""
    m = re.fullmatch(r"([+-]?\d+)%", str(info.get("rate") or "+0%").strip())
    current = int(m.group(1)) if m else 0
    target = fc.MAX_VIDEO_SECONDS - 2  # small margin for rounding
    needed = math.ceil(((1 + current / 100) * info["duration"] / target - 1) * 100)
    label = f"{lang.upper()} narration is {info['duration']:.0f}s"
    if needed - current > MAX_SPEEDUP_PERCENT:
        raise ValueError(
            f"{label}, over the {fc.MAX_VIDEO_SECONDS // 60}-minute maximum. "
            "Shorten the script and approve again."
        )
    rate = f"{needed:+d}%"
    log.warning("%s (over %ss); re-recording at rate %s", label, fc.MAX_VIDEO_SECONDS, rate)
    info = narrate(state["video_id"], lang, state["scenes"], state["placeholders"], rate=rate)
    if info["duration"] > fc.MAX_VIDEO_SECONDS:
        raise ValueError(
            f"{lang.upper()} narration is still {info['duration']:.0f}s at rate {rate}, over the "
            f"{fc.MAX_VIDEO_SECONDS // 60}-minute maximum. Shorten the script and approve again."
        )
    return info


@tracked("tts_en")
def tts_en(state: VideoState) -> dict:
    return _tts(state, "en")


@tracked("tts_ar")
def tts_ar(state: VideoState) -> dict:
    return _tts(state, "ar")


@tracked("audio_review")
def audio_review(state: VideoState) -> dict:
    # Pause so a person can listen to each narration with its music before the (slow) render.
    # Voices, speaking speed and music are chosen in Admin; "Re-record" re-runs from tts_en.
    if not get_setting("require_audio_review"):
        return {}
    interrupt({"video_id": state["video_id"], "awaiting": "audio approval"})
    return {}


def _languages(state: VideoState) -> list[str]:
    return [lang for lang in ("en", "ar") if lang in (state.get("audio") or {})]


def _save_files(video_id: str, **entries: Any) -> None:
    with Session(engine) as s:
        video = s.get(Video, video_id)
        files = dict(video.files or {})
        files.update(entries)
        video.files = files
        s.add(video)
        s.commit()


def _check_narration_length(state: VideoState) -> None:
    """Never render a video over the maximum (also covers retries of older, longer narrations)."""
    if not fc.length_enforced():
        return
    for lang, info in (state.get("audio") or {}).items():
        if info and info.get("duration", 0) > fc.MAX_VIDEO_SECONDS:
            raise ValueError(
                f"{lang.upper()} narration is {info['duration']:.0f}s, over the {fc.MAX_VIDEO_SECONDS // 60}-minute "
                "maximum. Regenerate from the start, or shorten the script and approve again."
            )


@tracked("build_props")
def build_props(state: VideoState) -> dict:
    _check_narration_length(state)
    found = get_quarter(state["company"], state["period"])
    if not found:
        raise ValueError(f"No quarter {state['period']} for {state['company']}")
    qf, _ = found
    # Use the approved script as stored (includes any edits made before approval).
    from ..services.script_store import load_script

    script = load_script(state["video_id"])
    props = {lang: str(rnd.prepare_props(state["video_id"], lang, script, qf)) for lang in _languages(state)}
    return {"props": props, "renders": {}}


def _render(state: VideoState, lang: str, node: str) -> dict:
    renders = dict(state.get("renders") or {})
    if lang not in (state.get("props") or {}):
        return {"renders": renders}
    vid, props_path = state["video_id"], Path(state["props"][lang])
    _check_narration_length(state)
    _set_node(vid, node, progress=0, detail=None)
    out_dir = rnd.VIDEOS_DIR
    parts = [("full", "QuarterlyVideo", out_dir / f"{vid}_{lang}.raw.mp4")]
    if get_setting("social_cut"):
        parts.append(("social", "SocialCut", out_dir / f"{vid}_{lang}_social.raw.mp4"))
    result = {}
    for part, comp, out in parts:
        def progress(done: int, total: int, part: str = part) -> None:
            _set_node(vid, node, progress=round(done * 100 / max(total, 1)), detail=f"{part} {done}/{total} frames")

        rnd.remotion_render(comp, props_path, out, progress)
        result[part] = str(out)
    renders[lang] = result
    return {"renders": renders}


@tracked("render_en")
def render_en(state: VideoState) -> dict:
    return _render(state, "en", "render_en")


@tracked("render_ar")
def render_ar(state: VideoState) -> dict:
    return _render(state, "ar", "render_ar")


@tracked("mix_audio")
def mix_audio(state: VideoState) -> dict:
    vid = state["video_id"]
    track = rnd.music_track()
    volume = float(get_setting("music_volume"))
    credit = rnd.music_credit(track)
    for lang, parts in (state.get("renders") or {}).items():
        props = json.loads(Path(state["props"][lang]).read_text(encoding="utf-8"))
        kpis = next((s for s in props["scenes"] if s["type"] == "kpis"), props["scenes"][0])
        entry: dict[str, Any] = {}
        for part, raw in parts.items():
            raw = Path(raw)
            final = raw.with_name(raw.name.replace(".raw.mp4", ".mp4"))
            rnd.mix_music(raw, final, track, volume)
            raw.unlink(missing_ok=True)
            entry["video" if part == "full" else "social"] = rnd.rel(final)
            if part == "full":
                entry["duration"] = rnd.probe_duration(final)
                poster = final.with_suffix(".jpg")
                rnd.make_poster(final, kpis["audioStart"] + 3, poster)
                entry["poster"] = rnd.rel(poster)
        vtt = rnd.VIDEOS_DIR / f"{vid}_{lang}.vtt"
        rnd.write_vtt(vid, lang, vtt)
        entry.update({
            "captions": rnd.rel(vtt),
            "props": rnd.rel(Path(state["props"][lang])),
            "music": track.name if track else None,
            "music_credit": credit,
            "rendered_at": _now(),
        })
        _save_files(vid, **{f"video_{lang}": entry})
        # the narration copy in video/public/renders is only needed while rendering
        (rnd.PUBLIC_RENDERS / f"{vid}_{lang}.mp3").unlink(missing_ok=True)
    return {}


@tracked("index_script")
def index_script(state: VideoState) -> dict:
    from ..services import rag
    from ..services.narration import audio_paths

    for lang in _languages(state):
        narration = json.loads(audio_paths(state["video_id"], lang)[1].read_text(encoding="utf-8"))
        rag.index_script(state["video_id"], lang, narration["scenes"])
    return {}


# ---------- graph ----------

def build_graph(checkpointer) -> Any:
    g = StateGraph(VideoState)
    for name, fn in [
        ("load_quarter", load_quarter),
        ("gather_context", gather_context),
        ("draft_script", draft_script),
        ("factcheck", factcheck),
        ("translate_ar", translate_ar),
        ("factcheck_ar", factcheck_ar),
        ("human_review", human_review),
        ("tts_en", tts_en),
        ("tts_ar", tts_ar),
        ("audio_review", audio_review),
        ("build_props", build_props),
        ("render_en", render_en),
        ("render_ar", render_ar),
        ("mix_audio", mix_audio),
        ("index_script", index_script),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "load_quarter")
    for a, b in zip(NODES, NODES[1:]):
        g.add_edge(a, b)
    g.add_edge(NODES[-1], END)
    return g.compile(checkpointer=checkpointer)


_checkpoint_conn = sqlite3.connect(settings.store_dir / "graph.db", check_same_thread=False)
video_graph = build_graph(SqliteSaver(_checkpoint_conn))


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _run(video_id: str, thread_id: str, title: str, step: Callable[[dict], None]) -> None:
    """Run one stretch of the graph and record how it ended: review, done, stopped or failed."""
    config = _config(thread_id)
    joblog.start(video_id, f"{title} (thread {thread_id})")
    try:
        _update_video(video_id, status="running", error=None)
        step(config)
        if has_pending_review(thread_id):
            _update_video(video_id, status="review", error=None)
            joblog.write("Paused for human review", video_id)
        elif has_pending_audio_review(thread_id):
            _update_video(video_id, status="audio_review", error=None)
            joblog.write("Paused for audio review: listen and approve to start rendering", video_id)
        else:
            _update_video(video_id, status="done", error=None)
            joblog.write("Finished", video_id)
    except jobcontrol.JobStopped:
        joblog.write("Run STOPPED by user", video_id)
        _update_video(video_id, status="stopped", error=None)
    except Exception as exc:
        log.error("Video graph failed for %s: %s", video_id, traceback.format_exc())
        joblog.write(f"Run FAILED: {exc}", video_id)
        _update_video(video_id, status="failed", error=str(exc))


def run_until_review(video_id: str, thread_id: str, company: str, period: str, fresh: bool = False) -> None:
    """Run the graph from the start until it pauses for human review."""
    _run(
        video_id, thread_id, f"Generate {company} {period} from the start (fresh={fresh})",
        lambda config: video_graph.invoke({"video_id": video_id, "company": company, "period": period, "fresh": fresh}, config),
    )


def has_pending_review(thread_id: str) -> bool:
    snapshot = video_graph.get_state(_config(thread_id))
    return "human_review" in (snapshot.next or ())


def has_pending_audio_review(thread_id: str) -> bool:
    return "audio_review" in (video_graph.get_state(_config(thread_id)).next or ())


def approve_audio(video_id: str) -> None:
    """Resume a job paused at audio_review: build props, render, mix (in a background thread)."""
    video = _video_or_raise(video_id)
    if not has_pending_audio_review(video.thread_id):
        raise ValueError("This job is not waiting for audio approval")
    jobcontrol.launch(
        video_id, _run, video_id, video.thread_id, "Audio approved: render the videos",
        lambda config: video_graph.invoke(Command(resume={"approved": True}), config),
    )


def resume_after_review(video_id: str, thread_id: str, decision: dict[str, Any]) -> None:
    """Continue after approval. First approval resumes the interrupt; a re-approval after an
    edit rewinds to just after human_review with the new scenes and runs the rest again."""

    def step(config: dict) -> None:
        if has_pending_review(thread_id):
            video_graph.invoke(Command(resume=decision), config)
        else:
            video_graph.update_state(config, {"review": decision, "scenes": decision["scenes"]}, as_node="human_review")
            video_graph.invoke(None, config)

    _run(video_id, thread_id, "Approved: narrate and render", step)


def approve_video(video_id: str, thread_id: str, decision: dict[str, Any]) -> None:
    """resume_after_review in a background thread (so it can be stopped)."""
    jobcontrol.launch(video_id, resume_after_review, video_id, thread_id, decision)


def _video_or_raise(video_id: str) -> Video:
    with Session(engine) as s:
        video = s.get(Video, video_id)
        if not video:
            raise LookupError(f"No video job '{video_id}'")
        return video


def stop_video(video_id: str) -> str:
    """Ask a running job to stop inside its current step. Returns "stopping" or "stopped"."""
    video = _video_or_raise(video_id)
    if video.status != "running":
        raise ValueError(f"The job is not running (status is '{video.status}')")
    if jobcontrol.request_stop(video_id):
        return "stopping"
    # No live thread (the server restarted mid-run): the job is already dead, just mark it.
    node = video.current_node
    if node and (video.node_status or {}).get(node, {}).get("status") == "running":
        _set_node(video_id, node, status="stopped", finished_at=_now())
    joblog.write("!! Marked stopped (no running thread found; the server probably restarted)", video_id)
    _update_video(video_id, status="stopped", error=None)
    return "stopped"


def retry_video(video_id: str) -> str:
    """Resume a failed or stopped job from the step where it ended (earlier results are kept)."""
    video = _video_or_raise(video_id)
    if video.status not in ("failed", "stopped"):
        raise ValueError(f"Only failed or stopped jobs can be resumed (status is '{video.status}')")
    thread_id, node = video.thread_id, video.current_node
    if not video_graph.get_state(_config(thread_id)).next:
        raise ValueError("Nothing to resume for this job; regenerate from the start instead")
    # LangGraph re-runs the step that raised; the steps before it keep their checkpointed results.
    _update_video(video_id, status="running", error=None)
    jobcontrol.launch(
        video_id, _run, video_id, thread_id, f"Resume from {node or '?'}", lambda config: video_graph.invoke(None, config)
    )
    return node or ""


def rerun_from(video_id: str, node: str) -> str:
    """Run the job again from `node` (any step that has run before), keeping the results of the steps
    before it. Steps that call the LLM skip the cache so they give a fresh answer."""
    if node not in NODES or node in ("human_review", "audio_review"):
        raise ValueError(f"Cannot re-run from '{node}'")
    video = _video_or_raise(video_id)
    if jobcontrol.is_active(video_id):
        raise jobcontrol.JobBusy("The job is still running; stop it first")
    if node == NODES[0]:
        start_video(video.company, video.period, force=True)
        return node
    if NODES.index(node) > NODES.index("human_review"):
        from ..services.script_store import load_script

        script = load_script(video_id)
        if not script or script.get("status") != "approved":
            raise ValueError("The script has changed since it was approved; approve it again to narrate and render")
    thread_id = video.thread_id
    target = next((snap for snap in video_graph.get_state_history(_config(thread_id)) if snap.next == (node,)), None)
    if target is None:
        raise ValueError(f"'{node}' has not run in this job yet, so there is nothing to re-run from")
    prev = NODES[NODES.index(node) - 1]

    def step(config: dict) -> None:
        # Fork from the latest checkpoint just before `node`; the graph continues from there.
        video_graph.update_state(target.config, {"fresh": True}, as_node=prev)
        video_graph.invoke(None, config)

    with Session(engine) as s:
        row = s.get(Video, video_id)
        row.node_status = {k: v for k, v in (row.node_status or {}).items() if NODES.index(k) < NODES.index(node)}
        row.current_node = node
        s.add(row)
        s.commit()
    _update_video(video_id, status="running", error=None)
    jobcontrol.launch(video_id, _run, video_id, thread_id, f"Re-run from {node}", step)
    return node


def start_video(company: str, period: str, force: bool = False) -> tuple[str, bool]:
    """Create or refresh the Video row and run the graph to human review in a background thread.
    Returns (video_id, started). A running job is never started twice."""
    import uuid

    from ..services import quarters as quarters_svc

    found = quarters_svc.get_quarter(company, period)
    if not found:
        raise ValueError(f"No quarter '{period}' for company '{company}'")
    qf, q = found
    video_id = f"{qf.slug}-{quarters_svc.period_slug(q.period)}"
    if jobcontrol.is_active(video_id):
        return video_id, False
    with Session(engine) as s:
        video = s.get(Video, video_id)
        if video and not force and video.status not in ("failed", "stopped"):
            return video_id, False
        video = video or Video(id=video_id, company=qf.slug, period=q.period)
        video.status = "running"
        video.thread_id = f"{video_id}:{uuid.uuid4().hex[:8]}"
        video.node_status = {}
        video.current_node = None
        video.error = None
        video.updated_at = datetime.now(timezone.utc)
        s.add(video)
        s.commit()
        thread_id = video.thread_id
    jobcontrol.launch(video_id, run_until_review, video_id, thread_id, qf.slug, q.period, force)
    return video_id, True
