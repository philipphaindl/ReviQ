import { describe, it, expect } from 'vitest'

import { generateMonochromaticScale, hexToHsl, hslToHex } from './scale'

describe('hexToHsl + hslToHex round-trip', () => {
  it('round-trips the accent color within 1° hue / 1% sat-lum', () => {
    const [h, s, l] = hexToHsl('#1E3A5F')
    const round = hexToHsl(hslToHex(h, s, l))
    expect(round[0]).toBeCloseTo(h, 0)
    expect(round[1]).toBeCloseTo(s, 0)
    expect(round[2]).toBeCloseTo(l, 0)
  })

  it('hexToHsl is robust to a leading "#" or none', () => {
    expect(hexToHsl('#1E3A5F')).toEqual(hexToHsl('1E3A5F'))
  })
})

describe('generateMonochromaticScale', () => {
  it('returns N colors, all distinct', () => {
    const scale = generateMonochromaticScale('#1E3A5F', 5)
    expect(scale).toHaveLength(5)
    expect(new Set(scale).size).toBe(5)
  })

  it('returns the empty array for n=0', () => {
    expect(generateMonochromaticScale('#1E3A5F', 0)).toEqual([])
  })

  it('produces a single dark variant for n=1 (largest slice gets darkest color)', () => {
    const [only] = generateMonochromaticScale('#1E3A5F', 1)
    const [, , l] = hexToHsl(only)
    expect(l).toBeLessThan(30)   // anchored at the darker end
  })

  it('lightness is monotonically increasing from index 0 to n-1', () => {
    const scale = generateMonochromaticScale('#1E3A5F', 6)
    const ls = scale.map(c => hexToHsl(c)[2])
    for (let i = 1; i < ls.length; i++) {
      expect(ls[i]).toBeGreaterThan(ls[i - 1])
    }
  })

  it('shares one hue across the entire scale (variation comes from luminance only)', () => {
    const scale = generateMonochromaticScale('#1E3A5F', 4)
    const hues = scale.map(c => hexToHsl(c)[0])
    for (const h of hues) {
      expect(Math.abs(h - hues[0])).toBeLessThan(1)
    }
  })

  it('matches the 4-slice spec landmarks (~22, 38, 54, 70 lightness)', () => {
    const ls = generateMonochromaticScale('#1E3A5F', 4).map(c => hexToHsl(c)[2])
    expect(ls[0]).toBeCloseTo(22, 0)
    expect(ls[1]).toBeCloseTo(38, 0)
    expect(ls[2]).toBeCloseTo(54, 0)
    expect(ls[3]).toBeCloseTo(70, 0)
  })
})
