"""FastAPI application — portfolio tracker REST API.

All routes are mounted under /api/. CORS is open for the dev frontend on
ports 5173/5174 plus the API itself.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pt import __version__
from pt.api.routes.assets import router as assets_router
from pt.api.routes.holdings import router as holdings_router
from pt.api.routes.performance import router as performance_router
from pt.api.routes.portfolios import router as portfolios_router
from pt.api.routes.sync import router as sync_router
from pt.api.routes.transactions import router as transactions_router
from pt.db.connection import is_available

app = FastAPI(
    title="Portfolio Tracker API",
    description="Multi-asset, read-only portfolio analytics.",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://localhost:8430",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api"
app.include_router(portfolios_router, prefix=API_PREFIX)
app.include_router(transactions_router, prefix=API_PREFIX)
app.include_router(holdings_router, prefix=API_PREFIX)
app.include_router(assets_router, prefix=API_PREFIX)
app.include_router(performance_router, prefix=API_PREFIX)
app.include_router(sync_router, prefix=API_PREFIX)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": __version__,
        "db": "ok" if is_available() else "unavailable",
    }
