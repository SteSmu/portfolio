"""Risk/return metrics — reference-case tests."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import pytest

from pt.performance.metrics import (
    cagr,
    calmar,
    daily_returns_from_snapshots,
    max_drawdown,
    sharpe,
    sortino,
    volatility,
)
from pt.performance.twr import Snapshot


def _close(a, b, tol=1e-6) -> bool:
    return abs(float(a) - float(b)) < tol


# -------------------- CAGR ------------------------------------------------------

def test_cagr_one_year_10pct_returns_10pct():
    assert _close(cagr(Decimal("100"), Decimal("110"), years=1.0), 0.10)


def test_cagr_doubling_in_2_years_is_root2_minus_1():
    assert _close(cagr(Decimal("100"), Decimal("200"), years=2.0), math.sqrt(2) - 1)


def test_cagr_negative_when_value_dropped():
    # 100 → 90 in 1 year → -10%
    assert _close(cagr(Decimal("100"), Decimal("90"), years=1.0), -0.10)


def test_cagr_returns_zero_for_zero_or_negative_inputs():
    assert cagr(Decimal("0"), Decimal("100"), years=1.0) == Decimal("0")
    assert cagr(Decimal("100"), Decimal("100"), years=0.0) == Decimal("0")
    assert cagr(Decimal("-100"), Decimal("100"), years=1.0) == Decimal("0")


# -------------------- Volatility -----------------------------------------------

def test_volatility_zero_for_constant_returns():
    """Same return every day → vol = 0."""
    assert volatility([0.001] * 100) == Decimal("0")


def test_volatility_known_case():
    """Returns alternate +1% / -1% → daily stddev = 0.01.
    Annualized at 252 trading days → 0.01 * sqrt(252) ≈ 0.1587."""
    returns = [0.01, -0.01] * 50  # 100 returns, sample stddev = 0.01...
    vol = float(volatility(returns, periods_per_year=252))
    expected = 0.01 * math.sqrt(252)
    # Sample stddev with this exact alternating series is 0.01005... (n-1 vs n)
    # Allow a small tolerance.
    assert abs(vol - expected) < 0.005


def test_volatility_empty_input_returns_zero():
    assert volatility([]) == Decimal("0")
    assert volatility([0.01]) == Decimal("0")  # need >= 2


# -------------------- Sharpe ----------------------------------------------------

def test_sharpe_zero_when_returns_constant():
    """Constant returns → no excess vol → Sharpe = 0 (denominator zero, returns 0)."""
    assert sharpe([0.001] * 100) == Decimal("0")


def test_sharpe_positive_when_returns_beat_risk_free():
    """Mean return > risk_free → Sharpe positive."""
    returns = [0.001, 0.002, 0.0015, 0.003, 0.0025] * 20  # all positive
    s = sharpe(returns, risk_free=0.0, periods_per_year=252)
    assert s > Decimal("0")


def test_sharpe_negative_when_returns_below_risk_free():
    """Need varying returns (non-zero stddev) for Sharpe to be defined."""
    returns = [0.0001, 0.0002, 0.00005, 0.0001] * 25  # mean ≈ 0.0001125
    s = sharpe(returns, risk_free=0.001, periods_per_year=252)
    assert s < Decimal("0")


# -------------------- Sortino ---------------------------------------------------

def test_sortino_zero_when_no_downside():
    """All returns positive → no downside vol → Sortino = 0 (we return 0 when dd=0)."""
    assert sortino([0.01] * 50) == Decimal("0")


def test_sortino_positive_with_mostly_upside():
    returns = [0.02, 0.01, 0.015, -0.005, 0.01, 0.012, -0.002] * 10
    assert sortino(returns) > Decimal("0")


# -------------------- Max Drawdown ----------------------------------------------

def test_max_drawdown_only_up_returns_zero():
    assert max_drawdown([0.01, 0.02, 0.005, 0.01]) == Decimal("0")


def test_max_drawdown_simple_dip():
    """+10%, -50%, +10%. Cumulative: 1.1, 0.55, 0.605.
    Peak after first = 1.1. Trough = 0.55. DD = 0.55/1.1 - 1 = -0.5."""
    assert _close(max_drawdown([0.10, -0.50, 0.10]), -0.5)


def test_max_drawdown_picks_deepest_trough():
    """Multiple drawdowns — pick the worst."""
    # +10% → 1.10  (peak)
    # -10% → 0.99  (dd from 1.10: -0.1)
    # +20% → 1.188 (new peak)
    # -50% → 0.594 (dd from 1.188: -0.5)
    assert _close(max_drawdown([0.10, -0.10, 0.20, -0.50]), -0.5)


def test_max_drawdown_empty_returns_zero():
    assert max_drawdown([]) == Decimal("0")


# -------------------- Calmar ----------------------------------------------------

def test_calmar_zero_when_no_drawdown():
    assert calmar([0.01, 0.02]) == Decimal("0")


def test_calmar_returns_positive_when_growing_with_drawdown():
    # 252 returns alternating between +0.5% and -0.3% — net positive with bumps
    rs = [0.005, -0.003] * 126
    c = calmar(rs)
    assert c > Decimal("0")


# -------------------- daily_returns_from_snapshots ------------------------------

def test_daily_returns_from_snapshots_matches_twr_logic():
    """Same input as TWR test: deposit doesn't show up as a 'return'.

    p1: 10000 → 20000 (no CF) → r_1 = 1.0
    p2: 20000 → 30000 (CF +10000) → r_2 = (30000 - 10000) / 20000 - 1 = 0.0
    """
    snaps = [
        Snapshot(date(2026, 1, 1), Decimal("10000")),
        Snapshot(date(2026, 6, 1), Decimal("20000")),
        Snapshot(date(2026, 6, 2), Decimal("30000"), cash_flow=Decimal("10000")),
    ]
    rs = daily_returns_from_snapshots(snaps)
    assert rs == [Decimal("1"), Decimal("0")]


def test_daily_returns_from_snapshots_skips_zero_starting_value():
    snaps = [
        Snapshot(date(2026, 1, 1), Decimal("0")),
        Snapshot(date(2026, 1, 2), Decimal("0")),
        Snapshot(date(2026, 1, 3), Decimal("100")),
    ]
    rs = daily_returns_from_snapshots(snaps)
    assert rs == []


def test_daily_returns_from_snapshots_empty_short_input():
    assert daily_returns_from_snapshots([]) == []
    assert daily_returns_from_snapshots([Snapshot(date(2026, 1, 1), Decimal("100"))]) == []
