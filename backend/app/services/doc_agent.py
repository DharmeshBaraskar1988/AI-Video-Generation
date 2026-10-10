"""Document agent: uploaded results documents -> verified quarter data -> (after approval) summary + video script.

    classify (LLM: company, period, type) -> index (RAG, tagged by company/period) -> extract (LLM, per company
    and period, every figure with an exact quote) -> verify (Python: the number must be printed in the cited
    passage; units converted here) -> DataReview "review"  ==> person approves / edits ==>
    quarter file written -> summary + video script generated automatically

Numbers still never come from the model's own knowledge: it may only copy figures that a program finds
printed in the cited passage, and a person approves them before any script uses them.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import traceback
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session, select

from ..config import settings
from ..db import DataReview, Document, engine
from . import rag, stock
from .llm import LLMError, get_llm, load_prompt
from .quarters import PERIOD_RE, load_file, period_slug

log = logging.getLogger(__name__)

METRICS = ("revenue", "net_profit", "eps", "cash")
EXTRACT_QUERIES = [
    "statement of profit or loss revenue profit for the period attributable to owners",
    "basic and diluted earnings per share",
    "cash and bank balances cash and cash equivalents fixed deposits",
    "segment information revenue share petrochemicals fertilisers steel",
    "financial performance review net profit declined increased due to volumes prices",
    "outlook dividend corporate developments acquisition",
]
PASSAGES_MAX = 16
_lock = threading.Lock()

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in
                   ("company_name", "company_name_ar", "ticker", "doc_type", "period", "period_end", "unit", "language", "confidence")},
    "required": ["company_name", "doc_type", "period", "confidence"],
}
_FIG = {
    "type": "object",
    "properties": {
        "metric": {"type": "string", "enum": list(METRICS)},
        "period": {"type": "string"},
        "value": {"type": "string"},
        "unit": {"type": "string"},
        "negative": {"type": "boolean"},
        "citation": {"type": "string"},
        "quote": {"type": "string"},
    },
    "required": ["metric", "period", "value", "unit", "citation", "quote"],
}
EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "figures": {"type": "array", "items": _FIG},
        "segments": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "share_pct": {"type": "string"}, "period": {"type": "string"},
            "citation": {"type": "string"}, "quote": {"type": "string"}},
            "required": ["name", "share_pct", "period", "citation"]}},
        "drivers": {"type": "array", "items": {"type": "object", "properties": {
            "en": {"type": "string"}, "ar": {"type": "string"}, "citation": {"type": "string"}},
            "required": ["en", "ar", "citation"]}},
    },
    "required": ["figures", "segments", "drivers"],
}


# ---------- small helpers ----------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def review_id(company: str, period: str) -> str:
    return f"{company}-{period_slug(period)}"


def normalize_period(text: str) -> str | None:
    t = re.sub(r"\s+", " ", (text or "").strip().upper())
    t = t.replace("HALF YEAR", "H1").replace("FULL YEAR", "FY")
    m = re.search(r"\b(Q[1-4]|H1|9M|FY)\s*-?\s*((?:19|20)\d{2})\b", t)
    if not m:
        return None
    period = f"{m.group(1)} {m.group(2)}"
    return period if PERIOD_RE.match(period) else None


def _digits(text: str) -> str:
    """Digits and decimal points only, with spaces/commas inside numbers removed (PDF text splits numbers)."""
    return re.sub(r"(?<=\d)[\s,](?=\d)", "", text)


def parse_number(text: str) -> Decimal | None:
    t = text.strip()
    negative = t.startswith("(") and t.endswith(")") or t.startswith("-")
    t = re.sub(r"[^\d.]", "", t)
    if not t:
        return None
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None
    return -v if negative else v


def unit_factor(unit: str, metric: str) -> Decimal | None:
    """Multiplier from the printed unit to QR million (EPS stays in QR)."""
    u = (unit or "").lower().replace("’", "'")
    if metric == "eps":
        return Decimal(1)
    if "000" in u or "thousand" in u:
        return Decimal("0.001")
    if "billion" in u or re.search(r"\bbn\b", u):
        return Decimal(1000)
    if "million" in u or re.search(r"\bmn\b|\bm\b", u):
        return Decimal(1)
    return None


def _round(v: Decimal, metric: str) -> float:
    places = 3 if metric == "eps" else 1
    q = float(round(v, places))
    return int(q) if metric != "eps" and q == int(q) else q


def _set_doc(doc_id: int, **fields: Any) -> None:
    with Session(engine) as s:
        doc = s.get(Document, doc_id)
        if doc:
            for k, v in fields.items():
                setattr(doc, k, v)
            s.add(doc)
            s.commit()


def _set_review(rid: str, **fields: Any) -> None:
    with Session(engine) as s:
        r = s.get(DataReview, rid)
        if r:
            for k, v in fields.items():
                setattr(r, k, v)
            r.updated_at = _now()
            s.add(r)
            s.commit()


# ---------- 1. classify ----------

def classify_document(doc_id: int) -> dict[str, Any]:
    _set_doc(doc_id, status="classifying", error=None)
    with Session(engine) as s:
        doc = s.get(Document, doc_id)
        path = rag.doc_path(doc)
        name = doc.name or doc.file
    text = rag.first_pages_text(path)
    if len(text.strip()) < 80:
        raise ValueError("No readable text found (a scanned PDF needs OCR first)")
    llm = get_llm()
    out = llm.generate_json(
        json.dumps({"FILE_NAME": name, "TEXT": text}, ensure_ascii=False),
        system=load_prompt("classify_doc.md"), temperature=0, schema=CLASSIFY_SCHEMA,
    )
    period = normalize_period(out.get("period", "")) or normalize_period(name)
    if not period:
        raise ValueError(f"Could not tell the reporting period (model said '{out.get('period')}')")
    matches = stock.resolve_companies(f"{out.get('company_name', '')} {out.get('ticker', '')}")
    if matches:
        c = matches[0]
        company = {"slug": c["code"].lower(), "name_en": c["name_en"], "name_ar": c["name_ar"], "ticker": c["code"]}
    else:
        base = out.get("ticker") or out.get("company_name") or name
        company = {"slug": re.sub(r"[^a-z0-9]", "", base.lower())[:12] or "company",
                   "name_en": out.get("company_name") or base, "name_ar": out.get("company_name_ar") or "",
                   "ticker": (out.get("ticker") or "").upper()}
    meta = {**out, "period": period, "company": company, "model": llm.last_model}
    _set_doc(doc_id, company=company["slug"], period=period, doc_type=out.get("doc_type"), meta=meta, status="classified")
    return meta


# ---------- 2. extract + verify ----------

NUM_IN_TEXT = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def _value_in_text(chunk_text: str, value: str) -> bool:
    """True when the number appears in the passage as a whole number (thousand separators ignored)."""
    target = parse_number(value)
    if target is None:
        return False
    target = abs(target)
    for n in NUM_IN_TEXT.findall(chunk_text):
        try:
            if Decimal(n.replace(",", "")) == target:
                return True
        except InvalidOperation:
            continue
    return False


def reverify(rid: str) -> dict[str, Any]:
    """Re-run the Python checks on a stored review (no LLM call), keeping the person's include choices."""
    r = get_review(rid)
    content = dict(r.content or {})
    for f in content.get("figures", []):
        src = f.get("source")
        issues = [i for i in f.get("issues", []) if i != "number not found in the cited passage"]
        if src and not _value_in_text(src["text"], f.get("value_text", "")):
            issues.append("number not found in the cited passage")
        was_verified = f.get("verified")
        f["issues"], f["verified"] = issues, not issues
        if f["verified"] and not was_verified:
            f["include"] = True
    for sg in content.get("segments", []):
        ok = bool(sg.get("source")) and _value_in_text(sg["source"]["text"], str(sg.get("share_pct", "")))
        sg["verified"], sg["issues"] = ok, [] if ok else ["share not found in the cited passage"]
        sg["include"] = sg["include"] or ok
    content["checks"] = {"figures": len(content.get("figures", [])),
                         "verified": sum(f["verified"] for f in content.get("figures", []))}
    _set_review(rid, content=content)
    return content


