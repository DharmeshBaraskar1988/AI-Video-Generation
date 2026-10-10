from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..config import settings
from ..db import Script, Video, engine
from ..graphs.video_graph import (
    NODES,
    SCENE_TYPES,
    approve_video,
    default_visual,
    has_pending_review,
    mask_figures,
    placeholder_list,
    rerun_from,
    approve_audio,
    retry_video,
    start_video,
    stop_video,
)
from ..services import factcheck as fc
from ..services import jobcontrol, joblog, rag
from ..services import quarters as quarters_svc
from ..services.app_settings import get_setting
from ..services.llm import LLMError, get_llm, load_prompt
from ..services.script_store import load_script, save_script

router = APIRouter(prefix="/api/scripts", tags=["scripts"])
log = logging.getLogger(__name__)


class GenerateRequest(BaseModel):
    company: str
    period: str
    force: bool = False  # regenerate even if a script exists (bypasses the LLM cache for the draft)


def _video_view(v: Video) -> dict:
    return {
        "id": v.id,
        "company": v.company,
        "period": v.period,
        "status": v.status,
        "stop_requested": jobcontrol.stop_requested(v.id),
        "current_node": v.current_node,
        "nodes": [{"name": n, **(v.node_status or {}).get(n, {"status": "pending"})} for n in NODES],
        "error": v.error,
        "files": v.files or {},
        "published": bool(v.published),
        "published_at": v.published_at,
        "updated_at": v.updated_at,
    }


@router.post("")
def generate(req: GenerateRequest) -> dict:
    try:
        video_id, started = start_video(req.company, req.period, force=req.force)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    with Session(engine) as s:
        status = s.get(Video, video_id).status
    return {"video_id": video_id, "status": status, "started": started}


@router.post("/{video_id}/retry")
def retry(video_id: str) -> dict:
    """Resume a failed or stopped job from the step where it ended."""
    try:
        node = retry_video(video_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, jobcontrol.JobBusy) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"video_id": video_id, "status": "running", "from_node": node}


@router.post("/{video_id}/stop")
def stop(video_id: str) -> dict:
    """Stop a running job inside its current step; resume or re-run it afterwards."""
    try:
        status = stop_video(video_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"video_id": video_id, "status": status}


class RerunBody(BaseModel):
    node: str


@router.post("/{video_id}/rerun")
def rerun(video_id: str, body: RerunBody) -> dict:
    """Run the job again from any step that has already run, keeping the steps before it."""
    try:
        node = rerun_from(video_id, body.node)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, jobcontrol.JobBusy) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"video_id": video_id, "status": "running", "from_node": node}


@router.post("/{video_id}/approve-audio")
def approve_audio_endpoint(video_id: str) -> dict:
    """The narrations (with music) sound right: continue to rendering."""
    try:
        approve_audio(video_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, jobcontrol.JobBusy) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"video_id": video_id, "status": "running"}


@router.delete("/{video_id}")
def delete_script(video_id: str) -> dict:
    """Delete a script and its video job: DB rows, script JSON, narration, renders, log, Q&A index."""
    with Session(engine) as s:
        video = s.get(Video, video_id)
        script_row = s.get(Script, video_id)
        if not video and not script_row:
            raise HTTPException(404, f"No script '{video_id}'")
        if video and jobcontrol.is_active(video_id):
            raise HTTPException(409, "This job is still running; stop it first, then delete it")
        if script_row:
            s.delete(script_row)
            s.flush()  # Script references Video
        if video:
            s.delete(video)
        s.commit()

    removed = 0
    folders = [
        settings.outputs_dir / "scripts", settings.outputs_dir / "audio", settings.outputs_dir / "videos",
        settings.outputs_dir / "logs", settings.video_dir / "public" / "renders",
    ]
    for folder in folders:
        if not folder.exists():
            continue
        for path in [*folder.glob(f"{video_id}.*"), *folder.glob(f"{video_id}_*")]:
            if path.is_file():
                path.unlink(missing_ok=True)
                removed += 1
    try:
        rag.collection().delete(where={"$and": [{"kind": "script"}, {"video_id": video_id}]})
    except Exception as exc:  # the index may not exist yet; deleting the script still succeeded
        log.warning("Could not remove %s from the Q&A index: %s", video_id, exc)
    log.info("Deleted script %s (%d files)", video_id, removed)
    return {"video_id": video_id, "deleted": True, "files_removed": removed}


