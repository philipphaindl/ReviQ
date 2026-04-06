import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useRef } from 'react'
import { useProject } from '../App'
import {
  importBibFile, getImportStats, getDuplicates, overrideDedup, importReviewerDecisions,
} from '../api/client'
import { Card, CardHeader, StatCard, EmptyState } from '../components/ui'
import { DATABASES, DatabaseBadge } from '../components/databases'
import type { Paper } from '../api/types'

export default function Search() {
  const { projectId } = useProject()
  const qc = useQueryClient()
  const bibInputRef = useRef<HTMLInputElement>(null)
  const decisionsInputRef = useRef<HTMLInputElement>(null)
  const [dbName, setDbName] = useState<string>(DATABASES[0].key)
  const [dbNameError, setDbNameError] = useState(false)
  const [importResult, setImportResult] = useState<any>(null)
  const [importDecResult, setImportDecResult] = useState<any>(null)
  const [showDuplicates, setShowDuplicates] = useState(false)

  const { data: stats } = useQuery({
    queryKey: ['import-stats', projectId],
    queryFn: () => getImportStats(projectId!),
    enabled: !!projectId,
  })

  const { data: duplicates = [] } = useQuery({
    queryKey: ['duplicates', projectId],
    queryFn: () => getDuplicates(projectId!),
    enabled: !!projectId && showDuplicates,
  })

  const importMutation = useMutation({
    mutationFn: ({ file }: { file: File }) => importBibFile(projectId!, dbName, file),
    onSuccess: (data) => {
      setImportResult(data)
      qc.invalidateQueries({ queryKey: ['import-stats', projectId] })
      qc.invalidateQueries({ queryKey: ['papers', projectId] })
      qc.invalidateQueries({ queryKey: ['duplicates', projectId] })
    },
  })

  const overrideMutation = useMutation({
    mutationFn: (paperId: number) => overrideDedup(projectId!, paperId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['duplicates', projectId] })
      qc.invalidateQueries({ queryKey: ['import-stats', projectId] })
    },
  })

  const importDecisionsMutation = useMutation({
    mutationFn: (file: File) => importReviewerDecisions(projectId!, file),
    onSuccess: (data) => {
      setImportDecResult(data)
      qc.invalidateQueries({ queryKey: ['conflicts', projectId] })
      qc.invalidateQueries({ queryKey: ['papers', projectId] })
    },
  })

  if (!projectId) {
    return <EmptyState icon="📥" message="No active project. Select or create one from the Overview." />
  }

  const sources = stats ? Object.entries(stats.by_source) : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-navy">Import</h1>
        <p className="text-sm text-gray-500">Phase 1 — Search &amp; Import BibTeX files</p>
      </div>

      {/* Summary stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-4">
          <StatCard label="Total Retrieved" value={stats.total_papers} />
          <StatCard label="Unique Papers" value={stats.total_original} color="include" />
          <StatCard label="Duplicates Removed" value={stats.total_duplicates} color="uncertain" />
        </div>
      )}

      {/* Per-database breakdown */}
      {sources.length > 0 && (
        <Card>
          <CardHeader title="Per-Database Counts" />
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-navy-muted uppercase tracking-wider">
                <th className="text-left pb-2 font-semibold">Database</th>
                <th className="text-right pb-2 font-semibold">Retrieved</th>
                <th className="text-right pb-2 font-semibold">Unique</th>
                <th className="text-right pb-2 font-semibold">Duplicates</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {sources.map(([source, counts]) => (
                <tr key={source}>
                  <td className="py-2">
                    <div className="flex items-center gap-2">
                      <DatabaseBadge dbKey={source} size="sm" />
                      <span className="font-medium text-navy">{DATABASES.find(d => d.key === source)?.label ?? source}</span>
                    </div>
                  </td>
                  <td className="py-2 text-right text-gray-600">{counts.total}</td>
                  <td className="py-2 text-right text-include font-medium">{counts.original}</td>
                  <td className="py-2 text-right text-uncertain">{counts.duplicate}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <button
            className="btn-secondary text-xs mt-4"
            onClick={() => setShowDuplicates(v => !v)}
          >
            {showDuplicates ? 'Hide' : 'Show'} Duplicate Log ({stats?.total_duplicates ?? 0})
          </button>
        </Card>
      )}

      {/* Duplicate log */}
      {showDuplicates && duplicates.length > 0 && (
        <Card>
          <CardHeader title="Duplicate Detection Log" />
          <div className="divide-y divide-border max-h-72 overflow-y-auto">
            {duplicates.map((p: Paper) => (
              <div key={p.id} className="py-2.5 flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-navy truncate">{p.title}</p>
                  <p className="text-xs text-gray-400">{p.citekey} · {p.source} · {p.year}</p>
                  <p className="text-xs text-uncertain">Flagged as duplicate</p>
                </div>
                <button
                  className="btn-secondary text-xs shrink-0"
                  onClick={() => overrideMutation.mutate(p.id)}
                >
                  Mark Unique
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Import BibTeX */}
      <Card>
        <CardHeader title="Import BibTeX File" />
        <div className="space-y-4 max-w-lg">
          <div>
            <label className="block text-xs font-semibold text-navy-muted uppercase tracking-wider mb-1.5">
              Database <span className="text-exclude normal-case font-normal">* required</span>
            </label>
            <select
              className={`select ${dbNameError ? 'border-exclude ring-1 ring-exclude' : ''}`}
              value={dbName}
              onChange={e => { setDbName(e.target.value); setDbNameError(false) }}
            >
              {DATABASES.map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
            </select>
            {dbNameError && (
              <p className="text-xs text-exclude mt-1">Select a database before choosing a file.</p>
            )}
          </div>
          <div>
            <label className="block text-xs font-semibold text-navy-muted uppercase tracking-wider mb-1.5">
              BibTeX File
            </label>
            <input
              ref={bibInputRef}
              type="file"
              accept=".bib"
              className="hidden"
              onChange={e => {
                const file = e.target.files?.[0]
                if (file && dbName) {
                  importMutation.mutate({ file })
                } else if (file && !dbName) {
                  setDbNameError(true)
                }
                e.target.value = ''
              }}
            />
            <button
              className="btn-primary"
              disabled={importMutation.isPending}
              onClick={() => {
                if (!dbName) { setDbNameError(true); return }
                bibInputRef.current?.click()
              }}
            >
              {importMutation.isPending ? 'Importing…' : 'Choose .bib File'}
            </button>
          </div>

          {/* Import result */}
          {importResult && (
            <div className="bg-green-50 border border-green-200 rounded-md p-3 text-sm">
              <p className="font-semibold text-include mb-1">Import complete — {importResult.db_name}</p>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div>
                  <p className="text-gray-400">In file</p>
                  <p className="font-semibold text-navy">{importResult.total_in_file}</p>
                </div>
                <div>
                  <p className="text-gray-400">Imported unique</p>
                  <p className="font-semibold text-include">{importResult.imported_unique}</p>
                </div>
                <div>
                  <p className="text-gray-400">Duplicates</p>
                  <p className="font-semibold text-uncertain">{importResult.detected_duplicates}</p>
                </div>
              </div>
            </div>
          )}

          {importMutation.isError && (
            <p className="text-xs text-exclude">Import failed. Check that the file is valid BibTeX and the database name is set.</p>
          )}
        </div>
      </Card>

      {/* Import reviewer decisions */}
      <Card>
        <CardHeader title="Import Reviewer Decisions" />
        <p className="text-xs text-gray-500 mb-4">
          Import a <code className="bg-gray-100 px-1 rounded">.json</code> decision file exported by a co-reviewer.
          Conflicts are automatically detected and shown in the Screening tab.
        </p>
        <input
          ref={decisionsInputRef}
          type="file"
          accept=".json"
          className="hidden"
          onChange={e => {
            const file = e.target.files?.[0]
            if (file) importDecisionsMutation.mutate(file)
            e.target.value = ''
          }}
        />
        <button
          className="btn-secondary"
          disabled={importDecisionsMutation.isPending}
          onClick={() => decisionsInputRef.current?.click()}
        >
          {importDecisionsMutation.isPending ? 'Importing…' : '📂 Choose Decision JSON'}
        </button>

        {importDecResult && (
          <div className="mt-3 bg-blue-50 border border-blue-200 rounded-md p-3 text-sm">
            <p className="font-semibold text-info mb-1">Decisions imported — {importDecResult.reviewer_name}</p>
            <p className="text-xs text-gray-600">
              {importDecResult.imported_decisions} decisions · {importDecResult.new_conflicts_detected} new conflicts
            </p>
            {importDecResult.conflict_papers?.length > 0 && (
              <p className="text-xs text-uncertain mt-1">
                Conflicts on: {importDecResult.conflict_papers.slice(0, 5).join(', ')}
                {importDecResult.conflict_papers.length > 5 ? ` +${importDecResult.conflict_papers.length - 5} more` : ''}
              </p>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}
