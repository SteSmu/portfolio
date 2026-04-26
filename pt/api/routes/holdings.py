"""Holdings (aggregated view from transactions)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from pt.db import holdings as _holdings

router = APIRouter(prefix="/portfolios/{portfolio_id}/holdings", tags=["holdings"])


@router.get("")
def list_holdings(portfolio_id: int, include_zero: bool = False) -> list[dict]:
    return _holdings.list_for_portfolio(portfolio_id, include_zero=include_zero)


@router.get("/{symbol}/{asset_type}")
def get_holding(portfolio_id: int, symbol: str, asset_type: str) -> dict:
    row = _holdings.get_for_symbol(portfolio_id, symbol, asset_type)
    if not row:
        raise HTTPException(status_code=404,
                            detail=f"No holding {symbol} ({asset_type}) in portfolio {portfolio_id}.")
    return row
