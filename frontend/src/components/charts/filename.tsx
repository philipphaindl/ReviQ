/**
 * Project-scoped chart-export filename plumbing.
 *
 * Every chart panel calls `useChartFilename('research-types')` and gets back
 * `reviq-{project-slug}-research-types-{YYYYMMDD}` — the same string used for
 * the PNG and PDF downloads (by the PanelMenu) and the CSV download (by the
 * panel-local `withCsv` helper). One context, one source of truth.
 */
import { createContext, useContext, useMemo, type ReactNode } from 'react'

import { chartFilename } from '../../utils/charts'

interface ChartFilenameCtx {
  projectTitle: string
  /** Stable Date so all downloads from the same page session share a date. */
  date: Date
}

const Ctx = createContext<ChartFilenameCtx | null>(null)

export function ChartFilenameProvider({
  projectTitle, children,
}: { projectTitle: string; children: ReactNode }) {
  // The Date is captured once per provider mount; navigating between
  // projects produces a fresh provider and a fresh stamp.
  const value = useMemo<ChartFilenameCtx>(
    () => ({ projectTitle, date: new Date() }),
    [projectTitle],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

/** Returns the canonical filename stem for a given chart-id, no extension. */
export function useChartFilename(chartId: string): string {
  const ctx = useContext(Ctx)
  if (!ctx) return chartFilename('project', chartId)
  return chartFilename(ctx.projectTitle, chartId, ctx.date)
}
