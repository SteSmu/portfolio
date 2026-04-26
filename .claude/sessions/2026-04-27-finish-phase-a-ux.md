# Phase A finish — UX redesign close-out

**Date:** 2026-04-27
**Cortex session:** #5
**Plan:** #2 (`approved` → `completed`)
**Branch:** main
**Commits this session:** 44ea8c2 → a9fb163 → 723c67e → ef1da9b (year-in-review) → e08902e → b85cd16 → 60e48a6 → (CLAUDE.md update + this log)
**Tests:** 227 → 228 (added regression for TWR cash-flow)

## Scope

Closed the six handoff items + caught two follow-up bugs the user spotted in
the Performance chart.

## Items shipped

| # | Item | Files |
|---|---|---|
| 1 | News markers on AssetDetail price chart with toggle | `AssetPriceChart.tsx`, `AssetDetail.tsx` |
| 2 | Allocation-over-time stacked area | `AllocationOverTime.tsx`, `Allocation.tsx` |
| 3 | Skeleton-loader consistency | `AssetDetail.tsx`, `Settings.tsx` |
| 4 | BenchmarkPicker UX (refresh + sync banner) | `BenchmarkPicker.tsx`, `BenchmarkSyncBanner.tsx`, `Dashboard.tsx`, `Performance.tsx` |
| 5 | Year-in-Review storyboard at `/year/:year` | `YearInReview.tsx`, `App.tsx` |
| 6 | Mobile pass at 375px | (verification only — caught + fixed AllocationOverTime CSS-var colour bug inline) |
| 7 | **Bonus:** TWR/risk fed per-day external cash flows | `pt/api/routes/performance.py`, `tests/test_api_phase_a2.py` |
| 8 | **Bonus:** Equity / Drawdown charts prefer `total_value_base` + FX-converted cost basis | `lib/snapshotSeries.ts`, `EquityCurve.tsx`, `DrawdownChart.tsx` |

## Architecture refs absorbed

- `references/charts.md` — News-marker single-plugin reuse pattern, `pickEquitySeries`
  base-currency picking, `AllocationOverTime` colour-via-theme-only rule
- `references/frontend.md` — `YearInReview` page + `AllocationOverTime` /
  `BenchmarkSyncBanner` / `snapshotSeries.ts` building blocks
- `references/performance.md` — `_cash_flows_by_date` rationale + regression-test
  reference

## Auto-Learning Report

| Row | Value |
|---|---|
| **Tier** | T4 — multi-subsystem (frontend pages + charts + backend route + tests + 3 arch refs) + user pivoted twice (mobile pass → user-bug-report). |
| **Helper-skills-loaded** | `skill-engineering` (architecture-ref edits). `cli-engineering` skipped — no CLI source touched. Compliance: ✅ |
| **Actions Taken** | 1 plan completed, 8 implementation commits (incl. 2 bonus bug-fixes), 1 arch-ref absorption commit, 1 CLAUDE.md staleness fix, 1 session log. Prod stack rebuilt. |
| **CLI-Pattern-Extraction-Proof** | skipped: no CLI source modified. |
| **Artifact-Updates** | `frontend.md` +6 entries, `charts.md` +2 sections (equity-series picker, news markers, allocation-over-time), `performance.md` +1 paragraph (cash-flow accounting). `CLAUDE.md` test count + Phase A status refreshed. |
| **Staleness-Audit-Proof** | `grep` pinned `217 tests` + "Frontend Phase A done" stanza in CLAUDE.md → updated. `grep cash_flow=0` over `pt/` returned no remaining hookups. `grep total_value` over chart files returned only docstrings — confirmed. |
| **Gap-Detection** | New symbols introduced this session (`pickEquitySeries`, `_cash_flows_by_date`, `BenchmarkSyncBanner`, `AllocationOverTime`, `YearInReview`) all referenced from at least one arch ref. |
| **Test-Gate** | 228 pytest green incl. new `test_performance_summary_subtracts_buy_cashflows_from_twr`. `npx tsc --noEmit` clean. |
| **Parallel-Session-Gate** | skipped: no concurrent worktree session. |
| **Handoff-Sim** | Future cold-start agent reading `references/performance.md` learns *why* TWR was wrong + which test pins it; reading `references/charts.md` learns the base-currency picker pattern + the ECharts `var(--token)` gotcha. Both refs cite the helper module path. |
| **Memory-Migration** | skipped: no user-personal preferences surfaced. |
| **Verification-Loop** | Backend: pytest. Frontend: `tsc --noEmit` + dev preview at 375px on Dashboard / Holdings / Allocation / Performance / AssetDetail / Transactions / Settings / YearInReview. Prod: `docker compose up -d --build` + `curl /api/health` 200 with healthy DB. |
| **Pollution-Scan** | New ref content omits dates / commit SHAs / specific test counts (only "test_performance_summary_subtracts_buy_cashflows_from_twr" by name — that's a stable anchor, not a date-pinned narrative). |
| **Session Quality** | Strong. Two user-bug-catches handled in-flight without losing track of the 6-item backlog. Single avoidable hiccup: `preview_eval` selector by index hit the wrong element twice. |
| **Meta-Reflection (T4)** | See below. |

## Meta-Reflection (T4)

### What worked

- **Diagnosing root cause + adjacent class.** When the user surfaced the chart
  bug I expanded the diagnosis ("plus the underlying TWR problem") and fixed
  both classes — the user accepted the unprompted broader scope without
  pushback. Signal: when an obvious user-visible bug (chart axis) shares a
  root cause with a less-visible one (TWR consumer hookup), fixing both at
  once is welcome.
- **Test before regen.** Added the cash-flow regression test BEFORE shipping
  the fix means future TWR refactors can't silently re-break the wire-up.

### What to extend

- **Pattern (already absorbed into `references/performance.md`):** snapshot
  pipelines that expose `(value, cash_flow)` need a route-level test that
  feeds non-zero cash_flow — module-level tests of the math don't catch
  consumer hookup bugs. The added test pins the helper, not the math.
- **Pattern (already absorbed into `references/charts.md`):** equity-style
  charts in a multi-currency-capable system MUST pick base-currency series
  via a single helper, never read `total_value` directly. The
  `pickEquitySeries` helper makes this enforceable by code-review grep.

### What to avoid

- **`preview_eval` selectors by index.** Hit the wrong `<select>` twice
  (`selects[0]` was the portfolio picker, not the BenchmarkPicker). Local
  rule for future preview interaction: narrow by `aria-label` /
  `name` / option `text` content, never positional index. Not skill-worthy
  on its own (no general skill exists for preview-mcp interaction) — folded
  into this session log as a "won't do that again" note.

### What stays out of scope

- The cash-flow accounting fix only covers `buy / sell / transfer_in /
  transfer_out / dividend`. `fee` / `deposit` / `withdrawal` actions are
  rare in this tracker today — when they show up the same helper needs
  extending. Not a fix for this session; flagged in commit message.
- A full per-currency cost-basis FX-conversion in `pickEquitySeries` would
  require historical FX rates per currency bucket, not just the implicit
  `total_value_base / total_value` ratio. The ratio works for a
  single-currency portfolio (which the user has today); a mixed-currency
  edge case is acceptable until it bites.
