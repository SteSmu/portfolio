"""Transaction CRUD routes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from pt.db import transactions as _tx

router = APIRouter(prefix="/portfolios/{portfolio_id}/transactions", tags=["transactions"])


class TransactionIn(BaseModel):
    symbol: str = Field(..., min_length=1)
    asset_type: str
    action: str
    executed_at: datetime
    quantity: Decimal
    price: Decimal
    trade_currency: str = Field(..., min_length=3, max_length=3)
    fees: Decimal = Decimal("0")
    fees_currency: str | None = None
    fx_rate: Decimal | None = None
    note: str | None = None
    source: str = "manual"
    changed_by: str | None = None


class TransactionOut(BaseModel):
    id: int
    portfolio_id: int
    symbol: str
    asset_type: str
    action: str
    executed_at: datetime
    quantity: Decimal
    price: Decimal
    trade_currency: str
    fees: Decimal
    fees_currency: str | None
    fx_rate: Decimal | None
    note: str | None
    source: str
    source_doc_id: str | None
    imported_at: datetime
    deleted_at: datetime | None


@router.post("", response_model=TransactionOut, status_code=201)
def create_transaction(portfolio_id: int, body: TransactionIn) -> dict:
    try:
        tx_id = _tx.insert(
            portfolio_id=portfolio_id,
            symbol=body.symbol,
            asset_type=body.asset_type,
            action=body.action,
            executed_at=body.executed_at,
            quantity=body.quantity,
            price=body.price,
            trade_currency=body.trade_currency,
            fees=body.fees,
            fees_currency=body.fees_currency,
            fx_rate=body.fx_rate,
            note=body.note,
            source=body.source,
            changed_by=body.changed_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _tx.get(tx_id)


@router.get("", response_model=list[TransactionOut])
def list_transactions(
    portfolio_id: int,
    symbol: str | None = None,
    action: str | None = None,
    limit: int = Query(100, ge=1, le=10000),
    include_deleted: bool = False,
) -> list[dict]:
    return _tx.list_for_portfolio(
        portfolio_id=portfolio_id,
        symbol=symbol,
        action=action,
        limit=limit,
        include_deleted=include_deleted,
    )


@router.get("/{tx_id}", response_model=TransactionOut)
def get_transaction(portfolio_id: int, tx_id: int) -> dict:
    row = _tx.get(tx_id)
    if not row or row["portfolio_id"] != portfolio_id:
        raise HTTPException(status_code=404, detail="Transaction not found in this portfolio.")
    return row


@router.delete("/{tx_id}", status_code=204)
def delete_transaction(portfolio_id: int, tx_id: int, actor: str | None = None) -> None:
    row = _tx.get(tx_id)
    if not row or row["portfolio_id"] != portfolio_id:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    _tx.soft_delete(tx_id, changed_by=actor)


@router.get("/{tx_id}/audit")
def transaction_audit(portfolio_id: int, tx_id: int) -> list[dict]:
    row = _tx.get(tx_id)
    if not row or row["portfolio_id"] != portfolio_id:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return _tx.audit_history(tx_id)
