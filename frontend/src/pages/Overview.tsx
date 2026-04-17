/** Overview — Project listing, creation, deletion, and replication package import. */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useProject } from '../App'
import { getProjects, createProject, getExportStats, getImportStats, getSearchStrings, deleteProject, importReplicationPackage } from '../api/client'
import { StatBar, StatCell, Card, CardHeader, EmptyState, Modal, FormField, ConfirmDialog } from '../components/ui'
import { DatabaseBadge } from '../components/databases'
import { useState, useRef } from 'react'
import type { Project } from '../api/types'

export default function Overview() {
  const { projectId, setProjectId } = useProject()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [form, setForm] = useState({ title: '', lead_researcher: '', description: '' })
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [importSuccess, setImportSuccess] = useState<string | null>(null)
  const importInputRef = useRef<HTMLInputElement>(null)

  const importMutation = useMutation({
    mutationFn: (file: File) => importReplicationPackage(file),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      setProjectId(data.id)
      setImportSuccess(`"${data.title}" imported successfully.`)
      setImportError(null)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Import failed.'
      setImportError(msg)
      setImportSuccess(null)
    },
  })

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
      // Auto-select the remaining project if only one is left
      const remaining = projects.filter(p => p.id !== id)
      if (remaining.length === 1) {
        setProjectId(remaining[0].id)
      } else if (projectId === id) {
        setProjectId(null)
      }
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
          <StatBar>
            <StatCell label="Retrieved"      value={stats.total_retrieved} />
            <StatCell label="Unique"         value={stats.total_unique} />
            <StatCell label="Duplicates"     value={stats.total_duplicates} color="uncertain" />
            <StatCell label="Open Conflicts" value={stats.open_conflicts} color={stats.open_conflicts > 0 ? 'exclude' : 'navy'} />
            <StatCell label="Screening Incl." value={stats.screening_included}
              sub={`${stats.screening_excluded} excl. · ${stats.screening_undecided} open`}
              color="include" />
            <StatCell label="Full-Text Incl." value={stats.fulltext_included}
              sub={`${stats.fulltext_excluded} excluded`}
              color="include" />
          </StatBar>

          {configuredDbs.length > 0 && (
            <div className="card py-4 px-5 flex items-center gap-5 flex-wrap">
              <span className="text-xs font-semibold text-ink-muted uppercase tracking-label shrink-0">Databases</span>
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
          action={
            <div className="flex gap-2 items-center">
              <input
                ref={importInputRef}
                type="file"
                accept=".zip"
                className="hidden"
                onChange={e => {
                  const file = e.target.files?.[0]
                  if (file) {
                    setImportError(null)
                    setImportSuccess(null)
                    importMutation.mutate(file)
                  }
                  e.target.value = ''
                }}
              />
              <button
                className="btn-secondary"
                disabled={importMutation.isPending}
                onClick={() => importInputRef.current?.click()}
              >
                {importMutation.isPending ? 'Importing…' : '↑ Import Package'}
              </button>
              <button className="btn-primary" onClick={openCreate}>+ New Project</button>
            </div>
          }
        />
        {importError && (
          <div className="mx-1 mb-2 px-3 py-2 rounded bg-red-50 border border-red-200 text-xs text-red-700">{importError}</div>
        )}
        {importSuccess && (
          <div className="mx-1 mb-2 px-3 py-2 rounded bg-green-50 border border-green-200 text-xs text-green-700">{importSuccess}</div>
        )}
        {projects.length === 0 ? (
          <EmptyState
            icon="—"
            message="No projects yet. Create your first SLR project to get started."
            action={<button className="btn-primary" onClick={openCreate}>Create Project</button>}
          />
        ) : (
          <div className="divide-y divide-rule">
            {projects.map(p => (
              <div key={p.id} className="py-3 flex items-center justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    {p.id === projectId && (
                      <span className="text-2xs bg-accent text-white px-1.5 py-0.5 rounded font-bold shrink-0 leading-none">
                        Active
                      </span>
                    )}
                    <p className="text-sm font-semibold text-ink truncate font-display">{p.title}</p>
                  </div>
                  <p className="text-xs text-ink-muted">
                    {p.lead_researcher} · {new Date(p.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex gap-1.5 items-center shrink-0">
                  {p.id !== projectId && (
                    <button className="btn-primary btn-sm" onClick={() => setProjectId(p.id)}>
                      Switch
                    </button>
                  )}
                  <button className="btn-secondary btn-sm" onClick={() => { setProjectId(p.id); navigate('/setup') }}>
                    Setup
                  </button>
                  <button className="btn-danger btn-sm" onClick={() => setConfirmDeleteId(p.id)}>
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
