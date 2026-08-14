/** Grey literature entering a multivocal review.
 *
 * Two ways in, and the difference matters. A retrieval this installation made
 * is imported by name from the listing — the same package the exporter writes,
 * assembled from the database it is imported into, so each source keeps the
 * keys that let the dataset view show the archived bytes later. A package file
 * is the path for a corpus from a co-reviewer or another installation, where
 * those keys do not exist and are honestly left empty.
 *
 * Three things this panel refuses to do:
 *
 * 1. **No engine dropdown.** The label comes from the package
 *    (`grey_service.engine_of`), because the runs record which engine actually
 *    answered and a hand-typed label could contradict them.
 * 2. **No credential fields.** Retrieval keys are read from the process
 *    environment, never the interface. Running a retrieval is a CLI operation;
 *    this panel imports what one produced.
 * 3. **No silent no-ops.** `incomplete` and `already_imported` are on screen
 *    before the button is pressed. Re-importing a scope counts every record as
 *    `already_present` and changes nothing, and silently doing nothing is
 *    worse than saying so.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'

import { getRetrievals, importGreyFromRetrieval, importGreyPackage } from '../api/client'
import type { GreyImportResult, Retrieval } from '../api/types'
import { reasonLabel } from '../utils/retrievalReasons'
import { Badge, Card, CardHeader } from './ui'

/** What the server said went wrong, not a sentence of our own.
 *
 * `parse_package` explains a rejected file precisely — including the command
 * that produces a valid one — and replacing that with "Import failed" would
 * throw away the only part of the message that tells a user what to do next.
 */
function errorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return 'The import failed. The server did not say why.'
}

function Count({ label, value, tone = 'text-ink' }: {
  label: string; value: number; tone?: string
}) {
  return (
    <div>
      <p className="text-ink-muted">{label}</p>
      <p className={`font-semibold ${tone}`}>{value}</p>
    </div>
  )
}

function RetrievalRow({ retrieval, onImport, busy }: {
  retrieval: Retrieval
  onImport: (scopeId: string) => void
  busy: boolean
}) {
  const { queries, engines, scope_id: scopeId } = retrieval
  return (
    <tr>
      <td className="py-2.5 pr-3 align-top">
        <div className="flex items-center gap-1.5 flex-wrap">
          <Badge label={retrieval.kind === 'batch' ? 'Batch' : 'Run'} variant="info" />
          {retrieval.incomplete && <Badge label="Incomplete" variant="uncertain" />}
          {retrieval.already_imported && <Badge label="Already imported" variant="neutral" />}
        </div>
        <p className="text-sm text-ink mt-1 break-words">
          {queries[0] ?? '(no query recorded)'}
          {queries.length > 1 && (
            <span className="text-ink-muted"> +{queries.length - 1} more</span>
          )}
        </p>
        {/* The id is shown but never typed: it is what makes the row citable
            in a methods section, and what `from-retrieval` resolves. */}
        <p className="text-xs text-ink-muted font-mono mt-0.5" title={scopeId}>
          {scopeId.slice(0, 12)}{scopeId.length > 12 ? '…' : ''}
        </p>
      </td>
      <td className="py-2.5 pr-3 align-top text-xs text-ink-light whitespace-nowrap">
        {retrieval.started_at_utc}
      </td>
      <td className="py-2.5 pr-3 align-top text-xs text-ink-light">
        {engines.join(', ')}
      </td>
      <td className="py-2.5 pr-3 align-top text-right text-sm text-ink">
        {retrieval.documents}
      </td>
      <td className="py-2.5 pr-3 align-top text-right text-xs text-ink-light">
        {retrieval.runs}
      </td>
      <td className="py-2.5 align-top text-right">
        <button
          className={retrieval.already_imported ? 'btn-secondary' : 'btn-primary'}
          disabled={busy}
          onClick={() => onImport(scopeId)}
        >
          {retrieval.already_imported ? 'Import again' : 'Import'}
        </button>
      </td>
    </tr>
  )
}

