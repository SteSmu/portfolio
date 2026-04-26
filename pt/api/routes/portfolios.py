"""Portfolio CRUD routes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pt.db import portfolios as _portfolios

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


class PortfolioCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    base_currency: str = Field("EUR", min_length=3, max_length=3)
    user_id: str | None = None


class PortfolioOut(BaseModel):
    id: int
    user_id: str | None
    name: str
    base_currency: str
    created_at: datetime
    archived_at: datetime | None


@router.post("", response_model=PortfolioOut, status_code=201)
def create_portfolio(body: PortfolioCreate) -> dict:
    if _portfolios.get_by_name(body.name):
        raise HTTPException(status_code=409, detail=f"Portfolio '{body.name}' already exists.")
    try:
        pid = _portfolios.create(body.name, body.base_currency, body.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _portfolios.get(pid)


@router.get("", response_model=list[PortfolioOut])
def list_portfolios(include_archived: bool = False) -> list[dict]:
    return _portfolios.list_all(include_archived=include_archived)


@router.get("/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(portfolio_id: int) -> dict:
    row = _portfolios.get(portfolio_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")
    return row


@router.delete("/{portfolio_id}", status_code=204)
def archive_portfolio(portfolio_id: int) -> None:
    if not _portfolios.archive(portfolio_id):
        raise HTTPException(status_code=404, detail="Not found or already archived.")
