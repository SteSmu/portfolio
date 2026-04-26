"""Twelve Data fetcher — Stocks, ETFs, indices, and FX.

Free tier: 800 calls/day, 8 calls/min. Requires TWELVE_DATA_API_KEY env.

Endpoints used:
  - GET /quote          — current snapshot
  - GET /time_series    — OHLCV historical
  - GET /symbol_search  — symbol lookup
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

import httpx

BASE_URL = "https://api.twelvedata.com"
DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


class TwelveDataError(RuntimeError):
    pass


def _api_key() -> str:
    key = os.getenv("TWELVE_DATA_API_KEY", "").strip()
    if not key:
        raise TwelveDataError(
            "TWELVE_DATA_API_KEY env var not set. Get a free key at https://twelvedata.com."
        )
    return key


def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=DEFAULT_TIMEOUT, transport=transport)


def fetch_quote(
    symbol: str,
    *,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Current quote for one symbol."""
    params = {"symbol": symbol, "apikey": api_key or _api_key()}
    with _client(transport=transport) as c:
        resp = c.get("/quote", params=params)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status") == "error":
        raise TwelveDataError(data.get("message", "Unknown Twelve Data error"))
    return data


def fetch_time_series(
    symbol: str,
    interval: str = "1day",
    outputsize: int = 365,
    *,
    api_key: str | None = None,
    asset_type: str = "stock",
    exchange: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """Historical OHLCV bars.

    interval: 1min, 5min, 15min, 30min, 45min, 1h, 2h, 4h, 1day, 1week, 1month
    outputsize: max 5000

    Returns list of candle dicts ready for `store.insert_candles()`.
    """
    if outputsize < 1 or outputsize > 5000:
        raise ValueError("outputsize must be 1..5000")
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key or _api_key(),
    }
    with _client(transport=transport) as c:
        resp = c.get("/time_series", params=params)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status") == "error":
        raise TwelveDataError(data.get("message", "Unknown Twelve Data error"))

    values = data.get("values", [])
    interval_norm = _normalize_interval(interval)
    out = []
    for row in values:
        out.append({
            "time": _parse_dt(row["datetime"]),
            "symbol": symbol.upper(),
            "interval": interval_norm,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume") or 0),
            "source": "twelve_data",
            "asset_type": asset_type,
            "exchange": exchange or data.get("meta", {}).get("exchange"),
        })
    return out


def search_symbol(
    query: str,
    *,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """Symbol search — returns matches with exchange, country, instrument type."""
    params = {"symbol": query, "apikey": api_key or _api_key()}
    with _client(transport=transport) as c:
        resp = c.get("/symbol_search", params=params)
        resp.raise_for_status()
        data = resp.json()
    return data.get("data", [])


def _parse_dt(s: str) -> datetime:
    # Twelve Data returns 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'
    fmt = "%Y-%m-%d %H:%M:%S" if " " in s else "%Y-%m-%d"
    return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)


def _normalize_interval(interval: str) -> str:
    """Map Twelve Data intervals onto our internal interval strings."""
    mapping = {
        "1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m", "45min": "45m",
        "1h": "1h", "2h": "2h", "4h": "4h",
        "1day": "1d", "1week": "1w", "1month": "1M",
    }
    return mapping.get(interval, interval)
