"""Holdings (aggregated view from transactions, optionally enriched with prices)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from pt.db import holdings as _holdings
from pt.db import prices as _prices

router = APIRouter(prefix="/portfolios/{portfolio_id}/holdings", tags=["holdings"])


@router.get("")
def list_holdings(
    portfolio_id: int,
    include_zero: bool = False,
    with_prices: bool = Query(True,
                              description="Enrich with latest close, market value, unrealized P&L."),
) -> list[dict]:
    if with_prices:
        return _holdings.list_for_portfolio_with_prices(portfolio_id, include_zero=include_zero)
    return _holdings.list_for_portfolio(portfolio_id, include_zero=include_zero)


# Specific path BEFORE the catch-all `/{symbol}/{asset_type}` — same ordering
# rule as in `assets.py`: a 2-segment path can otherwise be eaten by the
# 2-segment catch-all (FastAPI/Starlette match registration-order, first wins).
@router.get("/sparklines")
def holding_sparklines(
    portfolio_id: int,
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Per-symbol close-price series for inline holdings-table sparklines.

    Returns `{symbol: [close_t-(days-1), ..., close_t0]}` keyed by `symbol`
    (not symbol+asset_type — collisions across asset_types in one portfolio
    are extremely rare and would mean the same symbol on two exchanges,
    which we can refine later by upgrading the dict-key to `symbol/at`).

    Skips holdings without candle history rather than 502'ing — some assets
    only have a single latest close, in which case the sparkline silently
    omits them and the UI renders a flat dash.
    """
    rows = _holdings.list_for_portfolio_with_prices(portfolio_id)
    if not rows:
        return {"days": days, "series": {}}

    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)

    out: dict[str, list] = {}
    for h in rows:
        if not h.get("quantity") or h["quantity"] <= 0:
            continue
        history = _prices.history(
            symbol=h["symbol"],
            asset_type=h["asset_type"],
            start=start, end=end,
            interval=list(_prices.DAILY_INTERVALS),
            limit=days + 5,
        )
        # Reduce to a flat list of closes (oldest → newest).
        closes = [
            {"time": r["time"].isoformat(), "close": r["close"]}
            for r in history
            if r["close"] is not None
        ]
        if closes:
            out[h["symbol"]] = closes
    return {"days": days, "series": out}


@router.get("/{symbol}/{asset_type}")
def get_holding(portfolio_id: int, symbol: str, asset_type: str) -> dict:
    """Single-holding aggregate. Parity with the list endpoint: enriched
    with the same `*_base` FX-converted fields so callers don't get a
    different shape depending on which path they hit."""
    rows = _holdings.list_for_portfolio_with_prices(portfolio_id, include_zero=True)
    sym_u = symbol.upper()
    for r in rows:
        if r["symbol"] == sym_u and r["asset_type"] == asset_type:
            return r
    raise HTTPException(
        status_code=404,
        detail=f"No holding {symbol} ({asset_type}) in portfolio {portfolio_id}.",
    )
