/**
 * Default chart panels for the Charts tab.
 *
 * One file per chart? Tempting, but six panels share enough wiring (CSV
 * builder + filename hook + action menu) that splitting yields more import
 * lines than insight. They live here together and the rendered output of
 * each is single-responsibility per the iteration-2 brief: one panel = one
 * downloadable chart.
 */
import { useMemo, useState, useTransition } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { setVenueCategory, enrichVenues } from '../../api/client'

// User-selectable venue categories for the manual override dropdown.
const VENUE_CATEGORY_OPTIONS = [
  'Journal', 'Conference', 'Workshop',
  'Book chapter', 'Technical report', 'Thesis', 'Other',
] as const

// Shape returned by `getSearchMetrics` — duplicated locally (not exported from
// the API client) rather than touching unrelated API typings.
export interface SearchMetrics {
  total_included: number
  databases: Array<{
    db_name: string
    results_count: number | null
    imported: number
    included: number
    precision: number
    relative_recall: number
    f1: number
  }>
}

import {
  aggregateAbstractKeywords, aggregateKeywords, aggregatePublicationsPerYear,
  aggregateTopVenues, aggregateVenueTypes,
  categorizeVenue,
  type QAScoreBin, type QualityThresholds, type TaxonomyDistribution,
  type CategoryCount,
} from '../../utils/charts'
import { ChartPanel } from './ChartPanel'
import { HorizontalBarBody, PublicationsPerYearBody } from './bodies'
import { generateMonochromaticScale } from './scale'
import {
  ExtractionFieldChart, QAScoreDistributionChart,
} from './index'
import { Donut } from './Donut'
import { WordCloud } from './WordCloud'
import { downloadCsv } from './exportUtils'
import { COLORS, SANS } from './tokens'
import { usePaletteAccent } from './palette'
import type { PanelMenuAction } from './PanelMenu'
import { useChartFilename } from './filename'
import { DatabaseBadge } from '../databases'

// ── Action helpers ─────────────────────────────────────────────────────────

function withCsv(
  csvFilename: string,
  build: () => { headers: string[]; rows: (string | number | null)[][] },
): PanelMenuAction {
  return { kind: 'csv', onSelect: () => {
    const { headers, rows } = build()
    downloadCsv(`${csvFilename}.csv`, headers, rows)
  } }
}

function downloadActions(csv: PanelMenuAction): PanelMenuAction[] {
  return [csv, { kind: 'png' }, { kind: 'pdf' }]
}

// ── 1. Search Database Performance ─────────────────────────────────────────

