// Display helpers — accept string-encoded Decimals from the API and render them.
// We deliberately keep math out of the frontend; the backend is the source of truth.

/**
 * Money amount — always 2 decimals (locked for fiat consistency).
 * 1234.5 → "1.234,50", 1234 → "1.234,00".
 */
export function fmtMoney(value: string | number | null | undefined,
                         currency = ''): string {
  if (value == null) return '-'
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n)) return '-'
  const s = n.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return currency ? `${s} ${currency}` : s
}

/**
 * Per-unit price / cost basis — at least 2 decimals, up to maxPlaces, trailing
 * zeros stripped. 60000 → "60.000,00", 0.123456 → "0,1235", 180.50 → "180,50".
 */
export function fmtPrice(value: string | number | null | undefined,
                          maxPlaces = 4): string {
  if (value == null) return '-'
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n)) return '-'
  return n.toLocaleString('de-DE',
                           { minimumFractionDigits: 2, maximumFractionDigits: maxPlaces })
}

/**
 * Quantity — no minimum decimals, up to maxPlaces, trailing zeros stripped.
 * 8 → "8", 0.5 → "0,5", 0.12345678 → "0,12345678".
 */
export function fmtQty(value: string | number | null | undefined,
                        maxPlaces = 8): string {
  if (value == null) return '-'
  const n = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(n)) return '-'
  return n.toLocaleString('de-DE', { maximumFractionDigits: maxPlaces })
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
