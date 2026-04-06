import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useProject } from '../App'
import {
  getProject, updateProject,
  getReviewers, addReviewer, deleteReviewer,
  getInclusionCriteria, addInclusionCriterion, updateInclusionCriterion, deleteInclusionCriterion,
  getExclusionCriteria, addExclusionCriterion, updateExclusionCriterion, deleteExclusionCriterion,
  getQACriteria, addQACriterion, updateQACriterion, deleteQACriterion,
  getTaxonomyTypes, getTaxonomy, addTaxonomyEntry, deleteTaxonomyEntry, renameTaxonomyType, deleteTaxonomyType,
  getSearchStrings, addSearchString, updateSearchString, deleteSearchString,
} from '../api/client'
import { Card, CardHeader, Modal, FormField, EmptyState, ConfirmDialog } from '../components/ui'
import { DATABASES, DatabaseBadge } from '../components/databases'

type Tab = 'project' | 'reviewers' | 'criteria' | 'qa' | 'taxonomies' | 'search'

const TABS: { id: Tab; label: string }[] = [
  { id: 'project',    label: 'Project' },
  { id: 'reviewers',  label: 'Reviewers' },
  { id: 'criteria',   label: 'I/E Criteria' },
  { id: 'qa',         label: 'QA Schema' },
  { id: 'taxonomies', label: 'Taxonomies' },
  { id: 'search',     label: 'Search Strings' },
]

const ROLES = ['R1', 'R2', 'R3', 'R4', 'R5']

