import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useRef } from 'react'
import { useProject } from '../App'
import {
  getSnowballingIterations, createSnowballingIteration, confirmSaturation,
  importSnowballingBib, getPapers, getReviewers, getInclusionCriteria,
  getExclusionCriteria, addDecision,
} from '../api/client'
import {
  Card, CardHeader, StatCard, Modal, FormField,
  DecisionBadge, EmptyState, Badge,
} from '../components/ui'
import type { SnowballingIteration, Paper } from '../api/types'

export default function Snowballing() {
  const { projectId } = useProject()

  if (!projectId) {
    return <EmptyState icon="—" message="No active project. Select one from the Overview." />
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-navy">Snowballing</h1>
        <p className="text-sm text-gray-500">Phase 4 — Forward &amp; backward citation snowballing</p>
      </div>
      <IterationsView pid={projectId} />
    </div>
  )
}

function IterationsView({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [iterType, setIterType] = useState<'forward' | 'backward'>('forward')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: iterations = [], isLoading } = useQuery({
    queryKey: ['snowballing', pid],
    queryFn: () => getSnowballingIterations(pid),
  })

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
  const saturated = iterations.filter(it => it.saturation_confirmed).length

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Iterations" value={iterations.length} />
        <StatCard label="Total Papers" value={totalPapers} />
        <StatCard label="Included" value={totalIncluded} color="include" />
      </div>

      {saturated > 0 && (
        <div className="bg-green-50 border border-green-200 rounded-md px-4 py-2 text-sm text-green-800">
          {saturated === iterations.length && iterations.length > 0
            ? 'Saturation reached — all iterations confirmed saturated.'
            : `${saturated} of ${iterations.length} iteration(s) confirmed saturated.`}
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-400">
          {iterations.length === 0 ? 'No iterations yet. Create one to start snowballing.' : `${iterations.length} iteration(s)`}
        </p>
        <button className="btn-primary text-xs" onClick={() => setCreating(true)}>
          + New Iteration
        </button>
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading…</p>}

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

  const saturateMutation = useMutation({
    mutationFn: () => confirmSaturation(pid, iteration.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['snowballing', pid] }),
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

  const typeLabel = iteration.iteration_type === 'forward' ? 'Forward' : 'Backward'
  const isSaturated = iteration.saturation_confirmed

  return (
    <Card>
      <div className="flex items-center gap-3 cursor-pointer" onClick={onToggle}>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-navy">Iteration {iteration.iteration_number}</span>
            <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${
              iteration.iteration_type === 'forward'
                ? 'bg-blue-50 text-info border-blue-200'
                : 'bg-purple-50 text-purple-700 border-purple-200'
            }`}>{typeLabel}</span>
            {isSaturated && (
              <span className="text-xs font-semibold px-2 py-0.5 rounded border bg-green-50 text-green-700 border-green-200">
                Saturated
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            {iteration.paper_count} papers · {iteration.included_count} included
            {iteration.included_count === 0 && iteration.paper_count > 0 && ' (0 new → potentially saturated)'}
          </p>
        </div>
        <span className="text-gray-400 text-sm shrink-0">{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <div className="mt-4 border-t border-border pt-4 space-y-4">
          {/* Import BibTeX */}
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
                {importResult.imported_unique} imported · {importResult.detected_duplicates} duplicates detected
              </span>
            )}
            {!isSaturated && (
              <button
                className="btn-secondary text-xs border-green-300 text-green-700 hover:bg-green-50 ml-auto"
                disabled={saturateMutation.isPending}
                onClick={() => saturateMutation.mutate()}>
                {saturateMutation.isPending ? 'Confirming…' : 'Confirm Saturation'}
              </button>
            )}
          </div>

          {/* Papers for this iteration */}
          <IterationPapersView pid={pid} iterationNumber={iteration.iteration_number} />
        </div>
      )}
    </Card>
  )
}

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
          return (
            <div key={paper.id} className={`card pl-4 ${accentClass} cursor-pointer hover:shadow-card-hover transition-shadow`}
              onClick={() => setSelectedPaper(paper)}>
              <div className="flex-1 min-w-0">
                <div className="flex items-start gap-2 flex-wrap">
                  {dec ? <DecisionBadge decision={dec} /> : <Badge label="Undecided" variant="neutral" />}
                  <span className="text-xs text-gray-400">{paper.year}</span>
                </div>
                <h3 className="text-sm font-medium text-navy mt-1 leading-snug">{paper.title}</h3>
                {paper.authors && <p className="text-xs text-gray-400 mt-0.5 truncate">{paper.authors}</p>}
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
        <p className="text-xs text-gray-400 mb-3">{paper.authors} · {paper.year}</p>
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
