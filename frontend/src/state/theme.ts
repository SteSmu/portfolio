import { useEffect, useState } from 'react'

export type Theme = 'dark' | 'light' | 'system'
export type ResolvedTheme = 'dark' | 'light'

const STORAGE_KEY = 'pt:theme'

function readPref(): Theme {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === 'dark' || raw === 'light' || raw === 'system') return raw
    return 'system'
  } catch {
    return 'system'
  }
}

function writePref(theme: Theme) {
  try { localStorage.setItem(STORAGE_KEY, theme) } catch { /* noop */ }
}

function systemPrefers(): ResolvedTheme {
  try {
    return window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

function resolve(theme: Theme): ResolvedTheme {
  return theme === 'system' ? systemPrefers() : theme
}

function apply(resolved: ResolvedTheme) {
  document.documentElement.dataset.theme = resolved
  // Notify ECharts wrappers etc. that the active theme changed.
  window.dispatchEvent(new CustomEvent('pt:theme-change', { detail: resolved }))
}

const subs = new Set<(t: Theme) => void>()
function emit(t: Theme) { subs.forEach(fn => fn(t)) }

// Apply once at module load so the initial paint matches the saved pref.
if (typeof document !== 'undefined') {
  apply(resolve(readPref()))
  // Track system changes when user picked "system".
  try {
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    mq.addEventListener('change', () => {
      if (readPref() === 'system') apply(resolve('system'))
    })
  } catch { /* noop */ }
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readPref())

  useEffect(() => {
    const fn = (t: Theme) => setThemeState(t)
    subs.add(fn)
    return () => { subs.delete(fn) }
  }, [])

  function setTheme(t: Theme) {
    writePref(t)
    apply(resolve(t))
    emit(t)
    setThemeState(t)
  }

  return { theme, resolved: resolve(theme), setTheme }
}
