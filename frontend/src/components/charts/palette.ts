/**
 * Chart colour palette system.
 *
 * A palette is a single accent hex that drives the monochromatic scale used
 * in every donut chart and bar chart on the Charts tab. Switching palettes is
 * persisted to localStorage so it survives page reloads.
 *
 * All five presets use the same muted, editorial tonality — saturated enough
 * to read, never neon. The "Navy" palette is the project default.
 */
import { createContext, useContext, useState } from 'react'
import { COLORS } from './tokens'

export interface Palette {
  name:   string
  accent: string
}

export const PALETTES: Palette[] = [
  { name: 'Navy',      accent: COLORS.accent },   // #1E3A5F — project default
  { name: 'Forest',    accent: '#1A5240' },
  { name: 'Burgundy',  accent: '#6B1A2E' },
  { name: 'Slate',     accent: '#2E3F50' },
  { name: 'Teal',      accent: '#0D5B6B' },
]

const STORAGE_KEY = 'reviq_chart_palette'

function readAccent(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored && PALETTES.some(p => p.accent === stored)) return stored
  } catch { /* localStorage unavailable */ }
  return COLORS.accent
}

/** React context — provides the currently selected accent colour. */
export const PaletteContext = createContext<string>(COLORS.accent)

/** Convenience hook — read the active accent inside any chart component. */
export function usePaletteAccent(): string {
  return useContext(PaletteContext)
}

/**
 * State hook for use in the top-level ChartsView.
 * Returns the current accent and a setter that also persists to localStorage.
 */
export function usePalette(): { accent: string; select: (a: string) => void } {
  const [accent, setAccent] = useState<string>(readAccent)

  function select(a: string) {
    setAccent(a)
    try { localStorage.setItem(STORAGE_KEY, a) } catch { /* ignore */ }
  }

  return { accent, select }
}
