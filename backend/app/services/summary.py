"""Disclosure summary of a company's results documents (one company + period), portal style.

Two Gemini calls per summary:
  1. analysis  - passages from rag (statements, auditor's report, notes) -> document facts, key figures
                 copied exactly as printed, an executive summary with {{F1}} placeholders, implications
                 and a full analysis, every item citing its passages;
  2. Arabic    - translation of every text item, placeholders kept.
Python then checks each figure is printed in its cited passage, computes the year-on-year changes,
fills the placeholders and flags any other number not found in the cited passages.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import traceback
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from ..config import settings
from . import rag
from .doc_agent import _value_in_text, parse_number, unit_factor
from .factcheck import _num
from .llm import get_llm, load_prompt

log = logging.getLogger(__name__)

VERSION = 2
# Searches that together cover a results document: statements, auditor's report, notes, capital actions.
QUERIES = [
    "independent auditor's report opinion unqualified key audit matters",
    "auditor signature partner of Ernst & Young KPMG Deloitte PricewaterhouseCoopers Qatar Auditors Registry Number date",
    "statement of financial position total assets total liabilities total equity",
    "income statement revenue net profit for the year earnings per share",
    "statement of comprehensive income total comprehensive income for the year",
    "statement of cash flows net cash from operating activities",
    "dividend proposed distribution bonus shares share buyback capital",
    "approved by the board of directors and authorised for issue",
    "segment information revenue and profit by business segment",
    "expected credit loss impairment provisions credit risk stage",
    "tax regulation acquisitions subsidiaries subsequent events significant developments",
]
PASSAGES_PER_QUERY = 5
OPENING_PAGES = 3
MAX_PASSAGES = 45
SUMMARY_DIR = settings.outputs_dir / "summary"
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
PLACEHOLDER_RE = re.compile(r"\{\{\s*(F\d+)(?:\.(prior|change))?\s*\}\}")
NOTE_RE = re.compile(r"^(\d{1,2})\.\s")
MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December|"
    "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
    "يناير|فبراير|مارس|أبريل|مايو|يونيو|يوليو|أغسطس|سبتمبر|أكتوبر|نوفمبر|ديسمبر"
)
# Dates, years and period labels are not financial figures; they are skipped by the number check.
DATE_RE = re.compile(
    rf"\b\d{{1,2}}[ -](?:{MONTHS})(?:[ -]\d{{2,4}})?\b"  # 30 June 2026, 30-June-26, 30 يونيو
    r"|(?<![\d,.])(?:19|20)\d{2}(?![\d,.]\d)"  # years, not digits inside a larger number
    r"|\b[1-4]Q[- ]?\d{2}\b|\bQ[1-4]\b|\b[12]H[- ]?\d{2}\b|\bH[12]\b"  # 2Q-26, Q2, 1H-26, H1
    r"|\b(?:Note|Stage|Pillar|IFRS|IAS)\s+\d+\b"  # Note 10, Stage 3, Pillar Two, IFRS 9
)

_STR = {"type": "string"}
_CITES = {"type": "array", "items": _STR}
_ITEM = {"type": "object", "properties": {"text": _STR, "citations": _CITES}, "required": ["text", "citations"]}
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "document": {
            "type": "object",
            "properties": {
                "title": _STR, "issuer": _STR, "doc_kind": _STR, "auditor": _STR, "opinion": _STR,
                "opinion_citations": _CITES, "board_approval": _STR, "board_citations": _CITES,
            },
            "required": ["title", "issuer", "doc_kind", "auditor", "opinion", "opinion_citations",
                         "board_approval", "board_citations"],
        },
        "period_labels": {"type": "object", "properties": {"current": _STR, "prior": _STR}, "required": ["current", "prior"]},
        "figures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"metric": _STR, "current": _STR, "prior": _STR, "unit": _STR, "citations": _CITES},
                "required": ["metric", "current", "prior", "unit", "citations"],
            },
        },
        "executive": _ITEM,
        "implications": {
            "type": "array",
            "items": {"type": "object", "properties": {"title": _STR, "text": _STR, "citations": _CITES},
                      "required": ["title", "text", "citations"]},
        },
        "sections": {
            "type": "array",
            "items": {"type": "object", "properties": {"title": _STR, "points": {"type": "array", "items": _ITEM}},
                      "required": ["title", "points"]},
        },
    },
    "required": ["document", "period_labels", "figures", "executive", "implications", "sections"],
}
TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "properties": {"label": _STR, "ar": _STR}, "required": ["label", "ar"]}}},
    "required": ["items"],
}

_states: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


# ---------- number check ----------

def _numbers(text: str, skip_dates: bool = False) -> list[str]:
    if skip_dates:
        text = DATE_RE.sub(" ", text)
    return [n.rstrip(",.") for n in NUMBER_RE.findall(text)]


def _value(n: str) -> Decimal | None:
    try:
        return Decimal(n.replace(",", ""))
    except InvalidOperation:
        return None


def unverified_numbers(text: str, sources: list[str]) -> list[str]:
    """Numbers in `text` that do not appear in any cited source passage.
    A number also counts as found if a source has it at another scale (e.g. 5,900,123 thousand -> 5.9 billion)."""
    src_numbers = [n for s in sources for n in _numbers(s)]
    src_strings = {n.replace(",", "") for n in src_numbers}
    src_values = [v for n in src_numbers if (v := _value(n)) is not None]
    missing = []
    for n in _numbers(text, skip_dates=True):
        plain = n.replace(",", "")
        if plain in src_strings:
            continue
        v = _value(n)
        if v is None or v == 0:
            missing.append(n)
            continue
        decimals = -v.as_tuple().exponent if v.as_tuple().exponent < 0 else 0
        quantum = Decimal(1).scaleb(-decimals)
        scaled_ok = v >= 10 or decimals > 0  # small bare integers must match exactly
        if scaled_ok and any(
            (s * Decimal(10) ** e).quantize(quantum) == v
            for s in src_values
            for e in (-9, -6, -3, 3)
        ):
            continue
        missing.append(n)
    return missing


# ---------- figures: Python formats, compares and fills ----------

def _is_per_share(metric: str, unit: str) -> bool:
    t = f"{metric} {unit}".lower()
    return "per share" in t or "eps" in t.split() or "earnings per" in t


def format_amount(value: Decimal, unit: str, metric: str) -> tuple[str, str] | None:
    """Absolute printed value -> ('QR 1,391.3bn', '1,391.3 مليار ريال قطري'); None if the unit is unknown."""
    v = abs(value)
    if _is_per_share(metric, unit):
        n = _num(float(v), 2)
        return f"QR {n}", f"{n} ريال قطري"
    factor = unit_factor(unit, metric)
    if factor is None and re.fullmatch(r"\s*(qr|qar|riyals?)\s*", unit or "", re.I):
        factor = Decimal("0.000001")
    if factor is None:
        return None
    m = v * factor  # QR million
    if m >= 1000:
        b = m / 1000
        n = _num(float(b), 1 if b >= 100 else 2)
        return f"QR {n}bn", f"{n} مليار ريال قطري"
    n = _num(float(m), 0 if m >= 100 else 1)
    return f"QR {n}m", f"{n} مليون ريال قطري"


def change_pct(current: Decimal | None, prior: Decimal | None) -> float | None:
    """Year-on-year change, only when meaningful (positive base, no sign flip)."""
    if current is None or prior is None or prior <= 0 or current < 0:
        return None
    return float((current - prior) / prior * 100)


def _figure_display(f: dict) -> dict[str, dict[str, str]]:
    """Placeholder texts for one figure: {'F1': {en, ar}, 'F1.prior': ..., 'F1.change': ...}."""
    out: dict[str, dict[str, str]] = {}
    for key, raw in ((f["id"], f["current"]), (f"{f['id']}.prior", f["prior"])):
        v = parse_number(raw) if raw else None
        fmt = format_amount(v, f["unit"], f["metric_en"]) if v is not None else None
        if fmt:
            out[key] = {"en": fmt[0], "ar": fmt[1]}
        elif raw:
            out[key] = {"en": f"{raw.strip('()-')} {f['unit']}".strip(), "ar": f"{raw.strip('()-')} {f['unit']}".strip()}
    pct = f.get("change_pct")
    if pct is None:
        out[f"{f['id']}.change"] = {"en": "change not available", "ar": "التغير غير متاح"}
    elif abs(pct) < 0.05:
        out[f"{f['id']}.change"] = {"en": "unchanged", "ar": "دون تغيير"}
    else:
        n = _num(abs(pct), 1)
        out[f"{f['id']}.change"] = {"en": f"{'up' if pct > 0 else 'down'} {n}%",
                                    "ar": f"{'بارتفاع' if pct > 0 else 'بانخفاض'} {n}%"}
    return out


def fill(text: str, display: dict[str, dict[str, str]], lang: str) -> tuple[str, list[str]]:
    """Replace {{F1}} / {{F1.prior}} / {{F1.change}}; returns (text, unknown placeholders)."""
    unknown: list[str] = []

    def repl(m: re.Match) -> str:
        key = m.group(1) + (f".{m.group(2)}" if m.group(2) else "")
        if key in display:
            return display[key][lang]
        unknown.append(key)
        return "[?]"

    return PLACEHOLDER_RE.sub(repl, text), unknown


# ---------- storage keys ----------

def summary_key(company: str, period: str) -> str:
    return f"{company}_{period.lower().replace(' ', '-')}"


def summary_path(company: str, period: str):
    return SUMMARY_DIR / f"{summary_key(company, period)}.json"


def _company_names(company: str, period: str) -> dict[str, str]:
    """Company names from the quarter file if there is one, else from the document classification."""
    from .quarters import load_all

    files, _ = load_all()
    if company in files:
        c = files[company].company
        return {"name_en": c.name_en.replace(" (demo source)", ""), "name_ar": c.name_ar}
    for d in rag.list_documents():
        if d["company"] == company and d["meta"].get("company"):
            c = d["meta"]["company"]
            return {"name_en": c.get("name_en", company), "name_ar": c.get("name_ar", "")}
    return {"name_en": company.upper(), "name_ar": ""}


# ---------- generation ----------

def _gather(docs: list[dict], where: dict) -> list[dict]:
    """Opening pages of each document (title, auditor's report) + the best hits for each query, no duplicates."""
    seen: dict[str, dict] = {}
    for d in docs:
        for c in rag.doc_chunks(d["id"], OPENING_PAGES)[:6]:
            seen.setdefault(c["id"], c)
    for q in QUERIES:
        for h in rag.search(q, k=PASSAGES_PER_QUERY, where=where):
            seen.setdefault(h["id"], h)
    return list(seen.values())[:MAX_PASSAGES]


def _auditor_in(auditor: str, texts: list[str]) -> bool:
    """True when the firm's distinctive words (e.g. 'Ernst', 'Young') are printed in one passage."""
    words = [w for w in re.findall(r"[A-Za-z]{3,}", auditor) if w.lower() not in {"and", "llp", "the", "qatar", "branch", "co"}]
    return bool(words) and any(all(w.lower() in t.lower() for w in words) for t in texts)


def _note(section: str) -> str:
    m = NOTE_RE.match(section or "")
    return f"Note {m.group(1)}" if m else ""


def generate(company: str, period: str) -> dict[str, Any]:
    docs = [d for d in rag.list_documents() if d["company"] == company and d["period"] == period and d["indexed"]]
    if not docs:
        raise ValueError(f"No indexed documents for {company} {period}. Upload them on the Documents page.")
    names = _company_names(company, period)
    passages = _gather(docs, rag.doc_where(company, period))
    labelled = {f"C{i + 1}": p for i, p in enumerate(passages)}
    llm = get_llm()

    out = llm.generate_json(
        json.dumps({
            "COMPANY": names, "PERIOD": period,
            "DOCUMENTS": [{"file": d["name"], "type": d["doc_type"], "pages": d["pages"]} for d in docs],
            "PASSAGES": [{"label": lab, "file": p["file"], "page": p["page"], "section": p["section"], "text": p["text"]}
                         for lab, p in labelled.items()],
        }, ensure_ascii=False, indent=1),
        system=load_prompt("summary_disclosure.md"), temperature=0.1, schema=ANALYSIS_SCHEMA,
    )

    # passage labels C.. -> stable source keys K.. (only passages that are actually cited)
    keys: dict[str, str] = {}

    def cite(labels: list[str]) -> list[str]:
        return [keys.setdefault(lab, f"K{len(keys) + 1}") for lab in labels if lab in labelled]

    doc = out.get("document") or {}
    figures = []
    for f in (out.get("figures") or [])[:10]:
        if f.get("metric") and f.get("current"):
            figures.append({"id": f"F{len(figures) + 1}", "metric_en": f["metric"].strip(), "current": f["current"].strip(),
                            "prior": (f.get("prior") or "").strip(), "unit": (f.get("unit") or "").strip(),
                            "citations": cite(f.get("citations", []))})
    executive = {"en": (out.get("executive") or {}).get("text", "").strip(),
                 "citations": cite((out.get("executive") or {}).get("citations", []))}
    implications = [{"title_en": i.get("title", "").strip(), "en": i.get("text", "").strip(), "citations": cite(i.get("citations", []))}
                    for i in out.get("implications") or [] if i.get("text")]
    sections = [{"title_en": s.get("title", "").strip(),
                 "points": [{"en": p["text"].strip(), "citations": cite(p.get("citations", []))}
                            for p in s.get("points") or [] if p.get("text")]}
                for s in out.get("sections") or []]
    sections = [s for s in sections if s["points"]]
    # the auditor must be printed in the passages; a firm name from the model's own knowledge is dropped
    auditor = doc.get("auditor", "").strip()
    if auditor and not _auditor_in(auditor, [p["text"] for p in passages]):
        log.warning("Summary: auditor %r is not in any passage; dropped", auditor)
        auditor = ""
    document = {
        "title_en": doc.get("title", "").strip() or f"{names['name_en']}: {period} results",
        "issuer_en": doc.get("issuer", "").strip() or names["name_en"],
        "doc_kind": doc.get("doc_kind", ""), "auditor": auditor,
        "opinion": (doc.get("opinion") or "").strip().lower(), "opinion_citations": cite(doc.get("opinion_citations", [])),
        "board_approval": doc.get("board_approval", "").strip(), "board_citations": cite(doc.get("board_citations", [])),
    }

    # one Arabic call for every text item
    items = [("title", document["title_en"]), ("issuer", document["issuer_en"]), ("exec", executive["en"])]
    items += [(f"M{f['id']}", f["metric_en"]) for f in figures]
    for i, imp in enumerate(implications):
        items += [(f"IT{i}", imp["title_en"]), (f"I{i}", imp["en"])]
    for si, s in enumerate(sections):
        items.append((f"ST{si}", s["title_en"]))
        items += [(f"P{si}.{pi}", p["en"]) for pi, p in enumerate(s["points"])]
    tr = llm.generate_json(
        json.dumps({"COMPANY": names, "ITEMS": [{"label": lab, "en": t} for lab, t in items if t]}, ensure_ascii=False, indent=1),
        system=load_prompt("summary_translate_ar.md"), temperature=0.1, schema=TRANSLATE_SCHEMA,
    )
    ar = {t["label"]: t["ar"].strip() for t in tr.get("items") or [] if t.get("label") and t.get("ar")}
    document["title_ar"], document["issuer_ar"] = ar.get("title", ""), ar.get("issuer", "") or names["name_ar"]
    executive["ar"] = ar.get("exec", "")
    for f in figures:
        f["metric_ar"] = ar.get(f"M{f['id']}", "")
    for i, imp in enumerate(implications):
        imp["title_ar"], imp["ar"] = ar.get(f"IT{i}", ""), ar.get(f"I{i}", "")
    for si, s in enumerate(sections):
        s["title_ar"] = ar.get(f"ST{si}", "")
        for pi, p in enumerate(s["points"]):
            p["ar"] = ar.get(f"P{si}.{pi}", "")

    sources = {}
    for lab, k in keys.items():
        p = labelled[lab]
        sources[k] = {"id": p["id"], "doc_id": p.get("doc_id"), "file": p["file"], "path": p.get("path"), "page": p["page"],
                      "section": p.get("section", ""), "note": _note(p.get("section", "")), "type": p.get("type"), "text": p["text"]}

    result = {
        "version": VERSION,
        "company": company,
        "period": period,
        "names": names,
        "document": document,
        "period_labels": out.get("period_labels") or {"current": period, "prior": ""},
        "figures": figures,
        "executive": executive,
        "implications": implications,
        "sections": sections,
        "sources": sources,
        "documents": [{"id": d["id"], "file": d["name"], "path": d["file"], "pages": d["pages"], "doc_type": d["doc_type"],
                       "size_kb": d["size_kb"]} for d in docs],
        "model": llm.last_model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    recheck(result)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    summary_path(company, period).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


# ---------- checks (no LLM; run on every load) ----------

def recheck(result: dict[str, Any]) -> dict[str, Any]:
    sources = result["sources"]

    def cited(keys: list[str]) -> list[str]:
        return [sources[k]["text"] for k in keys if k in sources]

    display: dict[str, dict[str, str]] = {}
    for f in result["figures"]:
        f["citations"] = [k for k in f["citations"] if k in sources]
        texts = cited(f["citations"])
        f["issues"] = []
        if not texts:
            f["issues"].append("no source passage")
        elif not any(_value_in_text(t, f["current"]) for t in texts):
            f["issues"].append(f"{f['current']} not found in the cited passage")
        if f["prior"] and texts and not any(_value_in_text(t, f["prior"]) for t in texts):
            f["issues"].append(f"{f['prior']} not found in the cited passage")
        f["verified"] = not f["issues"]
        f["change_pct"] = change_pct(parse_number(f["current"]), parse_number(f["prior"]) if f["prior"] else None)
        display.update(_figure_display(f))

    def check(item: dict) -> dict:
        item["citations"] = [k for k in item.get("citations", []) if k in sources]
        texts = cited(item["citations"])
        item["display"], item["unverified"] = {}, {}
        for lang in ("en", "ar"):
            if not item.get(lang):
                continue
            item["display"][lang], unknown = fill(item[lang], display, lang)
            plain = PLACEHOLDER_RE.sub(" ", item[lang]).replace("**", "")
            item["unverified"][lang] = unknown + unverified_numbers(plain, texts)
        item["verified"] = bool(item["citations"]) and not any(item["unverified"].values())
        return item

    items = [check(result["executive"])]
    items += [check(i) for i in result["implications"]]
    items += [check(p) for s in result["sections"] for p in s["points"]]

    d = result["document"]
    for key in ("opinion_citations", "board_citations"):
        d[key] = [k for k in d.get(key, []) if k in sources]
    d["auditor_verified"] = bool(d["auditor"]) and _auditor_in(d["auditor"], [s["text"] for s in sources.values()])
    d["board_verified"] = bool(d["board_approval"]) and bool(d["board_citations"]) and not unverified_numbers(
        d["board_approval"], cited(d["board_citations"]))

    result["checks"] = {
        "bullets": len(items),
        "verified": sum(i["verified"] for i in items),
        "uncited": sum(not i["citations"] for i in items),
        "figures": len(result["figures"]),
        "figures_verified": sum(f["verified"] for f in result["figures"]),
    }
    return result


def _read(company: str, period: str) -> dict[str, Any] | None:
    path = summary_path(company, period)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if data.get("version") == VERSION else None  # older layout: regenerate


def load(company: str, period: str) -> dict[str, Any] | None:
    data = _read(company, period)
    return recheck(data) if data else None


def available() -> list[dict[str, Any]]:
    """Company/period pairs that have indexed documents, with whether a summary exists."""
    pairs = sorted({(d["company"], d["period"]) for d in rag.list_documents() if d["company"] and d["period"] and d["indexed"]})
    out = []
    for company, period in pairs:
        names = _company_names(company, period)
        out.append({"company": company, "period": period, "name_en": names["name_en"], "name_ar": names["name_ar"],
                    "has_summary": _read(company, period) is not None, "state": state(company, period)})
    return out


def state(company: str, period: str) -> dict[str, Any]:
    return dict(_states.get(summary_key(company, period), {"status": "idle", "error": None, "started_at": None}))


def run_in_background(company: str, period: str) -> bool:
    """Start generation unless one is running for this company/period. Returns False if already running."""
    key = summary_key(company, period)
    with _lock:
        if _states.get(key, {}).get("status") == "running":
            return False
        _states[key] = {"status": "running", "error": None, "started_at": datetime.now(timezone.utc).isoformat()}

    def work() -> None:
        try:
            generate(company, period)
            _states[key].update(status="done")
        except Exception as exc:  # noqa: BLE001
            log.error("Summary failed: %s", traceback.format_exc())
            _states[key].update(status="failed", error=str(exc))

    threading.Thread(target=work, daemon=True).start()
    return True
