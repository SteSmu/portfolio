"""Finnhub news + earnings calendar fetcher.

Free tier: 60 calls/min. Requires FINNHUB_API_KEY env.

Endpoints used:
  - GET /company-news       — per-stock news in date range
  - GET /news               — general market news (category=general/forex/crypto)
  - GET /calendar/earnings  — earnings calendar in date range
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx

BASE_URL = "https://finnhub.io/api/v1"
DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class FinnhubError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.getenv("FINNHUB_API_KEY", "").strip()
    if not key:
        raise FinnhubError(
            "FINNHUB_API_KEY env var not set. Get a free key at https://finnhub.io."
        )
    return key


def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=DEFAULT_TIMEOUT, transport=transport)


def fetch_company_news(
    symbol: str,
    days_back: int = 14,
    *,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """Per-stock news in the last `days_back` days. Returns asset_news rows.

    Output dict shape (compatible with `pt.db.news.upsert_many`):
      {time, source='finnhub', symbol, asset_type='stock', title, summary,
       url, sentiment=None (Finnhub free tier does not include it),
       metadata={category, image, related, id}}
    """
    if days_back < 1 or days_back > 365:
        raise ValueError("days_back must be 1..365")
    end = date.today()
    start = end - timedelta(days=days_back)
    params = {
        "symbol": symbol.upper(),
        "from": start.isoformat(),
        "to": end.isoformat(),
        "token": api_key or _api_key(),
    }
    with _client(transport=transport) as c:
        resp = c.get("/company-news", params=params)
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, dict) and data.get("error"):
        raise FinnhubError(data["error"])

    out: list[dict] = []
    for item in data:
        ts = item.get("datetime")
        if not ts:
            continue
        out.append({
            "time": datetime.fromtimestamp(int(ts), tz=timezone.utc),
            "source": "finnhub",
            "symbol": symbol.upper(),
            "asset_type": "stock",
            "title": item.get("headline") or "(untitled)",
            "summary": item.get("summary"),
            "url": item.get("url") or "",
            "sentiment": None,
            "metadata": {
                "category": item.get("category"),
                "image": item.get("image"),
                "related": item.get("related"),
                "id": item.get("id"),
                "source_label": item.get("source"),
            },
        })
    return out


def fetch_general_news(
    category: str = "general",
    *,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """Market-wide news. category=general|forex|crypto|merger.

    Stored with symbol='_MARKET_' so per-asset queries don't pick it up.
    """
    if category not in {"general", "forex", "crypto", "merger"}:
        raise ValueError(f"Unknown category: {category!r}")
    params = {"category": category, "token": api_key or _api_key()}
    with _client(transport=transport) as c:
        resp = c.get("/news", params=params)
        resp.raise_for_status()
        data = resp.json()

    if isinstance(data, dict) and data.get("error"):
        raise FinnhubError(data["error"])

    out: list[dict] = []
    asset_type = "crypto" if category == "crypto" else "fx" if category == "forex" else "stock"
    for item in data:
        ts = item.get("datetime")
        if not ts:
            continue
        out.append({
            "time": datetime.fromtimestamp(int(ts), tz=timezone.utc),
            "source": "finnhub",
            "symbol": "_MARKET_",
            "asset_type": asset_type,
            "title": item.get("headline") or "(untitled)",
            "summary": item.get("summary"),
            "url": item.get("url") or "",
            "sentiment": None,
            "metadata": {"category": category, "id": item.get("id"),
                          "source_label": item.get("source")},
        })
    return out


def fetch_earnings_calendar(
    days_ahead: int = 30,
    symbol: str | None = None,
    *,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """Upcoming earnings events.

    Returns list of {symbol, date, eps_estimate, eps_actual, hour, ...}.
    """
    if days_ahead < 1 or days_ahead > 365:
        raise ValueError("days_ahead must be 1..365")
    today = date.today()
    end = today + timedelta(days=days_ahead)
    params: dict = {
        "from": today.isoformat(),
        "to": end.isoformat(),
        "token": api_key or _api_key(),
    }
    if symbol:
        params["symbol"] = symbol.upper()

    with _client(transport=transport) as c:
        resp = c.get("/calendar/earnings", params=params)
        resp.raise_for_status()
        data = resp.json()

    cal = data.get("earningsCalendar", []) if isinstance(data, dict) else []
    out: list[dict] = []
    for e in cal:
        out.append({
            "symbol": e.get("symbol", "").upper(),
            "date": e.get("date"),
            "hour": e.get("hour"),
            "eps_estimate": Decimal(str(e.get("epsEstimate"))) if e.get("epsEstimate") is not None else None,
            "eps_actual": Decimal(str(e.get("epsActual"))) if e.get("epsActual") is not None else None,
            "revenue_estimate": e.get("revenueEstimate"),
            "revenue_actual": e.get("revenueActual"),
            "year": e.get("year"),
            "quarter": e.get("quarter"),
        })
    return out
