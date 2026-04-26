# Session: PDF Importer Refinement + yfinance Fallback + Holdings Cost-Basis Fix

**Date:** 2026-04-26
**Tier:** T4 (transformational — 4 commits across 3 subsystems, new dependency, multiple new patterns)
**Branch:** main
**Commits:** `b54643c`, `01e8673`, `9ecbb09`, `27833b5`

## What changed

User imported a real LGT Bank Vermögensaufstellung PDF and asked to see the
current portfolio value. That single goal exposed four independent gaps in
the stack — each fixed in its own commit:

1. **`b54643c` — Holdings aggregation: transfer_in/out now contribute to cost basis.**
   `pt/db/holdings.py` SQL had `ELSE 0` for the cost_delta on `transfer_in` /
   `transfer_out` while `pt.performance.cost_basis` already treated them as
   buy/sell equivalents. Result: any portfolio populated solely via PDF
   imports showed `total_cost = 0` for every position. The two modules are
   now in sync; 4 regression-guard tests pin the invariants.

2. **`01e8673` — PDF importer: extract Bloomberg ticker as preferred symbol.**
   LGT statements carry the Bloomberg ticker (`AMZN UW`, `NOVN SE`,
   `AIR FP`) two rows below the ISIN in the same x-column. Previously the
   importer captured ISIN+name only, so transactions landed with
   `symbol='AMAZON.COM LNC'` — useless for Twelve Data quote lookups. New
   `_extract_bloomberg_ticker` scans token pairs `<TICKER 1-6 alpha>
   <2-letter exchange code>`. Tolerant to OCR lowercase-on-first-letter
   (`sDZ → SDZ`). `ParsedHolding.symbol` priority: ticker > ISIN > name.
   8 unit tests, plus an end-to-end PDF regression-guard pinning
   AMZN/AVGO/ANET/NOVN/SDZ/AIR.

3. **`9ecbb09` — Auto-prices: yfinance fallback for SIX listings + rate-limit recovery.**
   Twelve Data Free can't carry SIX Swiss listings (Pro plan only) and caps
   at 8 calls/min — 3 of 10 holdings (NOVN, ROG, SDZ) couldn't be priced.
   New `pt/data/yahoo.py` wraps `yfinance` as a fallback. Routing in
   `sync.py`: known SIX/EU tickers (`_YAHOO_SYMBOL_MAP`) skip TD entirely;
   US tickers stay TD primary with Yahoo on `TwelveDataError`. Candles
   persist with the bare ticker (`NOVN`) regardless of provider so the
   holdings join keys consistently. 10 unit tests + an online integration
   test gated on `YAHOO_ONLINE=1`.

4. **`27833b5` — LGT parser: OCR-recover dates + reject price-column fragments.**
   The Alphabet/GOOGL block exposed two pathologies that silently dropped
   a 30k+ EUR position: date `3't.01.2025` for `31.01.2025` (`'t→1`), and
   price column shred where `201.9400` got sliced into `20` (integer-only)
   + `r.9400` (rejected by `_parse_decimal`). New `_try_parse_date`
   applies letter-substitution recovery when strict regex fails. Price
   tokens now require a decimal point (real LGT prices are always 4dp).
   Plus a y-row guard: entry- and current-price must share a visual row
   so an FX-rate token from the next row doesn't survive as a bogus
   stock price. When entry_price is genuinely unrecoverable (Alphabet),
   `to_transactions` skips the row rather than fabricate data.
   6 new tests + GOOGL e2e regression-guard. **204 tests green.**

After all four landed, the user's portfolio shows 11 holdings, all priced,
~306k EUR market value, +107k EUR (+53.9%) unrealized.

## Auto-Learning Report

