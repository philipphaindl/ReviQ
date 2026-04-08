import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useProject } from '../App'
import { getExportStats, getQASummary, getExtractionSummary, exportBibtexUrl } from '../api/client'
import { Card, CardHeader, StatCard, EmptyState } from '../components/ui'

type ResView = 'prisma' | 'charts' | 'export'

export default function Results() {
  const { projectId } = useProject()
  const [view, setView] = useState<ResView>('prisma')

  if (!projectId) {
    return <EmptyState icon="—" message="No active project. Select one from the Overview." />
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-navy">Results & Visualization</h1>
        <p className="text-sm text-gray-500">Phase 8 — Synthesize and visualize your findings</p>
      </div>

      <div className="flex gap-0 border-b border-border">
        {(['prisma', 'charts', 'export'] as ResView[]).map(v => (
          <button key={v} onClick={() => setView(v)}
            className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors relative ${
              view === v
                ? 'text-info after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-info'
                : 'text-gray-400 hover:text-navy'
            }`}>
            {v === 'prisma' ? 'PRISMA Flow' : v === 'charts' ? 'Charts' : 'Export'}
          </button>
        ))}
      </div>

      {view === 'prisma'  && <PrismaView pid={projectId} />}
      {view === 'charts'  && <ChartsView pid={projectId} />}
      {view === 'export'  && <ExportView pid={projectId} />}
    </div>
  )
}

// ── PRISMA Flow View ──────────────────────────────────────────────────────────

function PrismaView({ pid }: { pid: number }) {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['export-stats', pid],
    queryFn: () => getExportStats(pid),
  })

  if (isLoading) return <p className="text-sm text-gray-400">Loading…</p>
  if (!stats) return null

  const screened = stats.total_unique
  const screeningExcluded = stats.screening_excluded
  const fulltextAssessed = stats.screening_included
  const fulltextExcluded = stats.fulltext_excluded
  const included = stats.fulltext_included > 0 ? stats.fulltext_included : stats.screening_included

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Total Retrieved" value={stats.total_retrieved} />
        <StatCard label="After Deduplication" value={stats.total_unique} />
        <StatCard label="Screened" value={screened} />
        <StatCard label="Included" value={included} color="include" />
      </div>

      <Card>
        <CardHeader title="PRISMA 2020 Flow Diagram" />
        <div className="overflow-x-auto">
          <PrismaFlowDiagram
            totalRetrieved={stats.total_retrieved}
            totalDuplicates={stats.total_duplicates}
            totalUnique={stats.total_unique}
            screeningExcluded={screeningExcluded}
            screened={screened}
            fulltextAssessed={fulltextAssessed}
            fulltextExcluded={fulltextExcluded}
            included={included}
          />
        </div>
      </Card>
    </div>
  )
}

function PrismaFlowDiagram({
  totalRetrieved, totalDuplicates, totalUnique,
  screened, screeningExcluded,
  fulltextAssessed, fulltextExcluded,
  included,
}: {
  totalRetrieved: number; totalDuplicates: number; totalUnique: number
  screened: number; screeningExcluded: number
  fulltextAssessed: number; fulltextExcluded: number
  included: number
}) {
  // Layout constants
  const W = 700
  const H = 580
  const boxW = 260
  const boxH = 52
  const sideBoxW = 180
  const cx = W / 2  // center x of main column
  const sideX = cx + boxW / 2 + 20  // left edge of exclusion boxes
  const arrowColor = '#94a3b8'
  const mainColor = '#1e3a5f'
  const sectionColor = '#e2e8f0'
  const sectionText = '#64748b'

  // Y positions for main boxes (center y)
  const y1 = 60   // Records identified
  const y2 = 150  // After dedup
  const y3 = 250  // Screened
  const y4 = 350  // Full-text assessed
  const y5 = 470  // Included

  const labelStyle = { fontSize: '11px', fill: sectionText, fontWeight: '600' as const, textTransform: 'uppercase' as const, letterSpacing: '0.08em' }
  const boxTextStyle = { fontSize: '12px', fill: mainColor, fontWeight: '500' as const }
  const nStyle = { fontSize: '13px', fill: mainColor, fontWeight: '700' as const }

  function MainBox({ cy, label, n }: { cy: number; label: string; n: number }) {
    return (
      <g>
        <rect x={cx - boxW / 2} y={cy - boxH / 2} width={boxW} height={boxH}
          rx={6} fill="white" stroke="#cbd5e1" strokeWidth={1.5} />
        <text x={cx} y={cy - 7} textAnchor="middle" style={boxTextStyle}>{label}</text>
        <text x={cx} y={cy + 12} textAnchor="middle" style={nStyle}>n = {n}</text>
      </g>
    )
  }

  function ExclusionBox({ cy, label, n }: { cy: number; label: string; n: number }) {
    if (n === 0) return null
    return (
      <g>
        <rect x={sideX} y={cy - boxH / 2} width={sideBoxW} height={boxH}
          rx={6} fill="#fef2f2" stroke="#fecaca" strokeWidth={1.5} />
        <text x={sideX + sideBoxW / 2} y={cy - 7} textAnchor="middle" style={{ ...boxTextStyle, fontSize: '11px', fill: '#dc2626' }}>{label}</text>
        <text x={sideX + sideBoxW / 2} y={cy + 12} textAnchor="middle" style={{ ...nStyle, fill: '#dc2626' }}>n = {n}</text>
        {/* Arrow from main column to exclusion box */}
        <line x1={cx + boxW / 2} y1={cy} x2={sideX} y2={cy}
          stroke="#fca5a5" strokeWidth={1.5} markerEnd="url(#arrowRed)" />
      </g>
    )
  }

  function DownArrow({ y1: y1a, y2: y2a }: { y1: number; y2: number }) {
    return (
      <line x1={cx} y1={y1a + boxH / 2} x2={cx} y2={y2a - boxH / 2}
        stroke={arrowColor} strokeWidth={1.5} markerEnd="url(#arrowGray)" />
    )
  }

  function SectionLabel({ y: yPos, label }: { y: number; label: string }) {
    const lW = 120
    return (
      <g>
        <rect x={cx - boxW / 2 - lW - 10} y={yPos - 14} width={lW} height={26}
          rx={4} fill={sectionColor} />
        <text x={cx - boxW / 2 - lW / 2 - 10} y={yPos + 5} textAnchor="middle" style={labelStyle}>{label}</text>
      </g>
    )
  }

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ maxWidth: '100%' }}>
      <defs>
        <marker id="arrowGray" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
          <path d="M0,0 L0,8 L8,4 z" fill={arrowColor} />
        </marker>
        <marker id="arrowRed" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
          <path d="M0,0 L0,8 L8,4 z" fill="#fca5a5" />
        </marker>
      </defs>

      {/* Section labels */}
      <SectionLabel y={y1} label="IDENTIFICATION" />
      <SectionLabel y={y3} label="SCREENING" />
      <SectionLabel y={y4} label="ELIGIBILITY" />
      <SectionLabel y={y5} label="INCLUDED" />

      {/* Main flow boxes */}
      <MainBox cy={y1} label="Records retrieved" n={totalRetrieved} />

      {/* Dedup note */}
      {totalDuplicates > 0 && (
        <g>
          <rect x={sideX} y={y1 + 10} width={sideBoxW} height={40}
            rx={6} fill="#f8fafc" stroke="#e2e8f0" strokeWidth={1} />
          <text x={sideX + sideBoxW / 2} y={y1 + 26} textAnchor="middle"
            style={{ fontSize: '11px', fill: '#64748b' }}>Duplicates removed</text>
          <text x={sideX + sideBoxW / 2} y={y1 + 42} textAnchor="middle"
            style={{ fontSize: '12px', fill: '#334155', fontWeight: '700' }}>n = {totalDuplicates}</text>
        </g>
      )}

      <DownArrow y1={y1} y2={y2} />
      <MainBox cy={y2} label="Records after deduplication" n={totalUnique} />

      <DownArrow y1={y2} y2={y3} />
      <MainBox cy={y3} label="Records screened" n={screened} />
      <ExclusionBox cy={y3} label="Excluded (title/abstract)" n={screeningExcluded} />

      <DownArrow y1={y3} y2={y4} />
      <MainBox cy={y4} label="Full texts assessed" n={fulltextAssessed} />
      <ExclusionBox cy={y4} label="Not eligible (full-text)" n={fulltextExcluded} />

      <DownArrow y1={y4} y2={y5} />

      {/* Included box — highlighted */}
      <rect x={cx - boxW / 2} y={y5 - boxH / 2} width={boxW} height={boxH}
        rx={6} fill="#f0fdf4" stroke="#86efac" strokeWidth={2} />
      <text x={cx} y={y5 - 7} textAnchor="middle" style={{ ...boxTextStyle, fill: '#15803d' }}>
        Studies included in review
      </text>
      <text x={cx} y={y5 + 12} textAnchor="middle" style={{ ...nStyle, fill: '#15803d', fontSize: '15px' }}>
        n = {included}
      </text>
    </svg>
  )
}

// ── Charts View ───────────────────────────────────────────────────────────────

function ChartsView({ pid }: { pid: number }) {
  const { data: qaSummary } = useQuery({
    queryKey: ['qa-summary', pid],
    queryFn: () => getQASummary(pid),
  })
  const { data: extSummary } = useQuery({
    queryKey: ['extraction-summary', pid],
    queryFn: () => getExtractionSummary(pid),
  })

  // Build year distribution from extraction summary or QA summary
  const yearMap: Record<number, number> = {}

  if (extSummary?.papers.length) {
    for (const p of extSummary.papers) {
      if (p.year) yearMap[p.year] = (yearMap[p.year] ?? 0) + 1
    }
  } else if (qaSummary?.papers.length) {
    for (const p of qaSummary.papers) {
      if (p.paper_year) yearMap[p.paper_year] = (yearMap[p.paper_year] ?? 0) + 1
    }
  }

  const years = Object.keys(yearMap).map(Number).sort((a, b) => a - b)
  const maxYearCount = Math.max(...Object.values(yearMap), 1)

  const qualityDist = qaSummary ? {
    high:   qaSummary.papers.filter(p => p.quality_level === 'high').length,
    medium: qaSummary.papers.filter(p => p.quality_level === 'medium').length,
    low:    qaSummary.papers.filter(p => p.quality_level === 'low').length,
  } : null

  const hasYearData = years.length > 0
  const hasQA = qualityDist !== null && (qualityDist.high + qualityDist.medium + qualityDist.low) > 0
  const hasExt = extSummary && extSummary.fields.length > 0 && extSummary.papers.length > 0

  if (!hasYearData && !hasQA && !hasExt) {
    return <EmptyState icon="—" message="No data available yet. Complete screening or quality assessment to see charts." />
  }

  return (
    <div className="space-y-4">
      {/* Publications by year */}
      {hasYearData && (
        <Card>
          <CardHeader title="Publications per Year" />
          <div className="space-y-1.5 pt-1">
            {years.map(y => {
              const count = yearMap[y]
              const pct = Math.round((count / maxYearCount) * 100)
              return (
                <div key={y} className="flex items-center gap-3">
                  <span className="text-xs text-navy font-mono w-10 shrink-0 text-right">{y}</span>
                  <div className="flex-1 bg-gray-100 rounded-full h-5 relative">
                    <div
                      className="bg-info h-5 rounded-full transition-all flex items-center justify-end pr-2"
                      style={{ width: `${Math.max(pct, 4)}%` }}
                    >
                      <span className="text-xs font-bold text-white">{count}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Quality distribution */}
      {hasQA && qualityDist && (
        <Card>
          <CardHeader title="Quality Assessment Distribution" />
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="bg-green-50 border border-green-200 rounded-md p-3 text-center">
              <p className="text-xs text-green-700 font-semibold uppercase tracking-wider">High</p>
              <p className="text-2xl font-bold text-green-700 mt-1">{qualityDist.high}</p>
            </div>
            <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3 text-center">
              <p className="text-xs text-yellow-700 font-semibold uppercase tracking-wider">Medium</p>
              <p className="text-2xl font-bold text-yellow-700 mt-1">{qualityDist.medium}</p>
            </div>
            <div className="bg-red-50 border border-red-200 rounded-md p-3 text-center">
              <p className="text-xs text-red-700 font-semibold uppercase tracking-wider">Low</p>
              <p className="text-2xl font-bold text-red-700 mt-1">{qualityDist.low}</p>
            </div>
          </div>
          {/* Stacked bar */}
          {(() => {
            const total = qualityDist.high + qualityDist.medium + qualityDist.low
            if (total === 0) return null
            return (
              <div className="flex h-5 rounded-full overflow-hidden gap-0.5">
                {qualityDist.high > 0 && (
                  <div className="bg-green-500 flex items-center justify-center text-white text-xs font-bold transition-all"
                    style={{ width: `${qualityDist.high / total * 100}%` }}>
                    {qualityDist.high > 1 ? qualityDist.high : ''}
                  </div>
                )}
                {qualityDist.medium > 0 && (
                  <div className="bg-yellow-400 flex items-center justify-center text-white text-xs font-bold transition-all"
                    style={{ width: `${qualityDist.medium / total * 100}%` }}>
                    {qualityDist.medium > 1 ? qualityDist.medium : ''}
                  </div>
                )}
                {qualityDist.low > 0 && (
                  <div className="bg-red-400 flex items-center justify-center text-white text-xs font-bold transition-all"
                    style={{ width: `${qualityDist.low / total * 100}%` }}>
                    {qualityDist.low > 1 ? qualityDist.low : ''}
                  </div>
                )}
              </div>
            )
          })()}
        </Card>
      )}

      {/* Extraction completion */}
      {hasExt && extSummary && (
        <Card>
          <CardHeader title="Extraction Completion" />
          <div className="grid grid-cols-3 gap-3">
            <StatCard label="Papers" value={extSummary.papers.length} />
            <StatCard label="Fully Extracted"
              value={extSummary.papers.filter(p => p.filled === p.total_fields).length}
              color="include" />
            <StatCard label="Fields Defined" value={extSummary.fields.length} />
          </div>
        </Card>
      )}
    </div>
  )
}

// ── Export View ───────────────────────────────────────────────────────────────

function ExportView({ pid }: { pid: number }) {
  const { data: stats } = useQuery({
    queryKey: ['export-stats', pid],
    queryFn: () => getExportStats(pid),
  })

  const exports: { label: string; description: string; href: string; count: number }[] = [
    {
      label: 'Included Papers (Full-Text)',
      description: 'BibTeX file of papers included after full-text eligibility assessment',
      href: exportBibtexUrl(pid, 'full-text', 'I'),
      count: stats?.fulltext_included ?? 0,
    },
    {
      label: 'Included Papers (Screening)',
      description: 'BibTeX file of papers included after title/abstract screening',
      href: exportBibtexUrl(pid, 'screening', 'I'),
      count: stats?.screening_included ?? 0,
    },
    {
      label: 'Excluded Papers (Full-Text)',
      description: 'BibTeX file of papers excluded at full-text stage',
      href: exportBibtexUrl(pid, 'full-text', 'E'),
      count: stats?.fulltext_excluded ?? 0,
    },
  ]

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="BibTeX Exports" />
        <div className="space-y-0">
          {exports.map(e => (
            <div key={e.label} className="py-3 border-b border-border last:border-0 flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-navy">{e.label}</p>
                <p className="text-xs text-gray-400 mt-0.5">{e.description}</p>
              </div>
              <span className="text-xs text-gray-500 shrink-0">n = {e.count}</span>
              <a
                href={e.count > 0 ? e.href : undefined}
                download
                className={`btn-secondary text-xs shrink-0 ${e.count === 0 ? 'opacity-40 pointer-events-none' : ''}`}
              >
                ↓ .bib
              </a>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <CardHeader title="Summary Statistics" />
        {stats ? (
          <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
            <StatRow label="Total records retrieved" value={stats.total_retrieved} />
            <StatRow label="Unique records (after dedup)" value={stats.total_unique} />
            <StatRow label="Duplicates removed" value={stats.total_duplicates} />
            <StatRow label="Records screened" value={stats.total_unique} />
            <StatRow label="Screening: included" value={stats.screening_included} />
            <StatRow label="Screening: excluded" value={stats.screening_excluded} />
            <StatRow label="Full-text assessed" value={stats.screening_included} />
            <StatRow label="Full-text: included" value={stats.fulltext_included} />
            <StatRow label="Full-text: excluded" value={stats.fulltext_excluded} />
            <StatRow label="Open conflicts" value={stats.open_conflicts} />
          </div>
        ) : (
          <p className="text-sm text-gray-400">Loading…</p>
        )}
      </Card>
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between py-1 border-b border-border last:border-0">
      <span className="text-gray-600">{label}</span>
      <span className="font-semibold text-navy">{value}</span>
    </div>
  )
}