@router.get("/{video_id}/log")
def job_log(video_id: str, lines: int = 400) -> dict:
    return {"video_id": video_id, "lines": joblog.read(video_id, max(1, min(lines, 5000)))}


@router.get("")
def list_scripts() -> list[dict]:
    with Session(engine) as s:
        videos = s.exec(select(Video).order_by(Video.updated_at.desc())).all()
        scripts = {sc.video_id: sc for sc in s.exec(select(Script)).all()}
        out = []
        for v in videos:
            sc = scripts.get(v.id)
            out.append(
                _video_view(v)
                | {
                    "script_status": sc.status if sc else None,
                    "checks": (sc.content or {}).get("checks") if sc else None,
                }
            )
        return out


@router.get("/{video_id}")
def get_script(video_id: str) -> dict:
    with Session(engine) as s:
        video = s.get(Video, video_id)
        if not video:
            raise HTTPException(404, f"No script job '{video_id}'")
        view = _video_view(video)
    return {"job": view, "script": load_script(video_id)}


# ---------- editing (Step 4) ----------

class SceneEdit(BaseModel):
    id: str
    en: str
    ar: str
    type: str | None = None  # required only for a scene added in the editor


class ScenesBody(BaseModel):
    scenes: list[SceneEdit]


class RegenerateBody(BaseModel):
    instruction: str = ""
    scenes: list[SceneEdit] | None = None  # current (unsaved) editor text, for context


def _require_script(video_id: str) -> dict:
    script = load_script(video_id)
    if not script:
        raise HTTPException(404, f"No script '{video_id}'")
    return script


def _apply_edits(script: dict, edits: list[SceneEdit]) -> list[dict]:
    """Return scenes in the edited order with new text. Saved scenes left out are deleted; an id
    the script does not have yet is a new scene and needs a `type`."""
    by_id = {s["id"]: s for s in script["scenes"]}
    ids = [e.id for e in edits]
    if not ids:
        raise HTTPException(400, "A script needs at least one scene")
    if len(set(ids)) != len(ids):
        raise HTTPException(400, "Scene ids must be unique")
    ph = script["placeholders"]
    scenes = []
    for e in edits:
        if e.id in by_id:
            s = dict(by_id[e.id])
        elif e.type in SCENE_TYPES:
            s = {"id": e.id, "type": e.type, "visual": default_visual(e.type, [], ph)}
        else:
            raise HTTPException(400, f"New scene '{e.id}' needs a type: one of {', '.join(SCENE_TYPES)}")
        s["en"], s["ar"] = e.en.strip(), e.ar.strip()
        s["data_keys"] = fc.scene_keys(s["en"], ph)
        visual = dict(s.get("visual") or {})
        if visual.get("highlight") not in s["data_keys"]:
            visual["highlight"] = s["data_keys"][0] if s["data_keys"] else None
        s["visual"] = visual
        scenes.append(s)
    return scenes


def _empty_scenes(scenes: list[dict]) -> list[str]:
    return [s["id"] for s in scenes if not s.get("en", "").strip() or not s.get("ar", "").strip()]


@router.post("/{video_id}/check")
def check_scenes(video_id: str, body: ScenesBody) -> dict:
    """Fact-check unsaved editor text (no LLM call, nothing saved)."""
    script = _require_script(video_id)
    scenes = _apply_edits(script, body.scenes)
    return fc.full_checks(scenes, script["placeholders"], get_setting("arabic_digits"))


@router.put("/{video_id}")
def save_scenes(video_id: str, body: ScenesBody) -> dict:
    """Save edits, re-run the fact check. Any change sends an approved script back to draft."""
    script = _require_script(video_id)
    scenes = _apply_edits(script, body.scenes)
    changed = [
        (s["id"], s["en"], s["ar"]) for s in scenes
    ] != [(s["id"], s["en"], s["ar"]) for s in script["scenes"]]
    script["scenes"] = scenes
    script["checks"] = fc.full_checks(scenes, script["placeholders"], get_setting("arabic_digits"))
    if changed:
        script["status"] = "draft"
        script["edited_at"] = datetime.now(timezone.utc).isoformat()
    save_script(script)
    return script


