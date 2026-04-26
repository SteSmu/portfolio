"""Risk + return metrics on a return series.

These metrics work on simple returns (e.g. daily). Use Decimal at the input/
output boundary; internal stats math runs in float for speed and library
support. Output is always Decimal.

Conventions:
  - returns: list of period-over-period returns (e.g. 0.01 = +1% in one period)
  - periods_per_year: 252 for trading days, 365 for calendar days, 12 for
    monthly returns. Defaults to 252.
  - risk_free is per-period (NOT annualized). For an annual 4% risk-free at
    daily granularity, pass risk_free = 0.04 / 252.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from decimal import Decimal

from pt.performance.money import D
from pt.performance.twr import Snapshot

DEFAULT_PERIODS_PER_YEAR = 252


def daily_returns_from_snapshots(snapshots: list[Snapshot]) -> list[Decimal]:
    """Convert value snapshots into period-over-period simple returns.

    Strips cash-flow effect like TWR does:
        r_i = (V_i - CF_i) / V_{i-1} - 1
    """
    if len(snapshots) < 2:
        return []
    out: list[Decimal] = []
    for i in range(1, len(snapshots)):
        v_prev = D(snapshots[i - 1].value)
        v_curr = D(snapshots[i].value)
        cf = D(snapshots[i].cash_flow)
        if v_prev <= 0:
            continue
        out.append((v_curr - cf) / v_prev - Decimal("1"))
    return out


def cagr(start_value: Decimal, end_value: Decimal, years: float) -> Decimal:
    """Compound Annual Growth Rate.

    cagr = (end/start)^(1/years) - 1
    """
    sv = float(D(start_value))
    ev = float(D(end_value))
    if sv <= 0 or years <= 0:
        return Decimal("0")
    return D((ev / sv) ** (1.0 / years) - 1.0)


def volatility(returns: Iterable[Decimal | float],
               periods_per_year: int = DEFAULT_PERIODS_PER_YEAR) -> Decimal:
    """Annualized standard deviation of returns.

    annual_vol = stddev(returns) * sqrt(periods_per_year)
    Uses sample standard deviation (n-1).
    """
    rs = [float(r) for r in returns]
    if len(rs) < 2:
        return Decimal("0")
    mean = sum(rs) / len(rs)
    var = sum((r - mean) ** 2 for r in rs) / (len(rs) - 1)
    sd = math.sqrt(var)
    return D(sd * math.sqrt(periods_per_year))


def sharpe(returns: Iterable[Decimal | float],
           risk_free: float = 0.0,
           periods_per_year: int = DEFAULT_PERIODS_PER_YEAR) -> Decimal:
    """Annualized Sharpe ratio.

    sharpe = (mean_excess_return * periods_per_year) / annual_vol
    where excess_return = return - risk_free (per period).
    """
    rs = [float(r) for r in returns]
    if len(rs) < 2:
        return Decimal("0")
    excess = [r - risk_free for r in rs]
    mean_excess = sum(excess) / len(excess)
    sd_excess = _stddev(excess)
    if sd_excess == 0:
        return Decimal("0")
    return D((mean_excess * periods_per_year) / (sd_excess * math.sqrt(periods_per_year)))


def sortino(returns: Iterable[Decimal | float],
            risk_free: float = 0.0,
            periods_per_year: int = DEFAULT_PERIODS_PER_YEAR) -> Decimal:
    """Annualized Sortino ratio — like Sharpe but only downside deviation.

    Treats upside volatility as a feature, not a risk.
    """
    rs = [float(r) for r in returns]
    if len(rs) < 2:
        return Decimal("0")
    excess = [r - risk_free for r in rs]
    mean_excess = sum(excess) / len(excess)
    downside = [min(0.0, e) for e in excess]
    # Use n (not n-1) for downside deviation — convention varies, n is more common
    dd_var = sum(d * d for d in downside) / len(downside)
    dd = math.sqrt(dd_var)
    if dd == 0:
        return Decimal("0")
    return D((mean_excess * periods_per_year) / (dd * math.sqrt(periods_per_year)))


def max_drawdown(returns: Iterable[Decimal | float]) -> Decimal:
    """Maximum drawdown: deepest peak-to-trough decline of cumulative returns.

    Returns a NEGATIVE decimal — e.g. Decimal('-0.25') = max -25% drawdown.
    Returns 0 if returns is empty or only goes up.
    """
    rs = [float(r) for r in returns]
    if not rs:
        return Decimal("0")
    cumulative = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in rs:
        cumulative *= (1.0 + r)
        if cumulative > peak:
            peak = cumulative
        dd = cumulative / peak - 1.0
        if dd < max_dd:
            max_dd = dd
    return D(max_dd)


def calmar(returns: Iterable[Decimal | float],
           periods_per_year: int = DEFAULT_PERIODS_PER_YEAR) -> Decimal:
    """Calmar ratio: annualized return divided by absolute max drawdown."""
    rs = [float(r) for r in returns]
    if not rs:
        return Decimal("0")
    cumulative = 1.0
    for r in rs:
        cumulative *= (1.0 + r)
    annualized = cumulative ** (periods_per_year / len(rs)) - 1.0
    mdd = float(max_drawdown(rs))
    if mdd == 0:
        return Decimal("0")
    return D(annualized / abs(mdd))


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)
