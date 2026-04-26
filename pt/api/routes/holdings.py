"""Holdings (aggregated view from transactions, optionally enriched with prices)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from pt.db import holdings as _holdings

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


@router.get("/{symbol}/{asset_type}")
def get_holding(portfolio_id: int, symbol: str, asset_type: str) -> dict:
    row = _holdings.get_for_symbol(portfolio_id, symbol, asset_type)
    if not row:
        raise HTTPException(status_code=404,
                            detail=f"No holding {symbol} ({asset_type}) in portfolio {portfolio_id}.")
    # Single-symbol path also enriches with price for parity with list view.
    from pt.db import prices as _prices
    price, ts = _prices.latest_close(symbol, asset_type)
    row["current_price"] = price
    row["last_price_at"] = ts
    if price is not None and row["quantity"] is not None:
        market_value = row["quantity"] * price
        from decimal import Decimal
        cost = row.get("total_cost") or Decimal("0")
        row["market_value"] = market_value
        row["unrealized_pnl"] = market_value - cost
        row["unrealized_pnl_pct"] = float((market_value - cost) / cost) if cost > 0 else None
    else:
        row["market_value"] = None
        row["unrealized_pnl"] = None
        row["unrealized_pnl_pct"] = None
    return row
