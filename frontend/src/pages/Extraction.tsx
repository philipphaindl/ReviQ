/**
 * Data Extraction (Phase 7) — Schema definition, per-paper data entry, and tabular overview.
 * Fields are user-defined (text/number/boolean/dropdown) and ordered via sort_order.
 * Taxonomy categories from Setup are shown as a separate section in the extraction modal.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useProject } from '../App'
import {
  getExtractionFields, createExtractionField, updateExtractionField,
  deleteExtractionField, getExtractionSummary, upsertExtractionRecord,
  getReviewers, getTaxonomyTypes, getTaxonomy,
} from '../api/client'
import {
  Card, CardHeader, StatBar, StatCell, Modal, FormField, EmptyState,
} from '../components/ui'
import type { ExtractionField, ExtractionPaperRow } from '../api/types'
import { formatAuthors } from '../utils'

type ExtView = 'schema' | 'extract' | 'table'

const FIELD_TYPES = [
  { value: 'text',     label: 'Text'     },
  { value: 'number',   label: 'Number'   },
  { value: 'boolean',  label: 'Yes / No' },
  { value: 'dropdown', label: 'Dropdown' },
]

const TYPE_COLORS: Record<string, string> = {
  text:     'bg-blue-50 text-blue-700 border-blue-200',
  number:   'bg-purple-50 text-purple-700 border-purple-200',
  boolean:  'bg-green-50 text-green-700 border-green-200',
  dropdown: 'bg-amber-50 text-amber-700 border-amber-200',
}

// Derive a stable field_name from the display label: lowercase, non-alphanumerics → underscores,
// trimmed, max 50 chars. This becomes the database key so it must be slug-safe.
const slugify = (label: string) =>
  label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/, '').slice(0, 50)

export default function Extraction() {
  const { projectId } = useProject()
  const [view, setView] = useState<ExtView>('schema')

  if (!projectId) {
    return <EmptyState icon="—" message="No active project. Select one from the Overview." />
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-ink font-display">Data Extraction</h1>
        <p className="text-sm text-ink-muted">Phase 7 — Structured Data Extraction</p>
      </div>

      <div className="flex gap-0 border-b border-rule">
        {(['schema', 'extract', 'table'] as ExtView[]).map(v => (
          <button key={v} onClick={() => setView(v)}
            className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-label transition-colors relative capitalize ${
              view === v
                ? 'text-info after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-info'
                : 'text-ink-muted hover:text-ink'
            }`}>
            {v === 'schema' ? 'Field Schema' : v === 'extract' ? 'Extract' : 'Table View'}
          </button>
        ))}
      </div>

      {view === 'schema'  && <SchemaView pid={projectId} />}
      {view === 'extract' && <ExtractView pid={projectId} />}
      {view === 'table'   && <TableView pid={projectId} />}
    </div>
  )
}

// ── Schema View ───────────────────────────────────────────────────────────────

type FieldForm = {
  field_name: string
  field_label: string
  field_type: string
  options: string   // comma-separated for display; converted to JSON on save
}

const EMPTY_FORM: FieldForm = {
  field_name: '',
  field_label: '',
  field_type: 'text',
  options: '',
}

function SchemaView({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const [modal, setModal] = useState<{ mode: 'add' | 'edit'; field?: ExtractionField } | null>(null)
  const [form, setForm] = useState<FieldForm>(EMPTY_FORM)
  const [submitted, setSubmitted] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<ExtractionField | null>(null)
  const [moving, setMoving] = useState(false)

  const { data: allFields = [] } = useQuery({
    queryKey: ['extraction-fields', pid],
    queryFn: () => getExtractionFields(pid),
  })

  // Taxonomy types — always fetched so we can filter them out of the schema list
  const { data: taxonomyTypes = [] } = useQuery({
    queryKey: ['taxonomy-types', pid],
    queryFn: () => getTaxonomyTypes(pid),
  })

  // Hide fields that duplicate taxonomy categories — those are shown automatically
  // in the extraction dialog's Taxonomies section
  const taxonomySet = new Set(taxonomyTypes)
  const fields = allFields.filter(f => !taxonomySet.has(f.field_name))

  const optionsToJson = (raw: string) =>
    JSON.stringify(raw.split(',').map(s => s.trim()).filter(Boolean))

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['extraction-fields', pid] })
    qc.invalidateQueries({ queryKey: ['extraction-summary', pid] })
  }

  const createMut = useMutation({
    mutationFn: (data: FieldForm) => createExtractionField(pid, {
      field_name: data.field_name,
      field_label: data.field_label,
      field_type: data.field_type,
      options: data.field_type === 'dropdown' ? optionsToJson(data.options) : undefined,
      sort_order: fields.length,
    }),
    onSuccess: () => { invalidateAll(); close() },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<FieldForm> & { sort_order?: number } }) =>
      updateExtractionField(pid, id, {
        field_label: data.field_label,
        field_type: data.field_type,
        options: data.field_type === 'dropdown' ? optionsToJson(data.options ?? '') : undefined,
        sort_order: data.sort_order,
      }),
    onSuccess: () => { invalidateAll(); close() },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteExtractionField(pid, id),
    onSuccess: () => { invalidateAll(); setDeleteTarget(null) },
  })

  const openAdd = () => {
    setForm(EMPTY_FORM)
    setSubmitted(false)
    setModal({ mode: 'add' })
  }

  const openEdit = (f: ExtractionField) => {
    const optionsDisplay = f.options
      ? (() => { try { return (JSON.parse(f.options) as string[]).join(', ') } catch { return f.options } })()
      : ''
    setForm({ field_name: f.field_name, field_label: f.field_label, field_type: f.field_type, options: optionsDisplay })
    setSubmitted(false)
    setModal({ mode: 'edit', field: f })
  }

  const close = () => { setModal(null); setSubmitted(false) }

  const submit = () => {
    setSubmitted(true)
    if (!form.field_label.trim()) return
    if (form.field_type === 'dropdown' && !form.options.trim()) return
    if (modal?.mode === 'add') {
      const name = slugify(form.field_label) || `field_${fields.length + 1}`
      createMut.mutate({ ...form, field_name: name })
    } else if (modal?.field) {
      updateMut.mutate({ id: modal.field.id, data: form })
    }
  }

  // Reorder by swapping sort_order values between the moved field and its neighbor.
  // Both updates fire in parallel since they touch different rows.
  const moveField = async (idx: number, dir: 'up' | 'down') => {
    if (moving) return
    const target = dir === 'up' ? idx - 1 : idx + 1
    if (target < 0 || target >= fields.length) return
    setMoving(true)
    try {
      await Promise.all([
        updateExtractionField(pid, fields[idx].id, { sort_order: target }),
        updateExtractionField(pid, fields[target].id, { sort_order: idx }),
      ])
      invalidateAll()
    } finally {
      setMoving(false)
    }
  }

  const isPending = createMut.isPending || updateMut.isPending

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title={`Extraction Fields${fields.length > 0 ? ` — ${fields.length} field${fields.length !== 1 ? 's' : ''}` : ''}`}
          action={<button className="btn-secondary" onClick={openAdd}>+ Add Field</button>}
        />

        {fields.length === 0 ? (
          <EmptyState icon="—" message="No extraction fields defined. Add fields to start extracting data." />
        ) : (
          fields.map((f, idx) => (
            <div key={f.id} className="py-2.5 border-b border-rule last:border-0 flex items-center gap-3">
              {/* Up/Down reorder */}
              <div className="flex flex-col gap-0.5 shrink-0">
                <button
                  className="text-ink-muted/40 hover:text-ink-muted leading-none px-0.5 disabled:opacity-20"
                  onClick={() => moveField(idx, 'up')} disabled={idx === 0 || moving}
                  title="Move up">▲</button>
                <button
                  className="text-ink-muted/40 hover:text-ink-muted leading-none px-0.5 disabled:opacity-20"
                  onClick={() => moveField(idx, 'down')} disabled={idx === fields.length - 1 || moving}
                  title="Move down">▼</button>
              </div>
              {/* Type badge — uniform width */}
              <span className={`text-xs font-bold rounded px-2 py-0.5 border shrink-0 w-[72px] text-center ${TYPE_COLORS[f.field_type] ?? TYPE_COLORS.text}`}>
                {FIELD_TYPES.find(t => t.value === f.field_type)?.label ?? f.field_type}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-ink leading-snug">{f.field_label}</p>
                {f.field_type === 'dropdown' && f.options && (
                  <p className="text-xs text-ink-muted mt-0.5 truncate">
                    {(() => { try { return (JSON.parse(f.options) as string[]).join(' · ') } catch { return f.options } })()}
                  </p>
                )}
              </div>
              <div className="flex gap-1 shrink-0">
                <button className="btn-secondary" onClick={() => openEdit(f)}>Edit</button>
                <button className="btn-danger" onClick={() => setDeleteTarget(f)}>Remove</button>
              </div>
            </div>
          ))
        )}
      </Card>

      {/* Add / Edit modal */}
      {modal && (
        <Modal
          title={modal.mode === 'add' ? 'Add Extraction Field' : 'Edit Extraction Field'}
          onClose={close}
          onEnter={submit}
        >
          <FormField label="Display Label" required
            error={submitted && !form.field_label.trim() ? 'Label is required' : undefined}>
            <input
              className={`input ${submitted && !form.field_label.trim() ? 'border-exclude ring-1 ring-exclude' : ''}`}
              placeholder="Research Type"
              value={form.field_label}
              autoFocus
              onChange={e => setForm(f => ({ ...f, field_label: e.target.value }))}
            />
          </FormField>
          <FormField label="Field Type">
            <select className="input" value={form.field_type}
              onChange={e => setForm(f => ({ ...f, field_type: e.target.value, options: '' }))}>
              {FIELD_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </FormField>
          {form.field_type === 'dropdown' && (
            <>
              {/* Load from taxonomy shortcut */}
              {taxonomyTypes.length > 0 && (
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-ink-muted">Load from taxonomy:</span>
                  <div className="flex gap-1 flex-wrap">
                    {taxonomyTypes.map(type => (
                      <TaxonomyLoader key={type} pid={pid} type={type} onLoad={vals =>
                        setForm(f => ({ ...f, options: vals.join(', ') }))
                      } />
                    ))}
                  </div>
                </div>
              )}
              <FormField label="Options (comma-separated)" required
                error={submitted && form.field_type === 'dropdown' && !form.options.trim() ? 'At least one option required' : undefined}
                hint='E.g. "Qualitative, Quantitative, Mixed"'>
                <input
                  className={`input ${submitted && form.field_type === 'dropdown' && !form.options.trim() ? 'border-exclude ring-1 ring-exclude' : ''}`}
                  placeholder="Qualitative, Quantitative, Mixed"
                  value={form.options}
                  onChange={e => setForm(f => ({ ...f, options: e.target.value }))}
                />
              </FormField>
            </>
          )}
          <div className="flex gap-2 mt-2">
            <button className="btn-secondary flex-1 justify-center" onClick={close}>Cancel</button>
            <button className="btn-primary flex-1 justify-center" onClick={submit} disabled={isPending}>
              {isPending ? 'Saving…' : modal.mode === 'add' ? 'Add Field' : 'Save Changes'}
            </button>
          </div>
          {(createMut.isError || updateMut.isError) && (
            <p className="text-xs text-red-500 mt-2">
              {(createMut.error as any)?.response?.data?.detail ?? 'Could not save field.'}
            </p>
          )}
        </Modal>
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <Modal title="Remove Field" onClose={() => setDeleteTarget(null)}>
          <p className="text-sm text-ink mb-4">
            Remove field <span className="font-semibold text-ink">"{deleteTarget.field_label}"</span>? All extracted values for this field will be permanently deleted.
          </p>
          <div className="flex gap-2">
            <button className="btn-secondary flex-1 justify-center" onClick={() => setDeleteTarget(null)}>Cancel</button>
            <button className="btn-danger flex-1 justify-center" onClick={() => deleteMut.mutate(deleteTarget.id)}
              disabled={deleteMut.isPending}>
              {deleteMut.isPending ? 'Removing…' : 'Remove Field'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function TaxonomyLoader({ pid, type, onLoad }: { pid: number; type: string; onLoad: (vals: string[]) => void }) {
  const { data: entries } = useQuery({
    queryKey: ['taxonomy', pid, type],
    queryFn: () => getTaxonomy(pid, type),
  })
  const label = type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  return (
    <button
      type="button"
      className="text-xs px-2 py-0.5 rounded border border-info text-info hover:bg-blue-50 transition-colors"
      onClick={() => entries && onLoad(entries.map(e => e.value))}
    >
      {label}
    </button>
  )
}

// ── Extract View ──────────────────────────────────────────────────────────────

function ExtractView({ pid }: { pid: number }) {
  const [selectedPaper, setSelectedPaper] = useState<ExtractionPaperRow | null>(null)

  const { data: summary, isLoading } = useQuery({
    queryKey: ['extraction-summary', pid],
    queryFn: () => getExtractionSummary(pid),
  })

  // Pre-fetch taxonomy data here so it's ready when the modal opens
  const { data: taxonomyTypes = [] } = useQuery({
    queryKey: ['taxonomy-types', pid],
    queryFn: () => getTaxonomyTypes(pid),
  })
  const { data: taxonomyOptions = {} } = useQuery<Record<string, string[]>>({
    queryKey: ['all-taxonomy-entries', pid, taxonomyTypes.join(',')],
    queryFn: async () => {
      const pairs = await Promise.all(
        taxonomyTypes.map(type =>
          getTaxonomy(pid, type).then(entries => [type, entries.map(e => e.value)] as const)
        )
      )
      return Object.fromEntries(pairs)
    },
    enabled: taxonomyTypes.length > 0,
  })

  if (isLoading) return <p className="text-sm text-ink-muted">Loading…</p>
  if (!summary) return null

  if (summary.papers.length === 0) {
    return <EmptyState icon="—" message="No included papers yet. Complete Full-Text Eligibility (Phase 4) first." />
  }

  const hasTaxonomies = taxonomyTypes.length > 0
  const hasFields = summary.fields.length > 0
  const done = summary.papers.filter(p => p.filled === p.total_fields && p.total_fields > 0).length

  return (
    <div className="space-y-4">
      {!hasTaxonomies && !hasFields && (
        <div className="bg-amber-50 border border-amber-200 rounded-md px-4 py-2.5 text-sm text-amber-800">
          No taxonomies or extraction fields configured yet. Add taxonomies in Setup → Taxonomy and/or fields in the Field Schema tab.
        </div>
      )}
      <StatBar>
        <StatCell label="Included Papers" value={summary.papers.length} sub="Phase 4 (Full-Text Eligibility)" />
        {hasFields && <StatCell label="Fields Extracted" value={done} color="include" />}
        {hasTaxonomies && <StatCell label="Taxonomy Types" value={taxonomyTypes.length} color="info" />}
      </StatBar>

      <div className="space-y-2">
        {summary.papers.map(paper => (
          <ExtractionPaperCard key={paper.paper_id} paper={paper} onExtract={() => setSelectedPaper(paper)} />
        ))}
      </div>

      {selectedPaper && (
        <ExtractionModal
          paper={selectedPaper}
          fields={summary.fields.filter(f => !taxonomyTypes.includes(f.field_name))}
          pid={pid}
          taxonomyTypes={taxonomyTypes}
          taxonomyOptions={taxonomyOptions}
          onClose={() => setSelectedPaper(null)}
        />
      )}
    </div>
  )
}

function ExtractionPaperCard({ paper, onExtract }: { paper: ExtractionPaperRow; onExtract: () => void }) {
  const pct = paper.total_fields > 0 ? Math.round((paper.filled / paper.total_fields) * 100) : 0
  const done = paper.filled === paper.total_fields
  const accentClass = done ? 'left-accent-include' : paper.filled > 0 ? 'left-accent-uncertain' : 'left-accent-info'

  return (
    <div className={`card pl-4 ${accentClass} cursor-pointer hover:shadow-card-hover transition-shadow`} onClick={onExtract}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs font-bold px-2 py-0.5 rounded border ${
            done ? 'bg-green-100 text-green-800 border-green-200' :
            paper.filled > 0 ? 'bg-amber-100 text-amber-800 border-amber-200' :
            'bg-rule/30 text-ink-light border-rule'
          }`}>
            {done ? 'Complete' : `${paper.filled}/${paper.total_fields} filled`}
          </span>
          {paper.total_fields > 0 && !done && (
            <div className="flex-1 max-w-[120px] bg-rule rounded-full h-1.5">
              <div className="bg-info h-1.5 rounded-full transition-all" style={{ width: `${pct}%` }} />
            </div>
          )}
          <span className="text-xs text-ink-muted ml-auto">{paper.source} · {paper.year}</span>
        </div>
        <h3 className="text-sm font-medium text-ink mt-1 leading-snug">{paper.title}</h3>
        {paper.authors && <p className="text-xs text-ink-muted mt-0.5">{formatAuthors(paper.authors)}</p>}
      </div>
    </div>
  )
}

function ExtractionModal({ paper, fields, pid, taxonomyTypes, taxonomyOptions, onClose }: {
  paper: ExtractionPaperRow
  fields: ExtractionField[]
  pid: number
  taxonomyTypes: string[]
  taxonomyOptions: Record<string, string[]>
  onClose: () => void
}) {
  const qc = useQueryClient()
  const { reviewerId } = useProject()

  const { data: reviewers = [] } = useQuery({
    queryKey: ['reviewers', pid],
    queryFn: () => getReviewers(pid),
  })

  const activeReviewerId = reviewerId ?? reviewers.find(r => r.role === 'R1')?.id ?? reviewers[0]?.id

  // Initialize values for both taxonomy types and extraction fields from stored data
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    for (const type of taxonomyTypes) init[type] = paper.values[type] ?? ''
    for (const f of fields) init[f.field_name] = paper.values[f.field_name] ?? ''
    return init
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleChange = (key: string, value: string) => {
    setValues(prev => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  const handleSave = async () => {
    if (!activeReviewerId) return
    setSaving(true)
    setSaved(false)
    try {
      // Save taxonomy selections (keyed by taxonomy type name)
      for (const type of taxonomyTypes) {
        await upsertExtractionRecord(pid, paper.paper_id, {
          reviewer_id: activeReviewerId,
          field_name: type,
          field_value: values[type] || undefined,
        })
      }
      // Save extraction field values
      for (const f of fields) {
        await upsertExtractionRecord(pid, paper.paper_id, {
          reviewer_id: activeReviewerId,
          field_name: f.field_name,
          field_value: values[f.field_name] || undefined,
        })
      }
      qc.invalidateQueries({ queryKey: ['extraction-summary', pid] })
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  const toLabel = (type: string) =>
    type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

  return (
    <Modal title="Data Extraction" onClose={onClose} width="max-w-2xl">
      <div className="bg-paper rounded-md p-4 mb-4 border border-rule">
        <p className="text-sm font-semibold text-ink mb-1">{paper.title}</p>
        <p className="text-xs text-ink-muted">{formatAuthors(paper.authors)} · {paper.year}</p>
      </div>

      <div className="space-y-3 mb-4">
        {/* ── Taxonomies section ── */}
        {taxonomyTypes.length > 0 && (
          <>
            <p className="section-title mb-1 pt-1">Taxonomies</p>
            {taxonomyTypes.map(type => {
              const options = taxonomyOptions[type] ?? []
              return (
                <div key={type} className="border border-rule bg-paper rounded-md p-3">
                  <p className="text-xs font-semibold text-ink-muted uppercase tracking-label mb-2">{toLabel(type)}</p>
                  {options.length > 0 ? (
                    <select className="input" value={values[type] ?? ''} onChange={e => handleChange(type, e.target.value)}>
                      <option value="">— Select —</option>
                      {options.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <p className="text-xs text-ink-muted italic">No entries for this taxonomy. Add entries in Setup → Taxonomy.</p>
                  )}
                </div>
              )
            })}
          </>
        )}

        {/* ── Fields section ── */}
        {fields.length > 0 && (
          <>
            <p className="section-title mb-1 pt-1">Fields</p>
            {fields.map(field => (
              <div key={field.field_name} className="border border-rule rounded-md p-3">
                <p className="text-xs font-semibold text-ink-muted uppercase tracking-label mb-2">{field.field_label}</p>
                <FieldInput field={field} value={values[field.field_name] ?? ''} onChange={v => handleChange(field.field_name, v)} />
              </div>
            ))}
          </>
        )}

        {taxonomyTypes.length === 0 && fields.length === 0 && (
          <p className="text-sm text-ink-muted italic text-center py-4">
            No taxonomies or fields configured. Add taxonomies in Setup → Taxonomy or fields in Field Schema.
          </p>
        )}
      </div>

      {saved && <p className="text-xs text-green-600 mb-2">Saved.</p>}
      {!activeReviewerId && <p className="text-xs text-amber-600 mb-2">No reviewer selected. Select a reviewer in the top bar.</p>}

      <div className="flex gap-2">
        <button className="btn-secondary flex-1 justify-center" onClick={onClose}>Close</button>
        <button className="btn-primary flex-1 justify-center" onClick={handleSave} disabled={saving || !activeReviewerId}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </Modal>
  )
}

function FieldInput({ field, value, onChange, resolvedOptions }: {
  field: ExtractionField; value: string; onChange: (v: string) => void; resolvedOptions?: string[]
}) {
  if (field.field_type === 'boolean') {
    return (
      <div className="flex gap-3">
        {['Yes', 'No', ''].map(opt => (
          <label key={opt === '' ? 'none' : opt} className="flex items-center gap-1.5 cursor-pointer">
            <input type="radio" name={field.field_name} value={opt} checked={value === opt}
              onChange={() => onChange(opt)} className="accent-info" />
            <span className="text-sm text-ink">{opt === '' ? 'Not set' : opt}</span>
          </label>
        ))}
      </div>
    )
  }
  if (field.field_type === 'dropdown') {
    const options = resolvedOptions ?? (() => { try { return JSON.parse(field.options ?? '[]') as string[] } catch { return [] } })()
    return (
      <select className="input" value={value} onChange={e => onChange(e.target.value)}>
        <option value="">— Select —</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    )
  }
  if (field.field_type === 'number') {
    return <input type="number" className="input" value={value} onChange={e => onChange(e.target.value)} placeholder="Enter number" />
  }
  return <textarea className="textarea" rows={2} value={value} onChange={e => onChange(e.target.value)} placeholder="Enter value" />
}

// ── Table View ────────────────────────────────────────────────────────────────

function TableView({ pid }: { pid: number }) {
  const { data: summary, isLoading } = useQuery({
    queryKey: ['extraction-summary', pid],
    queryFn: () => getExtractionSummary(pid),
  })

  if (isLoading) return <p className="text-sm text-ink-muted">Loading…</p>
  if (!summary || summary.fields.length === 0) {
    return <EmptyState icon="—" message="No extraction fields defined. Add fields in the 'Field Schema' tab first." />
  }
  if (summary.papers.length === 0) {
    return <EmptyState icon="—" message="No included papers yet." />
  }

  const fieldCount = summary.fields.length

  return (
    <Card>
      <CardHeader title="Extraction Overview" />
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-rule">
              <th className="text-left pb-2 font-semibold pr-3 text-xs text-ink-muted uppercase tracking-label align-bottom" style={{ width: 160, minWidth: 120 }}>
                Paper
              </th>
              {summary.fields.map(f => (
                <th key={f.field_name} className="align-bottom p-0" style={{ width: fieldCount > 4 ? 44 : 100 }} title={f.field_label}>
                  <div className="relative" style={{ height: fieldCount > 4 ? 120 : 'auto', width: fieldCount > 4 ? 44 : 'auto' }}>
                    {fieldCount > 4 ? (
                      <span
                        className="absolute bottom-1 left-1/2 text-2xs font-semibold text-ink-muted uppercase tracking-label whitespace-nowrap origin-bottom-left"
                        style={{
                          transform: 'rotate(-50deg)',
                          transformOrigin: 'bottom left',
                          maxWidth: 140,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {f.field_label}
                      </span>
                    ) : (
                      <span className="text-xs font-semibold text-ink-muted uppercase tracking-label leading-snug line-clamp-2 block text-center pb-2 px-1">
                        {f.field_label}
                      </span>
                    )}
                  </div>
                </th>
              ))}
              <th className="align-bottom p-0" style={{ width: fieldCount > 4 ? 44 : 70 }} title="Progress">
                <div className="relative" style={{ height: fieldCount > 4 ? 120 : 'auto', width: fieldCount > 4 ? 44 : 'auto' }}>
                  {fieldCount > 4 ? (
                    <span
                      className="absolute bottom-1 left-1/2 text-2xs font-semibold text-ink-muted uppercase tracking-label whitespace-nowrap origin-bottom-left"
                      style={{
                        transform: 'rotate(-50deg)',
                        transformOrigin: 'bottom left',
                        maxWidth: 140,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      Progress
                    </span>
                  ) : (
                    <span className="text-xs font-semibold text-ink-muted uppercase tracking-label leading-snug block text-center pb-2 px-1">
                      Progress
                    </span>
                  )}
                </div>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-rule">
            {summary.papers.map(paper => (
              <tr key={paper.paper_id} className="hover:bg-paper transition-colors">
                <td className="py-2 pr-3">
                  <p className="text-sm font-medium text-ink leading-snug line-clamp-2">{paper.title}</p>
                  <p className="text-xs text-ink-muted">{formatAuthors(paper.authors)} · {paper.year}</p>
                </td>
                {summary.fields.map(f => {
                  const val = paper.values[f.field_name]
                  return (
                    <td key={f.field_name} className="py-2 text-center align-middle px-0.5">
                      {val == null || val === '' ? (
                        <span className="text-ink-muted/30 text-xs">—</span>
                      ) : (
                        <span className="text-2xs text-ink leading-tight line-clamp-2 block" title={val}>{val}</span>
                      )}
                    </td>
                  )
                })}
                <td className="py-2 text-center align-middle whitespace-nowrap">
                  <span className={`text-xs font-semibold ${
                    paper.filled === paper.total_fields ? 'text-green-600' :
                    paper.filled > 0 ? 'text-amber-600' : 'text-ink-muted'
                  }`}>
                    {paper.filled}/{paper.total_fields}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
