/**
 * Pure SVG-string generator for donut charts — no DOM, no React, no side effects.
 *
 * This is the single rendering function used by both the web view
 * (dangerouslySetInnerHTML) and file exports (font-injected SVG / PNG).
 * Changing element placement here changes both outputs simultaneously.
 *
 * Geometry is identical to the previous React-JSX rendering:
 *   • Fixed outer radius (DONUT_RADIUS) — consistent size across all cards.
 *   • Straight radial leader lines from anchor dot to text label.
 *   • Dynamic viewBox computed from label bounding-box estimates; pad added on
 *     all four sides.
 *   • Collision avoidance: radial extension (+20 px steps, max +60 px).
 *
 * Exports are tight-cropped at download time via getBBox() in exportUtils.ts.
 */
import type { CategoryCount } from '../../utils/charts'
import { generateMonochromaticScale } from './scale'
import { COLORS } from './tokens'

// CSS font stack for use inside double-quoted XML/HTML attributes.
// SANS from tokens.ts uses double-quoted font names ("Source Sans 3") which
// would terminate the enclosing attribute early; single quotes are required.
const CSS_SANS = "'Source Sans 3', system-ui, sans-serif"

// ── Fixed geometry ─────────────────────────────────────────────────────────────

const COORD_SIZE = 240
/** Outer ring radius in SVG user units.  Fixed globally — same for every donut. */
export const DONUT_RADIUS = COORD_SIZE * 0.44          // ≈ 105.6
const CX               = COORD_SIZE / 2                // ring center x = 120
const CY               = COORD_SIZE / 2                // ring center y = 120
const RI               = DONUT_RADIUS * 0.56           // inner radius ≈ 59.1

/**
 * Fixed canvas half-size beyond the outer ring.  ALL donuts use this same
 * value regardless of label count or length, so the ring always renders at
 * the same pixel size when the SVG fills its container.
 *
 * Chosen for typical SLR data (3–5 categories, labels ≤12 chars).
 * Verified safe for 3-slice "Evaluation Research" at cos_m=1 (margin 13 px).
 * 5+ slices with 13-char labels may be clipped — increase if needed.
 */
const FIXED_VIEW_PAD = 130

const LABEL_LINE_H    = 13    // px between adjacent text baselines
const LABEL_STEP      = 20    // extension increment per collision pass
const LABEL_MAX_EXTRA = 60    // max extra extension beyond BASE_EXT
const LABEL_SAFETY    = 8     // margin buffer on each side
const CHAR_W          = 6.5   // conservative char-width estimate (Source Sans 3, 11 px, 600)

// ── Utilities ─────────────────────────────────────────────────────────────────

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function labelLines(name: string): string[] {
  if (name.includes(' ')) return name.split(' ')
  return [name.length > 12 ? name.slice(0, 11) + '…' : name]
}

function arcPath(a0: number, a1: number): string {
  const ro = DONUT_RADIUS, ri = RI, cx = CX, cy = CY
  const sweep = a1 - a0
  if (sweep <= 0) return ''
  const isFull = sweep >= Math.PI * 2 - 1e-9
  const large  = sweep > Math.PI ? 1 : 0
  if (isFull) {
    return [
      `M ${cx + ro} ${cy}`,
      `A ${ro} ${ro} 0 1 1 ${cx - ro} ${cy}`,
      `A ${ro} ${ro} 0 1 1 ${cx + ro} ${cy}`,
      `M ${cx + ri} ${cy}`,
      `A ${ri} ${ri} 0 1 0 ${cx - ri} ${cy}`,
      `A ${ri} ${ri} 0 1 0 ${cx + ri} ${cy} Z`,
    ].join(' ')
  }
  const ox0 = cx + ro * Math.cos(a0), oy0 = cy + ro * Math.sin(a0)
  const ox1 = cx + ro * Math.cos(a1), oy1 = cy + ro * Math.sin(a1)
  const ix1 = cx + ri * Math.cos(a1), iy1 = cy + ri * Math.sin(a1)
  const ix0 = cx + ri * Math.cos(a0), iy0 = cy + ri * Math.sin(a0)
  return `M ${ox0} ${oy0} A ${ro} ${ro} 0 ${large} 1 ${ox1} ${oy1} L ${ix1} ${iy1} A ${ri} ${ri} 0 ${large} 0 ${ix0} ${iy0} Z`
}

// ── Geometry computation ───────────────────────────────────────────────────────

interface SliceData extends CategoryCount {
  path: string
  mid:  number
}

interface LabelItem extends SliceData {
  isRight: boolean
  p1x_in: number; p1y_in: number  // anchor dot (5 px inside ring)
  endX:   number; endY:   number  // connector line end
  textX:  number; textY:  number  // text anchor point
}

