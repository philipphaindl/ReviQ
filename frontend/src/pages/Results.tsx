/**
 * Results & Visualization (Phase 8) — PRISMA flow diagram, charts, and export.
 * PRISMA is inline SVG with two parallel streams (DB search + snowballing).
 */
import { useQuery } from '@tanstack/react-query'
import { useState, useRef, useCallback, useEffect, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { useProject } from '../App'
import { getExportStats, getQASummary, getExtractionSummary, exportBibtexUrl, getImportStats, getPapers, getTaxonomyTypes, exportReplicationPackageUrl, getSearchMetrics, getExclusionCriteria } from '../api/client'
import { Card, CardHeader, StatBar, StatCell, EmptyState } from '../components/ui'
import { normalizeDbKey, dbByKey, DatabaseBadge } from '../components/databases'
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
        <h1 className="text-xl font-bold text-ink font-display">Results & Visualization</h1>
        <p className="text-sm text-ink-muted">Phase 8 — Results Synthesis and Visualization</p>
      </div>

      <div className="flex gap-0 border-b border-rule">
        {(['prisma', 'charts', 'export'] as ResView[]).map(v => (
          <button key={v} onClick={() => setView(v)}
            className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-label transition-colors relative ${
              view === v
                ? 'text-info after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-info'
                : 'text-ink-muted hover:text-ink'
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
  const { data: exclusionCriteria = [] } = useQuery({
    queryKey: ['exclusion', pid],
    queryFn: () => getExclusionCriteria(pid),
  })

  // Map criterion label (e.g. "E1") → short_label for PRISMA diagram display
  const shortLabelMap: Record<string, string> = {}
  for (const c of exclusionCriteria) {
    if (c.short_label) shortLabelMap[c.label] = c.short_label
  }

  if (isLoading) return <p className="text-sm text-ink-muted">Loading…</p>
  if (!stats) return null

  const bySource = importStats?.by_source ?? {}

  // ── DB stream ───────────────────────────────────────────────────────────────
  const dbRetrieved = Object.entries(bySource)
    .filter(([src]) => !src.startsWith('snowballing:'))
    .reduce((s, [, v]) => s + v.total, 0)
  const dbUnique = screeningPapers.filter(
    p => !p.source?.startsWith('snowballing:') && p.dedup_status === 'original'
  ).length
  const dbDuplicates = Math.max(0, dbRetrieved - dbUnique)
  const dbScreeningExcluded = screeningPapers.filter(
    p => !p.source?.startsWith('snowballing:') && p.dedup_status === 'original' && p.final_decision?.decision === 'E'
  ).length
  const dbFTAssessed = screeningPapers.filter(
    p => !p.source?.startsWith('snowballing:') && p.dedup_status === 'original' && p.final_decision?.decision === 'I'
  ).length
  const dbFTExcluded = fulltextPapers.filter(
    p => !p.source?.startsWith('snowballing:') && p.final_decision?.decision === 'E'
  ).length
  const dbFTIncluded = fulltextPapers.filter(
    p => !p.source?.startsWith('snowballing:') && p.final_decision?.decision === 'I'
  ).length
  const dbScrExclByCrit: Record<string, number> = {}
  for (const p of screeningPapers) {
    if (!p.source?.startsWith('snowballing:') && p.dedup_status === 'original' && p.final_decision?.decision === 'E') {
      const c = p.decisions?.[0]?.criterion_label ?? 'Other'
      dbScrExclByCrit[c] = (dbScrExclByCrit[c] ?? 0) + 1
    }
  }
  const dbFTExclByCrit: Record<string, number> = {}
  for (const p of fulltextPapers) {
    if (!p.source?.startsWith('snowballing:') && p.final_decision?.decision === 'E') {
      const c = p.decisions?.[0]?.criterion_label ?? 'Other'
      dbFTExclByCrit[c] = (dbFTExclByCrit[c] ?? 0) + 1
    }
  }

  // ── Snowball stream ─────────────────────────────────────────────────────────
  const snowballRetrieved = Object.entries(bySource)
    .filter(([src]) => src.startsWith('snowballing:'))
    .reduce((s, [, v]) => s + v.total, 0)
  const snowballScreenedPapers = screeningPapers.filter(
    p => p.source?.startsWith('snowballing:') && p.dedup_status === 'original'
  )
  const snowballScreened = snowballScreenedPapers.length
  const snowballScrExcluded = snowballScreenedPapers.filter(p => p.final_decision?.decision === 'E').length
  // fulltextPapers returns ALL papers with their FT decisions (null if not yet reviewed).
  // Filter to snowballing papers that HAVE an actual FT decision recorded.
  const snowballFTPapers = fulltextPapers.filter(
    p => p.source?.startsWith('snowballing:') && p.final_decision !== null
  )
  const snowballFTAssessed = snowballFTPapers.length
  const snowballFTExcluded = snowballFTPapers.filter(p => p.final_decision?.decision === 'E').length
  const snowballFTIncluded = snowballFTPapers.filter(p => p.final_decision?.decision === 'I').length
  const snowballScrExclByCrit: Record<string, number> = {}
  for (const p of snowballScreenedPapers) {
    if (p.final_decision?.decision === 'E') {
      const c = p.decisions?.[0]?.criterion_label ?? 'Other'
      snowballScrExclByCrit[c] = (snowballScrExclByCrit[c] ?? 0) + 1
    }
  }
  const snowballFTExclByCrit: Record<string, number> = {}
  for (const p of snowballFTPapers) {
    if (p.final_decision?.decision === 'E') {
      const c = p.decisions?.[0]?.criterion_label ?? 'Other'
      snowballFTExclByCrit[c] = (snowballFTExclByCrit[c] ?? 0) + 1
    }
  }

  // Combined for stat cards
  const included = (dbFTIncluded + snowballFTIncluded) > 0
    ? dbFTIncluded + snowballFTIncluded
    : stats.screening_included

  return (
    <div className="space-y-4">
      <StatBar>
        <StatCell label="Total Retrieved" value={stats.total_retrieved} />
        <StatCell label="After Deduplication" value={dbUnique} />
        <StatCell label="Screened" value={dbUnique} />
        <StatCell label="Included" value={included} color="include" />
      </StatBar>

      <Card>
        <CardHeader title="PRISMA 2020 Flow Diagram"
          action={<PrismaSvgDownload />}
        />
        <div className="overflow-x-auto">
          <PrismaFlowDiagram
            dbRetrieved={dbRetrieved}
            dbDuplicates={dbDuplicates}
            dbUnique={dbUnique}
            dbScreeningExcluded={dbScreeningExcluded}
            dbFTAssessed={dbFTAssessed}
            dbFTExcluded={dbFTExcluded}
            dbFTIncluded={dbFTIncluded > 0 ? dbFTIncluded : snowballFTIncluded === 0 ? dbFTAssessed : dbFTIncluded}
            bySource={bySource}
            dbScrExclByCrit={dbScrExclByCrit}
            dbFTExclByCrit={dbFTExclByCrit}
            snowballRetrieved={snowballRetrieved}
            snowballScreened={snowballScreened}
            snowballScrExcluded={snowballScrExcluded}
            snowballFTAssessed={snowballFTAssessed}
            snowballFTExcluded={snowballFTExcluded}
            snowballFTIncluded={snowballFTIncluded}
            snowballScrExclByCrit={snowballScrExclByCrit}
            snowballFTExclByCrit={snowballFTExclByCrit}
            shortLabelMap={shortLabelMap}
          />
        </div>
      </Card>
    </div>
  )
}

// ── Grayscale SVG conversion ──────────────────────────────────────────────────
// ITU-R BT.601 luma: gray = 0.299R + 0.587G + 0.114B

function toGrayscaleSvg(svgStr: string): string {
  // Convert #rrggbb hex colors
  const hexConverted = svgStr.replace(/#([0-9a-fA-F]{6})\b/g, (_match, hex: string) => {
    const r = parseInt(hex.slice(0, 2), 16)
    const g = parseInt(hex.slice(2, 4), 16)
    const b = parseInt(hex.slice(4, 6), 16)
    const gray = Math.round(0.299 * r + 0.587 * g + 0.114 * b)
    const h = gray.toString(16).padStart(2, '0')
    return `#${h}${h}${h}`
  })
  // Convert rgb(r,g,b) colors
  return hexConverted.replace(/rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)/g,
    (_match, rs: string, gs: string, bs: string) => {
      const gray = Math.round(0.299 * Number(rs) + 0.587 * Number(gs) + 0.114 * Number(bs))
      return `rgb(${gray},${gray},${gray})`
    }
  )
}

function downloadPrismaSvg(grayscale: boolean) {
  const svg = document.getElementById('prisma-svg') as SVGSVGElement | null
  if (!svg) return
  let svgStr = '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(svg)
  if (grayscale) svgStr = toGrayscaleSvg(svgStr)
  const blob = new Blob([svgStr], { type: 'image/svg+xml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = grayscale ? 'prisma_flow_grayscale.svg' : 'prisma_flow.svg'
  a.click()
  URL.revokeObjectURL(url)
}

function PrismaSvgDownload() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button className="btn-secondary flex items-center gap-1.5"
        onClick={() => setOpen(o => !o)}>
        ↓ SVG
        <svg width="10" height="6" viewBox="0 0 10 6" fill="none" className={`transition-transform ${open ? 'rotate-180' : ''}`}>
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-44 rounded-lg border border-rule bg-surface shadow-lg z-20 py-1 text-xs">
          <button className="w-full text-left px-3 py-2 hover:bg-paper transition-colors text-ink flex items-center gap-2"
            onClick={() => { downloadPrismaSvg(false); setOpen(false) }}>
            <span className="w-3 h-3 rounded-sm border border-rule" style={{
              background: 'linear-gradient(135deg, #1e3a5f 25%, #22c55e 50%, #d97706 75%)'
            }} />
            Color
          </button>
          <button className="w-full text-left px-3 py-2 hover:bg-paper transition-colors text-ink flex items-center gap-2"
            onClick={() => { downloadPrismaSvg(true); setOpen(false) }}>
            <span className="w-3 h-3 rounded-sm border border-rule" style={{
              background: 'linear-gradient(135deg, #444 25%, #999 50%, #bbb 75%)'
            }} />
            Grayscale
          </button>
        </div>
      )}
    </div>
  )
}

