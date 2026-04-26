"""DB migration runner — applies schema_portfolio.sql against the configured DB.

Idempotent: every DDL uses IF NOT EXISTS / DO blocks, safe to re-run.
"""

from __future__ import annotations

from importlib.resources import files

from pt.db.connection import get_conn


def schema_path() -> str:
    """Path to the schema SQL file (works for installed + dev mode)."""
    return str(files("pt.db") / "schema_portfolio.sql")


def apply_schema() -> None:
    """Apply schema_portfolio.sql. Raises on failure."""
    sql = (files("pt.db") / "schema_portfolio.sql").read_text()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()


def list_tables() -> list[str]:
    """List all tables in the portfolio schema."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT tablename FROM pg_tables
               WHERE schemaname = 'portfolio'
               ORDER BY tablename"""
        )
        return [row[0] for row in cur.fetchall()]


def candles_has_asset_type() -> bool:
    """Verify the asset_type column exists on public.candles."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'candles'
                 AND column_name = 'asset_type'"""
        )
        return cur.fetchone() is not None
