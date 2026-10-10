"""Video Q&A graph (LangGraph).

retrieve_script -> retrieve_documents -> select -> (answer | not_covered) -> log

Script chunks of this video come first, then document chunks; the top 8 go to Gemini, which
answers only from them. Below the score threshold the reply is "not covered" without an LLM
call. The jump-to timestamp is picked in Python from the cited script scene, never by the LLM.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from ..db import QALog, engine
from ..services import rag
from ..services.llm import get_llm, load_prompt
from ..services.summary import unverified_numbers

log = logging.getLogger(__name__)

TOP_K = 8
SCRIPT_K = 4
# Calibrated on the demo index: on-topic questions score >= 0.72 (EN) / >= 0.62 (AR),
# off-topic ones <= 0.64 (EN) / <= 0.65 (AR). Arabic overlaps, so Gemini is the second gate.
THRESHOLD = {"en": 0.68, "ar": 0.60}
NOT_COVERED = {
    "en": "This is not covered in this video or the results documents.",
    "ar": "هذا السؤال غير مغطى في هذا الفيديو أو في وثائق النتائج.",
}
QA_SCHEMA = {
    "type": "object",
    "properties": {
        "covered": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["covered", "answer", "citations"],
}


class QAState(TypedDict, total=False):
    video_id: str
    company: str  # document search is limited to this company's documents
    question: str
    lang: str  # language of the question / answer
    watch_lang: str  # language of the video being watched (for the timestamp)
    script_hits: list[dict[str, Any]]
    doc_hits: list[dict[str, Any]]
    passages: list[dict[str, Any]]
    top_score: float
    covered: bool
    answer: str
    citations: list[dict[str, Any]]
    timestamp: dict[str, Any] | None
    unverified: list[str]
    model: str | None


def detect_lang(text: str) -> str:
    return "ar" if re.search(r"[؀-ۿ]", text) else "en"


def retrieve_script(state: QAState) -> dict:
    where = {"$and": [{"kind": "script"}, {"video_id": state["video_id"]}]}
    return {"script_hits": rag.search(state["question"], k=SCRIPT_K, where=where)}


def retrieve_documents(state: QAState) -> dict:
    return {"doc_hits": rag.search(state["question"], k=TOP_K, where=rag.doc_where(state.get("company") or None))}


def select(state: QAState) -> dict:
    # script first (deduplicated by scene: EN and AR versions of a scene say the same thing)
    passages, scenes = [], set()
    for h in state["script_hits"]:
        if h["scene"] not in scenes:
            scenes.add(h["scene"])
            passages.append(h)
    passages += state["doc_hits"]
    passages = passages[:TOP_K]
    top = max((p["score"] for p in passages), default=0.0)
    return {"passages": passages, "top_score": top}


def route(state: QAState) -> str:
    return "answer" if state["top_score"] >= THRESHOLD[state["lang"]] else "not_covered"


def _label(i: int, p: dict) -> str:
    return f"{'S' if p['kind'] == 'script' else 'D'}{i + 1}"


def _timestamp(state: QAState, cited: list[dict]) -> dict | None:
    """Start of the first cited scene, in the language of the video being watched."""
    scene = next((p for p in cited if p["kind"] == "script"), None)
    if not scene:
        return None
    watch = state["watch_lang"]
    if scene["lang"] != watch:
        same = rag.get_chunks([f"script:{state['video_id']}:{watch}:{scene['scene']}"])
        if same:
            scene = same[0]
    return {"seconds": round(float(scene["start"]), 2), "lang": scene["lang"], "scene": scene["scene"],
            "scene_type": scene["scene_type"]}


def answer(state: QAState) -> dict:
    labelled = {_label(i, p): p for i, p in enumerate(state["passages"])}
    payload = {
        "LANGUAGE": "Arabic" if state["lang"] == "ar" else "English",
        "QUESTION": state["question"],
        "PASSAGES": [
            {"label": lab, "kind": p["kind"],
             **({"scene": p["scene_type"]} if p["kind"] == "script" else {"file": p["file"], "page": p["page"], "section": p["section"]}),
             "text": p["text"][:2500]}
            for lab, p in labelled.items()
        ],
    }
    llm = get_llm()
    out = llm.generate_json(json.dumps(payload, ensure_ascii=False, indent=1), system=load_prompt("qa.md"),
                            temperature=0.2, schema=QA_SCHEMA)
    cited = [labelled[c] for c in out.get("citations", []) if c in labelled]
    text = (out.get("answer") or "").strip()
    if not out.get("covered") or not text or not cited:
        return {"covered": False, "answer": NOT_COVERED[state["lang"]], "citations": [], "timestamp": None,
                "unverified": [], "model": llm.last_model}
    citations = [
        {"kind": "script", "scene": p["scene"], "scene_type": p["scene_type"], "lang": p["lang"], "start": p["start"], "text": p["text"]}
        if p["kind"] == "script"
        else {"kind": "document", "file": p["file"], "page": p["page"], "section": p["section"], "text": p["text"]}
        for p in cited
    ]
    return {
        "covered": True,
        "answer": text,
        "citations": citations,
        "timestamp": _timestamp(state, cited),
        "unverified": unverified_numbers(text, [p["text"] for p in cited]),
        "model": llm.last_model,
    }


def not_covered(state: QAState) -> dict:
    return {"covered": False, "answer": NOT_COVERED[state["lang"]], "citations": [], "timestamp": None,
            "unverified": [], "model": None}


def log_answer(state: QAState) -> dict:
    with Session(engine) as s:
        s.add(QALog(
            video_id=state["video_id"], lang=state["lang"], question=state["question"], answer=state["answer"],
            covered=state["covered"], top_score=state["top_score"],
            citations=[{k: v for k, v in c.items() if k != "text"} for c in state["citations"]],
        ))
        s.commit()
    return {}


def build() -> Any:
    g = StateGraph(QAState)
    for name, fn in [("retrieve_script", retrieve_script), ("retrieve_documents", retrieve_documents),
                     ("select", select), ("answer", answer), ("not_covered", not_covered), ("log", log_answer)]:
        g.add_node(name, fn)
    g.add_edge(START, "retrieve_script")
    g.add_edge("retrieve_script", "retrieve_documents")
    g.add_edge("retrieve_documents", "select")
    g.add_conditional_edges("select", route, {"answer": "answer", "not_covered": "not_covered"})
    g.add_edge("answer", "log")
    g.add_edge("not_covered", "log")
    g.add_edge("log", END)
    return g.compile()


qa_graph = build()


def ask(video_id: str, question: str, watch_lang: str = "en", lang: str | None = None) -> dict[str, Any]:
    q = question.strip()
    lang = lang or detect_lang(q)
    from sqlmodel import Session as _S

    from ..db import Video

    with _S(engine) as s:
        video = s.get(Video, video_id)
        company = video.company if video else ""
    out = qa_graph.invoke({"video_id": video_id, "company": company, "question": q, "lang": lang, "watch_lang": watch_lang})
    return {k: out.get(k) for k in ("question", "lang", "covered", "answer", "citations", "timestamp", "unverified",
                                     "top_score", "model")}
