import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { fmtMoney, fmtPct, fmtQty, pnlSign } from '../lib/format'
import EmptyPortfolio from '../components/EmptyPortfolio'
import EquityCurve from '../components/charts/EquityCurve'
import Sparkline from '../components/charts/Sparkline'
import PeriodSelector, { type Period, periodStart } from '../components/PeriodSelector'
import BenchmarkPicker from '../components/BenchmarkPicker'
import BenchmarkSyncBanner from '../components/BenchmarkSyncBanner'
import { useBenchmark } from '../state/benchmark'
import { useBenchmarkOverlay } from '../lib/benchmark'

export default function Dashboard() {
  const { activeId } = useActivePortfolio()
  const qc = useQueryClient()

  const [period, setPeriod] = useState<Period>('3M')
  const start = useMemo(() => periodStart(period), [period])
  const { selected: benchmarkSel } = useBenchmark()

  const summary = useQuery({
    queryKey: ['perf-summary', activeId],
    queryFn: () => api.performanceSummary(activeId!),
    enabled: activeId != null,
  })
  const holdings = useQuery({
    queryKey: ['holdings', activeId],
    queryFn: () => api.listHoldings(activeId!),
    enabled: activeId != null,
  })
  // Always pull the full series for delta computation; the chart slices what it shows.
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
    },
  })

  if (activeId == null) return <EmptyPortfolio />

  const latest = snaps.data?.snapshots.at(-1)
  const visibleSnaps = useMemo(() => {
    if (!snaps.data) return []
    if (!start) return snaps.data.snapshots
    return snaps.data.snapshots.filter(s => s.date >= start)
  }, [snaps.data, start])
  const benchmarkOverlay = useBenchmarkOverlay(benchmarkSel, visibleSnaps)

  // Prefer FX-converted total_value_base when available; fall back to FX-naive
  // total_value with a "mixed currencies" caveat. The snapshot job emits
  // total_value_base = null when at least one currency bucket has no rate path
  // for that day — surfacing the caveat reminds the user to run `pt sync fx`.
  const baseCcy = (latest?.metadata?.base_currency as string | undefined) ?? 'EUR'
  const baseAvailable = latest?.total_value_base != null
  const totalValue = latest
    ? Number(baseAvailable ? latest.total_value_base : latest.total_value)
    : null
  const costBasis  = latest ? Number(latest.total_cost_basis) : null
  const unrealized = latest ? Number(latest.unrealized_pnl) : null
  const realized   = summary.data ? Number(summary.data.realized_pnl) : null

  const heroDeltas = useMemo<[string, number | null][]>(() => {
    const snapsArr = snaps.data?.snapshots ?? []
    if (snapsArr.length === 0) return []
    const items: [string, number | null][] = []
    // 1d is always shown — the user wants to know "what did today do".
    items.push(['1d', deltaPct(snapsArr, 1, baseAvailable)])
    // Second slot mirrors the active PeriodSelector. For 1W that's just
    // 7d (no need to repeat); other periods get an anchored "since X"
    // calculation so YTD really starts on Jan 01, etc.
    if (period === '1W') {
      items.push(['7d', deltaPct(snapsArr, 7, baseAvailable)])
    } else {
      items.push(['7d', deltaPct(snapsArr, 7, baseAvailable)])
      items.push([period, deltaPctSince(snapsArr, start, baseAvailable)])
    }
    return items
  }, [snaps.data, period, start, baseAvailable])

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          Dashboard
        </h1>
        <PeriodSelector value={period} onChange={setPeriod} />
      </div>

      {/* Hero — primary KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard
          label={baseAvailable ? `Portfolio value (${baseCcy})` : 'Portfolio value (mixed)'}
          primary={totalValue != null ? fmtMoney(totalValue) : '—'}
          deltas={latest ? heroDeltas : []}
          loading={snaps.isLoading}
          caveat={!baseAvailable && latest != null
            ? 'mixed currencies — run `pt sync fx`'
            : undefined}
        />
        <KpiCard
          label="Cost basis"
          primary={costBasis != null ? fmtMoney(costBasis) : '—'}
          loading={summary.isLoading}
        />
        <KpiCard
          label="Unrealized P&L"
          primary={unrealized != null ? fmtMoney(unrealized) : '—'}
          tone={tone(unrealized)}
          loading={snaps.isLoading}
        />
        <KpiCard
          label="Realized P&L"
          primary={realized != null ? fmtMoney(realized) : '—'}
          tone={tone(realized)}
          loading={summary.isLoading}
        />
      </div>

      {/* Equity curve */}
      <section className="card">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
              Equity curve
            </h2>
            <BenchmarkPicker />
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

