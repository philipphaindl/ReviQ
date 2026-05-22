/**
 * Reusable Recharts tooltip body. Same surface, same border, same typography
 * everywhere — uniform hover behavior is one of the few constants you can rely
 * on to anchor a multi-chart dashboard visually.
 */
import type { ReactNode } from 'react'

import { NUMERIC, SANS, TOOLTIP_CLASS } from './tokens'

interface Props {
  title: ReactNode
  rows?: Array<{ label: string; value: ReactNode; muted?: boolean }>
  /** Free-form children rendered below the rows (e.g. paper-key list). */
  children?: ReactNode
}

export function ChartTooltip({ title, rows, children }: Props) {
  return (
    <div className={TOOLTIP_CLASS} role="tooltip" style={{ fontFamily: SANS, ...NUMERIC }}>
      <div className="text-ink font-semibold leading-snug">{title}</div>
      {rows && rows.length > 0 && (
        <div className="mt-1 space-y-0.5">
          {rows.map(r => (
            <div key={r.label} className="flex justify-between gap-3">
              <span className={`text-[10px] uppercase ${r.muted ? 'text-ink-muted' : 'text-ink-light'}`}
                    style={{ letterSpacing: '0.08em' }}>
                {r.label}
              </span>
              <span className="text-ink-light">{r.value}</span>
            </div>
          ))}
        </div>
      )}
      {children}
    </div>
  )
}
