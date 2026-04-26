"""Benchmark routes — whitelist + on-demand history sync.

Surface:
  - ``GET /api/benchmarks`` — the curated catalog (SPY / URTH / IWDA / QQQ).
  - ``POST /api/benchmarks/{symbol}/sync?days=N`` — refresh candles for one
    benchmark via the Twelve Data → Yahoo fallback chain. Mirrors the news
    route's graceful-degradation pattern: missing ``TWELVE_DATA_API_KEY``
    plus a Yahoo failure returns a 502 with a clear detail rather than
    crashing.

The actual whitelist lives in :mod:`pt.jobs.benchmarks` so the CLI (and
future automation) can read the same source of truth.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query

from pt.jobs import benchmarks as _bm

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("")
def list_benchmarks() -> list[dict]:
    """Return the curated benchmark catalog.

    Each entry: ``{symbol, asset_type, display_name, region}``. The frontend
    feeds this into a ``<select>`` and persists the user's choice in
    localStorage under ``pt:benchmark``.
    """
    return _bm.list_all()


@router.post("/{symbol}/sync")
def sync_benchmark(
    symbol: str,
    days: int = Query(365, ge=1, le=5000,
                      description="Trailing window of candles to backfill."),
) -> dict:
    """Refresh candles for one benchmark.

    Returns ``{ok, rows_written, last_close, last_price_at, source}``. On
    upstream provider failure (no API key + no Yahoo fallback) responds 502
    with a human-readable detail, mirroring the rest of the API.
    """
    try:
        result = _bm.ensure_history(symbol, days=days)
    except httpx.HTTPError as exc:
        # Network-level failure outside the fetcher's typed errors — keep
        # the same 502 contract as `/api/sync/stock`.
        raise HTTPException(status_code=502,
                            detail=f"Benchmark fetch failed: {exc}")

    if not result.get("ok"):
        raise HTTPException(status_code=502,
                            detail=result.get("error", "benchmark sync failed"))

    return result
