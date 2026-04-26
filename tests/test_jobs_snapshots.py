"""Snapshot-job tests — pin compute_snapshot + backfill + UPSERT idempotency."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from pt.db import transactions as _tx
from pt.jobs import snapshots as _snap
from tests.conftest import requires_db


@requires_db
def test_snapshot_writes_then_reads(isolated_portfolio):
    pid = isolated_portfolio
    _tx.insert(
        portfolio_id=pid, symbol="AAA", asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        quantity=Decimal("10"), price=Decimal("100"),
        trade_currency="USD", source="test",
    )
    row = _snap.compute_snapshot(pid, date(2026, 1, 6))
    _snap.write_snapshot(row)

    rows = _snap.list_snapshots(pid)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-01-06"
    # No candles in DB for AAA in this isolated test → market_value=0,
    # but cost_basis still reflects the buy.
    assert Decimal(rows[0]["total_cost_basis"]) == Decimal("1000")


@requires_db
def test_snapshot_upsert_is_idempotent(isolated_portfolio):
    pid = isolated_portfolio
    _tx.insert(
        portfolio_id=pid, symbol="BBB", asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        quantity=Decimal("1"), price=Decimal("50"),
        trade_currency="USD", source="test",
    )
    row1 = _snap.compute_snapshot(pid, date(2026, 1, 2))
    _snap.write_snapshot(row1)
    _snap.write_snapshot(row1)
    assert len(_snap.list_snapshots(pid)) == 1


@requires_db
def test_snapshot_filter_at_or_before(isolated_portfolio):
    """Future-dated tx must not influence a past snapshot."""
    pid = isolated_portfolio
    _tx.insert(
        portfolio_id=pid, symbol="CCC", asset_type="stock", action="buy",
        executed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        quantity=Decimal("5"), price=Decimal("20"),
        trade_currency="USD", source="test",
    )
    row = _snap.compute_snapshot(pid, date(2026, 1, 1))
    assert row.total_cost_basis == Decimal("0")
    assert row.holdings_count == 0


@requires_db
def test_backfill_creates_one_row_per_day(isolated_portfolio):
    pid = isolated_portfolio
    rows = _snap.backfill(pid, days=3, end_date=date(2026, 1, 5))
    assert len(rows) == 3
    assert rows[0].snapshot_date == date(2026, 1, 3)
    assert rows[-1].snapshot_date == date(2026, 1, 5)
    written = _snap.list_snapshots(pid)
    assert len(written) == 3


@requires_db
def test_backfill_dry_run_does_not_write(isolated_portfolio):
    pid = isolated_portfolio
    rows = _snap.backfill(pid, days=2, end_date=date(2026, 1, 5), dry_run=True)
    assert len(rows) == 2
    assert _snap.list_snapshots(pid) == []
