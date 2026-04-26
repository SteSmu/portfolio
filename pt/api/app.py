"""FastAPI application — portfolio tracker REST API.

Routes are progressively added under /api/. Mirrors claude-trader's structure.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pt import __version__
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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": __version__,
        "db": "ok" if is_available() else "unavailable",
    }
