"""Frankfurter — ECB-based FX rates. Free, no API key, no rate limits.

Docs: https://frankfurter.dev — sources its data from ECB's daily reference rates.

We persist FX rates into public.market_meta with source='frankfurter' and
symbol=<BASE><QUOTE> (e.g. 'EURUSD'), value=rate.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import httpx

BASE_URL = "https://api.frankfurter.dev/v1"
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=DEFAULT_TIMEOUT, transport=transport)


def fetch_latest(
    base: str = "EUR",
    quotes: list[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Latest ECB FX rates.

    Returns: {"date": "YYYY-MM-DD", "base": "EUR", "rates": {"USD": 1.085, ...}}
    """
    params: dict = {"base": base.upper()}
    if quotes:
        params["symbols"] = ",".join(q.upper() for q in quotes)
    with _client(transport=transport) as c:
        resp = c.get("/latest", params=params)
        resp.raise_for_status()
        return resp.json()


def fetch_historical(
    on_date: date,
    base: str = "EUR",
    quotes: list[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Single-day historical rate."""
    params: dict = {"base": base.upper()}
    if quotes:
        params["symbols"] = ",".join(q.upper() for q in quotes)
    with _client(transport=transport) as c:
        resp = c.get(f"/{on_date.isoformat()}", params=params)
        resp.raise_for_status()
        return resp.json()


def fetch_time_series(
    start: date,
    end: date,
    base: str = "EUR",
    quotes: list[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Daily rates between start and end (inclusive)."""
    if start > end:
        raise ValueError(f"start {start} must be <= end {end}")
    params: dict = {"base": base.upper()}
    if quotes:
        params["symbols"] = ",".join(q.upper() for q in quotes)
    with _client(transport=transport) as c:
        resp = c.get(f"/{start.isoformat()}..{end.isoformat()}", params=params)
        resp.raise_for_status()
        return resp.json()


def to_market_meta_rows(payload: dict) -> list[dict]:
    """Convert a Frankfurter payload into market_meta-shaped rows.

    Handles both single-day (`/latest`, `/<date>`) and time-series payloads.

    Single-day: {"date": "YYYY-MM-DD", "base": "EUR", "rates": {...}}
    Time-series: {"start_date":..., "end_date":..., "base":"EUR", "rates": {date: {ccy: rate}}}
    """
    base = payload.get("base", "EUR").upper()
    out: list[dict] = []

    if "rates" not in payload:
        return out

    rates = payload["rates"]

    # Time-series shape: rates is {date_str: {ccy: rate}}
    if rates and isinstance(next(iter(rates.values())), dict):
        for date_str, currencies in rates.items():
            t = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
            for ccy, rate in currencies.items():
                out.append({
                    "time": t,
                    "source": "frankfurter",
                    "symbol": f"{base}{ccy.upper()}",
                    "value": Decimal(str(rate)),
                    "metadata": {"base": base, "quote": ccy.upper()},
                })
        return out

    # Single-day shape
    date_str = payload.get("date")
    if not date_str:
        return out
    t = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    for ccy, rate in rates.items():
        out.append({
            "time": t,
            "source": "frankfurter",
            "symbol": f"{base}{ccy.upper()}",
            "value": Decimal(str(rate)),
            "metadata": {"base": base, "quote": ccy.upper()},
        })
    return out
