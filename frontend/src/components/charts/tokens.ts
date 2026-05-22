/**
 * Shared design tokens for the ReviQ chart system.
 *
 * Every panel in the Results → Charts tab pulls its colors, typography,
 * gridline weights, and tooltip styling from this file. Keeping them in
 * one place is what makes the chart language feel uniform across the
 * page and across the PDF/PNG exports.
 *
 * The values match (and must stay in sync with) tailwind.config.js — but
 * recharts only consumes raw color/CSS values, hence the duplication.
 */
import type { CSSProperties } from 'react'
import type { QualityBand } from '../../utils/charts'

// ── Palette ────────────────────────────────────────────────────────────────
// The single source of truth for the chart accent. The CSS variable
// `--color-chart-accent` in src/index.css resolves to the same hex — TS
// callers (recharts, html-to-image) need the literal because they don't
// resolve CSS variables, so the two must be kept in lock-step.
export const CHART_ACCENT_VAR = '--color-chart-accent'

export const COLORS = {
  ink:       '#2B2B2B',
  inkLight:  '#555555',
  inkMuted:  '#888888',
  rule:      '#E5E2DD',
  paper:     '#FAF8F5',
  surface:   '#FFFFFF',
  /** The single accent hue used by every non-status chart in the Results tab. */
  accent:    '#1E3A5F',
  accentSoft:'#F0F3F7',     // tooltip cursor wash, derived from accent at very low chroma
  include:   '#2D6A4F',     // status — QA "high"
  uncertain: '#8B6914',     // status — QA "medium"
  exclude:   '#8B1A1A',     // status — QA "low"
} as const

export const BAND_FILL: Record<QualityBand, string> = {
  low:    '#DC2626',   // traffic-light red
  medium: '#F59E0B',   // traffic-light amber
  high:   '#16A34A',   // traffic-light green
}
export const BAND_LABEL: Record<QualityBand, string> = {
  low: 'Low', medium: 'Medium', high: 'High',
}

/**
 * Legacy categorical sequence — kept only for back-compat with snapshot
 * tests. New donut charts must use {@link generateMonochromaticScale} from
 * `./scale.ts` to derive luminance variants of the single accent hue.
 *
 * @deprecated Use generateMonochromaticScale(COLORS.accent, n) instead.
 */
export const CATEGORICAL = [
  COLORS.accent,
  '#3E5476',
  '#637A9B',
  '#8AA0BC',
] as const

// ── Typography ────────────────────────────────────────────────────────────

export const NUMERIC: CSSProperties = { fontVariantNumeric: 'tabular-nums' }
export const SANS  = '"Source Sans 3", system-ui, sans-serif'
export const SERIF = '"Newsreader", Georgia, serif'
/** Monospace — matches the `stat-value` class used on all other pages. */
export const MONO  = '"JetBrains Mono", Menlo, monospace'

/** Style preset for recharts <XAxis|YAxis tick={...}>. */
export const TICK_STYLE = {
  fontSize: 10,
  fill: COLORS.inkMuted,
  fontFamily: SANS,
  fontVariantNumeric: 'tabular-nums',
}

/** Style preset for category-axis ticks (typically darker + bigger). */
export const CATEGORY_TICK_STYLE = {
  fontSize: 11,
  fill: COLORS.inkLight,
  fontFamily: SANS,
}

/** Style preset for axis tick on inline value labels. */
export const VALUE_LABEL_STYLE = {
  fontSize: 11,
  fill: COLORS.ink,
  fontFamily: SANS,
  fontVariantNumeric: 'tabular-nums',
  fontWeight: 600,
}

// ── Common chart props (passed to <CartesianGrid>, <XAxis>, etc.) ─────────

export const GRID_PROPS = {
  stroke: COLORS.rule,
  strokeDasharray: '2 4',
  strokeWidth: 0.7,
  vertical: false,
} as const

export const HBAR_GRID_PROPS = {
  ...GRID_PROPS,
  vertical: true,
  horizontal: false,
} as const

export const AXIS_PROPS = {
  tickLine: false,
  axisLine: false,
  tick: TICK_STYLE as any,
} as const

export const CATEGORY_AXIS_PROPS = {
  tickLine: false,
  axisLine: false,
  tick: CATEGORY_TICK_STYLE as any,
} as const

export const CURSOR_PROPS = { fill: COLORS.accentSoft, opacity: 0.5 } as const

// ── Body text baseline — keeps chart text on the same colour as the Search
//    Database Performance table data rows (#2B2B2B).
export const BODY_TEXT_STYLE: CSSProperties = {
  fontFamily: SANS,
  color: COLORS.ink,
}

// ── Shared tooltip baseline (apply NUMERIC inside) ────────────────────────

export const TOOLTIP_CLASS =
  'bg-surface border border-rule rounded-[4px] shadow-[0_8px_24px_rgba(0,0,0,0.08)] px-2.5 py-1.5 text-2xs text-ink'
