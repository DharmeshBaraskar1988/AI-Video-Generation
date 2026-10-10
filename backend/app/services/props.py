"""Build Remotion props (schema in CLAUDE.md) from an approved script, its narration timings
and the quarter file. Every number shown on screen is formatted here, in Python."""
from __future__ import annotations

import json
import re
from typing import Any

from ..config import settings
from . import factcheck as fc
from .quarters import QuarterFile

QUARTER_AR = {"Q1": "الربع الأول", "Q2": "الربع الثاني", "Q3": "الربع الثالث", "Q4": "الربع الرابع",
              "H1": "النصف الأول", "9M": "الأشهر التسعة", "FY": "العام الكامل"}
TITLES = {
    "kpis": ("Headline figures", "أبرز الأرقام"),
    "trend": ("Net profit by quarter", "صافي الربح الفصلي"),
    "drivers": ("What drove the results", "محركات النتائج"),
    "segments": ("Revenue by segment", "الإيرادات حسب القطاع"),
    "outlook": ("Financial position", "المركز المالي"),
}
TEXT = {
    "kicker": ("Quarterly results", "النتائج الفصلية"),
    "revenue": ("Revenue", "الإيرادات"),
    "net_profit": ("Net profit", "صافي الربح"),
    "net_loss": ("Net loss", "صافي الخسارة"),
    "eps": ("Earnings per share", "ربحية السهم"),
    "loss_per_share": ("Loss per share", "خسارة السهم"),
    "cash": ("Cash and bank balances", "الأرصدة النقدية والمصرفية"),
    "derived": ("Derived from published year-to-date figures, not reported", "محسوبة من الأرقام التراكمية المنشورة وليست معلنة"),
    "unit": ("QR million", "مليون ريال قطري"),
    "loss": ("loss", "خسارة"),
    "vs_prev": ("vs previous quarter", "مقارنة بالربع السابق"),
    "vs_year": ("vs same period last year", "مقارنة بالفترة نفسها من العام الماضي"),
    "demo": (
        "Demo data: Industries Qatar's published results used as sample input.",
        "بيانات تجريبية: نتائج صناعات قطر المنشورة مستخدمة كمدخلات نموذجية.",
    ),
}


def _t(key: str, lang: str) -> str:
    en, ar = TEXT[key]
    return ar if lang == "ar" else en


def period_short(period: str, lang: str) -> str:
    kind, year = period.split()
    return f"{QUARTER_AR[kind]} {year}" if lang == "ar" else period


def _pct_short(value: float) -> str:
    return f"{fc._num(abs(value), 0 if abs(value) >= 10 else 1)}%"


def _change(ph: dict, key: str | None, lang: str, basis: str) -> dict | None:
    if not key or key not in ph:
        return None
    v = float(ph[key]["value"])
    return {"text": _pct_short(v), "direction": "up" if v > 0 else "down" if v < 0 else "flat", "basis": _t(basis, lang)}


def _money_card(ph: dict, key: str, label: str, lang: str, tone: str, change: dict | None) -> dict:
    p = ph[key]
    parts = fc.qr_parts(float(p["value"]))[lang]
    return {"key": key, "label": label, **{k: parts[k] for k in ("number", "decimals", "prefix", "suffix", "text")},
            "tone": tone, "derived": bool(p["derived"]), "change": change}


def _eps_card(ph: dict, key: str, lang: str, change: dict | None) -> dict:
    v = float(ph[key]["value"])
    n = fc._num(abs(v), 2)
    label = _t("loss_per_share" if v < 0 else "eps", lang)
    prefix, suffix = ("", " ريال قطري") if lang == "ar" else ("QR ", "")
    return {"key": key, "label": label, "number": abs(v), "decimals": 2, "prefix": prefix, "suffix": suffix,
            "text": f"{prefix}{n}{suffix}", "tone": "loss" if v < 0 else "neutral",
            "derived": bool(ph[key]["derived"]), "change": change}


def _kpi_data(ph: dict, lang: str) -> dict:
    cards = []
    if "revenue" in ph:
        ch = _change(ph, "revenue_qoq_change", lang, "vs_prev") or _change(ph, "revenue_yoy_change", lang, "vs_year")
        cards.append(_money_card(ph, "revenue", _t("revenue", lang), lang, "neutral", ch))
    if "net_result" in ph:
        loss = float(ph["net_result"]["value"]) < 0
        cards.append(_money_card(ph, "net_result", _t("net_loss" if loss else "net_profit", lang), lang,
                                 "loss" if loss else "gain", _change(ph, "net_profit_yoy_change", lang, "vs_year")))
    if "eps" in ph:
        cards.append(_eps_card(ph, "eps", lang, _change(ph, "eps_yoy_change", lang, "vs_year")))
    return {"cards": cards}


def quarterly_net_profit(qf: QuarterFile) -> list[dict]:
    """Single-quarter net profit series: prior years from YTD history, current year from quarter data."""
    series: dict[str, dict] = {}
    ytd = {h.period: h.ytd_net_profit for h in qf.history_net_profit}
    for year in sorted({int(p.split()[1]) for p in ytd}):
        steps = [("Q1", "Q1", None), ("Q2", "H1", "Q1"), ("Q3", "9M", "H1"), ("Q4", "FY", "9M")]
        for q, later, earlier in steps:
            a = ytd.get(f"{later} {year}")
            b = ytd.get(f"{earlier} {year}") if earlier else 0.0
            if a is None or b is None:
                continue
            series[f"{q} {year}"] = {"period": f"{q} {year}", "value": round(a - b, 2), "derived": earlier is not None}
    for q in qf.quarters:
        if q.is_single_quarter and q.net_profit is not None:
            series[q.period] = {"period": q.period, "value": q.net_profit, "derived": q.derived}
    order = lambda p: (int(p.split()[1]), p.split()[0])  # noqa: E731
    return [series[k] for k in sorted(series, key=order)]