def _existing_values(company: str, year: int) -> dict[str, dict[str, Any]]:
    path = settings.quarters_dir / f"{company}_{year}.json"
    if not path.exists():
        return {}
    try:
        qf = load_file(path)
    except Exception:  # noqa: BLE001
        return {}
    return {q.period: {"revenue": q.revenue, "net_profit": q.net_profit, "eps": q.eps_qr,
                       "cash": getattr(q, "cash_and_bank", None), "derived": q.derived} for q in qf.quarters}


def extract_review(company: str, period: str) -> dict[str, Any]:
    rid = review_id(company, period)
    with Session(engine) as s:
        docs = s.exec(select(Document).where(Document.company == company, Document.period == period)).all()
        doc_ids = [d.id for d in docs if d.chunks]
        names = {d.id: d.name or d.file for d in docs}
        meta = next((d.meta for d in docs if d.meta), {})
        r = s.get(DataReview, rid) or DataReview(id=rid, company=company, period=period)
        r.status, r.error, r.updated_at = "extracting", None, _now()
        s.add(r)
        s.commit()
    if not doc_ids:
        raise ValueError(f"No indexed documents for {company} {period}")
    for d in doc_ids:
        _set_doc(d, status="extracting")

    seen: dict[str, dict] = {}
    where = rag.doc_where(company, period)
    for q in EXTRACT_QUERIES:
        for h in rag.search(q, k=5, where=where):
            seen.setdefault(h["id"], h)
    hits = sorted(seen.values(), key=lambda h: -h["score"])[:PASSAGES_MAX]
    labelled = {f"C{i + 1}": h for i, h in enumerate(hits)}
    payload = {
        "COMPANY": meta.get("company", {}).get("name_en", company),
        "TARGET PERIOD": period,
        "PASSAGES": [{"label": lab, "file": h["file"], "page": h["page"], "section": h["section"], "text": h["text"][:3000]}
                     for lab, h in labelled.items()],
    }
    llm = get_llm()
    out = llm.generate_json(json.dumps(payload, ensure_ascii=False, indent=1), system=load_prompt("extract_data.md"),
                            temperature=0, schema=EXTRACT_SCHEMA)

    year = int(period.split()[1])
    existing = _existing_values(company, year)

    def source(lab: str) -> dict | None:
        h = labelled.get(lab)
        return h and {"chunk_id": h["id"], "doc_id": h.get("doc_id"), "file": h["file"], "path": h.get("path"),
                      "page": h["page"], "section": h["section"], "text": h["text"]}

    figures = []
    for i, f in enumerate(out.get("figures", [])):
        metric, fperiod = f.get("metric"), normalize_period(f.get("period", "")) or ""
        src = source(f.get("citation", ""))
        issues = []
        if metric not in METRICS:
            continue
        if not fperiod:
            issues.append("period not recognised")
        if not src:
            issues.append("cited passage not found")
        elif not _value_in_text(src["text"], f.get("value", "")):
            issues.append("number not found in the cited passage")
        num = parse_number(f.get("value", ""))
        if num is None:
            issues.append("not a number")
        if f.get("negative") and num is not None and num > 0:
            num = -num
        factor = unit_factor(f.get("unit", ""), metric)
        if factor is None:
            issues.append(f"unknown unit '{f.get('unit')}'")
        value = _round(num * factor, metric) if num is not None and factor is not None else None
        ex = existing.get(fperiod, {}).get(metric)
        figures.append({
            "id": f"f{i + 1}", "metric": metric, "period": fperiod, "value_text": f.get("value"), "unit": f.get("unit"),
            "value": value, "value_unit": "QR" if metric == "eps" else "QR million", "quote": f.get("quote", "")[:300],
            "source": src, "verified": not issues, "issues": issues, "existing": ex,
            "include": not issues,
        })
    # keep one figure per (metric, period): the verified one first
    best: dict[tuple, dict] = {}
    for f in sorted(figures, key=lambda f: not f["verified"]):
        best.setdefault((f["metric"], f["period"]), f)
    figures = sorted(best.values(), key=lambda f: (f["period"] != period, f["period"], METRICS.index(f["metric"])))

    segments = []
    for i, sg in enumerate(out.get("segments", [])):
        src = source(sg.get("citation", ""))
        ok = bool(src) and _value_in_text(src["text"], sg.get("share_pct", ""))
        num = parse_number(sg.get("share_pct", ""))
        segments.append({"id": f"s{i + 1}", "name": sg.get("name", "").strip(), "share_pct": float(num) if num is not None else None,
                         "period": normalize_period(sg.get("period", "")) or period, "source": src, "verified": ok,
                         "include": ok, "issues": [] if ok else ["share not found in the cited passage"]})
    drivers = [{"id": f"d{i + 1}", "en": d.get("en", "").strip(), "ar": d.get("ar", "").strip(),
                "source": source(d.get("citation", "")), "include": True}
               for i, d in enumerate(out.get("drivers", [])) if d.get("en")]
    drivers = [{**d, "issues": [] if not re.search(r"\d", d["en"]) else ["contains a number; reword or remove"],
                "include": not re.search(r"\d", d["en"])} for d in drivers]

    content = {
        "company": meta.get("company", {"slug": company, "name_en": company, "name_ar": "", "ticker": company.upper()}),
        "period": period,
        "documents": [{"id": d, "name": names[d]} for d in doc_ids],
        "figures": figures,
        "segments": segments,
        "drivers": drivers,
        "model": llm.last_model,
        "extracted_at": _now().isoformat(),
        "checks": {"figures": len(figures), "verified": sum(f["verified"] for f in figures)},
    }
    _set_review(rid, status="review", content=content)
    for d in doc_ids:
        _set_doc(d, status="review")
    return content


