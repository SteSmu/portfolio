import DateRangePicker from './DateRangePicker'
import { useTimeRange, resolveRange, type TimeRange } from '../state/timeRange'

export type Period = '1W' | '1M' | '3M' | 'YTD' | '1Y' | 'ALL' | 'CUSTOM'

const OPTIONS: Period[] = ['1W', '1M', '3M', 'YTD', '1Y', 'ALL', 'CUSTOM']

/**
 * Resolve a Period code to an inclusive `start` date string (`YYYY-MM-DD`)
 * relative to today. Returns `null` for `ALL` (no lower bound) and `null`
 * for `CUSTOM` — callers in CUSTOM mode should read `useTimeRange()` to
 * get both `from` and `to` instead. Backwards-compatible with legacy
 * call-sites that only know the preset list.
 */
export function periodStart(p: Period, now: Date = new Date()): string | null {
  if (p === 'ALL' || p === 'CUSTOM') return null
  const d = new Date(now)
  switch (p) {
    case '1W':  d.setDate(d.getDate() - 7); break
    case '1M':  d.setMonth(d.getMonth() - 1); break
    case '3M':  d.setMonth(d.getMonth() - 3); break
    case 'YTD': d.setMonth(0); d.setDate(1); break
    case '1Y':  d.setFullYear(d.getFullYear() - 1); break
  }
  return d.toISOString().slice(0, 10)
}

type Props = {
  value: Period
  onChange: (p: Period) => void
  className?: string
  /** When true and value === 'CUSTOM', renders an inline DateRangePicker
   *  bound to the global `useTimeRange()` hook. Pages that don't care
   *  about custom ranges can leave this off (default). */
  showCustomPicker?: boolean
}

export default function PeriodSelector({ value, onChange, className = '', showCustomPicker = false }: Props) {
  const { range, setRange } = useTimeRange()
  const customRange =
    range.kind === 'custom'
      ? { from: range.from, to: range.to }
      : (() => {
          // Sensible CUSTOM-mode default = YTD slice. Switching INTO custom
          // for the first time pre-fills with the current YTD window so the
          // user immediately sees data instead of an empty range.
          const r = resolveRange({ kind: 'preset', preset: 'YTD' })
          return { from: r.from ?? new Date().toISOString().slice(0, 10), to: r.to }
        })()

  return (
    <div className={`inline-flex items-center gap-2 flex-wrap ${className}`}>
      <div
        className="inline-flex rounded-md p-0.5 text-xs"
        style={{ backgroundColor: 'var(--bg-elev-hi)', border: '1px solid var(--border-base)' }}
        role="radiogroup"
        aria-label="Time period"
      >
        {OPTIONS.map(opt => {
          const active = opt === value
          return (
            <button
              key={opt}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => {
                onChange(opt)
                // Mirror the choice into the global TimeRange so other pages
                // pick it up. CUSTOM doesn't overwrite a previously-set
                // custom range; preset clicks always switch to preset mode.
                if (opt === 'CUSTOM') {
                  if (range.kind !== 'custom') {
                    setRange({ kind: 'custom', from: customRange.from, to: customRange.to })
                  }
                } else {
                  setRange({ kind: 'preset', preset: opt })
                }
              }}
              className="rounded px-2.5 py-1 font-medium transition-colors"
              style={{
                backgroundColor: active ? 'var(--accent)' : 'transparent',
                color: active ? '#ffffff' : 'var(--text-secondary)',
              }}
            >
              {opt}
            </button>
          )
        })}
      </div>
      {showCustomPicker && value === 'CUSTOM' && (
        <DateRangePicker
          from={customRange.from}
          to={customRange.to}
          onChange={({ from, to }) => setRange({ kind: 'custom', from, to } satisfies TimeRange)}
        />
      )}
    </div>
  )
}
