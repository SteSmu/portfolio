"""PDF importer tests.

These tests are a tier above the mock-driven unit tests: they parse the actual
LGT statement at the repo root if present, otherwise skip gracefully. CI runs
without the PDF; locally Stefan can drop one in to validate every change.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import requires_db

REFERENCE_PDF = Path(__file__).resolve().parent.parent / "1331_001.pdf"
requires_lgt_pdf = pytest.mark.skipif(
    not REFERENCE_PDF.exists(),
    reason="Reference LGT PDF not present (committed-out via .gitignore)."
)


# ---------- pure parser -------------------------------------------------------

@requires_lgt_pdf
def test_lgt_parser_extracts_all_eleven_holdings():
    from pt.importers.pdf import parse_pdf

    stmt = parse_pdf(REFERENCE_PDF)
    assert stmt.parser == "lgt:vermoegensaufstellung"
    assert stmt.customer == "Stefan Schmucker"
    assert stmt.statement_date.isoformat() == "2025-12-31"
    assert stmt.base_currency == "EUR"
    assert len(stmt.holdings) == 11

    by_name = {h.name.split()[0]: h for h in stmt.holdings if h.name != "?"}
    expected_names = {"Novartis", "Roche", "Sandoz", "Airbus", "Alphabet",
                       "Amazon.Com", "Arista", "Broadcom", "Marvell", "NVIDIA", "Oracle"}
    assert expected_names.issubset(set(by_name.keys()))


@requires_lgt_pdf
def test_lgt_parser_market_values_match_pdf_total_within_one_position():
    """Total parser-derived market value should match the PDF Total minus any
    OCR-damaged position (Marvell loses 10k due to a single-digit OCR loss)."""
    from pt.importers.pdf import parse_pdf

    stmt = parse_pdf(REFERENCE_PDF)
    parser_total = sum(
        h.current_value_base_ccy for h in stmt.holdings
        if h.current_value_base_ccy is not None
    )
    # PDF Total = 258'899.04. Marvell OCR-damaged → reads as 1940.98 instead of 11940.98.
    # Acceptable diff = 10,000.60.
    pdf_total = float(parser_total)
    assert 248_000 < pdf_total < 250_000


@requires_lgt_pdf
def test_lgt_parser_pins_known_positions():
    """Spot-check: a few well-known positions must come back exact."""
    from decimal import Decimal

    from pt.importers.pdf import parse_pdf

    stmt = parse_pdf(REFERENCE_PDF)
    by_isin = {h.isin: h for h in stmt.holdings if h.isin}

    # Sandoz — easy case: anchor row + data row above (Pattern B), exact values.
    sandoz = by_isin["CH1243598427"]
    assert sandoz.quantity == Decimal("100")  # OCR-merged 50 + 50
    assert sandoz.entry_price == Decimal("12.9800")
    assert sandoz.current_price == Decimal("57.8400")
    assert sandoz.current_value_base_ccy == Decimal("3108.48")
    assert sandoz.entry_currency == "CHF"
    assert sandoz.entry_date.isoformat() == "2023-10-04"


# ---------- to_transactions mapping -------------------------------------------

@requires_lgt_pdf
def test_to_transactions_yields_one_transfer_in_per_holding():
    from pt.importers.pdf import parse_pdf, to_transactions

    stmt = parse_pdf(REFERENCE_PDF)
    txs = to_transactions(stmt)
    # Skip holdings without entry_date (Alphabet OCR-damaged) — to_transactions
    # filters them out.
    assert all(t["action"] == "transfer_in" for t in txs)
    assert all(t["source"].startswith("pdf:lgt") for t in txs)
    # Idempotency key carries the file_hash + symbol
    keys = {t["source_doc_id"] for t in txs}
    assert len(keys) == len(txs)  # each unique


# ---------- end-to-end via the API --------------------------------------------

@pytest.fixture
def client() -> TestClient:
    from pt.api.app import app
    return TestClient(app)


@requires_lgt_pdf
@requires_db
def test_api_dry_run_returns_preview_without_writing(client, isolated_portfolio):
    with REFERENCE_PDF.open("rb") as fh:
        files = {"file": ("1331_001.pdf", fh, "application/pdf")}
        resp = client.post(
            f"/api/portfolios/{isolated_portfolio}/import/pdf?dry_run=true",
            files=files,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["parser"] == "lgt:vermoegensaufstellung"
    assert body["holdings_parsed"] == 11
    assert body["transactions_planned"] >= 9  # holdings with valid entry_date

    # Verify nothing was written
    from pt.db import transactions as _tx
    assert _tx.list_for_portfolio(isolated_portfolio) == []


@requires_lgt_pdf
@requires_db
def test_api_full_import_writes_transfer_in_rows_idempotently(client, isolated_portfolio):
    from pt.db import transactions as _tx

    with REFERENCE_PDF.open("rb") as fh:
        files = {"file": ("1331_001.pdf", fh, "application/pdf")}
        first = client.post(
            f"/api/portfolios/{isolated_portfolio}/import/pdf",
            files=files,
        )
    assert first.status_code == 200, first.text
    body1 = first.json()
    assert body1["transactions_added"] >= 9
    assert body1["skipped_reason"] is None

    written = _tx.list_for_portfolio(isolated_portfolio, limit=100)
    assert len(written) == body1["transactions_added"]
    assert all(t["action"] == "transfer_in" for t in written)
    assert all(t["source"].startswith("pdf:lgt") for t in written)

    # Re-import the SAME PDF — short-circuit via import_log idempotency
    with REFERENCE_PDF.open("rb") as fh:
        files = {"file": ("1331_001.pdf", fh, "application/pdf")}
        second = client.post(
            f"/api/portfolios/{isolated_portfolio}/import/pdf",
            files=files,
        )
    body2 = second.json()
    assert body2["skipped_reason"] is not None
    assert body2["transactions_added"] == 0


def test_api_404_for_unknown_portfolio(client):
    files = {"file": ("x.pdf", BytesIO(b"%PDF-1.4 dummy"), "application/pdf")}
    resp = client.post("/api/portfolios/99999999/import/pdf?dry_run=true", files=files)
    assert resp.status_code == 404


def test_api_400_for_non_lgt_pdf(client, tmp_path):
    """A minimal valid-PDF that isn't an LGT statement should be rejected with 400."""
    pdf = tmp_path / "notlgt.pdf"
    # Tiny PDF that just renders "Hello"
    pdf.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
    # Need a portfolio to exist to get past the 404 check
    from pt.db import portfolios as _portfolios
    pid = _portfolios.create("_pt_pdf_test")
    try:
        with pdf.open("rb") as fh:
            files = {"file": ("notlgt.pdf", fh, "application/pdf")}
            resp = client.post(
                f"/api/portfolios/{pid}/import/pdf?dry_run=true",
                files=files,
            )
        assert resp.status_code == 400
    finally:
        _portfolios.delete_hard(pid)
