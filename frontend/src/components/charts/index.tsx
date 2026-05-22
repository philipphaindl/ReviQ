/**
 * Public surface of the ReviQ chart system.
 *
 * The four "Synthesis charts" components (QAScoreDistributionChart,
 * TaxonomyBarColumn, KappaCard, ExtractionFieldChart) are pure chart bodies —
 * no panel chrome — and are the entities the snapshot tests pin. They are
 * composed into full panels by the higher-level `…Panel.tsx` files.
 *
 * `BAND_FILL`/`NUMERIC` are re-exported for back-compat with earlier callers.
 */
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'

import type { KappaResult } from '../../api/types'
import {
  aggregateExtractionField, aggregateTaxonomy, kappaBadgeBand,
  type QAScoreBin, type QualityBand, type QualityThresholds,
} from '../../utils/charts'
import {
  AXIS_PROPS, BAND_FILL, BAND_LABEL, CATEGORICAL, CATEGORY_AXIS_PROPS,
  COLORS, CURSOR_PROPS, GRID_PROPS, HBAR_GRID_PROPS, NUMERIC, SANS, SERIF,
  VALUE_LABEL_STYLE,
} from './tokens'
import { ChartTooltip } from './Tooltip'

// Re-export for tests + other callers.
export { BAND_FILL, BAND_LABEL, NUMERIC } from './tokens'
export const BAR_BLUE = COLORS.accent
export { CATEGORICAL }

// ── Chart 1: QA Score Distribution ─────────────────────────────────────────

function QABinTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null
  const bin = payload[0].payload as QAScoreBin
  const keys = bin.paperKeys.slice(0, 5)
  const moreCount = bin.paperKeys.length - keys.length
  return (
    <ChartTooltip
      title={`${bin.lower}–${bin.upper}%  ·  ${bin.count} paper${bin.count === 1 ? '' : 's'}`}
      rows={bin.count > 0 ? [
        ...(bin.low    > 0 ? [{ label: 'Low',    value: bin.low }] : []),
        ...(bin.medium > 0 ? [{ label: 'Medium', value: bin.medium }] : []),
        ...(bin.high   > 0 ? [{ label: 'High',   value: bin.high }] : []),
      ] : []}
    >
      {keys.length > 0 && (
        <ul className="text-ink-light mt-1.5 space-y-0.5 text-[11px]">
          {keys.map(k => <li key={k} className="truncate max-w-[220px]">{k}</li>)}
          {moreCount > 0 && <li className="text-ink-muted">+ {moreCount} more</li>}
        </ul>
      )}
    </ChartTooltip>
  )
}

