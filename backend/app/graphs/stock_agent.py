"""Stock chat agent (LangGraph).

understand -> [plan (Gemini, only if no company was recognised)] -> fetch (tools) -> write -> log

Tool choice is deterministic: the question's company names, period and "why" decide which tools run
(get_quote, get_history(days), search_news). Gemini is used at most twice: to read an unclear
question (structured output) and to phrase the answer from Python-formatted facts. Every number in
the answer must appear in those facts, otherwise a Python-written answer is used instead. The source
line (source, Doha time, delayed / closed) is always added by Python.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from ..db import StockLog, engine
from ..services import stock
from ..services.llm import LLMError, get_llm, load_prompt
from ..services.summary import unverified_numbers

log = logging.getLogger(__name__)

MAX_COMPANIES = 3
WHY_RE = re.compile(r"\bwhy\b|\breason|\bcause|لماذا|ليش|سبب|أسباب", re.I)
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "companies": {"type": "array", "items": {"type": "string"}},
        "days": {"type": "integer"},
        "why": {"type": "boolean"},
    },
    "required": ["companies", "days", "why"],
}
ANSWER_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}

TEXT = {
    "unavailable": {
        "en": "I can't fetch the price right now because the market data source isn't responding. Please try again in a few minutes.",
        "ar": "لا يمكنني جلب السعر الآن لأن مصدر بيانات السوق لا يستجيب. يرجى المحاولة مرة أخرى بعد بضع دقائق.",
    },
    "unknown": {
        "en": "Which Qatar Stock Exchange company do you mean? For example: Industries Qatar, QNB, Ooredoo.",
        "ar": "ما هي الشركة المدرجة في بورصة قطر التي تقصدها؟ مثلاً: صناعات قطر، بنك قطر الوطني، أريدُ.",
    },
}


class StockState(TypedDict, total=False):
    question: str
    lang: str
    companies: list[dict[str, Any]]
    days: int | None
    why: bool
    planned: bool
    quotes: list[dict[str, Any]]
    histories: list[dict[str, Any]]
    news: dict[str, list[dict[str, Any]]]
    facts: list[dict[str, Any]]
    ok: bool
    error: str | None
    answer: str
    answer_by: str
    source_line: str
    model: str | None


# ---------- parsing ----------

def detect_lang(text: str) -> str:
    return "ar" if re.search(r"[؀-ۿ]", text) else "en"


_AR_NUM = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def parse_days(text: str) -> int | None:
    """Period in calendar days from phrases like 'last month', '3 months', 'this year', 'أسبوع'."""
    t = text.lower().translate(_AR_NUM)
    if re.search(r"\bytd\b|year to date|this year|since (?:the start of the year|january)|منذ بداية (?:العام|السنة)|هذا العام|هذه السنة", t):
        return stock.days_since_year_start()
    m = re.search(r"(\d+)\s*(day|days|يوم|أيام)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(week|weeks|أسبوع|أسابيع)", t)
    if m:
        return int(m.group(1)) * 7
    m = re.search(r"(\d+)\s*(month|months|شهر|أشهر|شهور)", t)
    if m:
        return int(m.group(1)) * 30
    m = re.search(r"(\d+)\s*(year|years|سنة|سنوات|عام|أعوام)", t)
    if m:
        return int(m.group(1)) * 365
    if re.search(r"\bweek\b|weekly|أسبوع", t):
        return 7
    if re.search(r"\bmonth\b|monthly|شهر", t):
        return 30
    if re.search(r"\byear\b|annual|12 months|سنة|عام", t):
        return 365
    if re.search(r"perform|trend|change|move|doing|أداء|تغير|تحرك", t):
        return 30
    return None


# ---------- formatting (all numbers shown to the model and user are made here) ----------

def _signed(x: float | None, places: int = 3) -> str:
    if x is None:
        return "n/a"
    return f"{'+' if x > 0 else ''}{x:.{places}f}"


def _qr(x: float, lang: str) -> str:
    return f"{x:.3f} ريال قطري" if lang == "ar" else f"QR {x:.3f}"


def _direction(x: float | None, lang: str) -> str:
    if x is None or x == 0:
        return "دون تغيير" if lang == "ar" else "unchanged"
    if lang == "ar":
        return "ارتفاع" if x > 0 else "انخفاض"
    return "up" if x > 0 else "down"


def _name(c: dict, lang: str) -> str:
    return c["name_ar"] if lang == "ar" else c["name_en"]


def build_facts(state: StockState) -> list[dict[str, Any]]:
    lang = state["lang"]
    facts = []
    hist_by = {h["symbol"]: h for h in state.get("histories", [])}
    for c, q in zip(state["companies"], state["quotes"]):
        f: dict[str, Any] = {
            "company": _name(c, lang),
            "symbol": c["symbol"],
            "price": _qr(q["price"], lang),
            "day_change": f"{_signed(q['change'])} ({_signed(q['change_pct'], 2)}%)" if q["change"] is not None else "n/a",
            "day_direction": _direction(q["change"], lang),
            "previous_close": _qr(q["previous_close"], lang) if q["previous_close"] else "n/a",
            "price_time": f"{q['as_of_hhmm']} Doha time on {q['as_of_date']}",
            "market_open": q["market_open"],
        }
        h = hist_by.get(c["symbol"])
        if h:
            f["period"] = {
                "days": h["days"],
                "from": f"{_qr(h['start_close'], lang)} on {h['start_date']}",
                "to": f"{_qr(h['end_close'], lang)} on {h['end_date']}",
                "change": f"{_signed(h['change'])} ({_signed(h['change_pct'], 2)}%)",
                "direction": _direction(h["change"], lang),
                "high": f"{_qr(h['high'], lang)} on {h['high_date']}",
                "low": f"{_qr(h['low'], lang)} on {h['low_date']}",
            }
        facts.append(f)
    return facts


def template_answer(state: StockState) -> str:
    """Plain answer written by Python (used when the model is unavailable or its numbers don't match)."""
    parts = []
    for f in state["facts"]:
        if state["lang"] == "ar":
            s = f"{f['company']}: آخر سعر {f['price']}، بتغير {f['day_change']} عن الإغلاق السابق."
            if "period" in f:
                p = f["period"]
                s += f" خلال آخر {p['days']} يوماً تغير السهم {p['change']} (من {p['from']} إلى {p['to']})."
        else:
            s = f"{f['company']} last traded at {f['price']}, {f['day_change']} versus the previous close."
            if "period" in f:
                p = f["period"]
                s += f" Over the last {p['days']} days it moved {p['change']}, from {p['from']} to {p['to']}."
        parts.append(s)
    return " ".join(parts)


def source_line(state: StockState) -> str:
    q = state["quotes"][0]
    closed = not q["market_open"]
    if state["lang"] == "ar":
        return (f"المصدر: Yahoo Finance عبر yfinance، حتى الساعة {q['as_of_hhmm']} بتوقيت الدوحة ({q['as_of_date']})، "
                f"قد تكون الأسعار متأخرة" + ("؛ السوق مغلق حالياً." if closed else "."))
    return (f"Source: {stock.SOURCE}, as of {q['as_of_hhmm']} Doha time ({q['as_of_date']}), may be delayed"
            + ("; market closed." if closed else "."))


# ---------- nodes ----------

def understand(state: StockState) -> dict:
    q = state["question"]
    return {
        "lang": state.get("lang") or detect_lang(q),
        "companies": stock.resolve_companies(q)[:MAX_COMPANIES],
        "days": parse_days(q),
        "why": bool(WHY_RE.search(q)),
        "planned": False,
    }


def plan(state: StockState) -> dict:
    """Only when no company was recognised: let Gemini read the question (structured output)."""
    llm = get_llm()
    try:
        out = llm.generate_json(
            json.dumps({"QUESTION": state["question"]}, ensure_ascii=False),
            system=("Extract from a question about Qatar Stock Exchange shares: the company names mentioned "
                    "(as written, or their common English names), the period in calendar days (0 if none), and whether "
                    "it asks why something happened. Return JSON."),
            temperature=0, schema=PLAN_SCHEMA,
        )
    except LLMError as exc:
        log.warning("stock planner unavailable: %s", exc)
        return {"planned": True}
    found: list[dict] = []
    for name in out.get("companies", []):
        for c in stock.resolve_companies(name):
            if c["symbol"] not in {f["symbol"] for f in found}:
                found.append(c)
    days = out.get("days") or None
    return {"companies": found[:MAX_COMPANIES], "days": state.get("days") or days,
            "why": state.get("why") or bool(out.get("why")), "planned": True, "model": llm.last_model}


def after_understand(state: StockState) -> str:
    if state["companies"]:
        return "fetch"
    return "unknown" if state.get("planned") else "plan"


def fetch(state: StockState) -> dict:
    days = state.get("days")
    if state.get("why") and not days:
        days = 7
    try:
        quotes = [stock.get_quote(c["symbol"]) for c in state["companies"]]
        histories = [stock.get_history(c["symbol"], days) for c in state["companies"]] if days else []
    except stock.StockDataError as exc:
        return {"ok": False, "error": str(exc), "quotes": [], "histories": []}
    news = {c["symbol"]: stock.search_news(c) for c in state["companies"]} if state.get("why") else {}
    return {"ok": True, "error": None, "quotes": quotes, "histories": histories, "news": news, "days": days}


def after_fetch(state: StockState) -> str:
    return "write" if state["ok"] else "unavailable"


def write(state: StockState) -> dict:
    facts = build_facts({**state})
    state = {**state, "facts": facts}
    news = [{"company": c["name_en"], "headlines": [{"title": n["title"], "source": n["source"], "date": n["date"]} for n in items]}
            for c in state["companies"] if (items := state.get("news", {}).get(c["symbol"]))]
    payload = {"LANGUAGE": "Arabic" if state["lang"] == "ar" else "English", "QUESTION": state["question"],
               "FACTS": facts, "NEWS": news}
    answer, by, model = None, "template", state.get("model")
    try:
        llm = get_llm()
        out = llm.generate_json(json.dumps(payload, ensure_ascii=False, indent=1), system=load_prompt("stock.md"),
                                temperature=0.2, schema=ANSWER_SCHEMA)
        text = (out.get("answer") or "").strip()
        bad = unverified_numbers(text, [json.dumps(facts, ensure_ascii=False)])
        if text and not bad:
            answer, by, model = text, "llm", llm.last_model
        else:
            log.warning("stock answer had numbers not in the facts %s; using template", bad)
    except LLMError as exc:
        log.warning("stock writer unavailable, using template: %s", exc)
    if answer is None:
        answer = template_answer(state)
    return {"facts": facts, "answer": answer, "answer_by": by, "model": model, "source_line": source_line(state)}


def unavailable(state: StockState) -> dict:
    return {"answer": TEXT["unavailable"][state["lang"]], "answer_by": "fallback", "source_line": "", "facts": []}


def unknown(state: StockState) -> dict:
    return {"ok": False, "answer": TEXT["unknown"][state["lang"]], "answer_by": "fallback", "source_line": "",
            "facts": [], "quotes": [], "histories": []}


def log_answer(state: StockState) -> dict:
    raw = {k: state.get(k) for k in ("lang", "days", "why", "facts", "quotes", "histories", "news", "error", "answer_by", "model")}
    with Session(engine) as s:
        s.add(StockLog(question=state["question"], ticker=",".join(c["symbol"] for c in state.get("companies", [])) or None,
                       answer=state["answer"], raw=json.loads(json.dumps(raw, default=str)), ok=bool(state.get("ok"))))
        s.commit()
    return {}


def build() -> Any:
    g = StateGraph(StockState)
    for name, fn in [("understand", understand), ("plan", plan), ("fetch", fetch), ("write", write),
                     ("unavailable", unavailable), ("unknown", unknown), ("log", log_answer)]:
        g.add_node(name, fn)
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", after_understand, {"fetch": "fetch", "plan": "plan", "unknown": "unknown"})
    g.add_conditional_edges("plan", after_understand, {"fetch": "fetch", "plan": "unknown", "unknown": "unknown"})
    g.add_conditional_edges("fetch", after_fetch, {"write": "write", "unavailable": "unavailable"})
    for n in ("write", "unavailable", "unknown"):
        g.add_edge(n, "log")
    g.add_edge("log", END)
    return g.compile()


stock_agent = build()


def ask(question: str) -> dict[str, Any]:
    out = stock_agent.invoke({"question": question.strip()})
    companies = out.get("companies", [])
    return {
        "question": out["question"],
        "lang": out["lang"],
        "ok": bool(out.get("ok")),
        "answer": out["answer"],
        "source_line": out.get("source_line", ""),
        "answer_by": out.get("answer_by"),
        "model": out.get("model"),
        "companies": [{"symbol": c["symbol"], "name_en": c["name_en"], "name_ar": c["name_ar"]} for c in companies],
        "quotes": out.get("quotes", []),
        "histories": [{k: v for k, v in h.items() if k != "closes"} | {"closes": h["closes"][-60:]} for h in out.get("histories", [])],
        "news": out.get("news", {}),
    }
