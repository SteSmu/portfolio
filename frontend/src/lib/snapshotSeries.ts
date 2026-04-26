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
 * - When every visible snapshot has `total_value_base != null`, returns
 *   base-currency values plus a per-day FX-converted cost basis (the
 *   ratio `total_value_base / total_value` is the implicit FX rate the
 *   snapshot job used; applying the same ratio to `total_cost_basis`
 *   keeps the two lines comparable).
 * - Otherwise returns the raw FX-naive series so charts still render —
 *   the parent should surface a "run `pt sync fx`" hint when `mode` is
 *   'naive' and the portfolio actually mixes currencies.
 */
export function pickEquitySeries(snapshots: Snapshot[]): SeriesPair {
  const allHaveBase = snapshots.length > 0
    && snapshots.every(s => s.total_value_base != null)

  if (allHaveBase) {
    const currency = (snapshots[0].metadata?.base_currency as string | undefined) ?? ''
    return {
      mode: 'base',
      currency,
      values: snapshots.map(s => [s.date, Number(s.total_value_base)]),
      costs: snapshots.map(s => {
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
    values: snapshots.map(s => [s.date, Number(s.total_value)]),
    costs:  snapshots.map(s => [s.date, Number(s.total_cost_basis)]),
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
