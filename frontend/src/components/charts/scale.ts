/**
 * Monochromatic luminance scale used by every donut chart in the Charts tab.
 *
 * The accent hue + saturation come from `--color-chart-accent`; only the
 * lightness varies. With N slices, lightness is interpolated linearly from
 * 22 % (darkest, largest slice) to 70 % (lightest, smallest slice). The
 * range was picked to keep adjacent slices visually distinct without anyone
 * fading into the cream page background.
 *
 * No two slices share a color — verified by unit test.
 */

const MIN_LIGHTNESS = 22
const MAX_LIGHTNESS = 70

/** Convert `#RRGGBB` to an `[h, s, l]` triple (h ∈ [0, 360), s/l ∈ [0, 100]). */
export function hexToHsl(hex: string): [number, number, number] {
  const m = hex.replace('#', '').trim()
  if (m.length !== 6) throw new Error(`hexToHsl: expected #RRGGBB, got "${hex}"`)
  const r = parseInt(m.slice(0, 2), 16) / 255
  const g = parseInt(m.slice(2, 4), 16) / 255
  const b = parseInt(m.slice(4, 6), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return [0, 0, l * 100]
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h: number
  switch (max) {
    case r:  h = (g - b) / d + (g < b ? 6 : 0); break
    case g:  h = (b - r) / d + 2; break
    default: h = (r - g) / d + 4
  }
  return [h * 60, s * 100, l * 100]
}

/** Convert `[h, s, l]` (degrees, percent, percent) to `#RRGGBB`. */
export function hslToHex(h: number, s: number, l: number): string {
  const sn = s / 100, ln = l / 100
  const c = (1 - Math.abs(2 * ln - 1)) * sn
  const hp = ((h % 360) + 360) % 360 / 60
  const x = c * (1 - Math.abs((hp % 2) - 1))
  const [r1, g1, b1] =
    hp < 1 ? [c, x, 0] :
    hp < 2 ? [x, c, 0] :
    hp < 3 ? [0, c, x] :
    hp < 4 ? [0, x, c] :
    hp < 5 ? [x, 0, c] :
             [c, 0, x]
  const m = ln - c / 2
  const to = (v: number) => Math.round((v + m) * 255).toString(16).padStart(2, '0')
  return `#${to(r1)}${to(g1)}${to(b1)}`
}

/**
 * Generate `n` monochromatic luminance variants of the accent color.
 *
 * Result[0] is the darkest (assigned to the largest slice), result[n-1] the
 * lightest. With n = 1 the returned scale is just the accent color itself.
 */
export function generateMonochromaticScale(accentHex: string, n: number): string[] {
  if (n <= 0) return []
  const [h, s] = hexToHsl(accentHex)
  if (n === 1) return [hslToHex(h, s, MIN_LIGHTNESS)]
  const out: string[] = []
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1)
    const l = MIN_LIGHTNESS + (MAX_LIGHTNESS - MIN_LIGHTNESS) * t
    out.push(hslToHex(h, s, l))
  }
  return out
}
