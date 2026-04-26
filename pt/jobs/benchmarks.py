"""Benchmark catalog + history-fetch helper.

A benchmark is just an ETF/index proxy that we render as an overlay on the
equity curve so the user can eyeball relative outperformance vs the broad
market. The catalog is a static whitelist (curated, small) — anything more
exotic the user can pick up via the existing per-asset `pt sync stock`
flow and reference by symbol.

Symbol persistence follows the same rules as `pt.api.routes.sync`:
  - bare ticker is the DB key (`SPY`, `URTH`, `IWDA`)
  - non-US tickers carry an exchange suffix only on the Yahoo side and are
    rewritten to the bare ticker before `insert_candles`
  - Twelve Data primary → Yahoo fallback for stock/etf

Idempotent. Re-running `ensure_history()` only writes new candles because
`store.insert_candles` upserts on `(time, symbol, interval)`.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal

from pt.data import store as _store
from pt.data import twelve_data as _td
from pt.data import yahoo as _yh
from pt.db import prices as _prices


@dataclass(frozen=True)
class Benchmark:
    """One curated benchmark proxy.

    Attributes:
        symbol: bare ticker stored in `public.candles.symbol`.
        asset_type: matches the `candles.asset_type` enum (`etf` for ETFs).
        display_name: short human label shown in the picker.
        region: 'US' / 'EU' / 'GLOBAL' tag for grouping in the UI.
        provider: preferred fetcher key — 'twelve_data' or 'yahoo'.
        yahoo_symbol: Yahoo form (with exchange suffix) when provider != US.
            ``None`` means the bare ticker works on Yahoo too.
    """

    symbol: str
    asset_type: str
    display_name: str
    region: str
    provider: str
    yahoo_symbol: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # Keep the API surface compact — internal fetcher routing isn't
        # something a frontend cares about.
        d.pop("provider", None)
        d.pop("yahoo_symbol", None)
        return d


# Curated whitelist. Add new entries here; the route surfaces them via
# `GET /api/benchmarks`. Keep this small — for ad-hoc benchmarks the user
# can use `pt sync stock <symbol>` and reference it directly via the
# candles route.
BENCHMARKS: tuple[Benchmark, ...] = (
    Benchmark(
        symbol="SPY",
        asset_type="etf",
        display_name="S&P 500 (SPY)",
        region="US",
        provider="twelve_data",
    ),
    Benchmark(
        symbol="URTH",
        asset_type="etf",
        display_name="MSCI World (URTH)",
        region="US",
        provider="twelve_data",
    ),
    Benchmark(
        symbol="IWDA",
        asset_type="etf",
        display_name="MSCI World UCITS (IWDA.AS)",
        region="EU",
        provider="yahoo",
        yahoo_symbol="IWDA.AS",
    ),
    Benchmark(
        symbol="QQQ",
        asset_type="etf",
        display_name="Nasdaq-100 (QQQ)",
        region="US",
        provider="twelve_data",
    ),
)


def _by_symbol() -> dict[str, Benchmark]:
    return {b.symbol: b for b in BENCHMARKS}


def get(symbol: str) -> Benchmark | None:
    """Resolve a whitelisted benchmark by bare ticker (case-insensitive)."""
    return _by_symbol().get(symbol.upper())


def list_all() -> list[dict]:
    """Public API shape consumed by `GET /api/benchmarks`."""
    return [b.to_dict() for b in BENCHMARKS]


def ensure_history(
    symbol: str,
    asset_type: str | None = None,
    days: int = 365,
) -> dict:
    """Fetch + persist daily candles for one benchmark.

    Provider routing mirrors the auto-prices fallback chain: Twelve Data
    primary, Yahoo fallback. For benchmarks that only live on Yahoo
    (e.g. EU UCITS ETFs) we skip Twelve Data and go straight to Yahoo.

    Args:
        symbol: bare ticker (whitelisted or any user-known symbol).
        asset_type: optional override for the persisted ``asset_type``.
            Defaults to the catalog entry's value or ``'etf'``.
        days: trailing window to backfill. Yahoo + TD both honour this.

    Returns:
        ``{rows_written, last_close, last_price_at, source}``. ``last_close``
        is a ``Decimal`` (FastAPI serialises as JSON string at the API
        boundary). On error returns ``{ok: False, error: "..."}``.
    """
    if days < 1 or days > 5000:
        return {"ok": False, "error": "days must be 1..5000", "rows_written": 0}

    bm = get(symbol)
    sym = symbol.upper()
    asset_type_used = asset_type or (bm.asset_type if bm else "etf")

    candles, source, td_error = _fetch_with_fallback(
        symbol=sym, days=days, asset_type=asset_type_used,
        yahoo_symbol=bm.yahoo_symbol if bm else None,
        prefer_yahoo=(bm is not None and bm.provider == "yahoo"),
    )
    if candles is None:
        # All providers failed — graceful degradation, never crash.
        return {
            "ok": False,
            "error": td_error or "no benchmark data available",
            "rows_written": 0,
        }

    n = _store.insert_candles(candles)
    last_close, last_at = _prices.latest_close(sym, asset_type_used)
    return {
        "ok": True,
        "symbol": sym,
        "asset_type": asset_type_used,
        "source": source,
        "twelve_data_error": td_error,
        "rows_written": n,
        "last_close": last_close,
        "last_price_at": last_at,
    }


def _fetch_with_fallback(
    *,
    symbol: str,
    days: int,
    asset_type: str,
    yahoo_symbol: str | None,
    prefer_yahoo: bool,
) -> tuple[list[dict] | None, str, str | None]:
    """Run the primary→fallback chain, returning ``(candles, source, td_err)``.

    ``candles=None`` means both providers failed. The Twelve Data error
    message is preserved on the outcome so the caller / UI can explain
    why the fallback was needed even when Yahoo succeeds.
    """
    yh_target = yahoo_symbol or symbol

    if prefer_yahoo:
        try:
            candles = _yh.fetch_time_series(
                yh_target, days=days, asset_type=asset_type, db_symbol=symbol,
            )
            return candles, "yahoo", None
        except _yh.YahooFinanceError as exc:
            return None, "yahoo", f"yahoo: {exc}"

    try:
        candles = _td.fetch_time_series(
            symbol, interval="1day", outputsize=days, asset_type=asset_type,
        )
        return candles, "twelve_data", None
    except _td.TwelveDataError as td_err:
        # Twelve Data couldn't serve — try Yahoo.
        try:
            candles = _yh.fetch_time_series(
                yh_target, days=days, asset_type=asset_type, db_symbol=symbol,
            )
            return candles, "yahoo", str(td_err)
        except _yh.YahooFinanceError as yh_err:
            return None, "twelve_data", f"twelve_data: {td_err}; yahoo: {yh_err}"