function buildSlices(data: CategoryCount[], total: number): SliceData[] {
  let start = -Math.PI / 2
  return data
    .filter(d => d.count > 0)
    .map(d => {
      const sweep = total > 0 ? (d.count / total) * 2 * Math.PI : 0
      const end   = start + sweep
      const s     = { ...d, path: arcPath(start, end), mid: (start + end) / 2 }
      start = end
      return s
    })
}

function buildLabels(slices: SliceData[]): { items: LabelItem[]; padH: number; padV: number } {
  if (slices.length === 0) return { items: [], padH: 16, padV: 16 }

  const ro       = DONUT_RADIUS
  const BASE_EXT = Math.max(48, ro * 0.35)
  const exts     = slices.map(() => BASE_EXT)

  type Box = { l: number; r: number; t: number; b: number }

  function approxBox(i: number): Box {
    const { mid } = slices[i], ext = exts[i]
    const cm = Math.cos(mid), sm = Math.sin(mid)
    const tx = CX + (ro + ext + 4) * cm
    const ty = CY + (ro + ext + 4) * sm
    const W = 80, H = 30
    return { l: cm >= 0 ? tx : tx - W, r: cm >= 0 ? tx + W : tx, t: ty - H / 2, b: ty + H / 2 }
  }
  function overlaps(a: Box, b: Box) {
    return a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t
  }

  for (let pass = 0; pass < 3; pass++) {
    let any = false
    for (let i = 0; i < slices.length - 1; i++) {
      for (let j = i + 1; j < slices.length; j++) {
        if (overlaps(approxBox(i), approxBox(j))) {
          if (exts[i] - BASE_EXT < LABEL_MAX_EXTRA) { exts[i] += LABEL_STEP; any = true }
          if (exts[j] - BASE_EXT < LABEL_MAX_EXTRA) { exts[j] += LABEL_STEP; any = true }
        }
      }
    }
    if (!any) break
  }

  // Compute margins in center-relative coordinates.
  let mRight = 0, mLeft = 0, mTop = 0, mBottom = 0
  slices.forEach((s, i) => {
    const cm = Math.cos(s.mid), sm = Math.sin(s.mid)
    const ext = exts[i]
    const tx  = (ro + ext + 4) * cm    // relative text-anchor x
    const ty  = (ro + ext + 4) * sm    // relative text-anchor y

    const words     = labelLines(s.value)
    const countLine = `${s.count} · ${s.percentage.toFixed(1)}%`
    const maxW      = Math.max(...[...words, countLine].map(l => l.length * CHAR_W))
    const totalH    = words.length * LABEL_LINE_H + LABEL_LINE_H + 4

    const bLeft   = cm >= 0 ? tx : tx - maxW
    const bRight  = cm >= 0 ? tx + maxW : tx
    const bTop    = ty - totalH / 2
    const bBottom = ty + totalH / 2

    mRight  = Math.max(mRight,   bRight  + LABEL_SAFETY)
    mLeft   = Math.max(mLeft,   -bLeft   + LABEL_SAFETY)
    mTop    = Math.max(mTop,    -bTop    + LABEL_SAFETY)
    mBottom = Math.max(mBottom,  bBottom + LABEL_SAFETY)
  })

  const padH = Math.max(mLeft, mRight)
  const padV = Math.max(mTop,  mBottom)

  const items: LabelItem[] = slices.map((s, i) => {
    const cm  = Math.cos(s.mid), sm = Math.sin(s.mid)
    const ext = exts[i]
    return {
      ...s,
      isRight: cm >= 0,
      p1x_in: CX + (DONUT_RADIUS - 5) * cm,
      p1y_in: CY + (DONUT_RADIUS - 5) * sm,
      endX:   CX + (DONUT_RADIUS + ext) * cm,
      endY:   CY + (DONUT_RADIUS + ext) * sm,
      textX:  CX + (DONUT_RADIUS + ext + 4) * cm,
      textY:  CY + (DONUT_RADIUS + ext + 4) * sm,
    }
  })

  return { items, padH, padV }
}

// ── Public API ─────────────────────────────────────────────────────────────────

/**
 * Generate a complete SVG XML string for the given donut data.
 *
 * The viewBox is always 2*(DONUT_RADIUS + FIXED_VIEW_PAD) square so every
 * donut renders at the same scale when placed in same-width cards.  Label
 * positions are still computed accurately (buildLabels) — the canvas is just
 * large enough to guarantee they fit for any realistic SLR dataset.
 *
 * @param data      Array of category counts (zero-count entries are skipped).
 * @param accent    Base accent color for the monochromatic scale.
 * @param ariaLabel Accessible label on the root <svg> element.
 */
