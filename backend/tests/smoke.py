"""End-to-end smoke test for the D-Storify POC. Prints a pass/fail table.

Runs from the repo root (the API server does not need to be running):

    backend\\.venv\\Scripts\\python -m backend.tests.smoke              full run (~10 Gemini calls, 4 renders ~50 min)
    backend\\.venv\\Scripts\\python -m backend.tests.smoke --skip-render  everything except the MP4 renders
    backend\\.venv\\Scripts\\python -m backend.tests.smoke --offline      no Gemini calls, no renders (quick health check)

Scripts and videos are created under separate ids (smoke-iqcd-q1-2026, ...) so real scripts waiting for
review are never touched. They are deleted at the end unless --keep is given.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.app.config import settings
from backend.app.db import Script, Video, engine, init_db
from sqlmodel import Session

PERIODS = ["Q1 2026", "Q2 2026"]
QA_QUESTIONS = [
    ("Why was there a loss in Q2?", "covered"),
    ("How strong is the balance sheet?", "covered"),
    ("Who won the football World Cup?", "not_covered"),
]
STOCK_QUESTIONS = [
    ("What is Industries Qatar trading at?", 1),
    ("Compare QNB and Ooredoo over the last month", 2),
    ("كم سعر سهم أريد؟", 1),
]


@dataclass
class Result:
    name: str
    ok: bool | None  # None = skipped
    detail: str = ""
    seconds: float = 0.0


@dataclass
class Runner:
    results: list[Result] = field(default_factory=list)

    def check(self, name: str, fn: Callable[[], str], skip: str | None = None) -> bool:
        if skip:
            self.results.append(Result(name, None, skip))
            print(f"  SKIP  {name}: {skip}", flush=True)
            return True
        t = time.time()
        try:
            detail = fn() or ""
            ok = True
        except AssertionError as exc:
            detail, ok = f"FAILED: {exc}", False
        except Exception as exc:  # noqa: BLE001
            detail, ok = f"ERROR: {type(exc).__name__}: {exc}", False
            traceback.print_exc()
        r = Result(name, ok, detail, time.time() - t)
        self.results.append(r)
        print(f"  {'PASS' if ok else 'FAIL'}  {name} ({r.seconds:.1f}s): {detail}", flush=True)
        return ok

    def table(self) -> int:
        width = max(len(r.name) for r in self.results)
        print("\n" + "=" * (width + 70))
        print(f"{'Check'.ljust(width)}  Result  Time    Detail")
        print("-" * (width + 70))
        for r in self.results:
            status = "SKIP" if r.ok is None else "PASS" if r.ok else "FAIL"
            print(f"{r.name.ljust(width)}  {status:<6}  {r.seconds:>5.1f}s  {r.detail[:110]}")
        failed = [r for r in self.results if r.ok is False]
        passed = sum(1 for r in self.results if r.ok)
        print("-" * (width + 70))
        print(f"{passed} passed, {len(failed)} failed, {sum(1 for r in self.results if r.ok is None)} skipped")
        return 1 if failed else 0


def smoke_id(period: str) -> str:
    return f"smoke-iqcd-{period.lower().replace(' ', '-')}"


def ffprobe(path: Path) -> dict[str, Any]:
    from backend.app.services.render import find_ffmpeg

    out = subprocess.run(
        [find_ffmpeg("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="no Gemini calls and no renders")
    ap.add_argument("--skip-render", action="store_true", help="skip the Remotion renders")
    ap.add_argument("--keep", action="store_true", help="keep the smoke scripts/videos for inspection")
    args = ap.parse_args()
    use_llm = not args.offline
    render = use_llm and not args.skip_render

    init_db()
    run = Runner()
    no_llm = "--offline: no Gemini calls" if args.offline else None
    print(f"D-Storify smoke test  (llm={'on' if use_llm else 'off'}, render={'on' if render else 'off'})\n")

    # ---------- environment ----------
    def env() -> str:
        from backend.app.services.render import find_ffmpeg, npx

        assert settings.gemini_api_key, "GEMINI_API_KEY missing in .env"
        assert (settings.music_dir / "LICENSES.txt").exists(), "data/music/LICENSES.txt missing"
        return f"ffmpeg={Path(find_ffmpeg()).name}, npx ok ({Path(npx()).name}), model={settings.gemini_model}"

    run.check("environment (key, FFmpeg, Node)", env)

    # ---------- quarters ----------
    def quarters() -> str:
        from backend.app.services.quarters import get_quarter, load_all

        files, errors = load_all()
        assert not errors, f"quarter file errors: {errors}"
        _, q2 = get_quarter("iqcd", "Q2 2026")
        assert q2.derived and q2.net_profit == -518, f"Q2 should be derived with net loss 518, got {q2.net_profit}"
        return f"{sum(len(f.quarters) for f in files.values())} periods; Q2 derived, net loss 518"

    run.check("quarter data", quarters)

    def factcheck_negative() -> str:
        from backend.app.services import factcheck as fc
        from backend.app.services.quarters import get_quarter

        qf, q = get_quarter("iqcd", "Q2 2026")
        ph = fc.build_placeholders(qf, q)
        clean = [{"id": "s1", "en": "Revenue came to {{revenue}}.", "ar": "بلغت الإيرادات {{revenue}}."}]
        assert fc.checks_pass(fc.check_script(clean, ph)), "clean scene should pass"
        dirty = [{"id": "s1", "en": "Revenue came to {{revenue}}, about 600 million lower.", "ar": "بلغت الإيرادات {{revenue}}."}]
        c = fc.check_script(dirty, ph)
        assert not fc.checks_pass(c) and {s["text"] for s in c["stray_numbers"]} >= {"600", "million"}, c
        return "typed '600 million' is flagged; placeholders pass"

    run.check("fact-check catches typed numbers", factcheck_negative)

    # ---------- scripts -> review -> narration -> render ----------
    from backend.app.graphs import video_graph as vg
    from backend.app.services.script_store import load_script

    created: list[str] = []
    for period in PERIODS:
        vid = smoke_id(period)

        def generate(vid: str = vid, period: str = period) -> str:
            with Session(engine) as s:
                s.merge(Video(id=vid, company="iqcd", period=period, status="running",
                              thread_id=f"{vid}:{uuid.uuid4().hex[:8]}"))
                s.commit()
                thread = s.get(Video, vid).thread_id
            created.append(vid)
            vg.run_until_review(vid, thread, "iqcd", period)
            with Session(engine) as s:
                video = s.get(Video, vid)
                assert video.status == "review", f"expected review, got {video.status}: {video.error}"
            c = load_script(vid)["checks"]
            assert c["numbers_ok"] == c["numbers_total"] and not c["stray_numbers"], f"number check failed: {c}"
            assert not c["placeholder_mismatch"], f"Arabic placeholders differ: {c['placeholder_mismatch']}"
            assert c["length_ok"], f"too short: EN {c['estimated_seconds_en']}s AR {c['estimated_seconds_ar']}s"
            return (f"{c['numbers_ok']}/{c['numbers_total']} numbers verified, EN ~{c['estimated_seconds_en']}s, "
                    f"AR ~{c['estimated_seconds_ar']}s, model {load_script(vid)['model']}")

        ok = run.check(f"{period}: script EN+AR + fact-check", generate, skip=no_llm)

        def approve_and_produce(vid: str = vid) -> str:
            with Session(engine) as s:
                thread = s.get(Video, vid).thread_id
            script = load_script(vid)
            script["status"] = "approved"
            from backend.app.services.script_store import save_script

            save_script(script)
            if not render:  # stop after narration: run only the TTS nodes
                for lang in ("en", "ar"):
                    from backend.app.services.narration import narrate

                    info = narrate(vid, lang, script["scenes"], script["placeholders"])
                    assert info["timings_ok"], f"{lang} word timings failed"
                    assert info["length_ok"], f"{lang} narration only {info['duration']}s (must be 2-3 minutes)"
                return "narration EN+AR OK (render skipped)"
            vg.resume_after_review(vid, thread, {"approved": True, "scenes": script["scenes"]})
            with Session(engine) as s:
                video = s.get(Video, vid)
                assert video.status == "done", f"expected done, got {video.status}: {video.error}"
                files = video.files
            parts = []
            for lang in ("en", "ar"):
                assert files[f"audio_{lang}"]["timings_ok"], f"{lang} word timings failed"
                mp4 = settings.outputs_dir / files[f"video_{lang}"]["video"]
                info = ffprobe(mp4)
                kinds = {st["codec_type"] for st in info["streams"]}
                dur = float(info["format"]["duration"])
                assert {"video", "audio"} <= kinds, f"{lang} mp4 streams: {kinds}"
                assert dur >= 120, f"{lang} video only {dur:.0f}s"
                social = settings.outputs_dir / files[f"video_{lang}"]["social"]
                assert social.exists(), f"{lang} social cut missing"
                parts.append(f"{lang.upper()} {dur:.0f}s")
            return "videos " + ", ".join(parts) + " (+ social cuts)"

        run.check(f"{period}: approve -> narration{' -> render + music' if render else ''}", approve_and_produce,
                  skip=no_llm if no_llm else (None if ok else "script failed"))

    # offline narration check (edge-tts, no LLM): narrate two scenes of an existing script
    def narration_offline() -> str:
        from backend.app.services.narration import audio_paths, narrate

        src = next((load_script(i) for i in ("iqcd-q1-2026", "iqcd-q2-2026") if load_script(i)), None)
        assert src, "no existing script to narrate; generate one from the dashboard first"
        vid = "smoke-narration"
        created.append(vid)
        info = narrate(vid, "ar", src["scenes"][:2], src["placeholders"])
        assert info["timings_ok"], "word timings failed"
        assert not info["length_ok"], "a two-scene excerpt should be flagged as under 2 minutes"
        words = json.loads(audio_paths(vid, "ar")[1].read_text(encoding="utf-8"))["words"]
        assert all(b["start"] >= a["start"] for a, b in zip(words, words[1:])), "timings not monotonic"
        return (f"Arabic voice {info['voice']}: {len(words)} words, {info['duration']}s, timings monotonic; "
                f"short excerpt correctly flagged under 2 min")

    run.check("narration (edge-tts, word timings)", narration_offline, skip=None if args.offline else "covered by the runs above")

    # ---------- documents ----------
    def documents() -> str:
        from backend.app.services import rag

        docs = [d for d in rag.list_documents() if d["indexed"]]
        assert docs, "no indexed documents: upload results documents on the Documents page"
        assert all(d["company"] and d["period"] for d in docs), "some documents have no company/period"
        d0 = docs[0]
        hits = rag.search("revenue net profit for the period", k=3, where=rag.doc_where(d0["company"], d0["period"]))
        assert hits and all(h["company"] == d0["company"] for h in hits), "company filter returned other companies"
        groups = sorted({f"{d['company']} {d['period']}" for d in docs})
        return f"{len(docs)} documents in {len(groups)} company/period groups; filtered search OK"

    run.check("documents: indexed by company/period + search", documents)

    def data_review() -> str:
        from backend.app.services import doc_agent

        reviews = doc_agent.list_reviews()
        assert reviews, "no data reviews yet"
        bad = [r["id"] for r in reviews if r["status"] == "failed"]
        assert not bad, f"failed extractions: {bad}"
        return ", ".join(f"{r['id']} {r['status']} ({(r['checks'] or {}).get('verified', 0)}/{(r['checks'] or {}).get('figures', 0)} verified)" for r in reviews)

    run.check("document agent: extracted data reviews", data_review)

    def summary_present() -> str:
        from backend.app.services import summary

        opts = [o for o in summary.available() if o["has_summary"]]
        if not opts:
            return "no summary generated yet (Summary page > Generate)"
        s = summary.load(opts[0]["company"], opts[0]["period"])
        c = s["checks"]
        assert c["uncited"] == 0, f"{c['uncited']} uncited points"
        return f"{opts[0]['company']} {opts[0]['period']}: {c['bullets']} points, {c['verified']} with every number found in the cited source"

    run.check("summary: citations + number check", summary_present)

    # ---------- video Q&A ----------
    from backend.app.graphs.qa_graph import ask as qa_ask

    qa_video = next((v for v in (smoke_id("Q2 2026"), "iqcd-q2-2026", "iqcd-q1-2026")
                     if (settings.outputs_dir / "audio" / f"{v}_en_words.json").exists()), None)

    def index_for_qa() -> str:
        from backend.app.services import rag

        assert qa_video, "no narrated video to ask about"
        for lang in ("en", "ar"):
            n = json.loads((settings.outputs_dir / "audio" / f"{qa_video}_{lang}_words.json").read_text(encoding="utf-8"))
            rag.index_script(qa_video, lang, n["scenes"])
        return f"script of {qa_video} indexed with scene times"

    run.check("Q&A: index video script", index_for_qa)

    for question, expect in QA_QUESTIONS:
        def qa(question: str = question, expect: str = expect) -> str:
            r = qa_ask(qa_video, question)
            if expect == "covered":
                assert r["covered"] and r["citations"], f"expected a cited answer, got: {r['answer']}"
                assert not r["unverified"], f"numbers not in sources: {r['unverified']}"
                ts = f", jumps to {r['timestamp']['seconds']:.0f}s" if r["timestamp"] else ", no timestamp"
                return f"{len(r['citations'])} citations{ts}: {r['answer'][:60]}"
            assert not r["covered"], f"should be not covered, got: {r['answer']}"
            return "declined (not covered)"

        needs_llm = expect == "covered"
        run.check(f"Q&A: {question}", qa, skip=no_llm if needs_llm else None)

    # ---------- stock chat ----------
    from backend.app.graphs.stock_agent import ask as stock_ask, template_answer
    from backend.app.services import stock

    def stock_data() -> str:
        q = stock.get_quote("IQCD.QA")
        h = stock.get_history("IQCD.QA", 30)
        assert q["price"] > 0 and q["as_of"], "no price"
        pct = round((h["end_close"] - h["start_close"]) / h["start_close"] * 100, 2)
        assert abs(pct - h["change_pct"]) < 0.02, "change not computed consistently"
        return f"IQCD {q['price']} QAR as of {q['as_of_hhmm']} Doha ({'open' if q['market_open'] else 'closed'}), 30d {h['change_pct']}%"

    run.check("stock: live quote + history", stock_data)

    for question, n in STOCK_QUESTIONS:
        def sq(question: str = question, n: int = n) -> str:
            r = stock_ask(question)
            assert r["ok"], f"not ok: {r['answer']}"
            assert len(r["quotes"]) == n, f"expected {n} quotes, got {len(r['quotes'])}"
            assert r["source_line"] and ("Doha" in r["source_line"] or "الدوحة" in r["source_line"]), "source line missing"
            return f"[{r['answer_by']}] {r['answer'][:70]}"

        run.check(f"stock: {question}", sq, skip=no_llm)

    def stock_offline_template() -> str:
        state = {"lang": "en", "companies": [stock.find_by_symbol("IQCD")], "quotes": [stock.get_quote("IQCD.QA")], "histories": []}
        from backend.app.graphs.stock_agent import build_facts, source_line

        state["facts"] = build_facts(state)
        text = template_answer(state)
        assert "QR" in text and source_line(state).startswith("Source:"), text
        return text[:90]

    run.check("stock: answer without the LLM (fallback)", stock_offline_template)

    # ---------- cleanup ----------
    if not args.keep:
        cleanup(created)
    return run.table()


def cleanup(video_ids: list[str]) -> None:
    from backend.app.services import rag

    for vid in set(video_ids):
        with Session(engine) as s:
            for model in (Script, Video):
                row = s.get(model, vid)
                if row:
                    s.delete(row)
            s.commit()
        for folder in ("audio", "videos", "scripts"):
            for p in (settings.outputs_dir / folder).glob(f"{vid}*"):
                p.unlink(missing_ok=True) if p.is_file() else shutil.rmtree(p, ignore_errors=True)
        try:
            rag.collection().delete(where={"$and": [{"kind": "script"}, {"video_id": vid}]})
        except Exception:  # noqa: BLE001
            pass
    if video_ids:
        print(f"\ncleaned up: {', '.join(sorted(set(video_ids)))}  (use --keep to inspect them)")


if __name__ == "__main__":
    sys.exit(main())
