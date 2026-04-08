import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useProject } from '../App'
import {
  getPapers, getReviewers, getInclusionCriteria, getExclusionCriteria,
  addDecision, getConflicts, resolveConflict, getKappa,
  exportDecisionsUrl,
} from '../api/client'
import {
  Card, CardHeader, StatCard, Modal, FormField,
  DecisionBadge, EmptyState, Badge,
} from '../components/ui'
import type { Paper, ConflictLog } from '../api/types'

type ScreeningView = 'papers' | 'conflicts' | 'kappa'

export default function Screening() {
  const { projectId } = useProject()
  const [view, setView] = useState<ScreeningView>('papers')

  if (!projectId) {
    return <EmptyState icon="—" message="No active project. Select one from the Overview." />
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-navy">Screening</h1>
        <p className="text-sm text-gray-500">Phase 3 — Title &amp; Abstract Screening</p>
      </div>

      <div className="flex gap-0 border-b border-border">
        {(['papers', 'conflicts', 'kappa'] as ScreeningView[]).map(v => (
          <button key={v} onClick={() => setView(v)}
            className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors relative capitalize ${
              view === v
                ? 'text-info after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-info'
                : 'text-gray-400 hover:text-navy'
            }`}>
            {v}
          </button>
        ))}
      </div>

      {view === 'papers'    && <PapersView pid={projectId} />}
      {view === 'conflicts' && <ConflictsView pid={projectId} />}
      {view === 'kappa'     && <KappaView pid={projectId} />}
    </div>
  )
}

// ── Papers View ───────────────────────────────────────────────────────────────

function PapersView({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const { reviewerId: globalReviewerId, setReviewerId: setGlobalReviewerId } = useProject()
  const [filter, setFilter] = useState<'all' | 'undecided' | 'I' | 'E' | 'U'>('all')
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null)

  const { data: papers = [] } = useQuery({
    queryKey: ['papers', pid, 'screening'],
    queryFn: () => getPapers(pid, { phase: 'screening' }),
  })
  const { data: reviewers = [] } = useQuery({
    queryKey: ['reviewers', pid],
    queryFn: () => getReviewers(pid),
  })
  const { data: inclusions = [] } = useQuery({
    queryKey: ['inclusion', pid],
    queryFn: () => getInclusionCriteria(pid),
  })
  const { data: exclusions = [] } = useQuery({
    queryKey: ['exclusion', pid],
    queryFn: () => getExclusionCriteria(pid),
  })

  // Use global reviewer (set in NavBar), fall back to R1
  const activeReviewerId = globalReviewerId ?? reviewers.find(r => r.role === 'R1')?.id ?? reviewers[0]?.id

  const decisionMutation = useMutation({
    mutationFn: (data: any) => addDecision(pid, selectedPaper!.id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['papers', pid] })
      qc.invalidateQueries({ queryKey: ['conflicts', pid] })
      setSelectedPaper(null)
    },
  })

  // Filter papers
  const originalPapers = papers.filter(p => p.dedup_status === 'original')
  const filteredPapers = originalPapers.filter(p => {
    if (filter === 'all') return true
    if (filter === 'undecided') return !p.final_decision
    return p.final_decision?.decision === filter
  })

  const counts = {
    total: originalPapers.length,
    undecided: originalPapers.filter(p => !p.final_decision).length,
    I: originalPapers.filter(p => p.final_decision?.decision === 'I').length,
    E: originalPapers.filter(p => p.final_decision?.decision === 'E').length,
    U: originalPapers.filter(p => p.final_decision?.decision === 'U').length,
  }

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-5 gap-3">
        <StatCard label="Total" value={counts.total} />
        <StatCard label="Undecided" value={counts.undecided} color="uncertain" />
        <StatCard label="Included" value={counts.I} color="include" />
        <StatCard label="Excluded" value={counts.E} color="exclude" />
        <StatCard label="Uncertain" value={counts.U} color="uncertain" />
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Filter buttons */}
        <div className="flex gap-1 ml-auto">
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

        {/* Export decisions */}
        {activeReviewerId && (
          <a href={exportDecisionsUrl(pid, activeReviewerId, 'screening')} download
            className="btn-secondary text-xs">
            ↓ Export Decisions
          </a>
        )}
      </div>

      {/* Paper list */}
      {filteredPapers.length === 0 ? (
        <EmptyState icon="—" message="No papers match the current filter. Import BibTeX files first." />
      ) : (
        <div className="space-y-2">
          {filteredPapers.map(paper => (
            <PaperRow
              key={paper.id}
              paper={paper}
              onDecide={() => setSelectedPaper(paper)}
            />
          ))}
        </div>
      )}

      {/* Decision modal */}
      {selectedPaper && (
        <DecisionModal
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
          error={decisionMutation.isError ? 'Could not save decision. Make sure a reviewer is selected in the top bar.' : undefined}
        />
      )}
    </div>
  )
}

const LANG_NAMES: Record<string, string> = {
  de: 'German', fr: 'French', es: 'Spanish', zh: 'Chinese', ja: 'Japanese',
  pt: 'Portuguese', it: 'Italian', ru: 'Russian', ko: 'Korean', nl: 'Dutch',
  pl: 'Polish', ar: 'Arabic', tr: 'Turkish', sv: 'Swedish', cs: 'Czech',
}

function PaperRow({ paper, onDecide }: { paper: Paper; onDecide: () => void }) {
  const dec = paper.final_decision?.decision
  const accentClass = dec === 'I' ? 'left-accent-include' : dec === 'E' ? 'left-accent-exclude' : dec === 'U' ? 'left-accent-uncertain' : 'left-accent-info'
  const langName = paper.language && paper.language !== 'en' ? (LANG_NAMES[paper.language] ?? paper.language.toUpperCase()) : null

  return (
    <div className={`card pl-4 ${accentClass} cursor-pointer hover:shadow-card-hover transition-shadow`} onClick={onDecide}>
      <div className="flex-1 min-w-0">
        <div className="flex items-start gap-2 flex-wrap">
          {dec ? <DecisionBadge decision={dec} /> : <Badge label="Undecided" variant="neutral" />}
          {langName && <Badge label={`Non-English: ${langName}`} variant="uncertain" />}
          <span className="text-xs text-gray-400">{paper.source} · {paper.year}</span>
        </div>
        <h3 className="text-sm font-medium text-navy mt-1 leading-snug">{paper.title}</h3>
        {paper.authors && <p className="text-xs text-gray-400 mt-0.5 truncate">{paper.authors}</p>}
      </div>
    </div>
  )
}

function DecisionModal({
  paper,
  inclusionCriteria,
  exclusionCriteria,
  onSubmit,
  onClose,
  isPending,
  error,
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
  // For Uncertain: track which criterion direction the user picks ('I' | 'E' | '')
  const [uncertainDir, setUncertainDir] = useState<'I' | 'E' | ''>('')
  const [criterion, setCriterion] = useState('')
  const [rationale, setRationale] = useState('')
  const [submitted, setSubmitted] = useState(false)

  // Which criteria list to show
  const criteria = decision === 'I'
    ? inclusionCriteria
    : decision === 'E'
      ? exclusionCriteria
      : decision === 'U'
        ? (uncertainDir === 'I' ? inclusionCriteria : uncertainDir === 'E' ? exclusionCriteria : [])
        : []

  const criteriaRequired = decision !== 'U'
    ? criteria.length > 0
    : uncertainDir !== '' && criteria.length > 0

  const rationaleRequired = decision === 'U'

  const handleDecision = (d: string) => {
    setDecision(d)
    setCriterion('')
    setUncertainDir('')
    setSubmitted(false)
  }

  const handleUncertainDir = (dir: 'I' | 'E') => {
    setUncertainDir(dir)
    setCriterion('')
  }

  const handleSubmit = () => {
    setSubmitted(true)
    if (!decision) return
    if (criteriaRequired && !criterion) return
    if (rationaleRequired && !rationale.trim()) return
    onSubmit(decision, criterion, rationale)
  }

  return (
    <Modal title="Screening Decision" onClose={onClose} width="max-w-2xl" onEnter={handleSubmit}>
      {/* Paper info + abstract */}
      <div className="bg-card rounded-md p-4 mb-4 border border-border">
        <p className="text-sm font-semibold text-navy mb-1 leading-snug">{paper.title}</p>
        <p className="text-xs text-gray-400 mb-3">{paper.authors} · {paper.year} · {paper.source}</p>
        {paper.abstract ? (
          <div className="border-t border-border pt-3">
            <p className="text-xs font-semibold text-navy-muted uppercase tracking-wider mb-1.5">Abstract</p>
            <p className="text-xs text-gray-600 leading-relaxed overflow-y-auto max-h-64">{paper.abstract}</p>
          </div>
        ) : (
          <p className="text-xs text-gray-400 italic border-t border-border pt-3">No abstract available.</p>
        )}
        {paper.keywords && (
          <p className="text-xs text-gray-400 mt-2 border-t border-border pt-2">
            <span className="font-medium">Keywords:</span> {paper.keywords}
          </p>
        )}
      </div>

      {/* Decision buttons */}
      <FormField label="Decision" required error={submitted && !decision ? 'Select a decision' : undefined}>
        <div className="flex gap-2">
          {(['I', 'E', 'U'] as const).map(d => (
            <button key={d}
              onClick={() => handleDecision(d)}
              className={`flex-1 py-2.5 text-sm font-semibold rounded-md border transition-all ${
                decision === d
                  ? d === 'I' ? 'bg-include text-white border-include'
                    : d === 'E' ? 'bg-exclude text-white border-exclude'
                    : 'bg-uncertain text-white border-uncertain'
                  : d === 'I' ? 'btn-include' : d === 'E' ? 'btn-exclude' : 'btn-uncertain'
              }`}>
              {d === 'I' ? '✓ Include' : d === 'E' ? '✗ Exclude' : '? Uncertain'}
            </button>
          ))}
        </div>
      </FormField>

      {/* Uncertain: pick criterion direction (I or E, not both) */}
      {decision === 'U' && (
        <FormField label="Leaning Toward" required error={submitted && !uncertainDir ? 'Select a direction' : undefined}>
          <div className="flex gap-2">
            {(['I', 'E'] as const).map(dir => (
              <button key={dir} onClick={() => handleUncertainDir(dir)}
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

      {/* Criterion dropdown — required when criteria are configured */}
      {criteria.length > 0 && (
        <FormField
          label={decision === 'I' || uncertainDir === 'I' ? 'Inclusion Criterion' : 'Exclusion Criterion'}
          required
          error={submitted && criteriaRequired && !criterion ? 'Select a criterion' : undefined}
        >
          <select
            className={`select ${submitted && criteriaRequired && !criterion ? 'border-exclude ring-1 ring-exclude' : ''}`}
            value={criterion}
            onChange={e => setCriterion(e.target.value)}
          >
            <option value="">— Select criterion —</option>
            {criteria.map(c => (
              <option key={c.id} value={c.label}>{c.label}: {c.description}</option>
            ))}
          </select>
        </FormField>
      )}

      {/* Rationale — mandatory for Uncertain, optional otherwise */}
      {decision && (
        <FormField
          label="Comment"
          required={rationaleRequired}
          error={submitted && rationaleRequired && !rationale.trim() ? 'A comment is required for uncertain decisions' : undefined}
        >
          <textarea
            className={`textarea ${submitted && rationaleRequired && !rationale.trim() ? 'border-exclude ring-1 ring-exclude' : ''}`}
            rows={2} value={rationale}
            onChange={e => setRationale(e.target.value)}
            placeholder={decision === 'U' ? 'Explain why this paper is uncertain…' : 'Brief justification (optional)…'} />
        </FormField>
      )}

      {error && <p className="text-xs text-exclude mb-2">{error}</p>}

      <div className="flex gap-2 mt-2">
        <button className="btn-secondary flex-1 justify-center" onClick={onClose}>Cancel</button>
        <button
          className={`flex-1 justify-center ${
            !decision ? 'btn-primary' : decision === 'I' ? 'btn-include' : decision === 'E' ? 'btn-exclude' : 'btn-uncertain'
          }`}
          disabled={isPending}
          onClick={handleSubmit}
        >
          {isPending ? 'Saving…' : 'Confirm Decision'}
        </button>
      </div>
    </Modal>
  )
}

// ── Conflicts View ────────────────────────────────────────────────────────────

function ConflictsView({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<ConflictLog | null>(null)
  const [resolution, setResolution] = useState('')
  const [method, setMethod] = useState('discussion')
  const [note, setNote] = useState('')

  const { data: conflicts = [] } = useQuery({
    queryKey: ['conflicts', pid, 'open'],
    queryFn: () => getConflicts(pid, 'screening', false),
  })
  const { data: resolved = [] } = useQuery({
    queryKey: ['conflicts', pid, 'resolved'],
    queryFn: () => getConflicts(pid, 'screening', true),
  })
  const { data: reviewers = [] } = useQuery({ queryKey: ['reviewers', pid], queryFn: () => getReviewers(pid) })

  const resolveMutation = useMutation({
    mutationFn: () => resolveConflict(pid, selected!.id, {
      resolved_by_reviewer_id: reviewers.find(r => r.role === 'R1')?.id ?? reviewers[0]?.id ?? 0,
      resolution,
      resolution_method: method,
      resolution_note: note,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['conflicts', pid] })
      qc.invalidateQueries({ queryKey: ['papers', pid] })
      setSelected(null)
      setResolution('')
      setNote('')
    },
  })

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <StatCard label="Open Conflicts" value={conflicts.length} color={conflicts.length > 0 ? 'exclude' : 'navy'} />
        <StatCard label="Resolved" value={resolved.length} color="include" />
      </div>

      {conflicts.length === 0 ? (
        <Card>
          <EmptyState icon="—" message="No open conflicts. All screening decisions are in agreement." />
        </Card>
      ) : (
        <Card>
          <CardHeader title="Open Conflicts" />
          <div className="space-y-3">
            {conflicts.map(c => (
              <ConflictCard key={c.id} conflict={c} reviewers={reviewers} onResolve={() => setSelected(c)} />
            ))}
          </div>
        </Card>
      )}

      {resolved.length > 0 && (
        <Card>
          <CardHeader title="Resolved Conflicts" />
          <div className="space-y-3">
            {resolved.map(c => (
              <ConflictCard key={c.id} conflict={c} reviewers={reviewers} resolved />
            ))}
          </div>
        </Card>
      )}

      {selected && (
        <Modal title="Resolve Conflict" onClose={() => setSelected(null)} width="max-w-xl">
          <div className="mb-4">
            <p className="text-sm font-semibold text-navy mb-0.5">{selected.paper_title}</p>
            <p className="text-xs text-gray-400">{selected.paper_citekey}</p>
          </div>

          {/* Side-by-side decisions */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            {[
              { role: 'R1', decision: selected.r1_decision, rationale: selected.r1_rationale },
              { role: 'R2', decision: selected.r2_decision, rationale: selected.r2_rationale },
            ].map(r => (
              <div key={r.role} className={`p-3 rounded-md border ${r.decision === 'I' ? 'border-green-200 bg-green-50' : r.decision === 'E' ? 'border-red-200 bg-red-50' : 'border-orange-200 bg-orange-50'}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-gray-600">{r.role}</span>
                  {r.decision && <DecisionBadge decision={r.decision} />}
                </div>
                {r.rationale && <p className="text-xs text-gray-600">{r.rationale}</p>}
              </div>
            ))}
          </div>

          <FormField label="Final Decision">
            <div className="flex gap-2">
              {(['I', 'E', 'U'] as const).map(d => (
                <button key={d} onClick={() => setResolution(d)}
                  className={`flex-1 py-2 text-sm font-semibold rounded-md border transition-all ${
                    resolution === d
                      ? d === 'I' ? 'bg-include text-white border-include' : d === 'E' ? 'bg-exclude text-white border-exclude' : 'bg-uncertain text-white border-uncertain'
                      : d === 'I' ? 'btn-include' : d === 'E' ? 'btn-exclude' : 'btn-uncertain'
                  }`}>
                  {d === 'I' ? 'Include' : d === 'E' ? 'Exclude' : 'Uncertain'}
                </button>
              ))}
            </div>
          </FormField>

          <FormField label="Resolution Method">
            <select className="select" value={method} onChange={e => setMethod(e.target.value)}>
              <option value="discussion">Discussion (R1 + R2)</option>
              <option value="arbitration">Arbitration (R3+)</option>
              <option value="agreement">Retrospective Agreement</option>
            </select>
          </FormField>

          <FormField label="Resolution Note (optional)">
            <textarea className="textarea" rows={2} value={note} onChange={e => setNote(e.target.value)}
              placeholder="Brief note on how the conflict was resolved…" />
          </FormField>

          <button className="btn-primary w-full justify-center mt-2"
            disabled={!resolution || resolveMutation.isPending}
            onClick={() => resolveMutation.mutate()}>
            {resolveMutation.isPending ? 'Resolving…' : 'Confirm Resolution'}
          </button>
        </Modal>
      )}
    </div>
  )
}

