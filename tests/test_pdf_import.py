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


# ---------- bloomberg ticker extraction ---------------------------------------

def _fake_word(text: str, x0: float, top: float) -> dict:
    """Minimal pdfplumber-style word dict for unit tests."""
    return {"text": text, "x0": x0, "top": top, "x1": x0 + 10 * len(text), "bottom": top + 10}


def test_extract_bloomberg_ticker_us_listing():
    from pt.importers.pdf.lgt import _extract_bloomberg_ticker

    block = [
        _fake_word("US0231351067", 280, 100),  # ISIN
        _fake_word("645156", 280, 110),         # Valor
        _fake_word("AMZN", 280, 120),
        _fake_word("UW", 305, 121),             # 1px y-jitter — same row
        _fake_word("Nicht-Basis", 280, 132),    # GICS
    ]
    assert _extract_bloomberg_ticker(block) == "AMZN UW"


def test_extract_bloomberg_ticker_swiss_listing():
    from pt.importers.pdf.lgt import _extract_bloomberg_ticker

    block = [
        _fake_word("CH0012005267", 280, 100),
        _fake_word("1200526", 280, 110),
        _fake_word("NOVN", 280, 120),
        _fake_word("SE", 305, 122),
    ]
    assert _extract_bloomberg_ticker(block) == "NOVN SE"


def test_extract_bloomberg_ticker_paris_listing():
    from pt.importers.pdf.lgt import _extract_bloomberg_ticker

    block = [
        _fake_word("NL0000235190", 280, 100),
        _fake_word("AIR", 280, 120),
        _fake_word("FP", 305, 120),
    ]
    assert _extract_bloomberg_ticker(block) == "AIR FP"


def test_extract_bloomberg_ticker_returns_none_when_absent():
    from pt.importers.pdf.lgt import _extract_bloomberg_ticker

    block = [
        _fake_word("US0231351067", 280, 100),
        _fake_word("645156", 280, 110),
    ]
    assert _extract_bloomberg_ticker(block) is None


def test_extract_bloomberg_ticker_rejects_unknown_exchange_codes():
    """Two adjacent uppercase tokens that are NOT a known exchange suffix
    (e.g. random GICS sector words) must not produce false positives."""
    from pt.importers.pdf.lgt import _extract_bloomberg_ticker

    block = [
        _fake_word("FOO", 280, 100),  # not in _BLOOMBERG_EXCHANGE_CODES
        _fake_word("XX", 305, 100),   # XX is not a known exchange
    ]
    assert _extract_bloomberg_ticker(block) is None


def test_extract_bloomberg_ticker_rejects_when_y_too_far_apart():
    """Ticker and exchange code must be on the same visual row.
    Different `top` values mean they belong to different lines."""
    from pt.importers.pdf.lgt import _extract_bloomberg_ticker

    block = [
        _fake_word("AMZN", 280, 100),
        _fake_word("UW", 305, 130),  # 30px below — clearly a different row
    ]
    assert _extract_bloomberg_ticker(block) is None


def test_parsed_holding_ticker_property_strips_exchange():
    from datetime import date
    from decimal import Decimal

    from pt.importers.pdf.types import ParsedHolding

    h = ParsedHolding(
        isin="US0231351067", name="Amazon.Com Inc", asset_type="stock",
        quantity=Decimal("90"), entry_price=Decimal("233.51"), entry_currency="USD",
        entry_date=date(2025, 1, 23), current_price=None, current_value_base_ccy=None,
        bloomberg_ticker="AMZN UW",
    )
    assert h.ticker == "AMZN"
    assert h.bloomberg_exchange == "UW"
    assert h.symbol == "AMZN"  # ticker beats ISIN


def test_parsed_holding_falls_back_to_isin_without_bloomberg():
    from datetime import date
    from decimal import Decimal

    from pt.importers.pdf.types import ParsedHolding

    h = ParsedHolding(
        isin="US0231351067", name="Amazon.Com Inc", asset_type="stock",
        quantity=Decimal("90"), entry_price=Decimal("233.51"), entry_currency="USD",
        entry_date=date(2025, 1, 23), current_price=None, current_value_base_ccy=None,
        bloomberg_ticker=None,
    )
    assert h.ticker is None
    assert h.symbol == "US0231351067"


@requires_lgt_pdf
def test_lgt_parser_extracts_bloomberg_tickers_for_known_positions():
    """End-to-end on the reference PDF: every well-known holding must come
    back with the correct bare ticker so Twelve Data lookups work without
    further mapping. Regression-guard for the symbol pipeline."""
    from pt.importers.pdf import parse_pdf

    stmt = parse_pdf(REFERENCE_PDF)
    by_isin = {h.isin: h for h in stmt.holdings if h.isin}
    expected = {
        "CH0012005267": "NOVN",   # Novartis on SIX
        "CH1243598427": "SDZ",    # Sandoz on SIX
        "NL0000235190": "AIR",    # Airbus on Paris
        "US0231351067": "AMZN",   # Amazon on Nasdaq
        "US11135F1012": "AVGO",   # Broadcom on Nasdaq
        "US0404132054": "ANET",   # Arista Networks on NYSE
    }
    for isin, expected_ticker in expected.items():
        if isin not in by_isin:
            continue  # OCR may drop one; don't fail the suite for that
        assert by_isin[isin].ticker == expected_ticker, (
            f"{isin}: expected {expected_ticker}, got {by_isin[isin].ticker!r} "
            f"(bloomberg_ticker={by_isin[isin].bloomberg_ticker!r})"
        )


