"""Sync routes — trigger market data refresh from CoinGecko / Twelve Data / Frankfurter.

These are long-running by HTTP standards (1-3s typical). The API runs them
synchronously for now. If we ever need true async/queued sync, swap the
implementation here without changing the route surface.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

import httpx

from pt.data import coingecko as _cg
from pt.data import frankfurter as _fx
from pt.data import store as _store
from pt.data import twelve_data as _td

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/fx")
def sync_fx(base: str = "EUR", quote: list[str] | None = None, days: int = 0) -> dict:
    """Sync ECB FX rates. days=0 → latest only, days>0 → backfill."""
    try:
        if days > 0:
            end = date.today()
            start = end - timedelta(days=days)
            payload = _fx.fetch_time_series(start, end, base=base, quotes=quote)
        else:
            payload = _fx.fetch_latest(base=base, quotes=quote)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Frankfurter request failed: {e}")
    rows = _fx.to_market_meta_rows(payload)
    n = _store.insert_fx_rates(rows)
    return {"source": "frankfurter", "base": base.upper(), "rows_written": n, "days": days}


@router.post("/crypto")
def sync_crypto(coin: str, vs_currency: str = "usd", days: int = 365) -> dict:
    """Sync OHLC candles for one CoinGecko coin id."""
    try:
        candles = _cg.fetch_ohlc(coin, vs_currency, days)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"CoinGecko request failed: {e}")
    n = _store.insert_candles(candles)
    return {
        "source": "coingecko",
        "symbol": candles[0]["symbol"] if candles else None,
        "interval": candles[0]["interval"] if candles else None,
        "rows_written": n, "days": days,
    }


@router.post("/stock")
def sync_stock(
    symbol: str,
    interval: str = "1day",
    outputsize: int = 365,
    asset_type: str = "stock",
    exchange: str | None = None,
) -> dict:
    """Sync OHLCV bars for one Twelve Data symbol."""
    try:
        candles = _td.fetch_time_series(
            symbol, interval=interval, outputsize=outputsize,
            asset_type=asset_type, exchange=exchange,
        )
    except _td.TwelveDataError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Twelve Data request failed: {e}")
    n = _store.insert_candles(candles)
    return {
        "source": "twelve_data",
        "symbol": symbol.upper(),
        "interval": candles[0]["interval"] if candles else interval,
        "rows_written": n,
    }
