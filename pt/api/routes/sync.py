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
from pt.data import yahoo as _yh
from pt.db import holdings as _holdings

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


# ----- Bulk sync over a portfolio's holdings ----------------------------------

# Convention: crypto symbols in our DB are typed `crypto` and we map them to
# CoinGecko ids by lowercasing the symbol portion. For "BTC" we ask CoinGecko
# for "bitcoin" — we maintain a tiny alias table for the most common ones so
# users don't have to enter CoinGecko ids manually.
_CRYPTO_ID_ALIASES: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "MATIC": "matic-network",
    "AVAX": "avalanche-2",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "LINK": "chainlink",
    "ATOM": "cosmos",
    "USDT": "tether",
    "USDC": "usd-coin",
}


def _coingecko_id(symbol: str) -> str:
    sym = symbol.upper().split("-")[0]  # 'BITCOIN-USD' from our writes → 'BITCOIN'
    if sym in _CRYPTO_ID_ALIASES:
        return _CRYPTO_ID_ALIASES[sym]
    return sym.lower()


# Bare-ticker → Yahoo Finance form. Used when Twelve Data can't serve a symbol
# (SIX Swiss listings need Pro plan, etc.). Yahoo accepts bare US tickers
# directly, so only non-US listings need an entry. Long-term this should move
# to `assets.metadata` so it's editable per asset, but a static map is fine
# while the universe is small.
_YAHOO_SYMBOL_MAP: dict[str, str] = {
    # SIX Swiss
    "NOVN": "NOVN.SW",
    "ROG":  "ROG.SW",
    "SDZ":  "SDZ.SW",
    "NESN": "NESN.SW",
    "UBSG": "UBSG.SW",
    "ZURN": "ZURN.SW",
    # Euronext Paris (Twelve Data Free covers these too, listed for fallback symmetry)
    "AIR":  "AIR.PA",
    "MC":   "MC.PA",
    "BNP":  "BNP.PA",
    # Xetra / Frankfurt
    "SAP":  "SAP.DE",
    "ALV":  "ALV.DE",
    "BMW":  "BMW.DE",
    # London
    "BP":   "BP.L",
    "HSBA": "HSBA.L",
    # Amsterdam
    "ASML": "ASML.AS",
}


def _yahoo_symbol(symbol: str) -> str:
    """Bare ticker → Yahoo form. US tickers pass through unchanged."""
    sym = symbol.upper()
    return _YAHOO_SYMBOL_MAP.get(sym, sym)


def _fetch_stock_with_fallback(
    symbol: str, *, days: int, asset_type: str,
) -> tuple[list[dict], str, str | None]:
    """Try Twelve Data first; on TwelveDataError, fall back to Yahoo Finance.

    Returns (candles, source, td_error_msg). The TD error is preserved on the
    outcome row even when Yahoo succeeds — useful for the UI to surface
    "got NOVN via Yahoo because TD said: needs Pro plan".
    """
    # If we already know TD can't serve this symbol (e.g. SIX listing), skip
    # the failed call to avoid burning a rate-limit slot.
    if symbol.upper() in _YAHOO_SYMBOL_MAP and _YAHOO_SYMBOL_MAP[symbol.upper()] != symbol.upper():
        candles = _yh.fetch_time_series(
            _yahoo_symbol(symbol), days=days, asset_type=asset_type,
            db_symbol=symbol,
        )
        return candles, "yahoo", None

    try:
        candles = _td.fetch_time_series(
            symbol, interval="1day", outputsize=days, asset_type=asset_type,
        )
        return candles, "twelve_data", None
    except _td.TwelveDataError as td_err:
        # TD couldn't serve — try Yahoo. Surface the TD error on the outcome
        # so users still see why we needed the fallback.
        candles = _yh.fetch_time_series(
            _yahoo_symbol(symbol), days=days, asset_type=asset_type,
            db_symbol=symbol,
        )
        return candles, "yahoo", str(td_err)


@router.post("/portfolio/{portfolio_id}/auto-prices")
def sync_portfolio_prices(
    portfolio_id: int,
    days: int = 30,
    vs_currency: str = "usd",
) -> dict:
    """Sync the most recent prices for every open position in a portfolio.

    Per asset_type:
      - crypto → CoinGecko (no key needed)
      - stock / etf → Twelve Data (key required) → Yahoo Finance fallback
      - fx / commodity / bond → skipped for now

    Twelve Data is the primary stock source (official, stable). When it can't
    serve a symbol — SIX Swiss listings need a Pro plan, rate-limit hits the
    8/min Free Tier ceiling, etc. — we transparently retry via Yahoo Finance,
    which is free + scrapes Yahoo's internal endpoints. The candle stays
    keyed off the bare ticker so the holdings join works regardless of source.

    Errors per holding don't fail the call — every result is reported. UI shows
    the breakdown so users see exactly which provider failed for which symbol.
    """
    rows = _holdings.list_for_portfolio(portfolio_id)
    results: list[dict] = []
    total_written = 0

    for h in rows:
        symbol, asset_type = h["symbol"], h["asset_type"]
        outcome: dict = {"symbol": symbol, "asset_type": asset_type, "ok": False}
        try:
            if asset_type == "crypto":
                coin_id = _coingecko_id(symbol)
                candles = _cg.fetch_ohlc(coin_id, vs_currency, days=days)
                outcome["source"] = "coingecko"
                outcome["coingecko_id"] = coin_id
            elif asset_type in {"stock", "etf"}:
                candles, src, td_err = _fetch_stock_with_fallback(
                    symbol, days=days, asset_type=asset_type,
                )
                outcome["source"] = src
                if td_err:
                    outcome["twelve_data_error"] = td_err
            else:
                outcome["error"] = f"asset_type {asset_type!r} not auto-priced yet"
                results.append(outcome)
                continue

            n = _store.insert_candles(candles)
            outcome["ok"] = True
            outcome["fetched"] = len(candles)
            outcome["written"] = n
            total_written += n
        except _td.TwelveDataError as e:
            outcome["error"] = str(e)
        except _yh.YahooFinanceError as e:
            outcome["error"] = f"yahoo: {e}"
        except httpx.HTTPError as e:
            outcome["error"] = f"HTTP error: {e}"
        except Exception as e:  # pragma: no cover — unexpected fetcher failures
            outcome["error"] = f"unexpected: {e}"
        results.append(outcome)

    return {
        "portfolio_id": portfolio_id,
        "holdings_count": len(rows),
        "rows_written": total_written,
        "results": results,
    }
