import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useProject } from '../App'
import { getProjects, createProject, getExportStats, getImportStats } from '../api/client'
import { StatCard, Card, CardHeader, EmptyState } from '../components/ui'
import { useState } from 'react'
import type { Project } from '../api/types'

export default function Overview() {
  const { projectId, setProjectId } = useProject()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title: '', lead_researcher: '', description: '' })

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: getProjects,
  })

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
    },
  })

  const activeProject = projects.find(p => p.id === projectId)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-navy">ReviQ</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Systematic Literature Review Workbench · Kitchenham &amp; Charters (2007)
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          + New Project
        </button>
      </div>

      {/* Active project stats */}
      {activeProject && stats && (
        <>
          <div>
            <p className="section-title">Active Project — {activeProject.title}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <StatCard label="Retrieved" value={stats.total_retrieved} />
              <StatCard label="Unique" value={stats.total_unique} color="info" />
              <StatCard label="Duplicates" value={stats.total_duplicates} color="uncertain" />
              <StatCard label="Open Conflicts" value={stats.open_conflicts} color={stats.open_conflicts > 0 ? 'exclude' : 'navy'} />
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
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
            {importStats && (
              <StatCard
                label="Databases"
                value={Object.keys(importStats.by_source).length}
                sub={`${importStats.total_original} unique papers`}
              />
            )}
          </div>
        </>
      )}

      {/* Project list */}
      <Card>
        <CardHeader
          title="Projects"
          action={
            <button className="btn-secondary text-xs" onClick={() => setShowCreate(true)}>
              + New
            </button>
          }
        />
        {projects.length === 0 ? (
          <EmptyState
            icon="—"
            message="No projects yet. Create your first SLR project to get started."
            action={
              <button className="btn-primary" onClick={() => setShowCreate(true)}>
                Create Project
              </button>
            }
          />
        ) : (
          <div className="divide-y divide-border">
            {projects.map(p => (
              <div key={p.id} className="py-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-navy">{p.title}</p>
                  <p className="text-xs text-gray-400">
                    {p.lead_researcher} · {p.methodology} · {new Date(p.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex gap-2">
                  {p.id === projectId ? (
                    <span className="phase-badge bg-blue-50 text-info border border-blue-200">Active</span>
                  ) : (
                    <button
                      className="btn-secondary text-xs"
                      onClick={() => setProjectId(p.id)}
                    >
                      Switch
                    </button>
                  )}
                  <button
                    className="btn-secondary text-xs"
                    onClick={() => { setProjectId(p.id); navigate('/setup') }}
                  >
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
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/30" onClick={() => setShowCreate(false)} />
          <div className="relative bg-white rounded-card shadow-xl max-w-md w-full mx-4">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <h3 className="font-semibold text-navy text-sm">New SLR Project</h3>
              <button onClick={() => setShowCreate(false)} className="text-gray-400 hover:text-navy text-lg">×</button>
            </div>
            <div className="px-5 py-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-navy-muted uppercase tracking-wider mb-1.5">Title</label>
                <input
                  className="input"
                  placeholder="e.g. JVMTI Usage Patterns — A Systematic Literature Review"
                  value={form.title}
                  onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-navy-muted uppercase tracking-wider mb-1.5">Lead Researcher</label>
                <input
                  className="input"
                  placeholder="Your name"
                  value={form.lead_researcher}
                  onChange={e => setForm(f => ({ ...f, lead_researcher: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-navy-muted uppercase tracking-wider mb-1.5">Description (optional)</label>
                <textarea
                  className="textarea"
                  rows={3}
                  placeholder="Brief description of the research question"
                  value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                />
              </div>
              <button
                className="btn-primary w-full justify-center"
                disabled={!form.title || !form.lead_researcher || createMutation.isPending}
                onClick={() => createMutation.mutate(form)}
              >
                {createMutation.isPending ? 'Creating…' : 'Create Project'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
