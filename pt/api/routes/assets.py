"""Asset master CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pt.db import assets as _assets

router = APIRouter(prefix="/assets", tags=["assets"])


class AssetUpsert(BaseModel):
    symbol: str
    asset_type: str
    name: str
    currency: str
    exchange: str | None = None
    isin: str | None = None
    wkn: str | None = None
    sector: str | None = None
    region: str | None = None
    metadata: dict | None = None


@router.post("", status_code=201)
def upsert_asset(body: AssetUpsert) -> dict:
    _assets.upsert(**body.model_dump())
    return _assets.get(body.symbol, body.asset_type)


@router.get("")
def list_assets(asset_type: str | None = None, search: str | None = None) -> list[dict]:
    return _assets.list_all(asset_type=asset_type, search=search)


# Specific path declared BEFORE the catch-all `/{symbol}/{asset_type}`,
# otherwise `/_search/foo` is interpreted as symbol=`_search`, asset_type=`foo`.
@router.get("/_search/{query}")
def search_assets(query: str, limit: int = 10) -> list[dict]:
    return _assets.find_similar(query, limit=limit)


@router.get("/{symbol}/{asset_type}")
def get_asset(symbol: str, asset_type: str) -> dict:
    row = _assets.get(symbol, asset_type)
    if not row:
        raise HTTPException(status_code=404, detail=f"Asset {symbol} ({asset_type}) not found.")
    return row
