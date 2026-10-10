"""Load and validate quarter files from data/quarters, and derive missing quarters.

A file holds reported periods (Q1, H1, 9M, FY or single quarters). When a single quarter is
missing but its year-to-date neighbours exist (e.g. Q2 = H1 - Q1), it is derived here and
marked `derived: true`. Derived figures must never be presented as "reported".
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..config import settings

PERIOD_RE = re.compile(r"^(Q[1-4]|H1|9M|FY) (\d{4})$")

# single quarter -> (later YTD period, earlier YTD period) whose difference gives it
DERIVATION_RULES = {"Q2": ("H1", "Q1"), "Q3": ("9M", "H1"), "Q4": ("FY", "9M")}
# YTD period -> months covered (used for display of derived quarters)
QUARTER_MONTHS = {"Q1": "Jan-Mar", "Q2": "Apr-Jun", "Q3": "Jul-Sep", "Q4": "Oct-Dec"}
DERIVABLE_FIELDS = ("revenue", "net_profit")


class Company(BaseModel):
    model_config = ConfigDict(extra="allow")

    name_en: str
    name_ar: str
    ticker: str
    exchange: str
    currency: str = "QAR"
    unit: str = "QR million"
    fiscal_year: str | None = None


class Quarter(BaseModel):
    model_config = ConfigDict(extra="allow")

    period: str
    months: str | None = None
    revenue: float | None = None
    net_profit: float | None = None
    eps_qr: float | None = None
    derived: bool = False
    derivation: str | None = None
    derived_fields: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)

    @field_validator("period")
    @classmethod
    def _period_format(cls, v: str) -> str:
        if not PERIOD_RE.match(v):
            raise ValueError(f"period '{v}' must look like 'Q2 2026', 'H1 2026', '9M 2026' or 'FY 2026'")
        return v

    @property
    def kind(self) -> str:
        return self.period.split()[0]

    @property
    def year(self) -> int:
        return int(self.period.split()[1])

    @property
    def is_single_quarter(self) -> bool:
        return self.kind.startswith("Q")


class HistoryPoint(BaseModel):
    period: str
    ytd_net_profit: float


class QuarterFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    note: str = Field(default="", alias="_note")
    company: Company
    current_quarter: str
    quarters: list[Quarter]
    history_net_profit: list[HistoryPoint] = Field(default_factory=list)
    narrative_drivers: list[str] = Field(default_factory=list)
    source_documents: dict[str, str] = Field(default_factory=dict)

    @property
    def demo(self) -> bool:
        return "DEMO" in self.note

    @property
    def slug(self) -> str:
        return self.company.ticker.lower()


def period_slug(period: str) -> str:
    """'Q2 2026' -> 'q2-2026'."""
    return period.lower().replace(" ", "-")


def parse_period(value: str) -> str:
    """Accept 'q2-2026', 'Q2 2026' or 'Q2_2026' and return 'Q2 2026'."""
    return re.sub(r"[-_\s]+", " ", value.strip()).upper()


def _period_sort_key(q: Quarter) -> tuple[int, int, int]:
    order = {"Q1": (1, 0), "H1": (2, 1), "Q2": (2, 0), "9M": (3, 1), "Q3": (3, 0), "FY": (4, 1), "Q4": (4, 0)}
    month, ytd = order[q.kind]
    return (q.year, month, ytd)


def derive_missing(quarters: list[Quarter]) -> list[Quarter]:
    """Add single quarters that can be computed from year-to-date periods."""
    by_period = {q.period: q for q in quarters}
    years = {q.year for q in quarters}
    added: list[Quarter] = []

    for year in sorted(years):
        for target, (later, earlier) in DERIVATION_RULES.items():
            name = f"{target} {year}"
            later_q, earlier_q = by_period.get(f"{later} {year}"), by_period.get(f"{earlier} {year}")
            if name in by_period or not later_q or not earlier_q:
                continue
            values = {
                f: round(getattr(later_q, f) - getattr(earlier_q, f), 2)
                for f in DERIVABLE_FIELDS
                if getattr(later_q, f) is not None and getattr(earlier_q, f) is not None
            }
            if not values:
                continue
            q = Quarter(
                period=name,
                months=f"{QUARTER_MONTHS[target]} {year}",
                derived=True,
                derivation=f"{later} {year} minus {earlier} {year}.",
                derived_fields=sorted(values),
                sources=[f"computed from {earlier} {year} and {later} {year}"],
                **values,
            )
            by_period[name] = q
            added.append(q)

    for q in quarters:
        if q.derived and not q.derived_fields:
            q.derived_fields = [f for f in DERIVABLE_FIELDS if getattr(q, f) is not None]

    return sorted(quarters + added, key=_period_sort_key)


def load_file(path: Path) -> QuarterFile:
    data = json.loads(path.read_text(encoding="utf-8"))
    qf = QuarterFile.model_validate(data)
    qf.quarters = derive_missing(qf.quarters)
    return qf


def load_all() -> tuple[dict[str, QuarterFile], list[dict[str, str]]]:
    """Return (files keyed by company slug, errors). A bad file is reported, not fatal."""
    files: dict[str, QuarterFile] = {}
    errors: list[dict[str, str]] = []
    for path in sorted(settings.quarters_dir.glob("*.json")):
        try:
            qf = load_file(path)
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            errors.append({"file": path.name, "error": str(exc)})
            continue
        files[qf.slug] = _merge(files[qf.slug], qf) if qf.slug in files else qf
    return files, errors


def _merge(a: QuarterFile, b: QuarterFile) -> QuarterFile:
    """Combine two files for the same company (one file per year, e.g. qnbk_2025 + qnbk_2026)."""
    by_period = {q.period: q for q in a.quarters if not q.derived}
    by_period.update({q.period: q for q in b.quarters if not q.derived})
    quarters = derive_missing(list(by_period.values()))
    latest = max((q for q in quarters if not q.derived), key=_period_sort_key, default=quarters[-1])
    history = {h.period: h for h in a.history_net_profit + b.history_net_profit}
    return a.model_copy(update={
        "note": " ".join(n for n in (a.note, b.note) if n),
        "current_quarter": latest.period,
        "quarters": quarters,
        "history_net_profit": list(history.values()),
        "narrative_drivers": list(dict.fromkeys(a.narrative_drivers + b.narrative_drivers)),
        "source_documents": a.source_documents | b.source_documents,
    })


def quarter_view(qf: QuarterFile, q: Quarter) -> dict[str, Any]:
    """Quarter as sent to the UI, with flags the UI needs."""
    return {
        **q.model_dump(),
        "id": period_slug(q.period),
        "video_id": f"{qf.slug}-{period_slug(q.period)}",
        "is_single_quarter": q.is_single_quarter,
        "is_current": q.period == qf.current_quarter,
        "is_loss": q.net_profit is not None and q.net_profit < 0,
    }


def company_view(qf: QuarterFile) -> dict[str, Any]:
    return {
        "id": qf.slug,
        "company": qf.company.model_dump(),
        "current_quarter": qf.current_quarter,
        "demo": qf.demo,
        "note": qf.note,
        "quarters": [quarter_view(qf, q) for q in qf.quarters],
    }


def get_quarter(company: str, period: str) -> tuple[QuarterFile, Quarter] | None:
    files, _ = load_all()
    qf = files.get(company.lower())
    if not qf:
        return None
    wanted = parse_period(period)
    for q in qf.quarters:
        if q.period == wanted:
            return qf, q
    return None
