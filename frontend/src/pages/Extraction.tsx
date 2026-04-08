import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useProject } from '../App'
import {
  getExtractionFields, createExtractionField, updateExtractionField,
  deleteExtractionField, getExtractionSummary, upsertExtractionRecord,
  getReviewers, getTaxonomyTypes, getTaxonomy,
} from '../api/client'
import {
  Card, CardHeader, StatCard, Modal, FormField, EmptyState,
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
        <h1 className="text-xl font-bold text-navy">Data Extraction</h1>
        <p className="text-sm text-gray-500">Phase 7 — Structured Data Extraction</p>
      </div>

      <div className="flex gap-0 border-b border-border">
        {(['schema', 'extract', 'table'] as ExtView[]).map(v => (
          <button key={v} onClick={() => setView(v)}
            className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors relative capitalize ${
              view === v
                ? 'text-info after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-info'
                : 'text-gray-400 hover:text-navy'
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

  const { data: fields = [] } = useQuery({
    queryKey: ['extraction-fields', pid],
    queryFn: () => getExtractionFields(pid),
  })

  // Taxonomy types for pre-populating dropdown options
  const { data: taxonomyTypes = [] } = useQuery({
    queryKey: ['taxonomy-types', pid],
    queryFn: () => getTaxonomyTypes(pid),
    enabled: modal?.mode === 'add' || modal?.mode === 'edit',
  })

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
          action={<button className="btn-secondary text-xs" onClick={openAdd}>+ Add Field</button>}
        />

        {fields.length === 0 ? (
          <EmptyState icon="—" message="No extraction fields defined. Add fields to start extracting data." />
        ) : (
          fields.map((f, idx) => (
            <div key={f.id} className="py-2.5 border-b border-border last:border-0 flex items-center gap-3">
              {/* Up/Down reorder */}
              <div className="flex flex-col gap-0.5 shrink-0">
                <button
                  className="text-gray-300 hover:text-navy-muted leading-none px-0.5 disabled:opacity-20"
                  onClick={() => moveField(idx, 'up')} disabled={idx === 0 || moving}
                  title="Move up">▲</button>
                <button
                  className="text-gray-300 hover:text-navy-muted leading-none px-0.5 disabled:opacity-20"
                  onClick={() => moveField(idx, 'down')} disabled={idx === fields.length - 1 || moving}
                  title="Move down">▼</button>
              </div>
              {/* Type badge — uniform width */}
              <span className={`text-xs font-bold rounded px-2 py-0.5 border shrink-0 w-[72px] text-center ${TYPE_COLORS[f.field_type] ?? TYPE_COLORS.text}`}>
                {FIELD_TYPES.find(t => t.value === f.field_type)?.label ?? f.field_type}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-navy leading-snug">{f.field_label}</p>
                {f.field_type === 'dropdown' && f.options && (
                  <p className="text-xs text-gray-400 mt-0.5 truncate">
                    {(() => { try { return (JSON.parse(f.options) as string[]).join(' · ') } catch { return f.options } })()}
                  </p>
                )}
              </div>
              <div className="flex gap-1 shrink-0">
                <button className="btn-secondary text-xs" onClick={() => openEdit(f)}>Edit</button>
                <button className="btn-danger text-xs" onClick={() => setDeleteTarget(f)}>Remove</button>
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
                  <span className="text-xs text-gray-500">Load from taxonomy:</span>
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
          <p className="text-sm text-gray-700 mb-4">
            Remove field <span className="font-semibold text-navy">"{deleteTarget.field_label}"</span>? All extracted values for this field will be permanently deleted.
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

  if (isLoading) return <p className="text-sm text-gray-400">Loading…</p>
  if (!summary) return null

  if (summary.fields.length === 0) {
    return <EmptyState icon="—" message="No extraction fields defined. Add fields in the 'Field Schema' tab first." />
  }
  if (summary.papers.length === 0) {
    return <EmptyState icon="—" message="No included papers yet. Complete Full-Text Eligibility (Phase 4) first." />
  }

  const done = summary.papers.filter(p => p.filled === p.total_fields).length

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Included Papers" value={summary.papers.length} sub="From Phase 4 (Eligibility)" />
        <StatCard label="Fully Extracted" value={done} color="include" />
        <StatCard label="Pending" value={summary.papers.length - done} color="uncertain" />
      </div>

      <div className="space-y-2">
        {summary.papers.map(paper => (
          <ExtractionPaperCard key={paper.paper_id} paper={paper} onExtract={() => setSelectedPaper(paper)} />
        ))}
      </div>

      {selectedPaper && (
        <ExtractionModal
          paper={selectedPaper}
          fields={summary.fields}
          pid={pid}
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
            'bg-gray-100 text-gray-600 border-gray-200'
          }`}>
            {done ? 'Complete' : `${paper.filled}/${paper.total_fields} filled`}
          </span>
          {paper.total_fields > 0 && !done && (
            <div className="flex-1 max-w-[120px] bg-gray-200 rounded-full h-1.5">
              <div className="bg-info h-1.5 rounded-full transition-all" style={{ width: `${pct}%` }} />
            </div>
          )}
          <span className="text-xs text-gray-400 ml-auto">{paper.source} · {paper.year}</span>
        </div>
        <h3 className="text-sm font-medium text-navy mt-1 leading-snug">{paper.title}</h3>
        {paper.authors && <p className="text-xs text-gray-400 mt-0.5">{formatAuthors(paper.authors)}</p>}
      </div>
    </div>
  )
}

function ExtractionModal({ paper, fields, pid, onClose }: {
  paper: ExtractionPaperRow
  fields: ExtractionField[]
  pid: number
  onClose: () => void
}) {
  const qc = useQueryClient()
  const { reviewerId } = useProject()

  const { data: reviewers = [] } = useQuery({
    queryKey: ['reviewers', pid],
    queryFn: () => getReviewers(pid),
  })

  const activeReviewerId = reviewerId ?? reviewers.find(r => r.role === 'R1')?.id ?? reviewers[0]?.id

  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    for (const f of fields) init[f.field_name] = paper.values[f.field_name] ?? ''
    return init
  })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const handleChange = (fieldName: string, value: string) => {
    setValues(prev => ({ ...prev, [fieldName]: value }))
    setSaved(false)
  }

  const handleSave = async () => {
    if (!activeReviewerId) return
    setSaving(true)
    setSaved(false)
    try {
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

  return (
    <Modal title="Data Extraction" onClose={onClose} width="max-w-2xl">
      <div className="bg-card rounded-md p-4 mb-4 border border-border">
        <p className="text-sm font-semibold text-navy mb-1">{paper.title}</p>
        <p className="text-xs text-gray-400">{formatAuthors(paper.authors)} · {paper.year}</p>
      </div>

      <div className="space-y-3 mb-4">
        {fields.map(field => (
          <div key={field.field_name} className="border border-border rounded-md p-3">
            <p className="text-sm font-semibold text-navy mb-1">{field.field_label}</p>
            <FieldInput field={field} value={values[field.field_name] ?? ''} onChange={v => handleChange(field.field_name, v)} />
          </div>
        ))}
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

function FieldInput({ field, value, onChange }: {
  field: ExtractionField; value: string; onChange: (v: string) => void
}) {
  if (field.field_type === 'boolean') {
    return (
      <div className="flex gap-3">
        {['Yes', 'No', ''].map(opt => (
          <label key={opt === '' ? 'none' : opt} className="flex items-center gap-1.5 cursor-pointer">
            <input type="radio" name={field.field_name} value={opt} checked={value === opt}
              onChange={() => onChange(opt)} className="accent-info" />
            <span className="text-sm text-navy">{opt === '' ? 'Not set' : opt}</span>
          </label>
        ))}
      </div>
    )
  }
  if (field.field_type === 'dropdown') {
    const options: string[] = (() => { try { return JSON.parse(field.options ?? '[]') } catch { return [] } })()
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

  if (isLoading) return <p className="text-sm text-gray-400">Loading…</p>
  if (!summary || summary.fields.length === 0) {
    return <EmptyState icon="—" message="No extraction fields defined. Add fields in the 'Field Schema' tab first." />
  }
  if (summary.papers.length === 0) {
    return <EmptyState icon="—" message="No included papers yet." />
  }

  return (
    <Card>
      <CardHeader title="Extraction Overview" />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-navy-muted uppercase tracking-wider border-b border-border">
              <th className="text-left pb-2 font-semibold pr-3 min-w-[200px]">Paper</th>
              {summary.fields.map(f => (
                <th key={f.field_name} className="text-center pb-2 font-semibold px-2 min-w-[100px] max-w-[140px]" title={f.field_label}>
                  <span className="truncate block">{f.field_label}</span>
                </th>
              ))}
              <th className="text-right pb-2 font-semibold">Progress</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {summary.papers.map(paper => (
              <tr key={paper.paper_id} className="hover:bg-card transition-colors">
                <td className="py-2 pr-3">
                  <p className="text-sm font-medium text-navy leading-snug line-clamp-2">{paper.title}</p>
                  <p className="text-xs text-gray-400">{formatAuthors(paper.authors)} · {paper.year}</p>
                </td>
                {summary.fields.map(f => {
                  const val = paper.values[f.field_name]
                  return (
                    <td key={f.field_name} className="py-2 text-center px-2">
                      {val == null || val === '' ? (
                        <span className="text-gray-300 text-xs">—</span>
                      ) : (
                        <span className="text-xs text-navy max-w-[130px] truncate block mx-auto" title={val}>{val}</span>
                      )}
                    </td>
                  )
                })}
                <td className="py-2 text-right whitespace-nowrap">
                  <span className={`text-xs font-semibold ${
                    paper.filled === paper.total_fields ? 'text-green-600' :
                    paper.filled > 0 ? 'text-amber-600' : 'text-gray-400'
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
