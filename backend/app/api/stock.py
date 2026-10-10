from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import ChatMemory, StockLog, engine
from ..graphs.stock_agent import ask, public_evidence, public_profiles
from ..services import chat_memory, stock

router = APIRouter(prefix="/api/stock", tags=["stock"])


class ChatBody(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    session_id: str | None = Field(default=None, max_length=64)


def _memory_info(session_id: str | None) -> dict:
    mem = chat_memory.load(session_id)
    return {"summary": mem["summary"], "recent_turns": len(mem["recent"]), "older_turns": len(mem["older"])}


@router.post("/chat")
def chat(body: ChatBody, background: BackgroundTasks) -> dict:
    reply = ask(body.question, body.session_id)
    reply["memory"] = _memory_info(body.session_id)
    # Long-term summary is written after the reply is sent, so it never slows the chat.
    background.add_task(chat_memory.summarize_if_needed, body.session_id)
    return reply


@router.get("/session/{session_id}")
def session_history(session_id: str) -> dict:
    """Turns of a chat (to restore it after a page reload) plus its memory state."""
    with Session(engine) as s:
        rows = s.exec(select(StockLog).where(StockLog.session_id == session_id).order_by(StockLog.id)).all()
    turns = []
    for r in rows:
        raw = r.raw or {}
        turns.append({
            "question": r.question, "standalone": r.standalone, "relation": raw.get("relation"),
            "memory_model": raw.get("memory_model"), "session_id": session_id,
            "lang": raw.get("lang") or "en", "ok": r.ok, "answer": r.answer, "source_line": raw.get("source_line") or "",
            "answer_by": raw.get("answer_by"), "model": raw.get("model"), "companies": raw.get("companies") or [],
            "quotes": raw.get("quotes") or [],
            "histories": [h | {"closes": h.get("closes", [])[-60:]} for h in raw.get("histories") or []],
            "scope": raw.get("scope") or "in_scope", "intents": raw.get("intents") or [],
            "profiles": public_profiles(raw.get("profiles") or []), "evidence": public_evidence(raw.get("evidence") or []),
        })
    return {"session_id": session_id, "turns": turns, "memory": _memory_info(session_id)}


@router.delete("/session/{session_id}")
def forget_session(session_id: str) -> dict:
    """Forget a chat's memory (the turns stay in the stock log, detached from the session)."""
    with Session(engine) as s:
        for r in s.exec(select(StockLog).where(StockLog.session_id == session_id)).all():
            r.session_id = None
            s.add(r)
        if mem := s.get(ChatMemory, session_id):
            s.delete(mem)
        s.commit()
    return {"ok": True}


@router.get("/companies")
def list_companies() -> list[dict]:
    return [{k: c[k] for k in ("symbol", "code", "name_en", "name_ar", "sector")} for c in stock.companies()]


@router.get("/quote/{symbol}")
def quote(symbol: str) -> dict:
    if not stock.find_by_symbol(symbol):
        raise HTTPException(404, f"Unknown QSE symbol '{symbol}'")
    sym = symbol.upper() if symbol.upper().endswith(".QA") else f"{symbol.upper()}.QA"
    try:
        return stock.get_quote(sym)
    except stock.StockDataError as exc:
        raise HTTPException(503, f"Price source unavailable: {exc}") from exc


@router.get("/log")
def stock_log(limit: int = 50) -> list[StockLog]:
    with Session(engine) as s:
        return list(s.exec(select(StockLog).order_by(StockLog.created_at.desc()).limit(limit)).all())
