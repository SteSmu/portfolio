"""Daily orchestrator — chains the four data-refresh routines into one
idempotent run. Used by the `pt-cron` sidecar (and `pt sync daily` CLI).

Order matters:
  1. FX rates (cheap, ECB free, no key — every conversion below depends on
     today's rates being current).
  2. Auto-prices for every active portfolio (per-symbol candle refresh via
     CoinGecko / Twelve Data → Yahoo). Without this, snapshots compute
     against yesterday's last close.
  3. Benchmark candles (SPY / URTH / IWDA / QQQ — independent of any
     portfolio, refreshes the whitelist for the equity-curve overlay).
  4. Snapshots for every active portfolio (today only, no backfill).

Every step is wrapped in try/except — one failing source doesn't break the
others. The return shape is amenable to JSON logging from the cron sidecar
so failures surface in `docker logs pt-cron`.
"""

from __future__ import annotations

import logging
from typing import Any

from pt.api.routes.sync import sync_portfolio_prices
from pt.data import frankfurter as _fx
from pt.data import store as _store
from pt.db.connection import get_conn
from pt.jobs import benchmarks as _bench
from pt.jobs import snapshots as _snap

logger = logging.getLogger(__name__)


def _list_active_portfolio_ids() -> list[int]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM portfolio.portfolios "
            "WHERE archived_at IS NULL ORDER BY id"
        )
        return [r[0] for r in cur.fetchall()]


def _step_fx() -> dict[str, Any]:
    """Latest ECB rates, EUR base, all supported quotes."""
    try:
        payload = _fx.fetch_latest(base="EUR", quotes=None)
        rows = _fx.to_market_meta_rows(payload)
        n = _store.insert_fx_rates(rows)
        return {"ok": True, "rows_written": n}
    except Exception as e:  # noqa: BLE001
        logger.exception("daily.fx failed")
        return {"ok": False, "error": str(e)}


def _step_auto_prices(portfolio_ids: list[int]) -> dict[str, Any]:
    """Per-portfolio bulk price refresh — reuses the API route function so
    we don't drift from the UI's behaviour. Each portfolio reports its own
    success / partial-fail breakdown."""
    out: list[dict[str, Any]] = []
    total_rows = 0
    for pid in portfolio_ids:
        try:
            r = sync_portfolio_prices(portfolio_id=pid, days=5)
            total_rows += r.get("rows_written", 0)
            failed = [x for x in r.get("results", []) if not x.get("ok")]
            out.append({
                "portfolio_id": pid,
                "ok": True,
                "rows_written": r.get("rows_written", 0),
                "holdings_count": r.get("holdings_count", 0),
                "failures": [
                    {"symbol": x["symbol"], "asset_type": x["asset_type"],
                     "error": x.get("error")}
                    for x in failed
                ],
            })
        except Exception as e:  # noqa: BLE001
            logger.exception("daily.auto_prices failed for portfolio %s", pid)
            out.append({"portfolio_id": pid, "ok": False, "error": str(e)})
    return {
        "ok": all(p["ok"] for p in out),
        "portfolios": len(out),
        "rows_written": total_rows,
        "results": out,
    }


def _step_benchmarks() -> dict[str, Any]:
    """Backfill the latest 5 days for every benchmark in the whitelist."""
    out: list[dict[str, Any]] = []
    total_rows = 0
    for spec in _bench.BENCHMARKS:
        try:
            res = _bench.ensure_history(
                symbol=spec.symbol, asset_type=spec.asset_type, days=5,
            )
            if res.get("ok"):
                total_rows += res.get("rows_written", 0)
            out.append({"symbol": spec.symbol, **res})
        except Exception as e:  # noqa: BLE001
            logger.exception("daily.benchmarks failed for %s", spec.symbol)
            out.append({"symbol": spec.symbol, "ok": False, "error": str(e)})
    return {
        "ok": all(b.get("ok") for b in out),
        "benchmarks": len(out),
        "rows_written": total_rows,
        "results": out,
    }


def _step_snapshots(portfolio_ids: list[int]) -> dict[str, Any]:
    """Today's snapshot for every active portfolio (idempotent UPSERT)."""
    out: list[dict[str, Any]] = []
    for pid in portfolio_ids:
        try:
            row = _snap.write_today(pid)
            out.append({
                "portfolio_id": pid, "ok": True,
                "snapshot_date": row.snapshot_date.isoformat(),
                "total_value": str(row.total_value) if row.total_value is not None else None,
                "total_value_base": str(row.total_value_base) if row.total_value_base is not None else None,
                "holdings_count": row.holdings_count,
            })
        except Exception as e:  # noqa: BLE001
            logger.exception("daily.snapshots failed for portfolio %s", pid)
            out.append({"portfolio_id": pid, "ok": False, "error": str(e)})
    return {
        "ok": all(p["ok"] for p in out),
        "portfolios": len(out),
        "results": out,
    }


def run() -> dict[str, Any]:
    """Run the full daily refresh. Returns a structured result that the
    caller (CLI / cron) can JSON-encode for logging."""
    portfolio_ids = _list_active_portfolio_ids()
    fx = _step_fx()
    auto = _step_auto_prices(portfolio_ids) if portfolio_ids else {"ok": True, "skipped": "no active portfolios"}
    bench = _step_benchmarks()
    snaps = _step_snapshots(portfolio_ids) if portfolio_ids else {"ok": True, "skipped": "no active portfolios"}
    overall_ok = all(s.get("ok", True) for s in (fx, auto, bench, snaps))
    return {
        "ok": overall_ok,
        "portfolios": len(portfolio_ids),
        "steps": {
            "fx": fx,
            "auto_prices": auto,
            "benchmarks": bench,
            "snapshots": snaps,
        },
    }