export function generateDonutSvgString(
  data: CategoryCount[],
  accent: string,
  ariaLabel = 'Donut chart',
  svgId?: string,
): string {
  const nonZero = data.filter(d => d.count > 0)
  const total   = data.reduce((s, d) => s + d.count, 0)

  const scale    = generateMonochromaticScale(accent, Math.max(nonZero.length, 1))
  const colorMap = new Map<string, string>()
  nonZero.forEach((d, i) => colorMap.set(d.value, scale[i]))

  const slices                         = buildSlices(data, total)
  const { items: labels, padH, padV }  = buildLabels(slices)

  const ro = DONUT_RADIUS
  const ri = RI
  // Fixed canvas — identical for every donut so ring size is consistent.
  const vbX = CX - ro - FIXED_VIEW_PAD
  const vbY = CY - ro - FIXED_VIEW_PAD
  const vbW = 2 * (ro + FIXED_VIEW_PAD)
  const vbH = vbW

  // Export content bounds — measured from CENTER (padH/padV are center-to-edge
  // distances that already include LABEL_SAFETY).  Capped to the viewBox
  // half-extent (ro + FIXED_VIEW_PAD) so the crop never references clipped
  // content.  Using actual padH/padV when they fit inside the viewBox gives
  // tight per-axis crops — e.g. when slices land at diagonal angles the
  // vertical extent (padV) may be much less than the viewBox height, avoiding
  // the large empty space below that appeared with the old square crop.
  const viewHalf = DONUT_RADIUS + FIXED_VIEW_PAD   // viewBox half-extent from center
  const exportH  = Math.min(padH, viewHalf)
  const exportV  = Math.min(padV, viewHalf)
  const contentX = CX - exportH                     // center minus distance to left edge
  const contentY = CY - exportV
  const contentW = 2 * exportH
  const contentH = 2 * exportV

  // ── Ring ──────────────────────────────────────────────────────────────────
  const ringXml = total === 0
    ? `<circle cx="${CX}" cy="${CY}" r="${(ro + ri) / 2}" fill="none" stroke="${COLORS.rule}" stroke-width="${ro - ri}"/>`
    : slices.map(s =>
        `<path d="${s.path}" fill="${colorMap.get(s.value) ?? accent}" stroke="${COLORS.surface}" stroke-width="1"/>`
      ).join('')

  // ── Connectors + labels ───────────────────────────────────────────────────
  const labelsXml = labels.map(lbl => {
    const fill   = colorMap.get(lbl.value) ?? accent
    const words  = labelLines(lbl.value)
    const span   = words.length * LABEL_LINE_H
    const startY = lbl.textY - span / 2
    const anchor = lbl.isRight ? 'start' : 'end'

    const tspans = words.map((w, i) =>
      `<tspan x="${lbl.textX}" y="${startY + i * LABEL_LINE_H}" style="font-size:11px;font-weight:600;fill:${COLORS.ink}">${esc(w)}</tspan>`
    ).join('')
    const countTspan =
      `<tspan x="${lbl.textX}" y="${startY + words.length * LABEL_LINE_H}" ` +
      `style="font-size:10px;fill:${COLORS.inkMuted};font-variant-numeric:tabular-nums">` +
      `${lbl.count} · ${lbl.percentage.toFixed(1)}%</tspan>`

    return (
      `<g>` +
      `<line x1="${lbl.p1x_in}" y1="${lbl.p1y_in}" x2="${lbl.endX}" y2="${lbl.endY}" ` +
      `stroke="${fill}" stroke-width="1.1" opacity="0.75"/>` +
      `<text text-anchor="${anchor}" style="font-family:${CSS_SANS}">${tspans}${countTspan}</text>` +
      `</g>`
    )
  }).join('')

  // ── Anchor dots ───────────────────────────────────────────────────────────
  const dotsXml = labels.map(lbl => {
    const fill = colorMap.get(lbl.value) ?? accent
    return `<circle cx="${lbl.p1x_in}" cy="${lbl.p1y_in}" r="3" fill="${fill}" stroke="${COLORS.surface}" stroke-width="1"/>`
  }).join('')

  // All chart content lives in a named group so exportUtils can call
  // getBBox() on it rather than on the root <svg>.  getBBox() on the root
  // <svg> returns the viewport rectangle (0,0,vbW,vbH) in some browsers,
  // not the content bounding box, producing asymmetric export crops.
  return (
    `<svg width="${vbW}" height="${vbH}" viewBox="${vbX} ${vbY} ${vbW} ${vbH}" ` +
    `style="width:100%;height:auto;display:block" role="img" aria-label="${esc(ariaLabel)}"` +
    (svgId ? ` id="${esc(svgId)}"` : '') + ` ` +
    `data-content-x="${contentX}" data-content-y="${contentY}" ` +
    `data-content-w="${contentW}" data-content-h="${contentH}">` +
    `<g data-donut-content>${ringXml}${labelsXml}${dotsXml}</g>` +
    `</svg>`
  )
}
