import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useProject } from '../App'
import { getProjects, createProject, getExportStats, getImportStats } from '../api/client'
import { StatCard, Card, CardHeader, EmptyState, Modal, FormField, ConfirmDialog } from '../components/ui'
import { DatabaseBadge, DATABASES } from '../components/databases'
import { useState } from 'react'
import type { Project } from '../api/types'

export default function Overview() {
  const { projectId, setProjectId } = useProject()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [form, setForm] = useState({ title: '', lead_researcher: '', description: '' })

  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: getProjects })

  const { data: stats } = useQuery({
    queryKey: ['export-stats', projectId],
    queryFn: () => getExportStats(projectId!),
    enabled: !!projectId,
  })

  const { data: importStats } = useQuery({
    queryKey: ['import-stats', projectId],
    queryFn: () => getImportStats(projectId!),
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

  const activeProject = projects.find(p => p.id === projectId)

  const openCreate = () => { setForm({ title: '', lead_researcher: '', description: '' }); setSubmitted(false); setShowCreate(true) }
  const submitCreate = () => {
    setSubmitted(true)
    if (!form.title || !form.lead_researcher) return
    createMutation.mutate(form)
  }

  // Databases used in this project (from import stats)
  const usedDbs = importStats ? Object.keys(importStats.by_source) : []
  const knownDbs = usedDbs.filter(k => DATABASES.some(d => d.key === k))
  const unknownDbs = usedDbs.filter(k => !DATABASES.some(d => d.key === k))

  return (
    <div className="space-y-6">
      {/* Active project stats */}
      {activeProject && stats && (
        <div className="space-y-3">
          <p className="section-title">Active Project — {activeProject.title}</p>

          {/* Row 1: 6 stat boxes */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard label="Retrieved"          value={stats.total_retrieved} />
            <StatCard label="Unique"             value={stats.total_unique}    color="info" />
            <StatCard label="Duplicates"         value={stats.total_duplicates} color="uncertain" />
            <StatCard label="Open Conflicts"     value={stats.open_conflicts}  color={stats.open_conflicts > 0 ? 'exclude' : 'navy'} />
            <StatCard
              label="Screening Included"
              value={stats.screening_included}
              sub={`${stats.screening_excluded} excl · ${stats.screening_undecided} undec`}
              color="include"
            />
            <StatCard
              label="Full-text Included"
              value={stats.fulltext_included}
              sub={`${stats.fulltext_excluded} excluded`}
              color="include"
            />
          </div>

          {/* Row 2: database logos */}
          {usedDbs.length > 0 && (
            <div className="card py-4 px-5 flex items-center gap-5 flex-wrap">
              <span className="text-xs font-semibold text-navy-muted uppercase tracking-wider shrink-0">Databases</span>
              <div className="flex items-center gap-6 flex-wrap">
                {knownDbs.map(k => <DatabaseBadge key={k} dbKey={k} size="lg" />)}
                {unknownDbs.map(k => <DatabaseBadge key={k} dbKey={k} size="lg" />)}
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
              <div key={p.id} className="py-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-navy">{p.title}</p>
                  <p className="text-xs text-gray-400">
                    {p.lead_researcher} · {new Date(p.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex gap-2 items-center">
                  {p.id === projectId ? (
                    <span className="phase-badge bg-blue-50 text-info border border-blue-200 font-semibold">Active</span>
                  ) : (
                    <button className="btn-primary text-xs" onClick={() => setProjectId(p.id)}>
                      Switch to this project
                    </button>
                  )}
                  <button className="btn-secondary text-xs" onClick={() => { setProjectId(p.id); navigate('/setup') }}>
                    Setup
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
    </div>
  )
}
