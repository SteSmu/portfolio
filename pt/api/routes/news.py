"""News routes — list cached news + on-demand refresh from Finnhub/Marketaux."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from pt.data import finnhub as _finnhub
from pt.data import marketaux as _marketaux
from pt.db import news as _db_news

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/{symbol}/{asset_type}")
def list_news(
    symbol: str,
    asset_type: str,
    limit: int = Query(20, ge=1, le=200),
) -> dict:
    """Return cached news rows for one asset, newest first.

    The response also includes the average 14-day sentiment + the timestamp of
    the most recent fetch so the UI can decide whether a refresh is warranted.
    """
    rows = _db_news.list_for_symbol(symbol, asset_type, limit=limit)
    return {
        "symbol": symbol.upper(),
        "asset_type": asset_type,
        "items": rows,
        "avg_sentiment_14d": _db_news.avg_sentiment(symbol, asset_type, lookback_days=14),
        "last_fetched_at": _db_news.latest_fetched_at(symbol, asset_type),
    }


class SyncNewsBody(BaseModel):
    symbol: str
    asset_type: str
    sources: list[str] | None = None  # subset of ["finnhub", "marketaux"], default = all


@router.post("/sync")
def sync_news(body: SyncNewsBody) -> dict:
    """Refresh news for one asset from the configured providers.

    Errors from individual providers don't fail the whole call — they're
    surfaced per-source in the response so the UI can show partial results.
    """
    sources = body.sources or ["finnhub", "marketaux"]
    if any(s not in {"finnhub", "marketaux"} for s in sources):
        raise HTTPException(status_code=400,
                            detail="Allowed sources: finnhub, marketaux.")

    per_source: dict[str, dict] = {}
    total_written = 0

    if "finnhub" in sources and body.asset_type == "stock":
        # Finnhub free tier supports stocks reliably; crypto/forex only via /news?category=
        per_source["finnhub"] = _safe_sync(
            "finnhub",
            lambda: _finnhub.fetch_company_news(body.symbol),
        )
        total_written += per_source["finnhub"].get("written", 0)

    if "marketaux" in sources:
        per_source["marketaux"] = _safe_sync(
            "marketaux",
            lambda: _marketaux.fetch_news_for_symbols([body.symbol]),
        )
        total_written += per_source["marketaux"].get("written", 0)

    return {
        "symbol": body.symbol.upper(),
        "asset_type": body.asset_type,
        "rows_written": total_written,
        "sources": per_source,
    }


def _safe_sync(name: str, fetch_fn) -> dict:
    """Call a fetch function, persist the rows, and shape the per-source result.

    Catches missing-key and HTTP errors so one provider's outage doesn't
    block the others.
    """
    try:
        items = fetch_fn()
    except (_finnhub.FinnhubError, _marketaux.MarketauxError) as exc:
        return {"ok": False, "error": str(exc), "written": 0}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"HTTP error: {exc}", "written": 0}

    written = _db_news.upsert_many(items)
    return {"ok": True, "fetched": len(items), "written": written}
