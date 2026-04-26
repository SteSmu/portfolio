"""CoinGecko fetcher — Crypto prices (free tier, no API key).

Endpoints used:
  - GET /api/v3/simple/price       — current spot price (multi-coin, multi-currency)
  - GET /api/v3/coins/{id}/ohlc    — OHLC candles (4h granularity for ≤90d, daily otherwise)
  - GET /api/v3/coins/list         — symbol → coingecko-id mapping (cached)

Free-tier rate limit: ~10-30 req/min. We add a small `httpx.Timeout` and let
the caller back off if 429s occur.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx

BASE_URL = "https://api.coingecko.com/api/v3"
DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def _client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=DEFAULT_TIMEOUT, transport=transport)


def fetch_spot_prices(
    coin_ids: list[str],
    vs_currencies: list[str],
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, dict[str, Decimal]]:
    """Current spot prices.

    Returns: {coin_id: {currency: price as Decimal}}.
    Example call: fetch_spot_prices(["bitcoin", "ethereum"], ["usd", "eur"])
    """
    if not coin_ids or not vs_currencies:
        return {}
    params = {"ids": ",".join(coin_ids), "vs_currencies": ",".join(vs_currencies)}
    with _client(transport=transport) as c:
        resp = c.get("/simple/price", params=params)
        resp.raise_for_status()
        data = resp.json()
    return {
        cid: {cur.lower(): Decimal(str(price)) for cur, price in v.items()}
        for cid, v in data.items()
    }


def fetch_ohlc(
    coin_id: str,
    vs_currency: str,
    days: int,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """OHLC candles for one coin.

    CoinGecko returns 4h candles for days <= 30, daily for days > 30, hourly only
    on enterprise plan. days <= 1 → 30-min candles. We map the granularity into
    our `interval` column accordingly.

    Returns list of candle dicts ready for `store.insert_candles()`.
    """
    if days < 1:
        raise ValueError("days must be >= 1")
    interval = _interval_for_days(days)
    params = {"vs_currency": vs_currency, "days": days}
    with _client(transport=transport) as c:
        resp = c.get(f"/coins/{coin_id}/ohlc", params=params)
        resp.raise_for_status()
        raw = resp.json()

    symbol = f"{coin_id.upper()}-{vs_currency.upper()}"
    out = []
    for row in raw:
        # CoinGecko OHLC row: [timestamp_ms, open, high, low, close]
        out.append({
            "time": datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
            "symbol": symbol,
            "interval": interval,
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": 0.0,  # OHLC endpoint does not include volume
            "source": "coingecko",
            "asset_type": "crypto",
            "exchange": "coingecko",
        })
    return out


def search_coin(
    query: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """Look up coin ids by symbol/name. Returns list of {id, symbol, name}."""
    with _client(transport=transport) as c:
        resp = c.get("/search", params={"query": query})
        resp.raise_for_status()
        data = resp.json()
    return [
        {"id": coin["id"], "symbol": coin["symbol"], "name": coin["name"]}
        for coin in data.get("coins", [])
    ]


def _interval_for_days(days: int) -> str:
    if days <= 1:
        return "30m"
    if days <= 30:
        return "4h"
    return "1d"
