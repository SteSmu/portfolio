import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type PeriodCode, type Snapshot } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { fmtMoney, fmtPct, fmtQty, pnlSign } from '../lib/format'
import EmptyPortfolio from '../components/EmptyPortfolio'
import EquityCurve from '../components/charts/EquityCurve'
import Sparkline from '../components/charts/Sparkline'
import PeriodSelector, { type Period, periodStart } from '../components/PeriodSelector'
import PeriodCard from '../components/PeriodCard'
import BenchmarkPicker from '../components/BenchmarkPicker'
import BenchmarkSyncBanner from '../components/BenchmarkSyncBanner'
import { useBenchmark } from '../state/benchmark'
import { useBenchmarkOverlay } from '../lib/benchmark'

const HERO_PERIODS: Array<{ code: PeriodCode; label: string }> = [
  { code: '1D',  label: '1T'  },
  { code: '1W',  label: '7T'  },
  { code: '1M',  label: '1M'  },
  { code: '3M',  label: '3M'  },
  { code: 'YTD', label: 'YTD' },
  { code: '1Y',  label: '1J'  },
]

export default function Dashboard() {
  const { activeId } = useActivePortfolio()
  const qc = useQueryClient()

  // Period selector now only drives the equity-curve window. The hero KPI
  // cards always show all six periods at once — that's the point of the
  // redesign.
  const [chartPeriod, setChartPeriod] = useState<Period>('3M')
  const chartStart = useMemo(() => periodStart(chartPeriod), [chartPeriod])
  const { selected: benchmarkSel } = useBenchmark()

  const summary = useQuery({
    queryKey: ['perf-summary', activeId],
    queryFn: () => api.performanceSummary(activeId!),
    enabled: activeId != null,
  })
  const periods = useQuery({
    queryKey: ['perf-periods', activeId],
    queryFn: () => api.performancePeriods(activeId!),
    enabled: activeId != null,
  })
  const holdings = useQuery({
    queryKey: ['holdings', activeId],
    queryFn: () => api.listHoldings(activeId!),
    enabled: activeId != null,
  })
  const snaps = useQuery({
    queryKey: ['snapshots', activeId],
    queryFn: () => api.listSnapshots(activeId!),
    enabled: activeId != null,
  })
  const sparks = useQuery({
    queryKey: ['sparklines', activeId],
    queryFn: () => api.holdingSparklines(activeId!, 30),
    enabled: activeId != null,
  })

  const generateSnapshots = useMutation({
    mutationFn: () => api.generateSnapshots(activeId!, 365),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['snapshots', activeId] })
      qc.invalidateQueries({ queryKey: ['perf-summary', activeId] })
      qc.invalidateQueries({ queryKey: ['perf-periods', activeId] })
    },
  })

  // Hooks must be called in the same order every render — keep them ABOVE
  // the early-return for the no-portfolio state.
  const visibleSnaps = useMemo(() => {
    if (!snaps.data) return []
    if (!chartStart) return snaps.data.snapshots
    return snaps.data.snapshots.filter(s => s.date >= chartStart)
  }, [snaps.data, chartStart])
  const benchmarkOverlay = useBenchmarkOverlay(benchmarkSel, visibleSnaps)

  if (activeId == null) return <EmptyPortfolio />

  // Latest snapshot with a real value — backfill rows that pre-date the
  // candle history get total_value=null and would otherwise dash the KPI.
  const latest = snaps.data?.snapshots.filter(s => s.total_value != null).at(-1)

  // Prefer FX-converted total_value_base when available; fall back to FX-naive
  // total_value with a "mixed currencies" caveat. The snapshot job emits
  // total_value_base = null when at least one currency bucket has no rate path
  // for that day — surfacing the caveat reminds the user to run `pt sync fx`.
  const baseCcy = (periods.data?.base_currency)
                  ?? (latest?.metadata?.base_currency as string | undefined)
                  ?? 'EUR'
  const baseAvailable = latest?.total_value_base != null
  const totalValue = latest
    ? Number(baseAvailable ? latest.total_value_base : latest.total_value)
    : null
  const costBasis  = latest ? Number(latest.total_cost_basis) : null
  const unrealized = latest && latest.unrealized_pnl != null ? Number(latest.unrealized_pnl) : null
  const realized   = summary.data ? Number(summary.data.realized_pnl) : null

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
        Dashboard
      </h1>

      {/* Hero — one big portfolio-value card + six period cards stacked below */}
      <section className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <div className="card lg:col-span-1">
          <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>
            {baseAvailable ? `Portfolio value (${baseCcy})` : 'Portfolio value (mixed)'}
          </div>
          {snaps.isLoading ? (
            <div className="skeleton h-9 w-40 mt-2" />
          ) : (
            <div
              className="text-3xl font-bold mt-1 tabular-nums"
              style={{ color: 'var(--text-primary)' }}
            >
              {totalValue != null ? fmtMoney(totalValue) : '—'}
            </div>
          )}
          {!baseAvailable && latest != null && (
            <div className="text-[11px] mt-1" style={{ color: 'var(--loss)' }}
                 title="mixed currencies — run `pt sync fx`">
              ⚠ mixed currencies — run <code>pt sync fx</code>
            </div>
          )}
          <dl className="mt-3 space-y-1 text-sm">
            <div className="flex justify-between">
              <dt style={{ color: 'var(--text-tertiary)' }}>Cost basis</dt>
              <dd className="tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                {costBasis != null ? fmtMoney(costBasis) : '—'}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt style={{ color: 'var(--text-tertiary)' }}>Unrealized</dt>
              <dd
                className="tabular-nums"
                style={{
                  color: tone(unrealized) === 'gain' ? 'var(--gain)'
                       : tone(unrealized) === 'loss' ? 'var(--loss)'
                       : 'var(--text-secondary)',
                }}
              >
                {unrealized != null ? fmtMoney(unrealized) : '—'}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt style={{ color: 'var(--text-tertiary)' }}>Realized</dt>
              <dd
                className="tabular-nums"
                style={{
                  color: tone(realized) === 'gain' ? 'var(--gain)'
                       : tone(realized) === 'loss' ? 'var(--loss)'
                       : 'var(--text-secondary)',
                }}
              >
                {realized != null ? fmtMoney(realized) : '—'}
              </dd>
            </div>
          </dl>
        </div>

        <div className="lg:col-span-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {HERO_PERIODS.map(p => {
            const data = periods.data?.periods?.[p.code] ?? null
            const sparkline = data
              ? sliceSeries(snaps.data?.snapshots ?? [], data.from, data.to, baseAvailable)
              : []
            return (
              <PeriodCard
                key={p.code}
                code={p.code}
                label={p.label}
                data={data}
                sparkline={sparkline}
                currency={periods.data?.base_currency ?? baseCcy}
                loading={periods.isLoading || snaps.isLoading}
              />
            )
          })}
        </div>
      </section>

      {/* Equity curve */}
      <section className="card">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
              Equity curve
            </h2>
            <BenchmarkPicker />
            <PeriodSelector value={chartPeriod} onChange={setChartPeriod} showCustomPicker />
          </div>
          {snaps.data && snaps.data.snapshots.length > 0 && (
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              {snaps.data.snapshots.length} snapshots ·{' '}
              {snaps.data.snapshots[0].date} → {snaps.data.snapshots.at(-1)?.date}
            </span>
          )}
        </div>
        {benchmarkSel != null
          && benchmarkOverlay
          && benchmarkOverlay.series.length === 0
          && visibleSnaps.length >= 2 && (
          <BenchmarkSyncBanner
            symbol={benchmarkSel.symbol}
            assetType={benchmarkSel.asset_type}
          />
        )}
        {snaps.isLoading ? (
          <div className="skeleton h-72" />
        ) : visibleSnaps.length >= 2 ? (
          <EquityCurve snapshots={visibleSnaps} height={300} benchmark={benchmarkOverlay} />
        ) : (
          <NoSnapshots
            onGenerate={() => generateSnapshots.mutate()}
            loading={generateSnapshots.isPending}
            error={generateSnapshots.error?.message}
          />
        )}
      </section>

      {/* Top movers + Top holdings + Recent activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TopMoversCard holdings={holdings.data ?? []} loading={holdings.isLoading} />
        <TopHoldingsCard
          holdings={holdings.data ?? []}
          loading={holdings.isLoading}
          sparklines={sparks.data?.series ?? {}}
        />
        <ActivityCard summary={summary.data} loading={summary.isLoading} />
      </div>
    </div>
  )
}

// -----------------------------------------------------------------------------

function tone(v: number | null | undefined): 'gain' | 'loss' | undefined {
  if (v == null) return undefined
  if (v > 0) return 'gain'
  if (v < 0) return 'loss'
  return undefined
}

/**
 * Slice the snapshot series to `[fromIso, toIso]` and project each row to a
 * `[date, value]` pair using FX-converted totals when both endpoints have
 * them — same rule as `pickEquitySeries`. Used by `<PeriodCard>` for its
 * inline sparkline.
 */
function sliceSeries(
  snaps: Snapshot[],
  fromIso: string,
  toIso: string,
  preferBase: boolean,
): Array<[string, number]> {
  const out: Array<[string, number]> = []
  for (const s of snaps) {
    if (s.date < fromIso || s.date > toIso) continue
    if (s.total_value == null) continue
    const useBase = preferBase && s.total_value_base != null
    const v = Number(useBase ? s.total_value_base : s.total_value)
    if (!Number.isFinite(v) || v <= 0) continue
    out.push([s.date, v])
  }
  return out
}

function NoSnapshots({
  onGenerate, loading, error,
}: { onGenerate: () => void; loading: boolean; error?: string }) {
  return (
    <div
      className="rounded-lg p-8 flex flex-col items-center justify-center text-center gap-3"
      style={{
        border: '1px dashed var(--border-base)',
        color: 'var(--text-secondary)',
        minHeight: 240,
      }}
    >
      <div className="text-4xl">📈</div>
      <p className="max-w-md text-sm">
        No snapshots yet. Generate the daily portfolio history (last 365 days)
        to see the equity curve and the time-series metrics on the
        Performance page.
      </p>
      <button onClick={onGenerate} disabled={loading} className="btn-primary">
        {loading ? 'Generating…' : 'Generate snapshots (365d)'}
      </button>
      {error && (
        <p className="text-xs" style={{ color: 'var(--loss)' }}>
          {error}
        </p>
      )}
    </div>
  )
}

function TopMoversCard({
  holdings, loading,
}: { holdings: { symbol: string; asset_type: string; unrealized_pnl_pct?: number | null }[]; loading: boolean }) {
  const movers = holdings
    .filter(h => h.unrealized_pnl_pct != null)
    .map(h => ({
      symbol: h.symbol,
      asset_type: h.asset_type,
      pct: h.unrealized_pnl_pct as number,
    }))
    .sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct))
    .slice(0, 5)

  return (
    <div className="card">
      <h2 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
        Top movers
      </h2>
      {loading ? (
        <div className="skeleton h-40" />
      ) : movers.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
          no priced positions yet
        </p>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {movers.map(m => {
            const up = m.pct >= 0
            return (
              <li key={`${m.symbol}-${m.asset_type}`} className="flex items-center justify-between">
                <Link
                  to={`/asset/${encodeURIComponent(m.symbol)}/${m.asset_type}`}
                  className="font-medium"
                  style={{ color: 'var(--text-primary)' }}
                >
                  <span style={{ color: up ? 'var(--gain)' : 'var(--loss)' }}>
                    {up ? '▲' : '▼'}
                  </span>{' '}
                  {m.symbol}
                </Link>
                <span
                  className="tabular-nums"
                  style={{ color: up ? 'var(--gain)' : 'var(--loss)' }}
                >
                  {pnlSign(m.pct)}{fmtPct(m.pct)}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function TopHoldingsCard({
  holdings, sparklines, loading,
}: {
  holdings: { symbol: string; asset_type: string; quantity: string; total_cost: string; market_value?: string | null }[]
  sparklines: Record<string, Array<{ time: string; close: string }>>
  loading: boolean
}) {
  const top = holdings
    .slice()
    .sort((a, b) => Number(b.market_value ?? b.total_cost) - Number(a.market_value ?? a.total_cost))
    .slice(0, 5)

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
          Top holdings
        </h2>
        <Link to="/holdings" className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          view all →
        </Link>
      </div>
      {loading ? (
        <div className="skeleton h-40" />
      ) : top.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
          no holdings yet — import a PDF or add a transaction
        </p>
      ) : (
        <ul className="space-y-2 text-sm">
          {top.map(h => (
            <li
              key={`${h.symbol}-${h.asset_type}`}
              className="flex items-center justify-between gap-2"
            >
              <Link
                to={`/asset/${encodeURIComponent(h.symbol)}/${h.asset_type}`}
                className="font-medium shrink-0"
                style={{ color: 'var(--text-primary)' }}
              >
                {h.symbol}
              </Link>
              <div className="flex-1 mx-2 max-w-[120px]">
                <Sparkline points={sparklines[h.symbol] ?? []} height={20} />
              </div>
              <span className="tabular-nums" style={{ color: 'var(--text-secondary)' }}>
                {fmtQty(h.quantity)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ActivityCard({
  summary, loading,
}: {
  summary?: { tx_count: number; open_lot_count: number; match_count: number }
  loading: boolean
}) {
  return (
    <div className="card">
      <h2 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
        Activity
      </h2>
      {loading ? (
        <div className="skeleton h-32" />
      ) : !summary ? (
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>—</p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
          <dt style={{ color: 'var(--text-secondary)' }}>Transactions</dt>
          <dd className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
            {summary.tx_count}
          </dd>
          <dt style={{ color: 'var(--text-secondary)' }}>Open lots</dt>
          <dd className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
            {summary.open_lot_count}
          </dd>
          <dt style={{ color: 'var(--text-secondary)' }}>Realized matches</dt>
          <dd className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
            {summary.match_count}
          </dd>
        </dl>
      )}
    </div>
  )
}
