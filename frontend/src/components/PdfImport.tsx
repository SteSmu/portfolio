import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ImportPdfDryRun } from '../api/client'
import { fmtDate, fmtPrice, fmtQty } from '../lib/format'

export default function PdfImport({ portfolioId }: { portfolioId: number }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPdfDryRun | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const qc = useQueryClient()

  const dryRun = useMutation({
    mutationFn: (f: File) => api.importPdfDryRun(portfolioId, f),
    onSuccess: (r) => setPreview(r),
  })
  const commit = useMutation({
    mutationFn: (f: File) => api.importPdfCommit(portfolioId, f),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['holdings', portfolioId] })
      qc.invalidateQueries({ queryKey: ['transactions', portfolioId] })
      qc.invalidateQueries({ queryKey: ['perf-summary', portfolioId] })
      reset()
    },
  })

  function reset() {
    setFile(null)
    setPreview(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  function pickFile(f: File | null) {
    setFile(f)
    setPreview(null)
    if (f) dryRun.mutate(f)
  }

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div>
          <h2 className="font-semibold">Import broker statement (PDF)</h2>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
            Currently supported: LGT Bank Vermögensaufstellung. Drag in a PDF to preview;
            confirm to write transfer-in transactions.
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="text-xs file:mr-3 file:rounded file:border-0
                     file:px-3 file:py-1.5 file:text-sm
                     file:[background-color:var(--bg-elev-hi)]
                     file:[color:var(--text-primary)]
                     hover:file:[background-color:var(--bg-elev-hover)]"
          onChange={e => pickFile(e.target.files?.[0] ?? null)}
        />
      </div>

      {dryRun.isPending && (
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>parsing…</p>
      )}
      {dryRun.error && (
        <p className="loss text-sm">{(dryRun.error as Error).message}</p>
      )}

      {preview && (
        <div className="space-y-3">
          <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            <span className="font-medium" style={{ color: 'var(--text-primary)' }}>
              {preview.parser}
            </span>
            {' · '}{preview.customer}
            {' · '}{preview.statement_date}
            {' · '}{preview.base_currency}
            {' · '}<strong>{preview.holdings_parsed}</strong> holdings parsed
            {' · '}<strong>{preview.transactions_planned}</strong> transactions planned
            {preview.warnings.length > 0 && (
              <span className="loss">
                {' · '}{preview.warnings.length} warning(s)
              </span>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="uppercase" style={{ color: 'var(--text-tertiary)' }}>
                <tr style={{ borderBottom: '1px solid var(--border-base)' }}>
                  <th className="text-left py-1.5">Symbol</th>
                  <th className="text-left">Type</th>
                  <th className="text-right">Qty</th>
                  <th className="text-right">Price</th>
                  <th className="text-left">Cur</th>
                  <th className="text-left">Date</th>
                </tr>
              </thead>
              <tbody>
                {preview.transactions.map((t, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border-base)' }}>
                    <td className="py-1 font-medium" style={{ color: 'var(--text-primary)' }}>
                      {t.symbol}
                    </td>
                    <td style={{ color: 'var(--text-tertiary)' }}>{t.asset_type}</td>
                    <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
                      {fmtQty(t.quantity)}
                    </td>
                    <td className="text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>
                      {fmtPrice(t.price)}
                    </td>
                    <td style={{ color: 'var(--text-tertiary)' }}>{t.trade_currency}</td>
                    <td style={{ color: 'var(--text-tertiary)' }}>{fmtDate(t.executed_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {preview.warnings.length > 0 && (
            <details className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
              <summary className="cursor-pointer">Warnings</summary>
              <ul className="mt-1 space-y-1">
                {preview.warnings.map((w, i) => (
                  <li key={i} className="loss font-mono text-[11px]">{w}</li>
                ))}
              </ul>
            </details>
          )}

          <div className="flex items-center gap-2 pt-1">
            <button
              className="btn-primary"
              disabled={!file || commit.isPending}
              onClick={() => file && commit.mutate(file)}
            >
              {commit.isPending
                ? 'Importing…'
                : `Import ${preview.transactions_planned} transactions`}
            </button>
            <button className="btn-ghost" onClick={reset} disabled={commit.isPending}>
              Cancel
            </button>
          </div>

          {commit.error && (
            <p className="loss text-sm">{(commit.error as Error).message}</p>
          )}
          {commit.data && (
            <p className="gain text-sm">
              {commit.data.skipped_reason
                ? `Already imported (${commit.data.skipped_reason}).`
                : `Wrote ${commit.data.transactions_added} transaction(s).`}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