// Two-column layout when snowballing exists, single column otherwise.
// Y positions cascade top-to-bottom; each row accounts for the tallest
// exclusion box at that level (criteria count varies per box).
function PrismaFlowDiagram({
  dbRetrieved, dbDuplicates, dbUnique,
  dbScreeningExcluded, dbFTAssessed, dbFTExcluded, dbFTIncluded,
  bySource, dbScrExclByCrit, dbFTExclByCrit,
  snowballRetrieved, snowballScreened, snowballScrExcluded,
  snowballFTAssessed, snowballFTExcluded, snowballFTIncluded,
  snowballScrExclByCrit, snowballFTExclByCrit,
  shortLabelMap,
}: {
  dbRetrieved: number; dbDuplicates: number; dbUnique: number
  dbScreeningExcluded: number; dbFTAssessed: number; dbFTExcluded: number; dbFTIncluded: number
  bySource: Record<string, { total: number; original: number; duplicate: number }>
  dbScrExclByCrit: Record<string, number>; dbFTExclByCrit: Record<string, number>
  snowballRetrieved: number; snowballScreened: number; snowballScrExcluded: number
  snowballFTAssessed: number; snowballFTExcluded: number; snowballFTIncluded: number
  snowballScrExclByCrit: Record<string, number>; snowballFTExclByCrit: Record<string, number>
  shortLabelMap: Record<string, string>
}) {
  const hasSnowball = snowballRetrieved > 0 || snowballScreened > 0

  // Layout
  const GAP = 40
  const boxH = 52
  const W = hasSnowball ? 970 : 755
  const boxW = hasSnowball ? 200 : 260
  const cx1 = hasSnowball ? 240 : 310
  const cx2 = 660
  const excl1X = cx1 + boxW / 2 + 20
  const excl2X = cx2 + boxW / 2 + 20
  const exclW = hasSnowball ? 180 : 215

  // Publication-safe colors (all pass grayscale + WCAG AA)
  const arrowColor = '#6b7280'          // medium gray — darker than before for print
  const arrowRedColor = '#d97706'       // amber — distinct from blue in grayscale AND colorblind-safe
  const mainColor = '#1e3a5f'           // dark navy
  const sectionColor = '#e2e8f0'
  const sectionText = '#475569'
  // Inter matches the app's UI font; system-ui fallback keeps standalone SVG portable
  const FONT = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif'

  const sourceEntries = Object.entries(bySource)
    .filter(([src, v]) => !src.startsWith('snowballing:') && v.total > 0)

  const identBoxH = boxH + Math.max(0, sourceEntries.length) * 14
  const screenExclH  = dbScreeningExcluded > 0  ? boxH + Object.keys(dbScrExclByCrit).length * 14 : 0
  const ftExclH      = dbFTExcluded > 0          ? boxH + Object.keys(dbFTExclByCrit).length * 14 : 0
  const snoScrExclH  = snowballScrExcluded > 0   ? boxH + Object.keys(snowballScrExclByCrit).length * 14 : 0
  const snoFTExclH   = snowballFTExcluded > 0    ? boxH + Object.keys(snowballFTExclByCrit).length * 14 : 0

  // Y positions
  const Y_TOP = hasSnowball ? 28 : 12
  const db_ident_cy = Y_TOP + identBoxH / 2
  const db_dedup_cy = db_ident_cy + identBoxH / 2 + GAP + boxH / 2
  const shared_screened_cy = db_dedup_cy + boxH / 2 + GAP + boxH / 2
  const shared_ft_cy = shared_screened_cy
    + Math.max(boxH / 2, screenExclH / 2, hasSnowball ? snoScrExclH / 2 : 0) + GAP + boxH / 2
  const shared_incl_cy = shared_ft_cy
    + Math.max(boxH / 2, ftExclH / 2, hasSnowball ? snoFTExclH / 2 : 0) + GAP + boxH / 2
  const combined_cy = hasSnowball ? shared_incl_cy + boxH / 2 + GAP + boxH / 2 : 0

  // ── Legend: collect all unique criterion labels across both streams ──────────
  // Merges all four criterion maps; displays full label since these ARE the labels
  // (if your project uses short codes like E1/E2, see Option B: pass criteriaNames prop)
  const H = (hasSnowball ? combined_cy : shared_incl_cy) + boxH / 2 + 24

  const snow_ident_cy = Y_TOP + boxH / 2

  // Text styles — all include fontFamily for standalone SVG portability
  const labelStyle = {
    fontSize: '10px', fill: sectionText, fontWeight: '700' as const,
    textTransform: 'uppercase' as const, letterSpacing: '0.09em', fontFamily: FONT,
  }
  const boxTextStyle = { fontSize: '11.5px', fill: mainColor, fontWeight: '400' as const, fontFamily: FONT }
  const nStyle = { fontSize: '13px', fill: mainColor, fontWeight: '700' as const, fontFamily: FONT }
  const smallStyle = { fontSize: '9.5px', fill: '#475569', fontFamily: FONT }

  function SectionLabel({ y: yPos, label }: { y: number; label: string }) {
    const lW = hasSnowball ? 116 : 124
    const xLeft = hasSnowball ? 8 : cx1 - boxW / 2 - lW - 10
    return (
      <g>
        <rect x={xLeft} y={yPos - 15} width={lW} height={30} rx={4}
          fill={sectionColor} stroke="#cbd5e1" strokeWidth={0.75} />
        <text x={xLeft + lW / 2} y={yPos + 4} textAnchor="middle" style={labelStyle}>{label}</text>
      </g>
    )
  }

  function MainBox({ cx, cy, h = boxH, label, n, stroke = '#93aec8', fill = '#f7fafd', textFill = mainColor, children }: {
    cx: number; cy: number; h?: number; label: string; n: number
    stroke?: string; fill?: string; textFill?: string; children?: ReactNode
  }) {
    return (
      <g>
        <rect x={cx - boxW / 2} y={cy - h / 2} width={boxW} height={h}
          rx={5} fill={fill} stroke={stroke} strokeWidth={1.5} />
        <text x={cx} y={cy - h / 2 + 19} textAnchor="middle" style={{ ...boxTextStyle, fill: textFill }}>{label}</text>
        <text x={cx} y={cy - h / 2 + 36} textAnchor="middle" style={{ ...nStyle, fill: textFill }}>n = {n}</text>
        {children}
      </g>
    )
  }

  function ExclusionBox({ fromCx, cy, exclX, label, n, criteria }: {
    fromCx: number; cy: number; exclX: number; label: string; n: number; criteria: Record<string, number>
  }) {
    if (n === 0) return null
    const entries = Object.entries(criteria)
    const h = boxH + Math.max(entries.length, 1) * 14
    const top = cy - h / 2
    // Dashed red border → distinguishable in grayscale without relying on color alone
    return (
      <g>
        <rect x={exclX} y={top} width={exclW} height={h}
          rx={5} fill="#fff8f0" stroke="#c0392b" strokeWidth={1.5} strokeDasharray="5,3" />
        <text x={exclX + exclW / 2} y={top + 18} textAnchor="middle"
          style={{ ...boxTextStyle, fontSize: '10.5px', fill: '#c0392b', fontWeight: '600' as const }}>{label}</text>
        <text x={exclX + exclW / 2} y={top + 34} textAnchor="middle"
          style={{ ...nStyle, fill: '#c0392b' }}>n = {n}</text>
        {entries.map(([crit, count], i) => {
          const shortLabel = shortLabelMap[crit]
          const display = shortLabel ? `${crit} ${shortLabel}` : crit
          return (
            <text key={crit} x={exclX + 8} y={top + 50 + i * 14}
              style={{ ...smallStyle, fill: '#b45309' }}>• {display}: {count}</text>
          )
        })}
        {/* Horizontal arrow: tip lands at exclusion box left edge via refX="8" */}
        <line
          x1={fromCx + boxW / 2} y1={cy}
          x2={exclX} y2={cy}
          stroke={arrowRedColor} strokeWidth={1.5} markerEnd="url(#arrowAmber)"
        />
      </g>
    )
  }

  function DownArrow({ cx, fromY, toY }: { cx: number; fromY: number; toY: number }) {
    if (toY - fromY <= 8) return null
    // Line runs to the box edge exactly; arrowhead tip placed there via refX="8" in marker
    return (
      <line x1={cx} y1={fromY} x2={cx} y2={toY}
        stroke={arrowColor} strokeWidth={1.5} markerEnd="url(#arrowGray)" />
    )
  }

  return (
    // xmlns is required for standalone SVG files (copy-paste into Illustrator / LaTeX)
    <svg
      id="prisma-svg"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-labelledby="prisma-title prisma-desc"
      width={W} height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ maxWidth: '100%', fontFamily: FONT }}
    >
      {/* Accessibility — required for WCAG 2.1 AA in publications */}
      <title id="prisma-title">PRISMA 2020 Flow Diagram</title>
      <desc id="prisma-desc">
        Systematic literature review flow diagram following the PRISMA 2020 statement,
        showing records identified, screened, assessed for eligibility, and included.
      </desc>

      <defs>
        {/* refX="8" = tip of polygon, so arrowhead lands flush at line endpoint; markerUnits="strokeWidth" scales with stroke */}
        <marker id="arrowGray" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="strokeWidth">
          <polygon points="0,1 0,8 8,4.5" fill={arrowColor} />
        </marker>
        <marker id="arrowAmber" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="strokeWidth">
          <polygon points="0,1 0,8 8,4.5" fill={arrowRedColor} />
        </marker>
      </defs>

      {/* Column headers */}
      {hasSnowball && (
        <>
          <text x={cx1} y={16} textAnchor="middle"
            style={{ fontSize: '10px', fill: mainColor, fontWeight: '700', letterSpacing: '0.07em',
                     textTransform: 'uppercase' as const, fontFamily: FONT }}>
            Database Search
          </text>
          <text x={cx2} y={16} textAnchor="middle"
            style={{ fontSize: '10px', fill: mainColor, fontWeight: '700', letterSpacing: '0.07em',
                     textTransform: 'uppercase' as const, fontFamily: FONT }}>
            Other Methods
          </text>
          {/* Vertical divider — longer dash for cleaner print reproduction */}
          <line x1={(cx1 + cx2) / 2} y1={22} x2={(cx1 + cx2) / 2} y2={H - 24}
            stroke="#c8d4e0" strokeWidth={1} strokeDasharray="6,4" />
        </>
      )}

      {/* Section labels */}
      <SectionLabel y={db_ident_cy} label="IDENTIFICATION" />
      <SectionLabel y={shared_screened_cy} label="SCREENING" />
      <SectionLabel y={shared_ft_cy} label="ELIGIBILITY" />
      <SectionLabel y={hasSnowball ? combined_cy : shared_incl_cy} label="INCLUDED" />

      {/* ── DB STREAM ── */}

      {/* DB identification box — slightly tinted fill for visual hierarchy */}
      <MainBox cx={cx1} cy={db_ident_cy} h={identBoxH} label="Records from databases" n={dbRetrieved}>
        {sourceEntries.map(([src, v], i) => {
          const label = dbByKey(normalizeDbKey(src))?.label ?? src
          return (
            <text key={src} x={cx1} y={db_ident_cy - identBoxH / 2 + 52 + i * 14}
              textAnchor="middle" style={smallStyle}>
              {label}: {v.total} ({v.original} unique)
            </text>
          )
        })}
      </MainBox>

      {/* Duplicates removed — positioned alongside the identification→dedup arrow,
          with a connecting horizontal line for PRISMA 2020 conformance */}
      {dbDuplicates > 0 && (() => {
        // Midpoint on the vertical arrow between ident and dedup boxes
        const arrowMidY = (db_ident_cy + identBoxH / 2 + db_dedup_cy - boxH / 2) / 2
        const dedupBoxH = 42
        const dedupBoxW = exclW
        return (
          <g>
            <rect x={excl1X} y={arrowMidY - dedupBoxH / 2} width={dedupBoxW} height={dedupBoxH}
              rx={5} fill="#f1f5f9" stroke="#94a3b8" strokeWidth={1}
              strokeDasharray="5,3" />
            <text x={excl1X + dedupBoxW / 2} y={arrowMidY - 4} textAnchor="middle"
              style={{ ...smallStyle, fill: '#475569' }}>Duplicates removed</text>
            <text x={excl1X + dedupBoxW / 2} y={arrowMidY + 12} textAnchor="middle"
              style={{ fontSize: '12px', fill: '#334155', fontWeight: '700', fontFamily: FONT }}>n = {dbDuplicates}</text>
            {/* Horizontal connecting line from main flow */}
            <line x1={cx1 + boxW / 2} y1={arrowMidY} x2={excl1X - 2} y2={arrowMidY}
              stroke="#94a3b8" strokeWidth={1} strokeDasharray="3,2" />
          </g>
        )
      })()}

      <DownArrow cx={cx1} fromY={db_ident_cy + identBoxH / 2} toY={db_dedup_cy - boxH / 2} />
      <MainBox cx={cx1} cy={db_dedup_cy} label="Records after deduplication" n={dbUnique} />

      <DownArrow cx={cx1} fromY={db_dedup_cy + boxH / 2} toY={shared_screened_cy - boxH / 2} />
      <MainBox cx={cx1} cy={shared_screened_cy} label="Records screened" n={dbUnique} />
      <ExclusionBox fromCx={cx1} cy={shared_screened_cy} exclX={excl1X}
        label="Excluded (title/abstract)" n={dbScreeningExcluded} criteria={dbScrExclByCrit} />

      <DownArrow cx={cx1}
        fromY={shared_screened_cy + boxH / 2}
        toY={shared_ft_cy - boxH / 2} />
      <MainBox cx={cx1} cy={shared_ft_cy} label="Full texts assessed" n={dbFTAssessed} />
      <ExclusionBox fromCx={cx1} cy={shared_ft_cy} exclX={excl1X}
        label="Not eligible (full-text)" n={dbFTExcluded} criteria={dbFTExclByCrit} />

      <DownArrow cx={cx1}
        fromY={shared_ft_cy + boxH / 2}
        toY={shared_incl_cy - boxH / 2} />

      {hasSnowball ? (
        <MainBox cx={cx1} cy={shared_incl_cy} label="Included (databases)" n={dbFTIncluded} />
      ) : (
        /* Single stream: green "Studies included" final box */
        <g>
          <rect x={cx1 - boxW / 2} y={shared_incl_cy - boxH / 2} width={boxW} height={boxH}
            rx={5} fill="#f0fdf4" stroke="#22c55e" strokeWidth={2} />
          <text x={cx1} y={shared_incl_cy - 6} textAnchor="middle"
            style={{ ...boxTextStyle, fill: '#166534' }}>Studies included in review</text>
          <text x={cx1} y={shared_incl_cy + 13} textAnchor="middle"
            style={{ ...nStyle, fill: '#166534', fontSize: '15px' }}>n = {dbFTIncluded}</text>
        </g>
      )}

      {/* ── SNOWBALL STREAM ── */}
      {hasSnowball && (
        <>
          <g>
            <rect x={cx2 - boxW / 2} y={snow_ident_cy - boxH / 2} width={boxW} height={boxH}
              rx={5} fill="#f7fafd" stroke="#93aec8" strokeWidth={1.5} />
            <text x={cx2} y={snow_ident_cy - 6} textAnchor="middle" style={boxTextStyle}>Records via snowballing</text>
            <text x={cx2} y={snow_ident_cy + 13} textAnchor="middle" style={nStyle}>n = {snowballRetrieved}</text>
          </g>

          <DownArrow cx={cx2} fromY={snow_ident_cy + boxH / 2} toY={shared_screened_cy - boxH / 2} />

          <g>
            <rect x={cx2 - boxW / 2} y={shared_screened_cy - boxH / 2} width={boxW} height={boxH}
              rx={5} fill="#f7fafd" stroke="#93aec8" strokeWidth={1.5} />
            <text x={cx2} y={shared_screened_cy - 6} textAnchor="middle" style={boxTextStyle}>Records screened</text>
            <text x={cx2} y={shared_screened_cy + 13} textAnchor="middle" style={nStyle}>n = {snowballScreened}</text>
          </g>
          {snowballScrExcluded > 0 && (
            <ExclusionBox fromCx={cx2} cy={shared_screened_cy} exclX={excl2X}
              label="Excluded (screening)" n={snowballScrExcluded} criteria={snowballScrExclByCrit} />
          )}

          <DownArrow cx={cx2}
            fromY={shared_screened_cy + boxH / 2}
            toY={shared_ft_cy - boxH / 2} />

          <g>
            <rect x={cx2 - boxW / 2} y={shared_ft_cy - boxH / 2} width={boxW} height={boxH}
              rx={5} fill="#f7fafd" stroke="#93aec8" strokeWidth={1.5} />
            <text x={cx2} y={shared_ft_cy - 6} textAnchor="middle" style={boxTextStyle}>Full texts assessed</text>
            <text x={cx2} y={shared_ft_cy + 13} textAnchor="middle" style={nStyle}>n = {snowballFTAssessed}</text>
          </g>
          {snowballFTExcluded > 0 && (
            <ExclusionBox fromCx={cx2} cy={shared_ft_cy} exclX={excl2X}
              label="Not eligible (full-text)" n={snowballFTExcluded} criteria={snowballFTExclByCrit} />
          )}

          <DownArrow cx={cx2}
            fromY={shared_ft_cy + boxH / 2}
            toY={shared_incl_cy - boxH / 2} />

          <g>
            <rect x={cx2 - boxW / 2} y={shared_incl_cy - boxH / 2} width={boxW} height={boxH}
              rx={5} fill="#f7fafd" stroke="#93aec8" strokeWidth={1.5} />
            <text x={cx2} y={shared_incl_cy - 6} textAnchor="middle" style={boxTextStyle}>Included (snowballing)</text>
            <text x={cx2} y={shared_incl_cy + 13} textAnchor="middle" style={nStyle}>n = {snowballFTIncluded}</text>
          </g>

          {/* Convergence arrows: both included boxes → combined final box */}
          <line x1={cx1} y1={shared_incl_cy + boxH / 2} x2={cx1} y2={shared_incl_cy + boxH / 2 + 22}
            stroke={arrowColor} strokeWidth={1.5} />
          <line x1={cx2} y1={shared_incl_cy + boxH / 2} x2={cx2} y2={shared_incl_cy + boxH / 2 + 22}
            stroke={arrowColor} strokeWidth={1.5} />
          <line x1={cx1} y1={shared_incl_cy + boxH / 2 + 22} x2={cx2} y2={shared_incl_cy + boxH / 2 + 22}
            stroke={arrowColor} strokeWidth={1.5} />
          <line x1={(cx1 + cx2) / 2} y1={shared_incl_cy + boxH / 2 + 22}
            x2={(cx1 + cx2) / 2} y2={combined_cy - boxH / 2}
            stroke={arrowColor} strokeWidth={1.5} markerEnd="url(#arrowGray)" />

          {/* Combined final box — wider, green, prominent */}
          <rect x={(cx1 + cx2) / 2 - boxW * 0.85} y={combined_cy - boxH / 2}
            width={boxW * 1.7} height={boxH}
            rx={5} fill="#f0fdf4" stroke="#22c55e" strokeWidth={2} />
          <text x={(cx1 + cx2) / 2} y={combined_cy - 6} textAnchor="middle"
            style={{ ...boxTextStyle, fill: '#166534' }}>Studies included in review</text>
          <text x={(cx1 + cx2) / 2} y={combined_cy + 13} textAnchor="middle"
            style={{ ...nStyle, fill: '#166534', fontSize: '15px' }}>
            n = {dbFTIncluded + snowballFTIncluded}
          </text>
        </>
      )}

    </svg>
  )
}

