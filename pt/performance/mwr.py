"""Money-Weighted Return / XIRR — internal rate of return on irregular cash flows.

Computes the discount rate r that makes the NPV of a series of dated cash flows
zero. This is what Excel's XIRR returns, and what tells you "what return did I
actually earn given when I put money in and took it out".

Convention:
  Cash flows are signed from YOUR perspective:
    deposits / buys at start = NEGATIVE (money out of your pocket)
    withdrawals / sells / final portfolio value = POSITIVE (money back to you)

Algorithm:
  Newton-Raphson with bisection fallback. Newton converges fast in practice but
  diverges on weird inputs; bisection is the safety net to guarantee convergence
  whenever a sign change exists in [-0.999, large_upper].
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pt.performance.money import D

DAY_COUNT = 365.0
DEFAULT_GUESS = 0.10
MAX_NEWTON_ITER = 100
NEWTON_TOLERANCE = 1e-9
BISECTION_LO = -0.999     # rate must be > -100%
BISECTION_HI = 1e6        # 100,000,000% upper bound — should never be reached
BISECTION_TOL = 1e-12


def _to_date(d: date | datetime) -> date:
    return d.date() if isinstance(d, datetime) else d


def _npv(rate: float, cash_flows: list[tuple[date, float]]) -> float:
    if rate <= -1.0:
        return float("inf")
    t0 = cash_flows[0][0]
    return sum(
        cf * (1.0 + rate) ** (-(((d - t0).days) / DAY_COUNT))
        for d, cf in cash_flows
    )


def _dnpv(rate: float, cash_flows: list[tuple[date, float]]) -> float:
    if rate <= -1.0:
        return float("nan")
    t0 = cash_flows[0][0]
    return sum(
        cf * (-((d - t0).days) / DAY_COUNT)
            * (1.0 + rate) ** (-(((d - t0).days) / DAY_COUNT) - 1)
        for d, cf in cash_flows
    )


def xirr(
    cash_flows: list[tuple[date | datetime, Decimal | float]],
    guess: float = DEFAULT_GUESS,
) -> Decimal:
    """Money-Weighted Return (Excel-style XIRR).

    Returns the annualised IRR as a Decimal (e.g. Decimal('0.10') == +10%/yr).

    Requirements on `cash_flows`:
      - At least 2 entries.
      - At least one positive AND one negative — otherwise no IRR exists.
      - Sorted ascending by date (we re-sort defensively).

    Raises:
      ValueError if the requirements are not met or no sign change exists.
      RuntimeError if neither Newton nor bisection converges.
    """
    if len(cash_flows) < 2:
        raise ValueError("xirr needs at least 2 cash flows.")

    flows = sorted(
        ((_to_date(d), float(cf if isinstance(cf, Decimal) else cf)) for d, cf in cash_flows),
        key=lambda x: x[0],
    )
    if not (any(cf > 0 for _, cf in flows) and any(cf < 0 for _, cf in flows)):
        raise ValueError("xirr needs both positive and negative cash flows.")

    # ---------- Newton-Raphson ----------
    rate = guess
    for _ in range(MAX_NEWTON_ITER):
        npv = _npv(rate, flows)
        if abs(npv) < NEWTON_TOLERANCE:
            return D(rate)
        d = _dnpv(rate, flows)
        if d == 0 or d != d:  # NaN guard
            break
        new_rate = rate - npv / d
        if new_rate <= -1.0:  # would step into invalid region — fall back
            break
        if abs(new_rate - rate) < NEWTON_TOLERANCE:
            return D(new_rate)
        rate = new_rate

    # ---------- Bisection fallback ----------
    lo, hi = BISECTION_LO, BISECTION_HI
    npv_lo, npv_hi = _npv(lo, flows), _npv(hi, flows)
    if npv_lo * npv_hi > 0:
        # No sign change in the search interval → IRR not bracketable
        raise RuntimeError(
            "xirr did not converge: NPV does not change sign across "
            f"[{lo}, {hi}] (NPV_lo={npv_lo:.6g}, NPV_hi={npv_hi:.6g})."
        )
    for _ in range(200):
        mid = (lo + hi) / 2.0
        npv_mid = _npv(mid, flows)
        if abs(npv_mid) < BISECTION_TOL or (hi - lo) < BISECTION_TOL:
            return D(mid)
        if npv_lo * npv_mid < 0:
            hi, npv_hi = mid, npv_mid
        else:
            lo, npv_lo = mid, npv_mid
    return D((lo + hi) / 2.0)
