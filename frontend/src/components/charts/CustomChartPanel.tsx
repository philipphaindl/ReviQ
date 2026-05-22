/**
 * Renders a user-added chart panel from a stored `ChartConfig`.
 *
 * Pure presentational — the live SLR data is passed in from `ChartsView` so
 * this component doesn't need to know which queries are running. If the data
 * source the user chose is missing or empty, the panel shows an empty state
 * with a remove action so dashboards stay self-cleaning.
 */
import { useMemo } from 'react'

import {
  aggregateExtractionField, aggregatePublicationsPerYear, aggregatePublicationTypes,
  aggregateTaxonomy, binQAScores, percentageOf,
  type CategoryCount, type QualityThresholds,
} from '../../utils/charts'
import { ChartPanel } from './ChartPanel'
import {
  HorizontalBarBody, PublicationsPerYearBody, VerticalBarBody,
} from './bodies'
import { Donut } from './Donut'
import { QAScoreDistributionChart } from './index'
import { downloadCsv } from './exportUtils'
import type { PanelMenuAction } from './PanelMenu'
import { useChartFilename } from './filename'
import { SANS } from './tokens'
import { usePaletteAccent } from './palette'
import { dimensionLabel, type ChartConfig } from './customCharts'

interface DataBundle {
  qaThresholds: QualityThresholds
  qaInputs: Array<{ key: string; percentage: number }>
  extractionPapers: Array<{ values: Record<string, string | undefined> }>
  papers: Array<{ year?: number | null; entry_type?: string | null; venue?: string | null }>
  taxonomySchema: Record<string, string[]>
  venueCounts: CategoryCount[]
  extractionFieldLabels: Record<string, string>
}

interface Props {
  config: ChartConfig
  data: DataBundle
  onRemove: () => void
}

export function CustomChartPanel({ config, data, onRemove }: Props) {
  const accent   = usePaletteAccent()
  const title    = config.title || dimensionLabel(config.dimension)
  const filename = useChartFilename(`custom-${slug(title)}`)

  const { rows, csv, body, subtitle } = useMemo(() => {
    return renderConfig(config, data, accent)
  }, [config, data, accent])

  const csvAction: PanelMenuAction | null = csv ? {
    kind: 'csv',
    onSelect: () => downloadCsv(`${filename}.csv`, csv.headers, csv.rows),
  } : null

  const actions: PanelMenuAction[] = [
    ...(csvAction ? [csvAction] : []),
    { kind: 'png' },
    { kind: 'pdf' },
    { kind: 'divider' },
    { kind: 'remove', onSelect: onRemove },
  ]

  const isFlush = config.type === 'donut' && rows > 0

  return (
    <ChartPanel
      eyebrow="Custom"
      title={title}
      subtitle={subtitle}
      exportName={filename}
      actions={actions}
      flush={isFlush}
    >
      {rows === 0 ? (
        <p className="text-[13px] text-ink-muted" style={{ fontFamily: SANS }}>
          No data available for this dimension yet.
        </p>
      ) : body}
    </ChartPanel>
  )
}

// ── Per-config rendering ───────────────────────────────────────────────────

interface RenderResult {
  rows: number
  subtitle?: string
  body: React.ReactNode
  /**
   * CSV payload for the panel menu — note the filename is built from the
   * useChartFilename hook outside; here we only carry the data + headers.
   */
  csv: { headers: string[]; rows: (string | number | null)[][] } | null
}

function renderConfig(config: ChartConfig, data: DataBundle, accent: string): RenderResult {
  const d = config.dimension

  // Resolve a CategoryCount[] for whatever dimension the user picked.
  let series: CategoryCount[] = []
  let subtitle: string | undefined
  if (d.kind === 'year') {
    const years = aggregatePublicationsPerYear(data.papers)
    series = years.map(y => ({
      value: String(y.year), count: y.count,
      percentage: percentageOf(y.count, data.papers.length),
    }))
    subtitle = `${years.reduce((s, y) => s + y.count, 0)} paper${years.length === 1 ? '' : 's'} · ${years.length} year${years.length === 1 ? '' : 's'}`
  } else if (d.kind === 'pubtype') {
    series = aggregatePublicationTypes(data.papers)
    subtitle = `${series.reduce((s, c) => s + c.count, 0)} paper${series.length === 1 ? '' : 's'} · ${series.length} type${series.length === 1 ? '' : 's'}`
  } else if (d.kind === 'venue') {
    series = data.venueCounts
    subtitle = `${series.reduce((s, c) => s + c.count, 0)} paper${series.length === 1 ? '' : 's'} · ${series.length} venue${series.length === 1 ? '' : 's'}`
  } else if (d.kind === 'taxonomy') {
    const schema = data.taxonomySchema[d.key] ?? []
    series = aggregateTaxonomy(data.extractionPapers, d.key, schema).categories
    subtitle = `${data.extractionPapers.length} paper${data.extractionPapers.length === 1 ? '' : 's'} · ${series.length} categor${series.length === 1 ? 'y' : 'ies'}`
  } else if (d.kind === 'extraction') {
    series = aggregateExtractionField(data.extractionPapers, d.field)
    subtitle = `${series.reduce((s, c) => s + c.count, 0)} paper${series.length === 1 ? '' : 's'} · ${series.length} value${series.length === 1 ? '' : 's'}`
  } else if (d.kind === 'qa') {
    // Histogram is the only chart type that natively supports QA percentage.
    const bins = binQAScores(data.qaInputs, data.qaThresholds, config.bins ?? 10)
    subtitle = `${data.qaInputs.length} paper${data.qaInputs.length === 1 ? '' : 's'} assessed · ${config.bins ?? 10} bin${(config.bins ?? 10) === 1 ? '' : 's'}`
    return {
      rows: bins.length > 0 ? data.qaInputs.length : 0,
      subtitle,
      body: <QAScoreDistributionChart bins={bins} thresholds={data.qaThresholds} />,
      csv: {
        headers: ['Bin lower (%)', 'Bin upper (%)', 'Count', 'Low', 'Medium', 'High'],
        rows: bins.map(b => [b.lower, b.upper, b.count, b.low, b.medium, b.high]),
      },
    }
  }

  // Render the resolved series via the user's chosen chart type.
  let body: React.ReactNode = null
  if (series.length === 0) {
    body = null
  } else if (config.type === 'donut') {
    body = <Donut data={series} accent={accent} />
  } else if (config.type === 'hbar') {
    body = <HorizontalBarBody data={series} color={accent} />
  } else if (config.type === 'vbar' && d.kind === 'year') {
    const yearSeries = aggregatePublicationsPerYear(data.papers)
    body = <PublicationsPerYearBody data={yearSeries} color={accent} />
  } else {
    const labelled = series.map(s => ({
      label: s.value, count: s.count, percentage: s.percentage,
    }))
    body = <VerticalBarBody data={labelled} color={accent} angleLabels={labelled.length > 4} valueLabelOnTop />
  }

  return {
    rows: series.reduce((s, c) => s + c.count, 0),
    subtitle,
    body,
    csv: {
      headers: ['Value', 'Count', 'Percentage (%)'],
      rows: series.map(c => [c.value, c.count, c.percentage.toFixed(1)]),
    },
  }
}

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

// `extractionFieldLabels` is included in the bundle for forward use but kept
// optional here — TypeScript would otherwise warn about an unused field.
export type { DataBundle as CustomChartDataBundle }
