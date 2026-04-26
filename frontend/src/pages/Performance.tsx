import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { useActivePortfolio } from '../state/portfolio'
import { fmtDate, fmtMoney, fmtPct, fmtPrice, fmtQty, pnlClass, pnlSign } from '../lib/format'
import EmptyPortfolio from '../components/EmptyPortfolio'
import EquityCurve from '../components/charts/EquityCurve'
import DrawdownChart from '../components/charts/DrawdownChart'
import PeriodSelector, { type Period, periodStart } from '../components/PeriodSelector'
import BenchmarkPicker from '../components/BenchmarkPicker'
import { useBenchmark } from '../state/benchmark'
import { useBenchmarkOverlay } from '../lib/benchmark'

const METHODS = ['fifo', 'lifo', 'average'] as const
type Method = (typeof METHODS)[number]

export default function Performance() {
  const { activeId } = useActivePortfolio()
  const [method, setMethod] = useState<Method>('fifo')
  const [year, setYear] = useState<string>('')
  const [period, setPeriod] = useState<Period>('1Y')
  const start = useMemo(() => periodStart(period), [period])

  const summary = useQuery({
    queryKey: ['perf-summary', activeId, method, start],
    queryFn: () => api.performanceSummary(activeId!, method),
    enabled: activeId != null,
  })
  const cb = useQuery({
    queryKey: ['cost-basis', activeId, method],
    queryFn: () => api.costBasis(activeId!, method),
    enabled: activeId != null,
  })
  const realized = useQuery({
    queryKey: ['realized', activeId, method, year],
    queryFn: () => api.realized(activeId!, { method, year: year ? Number(year) : undefined }),
    enabled: activeId != null,
  })
  const snaps = useQuery({
    queryKey: ['snapshots', activeId],
    queryFn: () => api.listSnapshots(activeId!),
    enabled: activeId != null,
  })

  if (activeId == null) return <EmptyPortfolio />

  const visibleSnaps = useMemo(() => {
    if (!snaps.data) return []
    if (!start) return snaps.data.snapshots
    return snaps.data.snapshots.filter(s => s.date >= start)
  }, [snaps.data, start])
  const { selected: benchmarkSel } = useBenchmark()
  const benchmarkOverlay = useBenchmarkOverlay(benchmarkSel, visibleSnaps)

  const ts = summary.data?.timeseries ?? null

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          Performance
        </h1>
        <div className="flex items-center gap-3 flex-wrap">
          <PeriodSelector value={period} onChange={setPeriod} />
          <div>
            <label className="text-xs mr-2" style={{ color: 'var(--text-tertiary)' }}>
              Method
            </label>
            <select
              className="input"
              value={method}
              onChange={e => setMethod(e.target.value as Method)}
            >
              {METHODS.map(m => <option key={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs mr-2" style={{ color: 'var(--text-tertiary)' }}>
              Year (realized)
            </label>
            <input
              className="input w-24" placeholder="all"
              value={year}
              onChange={e => setYear(e.target.value.replace(/\D/g, ''))}
            />
          </div>
        </div>
      </div>

      {/* Time-series KPI cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MetricCard
          title="Time-Weighted Return"
          subtitle="period · annualized"
          loading={summary.isLoading}
          missingHint={!ts ? 'needs snapshots' : null}
          rows={ts ? [
            ['Period TWR',     formatPct(ts.twr_period),     toneFromPct(ts.twr_period)],
            ['Annualized TWR', formatPct(ts.twr_annualized), toneFromPct(ts.twr_annualized)],
          ] : []}
        />
        <MetricCard
          title="Money-Weighted Return"
          subtitle="XIRR (your cash-flows)"
          loading={summary.isLoading}
          missingHint={!ts ? 'needs snapshots' : null}
          rows={ts ? [
            ['MWR (annualized)', formatPctOrNa(ts.mwr), toneFromPctOrNa(ts.mwr)],
          ] : []}
        />
        <MetricCard
          title="Risk profile"
          subtitle="vola · DD · Sharpe · Calmar"
          loading={summary.isLoading}
          missingHint={!ts ? 'needs snapshots' : null}
          rows={ts ? [
            ['Volatility (annualized)', formatPct(ts.volatility),     undefined],
            ['Max drawdown',            formatPct(ts.max_drawdown),   'loss'],
            ['Sharpe',                  formatRatio(ts.sharpe),       toneFromNumber(ts.sharpe)],
            ['Calmar',                  formatRatio(ts.calmar),       toneFromNumber(ts.calmar)],
          ] : []}
        />
      </div>

      {/* Equity curve + Drawdown stack */}
      <section className="card">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
              Equity & drawdown
            </h2>
            {ts && (
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                {ts.snapshot_count} snapshots · {ts.from} → {ts.to}
              </p>
            )}
          </div>
          <BenchmarkPicker />
        </div>
        {snaps.isLoading ? (
          <div className="skeleton h-72" />
        ) : visibleSnaps.length >= 2 ? (
          <div className="space-y-3">
            <EquityCurve snapshots={visibleSnaps} height={260} benchmark={benchmarkOverlay} />
            <DrawdownChart snapshots={visibleSnaps} height={140} />
          </div>
        ) : (
          <div
            className="rounded-lg p-8 text-center text-sm"
            style={{
              border: '1px dashed var(--border-base)',
              color: 'var(--text-tertiary)',
            }}
          >
            No snapshots in this range — switch to ALL or generate more on the
            Dashboard.
          </div>
        )}
      </section>

      {/* Realized summary */}
      {realized.data && (
        <div className="card">
          <h2 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            Realized P&L
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <Stat label="Total" value={fmtMoney(realized.data.total)} pnl={realized.data.total} />
            <Stat label="Short-term (<1y)"
                  value={fmtMoney(realized.data.by_holding_period.short)}
                  pnl={realized.data.by_holding_period.short} />
            <Stat label="Long-term (≥1y)"
                  value={fmtMoney(realized.data.by_holding_period.long)}
                  pnl={realized.data.by_holding_period.long} />
            <Stat label="Matches" value={String(realized.data.match_count)} />
          </div>
          {Object.keys(realized.data.by_symbol).length > 0 && (
            <div>
              <h3 className="text-xs uppercase mb-2" style={{ color: 'var(--text-tertiary)' }}>
                By symbol
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {Object.entries(realized.data.by_symbol)
                  .sort(([, a], [, b]) => Number(b) - Number(a))
                  .map(([sym, pnl]) => (
                    <div key={sym} className="flex justify-between px-3 py-1.5 rounded"
                         style={{ backgroundColor: 'var(--bg-elev-hi)' }}>
                      <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{sym}</span>
                      <span className={`tabular-nums ${pnlClass(pnl)}`}>{fmtMoney(pnl)}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Open lots */}
      {cb.data && cb.data.open_lots.length > 0 && (
        <div className="card overflow-x-auto">
          <h2 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            Open tax lots — {method}
          </h2>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase" style={{ color: 'var(--text-tertiary)' }}>
              <tr style={{ borderBottom: '1px solid var(--border-base)' }}>
                <th className="text-left py-2">TxID</th>
                <th className="text-left">Symbol</th>
                <th className="text-left">Acquired</th>
                <th className="text-right">Qty (rem)</th>
                <th className="text-right">Unit cost</th>
                <th className="text-right">Cost basis</th>
                <th className="text-right">Cur</th>
              </tr>
            </thead>
            <tbody>
              {cb.data.open_lots.map(l => (
                <tr key={l.transaction_id} style={{ borderBottom: '1px solid var(--border-base)' }}>
                  <td className="py-2" style={{ color: 'var(--text-tertiary)' }}>#{l.transaction_id}</td>
                  <td className="font-medium" style={{ color: 'var(--text-primary)' }}>{l.symbol}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{fmtDate(l.executed_at)}</td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>{fmtQty(l.quantity)}</td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>{fmtPrice(l.price)}</td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>{fmtMoney(l.cost_basis)}</td>
                  <td className="text-right" style={{ color: 'var(--text-tertiary)' }}>{l.currency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Realized matches */}
      {cb.data && cb.data.matches.length > 0 && (
        <div className="card overflow-x-auto">
          <h2 className="font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>
            Realized matches
          </h2>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase" style={{ color: 'var(--text-tertiary)' }}>
              <tr style={{ borderBottom: '1px solid var(--border-base)' }}>
                <th className="text-left py-2">Sell→Buy</th>
                <th className="text-left">Symbol</th>
                <th className="text-right">Sold qty</th>
                <th className="text-right">Cost</th>
                <th className="text-right">Proceeds</th>
                <th className="text-right">P&L</th>
                <th className="text-right">Days</th>
              </tr>
            </thead>
            <tbody>
              {cb.data.matches.map((m, i) => (
                <tr key={i} style={{ borderBottom: '1px solid var(--border-base)' }}>
                  <td className="py-2 tabular-nums" style={{ color: 'var(--text-tertiary)' }}>
                    #{m.sell_transaction_id}→#{m.lot_transaction_id}
                  </td>
                  <td className="font-medium" style={{ color: 'var(--text-primary)' }}>{m.symbol}</td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>{fmtQty(m.sold_quantity)}</td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>{fmtMoney(m.cost)}</td>
                  <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>{fmtMoney(m.proceeds)}</td>
                  <td className={`text-right tabular-nums font-medium ${pnlClass(m.realized_pnl)}`}>
                    {fmtMoney(m.realized_pnl)}
                  </td>
                  <td className="text-right" style={{ color: 'var(--text-tertiary)' }}>{m.holding_period_days}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// -----------------------------------------------------------------------------

type Tone = 'gain' | 'loss' | undefined

function toneFromPct(pct: string | null | undefined): Tone {
  if (pct == null) return undefined
  const n = Number(pct)
  if (!Number.isFinite(n)) return undefined
  return n > 0 ? 'gain' : n < 0 ? 'loss' : undefined
}
function toneFromPctOrNa(pct: string | null | undefined): Tone {
  return pct == null ? undefined : toneFromPct(pct)
}
function toneFromNumber(v: string | null | undefined): Tone {
  if (v == null) return undefined
  const n = Number(v)
  if (!Number.isFinite(n)) return undefined
  return n > 0 ? 'gain' : n < 0 ? 'loss' : undefined
}
function formatPct(s: string): string {
  const n = Number(s)
  if (!Number.isFinite(n)) return '—'
  return `${pnlSign(n)}${fmtPct(n)}`
}
function formatPctOrNa(s: string | null): string {
  if (s == null) return 'n/a'
  return formatPct(s)
}
function formatRatio(s: string): string {
  const n = Number(s)
  if (!Number.isFinite(n)) return '—'
  return `${pnlSign(n)}${n.toFixed(2)}`
}

function MetricCard({
  title, subtitle, rows, loading, missingHint,
}: {
  title: string
  subtitle: string
  rows: [string, string, Tone?][]
  loading: boolean
  missingHint?: string | null
}) {
  return (
    <div className="card">
      <h2 className="font-semibold" style={{ color: 'var(--text-primary)' }}>{title}</h2>
      <p className="text-xs mb-3" style={{ color: 'var(--text-tertiary)' }}>{subtitle}</p>
      {loading ? (
        <div className="skeleton h-20" />
      ) : missingHint ? (
        <p className="text-xs italic" style={{ color: 'var(--text-tertiary)' }}>
          {missingHint} — generate snapshots first
        </p>
      ) : (
        <dl className="space-y-1.5 text-sm">
          {rows.map(([label, value, tone]) => (
            <div key={label} className="flex justify-between gap-4">
              <dt style={{ color: 'var(--text-secondary)' }}>{label}</dt>
              <dd
                className="tabular-nums font-medium"
                style={{ color: tone ? `var(--${tone})` : 'var(--text-primary)' }}
              >
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

function Stat(props: { label: string; value: string; pnl?: string }) {
  return (
    <div>
      <div className="text-xs uppercase" style={{ color: 'var(--text-tertiary)' }}>
        {props.label}
      </div>
      <div className={`text-xl font-bold tabular-nums ${pnlClass(props.pnl)}`}>
        {props.value}
      </div>
    </div>
  )
}