// ── Venue name cleanup ────────────────────────────────────────────────────────
// Strips common verbose prefixes from conference/journal names so the chart
// shows the essential name rather than "Proceedings of the Nth Annual ..."

function cleanVenueName(raw: string): string {
  let s = raw
  s = s.replace(/^Proceedings of (the )?/i, '')
  s = s.replace(/^\d+(st|nd|rd|th) /i, '')
  s = s.replace(/^Annual /i, '')
  s = s.replace(/^the /i, '')
  return s.trim()
}

// ── CSV download helper ───────────────────────────────────────────────────────

function downloadCsv(filename: string, headers: string[], rows: (string | number | null)[][]) {
  const escape = (v: string | number | null) => `"${String(v ?? '').replace(/"/g, '""')}"`
  const lines = [headers.map(escape).join(','), ...rows.map(r => r.map(escape).join(','))]
  const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

// ── Charts View ───────────────────────────────────────────────────────────────

function PieChart({ data }: { data: { label: string; value: number; color: string }[] }) {
  const total = data.reduce((s, d) => s + d.value, 0)
  if (total === 0) return null

  const size = 140
  const cx = size / 2
  const cy = size / 2
  const r = 54

  let currentAngle = -Math.PI / 2
  const slices = data.map(d => {
    const angle = (d.value / total) * 2 * Math.PI
    const start = currentAngle
    currentAngle += angle
    const mid = start + angle / 2
    return { ...d, start, end: currentAngle, angle, mid }
  })

  const arcPath = (start: number, end: number) => {
    const x1 = cx + r * Math.cos(start)
    const y1 = cy + r * Math.sin(start)
    const x2 = cx + r * Math.cos(end)
    const y2 = cy + r * Math.sin(end)
    const large = end - start > Math.PI ? 1 : 0
    return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`
  }

  return (
    <div className="flex items-start gap-5">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0 }}>
        {slices.map((s, i) => (
          <g key={i}>
            {s.angle >= Math.PI * 2 - 0.001
              ? <circle cx={cx} cy={cy} r={r} fill={s.color} />
              : <path d={arcPath(s.start, s.end)} fill={s.color} stroke="white" strokeWidth={1.5} />
            }
            {s.angle > 0.3 && (
              <text x={cx + r * 0.64 * Math.cos(s.mid)} y={cy + r * 0.64 * Math.sin(s.mid) + 4}
                textAnchor="middle"
                style={{ fontSize: '10px', fill: 'white', fontWeight: '700', pointerEvents: 'none' as const }}>
                {Math.round(s.value / total * 100)}%
              </text>
            )}
          </g>
        ))}
      </svg>
      <div className="space-y-2 flex-1 min-w-0 pt-1">
        {data.map(d => {
          const pct = Math.round(d.value / total * 100)
          return (
            <div key={d.label} className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: d.color }} />
              <span className="text-xs text-ink flex-1 min-w-0 truncate" title={d.label}>{d.label}</span>
              <span className="text-xs font-bold text-ink">{d.value}</span>
              <span className="text-xs text-ink-muted w-12 text-right">({pct}%)</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ChartsView({ pid }: { pid: number }) {
  const { data: searchMetrics } = useQuery({
    queryKey: ['search-metrics', pid],
    queryFn: () => getSearchMetrics(pid),
  })
  const { data: qaSummary } = useQuery({
    queryKey: ['qa-summary', pid],
    queryFn: () => getQASummary(pid),
  })
  const { data: extSummary } = useQuery({
    queryKey: ['extraction-summary', pid],
    queryFn: () => getExtractionSummary(pid),
  })
  const { data: ftPapers = [] } = useQuery({
    queryKey: ['papers', pid, 'full-text'],
    queryFn: () => getPapers(pid, { phase: 'full-text' }),
  })
  const { data: taxonomyTypes = [] } = useQuery({
    queryKey: ['taxonomy-types', pid],
    queryFn: () => getTaxonomyTypes(pid),
  })

  // Publications per year
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

  // Key venues — from full-text included papers
  const venueMap: Record<string, number> = {}
  for (const p of ftPapers) {
    if (p.final_decision?.decision === 'I' && p.venue) {
      venueMap[p.venue] = (venueMap[p.venue] ?? 0) + 1
    }
  }
  const venues = Object.entries(venueMap).sort((a, b) => b[1] - a[1]).slice(0, 10)
  const maxVenueCount = Math.max(...venues.map(([, n]) => n), 1)

  // Taxonomy type distributions — values stored in paper.values[taxType] by the extraction modal
  const taxTypeLabel = (key: string) =>
    key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  const taxonomyDists: { key: string; label: string; dist: Record<string, number> }[] = taxonomyTypes.map(type => {
    const dist: Record<string, number> = {}
    for (const p of extSummary?.papers ?? []) {
      const val = p.values[type]
      if (val) dist[val] = (dist[val] ?? 0) + 1
    }
    return { key: type, label: taxTypeLabel(type), dist }
  }).filter(d => Object.keys(d.dist).length > 0)

  // Extraction dropdown field distributions (excluding fields that overlap with taxonomy keys)
  const taxKeySet = new Set(taxonomyTypes)
  const dropdownFields: ExtractionField[] = extSummary?.fields.filter(
    f => f.field_type === 'dropdown' && !taxKeySet.has(f.field_name)
  ) ?? []
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
  const hasVenues = venues.length > 0
  const hasTaxonomy = taxonomyDists.length > 0 || fieldDists.length > 0
  const hasMetrics = (searchMetrics?.databases.length ?? 0) > 0

  if (!hasYearData && !hasQA && !hasVenues && !hasTaxonomy && !hasMetrics) {
    return <EmptyState icon="—" message="No data available yet. Complete screening or quality assessment to see charts." />
  }

  return (
    <div className="space-y-4">
      {/* Search database metrics: precision / recall / F1 */}
      {hasMetrics && searchMetrics && (
        <Card>
          <CardHeader
            title="Search Database Metrics"
            action={
              <button className="btn-secondary"
                onClick={() => downloadCsv(
                  'search_metrics.csv',
                  ['Database', 'DB Results', 'Imported (unique)', 'Included', 'Precision', 'Recall', 'F1'],
                  searchMetrics.databases.map(d => [
                    d.db_name,
                    d.results_count ?? d.imported,
                    d.imported,
                    d.included,
                    d.precision, d.relative_recall, d.f1,
                  ])
                )}>
                ↓ CSV
              </button>
            }
          />
          <p className="text-xs text-ink-muted mb-3">
            Precision = included / DB results &nbsp;·&nbsp;
            Recall = included from DB / total included ({searchMetrics.total_included}) &nbsp;·&nbsp;
            F1 = harmonic mean &nbsp;·&nbsp;
            <em>DB Results</em> uses the recorded search count when available, otherwise imported unique papers
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-rule text-left text-ink-muted">
                  <th className="pb-2 pr-4 font-medium">Database</th>
                  <th className="pb-2 pr-4 font-medium text-right">DB Results</th>
                  <th className="pb-2 pr-4 font-medium text-right">Imported</th>
                  <th className="pb-2 pr-4 font-medium text-right">Included</th>
                  <th className="pb-2 pr-4 font-medium text-right">Precision</th>
                  <th className="pb-2 pr-4 font-medium text-right">Recall</th>
                  <th className="pb-2 font-medium text-right">F1</th>
                </tr>
              </thead>
              <tbody>
                {searchMetrics.databases.map(d => (
                  <tr key={d.db_name} className="border-b border-gray-50 hover:bg-paper">
                    <td className="py-1.5 pr-4"><DatabaseBadge dbKey={d.db_name} size="md" width="140px" /></td>
                    <td className="py-1.5 pr-4 text-right">
                      {d.results_count != null ? d.results_count : <span className="text-ink-muted">{d.imported}</span>}
                    </td>
                    <td className="py-1.5 pr-4 text-right text-ink-muted">{d.imported}</td>
                    <td className="py-1.5 pr-4 text-right">{d.included}</td>
                    <td className="py-1.5 pr-4 text-right">{(d.precision * 100).toFixed(1)}%</td>
                    <td className="py-1.5 pr-4 text-right">{(d.relative_recall * 100).toFixed(1)}%</td>
                    <td className="py-1.5 text-right font-semibold">{(d.f1 * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Publications per year */}
      {hasYearData && (
        <Card>
          <CardHeader title="Publications per Year"
            action={
              <button className="btn-secondary"
                onClick={() => downloadCsv('publications_per_year.csv', ['Year', 'Count'],
                  years.map(y => [y, yearMap[y]]))}>
                ↓ CSV
              </button>
            }
          />
          <div className="pt-2 overflow-x-auto">
            {(() => {
              const barW = 28
              const gap = 6
              const maxBarH = 110
              const countH = 18  // space above bars for count labels
              const labelH = 38  // space below bars for rotated year labels
              const svgH = countH + maxBarH + labelH
              const svgW = Math.max(years.length * (barW + gap) + gap, 200)
              return (
                <svg width={svgW} height={svgH} style={{ display: 'block' }}>
                  {years.map((y, i) => {
                    const count = yearMap[y]
                    const barH = Math.max(Math.round((count / maxYearCount) * maxBarH), 3)
                    const x = gap + i * (barW + gap)
                    const barY = countH + (maxBarH - barH)
                    const labelX = x + barW / 2
                    const labelY = countH + maxBarH + 6
                    return (
                      <g key={y}>
                        <rect x={x} y={barY} width={barW} height={barH} rx={3} fill="#2563eb" />
                        <text x={x + barW / 2} y={barY - 3} textAnchor="middle"
                          style={{ fontSize: '9px', fill: '#1a1a2e', fontWeight: 700, fontFamily: '"Plus Jakarta Sans", system-ui, sans-serif' }}>
                          {count}
                        </text>
                        <text x={labelX} y={labelY} textAnchor="end"
                          transform={`rotate(-55 ${labelX} ${labelY})`}
                          style={{ fontSize: '9px', fill: '#8888a4', fontFamily: '"Plus Jakarta Sans", system-ui, sans-serif' }}>
                          {y}
                        </text>
                      </g>
                    )
                  })}
                </svg>
              )
            })()}
          </div>
        </Card>
      )}

      {/* Key venues */}
      {hasVenues && (
        <Card>
          <CardHeader title="Key Venues"
            action={
              <button className="btn-secondary"
                onClick={() => downloadCsv('key_venues.csv', ['Venue', 'Count'],
                  venues.map(([v, n]) => [cleanVenueName(v), n]))}>
                ↓ CSV
              </button>
            }
          />
          <div className="space-y-1.5 pt-1">
            {venues.map(([venue, count]) => {
              const pct = Math.round((count / maxVenueCount) * 100)
              const displayName = cleanVenueName(venue)
              return (
                <div key={venue} className="flex items-center gap-3">
                  <span className="text-xs text-ink-light w-56 shrink-0 truncate" title={venue}>{displayName}</span>
                  <div className="flex-1 bg-rule/30 rounded-md h-6 relative">
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

      {/* All pie charts in a responsive grid: QA + taxonomy types + dropdown fields */}
      {(() => {
        const qaPieData = qualityDist ? [
          { label: 'High',   value: qualityDist.high,   color: '#16a34a' },
          { label: 'Medium', value: qualityDist.medium, color: '#d97706' },
          { label: 'Low',    value: qualityDist.low,    color: '#dc2626' },
        ].filter(d => d.value > 0) : []

        const allPieCharts: { key: string; title: string; data: { label: string; value: number; color: string }[]; csvRows: (string | number)[][] }[] = [
          ...(qaPieData.length > 0 ? [{
            key: 'qa',
            title: 'Quality Assessment',
            data: qaPieData,
            csvRows: qaPieData.map(d => [d.label, d.value, Math.round(d.value / qaTotal * 100)] as (string | number)[]),
          }] : []),
          ...taxonomyDists.map(({ key, label, dist }) => {
            const entries = Object.entries(dist).sort((a, b) => b[1] - a[1])
            const t = entries.reduce((s, [, n]) => s + n, 0)
            return {
              key, title: label,
              data: entries.map(([lbl, value], i) => ({ label: lbl, value, color: PIE_COLORS[i % PIE_COLORS.length] })),
              csvRows: entries.map(([v, n]) => [v, n, Math.round(n / t * 100)] as (string | number)[]),
            }
          }),
          ...fieldDists.map(({ field, dist }) => {
            const entries = Object.entries(dist).sort((a, b) => b[1] - a[1])
            const t = entries.reduce((s, [, n]) => s + n, 0)
            return {
              key: field.field_name, title: field.field_label,
              data: entries.map(([lbl, value], i) => ({ label: lbl, value, color: PIE_COLORS[i % PIE_COLORS.length] })),
              csvRows: entries.map(([v, n]) => [v, n, Math.round(n / t * 100)] as (string | number)[]),
            }
          }),
        ]

        if (allPieCharts.length === 0) return null
        return (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {allPieCharts.map(chart => (
              <Card key={chart.key}>
                <CardHeader title={chart.title}
                  action={
                    <button className="btn-secondary"
                      onClick={() => downloadCsv(`${chart.key}.csv`, ['Value', 'Count', 'Percentage (%)'], chart.csvRows)}>
                      ↓ CSV
                    </button>
                  }
                />
                <PieChart data={chart.data} />
              </Card>
            ))}
          </div>
        )
      })()}
    </div>
  )
}

// ── Export View ───────────────────────────────────────────────────────────────

function ExportView({ pid }: { pid: number }) {
  const [pdfLoading, setPdfLoading] = useState(false)
  const { data: stats } = useQuery({
    queryKey: ['export-stats', pid],
    queryFn: () => getExportStats(pid),
  })
  const { data: extSummary } = useQuery({
    queryKey: ['extraction-summary', pid],
    queryFn: () => getExtractionSummary(pid),
  })

  // Queries for off-screen PRISMA rendering
  const { data: importStats } = useQuery({ queryKey: ['import-stats', pid], queryFn: () => getImportStats(pid) })
  const { data: screeningPapers = [] } = useQuery({ queryKey: ['papers', pid, 'screening'], queryFn: () => getPapers(pid, { phase: 'screening' }) })
  const { data: fulltextPapers = [] } = useQuery({ queryKey: ['papers', pid, 'full-text'], queryFn: () => getPapers(pid, { phase: 'full-text' }) })
  const { data: exclusionCriteria = [] } = useQuery({ queryKey: ['exclusion', pid], queryFn: () => getExclusionCriteria(pid) })

  /** Grab the PRISMA SVG from the DOM if mounted, otherwise render off-screen and serialize. */
  const getPrismaSvg = useCallback(async (): Promise<string | null> => {
    // 1. Already in DOM?
    let svgEl = document.getElementById('prisma-svg') as SVGSVGElement | null
    if (svgEl) {
      return new XMLSerializer().serializeToString(svgEl)
    }

    // 2. Render off-screen
    if (!stats || !importStats) return null
    const bySource = importStats.by_source ?? {}
    const shortLabelMap: Record<string, string> = {}
    for (const c of exclusionCriteria) { if (c.short_label) shortLabelMap[c.label] = c.short_label }

    const dbRetrieved = Object.entries(bySource).filter(([s]) => !s.startsWith('snowballing:')).reduce((a, [, v]) => a + v.total, 0)
    const dbUnique = screeningPapers.filter(p => !p.source?.startsWith('snowballing:') && p.dedup_status === 'original').length
    const dbDuplicates = Math.max(0, dbRetrieved - dbUnique)
    const dbScreeningExcluded = screeningPapers.filter(p => !p.source?.startsWith('snowballing:') && p.dedup_status === 'original' && p.final_decision?.decision === 'E').length
    const dbFTAssessed = screeningPapers.filter(p => !p.source?.startsWith('snowballing:') && p.dedup_status === 'original' && p.final_decision?.decision === 'I').length
    const dbFTExcluded = fulltextPapers.filter(p => !p.source?.startsWith('snowballing:') && p.final_decision?.decision === 'E').length
    const dbFTIncluded = fulltextPapers.filter(p => !p.source?.startsWith('snowballing:') && p.final_decision?.decision === 'I').length
    const dbScrExclByCrit: Record<string, number> = {}
    for (const p of screeningPapers) { if (!p.source?.startsWith('snowballing:') && p.dedup_status === 'original' && p.final_decision?.decision === 'E') { const c = p.decisions?.[0]?.criterion_label ?? 'Other'; dbScrExclByCrit[c] = (dbScrExclByCrit[c] ?? 0) + 1 } }
    const dbFTExclByCrit: Record<string, number> = {}
    for (const p of fulltextPapers) { if (!p.source?.startsWith('snowballing:') && p.final_decision?.decision === 'E') { const c = p.decisions?.[0]?.criterion_label ?? 'Other'; dbFTExclByCrit[c] = (dbFTExclByCrit[c] ?? 0) + 1 } }
    const snowballRetrieved = Object.entries(bySource).filter(([s]) => s.startsWith('snowballing:')).reduce((a, [, v]) => a + v.total, 0)
    const snowballScreenedPapers = screeningPapers.filter(p => p.source?.startsWith('snowballing:') && p.dedup_status === 'original')
    const snowballScreened = snowballScreenedPapers.length
    const snowballScrExcluded = snowballScreenedPapers.filter(p => p.final_decision?.decision === 'E').length
    const snowballFTPapers = fulltextPapers.filter(p => p.source?.startsWith('snowballing:') && p.final_decision !== null)
    const snowballFTAssessed = snowballFTPapers.length
    const snowballFTExcluded = snowballFTPapers.filter(p => p.final_decision?.decision === 'E').length
    const snowballFTIncluded = snowballFTPapers.filter(p => p.final_decision?.decision === 'I').length
    const snowballScrExclByCrit: Record<string, number> = {}
    for (const p of snowballScreenedPapers) { if (p.final_decision?.decision === 'E') { const c = p.decisions?.[0]?.criterion_label ?? 'Other'; snowballScrExclByCrit[c] = (snowballScrExclByCrit[c] ?? 0) + 1 } }
    const snowballFTExclByCrit: Record<string, number> = {}
    for (const p of snowballFTPapers) { if (p.final_decision?.decision === 'E') { const c = p.decisions?.[0]?.criterion_label ?? 'Other'; snowballFTExclByCrit[c] = (snowballFTExclByCrit[c] ?? 0) + 1 } }

    const container = document.createElement('div')
    container.style.cssText = 'position:absolute;left:-9999px;top:0;width:1200px'
    document.body.appendChild(container)
    const root = createRoot(container)
    root.render(
      <PrismaFlowDiagram
        dbRetrieved={dbRetrieved} dbDuplicates={dbDuplicates} dbUnique={dbUnique}
        dbScreeningExcluded={dbScreeningExcluded} dbFTAssessed={dbFTAssessed}
        dbFTExcluded={dbFTExcluded}
        dbFTIncluded={dbFTIncluded > 0 ? dbFTIncluded : snowballFTIncluded === 0 ? dbFTAssessed : dbFTIncluded}
        bySource={bySource} dbScrExclByCrit={dbScrExclByCrit} dbFTExclByCrit={dbFTExclByCrit}
        snowballRetrieved={snowballRetrieved} snowballScreened={snowballScreened}
        snowballScrExcluded={snowballScrExcluded} snowballFTAssessed={snowballFTAssessed}
        snowballFTExcluded={snowballFTExcluded} snowballFTIncluded={snowballFTIncluded}
        snowballScrExclByCrit={snowballScrExclByCrit} snowballFTExclByCrit={snowballFTExclByCrit}
        shortLabelMap={shortLabelMap}
      />
    )
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))

    svgEl = container.querySelector('#prisma-svg') as SVGSVGElement | null
    let result: string | null = null
    if (svgEl) result = new XMLSerializer().serializeToString(svgEl)
    root.unmount()
    document.body.removeChild(container)
    return result
  }, [stats, importStats, screeningPapers, fulltextPapers, exclusionCriteria])

  async function handlePdfDownload() {
    setPdfLoading(true)
    try {
      const prismaSvg = await getPrismaSvg()
      const response = await fetch(`/api/projects/${pid}/report/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prisma_svg: prismaSvg }),
      })
      if (!response.ok) throw new Error('PDF generation failed')
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `reviq_protocol.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } finally {
      setPdfLoading(false)
    }
  }

  function handleFullDatasetCsv() {
    if (!extSummary) return
    const fieldHeaders = extSummary.fields.map(f => f.field_label)
    const headers = ['Paper ID', 'Citekey', 'Title', 'Authors', 'Year', 'Source', ...fieldHeaders]
    const rows = extSummary.papers.map(p => [
      p.paper_id,
      p.citekey,
      p.title,
      p.authors ?? '',
      p.year ?? '',
      p.source,
      ...extSummary.fields.map(f => p.values[f.field_name] ?? ''),
    ])
    downloadCsv('extraction_dataset.csv', headers, rows)
  }

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

  const hasExtraction = (extSummary?.papers.length ?? 0) > 0

  return (
    <div className="space-y-4">
      {/* Replication package + PDF report */}
      <Card>
        <CardHeader title="Replication Package &amp; Report" />
        <div className="space-y-0">
          <div className="py-3 border-b border-rule flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-ink">Replication Package</p>
              <p className="text-xs text-ink-muted mt-0.5">
                Full SLR data as a ZIP archive (project.json + BibTeX files) — importable into any ReviQ instance
              </p>
            </div>
            <a
              href={exportReplicationPackageUrl(pid)}
              download
              className="btn-secondary shrink-0"
            >
              ↓ .zip
            </a>
          </div>
          <div className="py-3 flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-ink">Review Protocol & Results (PDF)</p>
              <p className="text-xs text-ink-muted mt-0.5">
                Complete A4 report — protocol, search strategy, PRISMA flow, screening stats, kappa, QA, extraction data, bibliography
              </p>
            </div>
            <button
              className="btn-secondary shrink-0"
              disabled={pdfLoading}
              onClick={handlePdfDownload}
            >
              {pdfLoading ? 'Generating...' : '↓ .pdf'}
            </button>
          </div>
        </div>
      </Card>

      {/* Full extraction dataset CSV */}
      {hasExtraction && (
        <Card>
          <CardHeader title="Extracted Dataset" />
          <div className="py-3 flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-ink">Full Extraction Dataset</p>
              <p className="text-xs text-ink-muted mt-0.5">
                All included papers with extracted data — {extSummary!.papers.length} paper{extSummary!.papers.length !== 1 ? 's' : ''}, {extSummary!.fields.length} field{extSummary!.fields.length !== 1 ? 's' : ''}
              </p>
            </div>
            <button className="btn-secondary shrink-0" onClick={handleFullDatasetCsv}>
              ↓ CSV
            </button>
          </div>
        </Card>
      )}

      <Card>
        <CardHeader title="BibTeX Exports" />
        <div className="space-y-0">
          {exports.map(e => (
            <div key={e.label} className="py-3 border-b border-rule last:border-0 flex items-center gap-3">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-ink">{e.label}</p>
                <p className="text-xs text-ink-muted mt-0.5">{e.description}</p>
              </div>
              <span className="text-xs text-ink-muted shrink-0">n = {e.count}</span>
              <a
                href={e.count > 0 ? e.href : undefined}
                download
                className={`btn-secondary shrink-0 ${e.count === 0 ? 'opacity-40 pointer-events-none' : ''}`}
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
          <p className="text-sm text-ink-muted">Loading…</p>
        )}
      </Card>
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between py-1 border-b border-rule">
      <span className="text-ink-light">{label}</span>
      <span className="font-semibold text-ink">{value}</span>
    </div>
  )
}