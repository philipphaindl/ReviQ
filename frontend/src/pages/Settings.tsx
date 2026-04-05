import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useProject } from '../App'
import {
  getProject, updateProject,
  getReviewers, addReviewer, deleteReviewer,
  getInclusionCriteria, addInclusionCriterion, updateInclusionCriterion, deleteInclusionCriterion,
  getExclusionCriteria, addExclusionCriterion, updateExclusionCriterion, deleteExclusionCriterion,
  getQACriteria, addQACriterion, updateQACriterion, deleteQACriterion,
  getTaxonomy, addTaxonomyEntry, deleteTaxonomyEntry,
  getSearchStrings, addSearchString, updateSearchString, deleteSearchString,
} from '../api/client'
import { Card, CardHeader, Modal, FormField, EmptyState } from '../components/ui'

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
  const mutation = useMutation({
    mutationFn: (data: any) => updateProject(pid, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project', pid] }); setForm({}) },
  })

  if (!project) return null
  const val = (key: string) => (key in form ? form[key] : (project as any)[key])
  const save = () => Object.keys(form).length > 0 && mutation.mutate(form)

  return (
    <div className="max-w-xl space-y-4">
      <Card>
        <CardHeader title="Project Details" />
        <FormField label="Title">
          <input className="input" value={val('title') as string}
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
        <button className="btn-primary" disabled={mutation.isPending || Object.keys(form).length === 0} onClick={save}>
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

  const addMutation = useMutation({
    mutationFn: () => addReviewer(pid, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['reviewers', pid] }); setModal(false); setForm({ name: '', email: '', role: 'R2' }) },
  })
  const deleteMutation = useMutation({
    mutationFn: (rid: number) => deleteReviewer(pid, rid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reviewers', pid] }),
  })

  const usedRoles = reviewers.map(r => r.role)
  const availableRoles = ROLES.filter(r => !usedRoles.includes(r))
  const submit = () => form.name && addMutation.mutate()

  return (
    <div className="max-w-xl">
      <Card>
        <CardHeader
          title="Reviewers (max 5)"
          action={reviewers.length < 5
            ? <button className="btn-secondary text-xs" onClick={() => setModal(true)}>+ Add</button>
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
                  <button className="btn-danger text-xs px-2 py-1" onClick={() => deleteMutation.mutate(r.id)}>Remove</button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {modal && (
        <Modal title="Add Reviewer" onClose={() => setModal(false)} onEnter={submit}>
          <FormField label="Name">
            <input className="input" value={form.name} autoFocus
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
            disabled={!form.name || addMutation.isPending} onClick={submit}>
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

  const openAdd = (type: 'add-i' | 'add-e') => {
    setForm({ label: '', description: '', phase: 'screening' })
    setModal({ type })
  }
  const openEdit = (type: 'edit-i' | 'edit-e', c: any) => {
    setForm({ label: c.label, description: c.description, phase: c.phase })
    setModal({ type, id: c.id })
  }
  const close = () => setModal(null)

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
              onEdit={() => openEdit('edit-i', c)} onDelete={() => delI.mutate(c.id)} />
          ))}
      </Card>

      <Card>
        <CardHeader title="Exclusion Criteria"
          action={<button className="btn-secondary text-xs" onClick={() => openAdd('add-e')}>+ Add</button>} />
        {exclusions.length === 0
          ? <EmptyState icon="—" message="No exclusion criteria defined." />
          : exclusions.map(c => (
            <CriterionRow key={c.id} label={c.label} description={c.description} badge={`Phase: ${c.phase}`}
              onEdit={() => openEdit('edit-e', c)} onDelete={() => delE.mutate(c.id)} />
          ))}
      </Card>

      {modal && (
        <Modal
          title={isAdd
            ? (isInclusion ? 'Add Inclusion Criterion' : 'Add Exclusion Criterion')
            : (isInclusion ? 'Edit Inclusion Criterion' : 'Edit Exclusion Criterion')}
          onClose={close}
          onEnter={submit}
        >
          <FormField label="Label (e.g. I1 or E3)">
            <input className="input" placeholder="I1" value={form.label} autoFocus
              onChange={e => setForm(f => ({ ...f, label: e.target.value }))} />
          </FormField>
          <FormField label="Description">
            <textarea className="textarea" rows={3} value={form.description}
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
            disabled={!form.label || !form.description || isPending} onClick={submit}>
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

  const totalMax = criteria.reduce((sum, c) => sum + c.max_score, 0)

  const openAdd = () => { setForm({ label: '', description: '', max_score: 1.0 }); setModal({ mode: 'add' }) }
  const openEdit = (c: any) => { setForm({ label: c.label, description: c.description, max_score: c.max_score }); setModal({ mode: 'edit', id: c.id }) }
  const close = () => setModal(null)

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
                <button className="btn-danger text-xs px-2 py-1" onClick={() => delMutation.mutate(c.id)}>Remove</button>
              </div>
            </div>
          ))}
      </Card>

      {modal && (
        <Modal title={modal.mode === 'add' ? 'Add QA Criterion' : 'Edit QA Criterion'}
          onClose={close} onEnter={submit}>
          <FormField label="Label (e.g. QA1)">
            <input className="input" placeholder="QA1" value={form.label} autoFocus
              onChange={e => setForm(f => ({ ...f, label: e.target.value }))} />
          </FormField>
          <FormField label="Description / Question">
            <textarea className="textarea" rows={3} value={form.description}
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
            disabled={!form.label || !form.description || isPending} onClick={submit}>
            {modal.mode === 'add' ? 'Add Criterion' : 'Save Changes'}
          </button>
        </Modal>
      )}
    </div>
  )
}