@router.post("/{video_id}/scenes/{scene_id}/regenerate")
def regenerate_scene(video_id: str, scene_id: str, body: RegenerateBody) -> dict:
    """One LLM call that rewrites a single scene in English and Arabic. Not saved until the editor saves."""
    script = _require_script(video_id)
    current = {s["id"]: s for s in script["scenes"]}
    if body.scenes:
        for e in body.scenes:
            if e.id in current:
                current[e.id] = {**current[e.id], "en": e.en, "ar": e.ar}
            elif e.type in SCENE_TYPES:  # a scene added in the editor but not saved yet
                current[e.id] = {"id": e.id, "type": e.type, "en": e.en, "ar": e.ar}
    if scene_id not in current:
        raise HTTPException(404, f"No scene '{scene_id}'")
    target = current[scene_id]
    ph = script["placeholders"]
    # Context in the editor's order, without scenes deleted there.
    ordered = [current[e.id] for e in body.scenes if e.id in current] if body.scenes else list(current.values())

    found = quarters_svc.get_quarter(script["company"], script["quarter"])
    drivers = [mask_figures(d) for d in found[0].narrative_drivers] if found else []
    en_list = {p["key"]: p for p in placeholder_list(ph, "en")}
    payload = {
        "TYPE": target["type"],
        "INSTRUCTION": body.instruction.strip() or "Write a fresh version of this scene.",
        "CURRENT_EN": target["en"],
        "PLACEHOLDERS": [
            {**en_list[p["key"]], "reads_as_ar": p["reads_as_ar"]} for p in placeholder_list(ph, "ar")
        ],
        "KEY DRIVERS": drivers,
        "SCRIPT": [{"id": s["id"], "type": s["type"], "en": s["en"]} for s in ordered],
    }
    try:
        out = get_llm().generate_json(
            json.dumps(payload, ensure_ascii=False, indent=1),
            system=load_prompt("scene.md"),
            temperature=0.7,
            cache=False,
        )
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc
    en, ar = (out.get("en") or "").strip(), (out.get("ar") or "").strip()
    if not en or not ar:
        raise HTTPException(502, "The model did not return both English and Arabic text")
    scene = {**target, "en": en, "ar": ar, "data_keys": fc.scene_keys(en, ph)}
    return {"scene": scene, "checks": fc.check_script([scene], ph)}


@router.post("/{video_id}/approve")
def approve(video_id: str) -> dict:
    script = _require_script(video_id)
    checks = fc.full_checks(script["scenes"], script["placeholders"], get_setting("arabic_digits"))
    if not checks["passed"]:
        raise HTTPException(409, "Fix the flagged numbers and save before approving")
    empty = _empty_scenes(script["scenes"])
    if empty:
        raise HTTPException(409, f"Scenes {', '.join(empty)} need text in English and Arabic (write or regenerate them)")
    if not checks["length_ok"]:
        en, ar = checks["estimated_seconds_en"], checks["estimated_seconds_ar"]
        too_long = max(en, ar) > checks["max_seconds"]
        raise HTTPException(
            409,
            f"Videos must run {checks['min_seconds'] // 60}-{checks['max_seconds'] // 60} minutes; this script is estimated "
            f"at EN {en}s, AR {ar}s. {'Shorten it' if too_long else 'Add content'} before approving.",
        )
    with Session(engine) as s:
        video = s.get(Video, video_id)
        if not video:
            raise HTTPException(404, f"No script job '{video_id}'")
        if jobcontrol.is_active(video_id):
            raise HTTPException(409, "The job is still running; wait for it or stop it first")
        thread_id = video.thread_id

    script["status"] = "approved"
    script["checks"] = checks
    script["approved_at"] = datetime.now(timezone.utc).isoformat()
    save_script(script)

    decision = {"approved": True, "scenes": script["scenes"]}
    resumed = has_pending_review(thread_id)
    try:
        approve_video(video_id, thread_id, decision)
    except jobcontrol.JobBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"video_id": video_id, "status": "approved", "resumed": resumed}
