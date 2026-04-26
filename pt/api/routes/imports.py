"""PDF import endpoint — multipart upload + dry-run preview + commit.

Workflow:
  1. Frontend uploads a PDF as multipart form data.
  2. With ?dry_run=true: parse + return what WOULD be imported (no DB write).
  3. With ?dry_run=false (default): parse + write transfer_in transactions
     into the target portfolio. Idempotent on file_hash + position-uid.

Errors:
  - 400 if the file is not a recognized broker statement
  - 404 if the portfolio doesn't exist
  - 200 with `skipped_reason` set if the same file_hash already imported
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Path as PathParam, Query, UploadFile

from pt.db import portfolios as _portfolios
from pt.importers.pdf import (
    UnsupportedFormatError,
    import_to_portfolio,
    parse_pdf,
    to_transactions,
)

router = APIRouter(prefix="/portfolios/{portfolio_id}/import", tags=["imports"])


@router.post("/pdf")
async def import_pdf(
    portfolio_id: int = PathParam(..., ge=1),
    file: UploadFile = File(..., description="Broker-statement PDF"),
    dry_run: bool = Query(False, description="Preview only — don't write to DB."),
    actor: str = Query("api", description="Audit attribution (e.g. user email)."),
) -> dict:
    """Upload a broker-statement PDF and (optionally) write its positions
    into the target portfolio as `transfer_in` transactions."""
    if not _portfolios.get(portfolio_id):
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found.")

    suffix = Path(file.filename or "upload.pdf").suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await file.read()
        tmp.write(content)
        tmp.close()

        if dry_run:
            try:
                stmt = parse_pdf(tmp.name)
            except UnsupportedFormatError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            tx_dicts = to_transactions(stmt)
            return {
                "dry_run": True,
                "parser": stmt.parser,
                "customer": stmt.customer,
                "statement_date": stmt.statement_date.isoformat(),
                "base_currency": stmt.base_currency,
                "file_name": file.filename,
                "file_hash": stmt.file_hash,
                "holdings_parsed": len(stmt.holdings),
                "cash_parsed": len(stmt.cash),
                "transactions_planned": len(tx_dicts),
                "transactions": [_serialize_tx(t) for t in tx_dicts],
                "warnings": stmt.warnings,
            }

        try:
            result = import_to_portfolio(tmp.name, portfolio_id, actor=actor)
        except UnsupportedFormatError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return result.__dict__ | {"dry_run": False}
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def _serialize_tx(t: dict) -> dict:
    """Coerce Decimal + datetime into JSON-friendly types for the dry-run preview."""
    out = dict(t)
    out["quantity"] = str(t["quantity"])
    out["price"] = str(t["price"])
    out["fees"] = str(t["fees"])
    if t.get("fx_rate") is not None:
        out["fx_rate"] = str(t["fx_rate"])
    out["executed_at"] = t["executed_at"].isoformat()
    return out
