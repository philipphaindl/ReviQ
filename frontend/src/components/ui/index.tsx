import { ReactNode, useState } from 'react'

// ── Card ──────────────────────────────────────────────────────────────────────

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`}>{children}</div>
}

export function CardHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-4">
      <h2 className="section-title">{title}</h2>
      {action}
    </div>
  )
}

// ── StatCard ──────────────────────────────────────────────────────────────────

export function StatCard({
  label,
  value,
  sub,
  color = 'navy',
}: {
  label: string
  value: string | number
  sub?: string
  color?: 'navy' | 'include' | 'exclude' | 'uncertain' | 'info'
}) {
  const colorClass = {
    navy: 'text-navy',
    include: 'text-include',
    exclude: 'text-exclude',
    uncertain: 'text-uncertain',
    info: 'text-info',
  }[color]

  return (
    <div className="card">
      <p className="stat-label">{label}</p>
      <p className={`stat-value mt-1 ${colorClass}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
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
    info: 'bg-blue-50 text-info border border-blue-200',
    neutral: 'bg-gray-100 text-gray-600 border border-gray-200',
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
        className="absolute inset-0 bg-black/30 backdrop-blur-[1px]"
        onClick={onClose}
      />
      <div className={`relative bg-white rounded-card shadow-xl ${width} w-full mx-4 max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <h3 className="font-semibold text-navy text-sm">{title}</h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-navy transition-colors text-lg leading-none"
          >
            ×
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
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
      <label className="block text-xs font-semibold text-navy-muted uppercase tracking-wider mb-1.5">
        {label}
        {required && <span className="text-exclude normal-case font-normal ml-1">*</span>}
      </label>
      {children}
      {error && <p className="text-xs text-exclude mt-1">{error}</p>}
      {!error && hint && <p className="text-xs text-gray-400 mt-1">{hint}</p>}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

export function EmptyState({ icon, message, action }: { icon: string; message: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <span className="text-4xl mb-3">{icon}</span>
      <p className="text-sm text-gray-500 mb-4">{message}</p>
      {action}
    </div>
  )
}

// ── Inline editable row ───────────────────────────────────────────────────────

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
    <div className="flex items-start gap-3 py-3 border-b border-border last:border-0">
      <span className="shrink-0 text-xs font-bold text-info bg-blue-50 border border-blue-200 rounded px-2 py-0.5 mt-0.5">
        {label}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-navy">{description}</p>
        {badge && <span className="text-xs text-gray-400">{badge}</span>}
      </div>
      <div className="flex gap-1 shrink-0">
        <button onClick={onEdit} className="btn-secondary text-xs px-2 py-1">Edit</button>
        <button onClick={onDelete} className="btn-danger text-xs px-2 py-1">×</button>
      </div>
    </div>
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
    <div className="max-w-2xl mx-auto mt-8">
      <div className="card text-center py-10">
        <span className="text-5xl">{icon}</span>
        <h1 className="text-xl font-bold text-navy mt-4 mb-1">{title}</h1>
        <p className="text-sm text-gray-500 mb-2">{phase}</p>
        <p className="text-sm text-gray-600 mb-6">{description}</p>
        <div className="bg-card rounded-md p-4 text-left inline-block min-w-[280px]">
          <p className="section-title mb-2">Planned features</p>
          <ul className="space-y-1">
            {planned.map(item => (
              <li key={item} className="text-xs text-gray-600 flex items-start gap-2">
                <span className="text-gray-300 mt-0.5">—</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