export function QAScoreDistributionChart({
  bins, thresholds,
}: { bins: QAScoreBin[]; thresholds: QualityThresholds }) {
  const data = bins.map(b => ({ ...b, binLabel: `${b.lower}` }))
  // Recharts categorical X scale only places ReferenceLine on existing tick values.
  const mediumTick = `${Math.floor(thresholds.medium / 10) * 10}`
  const highTick   = `${Math.floor(thresholds.high   / 10) * 10}`
  return (
    <div id="chart-quality-distribution-svg" data-testid="qa-distribution-chart">
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ top: 16, right: 16, bottom: 6, left: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis dataKey="binLabel" {...AXIS_PROPS} />
          <YAxis allowDecimals={false} width={28} {...AXIS_PROPS} />
          <Tooltip content={<QABinTooltip />} cursor={CURSOR_PROPS} />
          <Bar dataKey="low"    stackId="qa" fill={BAND_FILL.low}    isAnimationActive={false} radius={[0, 0, 0, 0]} />
          <Bar dataKey="medium" stackId="qa" fill={BAND_FILL.medium} isAnimationActive={false} radius={[0, 0, 0, 0]} />
          <Bar dataKey="high"   stackId="qa" fill={BAND_FILL.high}   isAnimationActive={false} radius={[3, 3, 0, 0]} />
          <ReferenceLine x={mediumTick} stroke={COLORS.inkLight} strokeDasharray="3 3" strokeWidth={0.8}
            label={{ value: `Medium ≥ ${thresholds.medium}%`, position: 'insideTopRight',
                     fill: COLORS.inkLight, fontSize: 10, fontFamily: SANS } as any} />
          <ReferenceLine x={highTick} stroke={COLORS.inkLight} strokeDasharray="3 3" strokeWidth={0.8}
            label={{ value: `High ≥ ${thresholds.high}%`, position: 'insideTopRight',
                     fill: COLORS.inkLight, fontSize: 10, fontFamily: SANS } as any} />
        </BarChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-2 text-[11px] text-ink-light" aria-label="band legend"
           style={{ fontFamily: SANS }}>
        {(['low', 'medium', 'high'] as QualityBand[]).map(band => (
          <span key={band} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-[2px]" style={{ backgroundColor: BAND_FILL[band] }} />
            {BAND_LABEL[band]}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Chart 2: Taxonomy Distribution (horizontal bars) ──────────────────────

function TaxonomyBarTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as { value: string; count: number; percentage: number }
  return (
    <ChartTooltip
      title={row.value}
      rows={[
        { label: 'Count',  value: row.count },
        { label: 'Share',  value: `${row.percentage.toFixed(1)}%`, muted: true },
      ]}
    />
  )
}

export function TaxonomyBarColumn({
  dist, color = COLORS.accent,
}: { dist: ReturnType<typeof aggregateTaxonomy>; color?: string }) {
  // Issue 3 of iteration 2: 28 px minimum bar thickness, 16 px gap. Even on
  // the rare path where this component is still used for an hbar render
  // (CustomChartPanel "hbar" type), the bars stay readable.
  const BAR_THICKNESS = 28
  const ROW_GAP = 16
  const ROW_HEIGHT = BAR_THICKNESS + ROW_GAP
  const height = Math.max(140, dist.categories.length * ROW_HEIGHT + 24)
  return (
    <div data-testid={`taxonomy-bars-${dist.key}`}>
      <p className="text-[10px] font-semibold uppercase text-ink-muted mb-2"
         style={{ letterSpacing: '0.12em', fontFamily: SANS }}>
        {dist.label}
      </p>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={dist.categories} layout="vertical"
                  margin={{ top: 4, right: 80, bottom: 4, left: 8 }}>
          <CartesianGrid {...HBAR_GRID_PROPS} />
          <XAxis type="number" allowDecimals={false} {...AXIS_PROPS} />
          <YAxis dataKey="value" type="category" width={120} interval={0}
                 {...CATEGORY_AXIS_PROPS} />
          <Tooltip content={<TaxonomyBarTooltip />} cursor={CURSOR_PROPS} />
          <Bar dataKey="count" fill={color} isAnimationActive={false}
               barSize={BAR_THICKNESS} radius={[0, 3, 3, 0]}>
            <LabelList dataKey="count" position="right"
              content={({ x, y, width, height: barH, value, index }: any) => {
                const row = dist.categories[index]
                const pct = row ? row.percentage : 0
                const cx = (Number(x) || 0) + (Number(width) || 0) + 6
                const cy = (Number(y) || 0) + (Number(barH) || 0) / 2 + 4
                return (
                  <text x={cx} y={cy} style={VALUE_LABEL_STYLE as any}>
                    {value}  ·  {pct.toFixed(1)}%
                  </text>
                )
              }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Chart 3: Inter-Rater Agreement card ────────────────────────────────────

export function KappaCard({ phaseLabel, kappa }: { phaseLabel: string; kappa: KappaResult }) {
  const band = kappaBadgeBand(kappa.kappa)
  return (
    <div
      className="border border-rule rounded-[4px] p-4 bg-paper/40"
      data-testid={`kappa-card-${kappa.phase}`}
      style={{ fontFamily: SANS }}
    >
      <p className="text-[10px] font-semibold uppercase text-ink-muted"
         style={{ letterSpacing: '0.12em' }}>
        {phaseLabel}
      </p>
      <p className="text-[12px] text-ink-light mt-0.5">
        {kappa.r1_name}  vs.  {kappa.r2_name}
      </p>

      {/* Headline κ + CI */}
      <div className="mt-3 flex items-baseline gap-2" style={NUMERIC}>
        <span className="text-[32px] leading-none text-ink"
              style={{ fontFamily: SERIF, fontWeight: 500 }}>
          {kappa.kappa.toFixed(3)}
        </span>
        <span className="text-[11px] text-ink-muted">
          95% CI [{kappa.kappa_ci_lower.toFixed(3)}, {kappa.kappa_ci_upper.toFixed(3)}]
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 mt-3 text-[12px]" style={NUMERIC}>
        <dt className="text-ink-muted">PABAK</dt>
        <dd className="text-ink text-right font-medium">{kappa.pabak.toFixed(3)}</dd>
        <dt className="text-ink-muted">Po</dt>
        <dd className="text-ink text-right font-medium">{(kappa.observed_agreement * 100).toFixed(1)}%</dd>
        <dt className="text-ink-muted">Sample</dt>
        <dd className="text-ink text-right font-medium">n = {kappa.n_papers}</dd>
      </dl>

      <span className="inline-block mt-3 px-2 py-0.5 text-[11px] font-semibold rounded-[4px]"
            style={{ backgroundColor: BAND_FILL[band], color: 'white' }}>
        {kappa.interpretation}
      </span>
    </div>
  )
}

// ── Chart 4: Custom Extraction Field Aggregation ───────────────────────────

function ExtractionFieldTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as { value: string; count: number; percentage?: number }
  return (
    <ChartTooltip
      title={row.value}
      rows={[
        { label: 'Count', value: row.count },
        ...(row.percentage != null
          ? [{ label: 'Share', value: `${row.percentage.toFixed(1)}%`, muted: true }]
          : []),
      ]}
    />
  )
}

export function ExtractionFieldChart({
  categories, color = COLORS.accent,
}: { categories: ReturnType<typeof aggregateExtractionField>; color?: string }) {
  // Decide layout: vertical bars for ≤ 5 categories, horizontal for more.
  if (categories.length > 5) {
    const height = Math.max(160, categories.length * 30)
    return (
      <div data-testid="extraction-field-chart">
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={categories} layout="vertical"
                    margin={{ top: 4, right: 64, bottom: 4, left: 8 }}>
            <CartesianGrid {...HBAR_GRID_PROPS} />
            <XAxis type="number" allowDecimals={false} {...AXIS_PROPS} />
            <YAxis dataKey="value" type="category" width={140} interval={0}
                   {...CATEGORY_AXIS_PROPS} />
            <Tooltip content={<ExtractionFieldTooltip />} cursor={CURSOR_PROPS} />
            <Bar dataKey="count" fill={color} isAnimationActive={false}
                 barSize={14} radius={[0, 3, 3, 0]}>
              <LabelList dataKey="count" position="right" style={VALUE_LABEL_STYLE as any}
                formatter={(v: any, _e: any, _i: number, _arr: any, payload: any) => {
                  const pct = payload?.percentage ?? 0
                  return `${v}  ·  ${pct.toFixed(0)}%`
                }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  return (
    <div data-testid="extraction-field-chart">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={categories} margin={{ top: 16, right: 16, bottom: 36, left: 0 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis dataKey="value" {...AXIS_PROPS}
                 angle={-25} textAnchor="end" interval={0} height={56}
                 tick={{ ...AXIS_PROPS.tick, fontSize: 11, fill: COLORS.inkLight }} />
          <YAxis allowDecimals={false} width={28} {...AXIS_PROPS} />
          <Tooltip content={<ExtractionFieldTooltip />} cursor={CURSOR_PROPS} />
          <Bar dataKey="count" isAnimationActive={false} radius={[3, 3, 0, 0]}>
            {categories.map(c => <Cell key={c.value} fill={color} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
