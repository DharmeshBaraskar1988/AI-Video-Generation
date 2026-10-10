"""QSE stock data: company lookup, quotes, history and news.

Prices come only from the price source (yfinance, Yahoo Finance); every change and percentage is
computed here in Python. Results are cached for STOCK_CACHE_SECONDS (default 60 s).
News (ddgs) is context for "why" questions only, never a source of prices.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)

DOHA = timezone(timedelta(hours=3))  # Qatar has no daylight saving time
SOURCE = "Yahoo Finance via yfinance"
TICKERS_PATH = Path(__file__).resolve().parents[1] / "data" / "qse_tickers.json"
# QSE continuous trading: Sunday-Thursday 09:30-13:15 Doha time
TRADING_DAYS = {6, 0, 1, 2, 3}  # Python weekday(): Mon=0 ... Sun=6
OPEN, CLOSE = (9, 30), (13, 15)

_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


class StockDataError(RuntimeError):
    """The price source could not be reached or returned no data."""


# ---------- companies ----------

_AR_DIACRITICS = re.compile(r"[ً-ْـ]")


def normalize(text: str) -> str:
    """Lowercase, unify Arabic letter variants, drop diacritics and punctuation."""
    t = _AR_DIACRITICS.sub("", text.lower())
    t = re.sub("[أإآ]", "ا", t).replace("ة", "ه").replace("ى", "ي")
    t = re.sub(r"[^\w\s&]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


@lru_cache(maxsize=1)
def companies() -> list[dict[str, Any]]:
    return json.loads(TICKERS_PATH.read_text(encoding="utf-8"))["companies"]


def resolve_companies(text: str) -> list[dict[str, Any]]:
    """Companies mentioned in the text, longest alias first, in order of appearance."""
    q = f" {normalize(text)} "
    found: list[tuple[int, int, dict]] = []
    taken: list[tuple[int, int]] = []
    candidates = [
        (normalize(alias), c) for c in companies() for alias in c["aliases"] if len(normalize(alias)) >= 2
    ]
    for alias, c in sorted(candidates, key=lambda x: -len(x[0])):
        for m in re.finditer(rf"(?<!\w){re.escape(alias)}(?!\w)", q):
            span = (m.start(), m.end())
            if any(s < span[1] and span[0] < e for s, e in taken):
                continue  # overlaps a longer name already matched
            if any(c["symbol"] == f[2]["symbol"] for f in found):
                taken.append(span)
                continue
            taken.append(span)
            found.append((m.start(), len(alias), c))
    return [c for _, _, c in sorted(found, key=lambda f: f[0])]


def find_by_symbol(symbol: str) -> dict[str, Any] | None:
    s = symbol.upper().removesuffix(".QA")
    return next((c for c in companies() if c["code"] == s), None)


# ---------- helpers ----------

def _cached(key: str, fn, ttl: float | None = None):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < (ttl or settings.stock_cache_seconds):
            return hit[1]
    value = fn()
    with _lock:
        _cache[key] = (now, value)
    return value


def r2(x: float, places: int = 2) -> float:
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def pct_change(new: float, old: float) -> float | None:
    return r2((new - old) / old * 100) if old else None


def market_status(now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(DOHA)
    open_t = now.replace(hour=OPEN[0], minute=OPEN[1], second=0, microsecond=0)
    close_t = now.replace(hour=CLOSE[0], minute=CLOSE[1], second=0, microsecond=0)
    is_open = now.weekday() in TRADING_DAYS and open_t <= now <= close_t
    return {"open": is_open, "now_doha": now.isoformat(timespec="minutes")}


# ---------- tools ----------

def get_quote(symbol: str) -> dict[str, Any]:
    """Latest price for a .QA symbol. Raises StockDataError if the source fails."""
    def fetch() -> dict[str, Any]:
        import yfinance as yf

        try:
            info = yf.Ticker(symbol).info
        except Exception as exc:  # noqa: BLE001 - any network/parse failure means no price
            raise StockDataError(f"price source unavailable for {symbol}: {exc}") from exc
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
        ts = info.get("regularMarketTime")
        if price is None or ts is None:
            raise StockDataError(f"no price returned for {symbol}")
        as_of = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(DOHA)
        status = market_status()
        change = r2(price - prev, 3) if prev else None
        return {
            "symbol": symbol,
            "price": float(price),
            "previous_close": float(prev) if prev else None,
            "change": change,
            "change_pct": pct_change(price, prev) if prev else None,
            "day_high": info.get("regularMarketDayHigh"),
            "day_low": info.get("regularMarketDayLow"),
            "volume": info.get("regularMarketVolume"),
            "currency": info.get("currency") or "QAR",
            "as_of": as_of.isoformat(timespec="minutes"),
            "as_of_hhmm": as_of.strftime("%H:%M"),
            "as_of_date": as_of.strftime("%d %b %Y"),
            "market_state": info.get("marketState"),
            "market_open": status["open"],
            "delayed": True,  # Yahoo's QSE prices are delayed
            "source": SOURCE,
            "fetched_at": datetime.now(DOHA).isoformat(timespec="seconds"),
        }

    return _cached(f"quote:{symbol}", fetch)


PROFILE_TTL = 6 * 3600  # company details change rarely


def yahoo_url(symbol: str) -> str:
    return f"https://finance.yahoo.com/quote/{symbol}"


def _big_qr(x: float | None) -> str | None:
    if not x:
        return None
    return f"QR {x / 1e9:,.2f} billion" if abs(x) >= 1e9 else f"QR {x / 1e6:,.1f} million"


def _num(x: Any, places: int = 2, suffix: str = "") -> str | None:
    return f"{float(x):,.{places}f}{suffix}" if isinstance(x, (int, float)) else None


def get_profile(symbol: str) -> dict[str, Any]:
    """Company details and valuation figures from the price source, formatted here (never by the model).
    Analyst buy/sell recommendations are left out on purpose (no investment advice)."""
    def fetch() -> dict[str, Any]:
        import yfinance as yf

        try:
            info = yf.Ticker(symbol).info
        except Exception as exc:  # noqa: BLE001
            raise StockDataError(f"profile unavailable for {symbol}: {exc}") from exc
        if not info or not (info.get("longName") or info.get("shortName") or info.get("longBusinessSummary")):
            raise StockDataError(f"no profile returned for {symbol}")
        dy = info.get("dividendYield")
        if isinstance(dy, (int, float)) and dy < 1:  # older yfinance returns a fraction
            dy = dy * 100
        low, high = info.get("fiftyTwoWeekLow"), info.get("fiftyTwoWeekHigh")
        fields = {
            "name": info.get("longName") or info.get("shortName"),
            "website": info.get("website"),
            "sector": info.get("sectorDisp") or info.get("sector"),
            "industry": info.get("industryDisp") or info.get("industry"),
            "city": info.get("city"),
            "employees": _num(info.get("fullTimeEmployees"), 0),
            "summary": (info.get("longBusinessSummary") or "")[:700] or None,
            "market_cap": _big_qr(info.get("marketCap")),
            "pe_trailing": _num(info.get("trailingPE")),
            "eps_trailing": _num(info.get("trailingEps"), 2),
            "dividend_per_share": f"QR {info['dividendRate']:.2f}" if isinstance(info.get("dividendRate"), (int, float)) else None,
            "dividend_yield": _num(dy, 2, "%"),
            "price_to_book": _num(info.get("priceToBook")),
            "week52_range": f"QR {low:.3f} - QR {high:.3f}" if low and high else None,
            "avg_50d": f"QR {info['fiftyDayAverage']:.3f}" if info.get("fiftyDayAverage") else None,
            "avg_200d": f"QR {info['twoHundredDayAverage']:.3f}" if info.get("twoHundredDayAverage") else None,
            "revenue_ttm": _big_qr(info.get("totalRevenue")),
            "net_income_ttm": _big_qr(info.get("netIncomeToCommon")),
        }
        return {"symbol": symbol, **{k: v for k, v in fields.items() if v}, "source": SOURCE, "url": yahoo_url(symbol),
                "fetched_at": datetime.now(DOHA).isoformat(timespec="minutes")}

    return _cached(f"profile:{symbol}", fetch, ttl=PROFILE_TTL)


def get_history(symbol: str, days: int) -> dict[str, Any]:
    """Daily closes over the last `days` calendar days and the change, computed here."""
    days = max(1, min(int(days), 3650))

    def fetch() -> dict[str, Any]:
        import yfinance as yf

        try:
            hist = yf.Ticker(symbol).history(period=f"{days + 10}d", interval="1d", auto_adjust=False)
        except Exception as exc:  # noqa: BLE001
            raise StockDataError(f"history unavailable for {symbol}: {exc}") from exc
        if hist is None or hist.empty:
            raise StockDataError(f"no history returned for {symbol}")
        closes = [(idx.date(), float(row["Close"])) for idx, row in hist.iterrows() if row["Close"] == row["Close"]]
        last_day, last_close = closes[-1]
        start_target = last_day - timedelta(days=days)
        start_day, start_close = next(((d, c) for d, c in reversed(closes) if d <= start_target), closes[0])
        window = [(d, c) for d, c in closes if d >= start_day]
        hi = max(window, key=lambda x: x[1])
        lo = min(window, key=lambda x: x[1])
        return {
            "symbol": symbol,
            "days": days,
            "start_date": start_day.isoformat(),
            "start_close": r2(start_close, 3),
            "end_date": last_day.isoformat(),
            "end_close": r2(last_close, 3),
            "change": r2(last_close - start_close, 3),
            "change_pct": pct_change(last_close, start_close),
            "high": r2(hi[1], 3),
            "high_date": hi[0].isoformat(),
            "low": r2(lo[1], 3),
            "low_date": lo[0].isoformat(),
            "closes": [{"date": d.isoformat(), "close": r2(c, 3)} for d, c in window],
            "source": SOURCE,
        }

    return _cached(f"history:{symbol}:{days}", fetch)


def search_news(company: dict[str, Any], max_results: int = 5) -> list[dict[str, Any]]:
    """Recent headlines (context only). Filtered to ones that mention the company."""
    def fetch() -> list[dict[str, Any]]:
        from ddgs import DDGS

        raw: list[dict] = []
        for query in (f"\"{company['name_en']}\" Qatar shares", f"{company['name_en']} {company['code']} Qatar Stock Exchange"):
            try:
                raw += list(DDGS().news(query, max_results=max_results * 3))
            except Exception as exc:  # noqa: BLE001 - news is optional
                log.warning("news search failed: %s", exc)
            if len(raw) >= max_results:
                break
        names = [normalize(a) for a in company["aliases"] if len(a) > 3]
        items = []
        for r in raw:
            text = normalize(f"{r.get('title', '')} {r.get('body', '')}")
            if any(n in text for n in names):
                items.append({"title": r.get("title"), "source": r.get("source"), "date": (r.get("date") or "")[:10],
                              "url": r.get("url"), "snippet": (r.get("body") or "")[:300]})
        return items[:max_results]

    return _cached(f"news:{company['symbol']}", fetch)


# Official pages, always offered for general market / regulator questions (no search needed)
OFFICIAL_LINKS = [
    {"title": "Qatar Stock Exchange (QSE) - official website", "url": "https://www.qe.com.qa/",
     "snippet": "Official site of the Qatar Stock Exchange: market data, listed companies, disclosures and news.",
     "keywords": ["qse", "exchange", "bourse", "market", "listed", "index", "بورصة", "السوق"]},
    {"title": "Qatar Financial Markets Authority (QFMA)", "url": "https://www.qfma.org.qa/",
     "snippet": "Regulator of Qatar's financial markets: rules, licensed companies and announcements.",
     "keywords": ["qfma", "regulator", "authority", "regulation", "هيئة", "رقابة"]},
]


def _domain(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0]


def official_links(text: str) -> list[dict[str, Any]]:
    t = normalize(text)
    return [{**{k: v for k, v in o.items() if k != "keywords"}, "source": _domain(o["url"]), "date": "", "official": True}
            for o in OFFICIAL_LINKS if any(normalize(k) in t for k in o["keywords"])]


def search_web(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """DuckDuckGo web results (title, url, snippet) for general market questions. Context and links only,
    never a source of prices or figures."""
    def fetch() -> list[dict[str, Any]]:
        from ddgs import DDGS

        try:
            raw = list(DDGS().text(query, max_results=max_results))
        except Exception as exc:  # noqa: BLE001 - search is optional
            log.warning("web search failed: %s", exc)
            return []
        return [{"title": r.get("title"), "url": r.get("href"), "snippet": (r.get("body") or "")[:300],
                 "source": _domain(r.get("href") or ""), "date": ""} for r in raw if r.get("href")]

    return _cached(f"web:{query.lower()}", fetch, ttl=3600)


def search_news_query(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """DuckDuckGo news for a free-text market question (no company)."""
    def fetch() -> list[dict[str, Any]]:
        from ddgs import DDGS

        try:
            raw = list(DDGS().news(query, max_results=max_results))
        except Exception as exc:  # noqa: BLE001
            log.warning("news search failed: %s", exc)
            return []
        return [{"title": r.get("title"), "source": r.get("source"), "date": (r.get("date") or "")[:10],
                 "url": r.get("url"), "snippet": (r.get("body") or "")[:300]} for r in raw if r.get("url")]

    return _cached(f"newsq:{query.lower()}", fetch)


def days_since_year_start(today: date | None = None) -> int:
    today = today or datetime.now(DOHA).date()
    return (today - date(today.year, 1, 1)).days
