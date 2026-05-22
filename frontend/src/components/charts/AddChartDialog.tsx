/**
 * Modal that lets the user add a new chart panel to the dashboard.
 *
 * The dialog is data-driven: it derives the list of available dimensions from
 * the loaded project (taxonomy types, dropdown extraction fields) so a user
 * who has set up a "research method" taxonomy automatically gets that as a
 * possible dimension without us having to hard-code anything.
 */
import { useMemo, useState } from 'react'

import { Modal } from '../ui'
import {
  type ChartConfig, type ChartDimension, type CustomChartType,
  defaultTypeFor, dimensionLabel,
} from './customCharts'

interface DimensionOption {
  /** Stable id for the radio (e.g. "taxonomy:contribution_type"). */
  id: string
  label: string
  dimension: ChartDimension
}

interface Props {
  open: boolean
  onClose: () => void
  onAdd: (cfg: Omit<ChartConfig, 'id'>) => void
  /** Available taxonomy_type keys from the project. */
  taxonomyKeys: string[]
  /** Available dropdown extraction fields (excluding taxonomy duplicates). */
  extractionFields: Array<{ field_name: string; field_label: string }>
}

const TYPE_OPTIONS: Array<{ value: CustomChartType; label: string; sub: string }> = [
  { value: 'vbar',      label: 'Vertical bars',   sub: 'Categorical counts (e.g. year)' },
  { value: 'hbar',      label: 'Horizontal bars', sub: 'Long category names; ranked' },
  { value: 'donut',     label: 'Donut',           sub: 'Share of total — best ≤ 7 cats' },
  { value: 'histogram', label: 'Histogram',       sub: 'QA percentage only' },
]

export function AddChartDialog({
  open, onClose, onAdd, taxonomyKeys, extractionFields,
}: Props) {
  const dimensions = useMemo<DimensionOption[]>(() => {
    const out: DimensionOption[] = [
      { id: 'year',    label: 'Publications per year', dimension: { kind: 'year' } },
      { id: 'qa',      label: 'QA percentage',         dimension: { kind: 'qa' } },
      { id: 'pubtype', label: 'Publication type',      dimension: { kind: 'pubtype' } },
      { id: 'venue',   label: 'Publication venues',    dimension: { kind: 'venue' } },
    ]
    for (const key of taxonomyKeys) {
      out.push({
        id: `taxonomy:${key}`,
        label: `Taxonomy — ${humanize(key)}`,
        dimension: { kind: 'taxonomy', key },
      })
    }
    for (const f of extractionFields) {
      out.push({
        id: `extraction:${f.field_name}`,
        label: `Extraction — ${f.field_label}`,
        dimension: { kind: 'extraction', field: f.field_name },
      })
    }
    return out
  }, [taxonomyKeys, extractionFields])

  const [dimensionId, setDimensionId] = useState<string>(dimensions[0]?.id ?? 'year')
  const [chartType, setChartType] = useState<CustomChartType>('donut')
  const [title, setTitle] = useState('')
  const [bins, setBins] = useState(10)

  const selected = dimensions.find(d => d.id === dimensionId) ?? dimensions[0]

  // Histogram is only meaningful for QA percentage; auto-disable elsewhere.
  const histogramOk = selected?.dimension.kind === 'qa'
  const effectiveType = !histogramOk && chartType === 'histogram'
    ? defaultTypeFor(selected.dimension)
    : chartType

  if (!open) return null

  const handleAdd = () => {
    if (!selected) return
    onAdd({
      type: effectiveType,
      dimension: selected.dimension,
      title: title.trim() || undefined,
      bins: effectiveType === 'histogram' ? bins : undefined,
    })
    setTitle('')
    onClose()
  }

  return (
    <Modal title="Add chart panel" onClose={onClose} onEnter={handleAdd} width="max-w-2xl">
      <div className="space-y-5">
        <FieldGroup label="Data dimension"
          hint="Pick what the chart should be about. The list reflects your project's taxonomy and extraction schema.">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-72 overflow-y-auto pr-1">
            {dimensions.map(d => (
              <RadioOption key={d.id}
                checked={dimensionId === d.id}
                onChange={() => setDimensionId(d.id)}
                label={d.label}
                value={d.id}
                name="dimension"
              />
            ))}
          </div>
        </FieldGroup>

        <FieldGroup label="Chart type">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
            {TYPE_OPTIONS.map(t => {
              const disabled = t.value === 'histogram' && !histogramOk
              const isSelected = effectiveType === t.value && !disabled
              return (
                <button
                  type="button"
                  key={t.value}
                  disabled={disabled}
                  onClick={() => setChartType(t.value)}
                  className={`text-left rounded-[4px] border px-3 py-2.5 transition-colors
                    ${isSelected
                      ? 'border-accent bg-accent/5 text-ink'
                      : disabled
                        ? 'border-rule/60 text-ink-muted/60 cursor-not-allowed'
                        : 'border-rule text-ink-light hover:border-ink/30 hover:text-ink'
                    }`}
                >
                  <div className="text-[13px] font-semibold">{t.label}</div>
                  <div className="text-[11px] mt-0.5 opacity-80">{t.sub}</div>
                </button>
              )
            })}
          </div>
        </FieldGroup>

        {effectiveType === 'histogram' && (
          <FieldGroup label="Bin count">
            <input
              type="number" min={2} max={50}
              value={bins}
              onChange={e => setBins(Math.min(50, Math.max(2, Number(e.target.value) || 10)))}
              className="w-24 border border-rule rounded-[4px] px-3 py-1.5 text-[13px]
                         focus:outline-none focus:border-accent"
            />
          </FieldGroup>
        )}

        <FieldGroup label="Title (optional)"
          hint="Leave blank to use the dimension's default title.">
          <input
            type="text"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder={selected ? dimensionLabel(selected.dimension) : ''}
            className="w-full border border-rule rounded-[4px] px-3 py-1.5 text-[13px]
                       focus:outline-none focus:border-accent"
          />
        </FieldGroup>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button onClick={handleAdd} className="btn-primary">Add to dashboard</button>
        </div>
      </div>
    </Modal>
  )
}

function FieldGroup({
  label, hint, children,
}: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase text-ink-muted mb-2"
         style={{ letterSpacing: '0.1em' }}>{label}</p>
      {children}
      {hint && <p className="text-[11px] text-ink-muted mt-1.5">{hint}</p>}
    </div>
  )
}

function RadioOption({
  checked, onChange, label, value, name,
}: { checked: boolean; onChange: () => void; label: string; value: string; name: string }) {
  return (
    <label className={`flex items-center gap-2 px-2.5 py-1.5 rounded-[4px] border text-[12px] cursor-pointer
      ${checked
        ? 'border-accent bg-accent/5 text-ink'
        : 'border-rule text-ink-light hover:border-ink/30 hover:text-ink'}`}>
      <input
        type="radio"
        className="accent-accent"
        name={name}
        value={value}
        checked={checked}
        onChange={onChange}
      />
      <span className="truncate">{label}</span>
    </label>
  )
}

function humanize(snake: string) {
  return snake.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