def _trend_data(qf: QuarterFile, quarter: str, lang: str) -> dict:
    bars = []
    for b in quarterly_net_profit(qf):
        kind, year = b["period"].split()
        n = fc._num(abs(b["value"]), 0)
        bars.append({
            "label": QUARTER_AR[kind] if lang == "ar" else kind,
            "sublabel": year,
            "value": b["value"],
            "text": f"{_t('loss', lang)} {n}" if b["value"] < 0 else n,
            "derived": b["derived"],
            "highlight": b["period"] == quarter,
        })
    return {"bars": bars, "unit": _t("unit", lang),
            "note": _t("derived", lang) if any(b["derived"] for b in bars) else None}


def _drivers_data(qf: QuarterFile, scene: dict, lang: str, placeholders: dict, digits: str) -> dict:
    extra = getattr(qf, "narrative_drivers_ar", None)
    if lang == "en":
        items = qf.narrative_drivers[:4]
    elif isinstance(extra, list) and extra:
        items = extra[:4]
    else:  # no Arabic driver list in the data file: use the Arabic narration's own sentences
        text = fc.fill(scene["ar"], placeholders, "ar", digits)
        items = [s.strip() for s in re.split(r"[.؛;]\s*", text) if len(s.strip()) > 15][:4]
    return {"items": items}


def _segments_data(ph: dict, lang: str) -> dict:
    slices = []
    for key, p in ph.items():
        m = re.match(r"^seg_(.+)_share$", key)
        if m:
            name = m.group(1)
            label = fc.SEGMENT_AR.get(name, name) if lang == "ar" else name.replace("_", " ").capitalize()
            slices.append({"label": label, "value": float(p["value"]), "text": f"{fc._num(float(p['value']), 1)}%"})
    slices.sort(key=lambda s: -s["value"])
    period = ph.get("segments_period", {}).get("value")
    return {"slices": slices, "period": period_short(period, lang) if period else None}


def _outlook_data(ph: dict, scene: dict, lang: str) -> dict:
    stats = []
    for key in scene.get("data_keys", []):
        p = ph.get(key)
        if not p:
            continue
        prefix = re.match(r"^(prev_|ytd_|)", key).group(1)
        base = key[len(prefix):]
        period_key = f"{prefix}period" if prefix else "period"
        when = period_short(ph[period_key]["value"], lang) if period_key in ph else None
        if base == "cash":
            label = _t("cash", lang)
        elif base == "revenue":
            label = _t("revenue", lang)
        elif base in ("net_result", "net_amount"):
            label = _t("net_loss" if float(p["value"]) < 0 else "net_profit", lang)
        else:
            continue
        stats.append({"label": label, "when": when, "text": fc.qr_parts(float(p["value"]))[lang]["text"],
                      "derived": bool(p["derived"])})
    return {"stats": stats[:4]}


def build_props(
    script: dict[str, Any],
    lang: str,
    narration: dict[str, Any],
    qf: QuarterFile,
    audio_src: str,
    digits: str = "western",
    captions: bool = True,
) -> dict[str, Any]:
    brand = json.loads((settings.brand_dir / "brand.json").read_text(encoding="utf-8"))
    ph = script["placeholders"]
    company = (script["company_name_ar"] if lang == "ar" else script["company_name_en"]).replace(" (demo source)", "")
    timing = {s["id"]: s for s in narration["scenes"]}

    scenes = []
    for scene in script["scenes"]:
        t = timing[scene["id"]]
        stype = scene["type"]
        if stype == "intro":
            data = {"kicker": _t("kicker", lang), "company": company, "period": period_short(script["quarter"], lang)}
        elif stype == "kpis":
            data = _kpi_data(ph, lang)
        elif stype == "trend":
            data = _trend_data(qf, script["quarter"], lang)
        elif stype == "drivers":
            data = _drivers_data(qf, scene, lang, ph, digits)
        elif stype == "segments":
            data = _segments_data(ph, lang)
        elif stype == "outlook":
            data = _outlook_data(ph, scene, lang)
        else:  # outro
            data = {"company": company, "tagline": brand["tagline_ar" if lang == "ar" else "tagline_en"],
                    "demoNote": _t("demo", lang) if script.get("demo") else None}
        if stype in TITLES:
            data["title"] = TITLES[stype][1 if lang == "ar" else 0]
        scenes.append({"id": scene["id"], "type": stype, "start": t["start"], "end": t["end"],
                       "audioStart": t["audio_start"], "text": t["text"], "data": data})

    props = {
        "language": lang,
        "direction": "rtl" if lang == "ar" else "ltr",
        "digits": digits,
        "brand": brand,
        "audio": audio_src,
        "durationSeconds": round(narration["duration"] + 1.5, 3),  # short hold on the outro
        "scenes": scenes,
        "words": [{"text": w["text"], "start": w["start"], "end": w["end"]} for w in narration["words"]],
        "captions": captions,
        "demo": bool(script.get("demo")),
        "company": company,
        "quarter": period_short(script["quarter"], lang),
    }
    # Display strings keep Western digits here; the video applies `digits` to text it shows.
    return props
