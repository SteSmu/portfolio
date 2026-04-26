"""Shared dataclasses for parsed broker statements.

The mapper in `pt.importers.pdf.__init__.to_transactions` converts these
into rows compatible with `pt.db.transactions.insert`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class ParsedHolding:
    """One position line from a broker statement."""

    isin: str | None
    name: str
    asset_type: str            # 'stock' / 'etf' / 'bond' / 'fund' / 'crypto'
    quantity: Decimal
    entry_price: Decimal | None
    entry_currency: str
    entry_date: date | None
    current_price: Decimal | None
    current_value_base_ccy: Decimal | None  # for reconciliation against parser sum
    metadata: dict = field(default_factory=dict)

    @property
    def symbol(self) -> str:
        """Best identifier — ISIN if available, otherwise the cleaned name."""
        return self.isin or self.name


@dataclass
class ParsedCashPosition:
    """A bank account / money-market position."""

    account: str
    currency: str
    balance: Decimal
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedStatement:
    """The shape every PDF parser must produce."""

    parser: str                # e.g. 'lgt:vermoegensaufstellung'
    customer: str
    statement_date: date
    base_currency: str
    file_hash: str
    file_name: str
    holdings: list[ParsedHolding] = field(default_factory=list)
    cash: list[ParsedCashPosition] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_value_base_ccy(self) -> Decimal:
        """Sum of position values (best-effort) for reconciliation."""
        total = Decimal("0")
        for h in self.holdings:
            if h.current_value_base_ccy is not None:
                total += h.current_value_base_ccy
        for c in self.cash:
            # Cash is in its own currency — caller must FX-convert if needed.
            if c.currency == self.base_currency:
                total += c.balance
        return total
