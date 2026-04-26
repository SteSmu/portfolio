import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { useBenchmark } from '../state/benchmark'

/**
 * Compact `<select>` of curated benchmarks used to overlay an index proxy
 * (S&P 500, MSCI World, ...) on top of the equity curve. Persists the
 * choice in localStorage under `pt:benchmark` via `useBenchmark()`.
 *
 * The picker stays usable even if the catalog API is briefly down — the
 * "none" option is always present. A trailing refresh button triggers a
 * one-year backfill of the currently-selected benchmark; consumers see
 * the new data once the candles query refetches.
 */
export default function BenchmarkPicker() {
  const qc = useQueryClient()
  const list = useQuery({
    queryKey: ['benchmarks'],
    queryFn: () => api.listBenchmarks(),
    staleTime: 5 * 60_000,
  })
  const { selected, setBenchmark } = useBenchmark()
  const value = selected ? `${selected.symbol}|${selected.asset_type}` : ''

  const sync = useMutation({
    mutationFn: () => api.syncBenchmark(selected!.symbol, 365),
    onSuccess: () => {
      if (selected) {
        qc.invalidateQueries({
          queryKey: ['benchmark-candles', selected.symbol, selected.asset_type],
        })
      }
    },
  })

  return (
    <div className="flex items-center gap-2">
      <label className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
        Benchmark
      </label>
      <select
        className="input"
        value={value}
        onChange={(e) => {
          const raw = e.target.value
          if (!raw) {
            setBenchmark(null)
            return
          }
          const [symbol, asset_type] = raw.split('|')
          setBenchmark({ symbol, asset_type })
        }}
        disabled={list.isLoading}
      >
        <option value="">none</option>
        {(list.data ?? []).map(b => (
          <option key={b.symbol} value={`${b.symbol}|${b.asset_type}`}>
            {b.display_name}
          </option>
        ))}
      </select>
      {selected && (
        <button
          type="button"
          className="btn-ghost px-2 py-1 text-xs"
          title={`Refresh ${selected.symbol} candles (last 365 days)`}
          aria-label={`Refresh ${selected.symbol} candles`}
          disabled={sync.isPending}
          onClick={() => sync.mutate()}
        >
          {sync.isPending ? '⟳…' : '⟳'}
        </button>
      )}
    </div>
  )
}
