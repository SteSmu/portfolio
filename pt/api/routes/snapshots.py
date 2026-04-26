"""Portfolio-snapshot routes — feed the equity-curve, drawdown, allocation-over-time UIs.

Snapshots are written by `pt sync snapshots` (CLI / cron). The frontend
reads via this route; computing on-the-fly per request would re-cost
~30 candle lookups per holding per day per render, which is too slow.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from pt.db import portfolios as _portfolios
from pt.jobs import snapshots as _snap

router = APIRouter(prefix="/portfolios/{portfolio_id}/snapshots", tags=["snapshots"])


@router.get("")
def list_snapshots(
    portfolio_id: int,
    start: date | None = Query(None, description="ISO date, inclusive lower bound."),
    end: date | None = Query(None, description="ISO date, inclusive upper bound."),
) -> dict:
    """Read snapshots for a portfolio, oldest-first.

    Empty `snapshots` list when no snapshots have been written yet — the UI
    surfaces a "run `pt sync snapshots --backfill 365`" hint in that case.
    """
    if not _portfolios.get(portfolio_id):
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")
    rows = _snap.list_snapshots(portfolio_id, start=start, end=end)
    return {
        "portfolio_id": portfolio_id,
        "from": start.isoformat() if start else None,
        "to": end.isoformat() if end else None,
        "snapshots": rows,
    }


@router.post("")
def write_snapshot(
    portfolio_id: int,
    backfill: int = Query(0, ge=0, le=3650, description="Days to backfill. 0 = today only."),
) -> dict:
    """On-demand snapshot generation. Cron / CLI is the normal path."""
    if not _portfolios.get(portfolio_id):
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")
    if backfill > 0:
        rows = _snap.backfill(portfolio_id, days=backfill)
    else:
        row = _snap.write_today(portfolio_id)
        rows = [row]
    latest = rows[-1]
    return {
        "portfolio_id": portfolio_id,
        "rows_written": len(rows),
        "from": rows[0].snapshot_date.isoformat(),
        "to": latest.snapshot_date.isoformat(),
        "latest": {
            "date": latest.snapshot_date.isoformat(),
            "total_value": latest.total_value,
            "total_cost_basis": latest.total_cost_basis,
            "unrealized_pnl": latest.unrealized_pnl,
            "realized_pnl": latest.realized_pnl,
            "holdings_count": latest.holdings_count,
        },
    }
