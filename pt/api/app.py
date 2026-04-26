"""FastAPI application — portfolio tracker REST API.

All routes are mounted under /api/. CORS is open for the dev frontend on
ports 5173/5174 plus the API itself.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pt import __version__
from pt.api.middleware import RequestLogMiddleware, install_logging_filter
from pt.api.routes.assets import router as assets_router
from pt.api.routes.holdings import router as holdings_router
from pt.api.routes.imports import router as imports_router
from pt.api.routes.news import router as news_router
from pt.api.routes.performance import router as performance_router
from pt.api.routes.portfolios import router as portfolios_router
from pt.api.routes.snapshots import router as snapshots_router
from pt.api.routes.sync import router as sync_router
from pt.api.routes.transactions import router as transactions_router
from pt.db.connection import get_conn, is_available
from pt.logging import configure as configure_logging

configure_logging()
install_logging_filter()

app = FastAPI(
    title="Portfolio Tracker API",
    description="Multi-asset, read-only portfolio analytics.",
    version=__version__,
)

app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://localhost:8430",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

API_PREFIX = "/api"
app.include_router(portfolios_router, prefix=API_PREFIX)
app.include_router(transactions_router, prefix=API_PREFIX)
app.include_router(holdings_router, prefix=API_PREFIX)
app.include_router(assets_router, prefix=API_PREFIX)
app.include_router(performance_router, prefix=API_PREFIX)
app.include_router(snapshots_router, prefix=API_PREFIX)
app.include_router(sync_router, prefix=API_PREFIX)
app.include_router(news_router, prefix=API_PREFIX)
app.include_router(imports_router, prefix=API_PREFIX)


@app.get("/api/health")
def health() -> dict:
    """Liveness + readiness probe.

    Returns:
      - status: "ok" if everything probes green, "degraded" if anything is off
      - version
      - db: ok|unavailable, with latency_ms
      - now: server time
      - counts: how full the DB is — useful as a smoke check after deploy
    """
    started = time.monotonic()
    db_ok = is_available()
    db_latency_ms = int((time.monotonic() - started) * 1000)
    now = datetime.now(timezone.utc).isoformat()

    counts: dict[str, int | None] = {
        "portfolios": None, "transactions": None,
        "candles": None, "news": None, "insights": None,
    }
    if db_ok:
        try:
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute("""
                    SELECT
                      (SELECT COUNT(*) FROM portfolio.portfolios WHERE archived_at IS NULL),
                      (SELECT COUNT(*) FROM portfolio.transactions WHERE deleted_at IS NULL),
                      (SELECT COUNT(*) FROM public.candles),
                      (SELECT COUNT(*) FROM portfolio.asset_news),
                      (SELECT COUNT(*) FROM portfolio.asset_insights)
                """)
                row = cur.fetchone()
                if row:
                    counts = {
                        "portfolios": row[0], "transactions": row[1],
                        "candles": row[2], "news": row[3], "insights": row[4],
                    }
        except Exception:
            db_ok = False

    status = "ok" if db_ok else "degraded"
    return {
        "status": status,
        "version": __version__,
        "now": now,
        "db": {"status": "ok" if db_ok else "unavailable", "latency_ms": db_latency_ms},
        "counts": counts,
    }
