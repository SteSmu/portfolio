import { useEffect, useState } from 'react'
import type { Period } from '../components/PeriodSelector'

const STORAGE_KEY = 'pt:time-range'

/** A user-chosen window. `preset` covers the pill-button presets;
 *  `'CUSTOM'` switches the UI into manual `from`/`to` mode. */
export type TimeRange =
  | { kind: 'preset'; preset: Period }
  | { kind: 'custom'; from: string; to: string }

const DEFAULT: TimeRange = { kind: 'preset', preset: '3M' }

function read(): TimeRange {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT
    const parsed = JSON.parse(raw) as TimeRange
    if (parsed?.kind === 'preset' && typeof parsed.preset === 'string') {
      return { kind: 'preset', preset: parsed.preset as Period }
    }
    if (parsed?.kind === 'custom' && typeof parsed.from === 'string' && typeof parsed.to === 'string') {
      return { kind: 'custom', from: parsed.from, to: parsed.to }
    }
    return DEFAULT
  } catch {
    return DEFAULT
  }
}

function write(v: TimeRange) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(v))
  } catch {
    // private mode etc.
  }
}

// Tiny event bus mirrored on `useActivePortfolio` / `useBenchmark` so multiple
// PeriodSelectors / pages stay in sync without a Provider-tree.
const subs = new Set<(v: TimeRange) => void>()
function emit(v: TimeRange) { subs.forEach(fn => fn(v)) }

export function useTimeRange() {
  const [range, setRangeState] = useState<TimeRange>(read())

  useEffect(() => {
    const fn = (v: TimeRange) => setRangeState(v)
    subs.add(fn)
    return () => { subs.delete(fn) }
  }, [])

  function setRange(v: TimeRange) {
    write(v)
    emit(v)
    setRangeState(v)
  }

  return { range, setRange }
}

/**
 * Resolve a TimeRange to an inclusive `from`/`to` ISO date pair (`YYYY-MM-DD`).
 * Returns `null` for `from` when the preset is `ALL` (no lower bound).
 */
export function resolveRange(range: TimeRange, now: Date = new Date()): { from: string | null; to: string } {
  const todayIso = now.toISOString().slice(0, 10)
  if (range.kind === 'custom') {
    return { from: range.from, to: range.to }
  }
  const p = range.preset
  if (p === 'ALL') return { from: null, to: todayIso }
  const d = new Date(now)
  switch (p) {
    case '1W':  d.setDate(d.getDate() - 7); break
    case '1M':  d.setMonth(d.getMonth() - 1); break
    case '3M':  d.setMonth(d.getMonth() - 3); break
    case 'YTD': d.setMonth(0); d.setDate(1); break
    case '1Y':  d.setFullYear(d.getFullYear() - 1); break
  }
  return { from: d.toISOString().slice(0, 10), to: todayIso }
}
