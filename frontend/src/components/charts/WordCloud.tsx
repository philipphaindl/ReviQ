/**
 * Pure-SVG word cloud — no external library.
 *
 * Layout: Archimedean spiral from center.  Each word is placed at the first
 * spiral position where its AABB doesn't overlap any already-placed word.
 * Words that can't fit after 600 steps are silently skipped.
 *
 * Font sizes: scaled by sqrt(relative_frequency) so very frequent terms
 * dominate without completely dwarfing everything else.
 * Colors: monochromatic palette (darker = more frequent), same as donuts.
 */
import { useMemo } from 'react'

import type { CategoryCount } from '../../utils/charts'
import { generateMonochromaticScale } from './scale'
import { SANS } from './tokens'

// Source Sans 3 weight-600 average char-width ≈ 0.58 × font-size
const CHAR_RATIO = 0.58
const WORD_PAD   = 6      // minimum pixel gap between word bounding boxes
const FONT_MIN   = 11
const FONT_MAX   = 42

interface Placed {
  text:  string
  x:     number  // left edge of bounding box
  y:     number  // top edge of bounding box
  size:  number  // font-size in px
  color: string
  bw:    number  // bbox width
  bh:    number  // bbox height
}

function layoutCloud(
  words:  CategoryCount[],
  accent: string,
  W: number,
  H: number,
): Placed[] {
  if (!words.length) return []

  const maxCount = words[0].count
  const minCount = words[words.length - 1].count
  const range    = Math.max(maxCount - minCount, 1)
  const colors   = generateMonochromaticScale(accent, words.length)
  const cx = W / 2
  const cy = H / 2
  const placed: Placed[] = []

  for (let idx = 0; idx < words.length; idx++) {
    const { value, count } = words[idx]
    const t        = (count - minCount) / range
    const fontSize = Math.round(FONT_MIN + (FONT_MAX - FONT_MIN) * Math.sqrt(t))
    const bw       = value.length * fontSize * CHAR_RATIO + 2
    const bh       = fontSize * 1.15

    let done = false
    for (let step = 0; step < 600 && !done; step++) {
      const angle = step * 0.42
      const r     = step * 1.8
      const lx    = cx + r * Math.cos(angle) - bw / 2
      const ty    = cy + r * Math.sin(angle) - bh / 2

      if (lx < 2 || ty < 2 || lx + bw > W - 2 || ty + bh > H - 2) continue

      let ok = true
      for (const p of placed) {
        if (
          lx < p.x + p.bw + WORD_PAD && lx + bw + WORD_PAD > p.x &&
          ty < p.y + p.bh + WORD_PAD && ty + bh + WORD_PAD > p.y
        ) { ok = false; break }
      }

      if (ok) {
        placed.push({ text: value, x: lx, y: ty, size: fontSize,
                      color: colors[idx], bw, bh })
        done = true
      }
    }
    // words that can't be placed after 600 steps are dropped silently
  }
  return placed
}

export function WordCloud({
  data, accent, width = 620, height = 340,
}: {
  data:    CategoryCount[]
  accent:  string
  width?:  number
  height?: number
}) {
  const cloud = useMemo(
    () => layoutCloud(data.slice(0, 50), accent, width, height),
    [data, accent, width, height],
  )

  if (!cloud.length) return null

  return (
    <svg viewBox={`0 0 ${width} ${height}`}
         style={{ width: '100%', height: 'auto', display: 'block' }}
         role="img" aria-label="Keyword word cloud">
      {cloud.map(w => (
        <text
          key={w.text}
          x={w.x}
          y={w.y + w.size}    // SVG text y = baseline
          fontSize={w.size}
          fontFamily={SANS}
          fontWeight={600}
          fill={w.color}
        >
          {w.text}
        </text>
      ))}
    </svg>
  )
}