function ResultBlock({ result }: { result: GreyImportResult }) {
  const reasons = Object.entries(result.unretrievable_by_reason)
    .filter(([, n]) => n > 0)
    .sort(([, a], [, b]) => b - a)
  const reported = result.package_reported?.documents
  const disagrees = reported != null && reported !== result.total_in_package

  return (
    <div className="bg-green-50 border border-green-200 rounded-md p-3 text-sm">
      <p className="font-semibold text-include mb-1">
        Import complete — {result.engine}
        {result.scope && <span className="font-normal text-ink-light"> · {result.scope.kind} {result.scope.id}</span>}
      </p>
      {/* The four below add up to "In package", as on the BibTeX path. Showing
          all of them is the point: these are the PRISMA numbers. */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <Count label="In package" value={result.total_in_package} />
        <Count label="Imported unique" value={result.imported_unique} tone="text-include" />
        <Count label="Duplicates" value={result.imported_duplicates} tone="text-uncertain" />
        <Count label="Already in project" value={result.already_present} tone="text-ink-light" />
        <Count label="Skipped (no key)" value={result.skipped_no_citekey} tone="text-ink-light" />
        {/* Identified by the search and never readable. Excluded at retrieval
            rather than at screening, and a review that cannot say how much of
            its grey literature had rotted is hiding a limitation. */}
        <Count label="Imported, not retrievable" value={result.imported_unretrievable}
          tone="text-uncertain" />
      </div>

      {/* The breakdown counts every unreadable record in the package, while
          the box above counts only the ones this import wrote a row for. The
          two populations differ whenever a scope overlaps what the project
          already holds — a re-imported run can report zero above and a list of
          causes here — so the list has to say which population it describes
          rather than read as an explanation of the number. */}
      {reasons.length > 0 && (
        <>
          <p className="text-xs text-ink-muted mt-2">
            Unreadable sources in the package, by cause — all of them, including
            records this project already had:
          </p>
          <ul className="text-xs text-ink-light mt-1 space-y-0.5">
            {reasons.map(([reason, n]) => (
              <li key={reason}>· {reasonLabel(reason)}: {n}</li>
            ))}
          </ul>
        </>
      )}

      {disagrees && (
        <p className="text-xs text-uncertain mt-2">
          The package reports {reported} documents but carries {result.total_in_package} records.
          The counts above describe what was actually read.
        </p>
      )}

      {/* A `refetch` or `re-extract` run carries no documents of its own: it
          re-read sources an earlier run identified. Importing one is not an
          error, but it is a no-op, and a row of zeros does not say so. */}
      {result.total_in_package === 0 && (
        <p className="text-xs text-ink-light mt-2">
          This scope carried no documents, so nothing was imported. A refetch or
          re-extraction run re-reads sources an earlier retrieval identified;
          import that retrieval instead.
        </p>
      )}
    </div>
  )
}

export default function GreyImportPanel({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [result, setResult] = useState<GreyImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data: retrievals = [], isLoading, isError } = useQuery({
    queryKey: ['retrievals', pid],
    queryFn: () => getRetrievals(pid),
  })

  function applied(data: GreyImportResult) {
    setResult(data)
    setError(null)
    qc.invalidateQueries({ queryKey: ['import-stats', pid] })
    qc.invalidateQueries({ queryKey: ['papers', pid] })
    qc.invalidateQueries({ queryKey: ['duplicates', pid] })
    // The listing carries `already_imported`, which this import just changed.
    qc.invalidateQueries({ queryKey: ['retrievals', pid] })
  }
  function failed(err: unknown) {
    setResult(null)
    setError(errorMessage(err))
  }

  const fromRetrieval = useMutation({
    mutationFn: (scopeId: string) => importGreyFromRetrieval(pid, scopeId),
    onSuccess: applied,
    onError: failed,
  })
  const fromFile = useMutation({
    mutationFn: (file: File) => importGreyPackage(pid, file),
    onSuccess: applied,
    onError: failed,
  })
  const busy = fromRetrieval.isPending || fromFile.isPending

  return (
    <Card>
      <CardHeader title="Import Grey Literature" />
      <p className="text-xs text-ink-muted mb-4 max-w-2xl">
        Grey literature is retrieved outside this interface, with{' '}
        <code className="bg-rule/30 px-1 rounded">python -m app.retrieval batch</code>;
        search-engine keys are read from the process environment and are never entered here.
        What a retrieval produced is imported below.
      </p>

      {isLoading && <p className="text-sm text-ink-muted">Loading retrievals…</p>}

      {isError && (
        <p className="text-xs text-exclude">
          The retrieval database could not be read. Grey literature can still be imported
          as a package file below.
        </p>
      )}

      {!isLoading && !isError && retrievals.length === 0 && (
        <p className="text-sm text-ink-muted">
          This project has made no retrievals yet. Run one from the command line, or import
          a package file from a co-reviewer below.
        </p>
      )}

      {retrievals.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[620px]">
            <thead>
              <tr className="text-xs text-ink-muted uppercase tracking-label">
                <th className="text-left pb-2 font-semibold">Retrieval</th>
                <th className="text-left pb-2 font-semibold">Started (UTC)</th>
                <th className="text-left pb-2 font-semibold">Engine</th>
                <th className="text-right pb-2 font-semibold">Documents</th>
                <th className="text-right pb-2 font-semibold">Runs</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {retrievals.map(r => (
                <RetrievalRow key={`${r.kind}:${r.scope_id}`} retrieval={r} busy={busy}
                  onImport={scopeId => fromRetrieval.mutate(scopeId)} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {retrievals.some(r => r.incomplete) && (
        <p className="text-xs text-uncertain mt-3">
          A retrieval marked incomplete has a run that did not finish. It can be imported,
          but the records it contributes are fewer than its query set asked for.
        </p>
      )}

      <div className="mt-5 pt-4 border-t border-rule">
        <p className="text-xs text-ink-muted mb-2">
          From elsewhere: a <code className="bg-rule/30 px-1 rounded">reviq-grey-v1</code>{' '}
          package exported by another installation.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".json,application/json"
          className="hidden"
          onChange={e => {
            const file = e.target.files?.[0]
            if (file) fromFile.mutate(file)
            e.target.value = ''
          }}
        />
        <button className="btn-secondary" disabled={busy}
          onClick={() => fileRef.current?.click()}>
          {fromFile.isPending ? 'Importing…' : 'Choose package file'}
        </button>
      </div>

      {busy && <p className="text-xs text-ink-muted mt-3">Importing…</p>}
      {error && <p className="text-xs text-exclude mt-3">{error}</p>}
      {result && <div className="mt-3"><ResultBlock result={result} /></div>}
    </Card>
  )
}