| Row | Content |
|---|---|
| **Tier** | T4 (4 commits, 3 subsystems edited: db/, importers/pdf/, data/, api/routes/, tests/) |
| **Helper-skills loaded** | `project-architecture-manager` (explicit user request), `testing` (test patterns for OCR-recovery + provider-fallback). `cli-engineering` skipped — no CLI source touched this session. `skill-engineering` skipped — only ref updates, no new skill. |
| **Actions Taken** | 4 src commits (holdings SQL, Bloomberg ticker extraction, yfinance fallback, OCR recovery); 6 architecture refs updated (SKILL.md, db.md, data-fetchers.md, pdf-import.md, pricing.md, deployment.md) — see Artifact-Updates row. |
| **CLI-Pattern-Extraction-Proof** | skipped: no CLI source in `pt/cli*.py` was touched. |
| **Artifact-Updates** | `SKILL.md`: data-fetchers count + provider-chain section + frontmatter keywords. `db.md`: cost_delta convention pinned to `cost_basis.py`, regression-guard. `data-fetchers.md`: yahoo.py module + provider-fallback-chain pattern + 2 new gotchas. `pdf-import.md`: symbol-priority ladder section + 4 new OCR pathologies in table + bloomberg_ticker field + skip>wrong-import gotcha + symbol-convention gotcha. `pricing.md`: provider-chain table + Yahoo symbol map. `deployment.md`: macOS Docker Compose `.env` quirk + yfinance dep note. |
| **Staleness-Audit-Proof** | All 6 refs read in full before edit. db.md line 47 (holdings.py description) was the gateway finding — its outdated phrasing led to the cost-basis bug being invisible. |
| **Gap-Detection** | New symbols introduced this session and pinned in refs: `bloomberg_ticker` field, `ticker` / `bloomberg_exchange` properties, `_extract_bloomberg_ticker`, `_try_parse_date`, `_recover_date_text`, `_YAHOO_SYMBOL_MAP`, `_yahoo_symbol`, `_fetch_stock_with_fallback`, `YahooFinanceError`, `_BLOOMBERG_EXCHANGE_CODES`. |
| **Test-Gate** | 204 passed, 1 skipped (online Yahoo integration). |
| **Parallel-Session-Gate** | N/A (single user, single repo). |
| **Handoff-Sim** | Reader entering with no memory of the session can answer "where is the symbol-priority ladder defined?" → `pdf-import.md` section "Symbol priority ladder". "How does auto-prices fall back?" → `pricing.md` provider-chain table + `data-fetchers.md` provider-fallback-chain section. "Why did `transfer_in.cost_delta=0` cause a bug?" → `db.md` holdings.py description + new gotcha. "What's the macOS docker compose gotcha?" → `deployment.md` last gotcha. |
| **Memory-Migration** | None — all learnings landed team-visible in refs (per priority ladder). No `~/.claude/...` memory writes this session. |
| **Verification-Loop** | Each ref updated → re-read by Edit-tool to confirm; final test run after all source commits = 204 green. End-to-end smoke: 11/11 holdings priced, all EUR totals match expected from PDF + market move. |
| **Pollution-Scan** | Refs intentionally pin SYMBOLS (function/file/field names) which is the contract surface — those are correct to pin. Refs avoid commit hashes, dates, and session-specific PR numbers (per skill rules). The session log here carries the dates+hashes; the refs do not. |
| **Session Quality** | High signal density. Each user pivot ("doch da steht der einstandskurs", "rechne das doch bitte zusammen", "prüfe nochmal in der PDF") surfaced a real gap that was then promoted into a regression-guard test + ref update. The user's "ja sauberer fix" was the trigger that turned a quick UPDATE-the-DB workaround into a proper importer-level extraction. |

## Patterns extracted (for future sessions)

1. **Cross-module semantic consistency.** When two modules share a domain
   convention (here: how `transfer_in` contributes to cost basis), drift
   between them is invisible until a portfolio populated solely through
   one path renders zeroes everywhere. `db.md` now pins this invariant.
2. **Provider-fallback chain pattern.** Primary → on specific error →
   secondary. Preserve the primary's error on the outcome row even when
   secondary succeeds, so the UI surfaces "got X via Y because primary
   said: Z" rather than a silent provider switch. Codified in
   `data-fetchers.md` and `pricing.md`.
3. **Layered OCR recovery.** Strict regex first, fall back to letter-
   substitution recovery on miss. `_try_parse_date` is the template;
   `_parse_decimal` already follows the same pattern for numbers.
4. **Skip > wrong-import.** When a critical field is unrecoverable, return
   `None` and let the user fill it in. Fabricating a value contaminates
   downstream stats — `pdf-import.md` carries this as a standalone gotcha.
5. **Symbol-priority ladder.** ticker > ISIN > name. New broker parsers
   must populate the ticker field whenever the source carries one,
   because price-feed providers key off tickers, not ISINs.
6. **macOS Docker Compose `.env` quirk.** Compose v2 may not auto-load
   `.env` on Mac. Source it into the shell before invoking compose.
   Codified in `deployment.md`.

## Status / next-up

User's stated UX backlog (Phase A):
- Light-mode toggle + color palette for asset types
- Allocation-Donut on Dashboard (Recharts)
- AssetDetail price chart with cost-basis line + tx markers
  (`lightweight-charts` already installed but unused)
- FX-converted EUR totals (Frankfurter ECB rates already wired in)

Not started this session — waiting on user go-ahead.
