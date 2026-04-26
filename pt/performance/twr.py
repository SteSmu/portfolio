"""Time-Weighted Return (TWR).

TWR removes the impact of cash flow timing. It chains sub-period returns
geometrically — the result is the return a buy-and-hold investor would have
seen, independent of when deposits/withdrawals happened.

Used for: comparing portfolio performance against benchmarks and funds.
NOT used for: "what was MY actual return" — that's MWR (see mwr.py).

Convention used here:
  - Caller supplies a list of `Snapshot(date, market_value, external_cash_flow)`
  - market_value: total portfolio value at end-of-day
  - external_cash_flow: deposit (+) or withdrawal (-) on that day; defaults to 0
    Buy/sell of existing positions are NOT cash flows (they swap cash↔shares
    inside the portfolio). Only money entering/leaving the portfolio counts.

Formula per sub-period i (between snapshot i-1 and i):
    r_i = (V_i - CF_i) / V_{i-1} - 1

Total TWR = ∏(1 + r_i) - 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from pt.performance.money import D


@dataclass
class Snapshot:
    """Portfolio value snapshot for TWR calculation."""
    when: date | datetime
    value: Decimal
    cash_flow: Decimal = Decimal("0")  # external in (+) / out (-)


def twr(snapshots: list[Snapshot]) -> Decimal:
    """Geometric chaining of sub-period returns.

    Returns the cumulative return (e.g. Decimal('0.15') = +15%).
    Returns Decimal('0') if fewer than 2 snapshots are provided.

    Raises ValueError if any snapshot prior to a non-zero CF has value <= 0,
    since the return for that period is undefined.
    """
    if len(snapshots) < 2:
        return Decimal("0")

    cumulative = Decimal("1")
    for i in range(1, len(snapshots)):
        v_prev = D(snapshots[i - 1].value)
        v_curr = D(snapshots[i].value)
        cf = D(snapshots[i].cash_flow)

        if v_prev <= 0:
            if cf == 0 and v_curr == 0:
                continue  # all zero, no contribution
            raise ValueError(
                f"Snapshot {i - 1} has value {v_prev} <= 0; "
                f"sub-period return undefined."
            )

        period_factor = (v_curr - cf) / v_prev
        cumulative *= period_factor

    return cumulative - Decimal("1")


def annualized_twr(snapshots: list[Snapshot], day_count: int = 365) -> Decimal:
    """Annualized TWR (CAGR-equivalent for the snapshot range).

    (1 + total_return)^(day_count / total_days) - 1

    Useful for normalising returns over arbitrary periods to a yearly figure.
    """
    if len(snapshots) < 2:
        return Decimal("0")

    total = twr(snapshots)
    start = snapshots[0].when
    end = snapshots[-1].when
    days = (end - start).days if hasattr(end - start, "days") else (end - start).total_seconds() / 86400
    if days <= 0:
        return Decimal("0")

    # Decimal doesn't do fractional powers natively — use float math, return Decimal
    factor = float(Decimal("1") + total)
    annualized = factor ** (day_count / days) - 1.0
    return D(annualized)
