import { fmtMoney, fmtPct, pnlSign } from '../lib/format'
import Sparkline from './charts/Sparkline'
import type { PerformancePeriod, PeriodCode } from '../api/client'

type Props = {
  code: PeriodCode
  /** Localised label shown in the card header (e.g. "1T", "1J"). Falls back
   *  to the raw code so the picker stays English-default. */
  label?: string
  /** Backend-supplied KPIs. `null` means the period has no usable baseline
   *  yet (fresh portfolio, not enough snapshots) — we render a dimmed
   *  placeholder. */
  data: PerformancePeriod | null
  /** Optional [date, value] series powering the inline sparkline; passed in
   *  by the parent because the snapshot list is shared across cards. */
  sparkline?: Array<[string, number]>
  /** Currency label for the absolute delta (e.g. "EUR"). Empty when the
   *  data is in `naive` mixed-currency mode. */
  currency: string
  loading?: boolean
}

/**
 * Six of these in a row power the redesigned Dashboard hero. Each shows the
 * cashflow-clean absolute change in base currency plus the period TWR — i.e.
 * a 16k buy on a 12k portfolio surfaces as ~0% rather than +130%, because
 * the math is done server-side in `/performance/periods`.
 *
 * The bar at the top of the card mirrors the colour of the change so the
 * "is it green or red?" answer reads from across the room.
 */
export default function PeriodCard({ code, label, data, sparkline, currency, loading }: Props) {
  const display = label ?? code
  const abs = data ? Number(data.abs_change) : null
  // simple_pct = abs_change / start_value — same numerator as the absolute
  // change. Pairing it with the absolute keeps the headline self-consistent
  // ("you made -€63, that's -0.24% of the period's opening value").
  const simplePctRaw = data ? Number(data.simple_pct) : null
  const simplePct = simplePctRaw != null && Number.isFinite(simplePctRaw) ? simplePctRaw : null
  // TWR is shown as a secondary metric — geometrically chained sub-period
  // returns. It diverges from simple% when the period contains big cash
  // flows; we surface it in the tooltip only when the gap is meaningful.
  const twrPctRaw = data?.twr_pct != null ? Number(data.twr_pct) : null
  const twrPct = twrPctRaw != null && Number.isFinite(twrPctRaw) ? twrPctRaw : null
  const tone = abs == null
    ? 'flat'
    : abs > 0 ? 'gain' : abs < 0 ? 'loss' : 'flat'

  const sparkPoints = (sparkline ?? []).map(([t, v]) => ({ time: t, close: String(v) }))

  const tooltipParts: string[] = []
  if (data) {
    tooltipParts.push(`${data.from} → ${data.to}`)
    if (twrPct != null && simplePct != null && Math.abs(twrPct - simplePct) > 0.001) {
      tooltipParts.push(
        `TWR (cashflow-bereinigt, geometrisch verkettet): ${pnlSign(twrPct)}${fmtPct(twrPct)}`,
      )
    }
    if (Number(data.cashflow) !== 0) {
      tooltipParts.push(`Cashflow ${currency || ''}: ${fmtMoney(data.cashflow)}`)
    }
    if (Number(data.realized) !== 0) {
      tooltipParts.push(`Realized: ${fmtMoney(data.realized)}`)
    }
    if (data.mode === 'naive') {
      tooltipParts.push('Mixed currency — totals in source currencies')
    }
  }

  return (
    <div
      className="card relative overflow-hidden"
      title={tooltipParts.length > 0 ? tooltipParts.join('\n') : undefined}
    >
      {/* tone bar (top edge) */}
      <div
        aria-hidden
        className="absolute left-0 right-0 top-0"
        style={{
          height: 3,
          backgroundColor:
            tone === 'gain' ? 'var(--gain)'
            : tone === 'loss' ? 'var(--loss)'
            : 'var(--border-base)',
        }}
      />
      <div className="text-xs uppercase tracking-wide" style={{ color: 'var(--text-tertiary)' }}>
        {display}
      </div>
      {loading ? (
        <div className="skeleton h-6 w-24 mt-2" />
      ) : data == null ? (
        <div className="text-sm mt-2" style={{ color: 'var(--text-tertiary)' }}>—</div>
      ) : (
        <>
          <div
            className="text-lg font-bold tabular-nums mt-1"
            style={{
              color:
                tone === 'gain' ? 'var(--gain)'
                : tone === 'loss' ? 'var(--loss)'
                : 'var(--text-primary)',
            }}
          >
            {abs != null ? `${pnlSign(abs)}${fmtMoney(abs)}` : '—'}
          </div>
          <div
            className="text-xs tabular-nums mt-0.5"
            style={{
              color:
                tone === 'gain' ? 'var(--gain)'
                : tone === 'loss' ? 'var(--loss)'
                : 'var(--text-secondary)',
            }}
          >
            {simplePct != null ? `${pnlSign(simplePct)}${fmtPct(simplePct)}` : '—'}
          </div>
          {twrPct != null && simplePct != null && Math.abs(twrPct - simplePct) > 0.001 && (
            <div
              className="text-[10px] tabular-nums mt-0.5"
              style={{ color: 'var(--text-tertiary)' }}
              aria-label="Time-Weighted Return for the period"
            >
              TWR {pnlSign(twrPct)}{fmtPct(twrPct)}
            </div>
          )}
          {sparkPoints.length >= 2 && (
            <div className="mt-2">
              <Sparkline points={sparkPoints} height={22} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
