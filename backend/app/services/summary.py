"""Cited results summary from the document index.

One Gemini call per section (passages from rag.search), then one call for the executive
summary (EN + AR) and Arabic translations of the section points. Every bullet keeps its
citations, and every number in it is checked against the cited passages.
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
from .llm import get_llm, load_prompt

log = logging.getLogger(__name__)

SECTIONS = [
    ("performance", "Financial performance", "النتائج المالية",
     "revenue net profit earnings per share for {period} compared with the same period last year"),
    ("segments", "Segment performance", "أداء القطاعات",
     "segment information revenue and profit by business segment"),
    ("drivers", "Operating environment and drivers", "بيئة التشغيل والعوامل المؤثرة",
     "sales volumes selling prices costs production factors affecting the results"),
    ("balance", "Balance sheet, cash and dividends", "الميزانية والنقد والتوزيعات",
     "cash and bank balances total assets equity liquidity debt dividend paid"),
    ("corporate", "Corporate developments and outlook", "التطورات المؤسسية والتوقعات",
     "acquisitions ownership changes subsidiaries joint ventures outlook strategy"),
]
PASSAGES_PER_SECTION = 8
SUMMARY_DIR = settings.outputs_dir / "summary"
LEGACY_PATH = SUMMARY_DIR / "summary.json"  # before summaries were per company/period (Industries Qatar H1 2026)
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
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
)

SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "citations": {"type": "array", "items": {"type": "string"}}},
                "required": ["text", "citations"],
            },
        }
    },
    "required": ["points"],
}
EXEC_SCHEMA = {
    "type": "object",
    "properties": {
        "title_en": {"type": "string"},
        "title_ar": {"type": "string"},
        "executive": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "en": {"type": "string"},
                    "ar": {"type": "string"},
                    "citations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["en", "ar", "citations"],
            },
        },
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "ar": {"type": "string"}},
                "required": ["label", "ar"],
            },
        },
    },
    "required": ["title_en", "title_ar", "executive", "translations"],
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


# ---------- generation ----------

def _section(title: str, query: str, where: dict) -> tuple[list[dict], list[dict]]:
    hits = rag.search(query, k=PASSAGES_PER_SECTION, where=where)
    if not hits:
        return [], []
    labelled = {f"C{i + 1}": h for i, h in enumerate(hits)}
    payload = {
        "SECTION": title,
        "PASSAGES": [
            {"label": lab, "file": h["file"], "page": h["page"], "section": h["section"], "text": h["text"]}
            for lab, h in labelled.items()
        ],
    }
    out = get_llm().generate_json(
        json.dumps(payload, ensure_ascii=False, indent=1), system=load_prompt("summary_section.md"), temperature=0.2,
        schema=SECTION_SCHEMA,
    )
    points = []
    for p in out.get("points", []):
        ids = [labelled[c]["id"] for c in p.get("citations", []) if c in labelled]
        if p.get("text") and ids:
            points.append({"en": p["text"].strip(), "chunk_ids": ids})
    return points, hits


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


def generate(company: str, period: str) -> dict[str, Any]:
    docs = [d for d in rag.list_documents() if d["company"] == company and d["period"] == period and d["indexed"]]
    if not docs:
        raise ValueError(f"No indexed documents for {company} {period}. Upload them on the Documents page.")
    where = rag.doc_where(company, period)

    sections = []
    for sid, title_en, title_ar, query in SECTIONS:
        points, _ = _section(title_en, query.format(period=period), where)
        sections.append({"id": sid, "title_en": title_en, "title_ar": title_ar, "points": points})

    # global citation keys K1.. and point labels P1..
    keys: dict[str, str] = {}
    labels: dict[str, dict] = {}
    for sec in sections:
        for p in sec["points"]:
            p["citations"] = [keys.setdefault(cid, f"K{len(keys) + 1}") for cid in p.pop("chunk_ids")]
            label = f"P{len(labels) + 1}"
            p["label"] = label
            labels[label] = p

    payload = {
        "COMPANY": _company_names(company, period),
        "PERIOD": period,
        "SECTIONS": [
            {"title": s["title_en"], "points": [{"label": p["label"], "text": p["en"], "citations": p["citations"]} for p in s["points"]]}
            for s in sections
        ],
    }
    out = get_llm().generate_json(
        json.dumps(payload, ensure_ascii=False, indent=1), system=load_prompt("summary_exec.md"), temperature=0.2,
        schema=EXEC_SCHEMA,
    )
    for t in out.get("translations") or []:
        if t.get("label") in labels and t.get("ar"):
            labels[t["label"]]["ar"] = t["ar"].strip()

    by_key = {k: cid for cid, k in keys.items()}
    chunks = {c["id"]: c for c in rag.get_chunks(list(keys))}
    sources = {k: {key: chunks[cid].get(key) for key in ("id", "file", "path", "page", "section", "type", "text")}
               for k, cid in by_key.items() if cid in chunks}

    def verify(item: dict) -> dict:
        return verify_item(item, sources)

    executive = [verify({"en": e.get("en", "").strip(), "ar": e.get("ar", "").strip(), "citations": e.get("citations", [])})
                 for e in out.get("executive", [])]
    for sec in sections:
        sec["points"] = [verify(p) for p in sec["points"]]

    result = {
        "title_en": out.get("title_en") or "Results summary",
        "title_ar": out.get("title_ar") or "ملخص النتائج",
        "executive": executive,
        "sections": [s for s in sections if s["points"]],
        "sources": sources,
        "company": company,
        "period": period,
        "documents": [{"file": d["name"], "pages": d["pages"]} for d in docs],
        "model": get_llm().last_model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    recheck(result)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    summary_path(company, period).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def verify_item(item: dict, sources: dict[str, dict]) -> dict:
    """Keep only known citations and list numbers not found in the cited passages."""
    cited = [sources[k]["text"] for k in item.get("citations", []) if k in sources]
    item["citations"] = [k for k in item.get("citations", []) if k in sources]
    item["unverified"] = {lang: unverified_numbers(item.get(lang, ""), cited) for lang in ("en", "ar") if item.get(lang)}
    item["verified"] = not any(item["unverified"].values())
    return item


def recheck(result: dict[str, Any]) -> dict[str, Any]:
    """(Re)run the number check on every bullet; cheap, no LLM call."""
    items = result["executive"] + [p for s in result["sections"] for p in s["points"]]
    for item in items:
        verify_item(item, result["sources"])
    result["checks"] = {
        "bullets": len(items),
        "verified": sum(i["verified"] for i in items),
        "uncited": sum(not i["citations"] for i in items),
    }
    return result


def _migrate_legacy() -> None:
    if LEGACY_PATH.exists() and not summary_path("iqcd", "H1 2026").exists():
        data = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
        data.setdefault("company", "iqcd")
        data.setdefault("period", "H1 2026")
        summary_path("iqcd", "H1 2026").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        LEGACY_PATH.unlink()


def load(company: str, period: str) -> dict[str, Any] | None:
    _migrate_legacy()
    path = summary_path(company, period)
    if not path.exists():
        return None
    return recheck(json.loads(path.read_text(encoding="utf-8")))


def available() -> list[dict[str, Any]]:
    """Company/period pairs that have indexed documents, with whether a summary exists."""
    _migrate_legacy()
    pairs = sorted({(d["company"], d["period"]) for d in rag.list_documents() if d["company"] and d["period"] and d["indexed"]})
    out = []
    for company, period in pairs:
        names = _company_names(company, period)
        out.append({"company": company, "period": period, "name_en": names["name_en"], "name_ar": names["name_ar"],
                    "has_summary": summary_path(company, period).exists(), "state": state(company, period)})
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
