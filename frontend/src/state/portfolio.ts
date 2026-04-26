import { useEffect, useState } from 'react'

const STORAGE_KEY = 'pt:active_portfolio_id'

function read(): number | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  } catch {
    return null
  }
}

function write(id: number | null) {
  try {
    if (id == null) localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, String(id))
  } catch {
    // localStorage may be unavailable (private mode)
  }
}

// Tiny event-bus so multiple <PortfolioPicker> consumers stay in sync.
const subs = new Set<(id: number | null) => void>()
function emit(id: number | null) { subs.forEach(fn => fn(id)) }

export function useActivePortfolio() {
  const [activeId, setActiveId] = useState<number | null>(read())

  useEffect(() => {
    const fn = (id: number | null) => setActiveId(id)
    subs.add(fn)
    return () => { subs.delete(fn) }
  }, [])

  function setActive(id: number | null) {
    write(id)
    emit(id)
    setActiveId(id)
  }

  return { activeId, setActive }
}