// ── Taxonomies Tab ────────────────────────────────────────────────────────────

const TAXONOMY_TYPES = [
  { key: 'research_type',    label: 'Research Type'    },
  { key: 'contribution_type', label: 'Contribution Type' },
  { key: 'usage_scenario',   label: 'Usage Scenario'   },
]

function TaxonomiesTab({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const [activeType, setActiveType] = useState(TAXONOMY_TYPES[0].key)
  const [newValue, setNewValue] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')

  const { data: entries = [] } = useQuery({
    queryKey: ['taxonomy', pid, activeType],
    queryFn: () => getTaxonomy(pid, activeType),
  })

  const addMutation = useMutation({
    mutationFn: () => addTaxonomyEntry(pid, activeType, newValue),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['taxonomy', pid, activeType] }); setNewValue('') },
  })
  const editMutation = useMutation({
    mutationFn: ({ id, value }: { id: number; value: string }) =>
      // Taxonomy update: delete + re-add (the API only has delete; we simulate edit)
      deleteTaxonomyEntry(pid, id).then(() => addTaxonomyEntry(pid, activeType, value)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['taxonomy', pid, activeType] }); setEditingId(null) },
  })
  const delMutation = useMutation({
    mutationFn: (id: number) => deleteTaxonomyEntry(pid, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['taxonomy', pid, activeType] }),
  })

  const startEdit = (id: number, value: string) => { setEditingId(id); setEditValue(value) }
  const confirmEdit = (id: number) => editValue.trim() && editMutation.mutate({ id, value: editValue.trim() })
  const cancelEdit = () => setEditingId(null)

  return (
    <div className="max-w-xl">
      <div className="flex gap-2 mb-4">
        {TAXONOMY_TYPES.map(t => (
          <button key={t.key} onClick={() => setActiveType(t.key)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md border transition-colors ${activeType === t.key ? 'bg-info text-white border-info' : 'bg-white text-navy-muted border-border hover:border-navy-muted'}`}>
            {t.label}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader title={TAXONOMY_TYPES.find(t => t.key === activeType)?.label ?? ''} />
        {entries.length === 0
          ? <p className="text-xs text-gray-400 py-2 mb-4">No entries yet. Add below.</p>
          : (
            <div className="divide-y divide-border mb-4">
              {entries.map(e => (
                <div key={e.id} className="py-2 flex items-center gap-2">
                  {editingId === e.id ? (
                    <>
                      <input className="input flex-1" value={editValue} autoFocus
                        onChange={ev => setEditValue(ev.target.value)}
                        onKeyDown={ev => { if (ev.key === 'Enter') confirmEdit(e.id); if (ev.key === 'Escape') cancelEdit() }} />
                      <button className="btn-primary text-xs px-2 py-1 shrink-0"
                        disabled={editMutation.isPending} onClick={() => confirmEdit(e.id)}>Save</button>
                      <button className="btn-secondary text-xs px-2 py-1 shrink-0" onClick={cancelEdit}>Cancel</button>
                    </>
                  ) : (
                    <>
                      <span className="text-sm text-navy flex-1">{e.value}</span>
                      <button className="btn-secondary text-xs px-2 py-1 shrink-0" onClick={() => startEdit(e.id, e.value)}>Edit</button>
                      <button className="btn-danger text-xs px-2 py-1 shrink-0" onClick={() => delMutation.mutate(e.id)}>Remove</button>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        <div className="flex gap-2">
          <input className="input" placeholder="New entry" value={newValue}
            onChange={e => setNewValue(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && newValue.trim() && addMutation.mutate()} />
          <button className="btn-primary shrink-0" disabled={!newValue.trim() || addMutation.isPending}
            onClick={() => addMutation.mutate()}>Add</button>
        </div>
      </Card>
    </div>
  )
}

// ── Search Strings Tab ────────────────────────────────────────────────────────

function SearchStringsTab({ pid }: { pid: number }) {
  const qc = useQueryClient()
  const { data: strings = [] } = useQuery({ queryKey: ['search-strings', pid], queryFn: () => getSearchStrings(pid) })
  const [modal, setModal] = useState<{ mode: 'add' | 'edit'; id?: number } | null>(null)
  const [form, setForm] = useState({ db_name: '', query_string: '', filter_settings: '', search_date: '' })

  const addMutation = useMutation({
    mutationFn: () => addSearchString(pid, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['search-strings', pid] }); setModal(null) },
  })
  const updateMutation = useMutation({
    mutationFn: () => updateSearchString(pid, modal!.id!, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['search-strings', pid] }); setModal(null) },
  })
  const delMutation = useMutation({
    mutationFn: (id: number) => deleteSearchString(pid, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['search-strings', pid] }),
  })

  const openEdit = (s: any) => {
    setForm({ db_name: s.db_name, query_string: s.query_string ?? '', filter_settings: s.filter_settings ?? '', search_date: s.search_date ?? '' })
    setModal({ mode: 'edit', id: s.id })
  }
  const submit = () => form.db_name && (modal?.mode === 'add' ? addMutation.mutate() : updateMutation.mutate())

  return (
    <div className="max-w-2xl">
      <Card>
        <CardHeader title="Database Search Strings"
          action={<button className="btn-secondary text-xs" onClick={() => { setForm({ db_name: '', query_string: '', filter_settings: '', search_date: '' }); setModal({ mode: 'add' }) }}>+ Add</button>} />
        {strings.length === 0
          ? <EmptyState icon="—" message="No search strings defined." />
          : strings.map(s => (
            <div key={s.id} className="py-3 border-b border-border last:border-0">
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-semibold text-navy uppercase tracking-wider">{s.db_name}</span>
                <div className="flex gap-1">
                  <button className="btn-secondary text-xs px-2 py-1" onClick={() => openEdit(s)}>Edit</button>
                  <button className="btn-danger text-xs px-2 py-1" onClick={() => delMutation.mutate(s.id)}>Remove</button>
                </div>
              </div>
              {s.query_string && <p className="text-xs font-mono text-gray-600 bg-gray-50 p-2 rounded break-all">{s.query_string}</p>}
              <div className="flex gap-4 mt-1">
                {s.filter_settings && <span className="text-xs text-gray-400">Filter: {s.filter_settings}</span>}
                {s.search_date && <span className="text-xs text-gray-400">Date: {s.search_date}</span>}
              </div>
            </div>
          ))}
      </Card>

      {modal && (
        <Modal title={modal.mode === 'add' ? 'Add Search String' : 'Edit Search String'}
          onClose={() => setModal(null)} onEnter={submit} width="max-w-2xl">
          <FormField label="Database Name">
            <input className="input" placeholder="e.g. scopus, ieee, acm, dblp" value={form.db_name} autoFocus
              onChange={e => setForm(f => ({ ...f, db_name: e.target.value }))} />
          </FormField>
          <FormField label="Query String">
            <textarea className="textarea font-mono text-xs" rows={5} value={form.query_string}
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
            disabled={!form.db_name || addMutation.isPending || updateMutation.isPending} onClick={submit}>
            {modal.mode === 'add' ? 'Add' : 'Save Changes'}
          </button>
        </Modal>
      )}
    </div>
  )
}
