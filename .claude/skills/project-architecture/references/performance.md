# Performance engine

Decimal-only money math. The hardest invariant in the codebase: every test
in [`tests/test_perf_*`](../../tests/) is a regression gate against
hand-verified reference cases. **Don't change formulas without updating
the corresponding reference test.**

## Modules

| File | Purpose |
|--|--|
| [`pt/performance/money.py`](../../pt/performance/money.py) | `D()` cast, `quantize_money` (2 dp), `quantize_qty` (8 dp), `convert(amount, from, to, on_date)` via `public.market_meta` (direct → inverse → EUR-triangulation) |
| [`pt/performance/cost_basis.py`](../../pt/performance/cost_basis.py) | `compute_lots(transactions, method='fifo'\|'lifo'\|'average')` returns `(open_lots, matches)`. `realized_pnl_total` and `unrealized_pnl(lots, current_prices)` |
| [`pt/performance/twr.py`](../../pt/performance/twr.py) | `Snapshot(when, value, cash_flow)` + `twr(snapshots)` (geometric chaining) + `annualized_twr` |
| [`pt/performance/mwr.py`](../../pt/performance/mwr.py) | `xirr(flows)` via Newton-Raphson with bisection fallback. Excel-XIRR-compatible, day count = 365 |
| [`pt/performance/metrics.py`](../../pt/performance/metrics.py) | `daily_returns_from_snapshots`, `cagr`, `volatility`, `sharpe`, `sortino`, `max_drawdown`, `calmar` |

## Cost-basis methods

`compute_lots(transactions, method)` builds tax lots from buys and matches
sells against them in the order dictated by the method:

- **fifo** — oldest lots consumed first
- **lifo** — newest lots first
- **average** — all lots in the pool collapsed to one weighted-average lot
  before each sell

Per match, the result captures `realized_pnl = proceeds - cost`,
`holding_period_days`, and the per-unit cost basis used. Sell fees are
allocated pro-rata across matched lots.

Buys have their fees folded into the per-unit cost (`unit_cost = price +
fees / qty`), so cost-basis computations don't need to re-allocate them.

`dividend`, `split`, `fee`, `deposit`, `withdrawal` actions don't change
lots here (splits are a planned corporate-actions phase).

## TWR vs MWR

- **TWR** (`twr.py`) removes cash-flow timing — what a buy-and-hold investor
  would have seen. Use for benchmark comparisons and fund-vs-portfolio.
  Formula per sub-period: `r_i = (V_i - CF_i) / V_{i-1} - 1`. Total =
  `∏(1 + r_i) - 1`.
- **MWR / XIRR** (`mwr.py`) gives the IRR on dated cash flows — what you
  actually earned given when you put money in. Sign convention: deposits/
  buys negative, sells/withdrawals/final value positive. Use for "my real
  return".

Both are needed; the UI plans to surface both side by side.

## XIRR algorithm

1. Newton-Raphson with `guess=0.10`, `MAX_NEWTON_ITER=100`, tolerance `1e-9`.
2. If Newton diverges or steps into `r ≤ -1`, fall back to bisection in
   `[-0.999, 1e6]` (200 iterations, tolerance `1e-12`).
3. Day count is `(d_i - d_0).days / 365.0` — calendar days. **Leap years
   are calendar-aware**: 2008-01-01 → 2008-03-01 is 60 days, not 59.

## Reference tests

| Test file | Pinned to |
|--|--|
| [`test_perf_money.py`](../../tests/test_perf_money.py) | Decimal precision, FX direct/inverse/triangulation lookup |
| [`test_perf_cost_basis.py`](../../tests/test_perf_cost_basis.py) | Hand-computed FIFO/LIFO/Average examples + edge cases (sell exceeds holdings, zero-qty buy, cross-symbol pool isolation) |
| [`test_perf_twr.py`](../../tests/test_perf_twr.py) | Deposit/withdrawal cash-flow stripping (TWR invariant), annualization with leap years |
| [`test_perf_mwr.py`](../../tests/test_perf_mwr.py) | Microsoft Excel XIRR docs example (37.34%/yr); DCA + sell; sign-change requirement |
| [`test_perf_metrics.py`](../../tests/test_perf_metrics.py) | CAGR doubling-in-2y = √2 - 1, MaxDD picks deepest trough, Sharpe sign |