export function SearchMetricsPanel({ metrics }: { metrics: SearchMetrics }) {
  const filename = useChartFilename('search-database-performance')
  const csv = withCsv(filename, () => ({
    headers: ['Database', 'DB Results', 'Imported (unique)', 'Included', 'Precision', 'Recall', 'F1'],
    rows: metrics.databases.map(d => [
      d.db_name,
      d.results_count ?? d.imported,
      d.imported, d.included,
      d.precision, d.relative_recall, d.f1,
    ]),
  }))
  return (
    <ChartPanel
      eyebrow="Sourcing"
      title="Search Database Performance"
      subtitle={<>Precision = included / DB results &nbsp;·&nbsp;
        Recall = included from DB / total included&nbsp;
        ({metrics.total_included}) &nbsp;·&nbsp; F1 = harmonic mean</>}
      exportName={filename}
      actions={downloadActions(csv)}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]" style={{ fontFamily: SANS }}>
          <thead>
            <tr className="border-b border-rule text-left text-ink-muted text-[10px] uppercase"
                style={{ letterSpacing: '0.08em' }}>
              <th className="pb-2 pr-4 font-semibold">Database</th>
              <th className="pb-2 pr-4 font-semibold text-right">DB results</th>
              <th className="pb-2 pr-4 font-semibold text-right">Imported</th>
              <th className="pb-2 pr-4 font-semibold text-right">Included</th>
              <th className="pb-2 pr-4 font-semibold text-right">Precision</th>
              <th className="pb-2 pr-4 font-semibold text-right">Recall</th>
              <th className="pb-2 font-semibold text-right">F1</th>
            </tr>
          </thead>
          <tbody style={{ fontVariantNumeric: 'tabular-nums' }}>
            {metrics.databases.map(d => (
              <tr key={d.db_name} className="border-b border-rule/60 hover:bg-paper/60">
                <td className="py-2 pr-4">
                  <DatabaseBadge dbKey={d.db_name} size="md" width="140px" />
                </td>
                <td className="py-2 pr-4 text-right">
                  {d.results_count != null
                    ? d.results_count
                    : <span className="text-ink-muted">{d.imported}</span>}
                </td>
                <td className="py-2 pr-4 text-right text-ink-muted">{d.imported}</td>
                <td className="py-2 pr-4 text-right">{d.included}</td>
                <td className="py-2 pr-4 text-right">{(d.precision * 100).toFixed(1)}%</td>
                <td className="py-2 pr-4 text-right">{(d.relative_recall * 100).toFixed(1)}%</td>
                <td className="py-2 text-right font-semibold">{(d.f1 * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartPanel>
  )
}

// ── 2. Publications per Year ───────────────────────────────────────────────

export function PublicationsPerYearPanel({ papers }: { papers: Array<{ year?: number | null }> }) {
  const data  = useMemo(() => aggregatePublicationsPerYear(papers), [papers])
  const total = data.reduce((s, d) => s + d.count, 0)
  const peak  = data.reduce((m, d) => d.count > m.count ? d : m, { year: 0, count: 0 })
  const span  = data.length > 0 ? `${data[0].year}–${data[data.length - 1].year}` : '—'
  const accent   = usePaletteAccent()
  // Second-darkest shade: 4-step scale mirrors the donut's typical 4-category
  // corpus, picking index 1.  With MIN_L=22% / MAX_L=70% this lands at 38%
  // lightness — the same shade the donut assigns to its second-position
  // segment, clearly distinguishable from the darkest (index 0 = 22%).
  const barColor = useMemo(() => generateMonochromaticScale(accent, 4)[1], [accent])

  const filename = useChartFilename('publications-per-year')
  const csv = withCsv(filename, () => ({
    headers: ['Year', 'Count'],
    rows: data.map(d => [d.year, d.count]),
  }))

  return (
    <ChartPanel
      eyebrow="Timeline"
      title="Publications per Year"
      subtitle={`${total} included papers spanning ${span}`}
      kpis={[
        { label: 'Papers',    value: total },
        { label: 'Years',     value: data.length },
        { label: 'Peak year', value: peak.count > 0 ? peak.year : '—' },
      ]}
      exportName={filename}
      actions={downloadActions(csv)}
    >
      <div id="chart-publications-year-svg">
        <PublicationsPerYearBody data={data} color={barColor} />
      </div>
    </ChartPanel>
  )
}

// ── 3. Quality Assessment Score Distribution ───────────────────────────────

export function QAScoreDistributionPanel({
  bins, thresholds, stats,
}: {
  bins: QAScoreBin[]
  thresholds: QualityThresholds
  stats: { n: number; mean: number; median: number }
}) {
  const filename = useChartFilename('qa-score-distribution')
  const csv = withCsv(filename, () => ({
    headers: ['Bin lower (%)', 'Bin upper (%)', 'Count', 'Low', 'Medium', 'High', 'Paper keys'],
    rows: bins.map(b => [
      b.lower, b.upper, b.count, b.low, b.medium, b.high, b.paperKeys.join('; '),
    ]),
  }))
  return (
    <ChartPanel
      eyebrow="Quality"
      title="Quality Score Distribution"
      subtitle={`${stats.n} paper${stats.n === 1 ? '' : 's'} assessed`}
      kpis={[
        { label: 'Mean',   value: `${stats.mean.toFixed(1)}%` },
        { label: 'Median', value: `${stats.median.toFixed(1)}%` },
      ]}
      exportName={filename}
      footnote="Bars stack the count of papers in each QA band within a bin; threshold lines reflect project setup."
      actions={downloadActions(csv)}
    >
      <QAScoreDistributionChart bins={bins} thresholds={thresholds} />
    </ChartPanel>
  )
}

// ── 4..N. One pie-chart panel per taxonomy (issue 5) ───────────────────────

export function TaxonomyPiePanel({
  dist, totalPapers, svgId,
}: { dist: TaxonomyDistribution; totalPapers: number; svgId?: string }) {
  const accent  = usePaletteAccent()
  const chartId = `taxonomy-${dist.key.replace(/_/g, '-')}`
  const filename = useChartFilename(chartId)
  const csv = withCsv(filename, () => ({
    headers: ['Category', 'Count', 'Percentage (%)'],
    rows: dist.categories.map(c => [c.value, c.count, c.percentage.toFixed(1)]),
  }))
  const ariaLabel = `${dist.label} donut`
  return (
    <ChartPanel
      eyebrow="Taxonomy"
      title={dist.label}
      subtitle={`${totalPapers} paper${totalPapers === 1 ? '' : 's'} · ${dist.categories.length} categor${dist.categories.length === 1 ? 'y' : 'ies'}`}
      exportName={filename}
      actions={downloadActions(csv)}
      flush
    >
      <Donut data={dist.categories} ariaLabel={ariaLabel} accent={accent} svgId={svgId} />
    </ChartPanel>
  )
}

// ── 5. Extraction Field (first dropdown) ───────────────────────────────────

export function ExtractionFieldPanel({
  field, categories,
}: {
  field: { field_name: string; field_label: string }
  categories: CategoryCount[]
}) {
  const accent   = usePaletteAccent()
  const filename = useChartFilename(`extraction-${field.field_name.replace(/_/g, '-')}`)
  const csv = withCsv(filename, () => ({
    headers: ['Value', 'Count', 'Percentage (%)'],
    rows: categories.map(c => [c.value, c.count, c.percentage.toFixed(1)]),
  }))
  const totalPapers = categories.reduce((s, c) => s + c.count, 0)
  return (
    <ChartPanel
      eyebrow="Extraction"
      title={field.field_label}
      subtitle={`${totalPapers} paper${totalPapers === 1 ? '' : 's'} · ${categories.length} value${categories.length === 1 ? '' : 's'}`}
      exportName={filename}
      actions={downloadActions(csv)}
    >
      <ExtractionFieldChart categories={categories} color={accent} />
    </ChartPanel>
  )
}

// ── 6. Venue Types donut + top-venues disclosure with manual override ─────────

export function VenueTypesPanel({
  papers, projectId,
}: {
  papers: Array<{ entry_type?: string | null; venue?: string | null; venue_category_override?: string | null }>
  projectId: number
}) {
  const qc     = useQueryClient()
  const accent = usePaletteAccent()
  const [, startTransition] = useTransition()

  const data = useMemo(() => aggregateVenueTypes(papers), [papers])
  const filename = useChartFilename('venue-types')
  const csv = withCsv(filename, () => ({
    headers: ['Category', 'Count', 'Percentage (%)'],
    rows: data.map(c => [c.value, c.count, c.percentage.toFixed(1)]),
  }))

  // Top-10 venues by name — each row also tracks the first paper's override.
  const topVenues = useMemo(() => {
    const counts = new Map<string, {
      count: number
      category: string
      override: string | null
    }>()
    for (const p of papers) {
      const name = (p.venue ?? '').trim()
      if (!name) continue
      const existing = counts.get(name) ?? {
        count: 0,
        category: categorizeVenue(p),
        override: p.venue_category_override ?? null,
      }
      counts.set(name, { ...existing, count: existing.count + 1 })
    }
    return Array.from(counts.entries())
      .map(([name, info]) => ({ name, ...info }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
      .slice(0, 15)
  }, [papers])

  async function handleCategoryChange(venue: string, newCategory: string) {
    const category = newCategory === '__auto__' ? null : newCategory
    await setVenueCategory(projectId, venue, category)
    // Invalidate papers query so the donut refreshes.
    startTransition(() => {
      qc.invalidateQueries({ queryKey: ['papers', projectId, 'full-text'] })
    })
  }

  // The edit-categories disclosure lives BELOW the card (not inside it) so
  // the Venue Types card body stays the same height as other donut cards.
  return (
    <>
      <ChartPanel
        eyebrow="Composition"
        title="Venue Types"
        subtitle={`${papers.length} included paper${papers.length === 1 ? '' : 's'}`}
        exportName={filename}
        actions={downloadActions(csv)}
        flush
      >
        <Donut data={data} ariaLabel="Venue types donut" accent={accent} svgId="chart-venue-types-svg" />
      </ChartPanel>

      {topVenues.length > 0 && (
        /* flex-col + overflow-hidden fills the grid row height (same as the
           Venue Types card via CSS Grid stretch).  min-h-0 on the scroll area
           lets the flex child shrink below its content height so the browser
           draws a scrollbar instead of overflowing. */
        <div className="border border-rule rounded-[4px] bg-surface overflow-hidden flex flex-col"
             data-export-exclude>

          {/* Card header — mirrors ChartPanel aesthetics */}
          <div className="px-5 pt-4 pb-3 shrink-0 border-b border-rule/60">
            <p className="text-[10px] font-semibold uppercase text-ink-muted mb-1"
               style={{ letterSpacing: '0.12em', fontFamily: SANS }}>
              Composition
            </p>
            <h3 className="text-[16px] leading-tight text-ink-light font-semibold"
                style={{ fontFamily: SANS }}>
              Edit Venue Categories
            </h3>
            <p className="text-[12px] text-ink-muted mt-1"
               style={{ fontFamily: SANS }}>
              Override the auto-detected category. Changes apply to all papers from that venue.
            </p>
          </div>

          {/* Scrollable venue table */}
          <div className="flex-1 overflow-y-auto min-h-0 px-5 pb-4">
            <table className="w-full text-[12px]"
                   style={{ fontFamily: SANS, fontVariantNumeric: 'tabular-nums' }}>
              <thead>
                <tr className="border-b border-rule text-left text-ink-muted text-[10px] uppercase
                               sticky top-0 bg-surface"
                    style={{ letterSpacing: '0.08em' }}>
                  <th className="pt-3 pb-1.5 pr-3 font-semibold">Venue</th>
                  <th className="pt-3 pb-1.5 pr-3 font-semibold">Category</th>
                  <th className="pt-3 pb-1.5 font-semibold text-right">Count</th>
                </tr>
              </thead>
              <tbody>
                {topVenues.map(v => (
                  <tr key={v.name} className="border-b border-rule/50">
                    <td className="py-1.5 pr-3 text-ink truncate max-w-[220px]" title={v.name}>
                      {v.name}
                    </td>
                    <td className="py-1 pr-3">
                      <select
                        value={v.override ?? '__auto__'}
                        onChange={e => handleCategoryChange(v.name, e.target.value)}
                        className="text-[11px] border border-rule rounded-[4px] px-1.5 py-0.5
                                   bg-paper text-ink focus:outline-none focus:border-ink/30
                                   cursor-pointer w-full"
                        style={{ fontFamily: SANS }}
                      >
                        <option value="__auto__">Auto: {v.category}</option>
                        {VENUE_CATEGORY_OPTIONS.map(opt => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-1.5 text-right font-semibold text-ink">{v.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}


// ── 7. Keyword Frequency ───────────────────────────────────────────────────

export function KeywordFrequencyPanel({
  papers,
}: { papers: Array<{ keywords?: string | null; abstract?: string | null }> }) {
  const accent   = usePaletteAccent()
  const barColor = useMemo(() => generateMonochromaticScale(accent, 4)[1], [accent])
  const [mode, setMode] = useState<'abstract' | 'wordcloud' | 'bibtex'>('abstract')

  const hasBibtex = useMemo(
    () => papers.some(p => !!(p.keywords?.trim())),
    [papers],
  )

  const abstractData  = useMemo(() => aggregateAbstractKeywords(papers, 20), [papers])
  const bibtexData    = useMemo(() => aggregateKeywords(papers, 20), [papers])
  const cloudData     = useMemo(() => aggregateAbstractKeywords(papers, 50), [papers])

  // Data used for the CSV export (always frequency data, not the cloud)
  const csvData = mode === 'bibtex' ? bibtexData : abstractData

  const filename = useChartFilename('keyword-frequency')
  const csv = withCsv(filename, () => ({
    headers: ['Keyword / Phrase', 'Count', 'Frequency (%)'],
    rows: csvData.map(d => [d.value, d.count, d.percentage.toFixed(1)]),
  }))

  type ModeKey = 'abstract' | 'wordcloud' | 'bibtex'
  const modes: Array<{ key: ModeKey; label: string }> = [
    { key: 'abstract',   label: 'Abstracts'  },
    { key: 'wordcloud',  label: 'Word Cloud' },
    ...(hasBibtex ? [{ key: 'bibtex' as ModeKey, label: 'BibTeX' }] : []),
  ]

  const toggle = (
    <div className="flex rounded-[4px] border border-rule overflow-hidden"
         style={{ fontSize: 11, fontFamily: SANS }}>
      {modes.map((m, i) => (
        <button
          key={m.key}
          type="button"
          onClick={() => setMode(m.key)}
          className={`px-2.5 py-0.5 transition-colors ${
            i > 0 ? 'border-l border-rule' : ''
          } ${mode === m.key
              ? 'bg-ink text-surface font-semibold'
              : 'bg-surface text-ink-muted hover:text-ink'}`}
          style={{ fontFamily: SANS }}
        >
          {m.label}
        </button>
      ))}
    </div>
  )

  const subtitle =
    mode === 'abstract'  ? `Top 20 terms from abstracts · ${papers.length} papers` :
    mode === 'wordcloud' ? `Top 50 terms from abstracts · ${papers.length} papers` :
    `Top 20 BibTeX keywords · ${papers.filter(p => p.keywords?.trim()).length} of ${papers.length} papers with data`

  return (
    <ChartPanel
      eyebrow="Synthesis"
      title="Keyword Frequency"
      subtitle={subtitle}
      exportName={filename}
      actions={downloadActions(csv)}
      headerExtra={toggle}
    >
      {mode === 'wordcloud' ? (
        cloudData.length === 0 ? (
          <p className="text-[13px] text-ink-muted px-5" style={{ fontFamily: SANS }}>
            No abstract data available.
          </p>
        ) : (
          <WordCloud data={cloudData} accent={accent} />
        )
      ) : (
        (() => {
          const d = mode === 'bibtex' ? bibtexData : abstractData
          return d.length === 0 ? (
            <p className="text-[13px] text-ink-muted px-5" style={{ fontFamily: SANS }}>
              No data available for this mode.
            </p>
          ) : (
            <HorizontalBarBody data={d} color={barColor} leftAlignLabels yAxisWidth={190} />
          )
        })()
      )}
    </ChartPanel>
  )
}



export function TopVenuesPanel({
  papers, projectId,
}: { papers: Array<{ venue?: string | null }>; projectId: number }) {
  const accent   = usePaletteAccent()
  const barColor = useMemo(() => generateMonochromaticScale(accent, 4)[1], [accent])
  const data     = useMemo(() => aggregateTopVenues(papers, 10), [papers])
  const filename = useChartFilename('top-venues')
  const qc       = useQueryClient()
  const [, startTransition] = useTransition()
  const [enriching, setEnriching] = useState(false)
  const [enrichMsg, setEnrichMsg] = useState<string | null>(null)

  const csv = withCsv(filename, () => ({
    headers: ['Venue', 'Count', 'Papers (%)'],
    rows: data.map(d => [d.value, d.count, d.percentage.toFixed(1)]),
  }))

  // No pre-truncation — the custom two-line tick in HorizontalBarBody handles
  // long names by wrapping at word boundaries.  Full names for CSV export.

  async function handleEnrich() {
    setEnriching(true)
    setEnrichMsg(null)
    try {
      const res = await enrichVenues(projectId)
      setEnrichMsg(`CrossRef: ${res.updated} venue${res.updated === 1 ? '' : 's'} added`)
      startTransition(() => {
        qc.invalidateQueries({ queryKey: ['papers', projectId, 'full-text'] })
      })
    } catch {
      setEnrichMsg('Enrichment failed — check network')
    } finally {
      setEnriching(false)
    }
  }

  const missingVenueCount = papers.filter(p => !(p.venue ?? '').trim()).length

  return (
    <ChartPanel
      eyebrow="Sourcing"
      title="Top Venues"
      subtitle={`${papers.length} included papers · ${data.length} venues shown`}
      exportName={filename}
      actions={downloadActions(csv)}
    >
      {missingVenueCount > 0 && (
        <div className="px-5 pt-3 pb-1 flex items-center gap-3 flex-wrap">
          <span className="text-[11px] text-ink-muted" style={{ fontFamily: SANS }}>
            {missingVenueCount} paper{missingVenueCount === 1 ? '' : 's'} without venue data
          </span>
          <button
            type="button"
            onClick={handleEnrich}
            disabled={enriching}
            className="text-[11px] px-2.5 py-1 rounded-[4px] border border-rule
                       bg-surface hover:border-ink/30 transition-colors disabled:opacity-50"
            style={{ fontFamily: SANS }}
          >
            {enriching ? 'Looking up via CrossRef…' : 'Fill via CrossRef'}
          </button>
          {enrichMsg && (
            <span className="text-[11px] text-include" style={{ fontFamily: SANS }}>
              {enrichMsg}
            </span>
          )}
        </div>
      )}
      <HorizontalBarBody data={data} color={barColor} yAxisWidth={380} leftAlignLabels />
    </ChartPanel>
  )
}
