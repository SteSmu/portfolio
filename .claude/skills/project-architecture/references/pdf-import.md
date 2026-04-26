# PDF importer (`pt/importers/pdf/`)

Generic registry-based pipeline for ingesting broker statement PDFs as
`transfer_in` transactions. One concrete parser today (LGT Bank
Vermögensaufstellung); architecture is designed to take more.

## Modules

| File | Role |
|--|--|
| [`types.py`](../../pt/importers/pdf/types.py) | `ParsedHolding` + `ParsedCashPosition` + `ParsedStatement` dataclasses — the contract every parser produces |
| [`format_detect.py`](../../pt/importers/pdf/format_detect.py) | Registry of parsers + `detect()` / `parser_for()`. Adding a new format = adding a tuple here |
| [`lgt.py`](../../pt/importers/pdf/lgt.py) | Concrete parser for LGT Bank statements; the heavy lifting |
| [`__init__.py`](../../pt/importers/pdf/__init__.py) | `parse_pdf()` (auto-detect + parse) + `to_transactions()` (mapping to DB rows) + `import_to_portfolio()` (end-to-end with idempotency) |

## Pipeline

```
PDF file
  │
  ▼
format_detect.parser_for(path)         # reads first page, picks parser
  │
  ▼
parser.parse(path) -> ParsedStatement  # holdings + cash + warnings + file_hash
  │
  ▼
to_transactions(stmt) -> list[dict]    # one transfer_in per holding with entry data
  │
  ▼
import_to_portfolio(path, pid)         # writes through db.transactions.insert
  │
  ├─ import_log(file_hash) → short-circuits if already imported
  └─ source_doc_id UNIQUE on transactions → blocks per-row dupes
```

Idempotency is enforced **twice** so even if the `import_log` row is
hand-deleted, individual transaction rows still don't double-write.

## Statement → transactions mapping

Each holding becomes a single `transfer_in` action — the only honest
mapping from a position snapshot. The original buy history isn't in a
year-end statement, only the current avg cost basis + first-acquired date.
Concretely per holding:

```python
{
  "action": "transfer_in",
  "symbol": isin or name (uppercased),
  "asset_type": "stock"|"etf"|"crypto"|"bond"|"fund",
  "executed_at": entry_date at 00:00:00 UTC,
  "quantity": Decimal,
  "price": entry_price (avg cost basis),
  "trade_currency": position currency,
  "fees": 0,                 # not extractable from statements
  "source": "pdf:lgt:vermoegensaufstellung",
  "source_doc_id": "{file_hash[:16]}:{symbol}",
}
```

Holdings without an entry date or entry price are **skipped silently** —
ingesting half-data would produce wrong cost-basis math downstream.

## LGT parser specifics

LGT Bank ships scanned PDFs whose OCR is fragile. The parser is
deliberately permissive — it extracts what it can, records anything
weird in `ParsedStatement.warnings`, never crashes on a single bad block.

### OCR pathologies the parser handles

| Symptom | Example (raw OCR) | Fix |
|--|--|--|
| Embedded space in ISIN | `cH001 2005267` for `CH0012005267` | Token-based extraction: try concatenating 1-4 adjacent tokens, validate `len==12 + ISO-country prefix + last digit` |
| Lowercase prefix on ISIN | `cH...`, `us...` | `.upper()` after concat |
| Letter-into-digit | `29'451.A3` for `29'451.03` | A→0, O→0, l/I→1 in `_parse_decimal` |
| Stray comma after thousands sep | `26',655.31` for `26'655.31` | Strip both `'` and `,` (LGT never uses comma as decimal) |
| Hyphen as date separator | `11.06-2019` | Permissive `[.\-/]+` separator regex |
| Title broken | `Vermögensaufstellu ng` | Strip whitespace before format-detection match |
| Header tampering | `5tückzahl` (5 instead of S) | Permissive header regex |
| Qty + market value pushed to row above the CCY anchor (Sandoz, Roche, Airbus, Alphabet, Amazon, Broadcom, NVIDIA, Oracle) | various | Block construction merges up to 2 rows above (within 10px of anchor) |
| Full data row pushed above the CCY anchor (Sandoz pattern) | `50 Sandoz Group AG ... 12.9800` above `CHF` | Same merge-up-to-2 logic |
| Orphan-above row of NEXT holding sucked into current block | Roche orphan above Roche anchor pulled into Novartis block | Look-ahead: row immediately preceding any CCY anchor is skipped |
| Total/footer row picks up market value | Page-end Total row at x=600 | Hard-stop on `Total` / `Verwendete` / `Währung` first-tokens |

### Column layout (measured from the reference PDF)

| Column | x range | Field |
|--|--|--|
| Whg. | 40-60 | currency (CCY anchor) |
| Stückzahl | 110-145 | quantity |
| Bezeichnung | 135-260 | name + country (multi-line) |
| ISIN/Valor | 280-410 | ISIN + Bloomberg + GICS (multi-line) |
| Einstands-Kurs | 460-510 | entry price + entry FX rate + entry date |
| Aktueller Kurs | 520-570 | current price + current FX rate + current date |
| Kurswert | 580-650 | EUR market value |
| G/V Markt | 650-700 | percentages |
| ... | ≥ 700 | more percentages |

