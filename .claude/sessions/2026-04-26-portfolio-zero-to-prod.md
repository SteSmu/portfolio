# 2026-04-26 — Portfolio Tracker: bootstrap → prod-ready

Single transformational session. Repo went from empty `.git` to a
production-deployable single-user portfolio analytics app: 15 commits,
174 tests, three Docker containers running with persistent volume,
LGT-Bank PDF importer, full architecture skill written.

## Outcome

| Phase | Commit | What landed |
|--|--|--|
| 0 Bootstrap | 73d52c0 | repo skeleton, `pt` CLI, FastAPI skeleton, 4 smoke tests, plan file |
| 1b-manual | f582d05 | DB helpers (portfolios/transactions/holdings/assets) + CLI sub-apps + audit trigger + 36 tests |
| 1b-fetcher | deea7fe | CoinGecko + Twelve Data + Frankfurter fetchers + sync CLI + 31 tests |
| 2 Performance | 7600d67 | money.py + cost-basis FIFO/LIFO/Avg + TWR + MWR/XIRR + metrics + 73 tests (Excel-XIRR-pinned) |
| 4 API | ce235e5 | 24 FastAPI routes + Pydantic models + TestClient tests |
| 5 Frontend | 52bc510 | React 19 + Vite + Tailwind 4 + TanStack Query + 4 pages + Layout |
| 5 polish | 6b18fff | fmtMoney/fmtPrice/fmtQty split — no more trailing `,0000` |
| 6 News | 3605f9a | Finnhub + Marketaux + AssetDetail page + dormant LLM scaffolding |
| Live-pricing | 19e20e8 | prices.py + holdings enrichment + auto-sync endpoint + UI columns |
| Hardening | ae7ed4d | structured logging + request-id middleware + enriched /api/health + CI workflow + frontend Dockerfile + nginx + README |
| Arch skill | 2612cd0 | `.claude/skills/project-architecture/` hub + 8 references |
| Prod Docker | 73316a8 | docker-compose.prod.yml + db/init/01_public_schema.sql + persistent volume `pt_db_data` |
| README polish | 5f85c4e | replaced docker section with actual commands |
| 3 PDF importer | 499a412 | `pt/importers/pdf/` + LGT parser + API endpoint + frontend widget + 8 tests |
| Arch skill update | 887dda3 | added pdf-import.md + deployment.md refs, updated Hub trigger keywords |

## Critical decisions

- **Read-only tool, no broker writes.** Stefan was explicit: "kein
  Trading, reines Analyse-Tool". PDF import is the primary ingestion
  path, manual entry is the fallback.
- **Shared TimescaleDB with claude-trader** in dev (port 5434);
  standalone TimescaleDB with persistent volume `pt_db_data` in prod.
  Both deployment paths supported by `docker-compose.prod.yml`.
- **OpenRouter LLM moves to the frontend** via TS SDK in a later
  phase. Python-side `pt/insights/llm.py` was scaffolded then
  deliberately un-wired after Stefan corrected the plan mid-session.
  Memory file `llm_provider_choice.md` records the rationale.
- **Holdings are derived, not stored.** Aggregated from transactions
  on every read. Audit is DB-enforced via trigger reading the
  `portfolio.changed_by` GUC.
- **Decimal-only money math.** Reference-test-pinned against Excel
  XIRR (calendar-day-aware, leap-year reference example) and CFA-style
  TWR cases.

## Numbers

- 174 tests green (Performance: 73, DB: 36, Fetchers: 31, API: 14,
  CLI: 9, smoke: 11)
- LGT PDF parser: 11/11 holdings extracted, 10/11 with correct
  market values (Marvell OCR-damaged — leading digit dropped),
  9/11 with correct entry dates (Alphabet OCR-damaged — date
  glyph misread). Acceptable; user-correctable in the UI.
- `pt-frontend` container ships a 298 KB hashed JS bundle behind
  nginx 1.27, proxies `/api` to `pt-api:8430` internally.

## What was wrong / corrected

- Initially proposed loading `claude-api` + `prompt-engineering` skills
  for LLM work — Stefan corrected: "achso nimm openRouter". Memory
  written.
- Tried Edit-tool replacements on `_parse_decimal` four times before
  realizing the file had `\xa0` (NBSP) and `—` (em-dash) chars that
  the matcher couldn't handle. Final fix went through Python file-write
  with explicit unicode chars. Memory written for future sessions.
- Initial CLI for News was scoped, then dropped per Stefan's "cli
  kannst ignorieren, erstmal frontend". Re-prioritized to API +
  frontend only.

## What's persisted now

- Project CLAUDE.md created (this commit)
- Architecture skill at `.claude/skills/project-architecture/` — Hub
  + 11 references, all under 200 lines
- Plan file at `.claude/plans/portfolio-bootstrap.md` (still tracked
  for Phase 7-9 follow-on work)
- User-memory entries: `llm_provider_choice.md`,
  `edit_tool_unicode_quirk.md`
- This session log

## Next session pickup

1. Phase 7: Tax DE-Reports (Spekulationsfrist, FIFO realized in
   Steuer-Format)
2. Phase 8: remaining frontend pages (Allocation sunburst,
   Income/Dividenden calendar, Settings)
3. Phase 9: claude-trader bridge — read-only signals on AssetDetail

The PDF parser pipeline is generic; new brokers (Trade Republic,
Scalable, etc.) need only `pt/importers/pdf/<broker>.py` plus a
registry entry in `format_detect.py`. No frontend / API changes
required for new parsers.