# ---------- pipeline (LangGraph) ----------

class PipelineState(TypedDict, total=False):
    doc_ids: list[int]
    groups: list[list[str]]
    errors: list[str]


def _node_classify(state: PipelineState) -> dict:
    errors = list(state.get("errors", []))
    for d in state["doc_ids"]:
        try:
            classify_document(d)
        except (LLMError, ValueError, Exception) as exc:  # noqa: BLE001
            log.error("classify failed for %s: %s", d, traceback.format_exc())
            _set_doc(d, status="failed", error=str(exc))
            errors.append(f"doc {d}: {exc}")
    return {"errors": errors}


def _node_index(state: PipelineState) -> dict:
    groups: set[tuple[str, str]] = set()
    errors = list(state.get("errors", []))
    for d in state["doc_ids"]:
        with Session(engine) as s:
            doc = s.get(Document, d)
            if not doc or doc.status == "failed":
                continue
        try:
            rag.index_document(d)
            _set_doc(d, status="indexed")
            groups.add((doc.company, doc.period))
        except Exception as exc:  # noqa: BLE001
            log.error("index failed for %s: %s", d, traceback.format_exc())
            _set_doc(d, status="failed", error=str(exc))
            errors.append(f"doc {d}: {exc}")
    return {"groups": [list(g) for g in sorted(groups)], "errors": errors}


