import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useProject } from '../App'
import { getProjects, createProject, getExportStats, getImportStats, getSearchStrings, deleteProject, exportProjectUrl } from '../api/client'
import { StatCard, Card, CardHeader, EmptyState, Modal, FormField, ConfirmDialog } from '../components/ui'
import { DatabaseBadge } from '../components/databases'
import { useState } from 'react'
import type { Project } from '../api/types'

export default function Overview() {
  const { projectId, setProjectId } = useProject()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [form, setForm] = useState({ title: '', lead_researcher: '', description: '' })
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)

  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: getProjects })

  const { data: stats } = useQuery({
    queryKey: ['export-stats', projectId],
    queryFn: () => getExportStats(projectId!),
    enabled: !!projectId,
  })

  const { data: searchStrings = [] } = useQuery({
    queryKey: ['search-strings', projectId],
    queryFn: () => getSearchStrings(projectId!),
    enabled: !!projectId,
  })

  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: (p: Project) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      setProjectId(p.id)
      setShowCreate(false)
      setForm({ title: '', lead_researcher: '', description: '' })
      setSubmitted(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteProject(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      if (projectId === id) setProjectId(null)
      setConfirmDeleteId(null)
    },
  })

  const activeProject = projects.find(p => p.id === projectId)
  const confirmDeleteProject = projects.find(p => p.id === confirmDeleteId)

  const openCreate = () => { setForm({ title: '', lead_researcher: '', description: '' }); setSubmitted(false); setShowCreate(true) }
  const submitCreate = () => {
    setSubmitted(true)
    if (!form.title || !form.lead_researcher) return
    createMutation.mutate(form)
  }

  const configuredDbs = searchStrings.map(s => s.db_name)

  return (
    <div className="space-y-6">
      {/* Active project stats */}
      {activeProject && stats && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard label="Retrieved"          value={stats.total_retrieved} />
            <StatCard label="Unique"             value={stats.total_unique} />
            <StatCard label="Duplicates"         value={stats.total_duplicates} color="uncertain" />
            <StatCard label="Open Conflicts"     value={stats.open_conflicts}  color={stats.open_conflicts > 0 ? 'exclude' : 'navy'} />
            <StatCard
              label="Screening Included"
              value={stats.screening_included}
              sub={`${stats.screening_excluded} excluded · ${stats.screening_undecided} undecided`}
              color="include"
            />
            <StatCard
              label="Full-text Included"
              value={stats.fulltext_included}
              sub={`${stats.fulltext_excluded} excluded`}
              color="include"
            />
          </div>

          {configuredDbs.length > 0 && (
            <div className="card py-4 px-5 flex items-center gap-5 flex-wrap">
              <span className="text-xs font-semibold text-navy-muted uppercase tracking-wider shrink-0">Databases</span>
              <div className="flex items-center gap-3 flex-wrap">
                {configuredDbs.map(k => <DatabaseBadge key={k} dbKey={k} size="lg" />)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Project list */}
      <Card>
        <CardHeader
          title="Projects"
          action={<button className="btn-primary text-xs" onClick={openCreate}>+ New Project</button>}
        />
        {projects.length === 0 ? (
          <EmptyState
            icon="—"
            message="No projects yet. Create your first SLR project to get started."
            action={<button className="btn-primary" onClick={openCreate}>Create Project</button>}
          />
        ) : (
          <div className="divide-y divide-border">
            {projects.map(p => (
              <div key={p.id} className="py-3 flex items-center justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-navy">{p.title}</p>
                  <p className="text-xs text-gray-400">
                    {p.lead_researcher} · {new Date(p.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex gap-2 items-center shrink-0">
                  {p.id === projectId ? (
                    <span className="phase-badge bg-blue-50 text-info border border-blue-200 font-semibold">Active</span>
                  ) : (
                    <button className="btn-primary text-xs" onClick={() => setProjectId(p.id)}>
                      Switch
                    </button>
                  )}
                  <button className="btn-secondary text-xs" onClick={() => { setProjectId(p.id); navigate('/setup') }}>
                    Setup
                  </button>
                  <a
                    href={exportProjectUrl(p.id)}
                    download={`${p.title.replace(/\s+/g, '_')}_export.json`}
                    className="btn-secondary text-xs"
                  >
                    ↓ Export
                  </a>
                  <button className="btn-danger text-xs" onClick={() => setConfirmDeleteId(p.id)}>
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Create project modal */}
      {showCreate && (
        <Modal title="New SLR Project" onClose={() => setShowCreate(false)} onEnter={submitCreate}>
          <FormField label="Title" required error={submitted && !form.title ? 'Title is required' : undefined}>
            <input
              className={`input ${submitted && !form.title ? 'border-exclude ring-1 ring-exclude' : ''}`}
              placeholder="e.g. JVMTI Usage Patterns — A Systematic Literature Review"
              value={form.title}
              autoFocus
              onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
            />
          </FormField>
          <FormField label="Lead Researcher" required error={submitted && !form.lead_researcher ? 'Lead researcher is required' : undefined}>
            <input
              className={`input ${submitted && !form.lead_researcher ? 'border-exclude ring-1 ring-exclude' : ''}`}
              placeholder="Your name"
              value={form.lead_researcher}
              onChange={e => setForm(f => ({ ...f, lead_researcher: e.target.value }))}
            />
          </FormField>
          <FormField label="Description (optional)">
            <textarea
              className="textarea"
              rows={3}
              placeholder="Brief description of the research question"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            />
          </FormField>
          <button
            className="btn-primary w-full justify-center mt-2"
            disabled={createMutation.isPending}
            onClick={submitCreate}
          >
            {createMutation.isPending ? 'Creating…' : 'Create Project'}
          </button>
        </Modal>
      )}

      {/* Delete confirmation */}
      {confirmDeleteId !== null && confirmDeleteProject && (
        <ConfirmDialog
          message={`Permanently delete "${confirmDeleteProject.title}" and all its papers, decisions, and data? This cannot be undone.`}
          confirmLabel="Delete Project"
          onConfirm={() => deleteMutation.mutate(confirmDeleteId)}
          onCancel={() => setConfirmDeleteId(null)}
        />
      )}
    </div>
  )
}
