"""PDF importer entry point.

Public API:
    parse_pdf(path)              -> ParsedStatement      auto-detect format
    to_transactions(stmt, pid)   -> list[dict]           ready for db.transactions.insert
    import_to_portfolio(path,pid) -> ImportResult        end-to-end with idempotency
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal
from pathlib import Path

from pt.db.connection import get_conn
from pt.db import transactions as _db_tx
from pt.importers.pdf import format_detect
from pt.importers.pdf.format_detect import UnsupportedFormatError  # re-export
from pt.importers.pdf.types import (
    ParsedCashPosition,
    ParsedHolding,
    ParsedStatement,
)

__all__ = [
    "parse_pdf",
    "to_transactions",
    "import_to_portfolio",
    "ImportResult",
    "ParsedStatement",
    "ParsedHolding",
    "ParsedCashPosition",
    "UnsupportedFormatError",
]


def parse_pdf(pdf_path: str | Path) -> ParsedStatement:
    """Auto-detect the format and parse."""
    parser_module = format_detect.parser_for(pdf_path)
    return parser_module.parse(pdf_path)


def to_transactions(stmt: ParsedStatement) -> list[dict]:
    """Convert a parsed statement into transaction dicts.

    Each holding becomes ONE `transfer_in` transaction at the recorded entry
    price + entry date. This is the only honest mapping from a position
    snapshot — we don't have the actual buy history, only the avg cost basis.

    The caller passes these dicts to `pt.db.transactions.insert` (one per
    call, since insert handles per-row validation).
    """
    rows: list[dict] = []
    for h in stmt.holdings:
        if h.entry_price is None or h.entry_date is None:
            continue  # parser couldn't extract enough — skip rather than guess
        executed_at = datetime.combine(
            h.entry_date, time(0, 0), tzinfo=timezone.utc,
        )
        # Symbol priority: bare ticker (Twelve-Data-friendly) > ISIN > name.
        # `source_doc_id` keeps the ISIN when available so re-imports stay
        # idempotent even if the Bloomberg line was previously OCR-damaged
        # and we fell back to the name on the first run.
        symbol = h.symbol.upper()
        doc_id_key = (h.isin or h.name).upper()
        rows.append({
            "symbol": symbol,
            "asset_type": h.asset_type,
            "action": "transfer_in",
            "executed_at": executed_at,
            "quantity": h.quantity,
            "price": h.entry_price,
            "trade_currency": h.entry_currency,
            "fees": Decimal("0"),
            "fees_currency": h.entry_currency,
            "fx_rate": None,
            "note": _build_note(stmt, h),
            "source": f"pdf:{stmt.parser}",
            "source_doc_id": f"{stmt.file_hash[:16]}:{doc_id_key}",
        })
    return rows


def _build_note(stmt: ParsedStatement, h: ParsedHolding) -> str:
    bits = [
        f"Imported from {stmt.file_name}",
        f"({stmt.parser}, {stmt.statement_date.isoformat()})",
    ]
    if h.name:
        bits.append(f"name={h.name!r}")
    if h.bloomberg_ticker:
        bits.append(f"bloomberg={h.bloomberg_ticker!r}")
    if h.isin:
        bits.append(f"isin={h.isin}")
    return " ".join(bits)


@dataclass
class ImportResult:
    parser: str
    file_name: str
    file_hash: str
    customer: str
    statement_date: str
    transactions_added: int
    transactions_skipped: int
    holdings_parsed: int
    cash_parsed: int
    warnings: list[str]
    skipped_reason: str | None = None  # set when the file_hash already imported


def import_to_portfolio(
    pdf_path: str | Path,
    portfolio_id: int,
    *,
    actor: str = "pdf-import",
    dry_run: bool = False,
) -> ImportResult:
    """Parse the PDF and write transfer_in transactions to the portfolio.

    Idempotency is enforced two ways:
      1. `import_log` row keyed on `(portfolio_id, file_hash)` — same PDF
         twice into the same portfolio short-circuits with `skipped_reason`.
      2. `transactions.source_doc_id` UNIQUE on
         `(portfolio_id, source, source_doc_id, executed_at, symbol, action,
         quantity)` so even if the import_log row was deleted, individual
         duplicate transaction rows get blocked.
    """
    stmt = parse_pdf(pdf_path)
    pdf_path = Path(pdf_path)

    if not dry_run and _import_log_exists(portfolio_id, stmt.file_hash):
        return ImportResult(
            parser=stmt.parser,
            file_name=stmt.file_name,
            file_hash=stmt.file_hash,
            customer=stmt.customer,
            statement_date=stmt.statement_date.isoformat(),
            transactions_added=0,
            transactions_skipped=len(stmt.holdings),
            holdings_parsed=len(stmt.holdings),
            cash_parsed=len(stmt.cash),
            warnings=stmt.warnings,
            skipped_reason="file_hash already imported into this portfolio",
        )

    rows = to_transactions(stmt)
    added = 0
    skipped = 0

    if not dry_run:
        for r in rows:
            try:
                _db_tx.insert(
                    portfolio_id=portfolio_id,
                    symbol=r["symbol"],
                    asset_type=r["asset_type"],
                    action=r["action"],
                    executed_at=r["executed_at"],
                    quantity=r["quantity"],
                    price=r["price"],
                    trade_currency=r["trade_currency"],
                    fees=r["fees"],
                    fees_currency=r["fees_currency"],
                    fx_rate=r["fx_rate"],
                    note=r["note"],
                    source=r["source"],
                    source_doc_id=r["source_doc_id"],
                    changed_by=actor,
                )
                added += 1
            except Exception as e:
                skipped += 1
                stmt.warnings.append(f"insert failed for {r['symbol']}: {e}")
        _import_log_record(
            portfolio_id=portfolio_id,
            file_name=stmt.file_name,
            file_hash=stmt.file_hash,
            file_type="pdf",
            parser=stmt.parser,
            transactions_added=added,
            transactions_skipped=skipped,
            raw_text=None,  # we keep this off for now — PII concern
        )

    return ImportResult(
        parser=stmt.parser,
        file_name=stmt.file_name,
        file_hash=stmt.file_hash,
        customer=stmt.customer,
        statement_date=stmt.statement_date.isoformat(),
        transactions_added=added if not dry_run else len(rows),
        transactions_skipped=skipped,
        holdings_parsed=len(stmt.holdings),
        cash_parsed=len(stmt.cash),
        warnings=stmt.warnings,
        skipped_reason=None,
    )


def _import_log_exists(portfolio_id: int, file_hash: str) -> bool:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM portfolio.import_log "
            "WHERE portfolio_id = %s AND file_hash = %s",
            (portfolio_id, file_hash),
        )
        return cur.fetchone() is not None


def _import_log_record(
    *,
    portfolio_id: int,
    file_name: str,
    file_hash: str,
    file_type: str,
    parser: str,
    transactions_added: int,
    transactions_skipped: int,
    raw_text: str | None,
) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO portfolio.import_log
                (portfolio_id, file_name, file_hash, file_type, parser,
                 transactions_added, transactions_skipped, raw_text)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (portfolio_id, file_hash) DO NOTHING""",
            (portfolio_id, file_name, file_hash, file_type, parser,
             transactions_added, transactions_skipped, raw_text),
        )
        conn.commit()
