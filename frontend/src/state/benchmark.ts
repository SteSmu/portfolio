import { useEffect, useState } from 'react'

const STORAGE_KEY = 'pt:benchmark'

export type BenchmarkSel = { symbol: string; asset_type: string } | null

function read(): BenchmarkSel {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed.symbol === 'string' && typeof parsed.asset_type === 'string') {
      return { symbol: parsed.symbol, asset_type: parsed.asset_type }
    }
    return null
  } catch {
    return null
  }
}

function write(v: BenchmarkSel) {
  try {
    if (v == null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(v))
  } catch {
    // private-mode etc.
  }
}

// Tiny event-bus mirrored on `useActivePortfolio` so multiple pickers /
// consumers (Dashboard + Performance) stay in sync without context.
const subs = new Set<(v: BenchmarkSel) => void>()
function emit(v: BenchmarkSel) { subs.forEach(fn => fn(v)) }

export function useBenchmark() {
  const [selected, setSelected] = useState<BenchmarkSel>(read())

  useEffect(() => {
    const fn = (v: BenchmarkSel) => setSelected(v)
    subs.add(fn)
    return () => { subs.delete(fn) }
  }, [])

  function setBenchmark(v: BenchmarkSel) {
    write(v)
    emit(v)
    setSelected(v)
  }

  return { selected, setBenchmark }
}
