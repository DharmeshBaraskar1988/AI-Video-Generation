"""Conversation memory for the stock chat.

Short-term: the last WINDOW turns of the current topic, kept verbatim.
Long-term: turns that leave the window stay raw while small; once they exceed SUMMARY_TRIGGER_CHARS
they are folded (one fast-model call) into a dense per-session summary in `ChatMemory`.

`route()` is the chat's single fast-model call per question: it decides whether the question is in
scope (QSE / finance / uploaded documents) or off-topic, which tools answer it, and whether it continues
the recent turns ("follow_up"), refers back to long-term memory ("earlier"), or starts a new topic
("new"), and rewrites it as a standalone question. Memory is only used to understand the question; prices and
changes always come fresh from the price tool, so the summary deliberately keeps no prices.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from ..db import ChatMemory, StockLog, engine
from .llm import LLMError, get_fast_llm, load_prompt

log = logging.getLogger(__name__)

WINDOW = 5  # recent turns kept verbatim
SUMMARY_TRIGGER_CHARS = 1500  # older raw turns above this size are summarised
ANSWER_CHARS = 300  # how much of each answer is shown to the fast model

INTENTS = ["price", "performance", "profile", "documents", "news", "concept", "web", "sources"]
ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {"type": "string", "enum": ["in_scope", "off_topic"]},
        "intents": {"type": "array", "items": {"type": "string", "enum": INTENTS}},
        "relation": {"type": "string", "enum": ["follow_up", "earlier", "new"]},
        "standalone_question": {"type": "string"},
        "companies": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["scope", "intents", "relation", "standalone_question", "companies"],
}
SUMMARY_SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}


def _turn(row: StockLog) -> dict[str, Any]:
    return {
        "question": row.standalone or row.question,
        "answer": row.answer[:ANSWER_CHARS],
        "companies": row.ticker.split(",") if row.ticker else [],
    }


def _chars(turns: list[dict]) -> int:
    return sum(len(t["question"]) + len(t["answer"]) for t in turns)


def _rows(s: Session, session_id: str) -> list[StockLog]:
    return list(s.exec(select(StockLog).where(StockLog.session_id == session_id).order_by(StockLog.id)).all())


def _split(rows: list[StockLog]) -> tuple[list[StockLog], list[StockLog]]:
    """(older, recent): recent = last WINDOW turns since the latest topic start."""
    start = max((i for i, r in enumerate(rows) if r.topic_start), default=0)
    recent_start = max(start, len(rows) - WINDOW)
    return rows[:recent_start], rows[recent_start:]


def load(session_id: str | None) -> dict[str, Any]:
    """{"summary", "older" (raw turns not yet summarised), "recent" (short-term window)}."""
    empty = {"summary": "", "older": [], "recent": []}
    if not session_id:
        return empty
    with Session(engine) as s:
        rows = _rows(s, session_id)
        mem = s.get(ChatMemory, session_id)
    older, recent = _split(rows)
    return {
        "summary": mem.summary if mem else "",
        "older": [_turn(r) for r in older if not r.summarized],
        "recent": [_turn(r) for r in recent],
    }


def has_history(memory: dict[str, Any]) -> bool:
    return bool(memory["summary"] or memory["older"] or memory["recent"])


def route(question: str, memory: dict[str, Any], document_companies: list[str]) -> dict[str, Any]:
    """Scope, intents, relation to history and a standalone question. One fast-model call."""
    payload = {
        "DOCUMENT_COMPANIES": document_companies,
        "LONG_TERM_SUMMARY": memory["summary"] or None,
        "OLDER_TURNS": memory["older"] or None,
        "RECENT_TURNS": memory["recent"] or None,
        "NEW_QUESTION": question,
    }
    llm = get_fast_llm()
    out = llm.generate_json(json.dumps(payload, ensure_ascii=False, indent=1), system=load_prompt("stock_context.md"),
                            temperature=0, schema=ROUTE_SCHEMA)
    relation = out.get("relation") if out.get("relation") in ("follow_up", "earlier", "new") else "new"
    if not has_history(memory):
        relation = "first"
    return {
        "scope": "off_topic" if out.get("scope") == "off_topic" else "in_scope",
        "intents": [i for i in out.get("intents") or [] if i in INTENTS],
        "relation": relation,
        "standalone": (out.get("standalone_question") or "").strip() or question,
        "companies": [c for c in out.get("companies") or [] if isinstance(c, str)],
        "model": llm.last_model,
    }


def summarize_if_needed(session_id: str | None) -> bool:
    """Fold older, unsummarised turns into the long-term summary once they get large. Runs after the
    reply is sent (background task), so it never slows the chat down."""
    if not session_id:
        return False
    with Session(engine) as s:
        rows = _rows(s, session_id)
        mem = s.get(ChatMemory, session_id)
    older, _ = _split(rows)
    pending = [r for r in older if not r.summarized]
    if not pending or _chars([_turn(r) for r in pending]) < SUMMARY_TRIGGER_CHARS:
        return False
    payload = {"PREVIOUS_SUMMARY": mem.summary if mem else None, "TURNS": [_turn(r) for r in pending]}
    try:
        out = get_fast_llm().generate_json(json.dumps(payload, ensure_ascii=False, indent=1),
                                           system=load_prompt("stock_memory.md"), temperature=0.1, schema=SUMMARY_SCHEMA)
    except LLMError as exc:
        log.warning("chat memory summary failed, will retry next turn: %s", exc)
        return False
    summary = (out.get("summary") or "").strip()
    if not summary:
        return False
    with Session(engine) as s:
        mem = s.get(ChatMemory, session_id) or ChatMemory(session_id=session_id)
        mem.summary = summary
        mem.turns += len(pending)
        mem.updated_at = datetime.now(timezone.utc)
        s.add(mem)
        for r in pending:
            row = s.get(StockLog, r.id)
            row.summarized = True
            s.add(row)
        s.commit()
    log.info("chat %s: summarised %d turns into long-term memory", session_id, len(pending))
    return True