def _node_extract(state: PipelineState) -> dict:
    errors = list(state.get("errors", []))
    for company, period in state.get("groups", []):
        try:
            extract_review(company, period)
        except Exception as exc:  # noqa: BLE001
            log.error("extract failed for %s %s: %s", company, period, traceback.format_exc())
            _set_review(review_id(company, period), status="failed", error=str(exc))
            errors.append(f"{company} {period}: {exc}")
    return {"errors": errors}


def _build() -> Any:
    g = StateGraph(PipelineState)
    g.add_node("classify", _node_classify)
    g.add_node("index", _node_index)
    g.add_node("extract", _node_extract)
    g.add_edge(START, "classify")
    g.add_edge("classify", "index")
    g.add_edge("index", "extract")
    g.add_edge("extract", END)
    return g.compile()


pipeline = _build()


def run_pipeline(doc_ids: list[int]) -> None:
    """Run in a background thread: classify, index and extract for the given documents."""
    with _lock:  # one pipeline at a time (free-tier rate limits)
        try:
            pipeline.invoke({"doc_ids": doc_ids, "errors": []})
        except Exception:  # noqa: BLE001
            log.error("document pipeline crashed: %s", traceback.format_exc())


def start_pipeline(doc_ids: list[int]) -> None:
    threading.Thread(target=run_pipeline, args=(doc_ids,), daemon=True).start()


