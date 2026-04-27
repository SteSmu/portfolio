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


# -- FX-aware base-currency totals (Phase A4) -----------------------------------

@requires_db
def test_total_value_base_uses_historical_fx(isolated_portfolio):
    """USD candle + EURUSD=1.10 → EUR base = total_value / 1.10."""
    from pt.data import store

    pid = isolated_portfolio  # fixture creates EUR-base portfolios
    snap_date = date(2026, 2, 10)
    end_of_day = datetime(2026, 2, 10, 23, 59, 59, tzinfo=timezone.utc)
    fx_time = datetime(2026, 2, 10, tzinfo=timezone.utc)
    sym = "PHASEAUSD"

    # Seed FX rate EURUSD = 1.10 on snapshot day.
    store.insert_fx_rates([{
        "time": fx_time, "source": "frankfurter", "symbol": "EURUSD",
        "value": Decimal("1.10"), "metadata": {},
    }])
    # Seed a USD-denominated candle (close = 100 USD) on the same day.
    store.insert_candles([{
        "time": end_of_day, "symbol": sym, "interval": "1day",
        "open": Decimal("100"), "high": Decimal("100"), "low": Decimal("100"),
        "close": Decimal("100"), "volume": Decimal("0"),
        "asset_type": "stock", "source": "test",
    }])
    # transfer_in pins cost basis (qty x price + fees) — same semantics as buy.
    _tx.insert(
        portfolio_id=pid, symbol=sym, asset_type="stock", action="transfer_in",
        executed_at=datetime(2026, 2, 9, tzinfo=timezone.utc),
        quantity=Decimal("3"), price=Decimal("100"),
        trade_currency="USD", source="test",
    )

    try:
        row = _snap.compute_snapshot(pid, snap_date)
        assert row.total_value == Decimal("300")  # 3 x 100 USD, FX-naive
        assert row.total_value_base is not None
        # 300 USD / 1.10 EURUSD = 272.727272... EUR. Pin to 2 dp at display.
        from pt.performance.money import quantize_money
        assert quantize_money(row.total_value_base) == Decimal("272.73")
    finally:
        from pt.db.connection import get_conn
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.market_meta WHERE source='frankfurter' "
                "AND symbol='EURUSD' AND time=%s",
                (fx_time,),
            )
            cur.execute(
                "DELETE FROM public.candles WHERE symbol=%s AND interval='1day'",
                (sym,),
            )
            conn.commit()


@requires_db
def test_total_value_base_is_none_when_fx_missing(isolated_portfolio):
    """No FX rate at-or-before snapshot day → total_value_base is None."""
    from pt.data import store

    pid = isolated_portfolio  # EUR-base
    snap_date = date(2026, 3, 15)
    end_of_day = datetime(2026, 3, 15, 23, 59, 59, tzinfo=timezone.utc)
    sym = "PHASEAGBP"

    # Seed a GBP-denominated candle, but DO NOT seed any EURGBP/GBPEUR rate.
    store.insert_candles([{
        "time": end_of_day, "symbol": sym, "interval": "1day",
        "open": Decimal("50"), "high": Decimal("50"), "low": Decimal("50"),
        "close": Decimal("50"), "volume": Decimal("0"),
        "asset_type": "stock", "source": "test",
    }])
    _tx.insert(
        portfolio_id=pid, symbol=sym, asset_type="stock", action="transfer_in",
        executed_at=datetime(2026, 3, 14, tzinfo=timezone.utc),
        quantity=Decimal("2"), price=Decimal("50"),
        trade_currency="GBP", source="test",
    )

    try:
        # Defensive: clear any pre-existing EURGBP rate that other tests may
        # have left in this shared dev DB. Frankfurter rates are global.
        from pt.db.connection import get_conn
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.market_meta WHERE source='frankfurter' "
                "AND symbol IN ('EURGBP','GBPEUR') AND time::date <= %s",
                (snap_date,),
            )
            conn.commit()

        row = _snap.compute_snapshot(pid, snap_date)
        assert row.total_value == Decimal("100")  # 2 x 50 GBP, FX-naive
        assert row.total_value_base is None
    finally:
        from pt.db.connection import get_conn
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.candles WHERE symbol=%s AND interval='1day'",
                (sym,),
            )
            conn.commit()


# -- None-vs-zero semantics for unpriceable snapshots --------------------------

@requires_db
def test_total_value_is_none_when_no_holding_can_be_priced(isolated_portfolio):
    """Backfill on a date that pre-dates the candle history must NOT write
    total_value=0 — that would draw the equity curve to zero on every
    history-less day. None signals 'couldn't price' so the chart can skip.
    """
    pid = isolated_portfolio
    _tx.insert(
        portfolio_id=pid, symbol="UNPRICED", asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        quantity=Decimal("10"), price=Decimal("100"),
        trade_currency="USD", source="test",
    )
    # No candles seeded for UNPRICED — the lookup returns None.
    row = _snap.compute_snapshot(pid, date(2026, 1, 6))

    assert row.total_value is None, "open holdings + no prices ⇒ total_value None"
    assert row.unrealized_pnl is None
    assert row.total_value_base is None
    # Cost basis is always known from the tx log even with no prices.
    assert row.total_cost_basis == Decimal("1000")
    # holdings_count still reports the open position so the UI can say "1 holding, no price yet".
    assert row.holdings_count == 1


@requires_db
def test_empty_portfolio_snapshot_stays_zero_not_none(isolated_portfolio):
    """No transactions at all → total_value=0 (not None). Empty portfolios
    legitimately value at zero; only OPEN-but-unpriced holdings warrant None."""
    pid = isolated_portfolio
    row = _snap.compute_snapshot(pid, date(2026, 1, 6))
    assert row.total_value == Decimal("0")
    assert row.holdings_count == 0


@requires_db
def test_snapshot_persists_none_total_value(isolated_portfolio):
    """Round-trip: compute → write → read back must preserve None."""
    pid = isolated_portfolio
    _tx.insert(
        portfolio_id=pid, symbol="UNPRICED2", asset_type="stock", action="buy",
        executed_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        quantity=Decimal("1"), price=Decimal("10"),
        trade_currency="USD", source="test",
    )
    row = _snap.compute_snapshot(pid, date(2026, 1, 6))
    _snap.write_snapshot(row)
    rows = _snap.list_snapshots(pid)
    assert len(rows) == 1
    assert rows[0]["total_value"] is None
    assert rows[0]["unrealized_pnl"] is None
