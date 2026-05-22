import { createContext, useContext } from 'react'

const STORAGE_KEY = 'reviq_export_padding'
const DEFAULT_PADDING = 8
const MIN_PADDING = 0
const MAX_PADDING = 40

/** Provides the live export-padding value to all chart components in the tree. */
export const ExportPaddingContext = createContext(DEFAULT_PADDING)
export function useExportPadding(): number { return useContext(ExportPaddingContext) }

export function getExportPadding(): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === null) return DEFAULT_PADDING
    const n = Number(raw)
    return Number.isFinite(n) ? Math.min(MAX_PADDING, Math.max(MIN_PADDING, n)) : DEFAULT_PADDING
  } catch {
    return DEFAULT_PADDING
  }
}

export function setExportPadding(px: number) {
  const clamped = Math.min(MAX_PADDING, Math.max(MIN_PADDING, Math.round(px)))
  try { localStorage.setItem(STORAGE_KEY, String(clamped)) } catch { /* ignore */ }
}

export { DEFAULT_PADDING, MIN_PADDING, MAX_PADDING }
