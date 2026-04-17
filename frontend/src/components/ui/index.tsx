/** Shared UI primitives: Card, StatBar, Modal, FormField, Badge, ConfirmDialog, etc. */
import { ReactNode } from 'react'

// ── Card ──────────────────────────────────────────────────────────────────────

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>
}

export function CardHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="section-title mb-0">{title}</h2>
      {action}
    </div>
  )
}

// ── StatCard — standalone card (legacy usage) ─────────────────────────────────

export function StatCard({
  label,
  value,
  sub,
  color = 'navy',
}: {
  label: ReactNode
  value: string | number
  sub?: string
  color?: 'navy' | 'include' | 'exclude' | 'uncertain' | 'info'
}) {
  const colorClass = {
    navy: 'text-ink',
    include: 'text-include',
    exclude: 'text-exclude',
    uncertain: 'text-uncertain',
    info: 'text-accent',
  }[color]

  return (
    <div className="card">
      <p className="stat-label">{label}</p>
      <p className={`stat-value mt-1.5 ${colorClass}`}>{value}</p>
      {sub && <p className="text-2xs text-ink-muted mt-1 leading-normal">{sub}</p>}
    </div>
  )
}

// ── StatBar + StatCell — horizontal stat strip (preferred) ────────────────────

export function StatBar({ children }: { children: ReactNode }) {
  return <div className="stat-bar">{children}</div>
}

export function StatCell({
  label,
  value,
  sub,
  color = 'navy',
}: {
  label: ReactNode
  value: string | number
  sub?: string
  color?: 'navy' | 'include' | 'exclude' | 'uncertain' | 'info'
}) {
  const colorClass = {
    navy: 'text-ink',
    include: 'text-include',
    exclude: 'text-exclude',
    uncertain: 'text-uncertain',
    info: 'text-accent',
  }[color]

  return (
    <div className="stat-cell">
      <p className="stat-label">{label}</p>
      <p className={`stat-value mt-1 ${colorClass}`}>{value}</p>
      {sub && <p className="text-2xs text-ink-muted mt-0.5 leading-normal">{sub}</p>}
    </div>
  )
}

// ── Badge ─────────────────────────────────────────────────────────────────────

type BadgeVariant = 'include' | 'exclude' | 'uncertain' | 'info' | 'neutral'

export function Badge({ label, variant = 'neutral' }: { label: string; variant?: BadgeVariant }) {
  const cls = {
    include: 'decision-I',
    exclude: 'decision-E',
    uncertain: 'decision-U',
    info: 'bg-accent-faint text-accent border border-accent/15',
    neutral: 'bg-rule/50 text-ink-muted border border-rule',
  }[variant]
  return <span className={`phase-badge ${cls}`}>{label}</span>
}

export function DecisionBadge({ decision }: { decision: string }) {
  const map: Record<string, { label: string; variant: BadgeVariant }> = {
    I: { label: 'Include', variant: 'include' },
    E: { label: 'Exclude', variant: 'exclude' },
    U: { label: 'Uncertain', variant: 'uncertain' },
  }
  const d = map[decision] ?? { label: decision, variant: 'neutral' }
  return <Badge label={d.label} variant={d.variant} />
}

// ── Modal ─────────────────────────────────────────────────────────────────────

export function Modal({
  title,
  onClose,
  onEnter,
  children,
  width = 'max-w-lg',
}: {
  title: string
  onClose: () => void
  onEnter?: () => void
  children: ReactNode
  width?: string
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && onEnter) { e.preventDefault(); onEnter() } }}
    >
      <div
        className="absolute inset-0 bg-ink/25 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div className={`relative bg-surface rounded-modal shadow-modal ${width} w-full mx-4 max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-rule">
          <h3 className="font-display font-semibold text-ink text-base">{title}</h3>
          <button
            onClick={onClose}
            className="text-ink-muted hover:text-ink transition-colors text-lg leading-none w-7 h-7 flex items-center justify-center rounded hover:bg-paper"
          >
            ×
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  )
}

// ── Form helpers ──────────────────────────────────────────────────────────────

export function FormField({
  label,
  children,
  hint,
  error,
  required,
}: {
  label: string
  children: ReactNode
  hint?: string
  error?: string
  required?: boolean
}) {
  return (
    <div className="mb-4">
      <label className="block text-2xs font-semibold text-ink-muted uppercase tracking-label mb-1.5">
        {label}
        {required && <span className="text-exclude normal-case font-normal ml-1">*</span>}
      </label>
      {children}
      {error && <p className="text-xs text-exclude mt-1">{error}</p>}
      {!error && hint && <p className="text-xs text-ink-muted mt-1">{hint}</p>}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

export function EmptyState({ icon, message, action }: { icon: string; message: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <span className="text-2xl mb-2.5 opacity-20">{icon}</span>
      <p className="text-sm text-ink-muted mb-4">{message}</p>
      {action}
    </div>
  )
}

// ── Criterion row — hover-reveal buttons ──────────────────────────────────────

export function CriterionRow({
  label,
  description,
  badge,
  onEdit,
  onDelete,
}: {
  label: string
  description: string
  badge?: string
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div className="group flex items-start gap-3 py-3 border-b border-rule last:border-0">
      <span className="shrink-0 text-2xs font-bold text-accent bg-accent-faint border border-accent/15 rounded-[3px] px-1.5 py-0.5 mt-0.5 font-mono">
        {label}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-ink">{description}</p>
        {badge && <span className="text-2xs text-ink-muted">{badge}</span>}
      </div>
      <div className="flex gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={onEdit} className="btn-ghost btn-sm">Edit</button>
        <button
          onClick={onDelete}
          className="btn-ghost btn-sm text-exclude hover:text-exclude hover:bg-red-50"
        >
          ×
        </button>
      </div>
    </div>
  )
}

// ── Confirm Dialog ────────────────────────────────────────────────────────────

export function ConfirmDialog({
  message,
  onConfirm,
  onCancel,
  confirmLabel = 'Delete',
}: {
  message: string
  onConfirm: () => void
  onCancel: () => void
  confirmLabel?: string
}) {
  return (
    <Modal title="Confirm" onClose={onCancel} onEnter={onConfirm}>
      <p className="text-sm text-ink mb-5">{message}</p>
      <div className="flex gap-2 justify-end">
        <button className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button className="btn-danger" onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </Modal>
  )
}

// ── Phase coming-soon ─────────────────────────────────────────────────────────

export function PhaseComingSoon({
  phase,
  icon,
  title,
  description,
  planned,
}: {
  phase: string
  icon: string
  title: string
  description: string
  planned: string[]
}) {
  return (
    <div className="max-w-2xl mx-auto mt-10">
      <div className="card text-center py-10">
        <span className="text-3xl opacity-30">{icon}</span>
        <h1 className="font-display text-lg font-semibold text-ink mt-4 mb-1">{title}</h1>
        <p className="text-2xs uppercase tracking-label text-ink-muted mb-2">{phase}</p>
        <p className="text-sm text-ink-light mb-7 max-w-md mx-auto">{description}</p>
        <div className="bg-paper rounded-[3px] p-4 text-left inline-block min-w-[280px]">
          <p className="section-title mb-2.5">Planned features</p>
          <ul className="space-y-1.5">
            {planned.map(item => (
              <li key={item} className="text-xs text-ink-light flex items-start gap-2">
                <span className="text-accent/30 mt-0.5">—</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
