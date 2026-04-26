"""Decimal-safe money math + FX conversion via stored ECB rates.

Hard rules enforced here:
  1. NEVER use float for money. Always Decimal.
  2. Rounding only at display boundary (`quantize_money`), never in storage
     or intermediate calculations.
  3. FX conversion uses stored historical rates from market_meta, never
     live rates for historical values.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, getcontext
from typing import Union

# 28-digit Decimal precision is the default — sufficient for portfolio math.
getcontext().prec = 28

NumberLike = Union[Decimal, str, int, float]

Q_MONEY = Decimal("0.01")          # 2 decimal places — display for fiat amounts
Q_QTY = Decimal("0.00000001")      # 8 decimal places — crypto-friendly quantity
Q_FX = Decimal("0.000001")         # 6 decimal places — FX rates


def D(value: NumberLike) -> Decimal:
    """Safe Decimal cast. `float` is converted via `str()` to avoid 0.1 → 0.1000000000…"""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


def quantize_money(amount: Decimal, q: Decimal = Q_MONEY) -> Decimal:
    """Round to display precision (default 2 decimal places, banker's-style ROUND_HALF_UP)."""
    return amount.quantize(q, rounding=ROUND_HALF_UP)


def quantize_qty(quantity: Decimal, q: Decimal = Q_QTY) -> Decimal:
    """Round quantity to 8 decimal places (crypto-friendly)."""
    return quantity.quantize(q, rounding=ROUND_HALF_UP)


def convert(
    amount: Decimal,
    from_ccy: str,
    to_ccy: str,
    on_date: date | None = None,
) -> Decimal:
    """Convert amount between currencies using ECB FX rates from market_meta.

    Lookup order:
      1. Direct rate FROM -> TO
      2. Inverse rate TO -> FROM (use 1/rate)
      3. Triangulation via EUR (ECB base): EUR -> FROM and EUR -> TO

    If `on_date` is given, the latest rate <= that date is used; otherwise the
    most recent rate available.

    Raises ValueError if no rate path can be found.
    """
    a = D(amount)
    if from_ccy.upper() == to_ccy.upper():
        return a

    direct = _lookup_fx_rate(f"{from_ccy.upper()}{to_ccy.upper()}", on_date)
    if direct is not None:
        return a * direct

    inverse = _lookup_fx_rate(f"{to_ccy.upper()}{from_ccy.upper()}", on_date)
    if inverse is not None:
        return a / inverse

    eur_to_from = _lookup_fx_rate(f"EUR{from_ccy.upper()}", on_date)
    eur_to_to = _lookup_fx_rate(f"EUR{to_ccy.upper()}", on_date)
    if eur_to_from is not None and eur_to_to is not None:
        return a / eur_to_from * eur_to_to

    raise ValueError(
        f"No FX rate available for {from_ccy}->{to_ccy}"
        + (f" on {on_date}" if on_date else "")
    )


def _lookup_fx_rate(symbol: str, on_date: date | None) -> Decimal | None:
    """Return the latest stored frankfurter rate for `symbol`, or None if missing."""
    from pt.db.connection import get_conn

    sql = (
        "SELECT value FROM public.market_meta "
        "WHERE source = 'frankfurter' AND symbol = %s"
    )
    params: list = [symbol]
    if on_date:
        sql += " AND time::date <= %s"
        params.append(on_date)
    sql += " ORDER BY time DESC LIMIT 1"

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return D(row[0]) if row else None
