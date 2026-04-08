import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useProject } from '../App'
import { getQASummary, upsertQAScore, getReviewers } from '../api/client'
import {
  Card, CardHeader, StatCard, Modal, FormField, EmptyState,
} from '../components/ui'
import type { QAPaperResult, QAScoreEntry } from '../api/types'

export default function Quality() {
  const { projectId } = useProject()
  const [view, setView] = useState<'scoring' | 'summary'>('scoring')

  if (!projectId) {
    return <EmptyState icon="—" message="No active project. Select one from the Overview." />
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-navy">Quality Assessment</h1>
        <p className="text-sm text-gray-500">Phase 6 — Quality Assessment of Included Studies</p>
      </div>

      <div className="flex gap-0 border-b border-border">
        {(['scoring', 'summary'] as const).map(v => (
          <button key={v} onClick={() => setView(v)}
            className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors relative capitalize ${
              view === v
                ? 'text-info after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-info'
                : 'text-gray-400 hover:text-navy'
            }`}>
            {v === 'scoring' ? 'Score Papers' : 'Summary'}
          </button>
        ))}
      </div>

      {view === 'scoring' && <ScoringView pid={projectId} />}
      {view === 'summary' && <SummaryView pid={projectId} />}
    </div>
  )
}

// ── Scoring View ──────────────────────────────────────────────────────────────

function ScoringView({ pid }: { pid: number }) {
  const [selectedPaper, setSelectedPaper] = useState<QAPaperResult | null>(null)

  const { data: summary, isLoading } = useQuery({
    queryKey: ['qa-summary', pid],
    queryFn: () => getQASummary(pid),
  })

  if (isLoading) return <p className="text-sm text-gray-400">Loading…</p>

  if (!summary || summary.papers.length === 0) {
    return (
      <EmptyState icon="—" message={
        summary?.criteria.length === 0
          ? 'No QA criteria defined. Add QA1, QA2, … criteria in Setup → Quality Assessment.'
          : 'No eligible papers yet. Include papers through screening or full-text eligibility first.'
      } />
    )
  }

  const scored = summary.papers.filter(p => p.fully_scored).length

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Eligible Papers" value={summary.papers.length} />
        <StatCard label="Fully Scored" value={scored} color="include" />
        <StatCard label="Pending" value={summary.papers.length - scored} color="uncertain" />
      </div>

      <div className="space-y-2">
        {summary.papers.map(paper => (
          <PaperQARow
            key={paper.paper_id}
            paper={paper}
            criteria={summary.criteria}
            onScore={() => setSelectedPaper(paper)}
          />
        ))}
      </div>

      {selectedPaper && (
        <QAScoringModal
          paper={selectedPaper}
          criteria={summary.criteria}
          pid={pid}
          onClose={() => setSelectedPaper(null)}
        />
      )}
    </div>
  )
}

const fmt = (n: number) => n % 1 === 0 ? String(Math.round(n)) : n.toFixed(1)

const QUALITY_COLORS = {
  high: { bg: 'bg-green-100', text: 'text-green-800', border: 'border-green-200' },
  medium: { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-200' },
  low: { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-200' },
}

function PaperQARow({ paper, criteria, onScore }: {
  paper: QAPaperResult
  criteria: { id: number; label: string; description: string; max_score: number }[]
  onScore: () => void
}) {
  const qc = QUALITY_COLORS[paper.quality_level]
  const accentClass = paper.quality_level === 'high' ? 'left-accent-include'
    : paper.quality_level === 'medium' ? 'left-accent-uncertain'
    : 'left-accent-exclude'

  return (
    <div className={`card pl-4 ${accentClass} cursor-pointer hover:shadow-card-hover transition-shadow`}
      onClick={onScore}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs font-bold px-2 py-0.5 rounded border ${qc.bg} ${qc.text} ${qc.border}`}>
            {paper.quality_level.toUpperCase()}
          </span>
          <span className="text-xs font-semibold text-navy">{fmt(paper.total_score)} / {fmt(paper.max_score)}</span>
          {paper.fully_scored
            ? <span className="text-xs text-green-600 font-medium">Fully scored</span>
            : <span className="text-xs text-amber-600 font-medium">
                {paper.scores.filter(s => s.score !== null).length}/{criteria.length} scored
              </span>
          }
          <span className="text-xs text-gray-400 ml-auto">{paper.paper_year}</span>
        </div>
        <h3 className="text-sm font-medium text-navy mt-1 leading-snug">{paper.paper_title}</h3>
        {paper.paper_authors && <p className="text-xs text-gray-400 mt-0.5 truncate">{paper.paper_authors}</p>}
      </div>
    </div>
  )
}

function QAScoringModal({ paper, criteria, pid, onClose }: {
  paper: QAPaperResult
  criteria: { id: number; label: string; description: string; max_score: number }[]
  pid: number
  onClose: () => void
}) {
  const qc = useQueryClient()
  const { reviewerId } = useProject()

  const { data: reviewers = [] } = useQuery({
    queryKey: ['reviewers', pid],
    queryFn: () => getReviewers(pid),
  })

  const activeReviewerId = reviewerId ?? reviewers.find(r => r.role === 'R1')?.id ?? reviewers[0]?.id

  // Local score state initialised from server data
  const [scores, setScores] = useState<Record<number, number | null>>(() => {
    const init: Record<number, number | null> = {}
    for (const s of paper.scores) {
      init[s.criterion_id] = s.score ?? null
    }
    return init
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const scoreMutation = useMutation({
    mutationFn: (data: { criterion_id: number; score: number }) =>
      upsertQAScore(pid, paper.paper_id, {
        reviewer_id: activeReviewerId!,
        criterion_id: data.criterion_id,
        score: data.score,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['qa-summary', pid] })
    },
  })

  const handleScoreChange = async (criterionId: number, score: number) => {
    setScores(prev => ({ ...prev, [criterionId]: score }))
    await scoreMutation.mutateAsync({ criterion_id: criterionId, score })
  }

  const handleSaveAll = async () => {
    if (!activeReviewerId) return
    setSaving(true)
    setSaved(false)
    try {
      for (const [cidStr, score] of Object.entries(scores)) {
        if (score !== null) {
          await upsertQAScore(pid, paper.paper_id, {
            reviewer_id: activeReviewerId,
            criterion_id: parseInt(cidStr),
            score,
          })
        }
      }
      qc.invalidateQueries({ queryKey: ['qa-summary', pid] })
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  const total = Object.entries(scores).reduce((sum, [cidStr, score]) => {
    if (score === null) return sum
    const crit = criteria.find(c => c.id === parseInt(cidStr))
    return sum + (score ?? 0)
  }, 0)
  const max = criteria.reduce((s, c) => s + c.max_score, 0)
  const pct = max > 0 ? (total / max * 100) : 0
  const level = pct >= 75 ? 'high' : pct >= 50 ? 'medium' : 'low'
  const levelColors = QUALITY_COLORS[level]

  return (
    <Modal title="Quality Assessment" onClose={onClose} width="max-w-2xl">
      <div className="bg-card rounded-md p-4 mb-4 border border-border">
        <p className="text-sm font-semibold text-navy mb-1">{paper.paper_title}</p>
        <p className="text-xs text-gray-400">{paper.paper_authors} · {paper.paper_year}</p>
      </div>

      <div className="space-y-4 mb-4">
        {criteria.map(criterion => {
          const currentScore = scores[criterion.id] ?? null
          const maxOpts: (0 | 0.5 | 1)[] = criterion.max_score >= 1 ? [0, 0.5, 1] : [0, 0.5]
          return (
            <div key={criterion.id} className="border border-border rounded-md p-3">
              <div className="flex items-start justify-between gap-2 mb-2">
                <div>
                  <p className="text-sm font-semibold text-navy">{criterion.label}</p>
                  <p className="text-xs text-gray-500">{criterion.description}</p>
                </div>
                {currentScore !== null && (
                  <span className={`text-xs font-bold px-2 py-0.5 rounded shrink-0 ${
                    currentScore === criterion.max_score ? 'bg-green-100 text-green-800' :
                    currentScore > 0 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800'
                  }`}>
                    {fmt(currentScore)} / {fmt(criterion.max_score)}
                  </span>
                )}
              </div>
              <div className="flex gap-2">
                {maxOpts.map(opt => (
                  <button
                    key={opt}
                    onClick={() => handleScoreChange(criterion.id, opt)}
                    className={`flex-1 py-2 text-sm font-semibold rounded-md border transition-all ${
                      currentScore === opt
                        ? opt === criterion.max_score ? 'bg-green-600 text-white border-green-600'
                          : opt > 0 ? 'bg-yellow-500 text-white border-yellow-500'
                          : 'bg-red-500 text-white border-red-500'
                        : 'bg-white text-navy-muted border-border hover:border-navy-muted'
                    }`}>
                    {opt === 0 ? '0 — No' : opt === 0.5 ? '0.5 — Partial' : '1 — Yes'}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {/* Running total */}
      <div className={`flex items-center gap-3 p-3 rounded-md border mb-4 ${levelColors.bg} ${levelColors.border}`}>
        <div className="flex-1">
          <p className="text-xs font-semibold text-gray-600 uppercase tracking-wider">Total Score</p>
          <p className={`text-lg font-bold ${levelColors.text}`}>{fmt(total)} / {fmt(max)}</p>
        </div>
        <span className={`text-sm font-bold px-3 py-1 rounded border ${levelColors.bg} ${levelColors.text} ${levelColors.border}`}>
          {level.toUpperCase()}
        </span>
      </div>

      {saved && <p className="text-xs text-green-600 mb-2">Scores saved.</p>}

      <div className="flex gap-2">
        <button className="btn-secondary flex-1 justify-center" onClick={onClose}>Close</button>
        <button className="btn-primary flex-1 justify-center" onClick={handleSaveAll} disabled={saving}>
          {saving ? 'Saving…' : 'Save All Scores'}
        </button>
      </div>
    </Modal>
  )
}

// ── Summary View ──────────────────────────────────────────────────────────────

function SummaryView({ pid }: { pid: number }) {
  const { data: summary, isLoading } = useQuery({
    queryKey: ['qa-summary', pid],
    queryFn: () => getQASummary(pid),
  })

  if (isLoading) return <p className="text-sm text-gray-400">Loading…</p>

  if (!summary || summary.papers.length === 0) {
    return <EmptyState icon="—" message="No papers to display. Score papers in the 'Score Papers' tab first." />
  }

  const high = summary.papers.filter(p => p.quality_level === 'high').length
  const medium = summary.papers.filter(p => p.quality_level === 'medium').length
  const low = summary.papers.filter(p => p.quality_level === 'low').length
  const avgScore = summary.papers.reduce((s, p) => s + p.total_score, 0) / summary.papers.length

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Avg. Score" value={fmt(avgScore)}
          sub={`out of ${summary.max_total} max`} />
        <StatCard label="High" value={high} color="include" />
        <StatCard label="Medium" value={medium} color="uncertain" />
        <StatCard label="Low" value={low} color="exclude" />
      </div>

      <Card>
        <CardHeader title="Papers Ranked by Quality Score" />
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-navy-muted uppercase tracking-wider border-b border-border">
              <th className="text-left pb-2 font-semibold">Paper</th>
              {summary.criteria.map(c => (
                <th key={c.id} className="text-center pb-2 font-semibold px-1 min-w-[3rem]" title={c.description}>{c.label}</th>
              ))}
              <th className="text-right pb-2 font-semibold">Score</th>
              <th className="text-right pb-2 font-semibold">Level</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {summary.papers.map(paper => {
              const qc = QUALITY_COLORS[paper.quality_level]
              return (
                <tr key={paper.paper_id} className="hover:bg-card transition-colors">
                  <td className="py-2 pr-3 max-w-[300px]">
                    <p className="text-sm font-medium text-navy leading-snug truncate">{paper.paper_title}</p>
                    <p className="text-xs text-gray-400">{paper.paper_authors?.split(',')[0]} · {paper.paper_year}</p>
                  </td>
                  {summary.criteria.map(c => {
                    const s = paper.scores.find(sc => sc.criterion_id === c.id)
                    const score = s?.score
                    return (
                      <td key={c.id} className="py-2 text-center px-1">
                        {score === null || score === undefined ? (
                          <span className="text-gray-300 text-xs">—</span>
                        ) : (
                          <span className={`text-xs font-bold ${
                            score === c.max_score ? 'text-green-600' :
                            score > 0 ? 'text-yellow-600' : 'text-red-500'
                          }`}>{score}</span>
                        )}
                      </td>
                    )
                  })}
                  <td className="py-2 text-right font-semibold text-navy whitespace-nowrap">
                    {fmt(paper.total_score)}/{fmt(paper.max_score)}
                  </td>
                  <td className="py-2 text-right">
                    <span className={`text-xs font-bold px-2 py-0.5 rounded border ${qc.bg} ${qc.text} ${qc.border}`}>
                      {paper.quality_level.toUpperCase()}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Card>

      {summary.criteria.length > 0 && (
        <Card>
          <CardHeader title="Quality Criteria" />
          <div className="space-y-0">
            {summary.criteria.map(c => (
              <div key={c.id} className="py-3 border-b border-border last:border-0 flex items-start gap-3">
                <span className="text-xs font-bold text-info bg-blue-50 border border-blue-200 rounded px-2 py-0.5 shrink-0 mt-0.5 w-[110px] truncate text-center inline-block" title={c.label}>{c.label}</span>
                <div className="flex-1">
                  <p className="text-sm text-navy">{c.description}</p>
                  <p className="text-xs text-gray-400 mt-0.5">Max score: {c.max_score}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
