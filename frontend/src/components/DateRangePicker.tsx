import { useId } from 'react'

type Props = {
  from: string
  to: string
  onChange: (next: { from: string; to: string }) => void
  className?: string
}

/**
 * Two native `<input type="date">` controls separated by an arrow. Used as
 * the CUSTOM-mode tail of `<PeriodSelector>` and persisted via
 * `useTimeRange`. No external dep — keeps the bundle small and respects
 * the OS-native date picker (locale, keyboard nav, ARIA) for free.
 */
export default function DateRangePicker({ from, to, onChange, className = '' }: Props) {
  const idFrom = useId()
  const idTo = useId()
  // The browser blocks invalid swaps inside the <input>, but a parent
  // setting `from > to` programmatically should still self-correct on the
  // next change to keep the selector usable.
  return (
    <div
      className={`inline-flex items-center gap-2 ${className}`}
      role="group"
      aria-label="Custom date range"
    >
      <label htmlFor={idFrom} className="sr-only">From</label>
      <input
        id={idFrom}
        type="date"
        className="input text-xs py-1"
        value={from}
        max={to}
        onChange={e => onChange({ from: e.target.value, to })}
      />
      <span aria-hidden style={{ color: 'var(--text-tertiary)' }}>→</span>
      <label htmlFor={idTo} className="sr-only">To</label>
      <input
        id={idTo}
        type="date"
        className="input text-xs py-1"
        value={to}
        min={from}
        onChange={e => onChange({ from, to: e.target.value })}
      />
    </div>
  )
}
