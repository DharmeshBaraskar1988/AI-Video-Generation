"""Build backend/app/data/qse_tickers.json: QSE-listed companies with EN/AR names, aliases and the
Yahoo symbol (ending .QA). Every symbol is checked with yfinance; ones without recent data are dropped.

Run from the repo root:  backend\\.venv\\Scripts\\python -m backend.scripts.build_qse_tickers
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import yfinance as yf

from backend.app.config import ROOT

# (code, English name, Arabic name, sector, extra aliases)
CANDIDATES: list[tuple[str, str, str, str, list[str]]] = [
    ("QNBK", "QNB Group", "بنك قطر الوطني", "Banks", ["QNB", "Qatar National Bank", "كيو إن بي"]),
    ("QIBK", "Qatar Islamic Bank", "مصرف قطر الإسلامي", "Banks", ["QIB", "المصرف"]),
    ("CBQK", "Commercial Bank of Qatar", "البنك التجاري", "Banks", ["CBQ", "Commercial Bank", "التجاري"]),
    ("MARK", "Masraf Al Rayan", "مصرف الريان", "Banks", ["Al Rayan", "QIIB Rayan", "الريان"]),
    ("DUBK", "Dukhan Bank", "بنك دخان", "Banks", ["Dukhan"]),
    ("QIIK", "Qatar International Islamic Bank", "بنك قطر الدولي الإسلامي", "Banks", ["QIIB", "الدولي الإسلامي"]),
    ("DHBK", "Doha Bank", "بنك الدوحة", "Banks", []),
    ("ABQK", "Ahli Bank", "البنك الأهلي", "Banks", ["Al Ahli Bank", "الأهلي"]),
    ("QFBQ", "Lesha Bank", "بنك لشا", "Banks", ["Qatar First Bank", "QFB", "لشا"]),
    ("IQCD", "Industries Qatar", "صناعات قطر", "Industrials", ["IQ", "Industries Qatar QPSC"]),
    ("QAMC", "Qatar Aluminium Manufacturing", "قطر لصناعة الألمنيوم", "Industrials", ["QAMCO", "Qatar Aluminium", "قامكو"]),
    ("MPHC", "Mesaieed Petrochemical Holding", "مسيعيد للبتروكيماويات", "Industrials", ["Mesaieed", "مسيعيد"]),
    ("QIMD", "Qatar Industrial Manufacturing", "قطر للصناعات التحويلية", "Industrials", ["QIMC"]),
    ("QNCD", "Qatar National Cement", "قطر الوطنية لصناعة الإسمنت", "Industrials", ["QNCC", "الإسمنت"]),
    ("QGMD", "Qatar German Medical Devices", "قطر الألمانية للمستلزمات الطبية", "Industrials", ["QGMD"]),
    ("QEWS", "Qatar Electricity & Water", "الكهرباء والماء القطرية", "Industrials", ["QEWC", "Qatar Electricity and Water", "الكهرباء والماء"]),
    ("GISS", "Gulf International Services", "الخليج الدولية للخدمات", "Industrials", ["GIS", "الخليج الدولية"]),
    ("QFLS", "Qatar Fuel", "قطر للوقود", "Industrials", ["Woqod", "وقود"]),
    ("AHCS", "Aamal Company", "أعمال", "Industrials", ["Aamal", "شركة أعمال"]),
    ("IGRD", "Estithmar Holding", "استثمار القابضة", "Industrials", ["Estithmar", "Investment Holding Group", "استثمار"]),
    ("ORDS", "Ooredoo", "أريدُ", "Telecoms", ["Ooredoo Qatar", "أوريدو", "اريد"]),
    ("VFQS", "Vodafone Qatar", "فودافون قطر", "Telecoms", ["Vodafone", "فودافون"]),
    ("QGTS", "Qatar Gas Transport (Nakilat)", "ناقلات", "Transportation", ["Nakilat", "Qatar Gas Transport"]),
    ("QNNS", "Qatar Navigation (Milaha)", "الملاحة القطرية", "Transportation", ["Milaha", "Qatar Navigation", "ملاحة"]),
    ("GWCS", "Gulf Warehousing", "الخليج للمخازن", "Transportation", ["GWC", "Gulf Warehousing Company"]),
    ("BRES", "Barwa Real Estate", "بروة العقارية", "Real Estate", ["Barwa", "بروة"]),
    ("ERES", "Ezdan Holding", "إزدان القابضة", "Real Estate", ["Ezdan", "إزدان"]),
    ("UDCD", "United Development Company", "المتحدة للتنمية", "Real Estate", ["UDC", "United Development"]),
    ("MRDS", "Mazaya Real Estate", "مزايا العقارية", "Real Estate", ["Mazaya", "مزايا"]),
    ("QATI", "Qatar Insurance", "قطر للتأمين", "Insurance", ["QIC", "Qatar Insurance Company"]),
    ("QGRI", "Qatar General Insurance & Reinsurance", "القطرية العامة للتأمين وإعادة التأمين", "Insurance", ["QGIRCO"]),
    ("DOHI", "Doha Insurance", "الدوحة للتأمين", "Insurance", ["Doha Insurance Group"]),
    ("AKHI", "Al Khaleej Takaful", "الخليج للتأمين التكافلي", "Insurance", ["Al Khaleej Takaful Insurance", "الخليج التكافلي"]),
    ("QISI", "Qatar Islamic Insurance", "قطر الإسلامية للتأمين", "Insurance", ["QIIC"]),
    ("BEMA", "Damaan Islamic Insurance (Beema)", "الضمان للتأمين الإسلامي (بيمه)", "Insurance", ["Beema", "Damaan", "بيمه"]),
    ("QLMI", "QLM Life & Medical Insurance", "كيو إل إم للتأمين على الحياة والتأمين الصحي", "Insurance", ["QLM"]),
    ("MCCS", "Mannai Corporation", "مجمع شركات المناعي", "Consumer", ["Mannai", "المناعي"]),
    ("MERS", "Al Meera Consumer Goods", "الميرة للمواد الاستهلاكية", "Consumer", ["Al Meera", "Meera", "الميرة"]),
    ("ZHCD", "Zad Holding", "زاد القابضة", "Consumer", ["Zad", "زاد"]),
    ("QCFS", "Qatar Cinema & Film Distribution", "قطر للسينما وتوزيع الأفلام", "Consumer", ["Qatar Cinema"]),
    ("WDAM", "Widam Food", "ودام الغذائية", "Consumer", ["Widam", "ودام"]),
    ("MCGS", "Medicare Group", "مجموعة الرعاية الطبية", "Consumer", ["Medicare", "الرعاية الطبية"]),
    ("SIIS", "Salam International Investment", "السلام العالمية للاستثمار", "Consumer", ["Salam International", "السلام العالمية"]),
    ("BLDN", "Baladna", "بلدنا", "Consumer", []),
    ("FALH", "Al Faleh Educational Holding", "الفالح التعليمية القابضة", "Consumer", ["Al Faleh", "الفالح"]),
    ("MEZA", "Meeza QSTP", "ميزة", "Consumer", ["Meeza", "ميزة كيو إس تي بي"]),
    ("QIGD", "Qatari Investors Group", "مجموعة المستثمرين القطريين", "Consumer", ["Qatari Investors", "المستثمرين القطريين"]),
    ("DBIS", "Dlala Brokerage & Investment Holding", "دلالة للوساطة والاستثمار القابضة", "Financial Services", ["Dlala", "دلالة"]),
    ("IHGS", "Inma Holding", "إنماء القابضة", "Financial Services", ["Inma", "إنماء"]),
    ("NLCS", "Alijarah Holding", "الإجارة القابضة", "Financial Services", ["National Leasing", "Alijarah", "الإجارة"]),
    ("QOIS", "Qatar Oman Investment", "قطر وعمان للاستثمار", "Financial Services", ["Qatar Oman"]),
    ("MKDM", "Mekdam Holding Group", "مقدام القابضة", "Industrials", ["Mekdam", "مقدام"]),
    ("MHAR", "Al Mahhar Holding", "المهار القابضة", "Industrials", ["Al Mahhar", "المهار"]),
    ("TQES", "Techno Q", "تكنو كيو", "Industrials", ["TechnoQ"]),
]


def main() -> None:
    symbols = [f"{code}.QA" for code, *_ in CANDIDATES]
    data = yf.download(symbols, period="1mo", progress=False, auto_adjust=False, group_by="column")
    closes = data["Close"]
    kept, dropped = [], []
    for code, name_en, name_ar, sector, aliases in CANDIDATES:
        sym = f"{code}.QA"
        series = closes[sym].dropna() if sym in closes else []
        if len(series) == 0:
            dropped.append(sym)
            continue
        kept.append({
            "symbol": sym,
            "code": code,
            "name_en": name_en,
            "name_ar": name_ar,
            "sector": sector,
            "aliases": sorted({code, name_en, name_ar, *aliases}),
            "last_close_checked": round(float(series.iloc[-1]), 3),
        })
    out = ROOT / "backend" / "app" / "data" / "qse_tickers.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "_note": "QSE companies with Yahoo Finance symbols. Built and verified by backend/scripts/build_qse_tickers.py.",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "dropped": dropped,
        "companies": kept,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"kept {len(kept)}, dropped {len(dropped)}: {dropped}")


if __name__ == "__main__":
    main()
