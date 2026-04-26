"""Asset master CRUD routes + per-asset price history."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from pt.db import assets as _assets
from pt.db import prices as _prices

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


# Sub-path of the catch-all (3 segments) — registered before the 2-segment
# catch-all so the ordering rule is consistent with `/_search/{query}`.
@router.get("/{symbol}/{asset_type}/candles")
def get_asset_candles(
    symbol: str,
    asset_type: str,
    start: datetime | None = Query(None, description="ISO datetime, inclusive lower bound."),
    end: datetime | None = Query(None, description="ISO datetime, inclusive upper bound."),
    interval: str = Query("1day", description="Candle interval — '1day' is the only one we serve consistently."),
    limit: int = Query(2000, ge=1, le=5000),
) -> dict:
    """OHLCV history for one asset, oldest-first.

    Backed by `public.candles` (shared with claude-trader). Returns
    `{symbol, asset_type, interval, candles: [{time, open, high, low, close, volume}, ...]}`.
    Empty `candles` list if the asset isn't in the cache yet — call
    `POST /api/sync/stock` or `POST /api/sync/crypto` first to populate it.
    """
    rows = _prices.history(
        symbol=symbol, asset_type=asset_type,
        start=start, end=end, interval=interval, limit=limit,
    )
    return {
        "symbol": symbol.upper(),
        "asset_type": asset_type,
        "interval": interval,
        "candles": rows,
    }


@router.get("/{symbol}/{asset_type}")
def get_asset(symbol: str, asset_type: str) -> dict:
    row = _assets.get(symbol, asset_type)
    if not row:
        raise HTTPException(status_code=404, detail=f"Asset {symbol} ({asset_type}) not found.")
    return row
