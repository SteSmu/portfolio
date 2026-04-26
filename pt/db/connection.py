"""TimescaleDB connection helper — psycopg 3 context manager.

Reads PT_DB_* environment variables. Sets search_path to PT_DB_SCHEMA so
portfolio tables live in their own schema while sharing the candles + market_meta
tables in the public schema with claude-trader.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg


def _conn_params() -> dict[str, str | int]:
    return {
        "host": os.getenv("PT_DB_HOST", "localhost"),
        "port": int(os.getenv("PT_DB_PORT", "5434")),
        "dbname": os.getenv("PT_DB_NAME", "claude_trader"),
        "user": os.getenv("PT_DB_USER", "trader"),
        "password": os.getenv("PT_DB_PASSWORD", "trader_dev_2024"),
    }


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Yield a TimescaleDB connection with portfolio search_path set."""
    schema = os.getenv("PT_DB_SCHEMA", "portfolio")
    conn = psycopg.connect(**_conn_params())
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET search_path TO {schema}, public")
        yield conn
    finally:
        conn.close()


def is_available() -> bool:
    """Health check for /api/health."""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        return False
