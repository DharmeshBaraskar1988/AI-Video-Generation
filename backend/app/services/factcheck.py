"""Numbers never come from the language model.

- `build_placeholders` turns the quarter file into {{placeholder}} values with display strings
  formatted here in Python (EN + AR). Percentage changes are computed here too.
- `check_text` / `check_script` find any digit or number word the model typed itself, unknown
  placeholders, and placeholders that the Arabic translation dropped or added.
- `fill` replaces placeholders with their display strings for narration and captions.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .quarters import Quarter, QuarterFile

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
# Western, Arabic-Indic and Extended Arabic-Indic digits, with decimal/thousand separators
DIGIT_RE = re.compile(r"[0-9٠-٩۰-۹]+(?:[.,٫٬][0-9٠-٩۰-۹]+)*")
# "one" is left out on purpose: too common in normal English ("one of the region's ...")
NUMBER_WORDS_EN = re.compile(
    r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundreds?|thousands?|millions?|billions?|bn|percent|per cent|dozens?)\b|%",
    re.I,
)
NUMBER_WORDS_AR = re.compile(
    r"(?:مليون|ملايين|مليار|مليارات|ألف|آلاف|بالمئة|بالمائة|في المئة|في المائة|٪|%|"
    r"\b[وفبل]?(?:اثنان|اثنين|اثني|ثلاثة|أربعة|خمسة|ستة|سبعة|ثمانية|تسعة|عشرة|عشر|عشرين|عشرون|ثلاثين|أربعين|خمسين|مئة|مائة)\b)"
)

EASTERN_DIGITS = str.maketrans("0123456789.", "٠١٢٣٤٥٦٧٨٩٫")

PERIOD_NAMES = {
    "Q1": ("the first quarter of {y}", "الربع الأول من عام {y}"),
    "Q2": ("the second quarter of {y}", "الربع الثاني من عام {y}"),
    "Q3": ("the third quarter of {y}", "الربع الثالث من عام {y}"),
    "Q4": ("the fourth quarter of {y}", "الربع الرابع من عام {y}"),
    "H1": ("the first half of {y}", "النصف الأول من عام {y}"),
    "9M": ("the first nine months of {y}", "الأشهر التسعة الأولى من عام {y}"),
    "FY": ("the full year {y}", "كامل عام {y}"),
}
# single quarter -> year-to-date period that ends with it
YTD_OF = {"Q2": "H1", "Q3": "9M", "Q4": "FY"}
PREV_QUARTER = {"Q2": "Q1", "Q3": "Q2", "Q4": "Q3"}
SEGMENT_AR = {"petrochemicals": "البتروكيماويات", "fertilisers": "الأسمدة", "fertilizers": "الأسمدة", "steel": "الحديد والصلب"}


# ---------- formatting (the only place display numbers are produced) ----------

def _num(value: float, decimals: int) -> str:
    """Round half up (not banker's rounding) and drop a trailing '.0'."""
    q = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    text = f"{q:,.{decimals}f}"
    if decimals and text.endswith("0" * decimals):
        text = text[: -(decimals + 1)]
    return text


def qr_parts(value_million: float) -> dict[str, dict[str, Any]]:
    """Absolute amount split for animated counters: prefix + number(decimals) + suffix per language.
    The joined text is exactly what format_qr returns."""
    v = abs(value_million)
    if v >= 1000:
        n = _num(v / 1000, 1)
        unit_en, unit_ar = " billion", " مليار ريال قطري"
    else:
        n = _num(v, 0)
        unit_en, unit_ar = " million", " مليون ريال قطري"
    number = float(n.replace(",", ""))
    decimals = len(n.split(".")[1]) if "." in n else 0
    return {
        "en": {"number": number, "decimals": decimals, "prefix": "QR ", "suffix": unit_en, "text": f"QR {n}{unit_en}"},
        "ar": {"number": number, "decimals": decimals, "prefix": "", "suffix": unit_ar, "text": f"{n}{unit_ar}"},
    }


def format_qr(value_million: float) -> tuple[str, str]:
    """Absolute amount in QR million -> ('QR 1.7 billion', '1.7 مليار ريال قطري')."""
    parts = qr_parts(value_million)
    return parts["en"]["text"], parts["ar"]["text"]


def format_result(value_million: float) -> tuple[str, str]:
    """Signed net result -> 'a net profit of ...' / 'a net loss of ...' (never '-518')."""
    en, ar = format_qr(value_million)
    if value_million < 0:
        return f"a net loss of {en}", f"صافي خسارة بقيمة {ar}"
    return f"a net profit of {en}", f"صافي ربح بقيمة {ar}"


def format_eps(value_qr: float) -> tuple[str, str]:
    n = _num(abs(value_qr), 2)
    if value_qr < 0:
        return f"a loss per share of QR {n}", f"خسارة للسهم بقيمة {n} ريال قطري"
    return f"QR {n}", f"{n} ريال قطري"


def format_pct(value: float, decimals: int | None = None) -> tuple[str, str]:
    """Changes >= 10% read as whole numbers; shares keep one decimal (decimals=1)."""
    if decimals is None:
        decimals = 0 if abs(value) >= 10 else 1
    n = _num(abs(value), decimals)
    return f"{n} percent", f"{n} بالمئة"


def format_change(current: float, prior: float) -> tuple[float, str, str] | None:
    """Percentage change, only when it is meaningful (positive base, no sign flip)."""
    if prior <= 0 or current < 0:
        return None
    pct = (current - prior) / prior * 100
    en, ar = format_pct(pct)
    if abs(pct) < 0.05:
        return pct, "unchanged", "دون تغيير"
    if pct > 0:
        return pct, f"up {en}", f"بارتفاع {ar}"
    return pct, f"down {en}", f"بانخفاض {ar}"


def period_names(period: str) -> tuple[str, str]:
    kind, year = period.split()
    en, ar = PERIOD_NAMES[kind]
    return en.format(y=year), ar.format(y=year)


def to_eastern_digits(text: str) -> str:
    return text.translate(EASTERN_DIGITS)


# ---------- placeholders ----------

def _ph(value: Any, en: str, ar: str, label: str, derived: bool = False) -> dict[str, Any]:
    return {"value": value, "display_en": en, "display_ar": ar, "derived": derived, "label": label}


def _quarter_figures(prefix: str, q: Quarter, what: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    d = set(q.derived_fields) if q.derived else set()
    if q.revenue is not None:
        out[f"{prefix}revenue"] = _ph(q.revenue, *format_qr(q.revenue), f"revenue, {what}", "revenue" in d)
    if q.net_profit is not None:
        out[f"{prefix}net_result"] = _ph(
            q.net_profit, *format_result(q.net_profit),
            f"net result phrase ('a net profit of ...' or 'a net loss of ...'), {what}", "net_profit" in d,
        )
        out[f"{prefix}net_amount"] = _ph(
            q.net_profit, *format_qr(q.net_profit),
            f"size of the net {'loss' if q.net_profit < 0 else 'profit'} without sign, {what}", "net_profit" in d,
        )
    if q.eps_qr is not None:
        out[f"{prefix}eps"] = _ph(q.eps_qr, *format_eps(q.eps_qr), f"earnings per share, {what}", "eps_qr" in d)
    cash = getattr(q, "cash_and_bank", None)
    if isinstance(cash, (int, float)):
        out[f"{prefix}cash"] = _ph(cash, *format_qr(cash), f"cash and bank balances at end of {what}")
    return out


def _comparatives(prefix: str, q: Quarter, what: str) -> dict[str, dict[str, Any]]:
    """comparatives like {'net_profit_h1_2025': 2000} -> prior value + computed change."""
    out: dict[str, dict[str, Any]] = {}
    comps = getattr(q, "comparatives", None) or {}
    for key, prior in comps.items():
        m = re.match(r"^(revenue|net_profit|eps)_([a-z0-9]+)_(\d{4})$", key)
        if not m or not isinstance(prior, (int, float)):
            continue  # e.g. net_profit_change_pct: we compute changes ourselves
        metric, _, year = m.groups()
        label = f"same period of {year}"
        current = {"revenue": q.revenue, "net_profit": q.net_profit, "eps": q.eps_qr}[metric]
        if metric == "eps":
            out[f"{prefix}eps_prior_year"] = _ph(prior, *format_eps(prior), f"earnings per share, {label}")
        elif metric == "revenue":
            out[f"{prefix}revenue_prior_year"] = _ph(prior, *format_qr(prior), f"revenue, {label}")
        else:
            out[f"{prefix}net_result_prior_year"] = _ph(prior, *format_result(prior), f"net result phrase, {label}")
        if current is not None:
            change = format_change(current, prior)
            if change:
                pct, en, ar = change
                out[f"{prefix}{metric}_yoy_change"] = _ph(
                    round(pct, 2), en, ar, f"change in {metric.replace('_', ' ')} of {what} versus {label}"
                )
    return out


def build_placeholders(qf: QuarterFile, q: Quarter) -> dict[str, dict[str, Any]]:
    by_period = {x.period: x for x in qf.quarters}
    kind, year = q.period.split()
    ph: dict[str, dict[str, Any]] = {}

    en, ar = period_names(q.period)
    ph["period"] = _ph(q.period, en, ar, "name of this reporting period")
    ph["year"] = _ph(int(year), year, year, "the year")
    ph.update(_quarter_figures("", q, "this period"))
    ph.update(_comparatives("", q, "this period"))

    prev = by_period.get(f"{PREV_QUARTER[kind]} {year}") if kind in PREV_QUARTER else None
    if prev:
        en, ar = period_names(prev.period)
        ph["prev_period"] = _ph(prev.period, en, ar, "name of the previous quarter")
        ph.update(_quarter_figures("prev_", prev, "previous quarter"))
        if q.revenue is not None and prev.revenue is not None:
            change = format_change(q.revenue, prev.revenue)
            if change:
                pct, en, ar = change
                ph["revenue_qoq_change"] = _ph(
                    round(pct, 2), en, ar, "change in revenue versus the previous quarter",
                    q.derived or prev.derived,
                )

    ytd = by_period.get(f"{YTD_OF[kind]} {year}") if kind in YTD_OF else None
    if ytd:
        en, ar = period_names(ytd.period)
        ph["ytd_period"] = _ph(ytd.period, en, ar, "name of the year-to-date period")
        ph.update(_quarter_figures("ytd_", ytd, "year to date"))
        ph.update(_comparatives("ytd_", ytd, "year to date"))

    seg_source = next((x for x in (q, ytd) if x is not None and getattr(x, "segment_revenue_share_pct", None)), None)
    if seg_source:
        en, ar = period_names(seg_source.period)
        ph["segments_period"] = _ph(seg_source.period, en, ar, "period the segment shares refer to")
        for name, share in seg_source.segment_revenue_share_pct.items():
            ph[f"seg_{name}_share"] = _ph(
                share, *format_pct(share, 1), f"{name} share of revenue ({SEGMENT_AR.get(name, name)})"
            )

    for h in qf.history_net_profit:
        hk, hy = h.period.split()
        en, ar = period_names(h.period)
        slug = f"{hk.lower()}_{hy}"
        ph[f"hist_{slug}_period"] = _ph(h.period, en, ar, f"name of period {h.period}")
        ph[f"hist_{slug}_net_result"] = _ph(
            h.ytd_net_profit, *format_result(h.ytd_net_profit), f"net result phrase, {h.period} (year to date)"
        )

    return ph


# ---------- checking ----------

def _strip_placeholders(text: str) -> str:
    return PLACEHOLDER_RE.sub(" ", text)


def check_text(text: str, placeholders: dict[str, Any], lang: str) -> dict[str, list[str]]:
    used = PLACEHOLDER_RE.findall(text)
    bare = _strip_placeholders(text)
    words_re = NUMBER_WORDS_AR if lang == "ar" else NUMBER_WORDS_EN
    stray = DIGIT_RE.findall(bare) + [m.group(0) for m in words_re.finditer(bare)]
    return {
        "used": [k for k in used if k in placeholders],
        "unknown": [k for k in used if k not in placeholders],
        "stray": stray,
    }


def check_script(scenes: list[dict[str, Any]], placeholders: dict[str, Any], langs: tuple[str, ...] = ("en", "ar")) -> dict[str, Any]:
    total = ok = 0
    stray: list[dict[str, str]] = []
    unknown: list[dict[str, str]] = []
    mismatch: list[dict[str, Any]] = []

    for scene in scenes:
        per_lang = {}
        for lang in langs:
            text = scene.get(lang) or ""
            r = check_text(text, placeholders, lang)
            per_lang[lang] = r
            total += len(r["used"]) + len(r["unknown"]) + len(r["stray"])
            ok += len(r["used"])
            stray += [{"scene": scene["id"], "lang": lang, "text": s} for s in r["stray"]]
            unknown += [{"scene": scene["id"], "lang": lang, "key": k} for k in r["unknown"]]
        if "en" in per_lang and "ar" in per_lang and scene.get("ar"):
            en_keys, ar_keys = sorted(per_lang["en"]["used"]), sorted(per_lang["ar"]["used"])
            if en_keys != ar_keys:
                mismatch.append({"scene": scene["id"], "en": en_keys, "ar": ar_keys})

    return {
        "numbers_total": total,
        "numbers_ok": ok,
        "stray_numbers": stray,
        "unknown_placeholders": unknown,
        "placeholder_mismatch": mismatch,
    }


def checks_pass(checks: dict[str, Any]) -> bool:
    return (
        checks["numbers_ok"] == checks["numbers_total"]
        and not checks["stray_numbers"]
        and not checks["unknown_placeholders"]
        and not checks.get("placeholder_mismatch")
    )


def fill(text: str, placeholders: dict[str, Any], lang: str, arabic_digits: str = "western") -> str:
    def repl(m: re.Match) -> str:
        p = placeholders.get(m.group(1))
        if not p:
            return m.group(0)
        value = p[f"display_{lang}"]
        return to_eastern_digits(value) if lang == "ar" and arabic_digits == "eastern" else value

    return PLACEHOLDER_RE.sub(repl, text)


def word_count(text: str) -> int:
    return len(text.split())


# Measured speaking speed of the default edge-tts voices (words per minute, pauses excluded):
# en-US-GuyNeural ~131, ar-QA-MoazNeural ~104. Used for length estimates and the word target.
WPM = {"en": 131, "ar": 104}
SCENE_PAUSE_SECONDS = 0.6
MIN_VIDEO_SECONDS = 120  # product rule: every video (EN and AR) runs 2-3 minutes
MAX_VIDEO_SECONDS = 180
# Measured: the Arabic narration runs ~1.22-1.29x as long as the English it was translated from.
AR_LENGTH_RATIO = 1.27


def estimate_seconds(word_total: int, lang: str, scene_count: int) -> int:
    return round(word_total / WPM[lang] * 60 + SCENE_PAUSE_SECONDS * max(0, scene_count - 1))


def words_for_seconds(seconds: float, lang: str, scene_count: int) -> int:
    """Word budget that narrates in `seconds` (inverse of estimate_seconds)."""
    speech = max(0.0, seconds - SCENE_PAUSE_SECONDS * max(0, scene_count - 1))
    return int(speech * WPM[lang] / 60)


def length_enforced() -> bool:
    """Admin switch `enforce_length`: when off, the 2-3 minute range is a target only, never a block."""
    from .app_settings import get_setting

    return bool(get_setting("enforce_length"))


def length_ok(seconds_en: float, seconds_ar: float) -> bool:
    if not length_enforced():
        return True
    return MIN_VIDEO_SECONDS <= min(seconds_en, seconds_ar) and max(seconds_en, seconds_ar) <= MAX_VIDEO_SECONDS


def scene_keys(text: str, placeholders: dict[str, Any]) -> list[str]:
    """Known placeholder keys in a text, in order of first use."""
    return [k for k in dict.fromkeys(PLACEHOLDER_RE.findall(text)) if k in placeholders]


def full_checks(
    scenes: list[dict[str, Any]],
    placeholders: dict[str, Any],
    arabic_digits: str = "western",
    repairs: list[str] | None = None,
) -> dict[str, Any]:
    """check_script plus pass flag and length figures (150 words per minute in English)."""
    checks = check_script(scenes, placeholders)
    words_en = sum(word_count(fill(s.get("en", ""), placeholders, "en")) for s in scenes)
    words_ar = sum(word_count(fill(s.get("ar", ""), placeholders, "ar", arabic_digits)) for s in scenes)
    sec_en = estimate_seconds(words_en, "en", len(scenes))
    sec_ar = estimate_seconds(words_ar, "ar", len(scenes))
    return {
        **checks,
        "passed": checks_pass(checks),
        "repairs": repairs or [],
        "words_en": words_en,
        "words_ar": words_ar,
        "estimated_seconds_en": sec_en,
        "estimated_seconds_ar": sec_ar,
        "min_seconds": MIN_VIDEO_SECONDS,
        "max_seconds": MAX_VIDEO_SECONDS,
        "length_ok": length_ok(sec_en, sec_ar),
        "enforce_length": length_enforced(),
    }