## CLI

```text
pt perf summary    --portfolio N [--method fifo|lifo|average]
pt perf cost-basis --portfolio N [--method ...] [--symbol X]
pt perf realized   --portfolio N [--method ...] [--year YYYY]

# snapshot generator (writes portfolio.portfolio_snapshots — feeds the
# equity curve / drawdown / TWR/MWR/Risk cards on the frontend)
pt sync snapshots [-p N] [--backfill DAYS] [--end-date YYYY-MM-DD] [--dry-run] [--json]
```

## Snapshot-fed time-series metrics

[`pt/jobs/snapshots.py`](../../pt/jobs/snapshots.py) writes one row per
(portfolio_id, snapshot_date) into `portfolio.portfolio_snapshots`:

- `total_value` — Σ qty × latest close at-or-before end-of-day from
  `public.candles` (FX-naive — caller of `_prices.latest_close_many`
  passes `as_of=end-of-day` so historical days are valued with prices
  that were actually known then)
- `total_cost_basis` — sum of `Lot.cost_basis` from `compute_lots(method='fifo')`
- `realized_pnl` — `realized_pnl_total(matches)` for the as-of point
- `unrealized_pnl` — `total_value - total_cost_basis` (or 0 if total_value <= 0)
- `holdings_count` — open positions
- `metadata` JSONB — per-`asset_type` and per-`currency` market-value
  breakdown for the allocation-over-time UI later

`/api/portfolios/{id}/performance/summary` now layers the time-series
math on top of those snapshots:

| Field | Computed via |
|--|--|
| `timeseries.twr_period` | `twr.twr(snapshots)` |
| `timeseries.twr_annualized` | `twr.annualized_twr(snapshots)` |
| `timeseries.mwr` | `mwr.xirr(tx_log_cashflows + (terminal_date, terminal_value))` — null if XIRR needs both signs and the tx log doesn't have any |
| `timeseries.max_drawdown` | `metrics.max_drawdown(daily_returns_from_snapshots(...))` |
| `timeseries.volatility` | `metrics.volatility(..., periods_per_year=365)` |
| `timeseries.sharpe` | `metrics.sharpe(..., periods_per_year=365)` |
| `timeseries.calmar` | `metrics.calmar(..., periods_per_year=365)` |

When fewer than 2 snapshots exist the whole `timeseries` block is null;
the frontend shows a "needs snapshots — run `pt sync snapshots
--backfill 365`" hint.

## Gotchas

- **Never `float` for money — use `Decimal`.** The hard rule. Internal stats
  math (Sharpe, Sortino, MaxDD) runs in float because numpy-style stats
  don't need Decimal precision, but the I/O surface is always Decimal.
  In particular, `D(0.1) == Decimal("0.1")` only because we cast through
  `str(float)`; a raw `Decimal(0.1)` would explode to `0.1000000000000…555`.
- **`compute_lots` re-sorts defensively** by `(executed_at, id)`. Don't rely
  on insertion order if you wire it into something new — pass any iterable.
- **Average-cost is destructive on the pool.** `_collapse_to_average` mutates
  the lot pool in place before each sell. If you need to inspect lots
  pre-collapse, deep-copy the input transactions before calling.
- **TWR is undefined when a sub-period starts with `V <= 0`.** Raises
  `ValueError`. Real portfolios shouldn't hit this; if a snapshot has
  cf == 0 and value == 0 we treat it as a no-op (skipping the period).
- **MWR fails fast on no sign change.** XIRR needs both positive and
  negative cash flows. The error message says so. A common bug:
  forgetting to make deposits negative.
- **Excel XIRR is calendar-day-based** — our reference test uses 2008
  dates because it's a leap year. If you re-derive the expected value with
  non-leap dates, expect a 0.15pp diff.
- **`metrics.calmar` annualizes via `cumulative ** (periods_per_year /
  N_returns)`.** That assumes the return series spans exactly N periods.
  If a caller passes mixed daily + monthly returns the result is
  meaningless — keep one cadence per call.
