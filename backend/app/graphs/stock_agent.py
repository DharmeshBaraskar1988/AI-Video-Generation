"""Stock chat agent (LangGraph).

route -> understand -> [plan (only if the router failed and no company was recognised)]
      -> gather (tools) -> write -> log          (off-topic questions -> off_topic -> log)

route (`services/chat_memory.py`, one fast lite-model call): is the question in scope (QSE companies,
markets, finance, uploaded results documents) or off-topic (politics, sport, ...)? Which intents
(price, performance, profile, documents, news, concept)? Does it follow the last 5 turns, refer to
long-term memory, or start a new topic? It also rewrites the question as a standalone question.

gather runs only the tools the intents need: get_quote, get_history(days), get_profile, search_news,
and RAG search over the uploaded results documents (filtered by company when known). Everything
becomes labelled evidence (Q price, C company profile, D document page, N news). The writer (main
model, one call) answers only from that evidence and cites labels; every number in the answer must
appear in the price/profile facts or the document passages, otherwise a Python-written answer is used.
Memory never supplies a number. The source line is always added by Python.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict
from urllib.parse import quote as urlquote

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session, select

from ..db import Document, StockLog, engine
from ..services import chat_memory, rag, stock
from ..services.llm import LLMError, get_llm, load_prompt
from ..services.summary import unverified_numbers

log = logging.getLogger(__name__)

MAX_COMPANIES = 3
DOC_K = 4  # passages per company
DOC_MAX = 6  # passages shown to the writer
# Same calibration as the video Q&A; a company filter already keeps passages on topic, so it is relaxed there.
DOC_THRESHOLD = {"en": 0.68, "ar": 0.60}
DOC_THRESHOLD_FILTERED = {"en": 0.62, "ar": 0.56}
WHY_RE = re.compile(r"\bwhy\b|\breason|\bcause|لماذا|ليش|سبب|أسباب", re.I)
# Fallback intent detection when the router model is unavailable
DOCS_RE = re.compile(r"revenue|profit|loss|income|result|report|quarter|\bq[1-4]\b|\bh[12]\b|\bfy\b|segment|asset|deposit|"
                     r"loan|outlook|earnings|إيرادات|أرباح|ربح|خسار|نتائج|تقرير|ربع", re.I)
PROFILE_RE = re.compile(r"about|detail|website|url|link|sector|business|market cap|dividend|p/e|\bpe\b|eps|52|"
                        r"profile|معلومات|تفاصيل|موقع|قطاع|توزيع", re.I)
NEWS_RE = re.compile(r"\bnews\b|headline|أخبار|خبر", re.I)
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "companies": {"type": "array", "items": {"type": "string"}},
        "days": {"type": "integer"},
        "why": {"type": "boolean"},
    },
    "required": ["companies", "days", "why"],
}
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "citations": {"type": "array", "items": {"type": "string"}}},
    "required": ["answer", "citations"],
}
QATAR_RE = re.compile(r"qatar|doha|qe\.com\.qa|qfma|قطر|الدوحة", re.I)
MULTI_LABEL_RE = re.compile(r"\[((?:[QCDNWP]\d+\s*[,;]\s*)+[QCDNWP]\d+)\]")
_MONTHS = (r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?")
DATE_RE = re.compile(rf"\b{_MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS},?\s+\d{{4}}\b", re.I)
NUMBER_RE = re.compile(r"\$?\d[\d,.]*%?")
LABEL_RE = re.compile(r"\[([QCDNWP]\d+)\]")

TEXT = {
    "unavailable": {
        "en": "I can't fetch the price right now because the market data source isn't responding. Please try again in a few minutes.",
        "ar": "لا يمكنني جلب السعر الآن لأن مصدر بيانات السوق لا يستجيب. يرجى المحاولة مرة أخرى بعد بضع دقائق.",
    },
    "unknown": {
        "en": "Which Qatar Stock Exchange company do you mean? For example: Industries Qatar, QNB, Ooredoo.",
        "ar": "ما هي الشركة المدرجة في بورصة قطر التي تقصدها؟ مثلاً: صناعات قطر، بنك قطر الوطني، أريدُ.",
    },
    "off_topic": {
        "en": ("I can only help with the Qatar Stock Exchange and financial topics: share prices and performance, company "
               "details, results from the uploaded reports, market news and finance concepts. Try asking about a listed company, "
               "for example \"Tell me about QNB\"."),
        "ar": ("يمكنني المساعدة فقط في موضوعات بورصة قطر والشؤون المالية: أسعار الأسهم وأداؤها، وتفاصيل الشركات، ونتائج التقارير "
               "المرفوعة، وأخبار السوق، والمفاهيم المالية. جرّب السؤال عن شركة مدرجة، مثلاً \"أخبرني عن بنك قطر الوطني\"."),
    },
    "no_evidence": {
        "en": "I couldn't find this in the market data or the uploaded results documents.",
        "ar": "لم أجد هذا في بيانات السوق أو في وثائق النتائج المرفوعة.",
    },
    "docs_below": {
        "en": "The most relevant passages from the uploaded results documents are listed below.",
        "ar": "أبرز المقاطع ذات الصلة من وثائق النتائج المرفوعة مدرجة أدناه.",
    },
}


class StockState(TypedDict, total=False):
    question: str  # as typed by the user
    session_id: str | None
    standalone: str  # question with the conversation's context filled in (what tools and writer use)
    relation: str  # "first" | "follow_up" | "earlier" | "new"
    scope: str  # "in_scope" | "off_topic"
    intents: list[str]
    routed_companies: list[str]  # names the router found
    recent_companies: list[str]  # symbols of the previous turn (fallback for follow-ups)
    memory_model: str | None
    lang: str
    companies: list[dict[str, Any]]
    doc_companies: list[str]  # document company slugs to search
    days: int | None
    why: bool
    planned: bool
    quotes: list[dict[str, Any]]
    histories: list[dict[str, Any]]
    profiles: list[dict[str, Any]]
    news: dict[str, list[dict[str, Any]]]
    passages: list[dict[str, Any]]
    web: list[dict[str, Any]]  # web results + official links (W)
    previous_evidence: list[dict[str, Any]]  # sources of the previous answer (P), for "where did you get this"
    facts: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
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


def guess_intents(text: str) -> list[str]:
    """Used only when the router model is unavailable."""
    intents = ["price"]
    if parse_days(text):
        intents.append("performance")
    if PROFILE_RE.search(text):
        intents.append("profile")
    if DOCS_RE.search(text) or WHY_RE.search(text):
        intents.append("documents")
    if NEWS_RE.search(text) or WHY_RE.search(text):
        intents.append("news")
    return intents


_SUFFIX_RE = re.compile(r"\b(group|company|holding|q ?[cp] ?s ?c|qpsc|qcsc|qsc|plc|ltd)\b")


def document_companies() -> dict[str, dict[str, Any]]:
    """Companies that have indexed uploaded documents: slug -> names, ticker, periods."""
    with Session(engine) as s:
        docs = s.exec(select(Document).where(Document.company.is_not(None))).all()
    out: dict[str, dict[str, Any]] = {}
    for d in docs:
        c = (d.meta or {}).get("company") or {}
        entry = out.setdefault(d.company, {"slug": d.company, "name_en": c.get("name_en") or d.company,
                                           "name_ar": c.get("name_ar") or "", "ticker": c.get("ticker") or "", "periods": []})
        if d.period and d.period not in entry["periods"]:
            entry["periods"].append(d.period)
    return out


def match_document_companies(text: str, companies: list[dict], docs: dict[str, dict]) -> list[str]:
    slugs = [c["code"].lower() for c in companies if c["code"].lower() in docs]
    t = stock.normalize(text)
    for slug, d in docs.items():
        if slug in slugs:
            continue
        for name in (d["name_en"], d["name_ar"]):
            core = _SUFFIX_RE.sub(" ", stock.normalize(name or "")).strip()
            if len(core) > 3 and core in t:
                slugs.append(slug)
                break
    return slugs[:MAX_COMPANIES]


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
    by_symbol = {c["symbol"]: c for c in state["companies"]}
    for q in state.get("quotes", []):
        c = by_symbol[q["symbol"]]
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


PROFILE_FIELDS = ["name", "website", "sector", "industry", "city", "employees", "summary", "market_cap", "pe_trailing",
                  "eps_trailing", "dividend_per_share", "dividend_yield", "price_to_book", "week52_range", "avg_50d",
                  "avg_200d", "revenue_ttm", "net_income_ttm"]


def _doc_title(file: str) -> str:
    return re.sub(r"^\d{14}_(\d+-\d+-)?", "", file).replace("+", " ").replace("_", " ")


def build_evidence(state: StockState) -> list[dict[str, Any]]:
    """Labelled evidence: `payload` goes to the writer, the rest is shown to the user as source cards."""
    lang = state["lang"]
    by_symbol = {c["symbol"]: c for c in state["companies"]}
    quotes = {q["symbol"]: q for q in state.get("quotes", [])}
    ev: list[dict[str, Any]] = []
    for i, f in enumerate(state.get("facts", []), 1):
        q = quotes[f["symbol"]]
        ev.append({"label": f"Q{i}", "kind": "price", "payload": f,
                   "title": f"{f['company']} share price", "subtitle": f"{stock.SOURCE} · {q['as_of_hhmm']} Doha, {q['as_of_date']}",
                   "url": stock.yahoo_url(f["symbol"]), "snippet": f"{f['price']} · {f['day_change']}"})
    for i, p in enumerate(state.get("profiles", []), 1):
        c = by_symbol.get(p["symbol"])
        payload = {"company": _name(c, lang) if c else p.get("name"), **{k: p[k] for k in PROFILE_FIELDS if k in p}}
        ev.append({"label": f"C{i}", "kind": "profile", "payload": payload,
                   "title": f"{payload['company']} company profile", "subtitle": stock.SOURCE,
                   "url": f"{p['url']}/profile", "snippet": (p.get("summary") or "")[:220]})
    docs = document_companies()
    for i, h in enumerate(state.get("passages", []), 1):
        company = docs.get(h.get("company") or "", {}).get("name_en") or h.get("company") or ""
        ev.append({"label": f"D{i}", "kind": "document",
                   "payload": {"file": h["file"], "company": company, "period": h.get("period"), "page": h["page"],
                               "section": h.get("section"), "text": h["text"][:1800]},
                   "title": _doc_title(h["file"]),
                   "subtitle": " · ".join(x for x in (company, h.get("period"), f"page {h['page']}") if x),
                   "url": f"/files/documents/{urlquote(h.get('path') or h['file'])}"
                          + (f"#page={h['page']}" if (h.get("path") or h["file"]).lower().endswith(".pdf") else ""),
                   "snippet": re.sub(r"\s+", " ", h["text"])[:280], "score": h.get("score")})
    n = 0
    for sym, items in (state.get("news") or {}).items():
        for item in items[:3]:
            n += 1
            ev.append({"label": f"N{n}", "kind": "news",
                       "payload": {"company": by_symbol[sym]["name_en"] if sym in by_symbol else sym, "title": item["title"],
                                   "source": item["source"], "date": item["date"]},
                       "title": item["title"], "subtitle": " · ".join(x for x in (item.get("source"), item.get("date")) if x),
                       "url": item.get("url"), "snippet": item.get("snippet") or ""})
    for i, w in enumerate(state.get("web") or [], 1):
        ev.append({"label": f"W{i}", "kind": "web",
                   "payload": {"title": w["title"], "url": w["url"], "source": w.get("source"), "date": w.get("date"),
                               "snippet": w.get("snippet"), "official": bool(w.get("official"))},
                   "title": w["title"], "subtitle": " · ".join(x for x in ("Official" if w.get("official") else "",
                                                                          w.get("source"), w.get("date")) if x),
                   "url": w["url"], "snippet": w.get("snippet") or ""})
    for i, e in enumerate(state.get("previous_evidence") or [], 1):
        ev.append({**e, "label": f"P{i}", "payload": {"kind": e["kind"], "title": e["title"], "detail": e.get("subtitle"),
                                                     "url": e.get("url")}})
    return ev


def previous_evidence(session_id: str | None) -> list[dict[str, Any]]:
    """Source cards of the most recent answer in this chat that had any (price, profile, document, news, web)."""
    if not session_id:
        return []
    with Session(engine) as s:
        rows = s.exec(select(StockLog).where(StockLog.session_id == session_id).order_by(StockLog.id.desc()).limit(5)).all()
    for r in rows:
        items = [e for e in (r.raw or {}).get("evidence") or [] if e.get("kind") != "previous"]
        cited = [e for e in items if e.get("cited")] or items
        if cited:
            return [{k: e.get(k) for k in ("kind", "title", "subtitle", "url", "snippet")} | {"cited": True} for e in cited]
    return []


def template_answer(state: StockState) -> str:
    """Plain answer written by Python (used when the model is unavailable or its numbers don't match)."""
    parts = []
    for i, f in enumerate(state.get("facts", []), 1):
        if state["lang"] == "ar":
            s = f"{f['company']}: آخر سعر {f['price']}، بتغير {f['day_change']} عن الإغلاق السابق [Q{i}]."
            if "period" in f:
                p = f["period"]
                s += f" خلال آخر {p['days']} يوماً تغير السهم {p['change']} (من {p['from']} إلى {p['to']})."
        else:
            s = f"{f['company']} last traded at {f['price']}, {f['day_change']} versus the previous close [Q{i}]."
            if "period" in f:
                p = f["period"]
                s += f" Over the last {p['days']} days it moved {p['change']}, from {p['from']} to {p['to']}."
        parts.append(s)
    for e in state.get("evidence", []):
        if e["kind"] == "profile":
            p = e["payload"]
            bits = [f"{k.replace('_', ' ')}: {p[k]}" for k in ("sector", "market_cap", "pe_trailing", "dividend_yield", "website") if k in p]
            parts.append(f"{p['company']}: " + "; ".join(bits) + f" [{e['label']}].")
    links = [e for e in state.get("evidence", []) if e["label"][0] in "WP" and e.get("url")]
    if links:
        parts.append("\n".join(f"- {e['title']}: {e['url']} [{e['label']}]" for e in links[:6]))
    if any(e["kind"] == "document" for e in state.get("evidence", [])):
        parts.append(TEXT["docs_below"][state["lang"]])
    return " ".join(parts) or TEXT["no_evidence"][state["lang"]]


def source_line(state: StockState, cited: set[str]) -> str:
    ar = state["lang"] == "ar"
    parts = []
    if state.get("quotes"):
        q = state["quotes"][0]
        closed = not q["market_open"]
        parts.append(
            (f"الأسعار: Yahoo Finance عبر yfinance، حتى الساعة {q['as_of_hhmm']} بتوقيت الدوحة ({q['as_of_date']})، قد تكون متأخرة"
             + ("؛ السوق مغلق حالياً" if closed else ""))
            if ar else
            (f"Prices: {stock.SOURCE}, as of {q['as_of_hhmm']} Doha time ({q['as_of_date']}), may be delayed"
             + ("; market closed" if closed else "")))
    kinds = {e["kind"] for e in state.get("evidence", []) if e["label"] in cited}
    if "profile" in kinds:
        parts.append("بيانات الشركة: Yahoo Finance" if ar else "Company data: Yahoo Finance")
    if "document" in kinds:
        parts.append("الوثائق: تقارير النتائج المرفوعة" if ar else "Documents: uploaded results reports")
    if any(c.startswith("P") for c in cited):
        parts.append("مصادر الإجابة السابقة مدرجة أدناه" if ar else "Sources of the previous answer are listed below")
    if "web" in kinds:
        parts.append("الويب: بحث DuckDuckGo وروابط رسمية" if ar else "Web: DuckDuckGo search and official links")
    if "news" in kinds:
        parts.append("الأخبار: بحث DuckDuckGo (للسياق فقط)" if ar else "News: DuckDuckGo search (context only)")
    if not parts:
        return ""
    return ("المصدر — " if ar else "Source — ") + ". ".join(parts) + "."


# ---------- nodes ----------

def route(state: StockState) -> dict:
    question = state["question"]
    memory = chat_memory.load(state.get("session_id"))
    last = memory["recent"][-1]["companies"] if memory["recent"] else []
    docs = document_companies()
    doc_names = [f"{d['name_en']} ({', '.join(d['periods'])})" for d in docs.values()]
    try:
        r = chat_memory.route(question, memory, doc_names)
    except LLMError as exc:
        # Router unavailable: keyword intents; a question without a company inherits the last turn's companies.
        log.warning("chat router unavailable: %s", exc)
        relation = "follow_up" if chat_memory.has_history(memory) else "first"
        return {"standalone": question, "relation": relation, "scope": "in_scope", "intents": guess_intents(question),
                "routed_companies": [], "recent_companies": last, "memory_model": None}
    intents = r["intents"] or guess_intents(r["standalone"])
    return {"standalone": r["standalone"], "relation": r["relation"], "scope": r["scope"], "intents": intents,
            "routed_companies": r["companies"], "recent_companies": last, "memory_model": r["model"]}


def understand(state: StockState) -> dict:
    q = state.get("standalone") or state["question"]
    companies = stock.resolve_companies(q)
    for name in state.get("routed_companies", []):
        for c in stock.resolve_companies(name):
            if c["symbol"] not in {x["symbol"] for x in companies}:
                companies.append(c)
    if not companies and state.get("relation") == "follow_up":
        companies = [c for sym in state.get("recent_companies", []) if (c := stock.find_by_symbol(sym))]
    companies = companies[:MAX_COMPANIES]
    doc_text = " ".join([q, *state.get("routed_companies", [])])
    return {
        "lang": state.get("lang") or detect_lang(state["question"]),
        "companies": companies,
        "doc_companies": match_document_companies(doc_text, companies, document_companies()),
        "days": parse_days(q),
        "why": bool(WHY_RE.search(q)),
        "planned": False,
    }


def plan(state: StockState) -> dict:
    """Only when the router gave nothing usable and no company was recognised (structured output)."""
    llm = get_llm()
    try:
        out = llm.generate_json(
            json.dumps({"QUESTION": state.get("standalone") or state["question"]}, ensure_ascii=False),
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
    if state.get("scope") == "off_topic":
        return "off_topic"
    intents = set(state.get("intents") or [])
    if state["companies"] or state.get("doc_companies") or intents & {"concept", "documents", "web", "news", "sources"}:
        return "gather"
    return "unknown" if state.get("planned") else "plan"


def gather(state: StockState) -> dict:
    intents = set(state.get("intents") or ["price"])
    companies = state["companies"]
    lang = state["lang"]
    why = state.get("why") or "news" in intents
    days = state.get("days")
    if not days and ("performance" in intents or why):
        days = 30 if "performance" in intents else 7
    want_quote = bool(intents & {"price", "performance", "profile"}) or (why and not intents & {"documents"})
    out: dict[str, Any] = {"quotes": [], "histories": [], "profiles": [], "news": {}, "passages": [], "web": [],
                           "previous_evidence": [], "error": None, "days": days, "why": why}
    query = state.get("standalone") or state["question"]
    if "sources" in intents:
        out["previous_evidence"] = previous_evidence(state.get("session_id"))
        if out["previous_evidence"] and intents <= {"sources", "web", "concept"}:
            out["ok"] = True
            return out  # the user only wants the links of the last answer
    if "web" in intents or ("news" in intents and not companies):
        found = stock.official_links(query)
        if "news" in intents and not companies:
            found += stock.search_news_query(f"{query} Qatar" if "qatar" not in query.lower() else query)
        if "web" in intents:
            found += stock.search_web(query)
        found = [w for w in found if w.get("official") or QATAR_RE.search(f"{w.get('title')} {w.get('snippet')} {w.get('url')}")]
        seen: set[str] = set()
        out["web"] = [w for w in found if w.get("url") and not (w["url"].rstrip("/") in seen or seen.add(w["url"].rstrip("/")))][:6]
    try:
        if want_quote:
            out["quotes"] = [stock.get_quote(c["symbol"]) for c in companies]
            if days:
                out["histories"] = [stock.get_history(c["symbol"], days) for c in companies]
    except stock.StockDataError as exc:
        out["error"] = str(exc)
        out["quotes"], out["histories"] = [], []
    if "profile" in intents:
        for c in companies:
            try:
                out["profiles"].append(stock.get_profile(c["symbol"]))
            except stock.StockDataError as exc:
                log.warning("profile unavailable: %s", exc)
    if why or "news" in intents:
        out["news"] = {c["symbol"]: items for c in companies if (items := stock.search_news(c))}
    if "documents" in intents or (why and companies) or ("profile" in intents and state.get("doc_companies")):
        hits: list[dict] = []
        if state.get("doc_companies"):
            for slug in state["doc_companies"]:
                hits += [h for h in rag.search(query, k=DOC_K, where=rag.doc_where(company=slug))
                         if h["score"] >= DOC_THRESHOLD_FILTERED[lang]]
        elif not companies:
            hits = [h for h in rag.search(query, k=DOC_K) if h["score"] >= DOC_THRESHOLD[lang]]
        hits.sort(key=lambda h: -h["score"])
        out["passages"] = hits[:DOC_MAX]
    has_evidence = (out["quotes"] or out["profiles"] or out["passages"] or out["news"] or out["web"]
                    or out["previous_evidence"])
    out["ok"] = bool(has_evidence) or (intents == {"concept"} and not companies)
    return out


def after_gather(state: StockState) -> str:
    if state["ok"]:
        return "write"
    return "unavailable" if state.get("error") else "no_evidence"


def write(state: StockState) -> dict:
    lang = state["lang"]
    facts = build_facts(state)
    state = {**state, "facts": facts}
    evidence = build_evidence(state)
    state["evidence"] = evidence
    labels = {e["label"] for e in evidence}
    def for_writer(e: dict) -> dict:
        item = {"label": e["label"], "kind": e["kind"], **e["payload"]}
        if e["kind"] in ("news", "web"):
            for k in ("title", "snippet"):
                if item.get(k):
                    item[k] = NUMBER_RE.sub("…", item[k])
        return item

    payload = {"LANGUAGE": "Arabic" if lang == "ar" else "English",
               "QUESTION": state.get("standalone") or state["question"],
               "EVIDENCE": [for_writer(e) for e in evidence]}
    number_sources = [json.dumps(e["payload"], ensure_ascii=False) for e in evidence
                      if e["kind"] not in ("news", "web") and not e["label"].startswith("P")]
    number_sources += [e["url"] for e in evidence if e.get("url")]  # digits inside URLs are not figures
    answer, by, model, cited = None, "template", state.get("model"), set()
    try:
        llm = get_llm()
        out = llm.generate_json(json.dumps(payload, ensure_ascii=False, indent=1), system=load_prompt("stock.md"),
                                temperature=0.2, schema=ANSWER_SCHEMA)
        text = (out.get("answer") or "").strip()
        text = MULTI_LABEL_RE.sub(lambda m: "".join(f"[{x.strip()}]" for x in re.split(r"[,;]", m.group(1))), text)
        text = LABEL_RE.sub(lambda m: m.group(0) if m.group(1) in labels else "", text)  # drop invented labels
        # label digits and calendar dates are not figures
        bad = unverified_numbers(DATE_RE.sub(" ", LABEL_RE.sub(" ", text)), number_sources)
        if text and not bad:
            answer, by, model = text, "llm", llm.last_model
            cited = ({c for c in out.get("citations") or [] if c in labels} | set(LABEL_RE.findall(text)))
        else:
            log.warning("stock answer had numbers not in the evidence %s; using template", bad)
    except LLMError as exc:
        log.warning("stock writer unavailable, using template: %s", exc)
    if answer is None:
        answer = template_answer(state)
        cited = labels
    for e in evidence:
        e["cited"] = e["label"] in cited
    return {"facts": facts, "evidence": evidence, "answer": answer, "answer_by": by, "model": model,
            "source_line": source_line(state, cited) or (_concept_line(lang) if not evidence else "")}


def unavailable(state: StockState) -> dict:
    return {"answer": TEXT["unavailable"][state["lang"]], "answer_by": "fallback", "source_line": "", "facts": [], "evidence": []}


def _concept_line(lang: str) -> str:
    return ("شرح عام لمفهوم مالي؛ لم تُستخدم بيانات شركة." if lang == "ar"
            else "General explanation of a finance concept; no company data used.")


def no_evidence(state: StockState) -> dict:
    return {"ok": False, "answer": TEXT["no_evidence"][state["lang"]], "answer_by": "fallback", "source_line": "",
            "facts": [], "evidence": []}


def unknown(state: StockState) -> dict:
    return {"ok": False, "answer": TEXT["unknown"][state["lang"]], "answer_by": "fallback", "source_line": "",
            "facts": [], "quotes": [], "histories": [], "evidence": []}


def off_topic(state: StockState) -> dict:
    return {"ok": False, "answer": TEXT["off_topic"][state["lang"]], "answer_by": "fallback", "source_line": "",
            "facts": [], "quotes": [], "histories": [], "evidence": [], "companies": []}


def log_answer(state: StockState) -> dict:
    raw = {k: state.get(k) for k in ("lang", "days", "why", "facts", "quotes", "histories", "news", "error", "answer_by",
                                     "model", "relation", "memory_model", "source_line", "scope", "intents", "profiles",
                                     "evidence")}
    raw["companies"] = [{k: c[k] for k in ("symbol", "name_en", "name_ar")} for c in state.get("companies", [])]
    standalone = state.get("standalone")
    with Session(engine) as s:
        s.add(StockLog(question=state["question"], ticker=",".join(c["symbol"] for c in state.get("companies", [])) or None,
                       answer=state["answer"], raw=json.loads(json.dumps(raw, default=str)), ok=bool(state.get("ok")),
                       session_id=state.get("session_id"),
                       standalone=standalone if standalone and standalone != state["question"] else None,
                       topic_start=state.get("relation") in ("first", "new", "earlier")))
        s.commit()
    return {}


def build() -> Any:
    g = StateGraph(StockState)
    for name, fn in [("route", route), ("understand", understand), ("plan", plan), ("gather", gather), ("write", write),
                     ("unavailable", unavailable), ("no_evidence", no_evidence), ("unknown", unknown),
                     ("off_topic", off_topic), ("log", log_answer)]:
        g.add_node(name, fn)
    g.add_edge(START, "route")
    g.add_edge("route", "understand")
    targets = {"gather": "gather", "plan": "plan", "unknown": "unknown", "off_topic": "off_topic"}
    g.add_conditional_edges("understand", after_understand, targets)
    g.add_conditional_edges("plan", after_understand, {**targets, "plan": "unknown"})
    g.add_conditional_edges("gather", after_gather, {"write": "write", "unavailable": "unavailable", "no_evidence": "no_evidence"})
    for n in ("write", "unavailable", "no_evidence", "unknown", "off_topic"):
        g.add_edge(n, "log")
    g.add_edge("log", END)
    return g.compile()


stock_agent = build()


def public_evidence(evidence: list[dict]) -> list[dict]:
    return [{k: v for k, v in e.items() if k != "payload"} for e in evidence or []]


def public_profiles(profiles: list[dict]) -> list[dict]:
    return [{k: p[k] for k in (*PROFILE_FIELDS, "symbol", "url", "source") if k in p} for p in profiles or []]


def ask(question: str, session_id: str | None = None) -> dict[str, Any]:
    out = stock_agent.invoke({"question": question.strip(), "session_id": session_id})
    companies = out.get("companies", [])
    return {
        "question": out["question"],
        "session_id": session_id,
        "standalone": out.get("standalone") if out.get("standalone") != out["question"] else None,
        "relation": out.get("relation"),
        "scope": out.get("scope", "in_scope"),
        "intents": out.get("intents", []) if out.get("scope") != "off_topic" else [],
        "memory_model": out.get("memory_model"),
        "lang": out["lang"],
        "ok": bool(out.get("ok")),
        "answer": out["answer"],
        "source_line": out.get("source_line", ""),
        "answer_by": out.get("answer_by"),
        "model": out.get("model"),
        "companies": [{"symbol": c["symbol"], "name_en": c["name_en"], "name_ar": c["name_ar"]} for c in companies],
        "quotes": out.get("quotes", []),
        "histories": [{k: v for k, v in h.items() if k != "closes"} | {"closes": h["closes"][-60:]} for h in out.get("histories", [])],
        "profiles": public_profiles(out.get("profiles", [])),
        "evidence": public_evidence(out.get("evidence", [])),
        "news": out.get("news", {}),
    }
