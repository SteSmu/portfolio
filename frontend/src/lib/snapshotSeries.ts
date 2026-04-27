import type { Snapshot } from '../api/client'

export type ValueMode = 'base' | 'naive'

export type SeriesPair = {
  /** Whether the chart values are in the portfolio's base currency or the
   *  FX-naive sum across source currencies. */
  mode: ValueMode
  /** ISO-3 currency label, e.g. "EUR" — empty when no base currency is
   *  resolvable from snapshot metadata. */
  currency: string
  /** [date, value] pairs for the equity line. */
  values: Array<[string, number]>
  /** [date, value] pairs for the cost-basis line, FX-converted to the
   *  same basis as `values` via the per-snapshot total_value_base /
   *  total_value ratio. Falls back to raw total_cost_basis in 'naive' mode. */
  costs: Array<[string, number]>
}

/**
 * Choose the best value/cost series for charts that show the equity curve.
 *
 * - When every snapshot with a `total_value` also has `total_value_base`,
 *   returns base-currency values plus a per-day FX-converted cost basis
 *   (the ratio `total_value_base / total_value` is the implicit FX rate
 *   the snapshot job used; applying the same ratio to `total_cost_basis`
 *   keeps the two lines comparable).
 * - Otherwise returns the raw FX-naive series so charts still render —
 *   the parent should surface a "run `pt sync fx`" hint when `mode` is
 *   'naive' and the portfolio actually mixes currencies.
 *
 * Snapshots where the chosen field is null (couldn't price any holding,
 * or no FX rate path) are filtered out entirely so the chart starts at the
 * first dated point with real data instead of plotting a misleading zero
 * baseline. Mid-series gaps therefore become missing points rather than
 * dropped-to-zero spikes.
 */
export function pickEquitySeries(snapshots: Snapshot[]): SeriesPair {
  // Defence-in-depth: drop both null and stale-zero rows. Snapshots
  // written by the post-fix code use null for "couldn't price"; any
  // pre-existing zero row from legacy writes (open holdings priced as 0
  // because no candle existed at-or-before snapshot_date) would otherwise
  // pin the equity curve's left edge to zero and mask everything else.
  const priced = snapshots.filter(s => {
    if (s.total_value == null) return false
    const n = Number(s.total_value)
    return Number.isFinite(n) && n > 0
  })
  const allHaveBase = priced.length > 0
    && priced.every(s => s.total_value_base != null)

  if (allHaveBase) {
    const currency = (priced[0].metadata?.base_currency as string | undefined) ?? ''
    return {
      mode: 'base',
      currency,
      values: priced.map(s => [s.date, Number(s.total_value_base)]),
      costs: priced.map(s => {
        const tv = Number(s.total_value)
        const tvb = Number(s.total_value_base)
        if (!Number.isFinite(tv) || tv <= 0) return [s.date, Number(s.total_cost_basis)]
        const ratio = tvb / tv
        return [s.date, Number(s.total_cost_basis) * ratio]
      }),
    }
  }
  return {
    mode: 'naive',
    currency: '',
    values: priced.map(s => [s.date, Number(s.total_value)]),
    costs:  priced.map(s => [s.date, Number(s.total_cost_basis)]),
  }
}

/** Drawdown series in % from the running peak — `[date, ddPct]`. */
export function drawdownFromValues(values: Array<[string, number]>): Array<[string, number]> {
  let peak = 0
  const out: Array<[string, number]> = []
  for (const [d, v] of values) {
    if (!Number.isFinite(v) || v <= 0) continue
    if (v > peak) peak = v
    const dd = peak > 0 ? (v - peak) / peak * 100 : 0
    out.push([d, dd])
  }
  return out
}