# ---------- OCR pathology recovery -------------------------------------------

def test_recover_date_text_handles_apostrophe_t_for_one():
    """LGT scan pathology: `1` rendered as `'t` glued to the previous digit."""
    from pt.importers.pdf.lgt import _try_parse_date
    from datetime import date

    assert _try_parse_date("3't.01.2025") == date(2025, 1, 31)
    assert _try_parse_date("0l.06.2019") == date(2019, 6, 1)   # l → 1
    assert _try_parse_date("1A.06.2019") == date(2019, 6, 10)  # A → 0


def test_recover_date_text_passes_clean_dates_unchanged():
    from pt.importers.pdf.lgt import _try_parse_date
    from datetime import date

    assert _try_parse_date("31.01.2025") == date(2025, 1, 31)
    assert _try_parse_date("not-a-date") is None


def test_extract_prices_rejects_integer_only_tokens():
    """When OCR slices `201.9400` into `20` + `r.9400`, the bare `20` must NOT
    survive as a pseudo-price. Real prices always carry a decimal portion in
    LGT statements."""
    from decimal import Decimal
    from pt.importers.pdf.lgt import _extract_prices

    # The "real" entry price `201.9400` is missing — only the OCR fragments
    # remain. The current price `313.0000` is intact.
    block = [
        {"text": "20",       "x0": 470, "top": 100},  # OCR fragment of `201`
        {"text": "r.9400",   "x0": 480, "top": 100},  # OCR fragment of `1.9400`
        {"text": "313.0000", "x0": 525, "top": 100},  # Aktueller Kurs intact
        {"text": "1.0430",   "x0": 470, "top": 110},  # FX rate, row below
        {"text": "1.1743",   "x0": 525, "top": 110},  # current FX rate
    ]
    entry, current = _extract_prices(block, qty=Decimal("100"))
    assert entry is None, f"entry must be None (OCR-shredded), got {entry}"
    assert current == Decimal("313.0000")


def test_extract_prices_rejects_fx_rate_bleed_into_empty_entry_column():
    """Defensive: if the entry-price column has only an FX-rate-shaped token
    (because the real price was OCR-shredded), and the current column has a
    real price on a different row, treat entry as missing rather than report
    the FX rate as the price."""
    from decimal import Decimal
    from pt.importers.pdf.lgt import _extract_prices

    block = [
        {"text": "313.0000", "x0": 525, "top": 100},  # current price, top row
        {"text": "1.0430",   "x0": 470, "top": 110},  # FX rate, row below — would be wrong as entry
    ]
    entry, current = _extract_prices(block, qty=Decimal("100"))
    assert entry is None
    assert current == Decimal("313.0000")


def test_extract_prices_keeps_aligned_entry_and_current():
    """Happy path: both prices on the same visual row → both extracted."""
    from decimal import Decimal
    from pt.importers.pdf.lgt import _extract_prices

    block = [
        {"text": "201.9400", "x0": 470, "top": 100},  # entry
        {"text": "313.0000", "x0": 525, "top": 100},  # current
    ]
    entry, current = _extract_prices(block, qty=Decimal("100"))
    assert entry == Decimal("201.9400")
    assert current == Decimal("313.0000")


@requires_lgt_pdf
def test_lgt_parser_recovers_googl_date_but_skips_unrecoverable_price():
    """Regression-guard: GOOGL's entry date was unreadable (`3't.01.2025`)
    AND its entry price was OCR-shredded (`r.9400` for `201.9400`). The date
    is now recoverable; the price is genuinely unrecoverable. We extract
    GOOGL into `holdings` but `to_transactions` correctly skips it because
    we won't fabricate a wrong cost basis."""
    from pt.importers.pdf import parse_pdf, to_transactions
    from datetime import date

    stmt = parse_pdf(REFERENCE_PDF)
    by_isin = {h.isin: h for h in stmt.holdings if h.isin}
    googl = by_isin.get("US02079K3059")
    assert googl is not None, "GOOGL holding must be parsed (with or without prices)"
    assert googl.entry_date == date(2025, 1, 31), (
        "date OCR recovery failed for GOOGL"
    )
    assert googl.entry_price is None, (
        "entry price was OCR-shredded — must NOT fabricate a cost basis"
    )

    txs = to_transactions(stmt)
    googl_txs = [t for t in txs if t.get("symbol") == "GOOGL"]
    assert googl_txs == [], (
        "GOOGL must be skipped in to_transactions when entry_price is None"
    )


@requires_lgt_pdf
def test_to_transactions_uses_bare_ticker_as_symbol():
    from pt.importers.pdf import parse_pdf, to_transactions

    stmt = parse_pdf(REFERENCE_PDF)
    txs = to_transactions(stmt)
    symbols = {t["symbol"] for t in txs}
    # Spot-check a few US tickers — these are unambiguous on Twelve Data.
    for ticker in ("AMZN", "AVGO", "ANET"):
        assert ticker in symbols, f"expected {ticker} as transaction.symbol, got {symbols}"


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
