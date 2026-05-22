/**
 * The frame every chart sits inside. One component, one visual language.
 *
 * Layout, top to bottom:
 *   1. Eyebrow row     — uppercase Source Sans, 9px, kind/grouping label
 *   2. Title           — Newsreader serif, 18px, the chart name
 *   3. Subtitle        — Source Sans regular, 12px, the n=… / metric line
 *   4. KPI strip       — optional, faro-style large numeric readouts
 *   5. Chart body      — caller's choice (recharts, a table, a card grid…)
 *   6. Footnote        — optional, italic 11px, citations or methodology
 *
 * The chart body is wrapped in a `ref` we expose via the `bodyRef` prop —
 * exportUtils relies on this to capture only the chart, not the panel chrome.
 */
import { useRef, type ReactNode } from 'react'

import { PanelMenu, type PanelMenuAction } from './PanelMenu'
import { COLORS, MONO, NUMERIC, SANS } from './tokens'

export interface ChartPanelProps {
  /** Tiny uppercase tracking label rendered above the title (e.g. "Quality"). */
  eyebrow?: string
  title: string
  subtitle?: ReactNode
  /** Optional faro-style KPI strip — array of {label, value}. */
  kpis?: Array<{ label: string; value: ReactNode; tone?: 'default' | 'positive' | 'negative' | 'neutral' }>
  /** Footnote rendered below the body (e.g. a citation). */
  footnote?: ReactNode
  /** Menu items to expose top-right: CSV / PNG / PDF and an optional Remove. */
  actions: PanelMenuAction[]
  /** A stable filename stem for exports (no extension). */
  exportName: string
  /** Test id stamped on the outer panel. */
  testId?: string
  /** Whether the chart body has its own padding (false = panel pads it). */
  flush?: boolean
  /** Optional content rendered between the title block and the ⋯ menu (e.g. a mode toggle). */
  headerExtra?: ReactNode
  children: ReactNode
}

const KPI_TONE = {
  default:  COLORS.ink,
  positive: COLORS.include,
  negative: COLORS.exclude,
  neutral:  COLORS.inkMuted,
} as const

export function ChartPanel({
  eyebrow, title, subtitle, kpis, footnote, actions, exportName,
  testId, flush = false, headerExtra, children,
}: ChartPanelProps) {
  const bodyRef = useRef<HTMLDivElement>(null)

  return (
    <section
      className="border border-rule rounded-[4px] bg-surface overflow-hidden"
      data-testid={testId}
      data-export-name={exportName}
    >
      {/* Header — single horizontal row, generous padding (faro breathes). */}
      <header className="flex items-start justify-between gap-4 px-5 pt-4 pb-3">
        <div className="min-w-0">
          {eyebrow && (
            <p
              className="text-[10px] font-semibold uppercase text-ink-muted mb-1"
              style={{ letterSpacing: '0.12em', fontFamily: SANS }}
            >
              {eyebrow}
            </p>
          )}
          <h3
            className="text-[16px] leading-tight text-ink-light font-semibold"
            style={{ fontFamily: SANS }}
          >
            {title}
          </h3>
          {subtitle && (
            <p
              className="text-[12px] text-ink-light mt-1"
              style={{ ...NUMERIC, fontFamily: SANS }}
            >
              {subtitle}
            </p>
          )}
        </div>
        {headerExtra && (
          <div className="shrink-0 flex items-center">{headerExtra}</div>
        )}
        <PanelMenu actions={actions} bodyRef={bodyRef} exportName={exportName} />
      </header>

      {/* Optional KPI strip — large numerics, faro1-style. */}
      {kpis && kpis.length > 0 && (
        <div className="flex flex-wrap gap-x-8 gap-y-3 px-5 pt-1 pb-4 border-b border-rule/60">
          {kpis.map(k => (
            <div key={String(k.label)} className="min-w-[80px]">
              <p
                className="text-2xs font-semibold uppercase tracking-label text-ink-muted"
                style={{ fontFamily: SANS }}
              >
                {k.label}
              </p>
              <p
                className="text-2xl leading-tight mt-1 font-bold"
                style={{
                  ...NUMERIC,
                  fontFamily: MONO,
                  color: KPI_TONE[k.tone ?? 'default'],
                }}
              >
                {k.value}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Body — chart, table, card grid. The ref is what export helpers capture. */}
      <div
        ref={bodyRef}
        className={flush ? '' : 'px-5 py-4'}
        data-chart-body="true"
      >
        {children}
      </div>

      {footnote && (
        <footer className="px-5 pb-4 pt-1">
          <p
            className="text-[11px] italic text-ink-muted"
            style={{ fontFamily: SANS }}
          >
            {footnote}
          </p>
        </footer>
      )}
    </section>
  )
}