type DeltaSnap = { date: string; total_value: string; total_value_base: string | null }

function deltaPct(
  snaps: DeltaSnap[],
  lookbackDays: number,
  preferBase = false,
): number | null {
  if (snaps.length < 2) return null
  const last = snaps[snaps.length - 1]
  // Find a snapshot at-or-before (last.date - lookbackDays).
  const target = new Date(last.date)
  target.setDate(target.getDate() - lookbackDays)
  const targetIso = target.toISOString().slice(0, 10)
  return computeDelta(snaps, targetIso, last, preferBase)
}

/**
 * Same delta math as `deltaPct` but anchored to a calendar date instead of
 * a numeric lookback. Powers period-aware Hero deltas so e.g. YTD really
 * means "from Jan 01 of the current year" rather than "the last 365 days".
 *
 * `sinceIso = null` (PeriodSelector returns null for ALL) compares to the
 * very first snapshot in the series.
 */
function deltaPctSince(
  snaps: DeltaSnap[],
  sinceIso: string | null,
  preferBase = false,
): number | null {
  if (snaps.length < 2) return null
  const last = snaps[snaps.length - 1]
  // For ALL → anchor to the earliest snapshot so the user sees lifetime change.
  if (sinceIso == null) {
    return computeDelta(snaps, snaps[0].date, last, preferBase)
  }
  return computeDelta(snaps, sinceIso, last, preferBase)
}

function computeDelta(
  snaps: DeltaSnap[],
  baselineCutoffIso: string,
  last: DeltaSnap,
  preferBase: boolean,
): number | null {
  // Pick the snapshot at-or-before the cutoff (mirrors the ECharts
  // visibleSnaps slice: any snapshot >= start is "in the window", so the
  // first one in-window approximates the period's opening level).
  let baseline = snaps[0]
  for (let i = snaps.length - 1; i >= 0; i--) {
    if (snaps[i].date <= baselineCutoffIso) { baseline = snaps[i]; break }
  }
  // Use FX-converted values when both endpoints have them (apples-to-apples
  // across the lookback window). Otherwise fall back to FX-naive.
  const useBase = preferBase
                  && baseline.total_value_base != null
                  && last.total_value_base != null
  const a = Number(useBase ? baseline.total_value_base : baseline.total_value)
  const b = Number(useBase ? last.total_value_base : last.total_value)
  if (a <= 0) return null
  return (b - a) / a
}

function KpiCard({
  label, primary, deltas, tone, loading, caveat,
}: {
  label: string
  primary: string
  deltas?: [string, number | null][]
  tone?: 'gain' | 'loss'
  loading?: boolean
  caveat?: string
}) {
  return (
    <div className="card">
      <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>
        {label}
      </div>
      {loading ? (
        <div className="skeleton h-7 w-32 mt-2" />
      ) : (
        <div
          className="text-2xl font-bold mt-1 tabular-nums"
          style={{ color: tone ? `var(--${tone})` : 'var(--text-primary)' }}
        >
          {primary}
        </div>
      )}
      {caveat && !loading && (
        <div className="text-[11px] mt-1" style={{ color: 'var(--loss)' }} title={caveat}>
          ⚠ {caveat}
        </div>
      )}
      {deltas && deltas.length > 0 && !loading && (
        <div className="flex gap-3 mt-2 text-xs">
          {deltas.map(([k, v]) => (
            <span key={k}>
              <span style={{ color: 'var(--text-tertiary)' }}>{k}:</span>{' '}
              <span
                className="tabular-nums"
                style={{
                  color: v == null ? 'var(--text-tertiary)'
                       : v > 0 ? 'var(--gain)'
                       : v < 0 ? 'var(--loss)'
                       : 'var(--text-secondary)',
                }}
              >
                {v == null ? '—' : `${pnlSign(v)}${fmtPct(v)}`}
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
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
