# Phase A finish — UX redesign close-out (2026-04-27)

Closed out the six items from `.claude/sessions/handoffs/2026-04-27-finish-phase-a-ux.md` plus one mid-session course correction. Cortex plan #2 marked completed.

## Shipped

| Item | Commit |
|--|--|
| News markers on AssetDetail price chart with toggle + click-through | `44ea8c2` |
| Allocation-over-time stacked-area tab (third view next to sunburst/donut) | `a9fb163` |
| Skeleton-loader consistency across Settings + AssetDetail news pane | `723c67e` |
| BenchmarkPicker `⟳` button + `BenchmarkSyncBanner` empty-state CTA | `723c67e` |
| Year-in-Review storyboard at `/year/:year` (Parqet/Wrapped style) | `024ceef` |
| AllocationOverTime palette fix (drop `var(--cat-N)` override) | `3a8f648` |
| Period-adaptive Dashboard hero deltas (course correction) | `08e6094` |
| Architecture refs absorb new patterns | `7bb01ea` |
| Drop unused `tone` prop on PeriodBlock to unblock prod `tsc -b` | `c676d5d` |

Pytest: **227 passed, 1 skipped** (unchanged from session start).
Frontend tsc and `tsc -b` both green after `c676d5d`.

## Course correction (mid-session)

User asked for Dashboard hero deltas to adapt to the active `PeriodSelector` rather than always showing 1d/7d/1Y. Resolution: keep 1d/7d as quick context, replace the third slot with the active period using a new `deltaPctSince(snaps, isoDate)` helper anchored to a calendar date instead of a numeric lookback. So YTD really starts on Jan 01, ALL anchors to the earliest snapshot, etc. Implementation extracted a shared `computeDelta` helper.

## Mobile pass (375px)

Walked Dashboard, Holdings (table + heatmap), Allocation (sunburst + donut + over-time), Performance, AssetDetail, Transactions, Settings, Year-in-Review. All pages render clean at 375px without horizontal overflow on body. Header nav wraps to 2 rows but stays legible — no burger menu needed. The only fix uncovered was the AllocationOverTime ECharts CSS-var bug (caught visually as default-grey area instead of categorical palette), already shipped in `3a8f648`.

## Architecture-ref absorption

- `frontend.md`: AllocationOverTime, BenchmarkSyncBanner, YearInReview added to the components/pages tables; AssetDetail row mentions the news toggle; BenchmarkPicker entry covers the new ⟳ refresh button.
- `charts.md`: AssetPriceChart wrapper section now documents the marker/price-line lifecycle (use `setMarkers` and `removePriceLine`, don't re-create primitives); new "Benchmark sync UX" section; new gotcha pinned: ECharts cannot resolve `var(--token)` on per-series colours — rely on the theme.color array (`--cat-1..8`) read by `lib/echarts.ts:readChartTokens`.

## Pending (needs user authorization)

- `git push` of `c676d5d` (and the four already-pushed prior commits — main is up-to-date through `7bb01ea` on the remote; `c676d5d` is local-only).
- `docker compose -f docker-compose.prod.yml up -d --build` to land the new pages on `:5174`. Initial attempt revealed the `tsc -b` strict-mode regression that `c676d5d` fixes; the rebuild after the fix was blocked by a "production deploy" permission prompt.

## Repo state

`commit-range` since handoff base `8d15ead`: 8 commits across frontend/src/{components/charts,components,pages} + .claude/skills/project-architecture/references. New components: `AllocationOverTime.tsx`, `BenchmarkSyncBanner.tsx`. New page: `YearInReview.tsx`. Modified: AssetPriceChart, AssetDetail, Allocation, Dashboard, Performance, Settings, Layout-adjacent state stayed untouched.
