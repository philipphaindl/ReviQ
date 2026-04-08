import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useRef } from 'react'
import { useProject } from '../App'
import {
  getSnowballingIterations, createSnowballingIteration,
  updateSnowballingIteration, deleteSnowballingIteration,
  confirmSaturation, revokeSaturation,
  importSnowballingBib, getPapers, getReviewers, getInclusionCriteria,
  getExclusionCriteria, addDecision,
} from '../api/client'
import {
  Card, CardHeader, StatCard, Modal, FormField,
  DecisionBadge, EmptyState, Badge,
} from '../components/ui'
import type { SnowballingIteration, Paper } from '../api/types'
import { formatAuthors } from '../utils'

export default function Snowballing() {
  const { projectId } = useProject()

  if (!projectId) {
    return <EmptyState icon="—" message="No active project. Select one from the Overview." />
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-navy">Snowballing</h1>
        <p className="text-sm text-gray-500">Phase 5 — Forward and Backward Citation Snowballing <span className="text-gray-300 font-normal">(optional)</span></p>
      </div>
      <IterationsView pid={projectId} />
    </div>
  )
}

// ── Iterations overview ───────────────────────────────────────────────────────

function IterationsView({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [iterType, setIterType] = useState<'forward' | 'backward'>('forward')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: iterations = [], isLoading } = useQuery({
    queryKey: ['snowballing', pid],
    queryFn: () => getSnowballingIterations(pid),
  })

  // Seed papers: original papers included from screening (non-snowballing source)
  const { data: screeningPapers = [] } = useQuery({
    queryKey: ['papers', pid, 'screening'],
    queryFn: () => getPapers(pid, { phase: 'screening' }),
  })

  const seedPapers = screeningPapers.filter(
    p => p.dedup_status === 'original'
      && !p.source.startsWith('snowballing:')
      && p.final_decision?.decision === 'I'
  )

  const createMutation = useMutation({
    mutationFn: () => createSnowballingIteration(pid, iterType),
    onSuccess: (newIt) => {
      qc.invalidateQueries({ queryKey: ['snowballing', pid] })
      setCreating(false)
      setExpandedId(newIt.id)
    },
  })

  const totalPapers = iterations.reduce((s, it) => s + it.paper_count, 0)
  const totalIncluded = iterations.reduce((s, it) => s + it.included_count, 0)
  const allSaturated = iterations.length > 0 && iterations.every(it => it.saturation_confirmed)
  const anySaturated = iterations.some(it => it.saturation_confirmed)

  return (
    <div className="space-y-5">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Seed Papers" value={seedPapers.length} color="include"
          sub="Included from screening" />
        <StatCard label="Iterations" value={iterations.length} />
        <StatCard label="Retrieved" value={totalPapers} />
        <StatCard label="Newly Included" value={totalIncluded} color={totalIncluded > 0 ? 'include' : 'navy'} />
      </div>

      {/* Saturation notice */}
      {allSaturated && (
        <div className="bg-green-50 border border-green-200 rounded-md px-4 py-2.5 text-sm text-green-800 font-medium">
          Saturation confirmed — no new papers were identified in the final iteration(s).
        </div>
      )}

      {/* Iteration funnel table */}
      {iterations.length > 0 && (
        <Card>
          <CardHeader title="Iteration Overview" />
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-navy-muted uppercase tracking-wider border-b border-border">
                <th className="text-left pb-2 font-semibold">Iteration</th>
                <th className="text-left pb-2 font-semibold">Type</th>
                <th className="text-right pb-2 font-semibold">Retrieved</th>
                <th className="text-right pb-2 font-semibold">Screened</th>
                <th className="text-right pb-2 font-semibold text-include">Included</th>
                <th className="text-right pb-2 font-semibold text-exclude">Excluded</th>
                <th className="text-right pb-2 font-semibold text-uncertain">Undecided</th>
                <th className="text-right pb-2 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {/* Seed papers row */}
              <tr className="bg-blue-50">
                <td className="py-2 font-semibold text-navy">Seed corpus</td>
                <td className="py-2 text-xs text-gray-500">Initial search</td>
                <td className="py-2 text-right text-navy font-medium">—</td>
                <td className="py-2 text-right text-navy font-medium">—</td>
                <td className="py-2 text-right text-include font-bold">{seedPapers.length}</td>
                <td className="py-2 text-right">—</td>
                <td className="py-2 text-right">—</td>
                <td className="py-2 text-right">
                  <span className="text-xs px-2 py-0.5 rounded border bg-blue-100 text-info border-blue-200 font-semibold">Seeds</span>
                </td>
              </tr>
              {iterations.map(it => {
                const paperCount = it.paper_count
                const screened = it.included_count + (screeningPapers.filter(p =>
                  p.source === `snowballing:${it.iteration_number}` &&
                  p.dedup_status === 'original' &&
                  (p.final_decision?.decision === 'E' || p.final_decision?.decision === 'U')
                ).length)
                const excluded = screeningPapers.filter(p =>
                  p.source === `snowballing:${it.iteration_number}` &&
                  p.dedup_status === 'original' &&
                  p.final_decision?.decision === 'E'
                ).length
                const undecided = screeningPapers.filter(p =>
                  p.source === `snowballing:${it.iteration_number}` &&
                  p.dedup_status === 'original' &&
                  !p.final_decision
                ).length
                return (
                  <tr key={it.id} className={`cursor-pointer transition-colors ${expandedId === it.id ? 'bg-blue-50' : 'hover:bg-card'}`}
                    onClick={() => setExpandedId(expandedId === it.id ? null : it.id)}>
                    <td className="py-2 font-semibold text-navy">Iteration {it.iteration_number}</td>
                    <td className="py-2 text-xs">
                      <span className={`px-2 py-0.5 rounded border font-semibold ${
                        it.iteration_type === 'forward'
                          ? 'bg-blue-50 text-info border-blue-200'
                          : 'bg-purple-50 text-purple-700 border-purple-200'
                      }`}>{it.iteration_type === 'forward' ? 'Forward' : 'Backward'}</span>
                    </td>
                    <td className="py-2 text-right text-navy font-medium">{paperCount}</td>
                    <td className="py-2 text-right text-navy font-medium">{screened}</td>
                    <td className="py-2 text-right text-include font-bold">{it.included_count}</td>
                    <td className="py-2 text-right text-exclude font-medium">{excluded}</td>
                    <td className="py-2 text-right text-uncertain font-medium">{undecided}</td>
                    <td className="py-2 text-right">
                      {it.saturation_confirmed ? (
                        <span className="text-xs px-2 py-0.5 rounded border bg-green-50 text-green-700 border-green-200 font-semibold">Saturated</span>
                      ) : it.included_count === 0 && paperCount > 0 ? (
                        <span className="text-xs px-2 py-0.5 rounded border bg-yellow-50 text-yellow-700 border-yellow-200 font-semibold">0 new</span>
                      ) : (
                        <span className="text-xs text-gray-400">Active</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}

      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400">
          {iterations.length === 0
            ? `${seedPapers.length} seed paper(s) ready. Create an iteration to begin snowballing.`
            : `${iterations.length} iteration(s)`}
        </p>
        <button className="btn-primary text-xs" onClick={() => setCreating(true)}>
          + New Iteration
        </button>
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading…</p>}

      {/* Iteration cards */}
      <div className="space-y-3">
        {iterations.map(it => (
          <IterationCard
            key={it.id}
            iteration={it}
            pid={pid}
            expanded={expandedId === it.id}
            onToggle={() => setExpandedId(expandedId === it.id ? null : it.id)}
          />
        ))}
      </div>

      {/* Create modal */}
      {creating && (
        <Modal title="New Snowballing Iteration" onClose={() => setCreating(false)} width="max-w-sm">
          <FormField label="Iteration Type">
            <div className="flex gap-2">
              {(['forward', 'backward'] as const).map(t => (
                <button key={t} onClick={() => setIterType(t)}
                  className={`flex-1 py-2.5 text-sm font-semibold rounded-md border transition-all ${
                    iterType === t ? 'bg-info text-white border-info' : 'btn-secondary'
                  }`}>
                  {t === 'forward' ? 'Forward' : 'Backward'}
                </button>
              ))}
            </div>
          </FormField>
          <p className="text-xs text-gray-400 mb-4">
            {iterType === 'forward'
              ? 'Forward snowballing: papers that cite the included studies.'
              : 'Backward snowballing: references listed in the included studies.'}
          </p>
          <div className="flex gap-2">
            <button className="btn-secondary flex-1 justify-center" onClick={() => setCreating(false)}>Cancel</button>
            <button className="btn-primary flex-1 justify-center"
              disabled={createMutation.isPending}
              onClick={() => createMutation.mutate()}>
              {createMutation.isPending ? 'Creating…' : 'Create'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Iteration card ────────────────────────────────────────────────────────────

function IterationCard({ iteration, pid, expanded, onToggle }: {
  iteration: SnowballingIteration
  pid: number
  expanded: boolean
  onToggle: () => void
}) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<{ imported_unique: number; detected_duplicates: number } | null>(null)
  const [editing, setEditing] = useState(false)
  const [editType, setEditType] = useState<'forward' | 'backward'>(iteration.iteration_type as 'forward' | 'backward')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const saturateMutation = useMutation({
    mutationFn: () => confirmSaturation(pid, iteration.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['snowballing', pid] }),
  })
  const unsaturateMutation = useMutation({
    mutationFn: () => revokeSaturation(pid, iteration.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['snowballing', pid] }),
  })
  const updateMutation = useMutation({
    mutationFn: () => updateSnowballingIteration(pid, iteration.id, editType),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['snowballing', pid] }); setEditing(false) },
  })
  const deleteMutation = useMutation({
    mutationFn: () => deleteSnowballingIteration(pid, iteration.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['snowballing', pid] }); qc.invalidateQueries({ queryKey: ['papers', pid] }) },
  })

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setImportResult(null)
    try {
      const result = await importSnowballingBib(pid, iteration.id, file)
      setImportResult(result)
      qc.invalidateQueries({ queryKey: ['snowballing', pid] })
      qc.invalidateQueries({ queryKey: ['papers', pid] })
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const isSaturated = iteration.saturation_confirmed

  return (
    <Card className={expanded ? 'border-info shadow-md' : ''}>
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0 cursor-pointer" onClick={onToggle}>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-navy">Iteration {iteration.iteration_number}</span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${
              iteration.iteration_type === 'forward'
                ? 'bg-blue-50 text-info border-blue-200'
                : 'bg-purple-50 text-purple-700 border-purple-200'
            }`}>{iteration.iteration_type === 'forward' ? 'Forward' : 'Backward'}</span>
            {isSaturated && (
              <span className="text-xs font-semibold px-2 py-0.5 rounded border bg-green-50 text-green-700 border-green-200">
                Saturated
              </span>
            )}
            {!isSaturated && iteration.included_count === 0 && iteration.paper_count > 0 && (
              <span className="text-xs font-semibold px-2 py-0.5 rounded border bg-yellow-50 text-yellow-700 border-yellow-200">
                0 new included
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-1.5">
            {iteration.paper_count} retrieved · {iteration.included_count} included
          </p>
        </div>
        {/* Action buttons */}
        <div className="flex items-center gap-1.5 shrink-0" onClick={e => e.stopPropagation()}>
          {isSaturated ? (
            <button
              className="text-xs px-2 py-1 rounded border border-yellow-300 text-yellow-700 hover:bg-yellow-50 transition-colors"
              disabled={unsaturateMutation.isPending}
              onClick={() => unsaturateMutation.mutate()}>
              Revoke saturation
            </button>
          ) : (
            <button
              className="text-xs px-2 py-1 rounded border border-green-300 text-green-700 hover:bg-green-50 transition-colors"
              disabled={saturateMutation.isPending}
              onClick={() => saturateMutation.mutate()}>
              Confirm saturation
            </button>
          )}
          <button
            className="text-xs px-2 py-1 rounded border border-border text-navy-muted hover:bg-card transition-colors"
            onClick={() => { setEditType(iteration.iteration_type as 'forward' | 'backward'); setEditing(true) }}>
            Edit
          </button>
          <button
            className="text-xs px-2 py-1 rounded border border-red-200 text-exclude hover:bg-red-50 transition-colors"
            onClick={() => setConfirmDelete(true)}>
            Delete
          </button>
        </div>
        <span className="text-gray-400 text-sm cursor-pointer shrink-0" onClick={onToggle}>{expanded ? '▲' : '▼'}</span>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="mt-4 border-t border-border pt-4 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <input ref={fileRef} type="file" accept=".bib" className="hidden" onChange={handleImport} />
            <button
              className="btn-secondary text-xs"
              disabled={importing}
              onClick={() => fileRef.current?.click()}>
              {importing ? 'Importing…' : '↑ Import BibTeX'}
            </button>
            {importResult && (
              <span className="text-xs text-gray-500">
                {importResult.imported_unique} imported · {importResult.detected_duplicates} cross-corpus duplicates
              </span>
            )}
          </div>
          <IterationPapersView pid={pid} iterationNumber={iteration.iteration_number} />
        </div>
      )}

      {/* Edit modal */}
      {editing && (
        <Modal title={`Edit Iteration ${iteration.iteration_number}`} onClose={() => setEditing(false)} width="max-w-sm">
          <FormField label="Iteration Type">
            <div className="flex gap-2">
              {(['forward', 'backward'] as const).map(t => (
                <button key={t} onClick={() => setEditType(t)}
                  className={`flex-1 py-2.5 text-sm font-semibold rounded-md border transition-all ${
                    editType === t ? 'bg-info text-white border-info' : 'btn-secondary'
                  }`}>
                  {t === 'forward' ? 'Forward' : 'Backward'}
                </button>
              ))}
            </div>
          </FormField>
          <div className="flex gap-2 mt-2">
            <button className="btn-secondary flex-1 justify-center" onClick={() => setEditing(false)}>Cancel</button>
            <button className="btn-primary flex-1 justify-center"
              disabled={updateMutation.isPending}
              onClick={() => updateMutation.mutate()}>
              {updateMutation.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </Modal>
      )}

      {/* Delete confirmation */}
      {confirmDelete && (
        <Modal title="Delete Iteration" onClose={() => setConfirmDelete(false)} width="max-w-sm">
          <p className="text-sm text-gray-600 mb-4">
            Delete Iteration {iteration.iteration_number}? This will permanently remove all{' '}
            <strong>{iteration.paper_count}</strong> papers imported in this iteration and their decisions.
          </p>
          <div className="flex gap-2">
            <button className="btn-secondary flex-1 justify-center" onClick={() => setConfirmDelete(false)}>Cancel</button>
            <button className="btn-danger flex-1 justify-center"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}>
              {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </Modal>
      )}
    </Card>
  )
}

// ── Papers within one iteration ───────────────────────────────────────────────

function IterationPapersView({ pid, iterationNumber }: { pid: number; iterationNumber: number }) {
  const qc = useQueryClient()
  const { reviewerId: globalReviewerId } = useProject()
  const [filter, setFilter] = useState<'all' | 'undecided' | 'I' | 'E' | 'U'>('all')
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null)

  const source = `snowballing:${iterationNumber}`

  const { data: allPapers = [] } = useQuery({
    queryKey: ['papers', pid, 'screening'],
    queryFn: () => getPapers(pid, { phase: 'screening' }),
  })
  const { data: reviewers = [] } = useQuery({ queryKey: ['reviewers', pid], queryFn: () => getReviewers(pid) })
  const { data: inclusions = [] } = useQuery({ queryKey: ['inclusion', pid], queryFn: () => getInclusionCriteria(pid) })
  const { data: exclusions = [] } = useQuery({ queryKey: ['exclusion', pid], queryFn: () => getExclusionCriteria(pid) })

  const activeReviewerId = globalReviewerId ?? reviewers.find(r => r.role === 'R1')?.id ?? reviewers[0]?.id

  const papers = allPapers.filter(p => p.source === source && p.dedup_status === 'original')

  const decisionMutation = useMutation({
    mutationFn: (data: any) => addDecision(pid, selectedPaper!.id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['papers', pid, 'screening'] })
      qc.invalidateQueries({ queryKey: ['snowballing', pid] })
      setSelectedPaper(null)
    },
  })

  const filteredPapers = papers.filter(p => {
    if (filter === 'all') return true
    if (filter === 'undecided') return !p.final_decision
    return p.final_decision?.decision === filter
  })

  const counts = {
    total: papers.length,
    undecided: papers.filter(p => !p.final_decision).length,
    I: papers.filter(p => p.final_decision?.decision === 'I').length,
    E: papers.filter(p => p.final_decision?.decision === 'E').length,
    U: papers.filter(p => p.final_decision?.decision === 'U').length,
  }

  if (papers.length === 0) {
    return <EmptyState icon="—" message="No papers imported yet. Upload a BibTeX file above." />
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-5 gap-2">
        <StatCard label="Total" value={counts.total} />
        <StatCard label="Undecided" value={counts.undecided} color="uncertain" />
        <StatCard label="Included" value={counts.I} color="include" />
        <StatCard label="Excluded" value={counts.E} color="exclude" />
        <StatCard label="Uncertain" value={counts.U} color="uncertain" />
      </div>

      <div className="flex gap-1 flex-wrap">
        {(['all', 'undecided', 'I', 'E', 'U'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
              filter === f ? 'bg-info text-white border-info' : 'bg-white text-navy-muted border-border hover:border-navy-muted'
            }`}>
            {f === 'all' ? 'All' : f === 'undecided' ? 'Undecided' : f === 'I' ? 'Include' : f === 'E' ? 'Exclude' : 'Uncertain'}
            {' '}({f === 'all' ? counts.total : f === 'undecided' ? counts.undecided : counts[f]})
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {filteredPapers.map(paper => {
          const dec = paper.final_decision?.decision
          const accentClass = dec === 'I' ? 'left-accent-include' : dec === 'E' ? 'left-accent-exclude' : dec === 'U' ? 'left-accent-uncertain' : 'left-accent-info'
          const appliedCriterion = paper.decisions?.[0]?.criterion_label
          return (
            <div key={paper.id} className={`card pl-4 ${accentClass} cursor-pointer hover:shadow-card-hover transition-shadow`}
              onClick={() => setSelectedPaper(paper)}>
              <div className="flex-1 min-w-0">
                <div className="flex items-start gap-2 flex-wrap">
                  {dec ? <DecisionBadge decision={dec} /> : <Badge label="Undecided" variant="neutral" />}
                  {appliedCriterion && (
                    <Badge label={appliedCriterion} variant={dec === 'I' ? 'include' : dec === 'E' ? 'exclude' : 'neutral'} />
                  )}
                  <span className="text-xs text-gray-400">{paper.year}</span>
                </div>
                <h3 className="text-sm font-medium text-navy mt-1 leading-snug">{paper.title}</h3>
                {paper.authors && <p className="text-xs text-gray-400 mt-0.5 truncate">{formatAuthors(paper.authors)}</p>}
              </div>
            </div>
          )
        })}
      </div>

      {selectedPaper && (
        <SnowDecisionModal
          paper={selectedPaper}
          inclusionCriteria={inclusions.filter(c => c.phase === 'screening')}
          exclusionCriteria={exclusions.filter(c => c.phase === 'screening')}
          onSubmit={(decision, criterion, rationale) => {
            decisionMutation.mutate({
              reviewer_id: activeReviewerId!,
              phase: 'screening',
              decision,
              criterion_label: criterion,
              rationale,
            })
          }}
          onClose={() => setSelectedPaper(null)}
          isPending={decisionMutation.isPending}
          error={decisionMutation.isError ? 'Could not save decision.' : undefined}
        />
      )}
    </div>
  )
}

// ── Snowballing decision modal ────────────────────────────────────────────────

function SnowDecisionModal({
  paper, inclusionCriteria, exclusionCriteria, onSubmit, onClose, isPending, error,
}: {
  paper: Paper
  inclusionCriteria: any[]
  exclusionCriteria: any[]
  onSubmit: (decision: string, criterion: string, rationale: string) => void
  onClose: () => void
  isPending: boolean
  error?: string
}) {
  const [decision, setDecision] = useState('')
  const [uncertainDir, setUncertainDir] = useState<'I' | 'E' | ''>('')
  const [criterion, setCriterion] = useState('')
  const [rationale, setRationale] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const criteria = decision === 'I' ? inclusionCriteria
    : decision === 'E' ? exclusionCriteria
    : decision === 'U'
      ? (uncertainDir === 'I' ? inclusionCriteria : uncertainDir === 'E' ? exclusionCriteria : [])
      : []

  const criteriaRequired = decision !== 'U' ? criteria.length > 0 : uncertainDir !== '' && criteria.length > 0
  const rationaleRequired = decision === 'U'

  const handleDecision = (d: string) => { setDecision(d); setCriterion(''); setUncertainDir(''); setSubmitted(false) }
  const handleSubmit = () => {
    setSubmitted(true)
    if (!decision) return
    if (criteriaRequired && !criterion) return
    if (rationaleRequired && !rationale.trim()) return
    onSubmit(decision, criterion, rationale)
  }

  return (
    <Modal title="Snowballing Screening Decision" onClose={onClose} width="max-w-2xl" onEnter={handleSubmit}>
      <div className="bg-card rounded-md p-4 mb-4 border border-border">
        <p className="text-sm font-semibold text-navy mb-1 leading-snug">{paper.title}</p>
        <p className="text-xs text-gray-400 mb-3">{formatAuthors(paper.authors)} · {paper.year}</p>
        {paper.abstract ? (
          <div className="border-t border-border pt-3">
            <p className="text-xs font-semibold text-navy-muted uppercase tracking-wider mb-1.5">Abstract</p>
            <p className="text-xs text-gray-600 leading-relaxed overflow-y-auto max-h-48">{paper.abstract}</p>
          </div>
        ) : (
          <p className="text-xs text-gray-400 italic border-t border-border pt-3">No abstract available.</p>
        )}
      </div>

      <FormField label="Decision" required error={submitted && !decision ? 'Select a decision' : undefined}>
        <div className="flex gap-2">
          {(['I', 'E', 'U'] as const).map(d => (
            <button key={d} onClick={() => handleDecision(d)}
              className={`flex-1 py-2.5 text-sm font-semibold rounded-md border transition-all ${
                decision === d
                  ? d === 'I' ? 'bg-include text-white border-include' : d === 'E' ? 'bg-exclude text-white border-exclude' : 'bg-uncertain text-white border-uncertain'
                  : d === 'I' ? 'btn-include' : d === 'E' ? 'btn-exclude' : 'btn-uncertain'
              }`}>
              {d === 'I' ? '✓ Include' : d === 'E' ? '✗ Exclude' : '? Uncertain'}
            </button>
          ))}
        </div>
      </FormField>

      {decision === 'U' && (
        <FormField label="Leaning Toward" required error={submitted && !uncertainDir ? 'Select a direction' : undefined}>
          <div className="flex gap-2">
            {(['I', 'E'] as const).map(dir => (
              <button key={dir} onClick={() => { setUncertainDir(dir); setCriterion('') }}
                className={`flex-1 py-2 text-sm font-semibold rounded-md border transition-all ${
                  uncertainDir === dir
                    ? dir === 'I' ? 'bg-include text-white border-include' : 'bg-exclude text-white border-exclude'
                    : dir === 'I' ? 'btn-include' : 'btn-exclude'
                }`}>
                {dir === 'I' ? 'Inclusion' : 'Exclusion'}
              </button>
            ))}
          </div>
        </FormField>
      )}

      {criteria.length > 0 && (
        <FormField
          label={decision === 'I' || uncertainDir === 'I' ? 'Inclusion Criterion' : 'Exclusion Criterion'}
          required error={submitted && criteriaRequired && !criterion ? 'Select a criterion' : undefined}>
          <select
            className={`select ${submitted && criteriaRequired && !criterion ? 'border-exclude ring-1 ring-exclude' : ''}`}
            value={criterion} onChange={e => setCriterion(e.target.value)}>
            <option value="">— Select criterion —</option>
            {criteria.map(c => <option key={c.id} value={c.label}>{c.label}: {c.description}</option>)}
          </select>
        </FormField>
      )}

      {decision && (
        <FormField label="Comment" required={rationaleRequired}
          error={submitted && rationaleRequired && !rationale.trim() ? 'A comment is required for uncertain decisions' : undefined}>
          <textarea
            className={`textarea ${submitted && rationaleRequired && !rationale.trim() ? 'border-exclude ring-1 ring-exclude' : ''}`}
            rows={2} value={rationale} onChange={e => setRationale(e.target.value)}
            placeholder={decision === 'U' ? 'Explain why this paper is uncertain…' : 'Brief justification (optional)…'} />
        </FormField>
      )}

      {error && <p className="text-xs text-exclude mb-2">{error}</p>}

      <div className="flex gap-2 mt-2">
        <button className="btn-secondary flex-1 justify-center" onClick={onClose}>Cancel</button>
        <button
          className={`flex-1 justify-center ${!decision ? 'btn-primary' : decision === 'I' ? 'btn-include' : decision === 'E' ? 'btn-exclude' : 'btn-uncertain'}`}
          disabled={isPending} onClick={handleSubmit}>
          {isPending ? 'Saving…' : 'Confirm Decision'}
        </button>
      </div>
    </Modal>
  )
}
