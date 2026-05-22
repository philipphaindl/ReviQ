/**
 * Snowballing (Phase 5) — Forward/backward citation snowballing with iteration management,
 * BibTeX import per iteration, saturation tracking, and per-iteration screening decisions.
 */
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
  Card, CardHeader, StatBar, StatCell, Modal, FormField,
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
        <h1 className="text-xl font-bold text-ink font-display">Snowballing</h1>
        <p className="text-sm text-ink-muted">Phase 5 — Forward and Backward Citation Snowballing <span className="text-ink-muted/40 font-normal">(optional)</span></p>
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

  const { data: screeningPapers = [] } = useQuery({
    queryKey: ['papers', pid, 'screening'],
    queryFn: () => getPapers(pid, { phase: 'screening' }),
  })
  // Seed corpus: full-text included if available, otherwise screening-included
  const { data: fulltextPapers = [] } = useQuery({
    queryKey: ['papers', pid, 'full-text'],
    queryFn: () => getPapers(pid, { phase: 'full-text' }),
  })

  const fulltextIncluded = fulltextPapers.filter(
    p => p.final_decision?.decision === 'I' && !p.source.startsWith('snowballing:')
  )
  const screeningIncluded = screeningPapers.filter(
    p => p.dedup_status === 'original'
      && !p.source.startsWith('snowballing:')
      && p.final_decision?.decision === 'I'
  )
  const seedPapers = fulltextIncluded.length > 0 ? fulltextIncluded : screeningIncluded
  const seedPhaseLabel = fulltextIncluded.length > 0
    ? 'From Phase 4 (Eligibility)'
    : 'From Phase 3 (Screening)'

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
  const totalFTIncluded = fulltextPapers.filter(
    p => p.source?.startsWith('snowballing:') && p.final_decision?.decision === 'I'
  ).length
  const allSaturated = iterations.length > 0 && iterations.every(it => it.saturation_confirmed)
  const anySaturated = iterations.some(it => it.saturation_confirmed)

  return (
    <div className="space-y-5">
      {/* Stats */}
      <StatBar>
        <StatCell label="Seed Papers" value={seedPapers.length} sub={seedPhaseLabel} />
        <StatCell label="Iterations" value={iterations.length} />
        <StatCell label="Retrieved" value={totalPapers} />
        <StatCell label="Incl. (Screening)" value={totalIncluded} sub="Passed title/abstract" />
        <StatCell label="Incl. (Full-Text)" value={totalFTIncluded} sub="Phase 4 eligible" color={totalFTIncluded > 0 ? 'include' : 'navy'} />
      </StatBar>

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
          <table className="w-full text-sm table-fixed">
            <thead>
              <tr className="text-xs text-ink-muted uppercase tracking-label border-b border-rule">
                <th className="text-left pb-2 font-semibold w-[17%]">Iteration</th>
                <th className="text-left pb-2 font-semibold w-[10%]">Type</th>
                <th className="text-right pb-2 font-semibold w-[8%]">Retrieved</th>
                <th className="text-right pb-2 font-semibold w-[8%]">Decided</th>
                <th className="text-right pb-2 font-semibold text-include leading-tight w-[11%]">Incl. after<br />Screening</th>
                <th className="text-right pb-2 font-semibold text-exclude w-[8%]">Excluded</th>
                <th className="text-right pb-2 font-semibold text-uncertain w-[8%]">Undecided</th>
                <th className="text-right pb-2 font-semibold text-include leading-tight w-[16%]">Incl. after<br />Full-Text Assessment</th>
                <th className="text-right pb-2 font-semibold w-[8%]">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {/* Seed papers row — highlighted only when no iteration is selected */}
              <tr className={`cursor-pointer transition-colors ${expandedId === null ? 'bg-blue-50' : 'hover:bg-paper'}`}
                onClick={() => setExpandedId(null)}>
                <td className="py-2 font-semibold text-ink">Seed corpus</td>
                <td className="py-2 text-xs text-ink-muted">Initial search</td>
                <td className="py-2 text-right text-ink font-medium">—</td>
                <td className="py-2 text-right text-ink font-medium">—</td>
                <td className="py-2 text-right text-include font-bold">{seedPapers.length}</td>
                <td className="py-2 text-right">—</td>
                <td className="py-2 text-right">—</td>
                <td className="py-2 text-right text-ink-muted">—</td>
                <td className="py-2 text-right">
                  <span className="text-xs px-2 py-0.5 rounded border bg-blue-100 text-info border-blue-200 font-semibold">Seeds</span>
                </td>
              </tr>
              {/* Funnel: for each iteration, compute the screening/FT pipeline counts
                  by filtering the global paper lists to this iteration's source tag */}
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
                const ftIncluded = fulltextPapers.filter(p =>
                  p.source === `snowballing:${it.iteration_number}` &&
                  p.final_decision?.decision === 'I'
                ).length
                return (
                  <tr key={it.id} className={`cursor-pointer transition-colors ${expandedId === it.id ? 'bg-blue-50' : 'hover:bg-paper'}`}
                    onClick={() => setExpandedId(expandedId === it.id ? null : it.id)}>
                    <td className="py-2 font-semibold text-ink">Iteration {it.iteration_number}</td>
                    <td className="py-2 text-xs">
                      <span className={`px-2 py-0.5 rounded border font-semibold ${
                        it.iteration_type === 'forward'
                          ? 'bg-accent-faint text-accent border-accent/20'
                          : 'bg-purple-50 text-purple-700 border-purple-200'
                      }`}>{it.iteration_type === 'forward' ? 'Forward' : 'Backward'}</span>
                    </td>
                    <td className="py-2 text-right text-ink font-medium">{paperCount}</td>
                    <td className="py-2 text-right text-ink font-medium">{screened}</td>
                    <td className="py-2 text-right text-include font-bold">{it.included_count}</td>
                    <td className="py-2 text-right text-exclude font-medium">{excluded}</td>
                    <td className="py-2 text-right text-uncertain font-medium">{undecided}</td>
                    <td className="py-2 text-right text-include font-bold">{ftIncluded > 0 ? ftIncluded : <span className="text-ink-muted">0</span>}</td>
                    <td className="py-2 text-right">
                      {it.saturation_confirmed ? (
                        <span className="text-xs px-2 py-0.5 rounded border bg-green-50 text-green-700 border-green-200 font-semibold">Saturated</span>
                      ) : it.included_count === 0 && paperCount > 0 ? (
                        <span className="text-xs px-2 py-0.5 rounded border bg-yellow-50 text-yellow-700 border-yellow-200 font-semibold">0 new</span>
                      ) : (
                        <span className="text-xs text-ink-muted">Active</span>
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
        <p className="text-xs text-ink-muted">
          {iterations.length === 0
            ? `${seedPapers.length} seed paper(s) ready. Create an iteration to begin snowballing.`
            : `${iterations.length} iteration(s)`}
        </p>
        <button className="btn-primary" onClick={() => setCreating(true)}>
          + New Iteration
        </button>
      </div>

      {isLoading && <p className="text-sm text-ink-muted">Loading…</p>}

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
                  className={`flex-1 py-1.5 text-xs font-semibold rounded-[3px] border transition-all ${
                    iterType === t ? 'bg-info text-white border-info' : 'btn-secondary'
                  }`}>
                  {t === 'forward' ? 'Forward' : 'Backward'}
                </button>
              ))}
            </div>
          </FormField>
          <p className="text-xs text-ink-muted mb-4">
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
            <span className="text-sm font-bold text-ink">Iteration {iteration.iteration_number}</span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${
              iteration.iteration_type === 'forward'
                ? 'bg-accent-faint text-accent border-accent/20'
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
          <p className="text-xs text-ink-muted mt-1.5">
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
            className="text-xs px-2 py-1 rounded border border-rule text-ink-muted hover:bg-paper transition-colors"
            onClick={() => { setEditType(iteration.iteration_type as 'forward' | 'backward'); setEditing(true) }}>
            Edit
          </button>
          <button
            className="text-xs px-2 py-1 rounded border border-red-200 text-exclude hover:bg-red-50 transition-colors"
            onClick={() => setConfirmDelete(true)}>
            Delete
          </button>
        </div>
        <span className="text-ink-muted text-sm cursor-pointer shrink-0" onClick={onToggle}>{expanded ? '▲' : '▼'}</span>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="mt-4 border-t border-rule pt-4 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <input ref={fileRef} type="file" accept=".bib" className="hidden" onChange={handleImport} />
            <button
              className="btn-secondary"
              disabled={importing}
              onClick={() => fileRef.current?.click()}>
              {importing ? 'Importing…' : '↑ Import BibTeX'}
            </button>
            {importResult && (
              <span className="text-xs text-ink-muted">
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
                  className={`flex-1 py-1.5 text-xs font-semibold rounded-[3px] border transition-all ${
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
          <p className="text-sm text-ink-light mb-4">
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
  const { data: fulltextPapers = [] } = useQuery({
    queryKey: ['papers', pid, 'full-text'],
    queryFn: () => getPapers(pid, { phase: 'full-text' }),
  })
  const { data: reviewers = [] } = useQuery({ queryKey: ['reviewers', pid], queryFn: () => getReviewers(pid) })
  const { data: inclusions = [] } = useQuery({ queryKey: ['inclusion', pid], queryFn: () => getInclusionCriteria(pid) })
  const { data: exclusions = [] } = useQuery({ queryKey: ['exclusion', pid], queryFn: () => getExclusionCriteria(pid) })

  const activeReviewerId = globalReviewerId ?? reviewers.find(r => r.role === 'R1')?.id ?? reviewers[0]?.id

  const papers = allPapers.filter(p => p.source === source && p.dedup_status === 'original')

  // Track which screening-included snowballing papers still need Phase 4 review
  // Check which screening-included snowball papers still lack a full-text decision
  const ftDecisionMap = new Map(fulltextPapers.map(p => [p.id, p]))
  const snowballIncluded = papers.filter(p => p.final_decision?.decision === 'I')
  const pendingFTReview = snowballIncluded.filter(p => !ftDecisionMap.get(p.id)?.final_decision)

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
      <StatBar>
        <StatCell label="Total" value={counts.total} />
        <StatCell label="Undecided" value={counts.undecided} color="uncertain" />
        <StatCell label="Included" value={counts.I} color="include" />
        <StatCell label="Excluded" value={counts.E} color="exclude" />
        <StatCell label="Uncertain" value={counts.U} color="uncertain" />
      </StatBar>

      {snowballIncluded.length > 0 && (
        <div className={`rounded-md p-3 border text-sm ${
          pendingFTReview.length > 0
            ? 'bg-amber-50 border-amber-200 text-amber-800'
            : 'bg-green-50 border-green-200 text-green-800'
        }`}>
          <p className="font-semibold mb-0.5">Full-text eligibility required (Phase 4)</p>
          <p className="text-xs">
            Snowballing papers must undergo the same full-text eligibility
            assessment as database papers.{' '}
            {pendingFTReview.length > 0
              ? <><strong>{pendingFTReview.length}</strong> of {snowballIncluded.length} included paper{snowballIncluded.length !== 1 ? 's' : ''} still need{pendingFTReview.length === 1 ? 's' : ''} review — go to <strong>Phase 4 (Full-Text Eligibility)</strong> to complete this step.</>
              : <>All {snowballIncluded.length} included paper{snowballIncluded.length !== 1 ? 's' : ''} have been assessed in Phase 4. ✓</>
            }
          </p>
        </div>
      )}

      <div className="flex gap-1 flex-wrap">
        {(['all', 'undecided', 'I', 'E', 'U'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
              filter === f ? 'bg-accent text-white border-accent' : 'bg-surface text-ink-muted border-rule hover:border-ink-muted'
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
                <div className="flex items-center gap-2 flex-wrap">
                  {dec ? <DecisionBadge decision={dec} /> : <Badge label="Undecided" variant="neutral" />}
                  {appliedCriterion && (
                    <Badge label={appliedCriterion} variant={dec === 'I' ? 'include' : dec === 'E' ? 'exclude' : 'neutral'} />
                  )}
                  <span className="text-xs text-ink-muted">{paper.year}</span>
                </div>
                <h3 className="text-sm font-medium text-ink mt-1 leading-snug">{paper.title}</h3>
                {paper.authors && <p className="text-xs text-ink-muted mt-0.5 truncate">{formatAuthors(paper.authors)}</p>}
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
          reviewerId={activeReviewerId}
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
  paper, inclusionCriteria, exclusionCriteria, reviewerId, onSubmit, onClose, isPending, error,
}: {
  paper: Paper
  inclusionCriteria: any[]
  exclusionCriteria: any[]
  reviewerId?: number
  onSubmit: (decision: string, criterion: string, rationale: string) => void
  onClose: () => void
  isPending: boolean
  error?: string
}) {
  // Pre-populate from existing decisions
  const decs = paper.decisions ?? []
  const myDec = decs.find(d => d.reviewer_id === reviewerId)
  const latestDec = decs.length ? decs.reduce((a, b) => new Date(a.timestamp) > new Date(b.timestamp) ? a : b) : null
  const prevDec = myDec?.decision ?? paper.final_decision?.decision ?? latestDec?.decision ?? ''
  const prevCriterion = myDec?.criterion_label
    ?? decs.find(d => d.decision === prevDec && d.criterion_label)?.criterion_label
    ?? ''
  const prevRationale = myDec?.rationale ?? latestDec?.rationale ?? ''

  const [decision, setDecision] = useState(prevDec)
  const [uncertainDir, setUncertainDir] = useState<'I' | 'E' | ''>(() => {
    if (prevDec !== 'U') return ''
    if (prevCriterion && inclusionCriteria.some(c => c.label === prevCriterion)) return 'I'
    if (prevCriterion && exclusionCriteria.some(c => c.label === prevCriterion)) return 'E'
    return ''
  })
  const [criterion, setCriterion] = useState(prevCriterion)
  const [rationale, setRationale] = useState(prevRationale)
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
      <div className="bg-paper rounded-md p-4 mb-4 border border-rule">
        <p className="text-sm font-semibold text-ink mb-1 leading-snug">{paper.title}</p>
        <p className="text-xs text-ink-muted mb-3">{formatAuthors(paper.authors)} · {paper.year}</p>
        {paper.abstract ? (
          <div className="border-t border-rule pt-3">
            <p className="text-xs font-semibold text-ink-muted uppercase tracking-label mb-1.5">Abstract</p>
            <p className="text-xs text-ink-light leading-relaxed overflow-y-auto max-h-48">{paper.abstract}</p>
          </div>
        ) : (
          <p className="text-xs text-ink-muted italic border-t border-rule pt-3">No abstract available.</p>
        )}
      </div>

      <FormField label="Decision" required error={submitted && !decision ? 'Select a decision' : undefined}>
        <div className="flex gap-2">
          {(['I', 'E', 'U'] as const).map(d => (
            <button key={d} onClick={() => handleDecision(d)}
              className={`flex-1 py-1.5 text-xs font-semibold rounded-[3px] border transition-all ${
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
                className={`flex-1 py-1.5 text-xs font-semibold rounded-[3px] border transition-all ${
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
