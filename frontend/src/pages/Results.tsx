import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { useProject } from '../App'
import { getExportStats, getQASummary, getExtractionSummary, exportBibtexUrl, getImportStats, getPapers } from '../api/client'
import { Card, CardHeader, StatCard, EmptyState } from '../components/ui'
import type { ExtractionField } from '../api/types'

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
        <p className="text-sm text-gray-500">Phase 8 — Results Synthesis and Visualization</p>
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
  const { data: importStats } = useQuery({
    queryKey: ['import-stats', pid],
    queryFn: () => getImportStats(pid),
  })
  const { data: screeningPapers = [] } = useQuery({
    queryKey: ['papers', pid, 'screening'],
    queryFn: () => getPapers(pid, { phase: 'screening' }),
  })
  const { data: fulltextPapers = [] } = useQuery({
    queryKey: ['papers', pid, 'full-text'],
    queryFn: () => getPapers(pid, { phase: 'full-text' }),
  })

  if (isLoading) return <p className="text-sm text-gray-400">Loading…</p>
  if (!stats) return null

  const screened = stats.total_unique
  const screeningExcluded = stats.screening_excluded
  const fulltextAssessed = stats.screening_included
  const fulltextExcluded = stats.fulltext_excluded
  const included = stats.fulltext_included > 0 ? stats.fulltext_included : stats.screening_included

  // Per-DB counts from import stats
  const bySource = importStats?.by_source ?? {}

  // Per-criterion exclusion breakdowns (client-side from paper decisions)
  const screeningExclusionByCriterion: Record<string, number> = {}
  for (const p of screeningPapers) {
    if (p.dedup_status === 'original' && p.final_decision?.decision === 'E') {
      const crit = p.decisions?.[0]?.criterion_label ?? 'Other'
      screeningExclusionByCriterion[crit] = (screeningExclusionByCriterion[crit] ?? 0) + 1
    }
  }
  const fulltextExclusionByCriterion: Record<string, number> = {}
  for (const p of fulltextPapers) {
    if (p.final_decision?.decision === 'E') {
      const crit = p.decisions?.[0]?.criterion_label ?? 'Other'
      fulltextExclusionByCriterion[crit] = (fulltextExclusionByCriterion[crit] ?? 0) + 1
    }
  }

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
            bySource={bySource}
            screeningExclusionByCriterion={screeningExclusionByCriterion}
            fulltextExclusionByCriterion={fulltextExclusionByCriterion}
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
  included, bySource,
  screeningExclusionByCriterion, fulltextExclusionByCriterion,
}: {
  totalRetrieved: number; totalDuplicates: number; totalUnique: number
  screened: number; screeningExcluded: number
  fulltextAssessed: number; fulltextExcluded: number
  included: number
  bySource: Record<string, { total: number; original: number; duplicate: number }>
  screeningExclusionByCriterion: Record<string, number>
  fulltextExclusionByCriterion: Record<string, number>
}) {
  // Layout constants
  const W = 720
  const boxW = 260
  const boxH = 52
  const sideBoxW = 190
  const cx = 300  // center x of main column
  const sideX = cx + boxW / 2 + 20  // left edge of exclusion boxes
  const arrowColor = '#94a3b8'
  const mainColor = '#1e3a5f'
  const sectionColor = '#e2e8f0'
  const sectionText = '#64748b'

  // Determine exclusion box heights based on criterion counts
  const screenCritEntries = Object.entries(screeningExclusionByCriterion)
  const ftCritEntries = Object.entries(fulltextExclusionByCriterion)
  const screenExclBoxH = screeningExcluded > 0
    ? boxH + Math.max(0, screenCritEntries.length - 0) * 14
    : 0
  const ftExclBoxH = fulltextExcluded > 0
    ? boxH + Math.max(0, ftCritEntries.length - 0) * 14
    : 0

  // Source entries for identification box — exclude snowballing iterations
  const sourceEntries = Object.entries(bySource)
    .filter(([src, v]) => !src.startsWith('snowballing:') && v.total > 0)
  const identBoxH = boxH + Math.max(0, sourceEntries.length) * 14

  // Y positions for main boxes (center y)
  const y1 = identBoxH / 2 + 10   // Records identified
  const y2 = y1 + identBoxH / 2 + 40 + boxH / 2  // After dedup
  const y3 = y2 + boxH / 2 + 40 + boxH / 2  // Screened
  const y4 = y3 + Math.max(boxH / 2, screenExclBoxH / 2) + 40 + boxH / 2  // Full-text assessed
  const y5 = y4 + Math.max(boxH / 2, ftExclBoxH / 2) + 40 + boxH / 2  // Included
  const H = y5 + boxH / 2 + 20

  const labelStyle = { fontSize: '11px', fill: sectionText, fontWeight: '600' as const, textTransform: 'uppercase' as const, letterSpacing: '0.08em' }
  const boxTextStyle = { fontSize: '12px', fill: mainColor, fontWeight: '500' as const }
  const nStyle = { fontSize: '13px', fill: mainColor, fontWeight: '700' as const }
  const smallStyle = { fontSize: '10px', fill: '#64748b' }

  function MainBox({ cy, label, n, children }: { cy: number; label: string; n: number; children?: ReactNode }) {
    const h = children ? identBoxH : boxH
    return (
      <g>
        <rect x={cx - boxW / 2} y={cy - h / 2} width={boxW} height={h}
          rx={6} fill="white" stroke="#cbd5e1" strokeWidth={1.5} />
        <text x={cx} y={cy - h / 2 + 18} textAnchor="middle" style={boxTextStyle}>{label}</text>
        <text x={cx} y={cy - h / 2 + 34} textAnchor="middle" style={nStyle}>n = {n}</text>
        {children}
      </g>
    )
  }

  function ExclusionBox({ cy, label, n, criteria }: { cy: number; label: string; n: number; criteria: Record<string, number> }) {
    if (n === 0) return null
    const critEntries = Object.entries(criteria)
    const h = boxH + critEntries.length * 14
    const boxTop = cy - h / 2
    return (
      <g>
        <rect x={sideX} y={boxTop} width={sideBoxW} height={h}
          rx={6} fill="#fef2f2" stroke="#fecaca" strokeWidth={1.5} />
        <text x={sideX + sideBoxW / 2} y={boxTop + 18} textAnchor="middle" style={{ ...boxTextStyle, fontSize: '11px', fill: '#dc2626' }}>{label}</text>
        <text x={sideX + sideBoxW / 2} y={boxTop + 34} textAnchor="middle" style={{ ...nStyle, fill: '#dc2626' }}>n = {n}</text>
        {critEntries.map(([crit, count], i) => (
          <text key={crit} x={sideX + 8} y={boxTop + 50 + i * 14} style={{ ...smallStyle, fill: '#dc2626' }}>
            • {crit}: {count}
          </text>
        ))}
        {/* Arrow from main column border to exclusion box border */}
        <line x1={cx + boxW / 2} y1={cy} x2={sideX - 6} y2={cy}
          stroke="#fca5a5" strokeWidth={1.5} markerEnd="url(#arrowRed)" />
      </g>
    )
  }

  function DownArrow({ fromY, toY }: { fromY: number; toY: number }) {
    return (
      <line x1={cx} y1={fromY} x2={cx} y2={toY - 6}
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
        <marker id="arrowGray" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L0,8 L8,4 z" fill={arrowColor} />
        </marker>
        <marker id="arrowRed" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L0,8 L8,4 z" fill="#fca5a5" />
        </marker>
      </defs>

      {/* Section labels */}
      <SectionLabel y={y1} label="IDENTIFICATION" />
      <SectionLabel y={y3} label="SCREENING" />
      <SectionLabel y={y4} label="ELIGIBILITY" />
      <SectionLabel y={y5} label="INCLUDED" />

      {/* Identification box with per-DB breakdown */}
      <MainBox cy={y1} label="Records retrieved" n={totalRetrieved}>
        {sourceEntries.map(([src, v], i) => (
          <text key={src} x={cx} y={y1 - identBoxH / 2 + 50 + i * 14} textAnchor="middle"
            style={{ ...smallStyle }}>
            {src}: {v.total} ({v.original} unique)
          </text>
        ))}
      </MainBox>

      {/* Dedup note */}
      {totalDuplicates > 0 && (
        <g>
          <rect x={sideX} y={y1 - 20} width={sideBoxW} height={40}
            rx={6} fill="#f8fafc" stroke="#e2e8f0" strokeWidth={1} />
          <text x={sideX + sideBoxW / 2} y={y1 - 4} textAnchor="middle"
            style={{ fontSize: '11px', fill: '#64748b' }}>Duplicates removed</text>
          <text x={sideX + sideBoxW / 2} y={y1 + 12} textAnchor="middle"
            style={{ fontSize: '12px', fill: '#334155', fontWeight: '700' }}>n = {totalDuplicates}</text>
        </g>
      )}

      <DownArrow fromY={y1 + identBoxH / 2} toY={y2 - boxH / 2} />
      <MainBox cy={y2} label="Records after deduplication" n={totalUnique} />

      <DownArrow fromY={y2 + boxH / 2} toY={y3 - boxH / 2} />
      <MainBox cy={y3} label="Records screened" n={screened} />
      <ExclusionBox cy={y3} label="Excluded (title/abstract)" n={screeningExcluded} criteria={screeningExclusionByCriterion} />

      <DownArrow fromY={y3 + Math.max(boxH / 2, screenExclBoxH / 2)} toY={y4 - boxH / 2} />
      <MainBox cy={y4} label="Full texts assessed" n={fulltextAssessed} />
      <ExclusionBox cy={y4} label="Not eligible (full-text)" n={fulltextExcluded} criteria={fulltextExclusionByCriterion} />

      <DownArrow fromY={y4 + Math.max(boxH / 2, ftExclBoxH / 2)} toY={y5 - boxH / 2} />

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

function PieChart({ data }: { data: { label: string; value: number; color: string }[] }) {
  const total = data.reduce((s, d) => s + d.value, 0)
  if (total === 0) return null

  const size = 130
  const cx = size / 2
  const cy = size / 2
  const r = 50

  let currentAngle = -Math.PI / 2
  const slices = data.map(d => {
    const angle = (d.value / total) * 2 * Math.PI
    const start = currentAngle
    currentAngle += angle
    return { ...d, start, end: currentAngle, angle }
  })

  const arcPath = (start: number, end: number, radius: number) => {
    const x1 = cx + radius * Math.cos(start)
    const y1 = cy + radius * Math.sin(start)
    const x2 = cx + radius * Math.cos(end)
    const y2 = cy + radius * Math.sin(end)
    const large = end - start > Math.PI ? 1 : 0
    return `M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${large} 1 ${x2} ${y2} Z`
  }

  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
        {slices.map((s, i) => (
          <path key={i} d={arcPath(s.start, s.end, r)} fill={s.color} stroke="white" strokeWidth={1.5} />
        ))}
      </svg>
      <div className="space-y-1.5 flex-1">
        {data.map(d => (
          <div key={d.label} className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: d.color }} />
            <span className="text-xs text-navy flex-1">{d.label}</span>
            <span className="text-xs font-semibold text-navy">{d.value}</span>
            <span className="text-xs text-gray-400">({Math.round(d.value / total * 100)}%)</span>
          </div>
        ))}
      </div>
    </div>
  )
}

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

  // Quality distribution
  const qualityDist = qaSummary ? {
    high:   qaSummary.papers.filter(p => p.quality_level === 'high').length,
    medium: qaSummary.papers.filter(p => p.quality_level === 'medium').length,
    low:    qaSummary.papers.filter(p => p.quality_level === 'low').length,
  } : null
  const qaTotal = qualityDist ? qualityDist.high + qualityDist.medium + qualityDist.low : 0

  // Taxonomy/dropdown field distributions from extraction data
  const dropdownFields: ExtractionField[] = extSummary?.fields.filter(f => f.field_type === 'dropdown') ?? []
  const fieldDists: { field: ExtractionField; dist: Record<string, number> }[] = dropdownFields.map(f => {
    const dist: Record<string, number> = {}
    for (const p of extSummary?.papers ?? []) {
      const val = p.values[f.field_name]
      if (val) dist[val] = (dist[val] ?? 0) + 1
    }
    return { field: f, dist }
  }).filter(d => Object.keys(d.dist).length > 0)

  const PIE_COLORS = ['#2563eb', '#16a34a', '#d97706', '#dc2626', '#7c3aed', '#0891b2', '#db2777', '#65a30d']

  const hasYearData = years.length > 0
  const hasQA = qaTotal > 0
  const hasTaxonomy = fieldDists.length > 0

  if (!hasYearData && !hasQA && !hasTaxonomy) {
    return <EmptyState icon="—" message="No data available yet. Complete screening or quality assessment to see charts." />
  }

  return (
    <div className="space-y-4">
      {/* Publications per year */}
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
                  <div className="flex-1 bg-gray-100 rounded-md h-6 relative">
                    <div className="bg-info h-6 rounded-md transition-all flex items-center justify-end pr-2"
                      style={{ width: `${Math.max(pct, 4)}%` }}>
                      <span className="text-xs font-bold text-white">{count}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Quality assessment bar chart with percentages */}
      {hasQA && qualityDist && (
        <Card>
          <CardHeader title="Quality Assessment Distribution" />
          <div className="space-y-2 pt-1">
            {[
              { label: 'High', count: qualityDist.high, color: 'bg-green-500', textColor: 'text-green-700' },
              { label: 'Medium', count: qualityDist.medium, color: 'bg-yellow-400', textColor: 'text-yellow-700' },
              { label: 'Low', count: qualityDist.low, color: 'bg-red-400', textColor: 'text-red-700' },
            ].map(row => {
              const pct = qaTotal > 0 ? Math.round(row.count / qaTotal * 100) : 0
              return (
                <div key={row.label} className="flex items-center gap-3">
                  <span className={`text-xs font-semibold w-14 shrink-0 ${row.textColor}`}>{row.label}</span>
                  <div className="flex-1 bg-gray-100 rounded-md h-6 relative">
                    <div className={`${row.color} h-6 rounded-md transition-all flex items-center justify-end pr-2`}
                      style={{ width: `${Math.max(pct, pct > 0 ? 6 : 0)}%` }}>
                      {pct >= 10 && <span className="text-xs font-bold text-white">{pct}%</span>}
                    </div>
                  </div>
                  <span className="text-xs text-gray-500 shrink-0 w-16 text-right">{row.count} paper{row.count !== 1 ? 's' : ''} ({pct}%)</span>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Taxonomy/dropdown field pie charts */}
      {hasTaxonomy && fieldDists.map(({ field, dist }) => {
        const entries = Object.entries(dist).sort((a, b) => b[1] - a[1])
        const pieData = entries.map(([ label, value ], i) => ({
          label, value, color: PIE_COLORS[i % PIE_COLORS.length],
        }))
        return (
          <Card key={field.field_name}>
            <CardHeader title={field.field_label} />
            <PieChart data={pieData} />
          </Card>
        )
      })}
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
    <div className="flex justify-between py-1 border-b border-border">
      <span className="text-gray-600">{label}</span>
      <span className="font-semibold text-navy">{value}</span>
    </div>
  )
}
