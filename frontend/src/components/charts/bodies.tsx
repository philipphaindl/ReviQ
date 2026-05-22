/**
 * Generic chart "bodies" — pure presentational SVGs with no panel chrome.
 * They are the building blocks the panel wrappers in `panels.tsx` and the
 * user-configurable `CustomChartPanel` compose into full chart panels.
 *
 * All bodies share the same axis style, gridline weight, tooltip surface,
 * and tabular-numerals tick typography — so a histogram next to a donut
 * next to a horizontal bar chart reads as one coherent dashboard.
 */
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

import {
  AXIS_PROPS, CATEGORY_AXIS_PROPS, COLORS, CURSOR_PROPS,
  GRID_PROPS, HBAR_GRID_PROPS, NUMERIC, SANS, VALUE_LABEL_STYLE,
} from './tokens'
import { ChartTooltip } from './Tooltip'
import type { CategoryCount, YearCount } from '../../utils/charts'

// ── Vertical bars (categorical X, count Y) ─────────────────────────────────

function VBarTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as { label: string; count: number; percentage?: number }
  return (
    <ChartTooltip title={row.label} rows={[
      { label: 'Count', value: row.count },
      ...(row.percentage != null ? [{ label: 'Share', value: `${row.percentage.toFixed(1)}%`, muted: true }] : []),
    ]} />
  )
}

export function VerticalBarBody({
  data, color = COLORS.accent, height = 220, angleLabels = false,
  valueLabelOnTop = false, tooltip = true,
}: {
  data: Array<{ label: string; count: number; percentage?: number }>
  color?: string
  height?: number
  angleLabels?: boolean
  valueLabelOnTop?: boolean
  tooltip?: boolean
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: valueLabelOnTop ? 22 : 12, right: 16,
                                       bottom: angleLabels ? 36 : 8, left: 0 }}>
        <CartesianGrid {...GRID_PROPS} />
        <XAxis dataKey="label" {...AXIS_PROPS}
               angle={angleLabels ? -25 : 0}
               textAnchor={angleLabels ? 'end' : 'middle'}
               interval={0} height={angleLabels ? 56 : 30}
               tick={{ ...AXIS_PROPS.tick, fontSize: angleLabels ? 11 : 10,
                       fill: COLORS.inkLight }} />
        <YAxis allowDecimals={false} width={28} {...AXIS_PROPS} />
        {tooltip && <Tooltip content={<VBarTooltip />} cursor={CURSOR_PROPS} />}
        <Bar dataKey="count" isAnimationActive={false} radius={[3, 3, 0, 0]}>
          {data.map((d, i) => <Cell key={`${d.label}-${i}`} fill={color} />)}
          {valueLabelOnTop && (
            <LabelList dataKey="count" position="top" style={{
              ...VALUE_LABEL_STYLE, fontSize: 10, fontWeight: 600,
            } as any} />
          )}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Horizontal bars — category labels at left, value labels at right ───────

export function HorizontalBarBody({
  data, color = COLORS.accent, yAxisWidth = 140, leftAlignLabels = false,
}: { data: CategoryCount[]; color?: string; yAxisWidth?: number; leftAlignLabels?: boolean }) {
  // Two-line rows need a taller bar slot so text doesn't overlap.
  const CHAR_PX      = 6.3    // Source Sans 3 at 11 px ≈ 6.3 px/char
  const MAX_LINE     = Math.floor((yAxisWidth - 8) / CHAR_PX)  // chars per line
  const BAR_THICKNESS = 28
  const ROW_GAP      = 16
  const ROW_HEIGHT   = BAR_THICKNESS + ROW_GAP
  const height = Math.max(160, data.length * ROW_HEIGHT + 24)

  // Custom tick: left-aligned, auto-wraps to two lines for long names.
  // Single-line names use dominantBaseline="middle" for perfect centering.
  // Two-line names split at the last space before MAX_LINE and stack vertically.
  const leftTick = leftAlignLabels
    ? (tickProps: any) => {
        const { x, y, payload } = tickProps
        const text: string = payload.value ?? ''
        const ox = x - yAxisWidth + 4   // left edge of Y-axis column

        if (text.length <= MAX_LINE) {
          return (
            <g transform={`translate(${ox},${y})`}>
              <text textAnchor="start" dominantBaseline="middle"
                    style={{ fill: COLORS.inkLight, fontSize: 11, fontFamily: SANS }}>
                {text}
              </text>
            </g>
          )
        }

        // Split at last word boundary before MAX_LINE
        const split = text.lastIndexOf(' ', MAX_LINE)
        const line1 = split > 0 ? text.slice(0, split) : text.slice(0, MAX_LINE)
        const rest  = split > 0 ? text.slice(split + 1) : text.slice(MAX_LINE)
        // Truncate second line if still too long
        const line2 = rest.length > MAX_LINE ? rest.slice(0, MAX_LINE - 1) + '…' : rest

        return (
          <g transform={`translate(${ox},${y})`}>
            <text textAnchor="start"
                  style={{ fill: COLORS.inkLight, fontSize: 11, fontFamily: SANS }}>
              <tspan x="0" dy="-7">{line1}</tspan>
              <tspan x="0" dy="14">{line2}</tspan>
            </text>
          </g>
        )
      }
    : undefined

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data.map(d => ({ ...d, label: d.value }))} layout="vertical"
                margin={{ top: 4, right: 92, bottom: 4, left: 8 }}>
        <CartesianGrid {...HBAR_GRID_PROPS} />
        <XAxis type="number" allowDecimals={false} {...AXIS_PROPS} />
        <YAxis dataKey="label" type="category" width={yAxisWidth} interval={0}
               tick={leftTick ?? CATEGORY_AXIS_PROPS.tick} />
        <Tooltip content={<VBarTooltip />} cursor={CURSOR_PROPS} />
        <Bar dataKey="count" fill={color} isAnimationActive={false}
             barSize={BAR_THICKNESS} radius={[0, 3, 3, 0]}>
          <LabelList dataKey="count" position="right" style={VALUE_LABEL_STYLE as any}
            content={({ x, y, width, height: barH, value, index }: any) => {
              const row = data[index]
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
  )
}

// ── Donut chart with side legend ───────────────────────────────────────────

// ── Publications per year — vertical bars with value labels on top ─────────

export function PublicationsPerYearBody({ data, color }: { data: YearCount[]; color?: string }) {
  const labelled = data.map(d => ({
    label: String(d.year), count: d.count,
  }))
  return (
    <VerticalBarBody data={labelled} color={color} valueLabelOnTop angleLabels={data.length > 8}
                      height={220} tooltip={false} />
  )
}

// ── Summary cards — generic faro-style large-numeric row ───────────────────

export function SummaryCardsBody({
  rows,
}: {
  rows: Array<{ label: string; value: string; sub?: string }>
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {rows.map(r => (
        <div key={r.label} className="border border-rule rounded-[4px] p-4 bg-paper/40">
          <p className="text-[10px] font-semibold uppercase text-ink-muted"
             style={{ letterSpacing: '0.12em', fontFamily: SANS }}>
            {r.label}
          </p>
          <p className="text-[28px] leading-tight text-ink mt-1 tabular-nums"
             style={{ fontFamily: '"Newsreader", Georgia, serif', fontWeight: 500 }}>
            {r.value}
          </p>
          {r.sub && (
            <p className="text-[11px] text-ink-muted mt-1" style={{ fontFamily: SANS }}>
              {r.sub}
            </p>
          )}
        </div>
      ))}
    </div>
  )
}
