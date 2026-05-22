/**
 * Top-right ⋯ action menu for every chart panel.
 *
 * Wraps a small icon button that toggles a dropdown of actions. The standard
 * set is CSV / PNG / PDF — the panel passes the CSV builder; PNG and PDF are
 * synthesised here against the panel's body ref.
 *
 * Custom user-added panels also expose a destructive "Remove from dashboard"
 * action at the bottom of the menu.
 */
import { useEffect, useRef, useState, type RefObject } from 'react'

import { exportPanelAsPdf, exportPanelAsPng } from './exportUtils'
import { COLORS, SANS } from './tokens'

export type PanelMenuAction =
  | { kind: 'csv';    onSelect: () => void }
  | { kind: 'png' }
  | { kind: 'pdf';    caption?: string }
  | { kind: 'remove'; onSelect: () => void }
  | { kind: 'divider' }
  | { kind: 'custom'; label: string; onSelect: () => void; destructive?: boolean }

interface Props {
  actions: PanelMenuAction[]
  bodyRef: RefObject<HTMLElement>
  exportName: string
}

const ITEM_LABEL: Record<string, string> = {
  csv: 'Download CSV',
  png: 'Download PNG',
  pdf: 'Download as vector (SVG)',
  remove: 'Remove panel',
}

export function PanelMenu({ actions, bodyRef, exportName }: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  async function handle(action: PanelMenuAction) {
    setOpen(false)
    const node = bodyRef.current as HTMLElement | null
    if (action.kind === 'csv')    { action.onSelect(); return }
    if (action.kind === 'remove') { action.onSelect(); return }
    if (action.kind === 'custom') { action.onSelect(); return }
    if (!node) return
    try {
      setBusy(action.kind)
      if (action.kind === 'png') await exportPanelAsPng(node, { filename: exportName })
      if (action.kind === 'pdf') await exportPanelAsPdf(node, { filename: exportName, caption: action.caption })
    } catch (err) {
      console.error('[chart export]', err)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label="Panel actions"
        onClick={() => setOpen(o => !o)}
        className="w-7 h-7 inline-flex items-center justify-center rounded-[4px] border border-rule
                   text-ink-muted hover:text-ink hover:border-ink/40 transition-colors bg-surface"
        style={{ fontFamily: SANS }}
      >
        {/* Three horizontal dots — single SVG keeps it crisp in exports. */}
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <circle cx="2.5" cy="7" r="1.2" fill="currentColor" />
          <circle cx="7"   cy="7" r="1.2" fill="currentColor" />
          <circle cx="11.5" cy="7" r="1.2" fill="currentColor" />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-1.5 min-w-[180px] py-1 rounded-[4px]
                     border border-rule bg-surface z-20
                     shadow-[0_8px_24px_rgba(0,0,0,0.08)]"
          style={{ fontFamily: SANS }}
        >
          {actions.map((a, i) => {
            if (a.kind === 'divider') {
              return <div key={`div-${i}`} className="my-1 border-t border-rule" />
            }
            const isCustom = a.kind === 'custom'
            const destructive = a.kind === 'remove' || (isCustom && a.destructive)
            const label = isCustom ? a.label : ITEM_LABEL[a.kind]
            return (
              <button
                key={`${a.kind}-${i}`}
                role="menuitem"
                onClick={() => handle(a)}
                disabled={busy !== null}
                className={`w-full text-left px-3 py-1.5 text-[12px] flex items-center gap-2
                  ${destructive ? 'text-exclude hover:bg-exclude/5' : 'text-ink hover:bg-paper'}
                  ${busy === a.kind ? 'opacity-50' : ''}`}
              >
                <span className="inline-block w-3 text-ink-muted">
                  <Glyph kind={a.kind} />
                </span>
                {busy === a.kind ? 'Working…' : label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function Glyph({ kind }: { kind: PanelMenuAction['kind'] }) {
  const color = COLORS.inkMuted
  switch (kind) {
    case 'csv':
      return (
        <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
          <rect x="1" y="1" width="10" height="10" rx="1.5" fill="none" stroke={color} />
          <path d="M3 6h6M3 8.5h6M3 3.5h6" stroke={color} strokeWidth="0.8" />
        </svg>
      )
    case 'png':
      return (
        <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
          <rect x="1" y="1.5" width="10" height="9" rx="1.5" fill="none" stroke={color} />
          <circle cx="4" cy="5" r="0.9" fill={color} />
          <path d="M2 9.5l2.5-2.5L6 8.5l2-1.5 2 2.5" stroke={color} strokeWidth="0.7" fill="none" />
        </svg>
      )
    case 'pdf':
      return (
        <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M3 1.5h4.5L9.5 3.5V10.5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V2.5a1 1 0 0 1 1-1z"
                fill="none" stroke={color} />
          <text x="3" y="9" fontSize="3.5" fill={color} fontFamily="monospace">pdf</text>
        </svg>
      )
    case 'remove':
      return (
        <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true">
          <path d="M3 4h6M5 6v3M7 6v3M3 4l.5 6.5h5L9 4M5 4V2.5h2V4"
                stroke="currentColor" fill="none" strokeWidth="0.8" />
        </svg>
      )
    default:
      return null
  }
}
