"""TWR reference-case tests.

Hand-verified examples ensure the formula stays correct across refactors.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pt.performance.money import quantize_money
from pt.performance.twr import Snapshot, annualized_twr, twr


def _q(d: Decimal, places: str = "0.0001") -> Decimal:
    return d.quantize(Decimal(places))


def test_twr_with_no_cashflows_equals_simple_return():
    """No external CFs: TWR = V_end / V_start - 1."""
    snaps = [
        Snapshot(date(2026, 1, 1), Decimal("10000")),
        Snapshot(date(2026, 12, 31), Decimal("11000")),
    ]
    assert twr(snaps) == Decimal("0.1")  # +10%


def test_twr_zero_when_value_unchanged():
    snaps = [
        Snapshot(date(2026, 1, 1), Decimal("10000")),
        Snapshot(date(2026, 6, 1), Decimal("10000")),
    ]
    assert twr(snaps) == Decimal("0")


def test_twr_strips_deposit_effect():
    """User starts at 10k, market doubles in p1 (→20k), then deposits 10k (→30k),
    then market is flat in p2. TWR should be +100% (the deposit doesn't change
    the underlying performance).

    Snapshot semantics: value AFTER cash flow on that day.
    p1 return = (20000 - 0) / 10000 = 2.0 → +100%
    p2 return = (30000 - 10000) / 20000 = 1.0 → 0%
    Cumulative = 2.0 * 1.0 - 1 = +100%
    """
    snaps = [
        Snapshot(date(2026, 1, 1), Decimal("10000"), cash_flow=Decimal("0")),
        Snapshot(date(2026, 6, 1), Decimal("20000"), cash_flow=Decimal("0")),
        Snapshot(date(2026, 6, 2), Decimal("30000"), cash_flow=Decimal("10000")),
    ]
    assert twr(snaps) == Decimal("1")


def test_twr_strips_withdrawal_effect():
    """Start 10k. P1 grows 50% → 15k. Withdraw 5k same day → 10k.
    P2 grows 20% → 12k.
    p1 = (15000 - 0) / 10000 = 1.5
    p2 = (12000 - (-5000)) / 15000 = 17000/15000 = 1.1333...
    Wait — withdrawal at day-end of p1 means snapshot value AFTER withdrawal.
    Convention: cf is on the snapshot's day, value is AFTER cf.
      snap1: V=15000 BEFORE withdrawal would be needed; we model differently.

    Simplest unambiguous model: split snapshots so CFs land on a snapshot.
      snap0: 2026-01-01, V=10000, cf=0
      snap1: 2026-06-01, V=10000, cf=-5000        # AFTER withdrawal of 5k
      snap2: 2026-12-01, V=12000, cf=0

    p1 = (10000 - (-5000)) / 10000 = 1.5  (50% gain in p1)
    p2 = (12000 - 0)       / 10000 = 1.2  (20% gain in p2)
    TWR = 1.5 * 1.2 - 1 = 0.80
    """
    snaps = [
        Snapshot(date(2026, 1, 1),  Decimal("10000")),
        Snapshot(date(2026, 6, 1),  Decimal("10000"), cash_flow=Decimal("-5000")),
        Snapshot(date(2026, 12, 1), Decimal("12000")),
    ]
    assert twr(snaps) == Decimal("0.80")


def test_twr_with_only_one_snapshot_returns_zero():
    assert twr([Snapshot(date(2026, 1, 1), Decimal("10000"))]) == Decimal("0")


def test_twr_with_empty_input_returns_zero():
    assert twr([]) == Decimal("0")


def test_twr_raises_when_period_starts_with_negative_value():
    snaps = [
        Snapshot(date(2026, 1, 1), Decimal("-100")),
        Snapshot(date(2026, 6, 1), Decimal("100")),
    ]
    with pytest.raises(ValueError, match="undefined"):
        twr(snaps)


# -------------------- Annualized -----------------------------------------------

def test_annualized_twr_one_year_is_simple_return():
    snaps = [
        Snapshot(date(2026, 1, 1), Decimal("10000")),
        Snapshot(date(2027, 1, 1), Decimal("11000")),  # exactly 365 days
    ]
    annual = annualized_twr(snaps)
    assert _q(annual) == Decimal("0.1000")


def test_annualized_twr_doubling_in_2_years_yields_root2_minus_1():
    """100% over 2y → annualized = sqrt(2) - 1 ≈ 0.4142."""
    snaps = [
        Snapshot(date(2026, 1, 1), Decimal("10000")),
        Snapshot(date(2028, 1, 1), Decimal("20000")),  # 730 days
    ]
    annual = annualized_twr(snaps)
    # sqrt(2) - 1 = 0.41421356...
    assert _q(annual, "0.001") == Decimal("0.414")


def test_annualized_twr_short_period_extrapolates_up():
    """+1% in 1 day annualized → (1.01)^365 - 1 ≈ very large number."""
    snaps = [
        Snapshot(date(2026, 1, 1), Decimal("100")),
        Snapshot(date(2026, 1, 2), Decimal("101")),
    ]
    annual = annualized_twr(snaps)
    # (1.01)^365 - 1 ≈ 36.78
    assert annual > Decimal("36")
    assert annual < Decimal("38")