function ConflictCard({ conflict, reviewers, resolved, onResolve }: {
  conflict: ConflictLog
  reviewers: any[]
  resolved?: boolean
  onResolve?: () => void
}) {
  const r1Name = reviewers.find(r => r.id === conflict.r1_reviewer_id)?.name ?? 'R1'
  const r2Name = reviewers.find(r => r.id === conflict.r2_reviewer_id)?.name ?? 'R2'

  return (
    <div className={`p-3 rounded-md border ${resolved ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-navy truncate">{conflict.paper_title ?? conflict.paper_citekey}</p>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-xs text-gray-500">{r1Name}:</span>
            {conflict.r1_decision && <DecisionBadge decision={conflict.r1_decision} />}
            <span className="text-xs text-gray-400">vs.</span>
            <span className="text-xs text-gray-500">{r2Name}:</span>
            {conflict.r2_decision && <DecisionBadge decision={conflict.r2_decision} />}
          </div>
          {resolved && conflict.resolution && (
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs text-gray-400">Resolved:</span>
              <DecisionBadge decision={conflict.resolution} />
              <span className="text-xs text-gray-400">({conflict.resolution_method})</span>
            </div>
          )}
        </div>
        {!resolved && onResolve && (
          <button className="btn-primary text-xs shrink-0" onClick={onResolve}>Resolve</button>
        )}
      </div>
    </div>
  )
}

// ── Kappa View ────────────────────────────────────────────────────────────────

function KappaView({ pid }: { pid: number }) {
  const { data: kappa, isLoading, isError } = useQuery({
    queryKey: ['kappa', pid, 'screening'],
    queryFn: () => getKappa(pid, 'screening'),
  })

  const kappaColor = (k: number) =>
    k >= 0.81 ? 'include' : k >= 0.61 ? 'info' : k >= 0.41 ? 'uncertain' : 'exclude'

  return (
    <div className="max-w-xl space-y-4">
      <Card>
        <CardHeader title="Inter-Rater Agreement — Screening" />

        {isLoading && <p className="text-sm text-gray-400">Calculating…</p>}
        {isError && (
          <p className="text-sm text-gray-400">
            Not enough data yet. Both reviewers need to screen at least one common paper.
          </p>
        )}

        {kappa && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <StatCard label="Cohen's κ" value={kappa.kappa.toFixed(3)}
                sub={`95% CI [${kappa.kappa_ci_lower.toFixed(3)}, ${kappa.kappa_ci_upper.toFixed(3)}]`}
                color={kappaColor(kappa.kappa)} />
              <StatCard label="PABAK" value={kappa.pabak.toFixed(3)}
                sub="Prevalence & bias adjusted" />
            </div>

            <div className="bg-card rounded-md p-3 border border-border">
              <p className="text-xs font-semibold text-navy-muted uppercase tracking-wider mb-1">Interpretation</p>
              <p className="text-sm font-semibold text-navy">{kappa.interpretation}</p>
              <p className="text-xs text-gray-400 mt-0.5">
                Landis &amp; Koch (1977) scale · κ = {kappa.kappa.toFixed(3)}
              </p>
            </div>

            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-navy-muted uppercase tracking-wider">
                  <th className="text-left pb-2 font-semibold">Metric</th>
                  <th className="text-right pb-2 font-semibold">Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                <tr><td className="py-2 text-gray-600">Papers in sample</td><td className="py-2 text-right font-medium text-navy">{kappa.n_papers}</td></tr>
                <tr><td className="py-2 text-gray-600">Observed agreement (Po)</td><td className="py-2 text-right font-medium text-navy">{(kappa.observed_agreement * 100).toFixed(1)}%</td></tr>
                <tr><td className="py-2 text-gray-600">Both Include</td><td className="py-2 text-right text-include font-medium">{kappa.n_agree_include}</td></tr>
                <tr><td className="py-2 text-gray-600">Both Exclude</td><td className="py-2 text-right text-exclude font-medium">{kappa.n_agree_exclude}</td></tr>
                <tr><td className="py-2 text-gray-600">Disagreements</td><td className="py-2 text-right text-uncertain font-medium">{kappa.n_disagree}</td></tr>
                <tr><td className="py-2 text-gray-600">Reviewers</td><td className="py-2 text-right text-navy">{kappa.r1_name} vs. {kappa.r2_name}</td></tr>
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="About Kappa" />
        <div className="space-y-1.5 text-xs text-gray-600">
          <p><span className="font-semibold text-navy">κ ≥ 0.81</span> — Almost perfect agreement</p>
          <p><span className="font-semibold text-navy">κ 0.61–0.80</span> — Substantial agreement</p>
          <p><span className="font-semibold text-navy">κ 0.41–0.60</span> — Moderate agreement</p>
          <p><span className="font-semibold text-navy">κ 0.21–0.40</span> — Fair agreement</p>
          <p><span className="font-semibold text-navy">κ &lt; 0.21</span> — Slight / poor agreement</p>
          <p className="pt-2 text-gray-400">U (Uncertain) counts as a distinct category, not as an abstention. PABAK adjusts for prevalence and bias (Byrt et al., 1993).</p>
        </div>
      </Card>
    </div>
  )
}
