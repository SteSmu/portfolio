// Display helpers — accept string-encoded Decimals from the API and render them.
// We deliberately keep math out of the frontend; the backend is the source of truth.

export function fmtMoney(value: string | number | null | undefined,
                         currency = '', places = 2): string {
  if (value == null) return '-'
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n)) return '-'
  const s = n.toLocaleString('de-DE', { minimumFractionDigits: places, maximumFractionDigits: places })
  return currency ? `${s} ${currency}` : s
}

export function fmtQty(value: string | number | null | undefined, places = 4): string {
  if (value == null) return '-'
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n)) return '-'
  return n.toLocaleString('de-DE', { maximumFractionDigits: places })
}

export function fmtPct(ratio: number, places = 2): string {
  if (!Number.isFinite(ratio)) return '-'
  return `${(ratio * 100).toFixed(places)}%`
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '-'
  return d.toISOString().slice(0, 10)
}

export function pnlClass(value: string | number | null | undefined): string {
  if (value == null) return 'flat'
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n) || n === 0) return 'flat'
  return n > 0 ? 'gain' : 'loss'
}

export function pnlSign(value: string | number): string {
  const n = typeof value === 'string' ? Number(value) : value
  return n > 0 ? '+' : ''
}
