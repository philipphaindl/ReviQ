/**
 * Results & Visualization (Phase 8) — PRISMA flow diagram, charts, and export.
 * PRISMA is inline SVG, one column per stream that contributed something:
 * database search, snowballing, and — in a multivocal review — grey literature.
 *
 * Stream membership comes from ../components/streams, never from testing the
 * `source` string here: that test had no third case, so a grey-literature
 * record counted as a database hit and inflated "records identified".
 */
import { useQueries, useQuery } from '@tanstack/react-query'
import { useMemo, useState, useRef, useCallback, useEffect, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { useProject } from '../App'
import { getExportStats, getQASummary, getExtractionSummary, exportBibtexUrl, getImportStats, getPapers, getTaxonomyTypes, getTaxonomy, getKappa, getReviewers, getProject, exportReplicationPackageUrl, getSearchMetrics, getExclusionCriteria } from '../api/client'
import { Card, CardHeader, StatBar, StatCell, EmptyState } from '../components/ui'
import { sourceLabel } from '../utils/sourceLabel'
import { counted, PHASE_NOUN } from '../utils/vocabulary'
import {
  allStreamCounts, streamIsPresent,
  type StreamCounts, type StreamSpec,
} from '../utils/prisma'
import type { KappaResult } from '../api/types'
import {
  aggregateExtractionField, aggregateTaxonomy, binQAScores,
  pickFirstSelectField, summarizeQAScores,
  type CategoryCount, type QualityThresholds,
} from '../utils/charts'
import { AddChartDialog } from '../components/charts/AddChartDialog'
import { CustomChartPanel } from '../components/charts/CustomChartPanel'
import {
  defaultTypeFor, useCustomCharts, type ChartConfig,
} from '../components/charts/customCharts'
import {
  ExtractionFieldPanel, KeywordFrequencyPanel, PublicationsPerYearPanel,
  QAScoreDistributionPanel, SearchMetricsPanel,
  TaxonomyPiePanel, TopVenuesPanel, VenueTypesPanel,
} from '../components/charts/panels'
import { ChartFilenameProvider } from '../components/charts/filename'
import { COLORS, SANS } from '../components/charts/tokens'
import { PALETTES, PaletteContext, usePalette } from '../components/charts/palette'
import { getExportPadding, setExportPadding, MIN_PADDING, MAX_PADDING, ExportPaddingContext } from '../components/charts/exportSettings'

// Each export is named for the phase whose decision it carries: screening
// decides on records, eligibility on reports, and the review includes studies.
// The CSV column headers below keep `Paper ID` — that is a data interchange a
// consumer may already parse, not a sentence anyone reads.
const RECORDS = PHASE_NOUN.screening
const REPORTS = PHASE_NOUN.eligibility
const STUDIES = PHASE_NOUN.results

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

      {view === 'prisma' && <PrismaView pid={projectId} />}

      {/* ChartsView is always mounted so its SVG elements stay in the DOM and
          are available when the user downloads the PDF from the Export tab.
          When another tab is active it is positioned off-screen (not display:none
          so Recharts ResponsiveContainer can still measure its container). */}
      <div
        style={view !== 'charts' ? {
          position: 'absolute', left: '-99999px', top: 0,
          width: '1280px', visibility: 'hidden', pointerEvents: 'none',
        } : undefined}
        aria-hidden={view !== 'charts' || undefined}
      >
        <ChartsView pid={projectId} />
      </div>

      {view === 'export' && <ExportView pid={projectId} />}
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

  // Every stream's eight numbers come from one derivation (utils/prisma.ts).
  // They used to be written out per stream here, and the two copies had already
  // drifted: "full texts assessed" meant *passed screening* for databases and
  // *has a full-text decision* for snowballing, in the same figure. Adding grey
  // literature as a third copy would have made that three definitions.
  const streams = allStreamCounts(screeningPapers, fulltextPapers, bySource)

  // Combined for stat cards. Reading only the database column understated
  // these for any review that snowballed or searched the web.
  const afterDedup = streams.reduce((n, s) => n + s.counts.unique, 0)
  const totalIncluded = streams.reduce((n, s) => n + s.counts.ftIncluded, 0)
  const included = totalIncluded > 0 ? totalIncluded : stats.screening_included

  return (
    <div className="space-y-4">
      <StatBar>
        <StatCell label="Total Retrieved" value={stats.total_retrieved} />
        <StatCell label="After Deduplication" value={afterDedup} />
        <StatCell label="Screened" value={afterDedup} />
        <StatCell label="Included" value={included} color="include" />
      </StatBar>

      <Card>
        <CardHeader title="PRISMA 2020 Flow Diagram"
          action={<PrismaSvgDownload />}
        />
        <div className="overflow-x-auto">
          <PrismaFlowDiagram
            streams={streams}
            bySource={bySource}
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

/** What a column draws beyond the skeleton every stream shares.
 *
 * Snowballing has neither a source breakdown — its "sources" are the seed
 * papers, one row each — nor a deduplication step of its own. A searched
 * stream has both: databases overlap with one another, and so do the search
 * engines behind a grey corpus.
 */
const COLUMN: Record<StreamSpec['key'], {
  header: string; ident: string; included: string
  breakdown: boolean; dedup: boolean
}> = {
  database: {
    header: 'Database search', ident: 'Records from databases',
    included: 'Included (databases)', breakdown: true, dedup: true,
  },
  snowball: {
    header: 'Snowballing', ident: 'Records via snowballing',
    included: 'Included (snowballing)', breakdown: false, dedup: false,
  },
  grey: {
    header: 'Grey literature', ident: 'Records from grey literature',
    included: 'Included (grey literature)', breakdown: true, dedup: true,
  },
}

// One column per stream that contributed something; the geometry follows from
// how many that is. The diagram used to take fixed `db*` and `snowball*` prop
// groups and switch its width on a `hasSnowball` boolean, so every position,
// the header band and the joining line all assumed one column or two — a third
// stream could not be expressed at all.
//
// Y positions still cascade top-to-bottom; each row accounts for the tallest
// exclusion box at that level (criteria count varies per box).
export function PrismaFlowDiagram({ streams, bySource, shortLabelMap }: {
  streams: { spec: StreamSpec; counts: StreamCounts }[]
  bySource: Record<string, { total: number; original: number; duplicate: number }>
  shortLabelMap: Record<string, string>
}) {
  // A review without grey literature must not carry an empty grey column into
  // its published figure, exactly as an SLR without snowballing does not.
  const present = streams.filter(s => streamIsPresent(s.counts))
  // An untouched project has no stream at all: draw the first as a skeleton of
  // zeros rather than an empty frame.
  const cols0 = present.length > 0 ? present : streams.slice(0, 1)
  const nCols = cols0.length
  const multi = nCols > 1

  // Layout
  const GAP = 40
  const boxH = 52
  const boxW = multi ? 200 : 260
  const exclW = multi ? 180 : 215
  const EXCL_GAP = 20
  // Box + gap + exclusion box + gutter — the pitch a column repeats at.
  const COL_PITCH = 420
  const cxOf = (i: number) => (multi ? 240 + i * COL_PITCH : 310)
  const exclXOf = (i: number) => cxOf(i) + boxW / 2 + EXCL_GAP
  const W = multi ? cxOf(nCols - 1) + boxW / 2 + EXCL_GAP + exclW + 10 : 755

  // Publication-safe colors (all pass grayscale + WCAG AA)
  const arrowColor = '#6b7280'          // medium gray — darker than before for print
  const arrowRedColor = '#d97706'       // amber — distinct from blue in grayscale AND colorblind-safe
  const mainColor = '#1e3a5f'           // dark navy
  const sectionColor = '#e2e8f0'
  const sectionText = '#475569'
  // Inter matches the app's UI font; system-ui fallback keeps standalone SVG portable
  const FONT = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif'

  // Per-column geometry: only the box heights vary between streams, and each
  // varies with its own criteria and sources.
  const cols = cols0.map(({ spec, counts }, i) => {
    const cfg = COLUMN[spec.key]
    const sources = cfg.breakdown
      ? Object.entries(bySource).filter(([src, v]) => spec.matchesSource(src) && v.total > 0)
      : []
    return {
      spec, counts, cfg, sources,
      cx: cxOf(i), exclX: exclXOf(i),
      identH: boxH + sources.length * 14,
      scrExclH: counts.screeningExcluded > 0
        ? boxH + Object.keys(counts.screeningExclByCriterion).length * 14 : 0,
      ftExclH: counts.ftExcluded > 0
        ? boxH + Object.keys(counts.ftExclByCriterion).length * 14 : 0,
    }
  })

  // Y positions — one band per PRISMA row, tall enough for every column in it.
  const Y_TOP = multi ? 28 : 12
  const identBottom = Y_TOP + Math.max(...cols.map(c => c.identH))
  // Streams that do not deduplicate run one long arrow through this band.
  const hasDedupRow = cols.some(c => c.cfg.dedup)
  const dedup_cy = identBottom + GAP + boxH / 2
  const shared_screened_cy = (hasDedupRow ? dedup_cy + boxH / 2 : identBottom) + GAP + boxH / 2
  const shared_ft_cy = shared_screened_cy
    + Math.max(boxH / 2, ...cols.map(c => c.scrExclH / 2)) + GAP + boxH / 2
  const shared_incl_cy = shared_ft_cy
    + Math.max(boxH / 2, ...cols.map(c => c.ftExclH / 2)) + GAP + boxH / 2
  const combined_cy = multi ? shared_incl_cy + boxH / 2 + GAP + boxH / 2 : 0

  const H = (multi ? combined_cy : shared_incl_cy) + boxH / 2 + 24

  // Text styles — all include fontFamily for standalone SVG portability
  const labelStyle = {
    fontSize: '10px', fill: sectionText, fontWeight: '700' as const,
    textTransform: 'uppercase' as const, letterSpacing: '0.09em', fontFamily: FONT,
  }
  const boxTextStyle = { fontSize: '11.5px', fill: mainColor, fontWeight: '400' as const, fontFamily: FONT }
  const nStyle = { fontSize: '13px', fill: mainColor, fontWeight: '700' as const, fontFamily: FONT }
  const smallStyle = { fontSize: '9.5px', fill: '#475569', fontFamily: FONT }

  function SectionLabel({ y: yPos, label }: { y: number; label: string }) {
    const lW = multi ? 116 : 124
    const xLeft = multi ? 8 : cxOf(0) - boxW / 2 - lW - 10
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

      {/* Column headers, one per drawn stream, with a divider between neighbours.
          Uppercased here rather than by `text-transform`, which the standalone
          SVG and the PDF renderer do not apply. */}
      {multi && cols.map((c, i) => (
        <g key={`head-${c.spec.key}`}>
          <text x={c.cx} y={16} textAnchor="middle"
            style={{ fontSize: '10px', fill: mainColor, fontWeight: '700', letterSpacing: '0.07em',
                     fontFamily: FONT }}>
            {c.cfg.header.toUpperCase()}
          </text>
          {i > 0 && (
            /* Vertical divider — longer dash for cleaner print reproduction */
            <line x1={(cols[i - 1].cx + c.cx) / 2} y1={22}
              x2={(cols[i - 1].cx + c.cx) / 2} y2={H - 24}
              stroke="#c8d4e0" strokeWidth={1} strokeDasharray="6,4" />
          )}
        </g>
      ))}

      {/* Section labels */}
      <SectionLabel y={Y_TOP + Math.max(...cols.map(c => c.identH)) / 2} label="IDENTIFICATION" />
      <SectionLabel y={shared_screened_cy} label="SCREENING" />
      <SectionLabel y={shared_ft_cy} label="ELIGIBILITY" />
      <SectionLabel y={multi ? combined_cy : shared_incl_cy} label="INCLUDED" />

      {/* ── One column per stream ── */}
      {cols.map(c => {
        const identCy = Y_TOP + c.identH / 2
        return (
          <g key={c.spec.key}>
            {/* Identification box — slightly tinted fill for visual hierarchy */}
            <MainBox cx={c.cx} cy={identCy} h={c.identH}
              label={c.cfg.ident} n={c.counts.retrieved}>
              {c.sources.map(([src, v], i) => (
                <text key={src} x={c.cx} y={Y_TOP + 52 + i * 14}
                  textAnchor="middle" style={smallStyle}>
                  {sourceLabel(src)}: {v.total} ({v.original} unique)
                </text>
              ))}
            </MainBox>

            {/* Duplicates removed — positioned alongside the identification→dedup
                arrow, with a connecting horizontal line for PRISMA 2020 conformance */}
            {c.cfg.dedup && c.counts.duplicates > 0 && (() => {
              // Midpoint on the vertical arrow between ident and dedup boxes
              const arrowMidY = (Y_TOP + c.identH + dedup_cy - boxH / 2) / 2
              const dedupBoxH = 42
              const dedupBoxW = exclW
              return (
                <g>
                  <rect x={c.exclX} y={arrowMidY - dedupBoxH / 2} width={dedupBoxW} height={dedupBoxH}
                    rx={5} fill="#f1f5f9" stroke="#94a3b8" strokeWidth={1}
                    strokeDasharray="5,3" />
                  <text x={c.exclX + dedupBoxW / 2} y={arrowMidY - 4} textAnchor="middle"
                    style={{ ...smallStyle, fill: '#475569' }}>Duplicates removed</text>
                  <text x={c.exclX + dedupBoxW / 2} y={arrowMidY + 12} textAnchor="middle"
                    style={{ fontSize: '12px', fill: '#334155', fontWeight: '700', fontFamily: FONT }}>n = {c.counts.duplicates}</text>
                  {/* Horizontal connecting line from main flow */}
                  <line x1={c.cx + boxW / 2} y1={arrowMidY} x2={c.exclX - 2} y2={arrowMidY}
                    stroke="#94a3b8" strokeWidth={1} strokeDasharray="3,2" />
                </g>
              )
            })()}

            {c.cfg.dedup ? (
              <>
                <DownArrow cx={c.cx} fromY={Y_TOP + c.identH} toY={dedup_cy - boxH / 2} />
                <MainBox cx={c.cx} cy={dedup_cy}
                  label="Records after deduplication" n={c.counts.unique} />
                <DownArrow cx={c.cx} fromY={dedup_cy + boxH / 2} toY={shared_screened_cy - boxH / 2} />
              </>
            ) : (
              /* No deduplication step: one arrow through the band the others use */
              <DownArrow cx={c.cx} fromY={Y_TOP + c.identH} toY={shared_screened_cy - boxH / 2} />
            )}

            <MainBox cx={c.cx} cy={shared_screened_cy} label="Records screened" n={c.counts.unique} />
            <ExclusionBox fromCx={c.cx} cy={shared_screened_cy} exclX={c.exclX}
              label="Excluded (title/abstract)" n={c.counts.screeningExcluded}
              criteria={c.counts.screeningExclByCriterion} />

            <DownArrow cx={c.cx}
              fromY={shared_screened_cy + boxH / 2}
              toY={shared_ft_cy - boxH / 2} />
            <MainBox cx={c.cx} cy={shared_ft_cy} label="Full texts assessed" n={c.counts.ftAssessed} />
            <ExclusionBox fromCx={c.cx} cy={shared_ft_cy} exclX={c.exclX}
              label="Not eligible (full-text)" n={c.counts.ftExcluded}
              criteria={c.counts.ftExclByCriterion} />

            <DownArrow cx={c.cx}
              fromY={shared_ft_cy + boxH / 2}
              toY={shared_incl_cy - boxH / 2} />

            {multi ? (
              <MainBox cx={c.cx} cy={shared_incl_cy}
                label={c.cfg.included} n={c.counts.ftIncluded} />
            ) : (
              /* Single stream: its included box is the final one, and green */
              <g>
                <rect x={c.cx - boxW / 2} y={shared_incl_cy - boxH / 2} width={boxW} height={boxH}
                  rx={5} fill="#f0fdf4" stroke="#22c55e" strokeWidth={2} />
                <text x={c.cx} y={shared_incl_cy - 6} textAnchor="middle"
                  style={{ ...boxTextStyle, fill: '#166534' }}>Studies included in review</text>
                <text x={c.cx} y={shared_incl_cy + 13} textAnchor="middle"
                  style={{ ...nStyle, fill: '#166534', fontSize: '15px' }}>n = {c.counts.ftIncluded}</text>
              </g>
            )}
          </g>
        )
      })}

      {/* ── Where the streams join ── */}
      {multi && (() => {
        const first = cols[0].cx
        const last = cols[cols.length - 1].cx
        const mid = (first + last) / 2
        const joinY = shared_incl_cy + boxH / 2 + 22
        return (
          <>
            {/* Convergence arrows: every included box → the combined final box */}
            {cols.map(c => (
              <line key={`join-${c.spec.key}`} x1={c.cx} y1={shared_incl_cy + boxH / 2}
                x2={c.cx} y2={joinY} stroke={arrowColor} strokeWidth={1.5} />
            ))}
            <line x1={first} y1={joinY} x2={last} y2={joinY}
              stroke={arrowColor} strokeWidth={1.5} />
            <line x1={mid} y1={joinY} x2={mid} y2={combined_cy - boxH / 2}
              stroke={arrowColor} strokeWidth={1.5} markerEnd="url(#arrowGray)" />

            {/* Combined final box — wider, green, prominent */}
            <rect x={mid - boxW * 0.85} y={combined_cy - boxH / 2}
              width={boxW * 1.7} height={boxH}
              rx={5} fill="#f0fdf4" stroke="#22c55e" strokeWidth={2} />
            <text x={mid} y={combined_cy - 6} textAnchor="middle"
              style={{ ...boxTextStyle, fill: '#166534' }}>Studies included in review</text>
            <text x={mid} y={combined_cy + 13} textAnchor="middle"
              style={{ ...nStyle, fill: '#166534', fontSize: '15px' }}>
              n = {cols.reduce((sum, c) => sum + c.counts.ftIncluded, 0)}
            </text>
          </>
        )
      })()}

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


// ── Charts View ──────────────────────────────────────────────────────────────

function ChartsView({ pid }: { pid: number }) {
  const [addOpen, setAddOpen] = useState(false)
  const [exportPad, setExportPadState] = useState(() => getExportPadding())
  const { configs, add, remove } = useCustomCharts(pid)
  const { accent, select: selectPalette } = usePalette()

  function handlePadChange(px: number) {
    setExportPadState(px)
    setExportPadding(px)
  }

  // ── Data dependencies (all the SLR-state queries the panels need) ──────
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
  const { data: project } = useQuery({
    queryKey: ['project', pid],
    queryFn: () => getProject(pid),
  })
  const { data: reviewers = [] } = useQuery({
    queryKey: ['reviewers', pid],
    queryFn: () => getReviewers(pid),
  })
  // Fan out one taxonomy-schema query per taxonomy_type. Issue 5 of the
  // iteration brief requires *one pie panel per dimension*, including any
  // custom taxonomies the user defined in Setup, so the number of queries
  // is dynamic — `useQueries` is the natural fit.
  const taxonomyQueries = useQueries({
    queries: taxonomyTypes.map(type => ({
      queryKey: ['taxonomy', pid, type] as const,
      queryFn: () => getTaxonomy(pid, type),
    })),
  })
  const taxonomySchemas = useMemo<Record<string, string[]>>(() => {
    const out: Record<string, string[]> = {}
    taxonomyTypes.forEach((key, i) => {
      out[key] = (taxonomyQueries[i]?.data ?? []).map(e => e.value)
    })
    return out
  }, [taxonomyTypes, taxonomyQueries])

  // Included full-text papers — the population every chart pulls from.
  const includedPapers = useMemo(
    () => ftPapers.filter(p => p.final_decision?.decision === 'I'),
    [ftPapers],
  )

  // ── Derived data for the default panels ────────────────────────────────
  const qaThresholds: QualityThresholds = {
    medium: project?.qa_medium_threshold ?? 50,
    high:   project?.qa_high_threshold   ?? 75,
  }
  const citekeyByPaperId = useMemo(() => {
    const m = new Map<number, string>()
    for (const p of ftPapers) m.set(p.id, p.citekey)
    return m
  }, [ftPapers])

  const qaInputs = useMemo(
    () => (qaSummary?.papers ?? []).map(p => ({
      key: citekeyByPaperId.get(p.paper_id) ?? p.paper_title ?? `paper-${p.paper_id}`,
      percentage: p.percentage,
    })),
    [qaSummary, citekeyByPaperId],
  )
  const qaBins  = useMemo(() => binQAScores(qaInputs, qaThresholds), [qaInputs, qaThresholds])
  const qaStats = useMemo(() => summarizeQAScores(qaInputs), [qaInputs])

  // One aggregated distribution per taxonomy_type — order follows the order
  // returned by /taxonomy-types (which is the user's setup order).
  const taxonomyDistributions = useMemo(
    () => taxonomyTypes.map(key => aggregateTaxonomy(
      extSummary?.papers ?? [], key, taxonomySchemas[key] ?? [],
    )),
    [taxonomyTypes, taxonomySchemas, extSummary],
  )

  const extractionField = extSummary
    ? pickFirstSelectField(extSummary.fields, taxonomyTypes)
    : null
  const extractionDist = useMemo(
    () => extractionField
      ? aggregateExtractionField(extSummary?.papers ?? [], extractionField.field_name)
      : [],
    [extSummary, extractionField],
  )

  // ── Available-data flags ────────────────────────────────────────────────
  const hasMetrics    = (searchMetrics?.databases.length ?? 0) > 0
  const hasYearData   = includedPapers.some(p => p.year)
  const hasQaScores   = qaStats.n > 0
  const hasTaxonomies = taxonomyDistributions.some(d => d.categories.length > 0)
  const hasExtraction = !!extractionField && extractionDist.length > 0
  const hasIncluded   = includedPapers.length > 0

  if (!hasMetrics && !hasYearData && !hasQaScores
      && !hasTaxonomies && !hasExtraction && !hasIncluded) {
    return <EmptyState icon="—"
      message="No data available yet. Complete screening or quality assessment to see charts." />
  }

  // ── Bundle for CustomChartPanel ────────────────────────────────────────
  const extractionFieldLabels: Record<string, string> = {}
  for (const f of extSummary?.fields ?? []) extractionFieldLabels[f.field_name] = f.field_label
  // Venue counts kept for CustomChartPanel's "venue" dimension (custom user
  // panels can still aggregate venues by name).
  const venueCountsCustom: CategoryCount[] = (() => {
    const map = new Map<string, number>()
    for (const p of includedPapers) {
      if (!p.venue) continue
      map.set(p.venue, (map.get(p.venue) ?? 0) + 1)
    }
    const total = includedPapers.length || 1
    return Array.from(map.entries())
      .map(([value, count]) => ({ value: cleanVenueName(value), count,
                                   percentage: (count / total) * 100 }))
      .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
      .slice(0, 10)
  })()
  const customDataBundle = {
    qaThresholds,
    qaInputs,
    extractionPapers: extSummary?.papers ?? [],
    papers: includedPapers,
    taxonomySchema: taxonomySchemas,
    venueCounts: venueCountsCustom,
    extractionFieldLabels,
  }

  // Dropdown extraction fields available for the AddChartDialog.
  const taxSet = new Set(taxonomyTypes)
  const dropdownFields = (extSummary?.fields ?? [])
    .filter(f => f.field_type === 'dropdown' && !taxSet.has(f.field_name))
    .map(f => ({ field_name: f.field_name, field_label: f.field_label }))

  const defaultPanelCount =
    (hasMetrics ? 1 : 0)
    + (hasYearData ? 1 : 0)
    + (hasQaScores ? 1 : 0)
    + taxonomyDistributions.filter(d => d.categories.length > 0).length
    + (hasExtraction ? 1 : 0)
    + (hasIncluded ? 3 : 0)  // Venue Types + Keyword Frequency + Top Venues

  return (
    <ExportPaddingContext.Provider value={exportPad}>
    <PaletteContext.Provider value={accent}>
    <ChartFilenameProvider projectTitle={project?.title ?? `project-${pid}`}>
      <div className="space-y-5">
        <ChartsToolbar
          defaultCount={defaultPanelCount}
          customCount={configs.length}
          onAdd={() => setAddOpen(true)}
          accent={accent}
          onPaletteSelect={selectPalette}
          exportPad={exportPad}
          onExportPadChange={handlePadChange}
        />

        {/* DEFAULT PANEL LINEUP — issue 5/6 final order:
            1) Search DB performance · 2) Publications/yr · 3) QA score
            distribution · 4) Contribution Type + Research Type side-by-side
            · 5..N) other taxonomy pies · N+1) Extraction field · last) Venue
            Types.  Inter-rater agreement lives on the Screening page + PDF. */}
        {hasMetrics && searchMetrics && <SearchMetricsPanel metrics={searchMetrics} />}
        {hasYearData && <PublicationsPerYearPanel papers={includedPapers} />}
        {hasQaScores &&
          <QAScoreDistributionPanel bins={qaBins} thresholds={qaThresholds} stats={qaStats} />}

        {/* The two "default" taxonomy keys always render as a side-by-side pair
            when both are present so users compare them at a glance. Every panel
            still has its own ⋯ menu for individual CSV / SVG downloads. */}
        {(() => {
          const DEFAULT_TAX_KEYS = ['contribution_type', 'research_type']
          const totalPapers = extSummary?.papers.length ?? 0
          const pairDists = taxonomyDistributions.filter(
            d => DEFAULT_TAX_KEYS.includes(d.key) && d.categories.length > 0
          )
          const otherDists = taxonomyDistributions.filter(
            d => !DEFAULT_TAX_KEYS.includes(d.key) && d.categories.length > 0
          )
          return (
            <>
              {pairDists.length >= 2 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {pairDists.map(d =>
                    <TaxonomyPiePanel key={d.key} dist={d} totalPapers={totalPapers}
                      svgId={d.key === 'research_type' ? 'chart-research-type-svg'
                           : d.key === 'contribution_type' ? 'chart-contribution-type-svg'
                           : undefined} />
                  )}
                </div>
              ) : (
                pairDists.map(d =>
                  <TaxonomyPiePanel key={d.key} dist={d} totalPapers={totalPapers}
                    svgId={d.key === 'research_type' ? 'chart-research-type-svg'
                         : d.key === 'contribution_type' ? 'chart-contribution-type-svg'
                         : undefined} />
                )
              )}
              {otherDists.map(d =>
                <TaxonomyPiePanel key={d.key} dist={d} totalPapers={totalPapers} />
              )}
            </>
          )
        })()}

        {hasExtraction && extractionField &&
          <ExtractionFieldPanel field={extractionField} categories={extractionDist} />}
        {/* Venue Types rendered at the same half-width as the taxonomy donuts above
            so the visual dimensions match. The empty second column is intentional. */}
        {hasIncluded && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <VenueTypesPanel papers={includedPapers} projectId={pid} />
          </div>
        )}
        {/* Keyword frequency and top venues by name — full-width horizontal bars. */}
        {hasIncluded && <KeywordFrequencyPanel papers={includedPapers} />}
        {hasIncluded && <TopVenuesPanel papers={includedPapers} projectId={pid} />}

        {/* USER-ADDED PANELS — donut panels constrained to half-width so they
            match the default taxonomy donuts. Other types render full-width. */}
        {(() => {
          const donutCfgs = configs.filter(c => c.type === 'donut')
          const otherCfgs = configs.filter(c => c.type !== 'donut')
          return (
            <>
              {donutCfgs.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {donutCfgs.map(cfg => (
                    <CustomChartPanel key={cfg.id} config={cfg}
                      data={customDataBundle} onRemove={() => remove(cfg.id)} />
                  ))}
                </div>
              )}
              {otherCfgs.map(cfg => (
                <CustomChartPanel key={cfg.id} config={cfg}
                  data={customDataBundle} onRemove={() => remove(cfg.id)} />
              ))}
            </>
          )
        })()}

        <AddChartDialog
          open={addOpen}
          onClose={() => setAddOpen(false)}
          onAdd={(cfg) => add({
            ...cfg,
            type: cfg.type ?? defaultTypeFor(cfg.dimension),
          })}
          taxonomyKeys={taxonomyTypes}
          extractionFields={dropdownFields}
        />
      </div>
    </ChartFilenameProvider>
    </PaletteContext.Provider>
    </ExportPaddingContext.Provider>
  )
}

// ── Charts tab toolbar ───────────────────────────────────────────────────────

function ChartsToolbar({
  defaultCount, customCount, onAdd, accent, onPaletteSelect, exportPad, onExportPadChange,
}: {
  defaultCount: number
  customCount: number
  onAdd: () => void
  accent: string
  onPaletteSelect: (a: string) => void
  exportPad: number
  onExportPadChange: (px: number) => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 pb-1 flex-wrap">
      <p className="text-[12px] text-ink-muted" style={{ fontFamily: SANS }}>
        Showing <span className="text-ink font-semibold">{defaultCount}</span> default
        {defaultCount === 1 ? ' panel' : ' panels'}
        {customCount > 0 && <> · <span className="text-ink font-semibold">{customCount}</span> custom</>}
      </p>

      <div className="flex items-center gap-3">
        {/* Export padding — affects both web rendering and file exports */}
        <label className="flex items-center gap-1.5" title="Export crop padding (px)">
          <span className="text-[11px] text-ink-muted" style={{ fontFamily: SANS }}>
            Export padding
          </span>
          <input
            type="number"
            min={MIN_PADDING}
            max={MAX_PADDING}
            step={1}
            value={exportPad}
            onChange={e => onExportPadChange(Number(e.target.value))}
            className="w-10 rounded-[4px] border border-rule bg-surface text-center
                       text-[11px] text-ink py-0.5 px-1 focus:outline-none focus:border-ink/30"
            style={{ fontFamily: SANS, fontVariantNumeric: 'tabular-nums' }}
          />
          <span className="text-[11px] text-ink-muted" style={{ fontFamily: SANS }}>px</span>
        </label>

        {/* Palette picker — 5 colour swatches */}
        <div className="flex items-center gap-1.5" title="Chart colour palette">
          {PALETTES.map(p => (
            <button
              key={p.accent}
              type="button"
              onClick={() => onPaletteSelect(p.accent)}
              title={p.name}
              className="w-4 h-4 rounded-full transition-transform hover:scale-125"
              style={{
                backgroundColor: p.accent,
                outline: p.accent === accent ? `2px solid ${p.accent}` : 'none',
                outlineOffset: 2,
              }}
            />
          ))}
        </div>

        <button
          type="button"
          onClick={onAdd}
          className="inline-flex items-center gap-1.5 rounded-[4px] border border-rule
                     bg-surface px-3 py-1.5 text-[12px] text-ink hover:border-ink/30
                     transition-colors"
          style={{ fontFamily: SANS, color: COLORS.ink }}
        >
          <span style={{ fontSize: '14px', lineHeight: '14px' }}>+</span>
          Add chart
        </button>
      </div>
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

    // The same derivation the on-screen view uses, all three streams of it.
    // This block used to be a second copy, so the PDF's figure and the
    // browser's could disagree about the same review — the defect
    // `dedup_status` and `detected_duplicates` each caused once already.
    const streams = allStreamCounts(screeningPapers, fulltextPapers, bySource)

    const container = document.createElement('div')
    container.style.cssText = 'position:absolute;left:-9999px;top:0;width:1200px'
    document.body.appendChild(container)
    const root = createRoot(container)
    root.render(
      <PrismaFlowDiagram
        streams={streams} bySource={bySource} shortLabelMap={shortLabelMap}
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

      // Serialize chart SVGs using the same XMLSerializer pattern as PRISMA.
      const serializer = new XMLSerializer()
      const serializeSvg = (id: string): string | null => {
        // getElementById may return a wrapper <div> when the id is on a container.
        // Always resolve to the actual <svg> element before serializing.
        const found = document.getElementById(id)
        const svgEl: SVGSVGElement | null =
          found instanceof SVGSVGElement
            ? found
            : (found?.querySelector('svg') as SVGSVGElement | null)
              ?? (document.querySelector(`#${id} svg`) as SVGSVGElement | null)
        if (!svgEl) return null
        // Ensure explicit width/height so ReportLab/svglib can size the drawing
        if (!svgEl.getAttribute('width') && svgEl.viewBox?.baseVal?.width) {
          svgEl.setAttribute('width',  String(svgEl.viewBox.baseVal.width))
          svgEl.setAttribute('height', String(svgEl.viewBox.baseVal.height))
        }
        return serializer.serializeToString(svgEl)
      }
      const chartSvgs = {
        quality_distribution_svg: serializeSvg('chart-quality-distribution-svg'),
        publications_year_svg:    serializeSvg('chart-publications-year-svg'),
        research_type_svg:        serializeSvg('chart-research-type-svg'),
        contribution_type_svg:    serializeSvg('chart-contribution-type-svg'),
        venue_types_svg:          serializeSvg('chart-venue-types-svg'),
      }

      const response = await fetch(`/api/projects/${pid}/report/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prisma_svg: prismaSvg, ...chartSvgs }),
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
      label: `Included ${STUDIES.Many} (Full-Text)`,
      description: `BibTeX file of ${STUDIES.many} included after full-text eligibility assessment`,
      href: exportBibtexUrl(pid, 'full-text', 'I'),
      count: stats?.fulltext_included ?? 0,
    },
    {
      label: `Included ${RECORDS.Many} (Screening)`,
      description: `BibTeX file of ${RECORDS.many} included after title/abstract screening`,
      href: exportBibtexUrl(pid, 'screening', 'I'),
      count: stats?.screening_included ?? 0,
    },
    {
      label: `Excluded ${REPORTS.Many} (Full-Text)`,
      description: `BibTeX file of ${REPORTS.many} excluded at full-text stage`,
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
                {/* "Full review data", not "Full SLR data": the same button in a
                    multivocal review exports its grey literature too. */}
                Full review data as a ZIP archive (project.json + BibTeX files) — importable into any ReviQ instance
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
                All included {STUDIES.many} with extracted data — {counted(extSummary!.papers.length, STUDIES)}, {extSummary!.fields.length} field{extSummary!.fields.length !== 1 ? 's' : ''}
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