export default function Settings() {
  const { projectId } = useProject()
  const [tab, setTab] = useState<Tab>('project')

  if (!projectId) {
    return (
      <EmptyState
        icon="⚙"
        message="No active project. Create or select a project from the Overview first."
      />
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-navy">Setup</h1>
        <p className="text-sm text-gray-500">Phase 0 — Configure your SLR project</p>
      </div>

      <div className="flex gap-0 border-b border-border">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors relative ${
              tab === t.id
                ? 'text-info after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-info'
                : 'text-gray-400 hover:text-navy'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'project'    && <ProjectTab pid={projectId} />}
      {tab === 'reviewers'  && <ReviewersTab pid={projectId} />}
      {tab === 'criteria'   && <CriteriaTab pid={projectId} />}
      {tab === 'qa'         && <QATab pid={projectId} />}
      {tab === 'taxonomies' && <TaxonomiesTab pid={projectId} />}
      {tab === 'search'     && <SearchStringsTab pid={projectId} />}
    </div>
  )
}

// ── Project Tab ───────────────────────────────────────────────────────────────

function ProjectTab({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const { data: project } = useQuery({ queryKey: ['project', pid], queryFn: () => getProject(pid) })
  const [form, setForm] = useState<Record<string, string | number>>({})
  const [submitted, setSubmitted] = useState(false)
  const mutation = useMutation({
    mutationFn: (data: any) => updateProject(pid, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project', pid] }); setForm({}); setSubmitted(false) },
  })

  if (!project) return null
  const val = (key: string) => (key in form ? form[key] : (project as any)[key])
  const currentTitle = val('title') as string
  const save = () => {
    setSubmitted(true)
    if (!currentTitle?.trim()) return
    if (Object.keys(form).length > 0) mutation.mutate(form)
  }

  return (
    <div className="max-w-xl space-y-4">
      <Card>
        <CardHeader title="Project Details" />
        <FormField label="Title" required error={submitted && !currentTitle?.trim() ? 'Title is required' : undefined}>
          <input className={`input ${submitted && !currentTitle?.trim() ? 'border-exclude ring-1 ring-exclude' : ''}`}
            value={currentTitle}
            onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            onKeyDown={e => e.key === 'Enter' && save()} />
        </FormField>
        <FormField label="Lead Researcher">
          <input className="input" value={val('lead_researcher') as string}
            onChange={e => setForm(f => ({ ...f, lead_researcher: e.target.value }))}
            onKeyDown={e => e.key === 'Enter' && save()} />
        </FormField>
        <FormField label="Description">
          <textarea className="textarea" rows={3} value={val('description') as string ?? ''}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
        </FormField>
      </Card>

      <Card>
        <CardHeader title="QA Thresholds" />
        <div className="grid grid-cols-2 gap-4">
          <FormField label="High Quality ≥ (%)">
            <input type="number" className="input" min={0} max={100} value={val('qa_high_threshold') as number}
              onChange={e => setForm(f => ({ ...f, qa_high_threshold: parseFloat(e.target.value) }))}
              onKeyDown={e => e.key === 'Enter' && save()} />
          </FormField>
          <FormField label="Medium Quality ≥ (%)">
            <input type="number" className="input" min={0} max={100} value={val('qa_medium_threshold') as number}
              onChange={e => setForm(f => ({ ...f, qa_medium_threshold: parseFloat(e.target.value) }))}
              onKeyDown={e => e.key === 'Enter' && save()} />
          </FormField>
        </div>
        <FormField label="Post-year Threshold">
          <input type="number" className="input" value={val('post_year_threshold') as number}
            onChange={e => setForm(f => ({ ...f, post_year_threshold: parseInt(e.target.value) }))}
            onKeyDown={e => e.key === 'Enter' && save()} />
        </FormField>
      </Card>

      <div className="flex items-center gap-3">
        <button className="btn-primary" disabled={mutation.isPending} onClick={save}>
          {mutation.isPending ? 'Saving…' : 'Save Changes'}
        </button>
        {mutation.isSuccess && <span className="text-xs text-include">Saved</span>}
      </div>
    </div>
  )
}

// ── Reviewers Tab ─────────────────────────────────────────────────────────────

function ReviewersTab({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const { data: reviewers = [] } = useQuery({ queryKey: ['reviewers', pid], queryFn: () => getReviewers(pid) })
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState({ name: '', email: '', role: 'R2' })
  const [submitted, setSubmitted] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  const addMutation = useMutation({
    mutationFn: () => addReviewer(pid, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['reviewers', pid] }); setModal(false); setForm({ name: '', email: '', role: 'R2' }); setSubmitted(false) },
  })
  const deleteMutation = useMutation({
    mutationFn: (rid: number) => deleteReviewer(pid, rid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reviewers', pid] }),
  })

  const usedRoles = reviewers.map(r => r.role)
  const availableRoles = ROLES.filter(r => !usedRoles.includes(r))
  const submit = () => { setSubmitted(true); if (form.name) addMutation.mutate() }

  return (
    <div className="max-w-xl">
      <Card>
        <CardHeader
          title="Reviewers (max 5)"
          action={reviewers.length < 5
            ? <button className="btn-secondary text-xs" onClick={() => { setSubmitted(false); setModal(true) }}>+ Add</button>
            : null}
        />
        {reviewers.length === 0 ? (
          <EmptyState icon="—" message="No reviewers configured. R1 is always the lead reviewer." />
        ) : (
          <div className="divide-y divide-border">
            {reviewers.sort((a, b) => a.role.localeCompare(b.role)).map(r => (
              <div key={r.id} className="py-3 flex items-center gap-3">
                <span className={`text-xs font-bold px-2 py-0.5 rounded border ${r.role === 'R1' ? 'bg-blue-50 text-info border-blue-200' : 'bg-gray-50 text-gray-600 border-gray-200'}`}>
                  {r.role}
                </span>
                <div className="flex-1">
                  <p className="text-sm font-medium text-navy">{r.name}</p>
                  {r.email && <p className="text-xs text-gray-400">{r.email}</p>}
                </div>
                {r.role !== 'R1' && (
                  <button className="btn-danger text-xs px-2 py-1" onClick={() => setConfirmDelete(r.id)}>Remove</button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {confirmDelete !== null && (
        <ConfirmDialog
          message="Remove this reviewer? Their decisions will remain but they will no longer appear in the reviewer list."
          onConfirm={() => { deleteMutation.mutate(confirmDelete); setConfirmDelete(null) }}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      {modal && (
        <Modal title="Add Reviewer" onClose={() => setModal(false)} onEnter={submit}>
          <FormField label="Name" required error={submitted && !form.name ? 'Name is required' : undefined}>
            <input className={`input ${submitted && !form.name ? 'border-exclude ring-1 ring-exclude' : ''}`}
              value={form.name} autoFocus
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          </FormField>
          <FormField label="Email (display only)">
            <input className="input" type="email" value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
          </FormField>
          <FormField label="Role">
            <select className="select" value={form.role}
              onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
              {availableRoles.map(r => <option key={r} value={r}>{r}{r === 'R1' ? ' (Lead)' : ''}</option>)}
            </select>
          </FormField>
          <button className="btn-primary w-full justify-center mt-2"
            disabled={addMutation.isPending} onClick={submit}>
            {addMutation.isPending ? 'Adding…' : 'Add Reviewer'}
          </button>
        </Modal>
      )}
    </div>
  )
}

// ── Criteria Tab ──────────────────────────────────────────────────────────────

type CriterionModalState = {
  type: 'add-i' | 'add-e' | 'edit-i' | 'edit-e'
  id?: number
  label?: string
  description?: string
  phase?: string
} | null

function CriteriaTab({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const { data: inclusions = [] } = useQuery({ queryKey: ['inclusion', pid], queryFn: () => getInclusionCriteria(pid) })
  const { data: exclusions = [] } = useQuery({ queryKey: ['exclusion', pid], queryFn: () => getExclusionCriteria(pid) })

  const [modal, setModal] = useState<CriterionModalState>(null)
  const [form, setForm] = useState({ label: '', description: '', phase: 'screening' })
  const [submitted, setSubmitted] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<{ type: 'i' | 'e'; id: number } | null>(null)

  const openAdd = (type: 'add-i' | 'add-e') => {
    setForm({ label: '', description: '', phase: 'screening' }); setSubmitted(false); setModal({ type })
  }
  const openEdit = (type: 'edit-i' | 'edit-e', c: any) => {
    setForm({ label: c.label, description: c.description, phase: c.phase }); setSubmitted(false); setModal({ type, id: c.id })
  }
  const close = () => { setModal(null); setSubmitted(false) }

  const addI = useMutation({
    mutationFn: () => addInclusionCriterion(pid, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['inclusion', pid] }); close() },
  })
  const addE = useMutation({
    mutationFn: () => addExclusionCriterion(pid, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['exclusion', pid] }); close() },
  })
  const editI = useMutation({
    mutationFn: () => updateInclusionCriterion(pid, modal!.id!, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['inclusion', pid] }); close() },
  })
  const editE = useMutation({
    mutationFn: () => updateExclusionCriterion(pid, modal!.id!, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['exclusion', pid] }); close() },
  })
  const delI = useMutation({ mutationFn: (id: number) => deleteInclusionCriterion(pid, id), onSuccess: () => qc.invalidateQueries({ queryKey: ['inclusion', pid] }) })
  const delE = useMutation({ mutationFn: (id: number) => deleteExclusionCriterion(pid, id), onSuccess: () => qc.invalidateQueries({ queryKey: ['exclusion', pid] }) })

  const isAdd = modal?.type === 'add-i' || modal?.type === 'add-e'
  const isInclusion = modal?.type === 'add-i' || modal?.type === 'edit-i'
  const isPending = addI.isPending || addE.isPending || editI.isPending || editE.isPending
  const submit = () => {
    setSubmitted(true)
    if (!form.label || !form.description) return
    if (modal?.type === 'add-i') addI.mutate()
    else if (modal?.type === 'add-e') addE.mutate()
    else if (modal?.type === 'edit-i') editI.mutate()
    else if (modal?.type === 'edit-e') editE.mutate()
  }

  return (
    <div className="max-w-2xl space-y-4">
      <Card>
        <CardHeader title="Inclusion Criteria"
          action={<button className="btn-secondary text-xs" onClick={() => openAdd('add-i')}>+ Add</button>} />
        {inclusions.length === 0
          ? <EmptyState icon="—" message="No inclusion criteria defined." />
          : inclusions.map(c => (
            <CriterionRow key={c.id} label={c.label} description={c.description} badge={`Phase: ${c.phase}`}
              onEdit={() => openEdit('edit-i', c)} onDelete={() => setConfirmDelete({ type: 'i', id: c.id })} />
          ))}
      </Card>

      <Card>
        <CardHeader title="Exclusion Criteria"
          action={<button className="btn-secondary text-xs" onClick={() => openAdd('add-e')}>+ Add</button>} />
        {exclusions.length === 0
          ? <EmptyState icon="—" message="No exclusion criteria defined." />
          : exclusions.map(c => (
            <CriterionRow key={c.id} label={c.label} description={c.description} badge={`Phase: ${c.phase}`}
              onEdit={() => openEdit('edit-e', c)} onDelete={() => setConfirmDelete({ type: 'e', id: c.id })} />
          ))}
      </Card>

      {confirmDelete !== null && (
        <ConfirmDialog
          message="Delete this criterion? This cannot be undone."
          onConfirm={() => {
            confirmDelete.type === 'i' ? delI.mutate(confirmDelete.id) : delE.mutate(confirmDelete.id)
            setConfirmDelete(null)
          }}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      {modal && (
        <Modal
          title={isAdd
            ? (isInclusion ? 'Add Inclusion Criterion' : 'Add Exclusion Criterion')
            : (isInclusion ? 'Edit Inclusion Criterion' : 'Edit Exclusion Criterion')}
          onClose={close}
          onEnter={submit}
        >
          <FormField label="Label" required error={submitted && !form.label ? 'Label is required (e.g. I1, E3)' : undefined}>
            <input className={`input ${submitted && !form.label ? 'border-exclude ring-1 ring-exclude' : ''}`}
              placeholder="I1" value={form.label} autoFocus
              onChange={e => setForm(f => ({ ...f, label: e.target.value }))} />
          </FormField>
          <FormField label="Description" required error={submitted && !form.description ? 'Description is required' : undefined}>
            <textarea className={`textarea ${submitted && !form.description ? 'border-exclude ring-1 ring-exclude' : ''}`}
              rows={3} value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          </FormField>
          <FormField label="Phase">
            <select className="select" value={form.phase}
              onChange={e => setForm(f => ({ ...f, phase: e.target.value }))}>
              <option value="screening">Screening (title/abstract)</option>
              <option value="full-text">Full-text eligibility</option>
            </select>
          </FormField>
          <button className="btn-primary w-full justify-center mt-2"
            disabled={isPending} onClick={submit}>
            {isAdd ? 'Add Criterion' : 'Save Changes'}
          </button>
        </Modal>
      )}
    </div>
  )
}

// ── Criterion row component ───────────────────────────────────────────────────

function CriterionRow({ label, description, badge, onEdit, onDelete }: {
  label: string; description: string; badge?: string; onEdit: () => void; onDelete: () => void
}) {
  return (
    <div className="flex items-start gap-3 py-3 border-b border-border last:border-0">
      <span className="shrink-0 text-xs font-bold text-info bg-blue-50 border border-blue-200 rounded px-2 py-0.5 mt-0.5">{label}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-navy">{description}</p>
        {badge && <span className="text-xs text-gray-400">{badge}</span>}
      </div>
      <div className="flex gap-1 shrink-0">
        <button onClick={onEdit} className="btn-secondary text-xs px-2 py-1">Edit</button>
        <button onClick={onDelete} className="btn-danger text-xs px-2 py-1">Remove</button>
      </div>
    </div>
  )
}

// ── QA Tab ────────────────────────────────────────────────────────────────────

type QAModalState = { mode: 'add' | 'edit'; id?: number } | null

function QATab({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const { data: criteria = [] } = useQuery({ queryKey: ['qa', pid], queryFn: () => getQACriteria(pid) })
  const [modal, setModal] = useState<QAModalState>(null)
  const [form, setForm] = useState({ label: '', description: '', max_score: 1.0 })
  const [submitted, setSubmitted] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  const totalMax = criteria.reduce((sum, c) => sum + c.max_score, 0)

  const openAdd = () => { setForm({ label: '', description: '', max_score: 1.0 }); setSubmitted(false); setModal({ mode: 'add' }) }
  const openEdit = (c: any) => { setForm({ label: c.label, description: c.description, max_score: c.max_score }); setSubmitted(false); setModal({ mode: 'edit', id: c.id }) }
  const close = () => { setModal(null); setSubmitted(false) }

  const addMutation = useMutation({
    mutationFn: () => addQACriterion(pid, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['qa', pid] }); close() },
  })
  const editMutation = useMutation({
    mutationFn: () => updateQACriterion(pid, modal!.id!, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['qa', pid] }); close() },
  })
  const delMutation = useMutation({
    mutationFn: (id: number) => deleteQACriterion(pid, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['qa', pid] }),
  })

  const isPending = addMutation.isPending || editMutation.isPending
  const submit = () => {
    setSubmitted(true)
    if (!form.label || !form.description) return
    modal?.mode === 'add' ? addMutation.mutate() : editMutation.mutate()
  }

  return (
    <div className="max-w-2xl">
      <Card>
        <CardHeader
          title={`QA Schema — Max score: ${totalMax.toFixed(1)}`}
          action={<button className="btn-secondary text-xs" onClick={openAdd}>+ Add</button>}
        />
        {criteria.length === 0
          ? <EmptyState icon="—" message="No QA criteria defined." />
          : criteria.map(c => (
            <div key={c.id} className="py-3 border-b border-border last:border-0 flex items-start gap-3">
              <span className="text-xs font-bold text-info bg-blue-50 border border-blue-200 rounded px-2 py-0.5 shrink-0 mt-0.5">{c.label}</span>
              <div className="flex-1">
                <p className="text-sm text-navy">{c.description}</p>
                <p className="text-xs text-gray-400 mt-0.5">Max score: {c.max_score}</p>
              </div>
              <div className="flex gap-1 shrink-0">
                <button className="btn-secondary text-xs px-2 py-1" onClick={() => openEdit(c)}>Edit</button>
                <button className="btn-danger text-xs px-2 py-1" onClick={() => setConfirmDelete(c.id)}>Remove</button>
              </div>
            </div>
          ))}
      </Card>

      {confirmDelete !== null && (
        <ConfirmDialog
          message="Delete this QA criterion? This cannot be undone."
          onConfirm={() => { delMutation.mutate(confirmDelete); setConfirmDelete(null) }}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      {modal && (
        <Modal title={modal.mode === 'add' ? 'Add QA Criterion' : 'Edit QA Criterion'}
          onClose={close} onEnter={submit}>
          <FormField label="Label" required error={submitted && !form.label ? 'Label is required (e.g. QA1)' : undefined}>
            <input className={`input ${submitted && !form.label ? 'border-exclude ring-1 ring-exclude' : ''}`}
              placeholder="QA1" value={form.label} autoFocus
              onChange={e => setForm(f => ({ ...f, label: e.target.value }))} />
          </FormField>
          <FormField label="Description / Question" required error={submitted && !form.description ? 'Description is required' : undefined}>
            <textarea className={`textarea ${submitted && !form.description ? 'border-exclude ring-1 ring-exclude' : ''}`}
              rows={3} value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          </FormField>
          <FormField label="Max Score">
            <select className="select" value={form.max_score}
              onChange={e => setForm(f => ({ ...f, max_score: parseFloat(e.target.value) }))}>
              <option value={1.0}>1.0</option>
              <option value={0.5}>0.5</option>
            </select>
          </FormField>
          <button className="btn-primary w-full justify-center mt-2"
            disabled={isPending} onClick={submit}>
            {modal.mode === 'add' ? 'Add Criterion' : 'Save Changes'}
          </button>
        </Modal>
      )}
    </div>
  )
}

// ── Taxonomies Tab ────────────────────────────────────────────────────────────

const DEFAULT_TAXONOMY_TYPES = [
  { key: 'research_type',     label: 'Research Type'     },
  { key: 'contribution_type', label: 'Contribution Type' },
  { key: 'usage_scenario',    label: 'Usage Scenario'    },
]

type TaxonomyModal =
  | { kind: 'add-category' }
  | { kind: 'edit-category'; key: string; label: string }
  | { kind: 'confirm-delete-category'; key: string }
  | { kind: 'add-entry' }
  | { kind: 'confirm-delete-entry'; id: number }

function TaxonomiesTab({ pid }: { pid: number }) {
  const qc = useQueryClient()

  // Track which built-in default categories have been explicitly deleted, per project
  const lsKey = `reviq_deleted_taxonomies_${pid}`
  const [deletedDefaults, setDeletedDefaults] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem(lsKey) ?? '[]')) } catch { return new Set() }
  })
  const markDeleted = (key: string) => {
    setDeletedDefaults(prev => {
      const next = new Set(prev)
      next.add(key)
      localStorage.setItem(lsKey, JSON.stringify([...next]))
      return next
    })
  }

  // Load taxonomy types from the backend (= distinct taxonomy_type strings that have entries)
  const { data: backendTypes = [] } = useQuery({
    queryKey: ['taxonomy-types', pid],
    queryFn: () => getTaxonomyTypes(pid),
  })

  // Merge: defaults (minus deleted) + backend-only types, deduplicated
  const allTypes = [
    ...DEFAULT_TAXONOMY_TYPES.filter(d => !deletedDefaults.has(d.key)),
    ...backendTypes
      .filter(k => !DEFAULT_TAXONOMY_TYPES.some(d => d.key === k))
      .map(k => ({ key: k, label: k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) })),
  ]

  const [activeKey, setActiveKey] = useState(DEFAULT_TAXONOMY_TYPES[0].key)
  const activeLabel = allTypes.find(t => t.key === activeKey)?.label ?? activeKey

  const [modal, setModal] = useState<TaxonomyModal | null>(null)
  const [catForm, setCatForm] = useState({ label: '' })
  const [catSubmitted, setCatSubmitted] = useState(false)
  const [entryValue, setEntryValue] = useState('')
  const [entrySubmitted, setEntrySubmitted] = useState(false)
  const [editingEntryId, setEditingEntryId] = useState<number | null>(null)
  const [editEntryValue, setEditEntryValue] = useState('')
  const [editEntryError, setEditEntryError] = useState(false)

  const { data: entries = [] } = useQuery({
    queryKey: ['taxonomy', pid, activeKey],
    queryFn: () => getTaxonomy(pid, activeKey),
  })

  // Category mutations
  const renameCatMutation = useMutation({
    mutationFn: ({ oldKey, newKey }: { oldKey: string; newKey: string }) => renameTaxonomyType(pid, oldKey, newKey),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['taxonomy-types', pid] })
      qc.invalidateQueries({ queryKey: ['taxonomy', pid] })
      setModal(null)
    },
  })
  const deleteCatMutation = useMutation({
    mutationFn: (key: string) => deleteTaxonomyType(pid, key),
    onSuccess: (_data, key) => {
      // If it's a built-in default, remember it was deleted so it doesn't reappear
      if (DEFAULT_TAXONOMY_TYPES.some(d => d.key === key)) markDeleted(key)
      qc.invalidateQueries({ queryKey: ['taxonomy-types', pid] })
      qc.invalidateQueries({ queryKey: ['taxonomy', pid] })
      const remaining = allTypes.filter(t => t.key !== key)
      setActiveKey(remaining[0]?.key ?? '')
      setModal(null)
    },
  })

  // Entry mutations
  const addEntryMutation = useMutation({
    mutationFn: () => addTaxonomyEntry(pid, activeKey, entryValue.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['taxonomy', pid, activeKey] })
      qc.invalidateQueries({ queryKey: ['taxonomy-types', pid] })
      setEntryValue('')
      setEntrySubmitted(false)
      setModal(null)
    },
  })
  const editEntryMutation = useMutation({
    mutationFn: ({ id, value }: { id: number; value: string }) =>
      deleteTaxonomyEntry(pid, id).then(() => addTaxonomyEntry(pid, activeKey, value)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['taxonomy', pid, activeKey] }); setEditingEntryId(null) },
  })
  const delEntryMutation = useMutation({
    mutationFn: (id: number) => deleteTaxonomyEntry(pid, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['taxonomy', pid, activeKey] }),
  })

  const submitAddCategory = () => {
    setCatSubmitted(true)
    if (!catForm.label.trim()) return
    // Key is auto-derived from label; category is created implicitly on first entry add
    const newKey = catForm.label.trim().toLowerCase().replace(/\s+/g, '_')
    setActiveKey(newKey)
    setModal(null)
    setCatSubmitted(false)
  }

  const submitEditCategory = (oldKey: string) => {
    setCatSubmitted(true)
    if (!catForm.label.trim()) return
    const newKey = catForm.label.trim().toLowerCase().replace(/\s+/g, '_')
    renameCatMutation.mutate({ oldKey, newKey })
  }

  const submitAddEntry = () => {
    setEntrySubmitted(true)
    if (!entryValue.trim()) return
    addEntryMutation.mutate()
  }

  return (
    <div className="max-w-xl space-y-3">
      {/* Category selector + management */}
      <Card>
        <CardHeader
          title="Taxonomy Categories"
          action={
            <button className="btn-secondary text-xs" onClick={() => { setCatForm({ label: '' }); setCatSubmitted(false); setModal({ kind: 'add-category' }) }}>
              + New Category
            </button>
          }
        />
        <div className="divide-y divide-border">
          {allTypes.map(t => (
            <div key={t.key} className={`flex items-center justify-between py-2 px-1 rounded cursor-pointer transition-colors ${activeKey === t.key ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
              onClick={() => setActiveKey(t.key)}>
              <span className={`text-sm font-medium ${activeKey === t.key ? 'text-info' : 'text-navy'}`}>{t.label}</span>
              <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                <button className="btn-secondary text-xs px-2 py-0.5"
                  onClick={() => { setCatForm({ label: t.label }); setCatSubmitted(false); setModal({ kind: 'edit-category', key: t.key, label: t.label }) }}>
                  Edit
                </button>
                <button className="btn-danger text-xs px-2 py-0.5"
                  onClick={() => setModal({ kind: 'confirm-delete-category', key: t.key })}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Entries for active category */}
      <Card>
        <CardHeader
          title={`Entries — ${activeLabel}`}
          action={<button className="btn-secondary text-xs" onClick={() => { setEntryValue(''); setEntrySubmitted(false); setModal({ kind: 'add-entry' }) }}>+ Add</button>}
        />
        {entries.length === 0
          ? <EmptyState icon="—" message="No entries yet." />
          : (
            <div className="divide-y divide-border">
              {entries.map(e => (
                <div key={e.id} className="py-2 flex items-center gap-2">
                  {editingEntryId === e.id ? (
                    <div className="flex-1 flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <input
                          className={`input flex-1 text-sm ${editEntryError && !editEntryValue.trim() ? 'border-exclude ring-1 ring-exclude' : ''}`}
                          value={editEntryValue} autoFocus
                          onChange={ev => { setEditEntryValue(ev.target.value); if (editEntryError) setEditEntryError(false) }}
                          onKeyDown={ev => {
                            if (ev.key === 'Enter') {
                              if (!editEntryValue.trim()) { setEditEntryError(true); return }
                              editEntryMutation.mutate({ id: e.id, value: editEntryValue.trim() })
                            }
                            if (ev.key === 'Escape') setEditingEntryId(null)
                          }} />
                        <button className="btn-primary text-xs px-2 py-1 shrink-0"
                          disabled={editEntryMutation.isPending}
                          onClick={() => {
                            if (!editEntryValue.trim()) { setEditEntryError(true); return }
                            editEntryMutation.mutate({ id: e.id, value: editEntryValue.trim() })
                          }}>Save</button>
                        <button className="btn-secondary text-xs px-2 py-1 shrink-0" onClick={() => setEditingEntryId(null)}>Cancel</button>
                      </div>
                      {editEntryError && !editEntryValue.trim() && (
                        <p className="text-xs text-exclude">Entry name is required</p>
                      )}
                    </div>
                  ) : (
                    <>
                      <span className="text-sm text-navy flex-1">{e.value}</span>
                      <button className="btn-secondary text-xs px-2 py-1 shrink-0" onClick={() => { setEditingEntryId(e.id); setEditEntryValue(e.value); setEditEntryError(false) }}>Edit</button>
                      <button className="btn-danger text-xs px-2 py-1 shrink-0" onClick={() => setModal({ kind: 'confirm-delete-entry', id: e.id })}>Remove</button>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
      </Card>

      {/* Modals */}
      {modal?.kind === 'add-category' && (
        <Modal title="New Taxonomy Category" onClose={() => setModal(null)} onEnter={submitAddCategory}>
          <FormField label="Category Name" required error={catSubmitted && !catForm.label.trim() ? 'Category name is required' : undefined}>
            <input className={`input ${catSubmitted && !catForm.label.trim() ? 'border-exclude ring-1 ring-exclude' : ''}`}
              placeholder="e.g. Venue Type" value={catForm.label} autoFocus
              onChange={e => setCatForm(f => ({ ...f, label: e.target.value }))} />
          </FormField>
          <button className="btn-primary w-full justify-center mt-2" onClick={submitAddCategory}>
            Create Category
          </button>
        </Modal>
      )}

      {modal?.kind === 'edit-category' && (
        <Modal title="Edit Taxonomy Category" onClose={() => setModal(null)} onEnter={() => submitEditCategory(modal.key)}>
          <FormField label="Display Name" required error={catSubmitted && !catForm.label.trim() ? 'Display name is required' : undefined}>
            <input className={`input ${catSubmitted && !catForm.label.trim() ? 'border-exclude ring-1 ring-exclude' : ''}`}
              value={catForm.label} autoFocus
              onChange={e => setCatForm(f => ({ ...f, label: e.target.value }))} />
          </FormField>
          <button className="btn-primary w-full justify-center mt-2"
            disabled={renameCatMutation.isPending} onClick={() => submitEditCategory(modal.key)}>
            Save Changes
          </button>
        </Modal>
      )}

      {modal?.kind === 'confirm-delete-category' && (
        <ConfirmDialog
          message={`Delete the entire "${allTypes.find(t => t.key === modal.key)?.label ?? modal.key}" category and all its entries? This cannot be undone.`}
          confirmLabel="Delete Category"
          onConfirm={() => deleteCatMutation.mutate(modal.key)}
          onCancel={() => setModal(null)}
        />
      )}

      {modal?.kind === 'add-entry' && (
        <Modal title={`Add Entry to "${activeLabel}"`} onClose={() => setModal(null)} onEnter={submitAddEntry}>
          <FormField label="Value" required error={entrySubmitted && !entryValue.trim() ? 'Value is required' : undefined}>
            <input className={`input ${entrySubmitted && !entryValue.trim() ? 'border-exclude ring-1 ring-exclude' : ''}`}
              placeholder="e.g. Empirical Study" value={entryValue} autoFocus
              onChange={e => setEntryValue(e.target.value)} />
          </FormField>
          <button className="btn-primary w-full justify-center mt-2"
            disabled={addEntryMutation.isPending} onClick={submitAddEntry}>
            Add Entry
          </button>
        </Modal>
      )}

      {modal?.kind === 'confirm-delete-entry' && (
        <ConfirmDialog
          message="Remove this taxonomy entry? This cannot be undone."
          onConfirm={() => { delEntryMutation.mutate(modal.id); setModal(null) }}
          onCancel={() => setModal(null)}
        />
      )}
    </div>
  )
}

// ── Search Strings Tab ────────────────────────────────────────────────────────

function SearchStringsTab({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const { data: strings = [] } = useQuery({ queryKey: ['search-strings', pid], queryFn: () => getSearchStrings(pid) })
  const [modal, setModal] = useState<{ mode: 'add' | 'edit'; id?: number } | null>(null)
  const [form, setForm] = useState<{ db_name: string; query_string: string; filter_settings: string; search_date: string }>({ db_name: DATABASES[0].key, query_string: '', filter_settings: '', search_date: '' })
  const [submitted, setSubmitted] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  const addMutation = useMutation({
    mutationFn: () => addSearchString(pid, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['search-strings', pid] }); setModal(null); setSubmitted(false) },
  })
  const updateMutation = useMutation({
    mutationFn: () => updateSearchString(pid, modal!.id!, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['search-strings', pid] }); setModal(null); setSubmitted(false) },
  })
  const delMutation = useMutation({
    mutationFn: (id: number) => deleteSearchString(pid, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['search-strings', pid] }),
  })

  // Databases already configured (for dedup check)
  const usedKeys = strings.map(s => s.db_name)

  const openAdd = () => {
    // Pre-select first database not yet used
    const firstAvailable = DATABASES.find(d => !usedKeys.includes(d.key))?.key ?? DATABASES[0].key
    setForm({ db_name: firstAvailable, query_string: '', filter_settings: '', search_date: '' })
    setSubmitted(false)
    setModal({ mode: 'add' })
  }
  const openEdit = (s: any) => {
    setForm({ db_name: s.db_name, query_string: s.query_string ?? '', filter_settings: s.filter_settings ?? '', search_date: s.search_date ?? '' })
    setSubmitted(false)
    setModal({ mode: 'edit', id: s.id })
  }
  const submit = () => {
    setSubmitted(true)
    if (!form.db_name || !form.query_string.trim()) return
    modal?.mode === 'add' ? addMutation.mutate() : updateMutation.mutate()
  }

  // For the add modal: only show databases not yet configured
  const availableDbs = modal?.mode === 'edit'
    ? DATABASES  // when editing, show all (the current db is already in the list)
    : DATABASES.filter(d => !usedKeys.includes(d.key) || d.key === form.db_name)

  return (
    <div className="max-w-2xl">
      <Card>
        <CardHeader title="Database Search Strings"
          action={usedKeys.length < DATABASES.length
            ? <button className="btn-secondary text-xs" onClick={openAdd}>+ Add</button>
            : null} />
        {strings.length === 0
          ? <EmptyState icon="—" message="No search strings defined." />
          : strings.map(s => (
            <div key={s.id} className="py-4 border-b border-border last:border-0">
              <div className="flex items-start justify-between gap-3">
                {/* Logo only — no redundant text label */}
                <div className="shrink-0 flex items-center" style={{ minWidth: 140 }}>
                  <DatabaseBadge dbKey={s.db_name} size="lg" />
                </div>
                <div className="flex-1 min-w-0">
                  {s.query_string
                    ? <p className="text-xs font-mono text-gray-600 bg-gray-50 p-2 rounded break-all leading-relaxed">{s.query_string}</p>
                    : <p className="text-xs text-gray-400 italic">No query string</p>}
                  <div className="flex gap-4 mt-1.5">
                    {s.filter_settings && <span className="text-xs text-gray-400">Filter: {s.filter_settings}</span>}
                    {s.search_date && <span className="text-xs text-gray-400">Searched: {s.search_date}</span>}
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button className="btn-secondary text-xs px-2 py-1" onClick={() => openEdit(s)}>Edit</button>
                  <button className="btn-danger text-xs px-2 py-1" onClick={() => setConfirmDelete(s.id)}>Remove</button>
                </div>
              </div>
            </div>
          ))}
      </Card>

      {confirmDelete !== null && (
        <ConfirmDialog
          message="Remove this search string entry? This cannot be undone."
          onConfirm={() => { delMutation.mutate(confirmDelete); setConfirmDelete(null) }}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      {modal && (
        <Modal title={modal.mode === 'add' ? 'Add Search String' : 'Edit Search String'}
          onClose={() => setModal(null)} onEnter={submit} width="max-w-2xl">
          <FormField label="Database" required error={submitted && !form.db_name ? 'Select a database' : undefined}>
            <select className="select" value={form.db_name}
              onChange={e => setForm(f => ({ ...f, db_name: e.target.value }))}>
              {availableDbs.map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
            </select>
          </FormField>
          <FormField label="Query String" required error={submitted && !form.query_string.trim() ? 'Query string is required' : undefined}>
            <textarea className={`textarea font-mono text-xs ${submitted && !form.query_string.trim() ? 'border-exclude ring-1 ring-exclude' : ''}`}
              rows={5} value={form.query_string}
              placeholder={'TITLE-ABS-KEY( "your terms" )'}
              onChange={e => setForm(f => ({ ...f, query_string: e.target.value }))} />
          </FormField>
          <FormField label="Filter Settings">
            <input className="input" placeholder="e.g. Computer Science, Journal Articles" value={form.filter_settings}
              onChange={e => setForm(f => ({ ...f, filter_settings: e.target.value }))} />
          </FormField>
          <FormField label="Search Date">
            <input type="date" className="input" value={form.search_date}
              onChange={e => setForm(f => ({ ...f, search_date: e.target.value }))} />
          </FormField>
          <button className="btn-primary w-full justify-center mt-2"
            disabled={addMutation.isPending || updateMutation.isPending} onClick={submit}>
            {modal.mode === 'add' ? 'Add' : 'Save Changes'}
          </button>
        </Modal>
      )}
    </div>
  )
}
