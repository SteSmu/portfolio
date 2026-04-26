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
  "symbol": ParsedHolding.symbol  # priority: ticker > ISIN > name
  "asset_type": "stock"|"etf"|"crypto"|"bond"|"fund",
  "executed_at": entry_date at 00:00:00 UTC,
  "quantity": Decimal,
  "price": entry_price (Einstandskurs from the statement),
  "trade_currency": position currency,
  "fees": 0,                 # not extractable from statements
  "source": "pdf:lgt:vermoegensaufstellung",
  "source_doc_id": "{file_hash[:16]}:{ISIN or name}",
}
```

Holdings without an entry date or entry price are **skipped silently** —
ingesting half-data would produce wrong cost-basis math downstream.

### Symbol priority ladder

`ParsedHolding.symbol` resolves to the first non-empty of:

1. **Bare ticker** (e.g. `AMZN`, `NOVN`) — derived from `bloomberg_ticker`
   by stripping the exchange code. Twelve Data + Yahoo both key off the
   bare ticker, so this is the only form that makes auto-prices work
   without further mapping.
2. **ISIN** (e.g. `US0231351067`) — fallback when the parser can't
   capture a Bloomberg field.
3. **Cleaned company name** (e.g. `AMAZON.COM LNC`) — last resort.

`source_doc_id` uses ISIN-or-name (NOT ticker) so a re-import where the
parser previously fell back to ISIN/name and now extracts a ticker stays
idempotent — the dedup key is stable across parser improvements.

## LGT parser specifics

LGT Bank ships scanned PDFs whose OCR is fragile. The parser is
deliberately permissive — it extracts what it can, records anything
weird in `ParsedStatement.warnings`, never crashes on a single bad block.

### OCR pathologies the parser handles

| Symptom | Example (raw OCR) | Fix |
|--|--|--|
| Embedded space in ISIN | `cH001 2005267` for `CH0012005267` | Token-based extraction: try concatenating 1-4 adjacent tokens, validate `len==12 + ISO-country prefix + last digit` |
| Lowercase prefix on ISIN / ticker | `cH...`, `us...`, `sDZ` for `SDZ` | `.upper()` after concat / before validation |
| Letter-into-digit | `29'451.A3` for `29'451.03` | A→0, O→0, l/I→1 in `_parse_decimal` |
| Letter-into-digit in dates | `3't.01.2025` for `31.01.2025` | `_recover_date_text` applies same substitutions plus `'t→1`, retried after strict `_DATE_RE` fails |
| Stray comma after thousands sep | `26',655.31` for `26'655.31` | Strip both `'` and `,` (LGT never uses comma as decimal) |
| Hyphen as date separator | `11.06-2019` | Permissive `[.\-/]+` separator regex |
| Title broken | `Vermögensaufstellu ng` | Strip whitespace before format-detection match |
| Header tampering | `5tückzahl` (5 instead of S) | Permissive header regex |
| Qty + market value pushed to row above the CCY anchor (Sandoz, Roche, Airbus, Alphabet, Amazon, Broadcom, NVIDIA, Oracle) | various | Block construction merges up to 2 rows above (within 10px of anchor) |
| Full data row pushed above the CCY anchor (Sandoz pattern) | `50 Sandoz Group AG ... 12.9800` above `CHF` | Same merge-up-to-2 logic |
| Orphan-above row of NEXT holding sucked into current block | Roche orphan above Roche anchor pulled into Novartis block | Look-ahead: row immediately preceding any CCY anchor is skipped |
| Total/footer row picks up market value | Page-end Total row at x=600 | Hard-stop on `Total` / `Verwendete` / `Währung` first-tokens |
| Price column fragment (no decimal) | `20` (sliced from `201.9400` when the fractional half was OCR-shredded into `r.9400`) | Require `.` in the price token — real LGT prices are always 4dp |
| FX-rate bleed into empty entry-price column | `1.0430` (USD/EUR rate) surviving as a $1.04 stock price | y-row guard: entry- and current-price must share the same visual row (≤5px), otherwise drop the entry-side candidate |

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
- bloomberg_ticker (e.g. `AMZN UW`, `NOVN SE`) — extracted from the
  ISIN/Valor/Bloomberg/GICS column when an alpha+exchange-suffix pair sits
  on a single visual row. The `.ticker` property derives the bare ticker
  used as `transactions.symbol`.

### Unrecoverable losses

Some pathologies the parser cannot recover from. When entry_price OR
entry_date stays None, `to_transactions` skips the row rather than
fabricating cost-basis math:

| Loss | Example | What's missing |
|--|--|--|
| OCR-dropped leading digit | `1',940.98` instead of `11',940.98` | The leading `1` is gone — no way to know |
| Price split + half OCR-shredded | `r.9400` (half of `201.9400`, the `1` is lost in `r`) | The integer prefix can't be re-merged — `_parse_decimal` rejects `r.9400`, and the surviving `20` fragment fails the `.`-required price filter |

The parser surfaces these via `warnings` (the import-log keeps them);
the user adds the affected position via `pt tx add` or the Transactions
page. Skipping is a deliberate invariant: a wrong cost basis contaminates
all downstream P&L, FIFO/LIFO bucketing, and tax reporting — the cost of
"manually add 1 row" is far smaller than the cost of "audit and rebuild
performance numbers".

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
- **The N/N → N-K transactions gap** is intentional: holdings without a
  parseable entry date or entry price are SKIPPED at the `to_transactions`
  boundary, not silently filled in with the statement date or fabricated
  cost. Don't relax this — entry dates determine FIFO/LIFO holding-period
  buckets and tax outcomes; entry prices determine cost basis and unrealized
  P&L.
- **Skip > wrong-import.** When OCR mangles a field beyond recovery, return
  None and let the user add the row by hand. Inventing a value to fill the
  gap (statement-date for entry-date, current-price for entry-price, an FX
  rate that landed in the price column) silently contaminates downstream
  performance numbers — much harder to detect and fix later than 1 missing
  row that's flagged in `warnings`.
- **Symbol priority is ticker > ISIN > name.** New parsers MUST set
  `bloomberg_ticker` (or an analogous field) on `ParsedHolding` whenever
  the source carries a ticker — even bank-internal forms. Falling back to
  ISIN works for the holdings table but breaks Twelve Data / Yahoo lookups
  in `auto-prices`. The `.symbol` property handles the priority cascade.
