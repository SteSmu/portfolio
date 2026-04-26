"""Cost-basis methods: FIFO, LIFO, Average. Produces tax-lots + realized P&L per match.

The transaction log is the source of truth — lots are computed, never stored
primarily. This means correcting a wrong transaction recomputes lots correctly,
no manual lot-resync needed.

Conventions:
  - Buy fees are folded into the per-unit cost basis: `unit_cost = price + (fees/qty)`.
  - Sell fees are allocated pro-rata across matched lots and reduce proceeds.
  - "transfer_in" behaves like buy (cost = price field, e.g. fair-market-value at transfer).
  - "transfer_out" behaves like sell at the supplied price.
  - dividend/fee/deposit/withdrawal/split do NOT touch lots here — splits are
    handled by `audit/corp_actions.py` which rewrites the underlying transactions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pt.performance.money import D

CostBasisMethod = Literal["fifo", "lifo", "average"]
_VALID_METHODS = {"fifo", "lifo", "average"}


@dataclass
class Lot:
    """An open tax lot — remaining shares from a buy."""
    transaction_id: int
    symbol: str
    asset_type: str
    quantity: Decimal             # remaining shares
    quantity_original: Decimal    # original buy quantity
    price: Decimal                # per-unit cost (incl. allocated buy fees)
    fees: Decimal                 # original total fees on the buy
    executed_at: datetime
    currency: str = "USD"

    @property
    def cost_basis(self) -> Decimal:
        """Cost basis of remaining shares (qty * unit_cost)."""
        return self.quantity * self.price

    @property
    def cost_basis_original(self) -> Decimal:
        """Cost basis at acquisition (original_qty * unit_cost)."""
        return self.quantity_original * self.price


@dataclass
class LotMatch:
    """A sell matched against a specific buy lot — basis for realized P&L."""
    sell_transaction_id: int
    lot_transaction_id: int
    symbol: str
    asset_type: str
    sold_quantity: Decimal
    cost_per_unit: Decimal
    sell_price: Decimal
    sell_fees_allocated: Decimal
    proceeds: Decimal             # sold_qty * sell_price - allocated_fees
    cost: Decimal                 # sold_qty * cost_per_unit
    realized_pnl: Decimal         # proceeds - cost
    holding_period_days: int
    sell_executed_at: datetime
    buy_executed_at: datetime
    currency: str = "USD"


def compute_lots(
    transactions: list[dict],
    method: CostBasisMethod = "fifo",
) -> tuple[list[Lot], list[LotMatch]]:
    """Process transactions chronologically, produce open lots + matched sells.

    Args:
        transactions: dicts with id, symbol, asset_type, action, executed_at,
            quantity (Decimal/numeric), price, trade_currency, fees.
            Re-sorted defensively by (executed_at, id).
        method: 'fifo' | 'lifo' | 'average'.

    Returns:
        (open_lots, matched_lots) — open_lots have quantity > 0.

    Raises:
        ValueError on invalid method or sell-exceeds-holdings.
    """
    if method not in _VALID_METHODS:
        raise ValueError(f"Unknown method {method!r}. Allowed: {sorted(_VALID_METHODS)}")

    pools: dict[tuple[str, str], list[Lot]] = {}
    matches: list[LotMatch] = []

    sorted_tx = sorted(transactions, key=lambda t: (t["executed_at"], t["id"]))

    for tx in sorted_tx:
        action = tx["action"]
        if action in {"dividend", "fee", "deposit", "withdrawal", "split"}:
            continue  # handled elsewhere — no lot impact

        sym = tx["symbol"]
        at = tx["asset_type"]
        ccy = tx.get("trade_currency", "USD")
        key = (sym, at)
        pool = pools.setdefault(key, [])

        qty = D(tx["quantity"])
        price = D(tx["price"])
        fees = D(tx.get("fees") or 0)

        if action in {"buy", "transfer_in"}:
            if qty <= 0:
                raise ValueError(f"Buy quantity must be > 0 (tx {tx.get('id')}: {qty}).")
            unit_cost = price + (fees / qty)
            pool.append(Lot(
                transaction_id=tx["id"], symbol=sym, asset_type=at,
                quantity=qty, quantity_original=qty,
                price=unit_cost, fees=fees,
                executed_at=tx["executed_at"], currency=ccy,
            ))

        elif action in {"sell", "transfer_out"}:
            available = sum((l.quantity for l in pool), Decimal("0"))
            if qty > available:
                raise ValueError(
                    f"Sell {qty} {sym} at {tx['executed_at']} exceeds holdings "
                    f"({available}). Tx id={tx.get('id')}."
                )

            if method == "average":
                _collapse_to_average(pool, sym, at, ccy)

            # Iteration order
            iter_pool = pool if method != "lifo" else list(reversed(pool))

            remaining = qty
            for lot in iter_pool:
                if remaining <= 0:
                    break
                if lot.quantity <= 0:
                    continue
                matched_qty = min(lot.quantity, remaining)
                fee_alloc = (fees * matched_qty / qty) if qty > 0 else Decimal("0")
                proceeds = matched_qty * price - fee_alloc
                cost = matched_qty * lot.price

                matches.append(LotMatch(
                    sell_transaction_id=tx["id"],
                    lot_transaction_id=lot.transaction_id,
                    symbol=sym, asset_type=at,
                    sold_quantity=matched_qty,
                    cost_per_unit=lot.price,
                    sell_price=price,
                    sell_fees_allocated=fee_alloc,
                    proceeds=proceeds,
                    cost=cost,
                    realized_pnl=proceeds - cost,
                    holding_period_days=(tx["executed_at"] - lot.executed_at).days,
                    sell_executed_at=tx["executed_at"],
                    buy_executed_at=lot.executed_at,
                    currency=ccy,
                ))
                lot.quantity -= matched_qty
                remaining -= matched_qty

            # Drop fully-consumed lots so the pool stays compact
            pool[:] = [l for l in pool if l.quantity > 0]

    open_lots = [l for pool in pools.values() for l in pool if l.quantity > 0]
    return open_lots, matches


def _collapse_to_average(pool: list[Lot], sym: str, at: str, ccy: str) -> None:
    """In-place merge of all lots in pool into one weighted-average lot."""
    if not pool:
        return
    total_qty = sum((l.quantity for l in pool), Decimal("0"))
    if total_qty <= 0:
        return
    total_cost = sum((l.quantity * l.price for l in pool), Decimal("0"))
    avg = Lot(
        transaction_id=pool[0].transaction_id,
        symbol=sym, asset_type=at,
        quantity=total_qty, quantity_original=total_qty,
        price=total_cost / total_qty,
        fees=Decimal("0"),
        executed_at=pool[0].executed_at, currency=ccy,
    )
    pool.clear()
    pool.append(avg)


def realized_pnl_total(matches: list[LotMatch]) -> Decimal:
    """Sum of realized P&L across all matches."""
    return sum((m.realized_pnl for m in matches), Decimal("0"))


def unrealized_pnl(
    open_lots: list[Lot],
    current_prices: dict[tuple[str, str], Decimal],
) -> Decimal:
    """Sum of (current_price - cost_basis_per_unit) * remaining_qty across open lots.

    Lots without a current price entry are skipped (not failed) — caller
    decides how to surface stale prices in the UI.
    """
    total = Decimal("0")
    for lot in open_lots:
        cur = current_prices.get((lot.symbol, lot.asset_type))
        if cur is not None:
            total += (cur - lot.price) * lot.quantity
    return total
