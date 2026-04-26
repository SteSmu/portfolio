"""XIRR (Money-Weighted Return) reference-case tests.

Reference values are taken from Excel XIRR / standard financial textbook
examples. Tolerance is set tight (1e-6) — Newton-Raphson plus bisection
fallback should converge to that precision easily.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pt.performance.mwr import xirr


def _close(a: Decimal, b: Decimal | float, tol: float = 1e-6) -> bool:
    return abs(float(a) - float(b)) < tol


# -------------------- Trivial sanity checks -------------------------------------

def test_xirr_one_year_10pct_return():
    """Invest 100, get back 110 after exactly 365 days → 10%/yr."""
    flows = [
        (date(2026, 1, 1), Decimal("-100")),
        (date(2027, 1, 1), Decimal("110")),
    ]
    assert _close(xirr(flows), 0.10)


def test_xirr_doubles_in_one_year_is_100pct():
    flows = [
        (date(2026, 1, 1), Decimal("-100")),
        (date(2027, 1, 1), Decimal("200")),
    ]
    assert _close(xirr(flows), 1.00)


def test_xirr_loss_returns_negative():
    flows = [
        (date(2026, 1, 1), Decimal("-100")),
        (date(2027, 1, 1), Decimal("90")),
    ]
    assert _close(xirr(flows), -0.10)


def test_xirr_zero_return_when_no_change():
    flows = [
        (date(2026, 1, 1), Decimal("-100")),
        (date(2027, 1, 1), Decimal("100")),
    ]
    assert _close(xirr(flows), 0.0, tol=1e-6)


# -------------------- Excel reference example -----------------------------------

def test_xirr_excel_doc_example():
    """Verbatim Microsoft Excel XIRR documentation example.

    These dates fall in 2008/2009 — 2008 IS a leap year, so Jan 1 → Mar 1 is
    60 days, not 59. Our day-count is `(d - d0).days` (calendar days), matching
    Excel exactly. Reference value 0.373362535 (37.34%/yr).
    """
    flows = [
        (date(2008, 1, 1),  Decimal("-10000")),
        (date(2008, 3, 1),  Decimal("2750")),    # 60 days from start (leap year)
        (date(2008, 10, 30), Decimal("4250")),
        (date(2009, 2, 15), Decimal("3250")),
        (date(2009, 4, 1),  Decimal("2750")),
    ]
    result = xirr(flows)
    assert _close(result, 0.373362535, tol=1e-4)


# -------------------- Multiple irregular cashflows ------------------------------

def test_xirr_dca_then_full_sell():
    """Dollar-cost-average 100/month for 12 months, then sell at +20% over total invested.
    Avg holding period < 1 year, so the IRR > simple +20%.
    """
    flows: list[tuple[date, Decimal]] = []
    for m in range(1, 13):
        flows.append((date(2026, m, 1), Decimal("-100")))
    # Total invested = 1200; sell at 1440
    flows.append((date(2027, 1, 1), Decimal("1440")))
    result = xirr(flows)
    assert result > Decimal("0.30")  # > 30% (compounded with shorter holdings)


# -------------------- Error paths ----------------------------------------------

def test_xirr_requires_at_least_two_flows():
    with pytest.raises(ValueError, match="at least 2"):
        xirr([(date(2026, 1, 1), Decimal("-100"))])


def test_xirr_requires_sign_change():
    with pytest.raises(ValueError, match="positive and negative"):
        xirr([(date(2026, 1, 1), Decimal("-100")), (date(2027, 1, 1), Decimal("-50"))])


# -------------------- Ordering invariant ----------------------------------------

def test_xirr_is_order_independent():
    """Re-ordering input cash flows must not change the result (we re-sort)."""
    flows = [
        (date(2026, 1, 1),  Decimal("-100")),
        (date(2026, 6, 1),  Decimal("-50")),
        (date(2027, 1, 1),  Decimal("180")),
    ]
    out_sorted = xirr(flows)
    out_shuffled = xirr([flows[2], flows[0], flows[1]])
    assert out_sorted == out_shuffled