The parser extracts each field by x-bound, NOT by text-position order —
that's how it survives OCR slips that change visual order.

### Fields parsed per holding

- ISIN (with ISO-country prefix sanity check)
- name (top row of name column, filtered for percent/numeric tokens)
- quantity
- entry_price + entry_currency + entry_date
- current_price + current_date
- current_value_base_ccy (for reconciliation against PDF Total)
- asset_type (heuristic from GICS text: `bond` / `etf` / default `stock`)

### Unrecoverable losses

Two pathologies the parser cannot recover from:

| Loss | Example | What's missing |
|--|--|--|
| OCR-dropped digit | `1',940.98` instead of `11',940.98` | The leading `1` is gone — no way to know |
| Garbled date glyph | `3't.01.2025` for `31.01.2025` | The `1` reads as `'t`, `_DATE_RE.fullmatch` fails |

The parser surfaces these via `warnings` (the import-log keeps them);
the user can correct the resulting transactions by hand on the
Transactions page.

## API surface

```text
POST /api/portfolios/{id}/import/pdf
  multipart: file (the PDF)
  query: dry_run=bool (default false), actor=string

  dry_run=true   -> {parser, customer, statement_date, holdings_parsed,
                     transactions_planned, transactions[], warnings[]}
  dry_run=false  -> ImportResult (transactions_added, transactions_skipped,
                                  warnings, skipped_reason)

Status codes:
  200 - ok (skipped_reason set if file already imported)
  400 - unsupported PDF format / unparseable header
  404 - portfolio doesn't exist
```

Dry-run never writes; full import writes through `db.transactions.insert`
(audit trigger fires automatically) and records an `import_log` row.

## Frontend integration

[`frontend/src/components/PdfImport.tsx`](../../frontend/src/components/PdfImport.tsx)
is mounted at the top of the Holdings page (also visible in the
empty-portfolio state). Drop in a PDF → API dry-run → preview table → Confirm.

Re-uploading the same PDF returns a `skipped_reason` from the backend
(idempotent), so users can safely click `Import` twice without thinking.

## Adding a new broker

1. Create `pt/importers/pdf/<broker>.py` with two top-level functions:
   - `def can_parse(first_page_text: str) -> bool` — fast path, uses the
     first page text only
   - `def parse(pdf_path) -> ParsedStatement` — the heavy lifting
   - Plus `PARSER_NAME = "<broker>:<format>"` module-level constant
2. Append it to `_REGISTRY` in `format_detect.py`
3. Write tests in `tests/test_pdf_import.py` (or a sibling test file). The
   reference PDF goes to repo root, gitignored, and tests skip if missing.
4. The frontend widget needs no change — it auto-detects via the registry.

## Tests

[`tests/test_pdf_import.py`](../../tests/test_pdf_import.py) — 8 tests:

- parser extracts 11 holdings from the LGT reference PDF
- market-value total within OCR tolerance (Marvell expected to be off)
- Sandoz spot-check (qty/prices/date exact)
- `to_transactions` mapping shape
- API dry-run returns preview without DB writes
- Full import writes 9+ transactions then short-circuits on second call
- 404 for unknown portfolio
- 400 for non-LGT valid-PDF

Tests skip with `requires_lgt_pdf` when the reference PDF is absent — CI
doesn't have it; local dev has it; both pass.

## Gotchas

- **Use `extract_words`, not `extract_text`.** The text-mode loses x positions,
  which the parser relies on heavily for OCR-resilient column extraction.
  → fix: every new parser should follow the same `_cluster_rows()` +
  x-bound pattern instead of regexing `extract_text()` output.
- **`_DATE_RE.fullmatch` (not `findall`).** Findall on the joined block text
  returns dates in mixed order across columns. Match each token individually
  so we can use the token's x position to bucket entry vs current.
- **`_parse_decimal` is OCR-tolerant by design.** Don't add new substitutions
  blindly — every `X→Y` turns weirdness into bogus numbers somewhere. The
  current set (A→0, O→0, l/I→1) was tuned against the actual statements.
- **Cash positions are extracted but NOT mapped to transactions yet.**
  `to_transactions(stmt)` only reads `stmt.holdings`. Cash needs deposit/
  withdrawal logic + currency reconciliation that doesn't exist.
- **Idempotency relies on `file_hash`**, which is `sha256(file_bytes)`. Even
  re-saving the same PDF in a different viewer changes byte content, which
  changes the hash, which would re-import. If you need stable dedup across
  re-saves, add a content-based key (e.g. statement_date + customer +
  holdings count).
- **Pages 1-5 are skipped.** They contain customer header + performance
  history, not positions. The parser only walks pages with an "Aktien"
  table header (or Konten/Callgelder for cash).
- **The 11/11 → 9 transactions gap** is intentional: holdings without a
  parseable entry date are SKIPPED at the `to_transactions` boundary, not
  silently filled in with the statement date. Don't relax this — entry
  dates determine FIFO/LIFO holding-period buckets and tax outcomes.
