import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type Snapshot, type Transaction } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import EmptyPortfolio from '../components/EmptyPortfolio'
import Sparkline from '../components/charts/Sparkline'
import { fmtMoney, fmtPct, pnlSign } from '../lib/format'

/**
 * Parqet/Wrapped-style storyboard for a single calendar year. Pure
 * derivation from snapshots + tx-log + realized — no new API routes.
 *
 * Sections (top → bottom, single scrollable page):
 *   1. Hero — total return, end-of-year value, deposits/withdrawals
 *   2. Best & worst month
 *   3. Best week
 *   4. Top mover (largest absolute realized P&L per symbol)
 *   5. Activity counters (transactions, dividends placeholder)
 *
 * Routes: `/year/:year`. Defaults to the current year if `:year` is missing.
 */
export default function YearInReview() {
  const { activeId } = useActivePortfolio()
  const params = useParams()
  const nav = useNavigate()
  const year = Number(params.year ?? new Date().getFullYear())
  const yearStart = `${year}-01-01`
  const yearEnd   = `${year}-12-31`

  const snaps = useQuery({
    queryKey: ['snapshots', activeId],
    queryFn: () => api.listSnapshots(activeId!),
    enabled: activeId != null,
  })
  const txs = useQuery({
    queryKey: ['transactions', activeId, 'all'],
    queryFn: () => api.listTransactions(activeId!, { limit: 5000 }),
    enabled: activeId != null,
  })
  const realized = useQuery({
    queryKey: ['realized', activeId, 'fifo', year],
    queryFn: () => api.realized(activeId!, { method: 'fifo', year }),
    enabled: activeId != null,
  })

  if (activeId == null) return <EmptyPortfolio />

  const snapsInYear = useMemo(() => {
    if (!snaps.data) return [] as Snapshot[]
    return snaps.data.snapshots.filter(s => s.date >= yearStart && s.date <= yearEnd)
  }, [snaps.data, yearStart, yearEnd])
  const txsInYear = useMemo(() => {
    if (!txs.data) return [] as Transaction[]
    return txs.data.filter(t => t.executed_at.slice(0, 10) >= yearStart
                             && t.executed_at.slice(0, 10) <= yearEnd)
  }, [txs.data, yearStart, yearEnd])

  const yearSparkline = useMemo(() =>
    snapsInYear.map(s => ({ time: s.date, close: s.total_value })),
    [snapsInYear])

  const heroStats = useMemo(() => computeHero(snapsInYear), [snapsInYear])
  const bestMonth = useMemo(() => bestPeriod(snapsInYear, 'month'), [snapsInYear])
  const worstMonth = useMemo(() => worstPeriod(snapsInYear, 'month'), [snapsInYear])
  const bestWeek = useMemo(() => bestPeriod(snapsInYear, 'week'), [snapsInYear])
  const topRealized = useMemo(() => {
    if (!realized.data) return null
    const entries = Object.entries(realized.data.by_symbol)
      .map(([sym, pnl]) => [sym, Number(pnl)] as [string, number])
      .filter(([, n]) => Number.isFinite(n) && n !== 0)
      .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))
    return entries[0] ?? null
  }, [realized.data])

  const isLoading = snaps.isLoading || txs.isLoading || realized.isLoading
  const hasData = snapsInYear.length >= 2

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>
            Year in review
          </p>
          <h1 className="text-4xl font-bold" style={{ color: 'var(--text-primary)' }}>{year}</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button" className="btn-ghost px-2 py-1 text-sm"
            onClick={() => nav(`/year/${year - 1}`)}
          >
            ← {year - 1}
          </button>
          <button
            type="button" className="btn-ghost px-2 py-1 text-sm"
            onClick={() => nav(`/year/${year + 1}`)}
          >
            {year + 1} →
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <div className="skeleton h-72" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="skeleton h-40" />
            <div className="skeleton h-40" />
          </div>
        </div>
      ) : !hasData ? (
        <div
          className="card text-sm text-center"
          style={{ color: 'var(--text-tertiary)' }}
        >
          Not enough snapshots in {year} to assemble a review. Generate
          snapshots on the <Link to="/" style={{ color: 'var(--accent)' }}>Dashboard</Link> first
          (the backfill covers the last 365 days).
        </div>
      ) : (
        <>
          <HeroBlock stats={heroStats} sparkline={yearSparkline} year={year} />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <PeriodBlock title="Best month" period={bestMonth} tone="gain" />
            <PeriodBlock title="Worst month" period={worstMonth} tone="loss" />
          </div>

          <PeriodBlock title="Best week" period={bestWeek} tone="gain" wide />

          {topRealized && (
            <div className="card">
              <p className="text-xs uppercase tracking-wide mb-1"
                 style={{ color: 'var(--text-tertiary)' }}>
                Top realized P&L
              </p>
              <div className="flex items-baseline justify-between flex-wrap gap-3">
                <Link
                  to={`/asset/${encodeURIComponent(topRealized[0])}/stock`}
                  className="text-3xl font-bold"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {topRealized[0]}
                </Link>
                <span
                  className="text-3xl font-bold tabular-nums"
                  style={{ color: topRealized[1] >= 0 ? 'var(--gain)' : 'var(--loss)' }}
                >
                  {pnlSign(topRealized[1])}{fmtMoney(topRealized[1])}
                </span>
              </div>
            </div>
          )}

          <div className="card">
            <p className="text-xs uppercase tracking-wide mb-3"
               style={{ color: 'var(--text-tertiary)' }}>
              Activity
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Stat label="Transactions" value={String(txsInYear.length)} />
              <Stat label="Buys"
                    value={String(txsInYear.filter(t => t.action === 'buy').length)} />
              <Stat label="Sells"
                    value={String(txsInYear.filter(t => t.action === 'sell').length)} />
              <Stat label="Realized matches"
                    value={String(realized.data?.match_count ?? 0)} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// -----------------------------------------------------------------------------

type HeroStats = {
  startValue: number
  endValue: number
  totalReturn: number
  totalReturnPct: number
}

function computeHero(snaps: Snapshot[]): HeroStats {
  if (snaps.length === 0) {
    return { startValue: 0, endValue: 0, totalReturn: 0, totalReturnPct: 0 }
  }
  const first = snaps[0]
  const last = snaps[snaps.length - 1]
  const useBase = first.total_value_base != null && last.total_value_base != null
  const a = Number(useBase ? first.total_value_base : first.total_value)
  const b = Number(useBase ? last.total_value_base : last.total_value)
  return {
    startValue: a,
    endValue: b,
    totalReturn: b - a,
    totalReturnPct: a > 0 ? (b - a) / a : 0,
  }
}

type PeriodResult = {
  label: string         // e.g. "March 2026" or "Mar 03 → Mar 09"
  startDate: string
  endDate: string
  startValue: number
  endValue: number
  pct: number
} | null

function bestPeriod(snaps: Snapshot[], grain: 'month' | 'week'): PeriodResult {
  return extremePeriod(snaps, grain, true)
}
function worstPeriod(snaps: Snapshot[], grain: 'month' | 'week'): PeriodResult {
  return extremePeriod(snaps, grain, false)
}

function extremePeriod(snaps: Snapshot[], grain: 'month' | 'week', best: boolean): PeriodResult {
  if (snaps.length < 2) return null
  // Bucket snapshots into periods, then compute first→last delta per bucket.
  const buckets = new Map<string, Snapshot[]>()
  for (const s of snaps) {
    const key = grain === 'month' ? s.date.slice(0, 7) : isoWeekKey(s.date)
    const arr = buckets.get(key) ?? []
    arr.push(s)
    buckets.set(key, arr)
  }
  let pick: PeriodResult = null
  for (const arr of buckets.values()) {
    if (arr.length < 2) continue
    const a = arr[0]
    const b = arr[arr.length - 1]
    const useBase = a.total_value_base != null && b.total_value_base != null
    const av = Number(useBase ? a.total_value_base : a.total_value)
    const bv = Number(useBase ? b.total_value_base : b.total_value)
    if (av <= 0) continue
    const pct = (bv - av) / av
    if (pick == null || (best ? pct > pick.pct : pct < pick.pct)) {
      pick = {
        label: grain === 'month'
          ? new Date(a.date).toLocaleString('en-US', { month: 'long', year: 'numeric' })
          : `${a.date} → ${b.date}`,
        startDate: a.date,
        endDate: b.date,
        startValue: av,
        endValue: bv,
        pct,
      }
    }
  }
  return pick
}

function isoWeekKey(iso: string): string {
  // Group by ISO week (Monday-start). Cheap implementation: pick the Monday
  // of the week and use it as a stable bucket key.
  const d = new Date(iso)
  const day = d.getUTCDay()
  const mondayOffset = (day + 6) % 7 // 0=Mon, ... 6=Sun
  d.setUTCDate(d.getUTCDate() - mondayOffset)
  return d.toISOString().slice(0, 10)
}

function HeroBlock({
  stats, sparkline, year,
}: {
  stats: HeroStats
  sparkline: { time: string; close: string }[]
  year: number
}) {
  const tone = stats.totalReturn >= 0 ? 'gain' : 'loss'
  return (
    <section
      className="card relative overflow-hidden"
      style={{ minHeight: 240 }}
    >
      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <Sparkline points={sparkline} height={240} width={1200} />
      </div>
      <div className="relative">
        <p className="text-xs uppercase tracking-wide mb-2"
           style={{ color: 'var(--text-tertiary)' }}>
          {year} total return
        </p>
        <p
          className="text-6xl font-bold tabular-nums leading-none"
          style={{ color: `var(--${tone})` }}
        >
          {pnlSign(stats.totalReturnPct)}{fmtPct(stats.totalReturnPct)}
        </p>
        <p
          className="mt-3 text-2xl tabular-nums"
          style={{ color: `var(--${tone})` }}
        >
          {pnlSign(stats.totalReturn)}{fmtMoney(stats.totalReturn)}
        </p>
        <p className="mt-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
          {fmtMoney(stats.startValue)} → {fmtMoney(stats.endValue)}
        </p>
      </div>
    </section>
  )
}

function PeriodBlock({
  title, period, wide,
}: { title: string; period: PeriodResult; tone: 'gain' | 'loss'; wide?: boolean }) {
  if (period == null) {
    return (
      <div className="card text-sm" style={{ color: 'var(--text-tertiary)' }}>
        <p className="text-xs uppercase tracking-wide mb-2">{title}</p>
        — not enough snapshots
      </div>
    )
  }
  const colorTone = period.pct >= 0 ? 'gain' : 'loss'
  return (
    <div className={`card ${wide ? '' : ''}`}>
      <p className="text-xs uppercase tracking-wide mb-1"
         style={{ color: 'var(--text-tertiary)' }}>
        {title}
      </p>
      <p className="text-lg font-medium" style={{ color: 'var(--text-primary)' }}>
        {period.label}
      </p>
      <p
        className="text-4xl font-bold tabular-nums mt-2"
        style={{ color: `var(--${colorTone})` }}
      >
        {pnlSign(period.pct)}{fmtPct(period.pct)}
      </p>
      <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
        {fmtMoney(period.startValue)} → {fmtMoney(period.endValue)}
      </p>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase" style={{ color: 'var(--text-tertiary)' }}>
        {label}
      </div>
      <div className="text-2xl font-bold tabular-nums mt-1"
           style={{ color: 'var(--text-primary)' }}>
        {value}
      </div>
    </div>
  )
}
