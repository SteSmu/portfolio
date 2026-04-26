"""Tests for Decimal money math + FX conversion via ECB rates."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from pt.performance.money import (
    D,
    Q_FX,
    Q_MONEY,
    Q_QTY,
    convert,
    quantize_money,
    quantize_qty,
)
from tests.conftest import requires_db


def test_D_accepts_string_int_decimal_float():
    assert D("0.10") == Decimal("0.10")
    assert D(10) == Decimal("10")
    assert D(Decimal("1.5")) == Decimal("1.5")
    assert D(0.1) == Decimal("0.1")  # via str() — no float artefacts


def test_quantize_money_rounds_to_cent_half_up():
    assert quantize_money(Decimal("1.005")) == Decimal("1.01")
    assert quantize_money(Decimal("1.004")) == Decimal("1.00")


def test_quantize_qty_rounds_to_8_decimals():
    assert quantize_qty(Decimal("0.123456789")) == Decimal("0.12345679")


def test_q_constants_documented_precision():
    assert Q_MONEY == Decimal("0.01")
    assert Q_QTY == Decimal("0.00000001")
    assert Q_FX == Decimal("0.000001")


def test_convert_same_currency_returns_input_unchanged():
    assert convert(Decimal("100"), "EUR", "EUR") == Decimal("100")


# -- FX conversion via stored ECB rates: integration tests ----------------------

@pytest.fixture
def fx_rates_loaded():
    """Insert temporary EUR/USD and EUR/CHF rates for conversion tests."""
    from pt.data import store

    on = datetime(2026, 4, 25, tzinfo=timezone.utc)
    sym_usd = f"_PTFX{uuid.uuid4().hex[:6].upper()}"
    sym_chf = f"_PTFX{uuid.uuid4().hex[:6].upper()}"
    # Use real-looking 'EURUSD'/'EURCHF' symbols for rate lookup tests
    rows = [
        {"time": on, "source": "frankfurter", "symbol": "EURUSD",
         "value": Decimal("1.10"), "metadata": {}},
        {"time": on, "source": "frankfurter", "symbol": "EURCHF",
         "value": Decimal("0.95"), "metadata": {}},
    ]
    store.insert_fx_rates(rows)
    yield

    from pt.db.connection import get_conn
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM public.market_meta WHERE source='frankfurter' "
                    "AND symbol IN ('EURUSD','EURCHF') AND time=%s", (on,))
        conn.commit()


@requires_db
def test_convert_uses_direct_rate_eur_to_usd(fx_rates_loaded):
    # EURUSD = 1.10 → 100 EUR → 110 USD
    assert convert(Decimal("100"), "EUR", "USD", on_date=date(2026, 4, 25)) == Decimal("110.00")


@requires_db
def test_convert_uses_inverse_rate_usd_to_eur(fx_rates_loaded):
    # No USDEUR rate stored → inverse of EURUSD: 110 / 1.10 = 100
    out = convert(Decimal("110"), "USD", "EUR", on_date=date(2026, 4, 25))
    assert quantize_money(out) == Decimal("100.00")


@requires_db
def test_convert_triangulates_via_eur(fx_rates_loaded):
    # No USDCHF rate, no CHFUSD: triangulate via EUR.
    # 110 USD / EURUSD(1.10) = 100 EUR. 100 EUR * EURCHF(0.95) = 95 CHF.
    out = convert(Decimal("110"), "USD", "CHF", on_date=date(2026, 4, 25))
    assert quantize_money(out) == Decimal("95.00")


@requires_db
def test_convert_raises_when_no_rate_path():
    # Use unlikely currency code that won't have a rate
    with pytest.raises(ValueError, match="No FX rate"):
        convert(Decimal("1"), "ZZZ", "YYY")
