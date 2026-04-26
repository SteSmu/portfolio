"""Performance routes (cost-basis, realized P&L, summary)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from pt.db import transactions as _tx
from pt.performance.cost_basis import compute_lots, realized_pnl_total

router = APIRouter(prefix="/portfolios/{portfolio_id}/performance", tags=["performance"])

_VALID_METHODS = {"fifo", "lifo", "average"}


def _load_tx(portfolio_id: int, symbol: str | None = None) -> list[dict]:
    return _tx.list_for_portfolio(portfolio_id=portfolio_id, symbol=symbol, limit=None)


def _validate_method(method: str) -> None:
    if method not in _VALID_METHODS:
        raise HTTPException(status_code=400,
                            detail=f"method must be one of {sorted(_VALID_METHODS)}, got {method!r}")


@router.get("/cost-basis")
def cost_basis(
    portfolio_id: int,
    method: str = Query("fifo"),
    symbol: str | None = None,
) -> dict:
    _validate_method(method)
    txs = _load_tx(portfolio_id, symbol=symbol)
    try:
        open_lots, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "method": method,
        "open_lots": [_lot_dict(l) for l in open_lots],
        "matches": [_match_dict(m) for m in matches],
        "realized_pnl": realized_pnl_total(matches),
    }


@router.get("/realized")
def realized(
    portfolio_id: int,
    method: str = Query("fifo"),
    year: int | None = None,
) -> dict:
    _validate_method(method)
    txs = _load_tx(portfolio_id)
    try:
        _, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if year is not None:
        matches = [m for m in matches if m.sell_executed_at.year == year]

    by_symbol: dict[str, Decimal] = {}
    by_holding: dict[str, Decimal] = {"short": Decimal("0"), "long": Decimal("0")}
    total = Decimal("0")
    for m in matches:
        by_symbol[m.symbol] = by_symbol.get(m.symbol, Decimal("0")) + m.realized_pnl
        bucket = "long" if m.holding_period_days >= 365 else "short"
        by_holding[bucket] += m.realized_pnl
        total += m.realized_pnl

    return {
        "year": year,
        "method": method,
        "total": total,
        "match_count": len(matches),
        "by_symbol": by_symbol,
        "by_holding_period": by_holding,
        "matches": [_match_dict(m) for m in matches],
    }


@router.get("/summary")
def summary(portfolio_id: int, method: str = Query("fifo")) -> dict:
    _validate_method(method)
    txs = _load_tx(portfolio_id)
    try:
        open_lots, matches = compute_lots(txs, method=method)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "portfolio_id": portfolio_id,
        "method": method,
        "tx_count": len(txs),
        "open_lot_count": len(open_lots),
        "open_cost_basis": sum((l.cost_basis for l in open_lots), Decimal("0")),
        "realized_pnl": realized_pnl_total(matches),
        "match_count": len(matches),
    }


def _lot_dict(lot) -> dict:
    return {
        "transaction_id": lot.transaction_id,
        "symbol": lot.symbol,
        "asset_type": lot.asset_type,
        "quantity": lot.quantity,
        "quantity_original": lot.quantity_original,
        "price": lot.price,
        "fees": lot.fees,
        "executed_at": lot.executed_at,
        "currency": lot.currency,
        "cost_basis": lot.cost_basis,
    }


def _match_dict(m) -> dict:
    return {
        "sell_transaction_id": m.sell_transaction_id,
        "lot_transaction_id": m.lot_transaction_id,
        "symbol": m.symbol,
        "asset_type": m.asset_type,
        "sold_quantity": m.sold_quantity,
        "cost_per_unit": m.cost_per_unit,
        "sell_price": m.sell_price,
        "sell_fees_allocated": m.sell_fees_allocated,
        "proceeds": m.proceeds,
        "cost": m.cost,
        "realized_pnl": m.realized_pnl,
        "holding_period_days": m.holding_period_days,
        "sell_executed_at": m.sell_executed_at,
        "buy_executed_at": m.buy_executed_at,
        "currency": m.currency,
    }
