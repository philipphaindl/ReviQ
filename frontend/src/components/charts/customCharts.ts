/**
 * Custom-chart configuration model + localStorage persistence.
 *
 * Each user-added chart panel is a `ChartConfig` row scoped to a project.
 * Configs serialize to JSON, survive page reloads, and are reconstructed by
 * `CustomChartPanel` against the live SLR data on mount.
 */
import { useCallback, useEffect, useState } from 'react'

export type CustomChartType = 'vbar' | 'hbar' | 'donut' | 'histogram'

export type ChartDimension =
  | { kind: 'year' }
  | { kind: 'qa' }
  | { kind: 'pubtype' }
  | { kind: 'venue' }
  | { kind: 'taxonomy';   key: string }
  | { kind: 'extraction'; field: string }

export interface ChartConfig {
  /** Stable id assigned on creation (UUID-shaped, but any unique string works). */
  id: string
  type: CustomChartType
  dimension: ChartDimension
  /** User-supplied title; if empty the panel derives one from the dimension. */
  title?: string
  /** Histogram bin count (only meaningful for `type='histogram'`). */
  bins?: number
}

const STORAGE_PREFIX = 'reviq_custom_charts_'

function storageKey(projectId: number) {
  return `${STORAGE_PREFIX}${projectId}`
}

function readStored(projectId: number): ChartConfig[] {
  try {
    const raw = localStorage.getItem(storageKey(projectId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeStored(projectId: number, configs: ChartConfig[]) {
  try {
    localStorage.setItem(storageKey(projectId), JSON.stringify(configs))
  } catch {
    /* localStorage quota or disabled — silently degrade. */
  }
}

/**
 * React hook that exposes a project's custom chart list along with
 * add/remove/clear actions. Persists to localStorage on every change.
 */
export function useCustomCharts(projectId: number) {
  const [configs, setConfigs] = useState<ChartConfig[]>(() => readStored(projectId))

  // Reload when the project changes so we don't leak one SLR's panels into another.
  useEffect(() => {
    setConfigs(readStored(projectId))
  }, [projectId])

  useEffect(() => {
    writeStored(projectId, configs)
  }, [projectId, configs])

  const add = useCallback((cfg: Omit<ChartConfig, 'id'>) => {
    const id = (typeof crypto !== 'undefined' && 'randomUUID' in crypto)
      ? crypto.randomUUID()
      : `cc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    setConfigs(prev => [...prev, { ...cfg, id }])
  }, [])

  const remove = useCallback((id: string) => {
    setConfigs(prev => prev.filter(c => c.id !== id))
  }, [])

  const clear = useCallback(() => setConfigs([]), [])

  return { configs, add, remove, clear }
}

/** Human-readable label for a dimension (used as the default panel title). */
export function dimensionLabel(d: ChartDimension): string {
  switch (d.kind) {
    case 'year':       return 'Publications per year'
    case 'qa':         return 'Quality assessment score'
    case 'pubtype':    return 'Publication type'
    case 'venue':      return 'Publication venues'
    case 'taxonomy':   return `Taxonomy — ${humanize(d.key)}`
    case 'extraction': return `Extraction — ${humanize(d.field)}`
  }
}

function humanize(snake: string) {
  return snake.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

/** Default chart type for a given dimension when the user hasn't picked one. */
export function defaultTypeFor(d: ChartDimension): CustomChartType {
  switch (d.kind) {
    case 'qa':       return 'histogram'
    case 'year':     return 'vbar'
    case 'venue':    return 'hbar'
    default:         return 'donut'
  }
}