def reindex_group(company: str, period: str) -> None:
    """After a person corrects a document's company/period: re-index it and extract again."""
    def work() -> None:
        with _lock:
            with Session(engine) as s:
                ids = [d.id for d in s.exec(select(Document).where(Document.company == company, Document.period == period)).all()]
            for d in ids:
                rag.index_document(d)
                _set_doc(d, status="indexed")
            try:
                extract_review(company, period)
            except Exception as exc:  # noqa: BLE001
                _set_review(review_id(company, period), status="failed", error=str(exc))

    threading.Thread(target=work, daemon=True).start()


# ---------- 3. approve -> quarter file -> summary + script ----------

def _period_parts(period: str) -> tuple[str, int]:
    kind, year = period.split()
    return kind, int(year)


def approve(rid: str, content: dict[str, Any], auto_continue: bool = True) -> dict[str, Any]:
    """Write the approved figures into data/quarters/{company}_{year}.json and start summary + script."""
    company_info = content["company"]
    slug, period = company_info["slug"], content["period"]
    _, year = _period_parts(period)
    path = settings.quarters_dir / f"{slug}_{year}.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "_note": "", "company": {}, "current_quarter": period, "quarters": [], "history_net_profit": [],
        "narrative_drivers": [], "source_documents": {},
    }
    if not path.exists() or "DEMO" not in data.get("_note", ""):
        data["_note"] = f"Extracted from uploaded documents and approved by a reviewer on {_now().date().isoformat()}."
    data["company"] = {
        **{"exchange": "Qatar Stock Exchange", "currency": "QAR", "unit": "QR million", "fiscal_year": "Calendar (Jan-Dec)"},
        **data.get("company", {}),
        "name_en": company_info.get("name_en") or data.get("company", {}).get("name_en", slug),
        # the Arabic video needs a company name; fall back to the English one if the documents give none
        "name_ar": company_info.get("name_ar") or data.get("company", {}).get("name_ar") or company_info.get("name_en") or slug,
        "ticker": company_info.get("ticker") or data.get("company", {}).get("ticker", slug.upper()),
    }
    # explicit derived periods are dropped; they are recalculated from the new figures when loaded
    quarters = {q["period"]: q for q in data.get("quarters", []) if not q.get("derived")}
    history = {h["period"]: h for h in data.get("history_net_profit", [])}
    field_name = {"revenue": "revenue", "net_profit": "net_profit", "eps": "eps_qr", "cash": "cash_and_bank"}
    months = {"Q1": "Jan-Mar", "Q2": "Apr-Jun", "Q3": "Jul-Sep", "Q4": "Oct-Dec", "H1": "Jan-Jun", "9M": "Jan-Sep", "FY": "Jan-Dec"}

    def entry(p: str) -> dict:
        k, y = _period_parts(p)
        return quarters.setdefault(p, {"period": p, "months": f"{months[k]} {y}", "derived": False, "sources": []})

    target = entry(period)
    for f in content.get("figures", []):
        if not f.get("include") or f.get("value") is None or not f.get("period"):
            continue
        fk, fy = _period_parts(f["period"])
        src = f.get("source") or {}
        cite = f"{src.get('file', 'document')} p.{src.get('page', '?')}"
        if fy == year:
            e = entry(f["period"])
            e[field_name[f["metric"]]] = f["value"]
            e["derived"] = False
            e.pop("derivation", None)
            if cite not in e["sources"]:
                e["sources"].append(cite)
        else:  # prior-year comparative
            metric = "eps" if f["metric"] == "eps" else f["metric"]
            if metric in ("revenue", "net_profit", "eps"):
                target.setdefault("comparatives", {})[f"{metric}_{fk.lower()}_{fy}"] = f["value"]
            if f["metric"] == "net_profit" and fk in ("Q1", "H1", "9M", "FY"):
                history[f["period"]] = {"period": f["period"], "ytd_net_profit": f["value"]}
    segs = [sg for sg in content.get("segments", []) if sg.get("include") and sg.get("share_pct") is not None]
    if segs:
        target["segment_revenue_share_pct"] = {sg["name"].lower(): sg["share_pct"] for sg in segs}
    drivers = [d for d in content.get("drivers", []) if d.get("include") and d.get("en")]
    if drivers:
        data["narrative_drivers"] = [d["en"] for d in drivers]
        data["narrative_drivers_ar"] = [d["ar"] for d in drivers if d.get("ar")]
    for d in content.get("documents", []):
        data.setdefault("source_documents", {})[f"doc_{d['id']}"] = d["name"]

    data["quarters"] = list(quarters.values())
    order = {"Q1": 1, "H1": 2, "9M": 3, "FY": 4}
    data["history_net_profit"] = sorted(
        history.values(), key=lambda h: (int(h["period"].split()[1]), order.get(h["period"].split()[0], 9))
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # newest single quarter (reported or derived) becomes the current quarter
    qf = load_file(path)
    singles = [q for q in qf.quarters if q.is_single_quarter]
    current = (singles[-1] if singles else qf.quarters[-1]).period
    data["current_quarter"] = current
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    content = {**content, "approved_at": _now().isoformat(), "quarter_file": path.name, "current_quarter": current}
    _set_review(rid, status="approved", content=content)
    for d in content.get("documents", []):
        _set_doc(d["id"], status="approved")

    video_id = f"{slug}-{period_slug(current)}"
    if auto_continue:
        threading.Thread(target=_continue_after_approval, args=(slug, period, current), daemon=True).start()
    return {"quarter_file": path.name, "current_quarter": current, "video_id": video_id,
            "summary_id": f"{slug}-{period_slug(period)}"}


def _continue_after_approval(company: str, period: str, current_quarter: str) -> None:
    """The agent carries on: write the cited summary for the documents' period and the video script."""
    from ..graphs.video_graph import start_video
    from . import summary

    try:
        start_video(company, current_quarter, force=True)
    except Exception:  # noqa: BLE001
        log.error("auto script generation failed: %s", traceback.format_exc())
    summary.run_in_background(company, period)


def get_review(rid: str) -> DataReview | None:
    with Session(engine) as s:
        return s.get(DataReview, rid)


def list_reviews() -> list[dict[str, Any]]:
    with Session(engine) as s:
        rows = s.exec(select(DataReview).order_by(DataReview.updated_at.desc())).all()
    return [{"id": r.id, "company": r.company, "period": r.period, "status": r.status, "error": r.error,
             "company_name": (r.content or {}).get("company", {}).get("name_en"),
             "checks": (r.content or {}).get("checks"), "updated_at": r.updated_at} for r in rows]
