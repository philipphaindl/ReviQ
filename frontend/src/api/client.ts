import axios from 'axios'
import type {
  Project, Reviewer, InclusionCriterion, ExclusionCriterion,
  QACriterion, TaxonomyEntry, DatabaseSearchString,
  Paper, KappaResult, ImportStats, ConflictLog, ExportStats,
  SnowballingIteration, QASummary,
} from './types'

const api = axios.create({ baseURL: '/api' })

// ── Projects ──────────────────────────────────────────────────────────────────

export const getProjects = () => api.get<Project[]>('/projects').then(r => r.data)
export const createProject = (data: Partial<Project>) => api.post<Project>('/projects', data).then(r => r.data)
export const getProject = (id: number) => api.get<Project>(`/projects/${id}`).then(r => r.data)
export const updateProject = (id: number, data: Partial<Project>) => api.put<Project>(`/projects/${id}`, data).then(r => r.data)
export const deleteProject = (id: number) => api.delete(`/projects/${id}`)
export const exportProjectUrl = (id: number) => `/api/projects/${id}/export`

// ── Reviewers ─────────────────────────────────────────────────────────────────

export const getReviewers = (pid: number) => api.get<Reviewer[]>(`/projects/${pid}/reviewers`).then(r => r.data)
export const addReviewer = (pid: number, data: Partial<Reviewer>) => api.post<Reviewer>(`/projects/${pid}/reviewers`, data).then(r => r.data)
export const updateReviewer = (pid: number, rid: number, data: Partial<Reviewer>) => api.put<Reviewer>(`/projects/${pid}/reviewers/${rid}`, data).then(r => r.data)
export const deleteReviewer = (pid: number, rid: number) => api.delete(`/projects/${pid}/reviewers/${rid}`)

// ── Criteria ──────────────────────────────────────────────────────────────────

export const getInclusionCriteria = (pid: number) => api.get<InclusionCriterion[]>(`/projects/${pid}/criteria/inclusion`).then(r => r.data)
export const addInclusionCriterion = (pid: number, data: Partial<InclusionCriterion>) => api.post<InclusionCriterion>(`/projects/${pid}/criteria/inclusion`, data).then(r => r.data)
export const updateInclusionCriterion = (pid: number, cid: number, data: Partial<InclusionCriterion>) => api.put<InclusionCriterion>(`/projects/${pid}/criteria/inclusion/${cid}`, data).then(r => r.data)
export const deleteInclusionCriterion = (pid: number, cid: number) => api.delete(`/projects/${pid}/criteria/inclusion/${cid}`)

export const getExclusionCriteria = (pid: number) => api.get<ExclusionCriterion[]>(`/projects/${pid}/criteria/exclusion`).then(r => r.data)
export const addExclusionCriterion = (pid: number, data: Partial<ExclusionCriterion>) => api.post<ExclusionCriterion>(`/projects/${pid}/criteria/exclusion`, data).then(r => r.data)
export const updateExclusionCriterion = (pid: number, cid: number, data: Partial<ExclusionCriterion>) => api.put<ExclusionCriterion>(`/projects/${pid}/criteria/exclusion/${cid}`, data).then(r => r.data)
export const deleteExclusionCriterion = (pid: number, cid: number) => api.delete(`/projects/${pid}/criteria/exclusion/${cid}`)

// ── QA Criteria ───────────────────────────────────────────────────────────────

export const getQACriteria = (pid: number) => api.get<QACriterion[]>(`/projects/${pid}/qa-criteria`).then(r => r.data)
export const addQACriterion = (pid: number, data: Partial<QACriterion>) => api.post<QACriterion>(`/projects/${pid}/qa-criteria`, data).then(r => r.data)
export const updateQACriterion = (pid: number, qid: number, data: Partial<QACriterion>) => api.put<QACriterion>(`/projects/${pid}/qa-criteria/${qid}`, data).then(r => r.data)
export const deleteQACriterion = (pid: number, qid: number) => api.delete(`/projects/${pid}/qa-criteria/${qid}`)

// ── Taxonomies ────────────────────────────────────────────────────────────────

export const getTaxonomyTypes = (pid: number) => api.get<string[]>(`/projects/${pid}/taxonomy-types`).then(r => r.data)
export const renameTaxonomyType = (pid: number, type: string, newType: string) => api.put(`/projects/${pid}/taxonomy-types/${encodeURIComponent(type)}`, { new_type: newType }).then(r => r.data)
export const deleteTaxonomyType = (pid: number, type: string) => api.delete(`/projects/${pid}/taxonomy-types/${encodeURIComponent(type)}`)

export const getTaxonomy = (pid: number, type: string) => api.get<TaxonomyEntry[]>(`/projects/${pid}/taxonomies/${type}`).then(r => r.data)
export const addTaxonomyEntry = (pid: number, type: string, value: string) => api.post<TaxonomyEntry>(`/projects/${pid}/taxonomies/${type}`, { value }).then(r => r.data)
export const deleteTaxonomyEntry = (pid: number, eid: number) => api.delete(`/projects/${pid}/taxonomies/${eid}`)

// ── Search Strings ────────────────────────────────────────────────────────────

export const getSearchStrings = (pid: number) => api.get<DatabaseSearchString[]>(`/projects/${pid}/search-strings`).then(r => r.data)
export const addSearchString = (pid: number, data: Partial<DatabaseSearchString>) => api.post<DatabaseSearchString>(`/projects/${pid}/search-strings`, data).then(r => r.data)
export const updateSearchString = (pid: number, sid: number, data: Partial<DatabaseSearchString>) => api.put<DatabaseSearchString>(`/projects/${pid}/search-strings/${sid}`, data).then(r => r.data)
export const deleteSearchString = (pid: number, sid: number) => api.delete(`/projects/${pid}/search-strings/${sid}`)

// ── Import ────────────────────────────────────────────────────────────────────

export const importBibFile = (pid: number, dbName: string, file: File) => {
  const formData = new FormData()
  formData.append('db_name', dbName)
  formData.append('file', file)
  return api.post<{
    db_name: string
    total_in_file: number
    imported_unique: number
    detected_duplicates: number
    imported_citekeys: string[]
    duplicate_citekeys: string[]
  }>(`/projects/${pid}/import/bib`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)
}

export const getImportStats = (pid: number) => api.get<ImportStats>(`/projects/${pid}/import/stats`).then(r => r.data)
export const getDuplicates = (pid: number) => api.get<Paper[]>(`/projects/${pid}/import/duplicates`).then(r => r.data)
export const overrideDedup = (pid: number, paperId: number) => api.post(`/projects/${pid}/papers/${paperId}/override-dedup`).then(r => r.data)

export const importReviewerDecisions = (pid: number, file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post(`/projects/${pid}/import/reviewer-decisions`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)
}

// ── Papers ────────────────────────────────────────────────────────────────────

export const getPapers = (pid: number, params?: Record<string, string>) =>
  api.get<Paper[]>(`/projects/${pid}/papers`, { params }).then(r => r.data)

export const getPaper = (pid: number, paperId: number) =>
  api.get<Paper>(`/projects/${pid}/papers/${paperId}`).then(r => r.data)

// ── Decisions ─────────────────────────────────────────────────────────────────

export const addDecision = (
  pid: number,
  paperId: number,
  data: { reviewer_id: number; phase: string; decision: string; criterion_label?: string; rationale?: string }
) => api.post(`/projects/${pid}/papers/${paperId}/decisions`, data).then(r => r.data)

export const getPaperDecisions = (pid: number, paperId: number, phase: string) =>
  api.get(`/projects/${pid}/papers/${paperId}/decisions`, { params: { phase } }).then(r => r.data)

// ── Conflicts ─────────────────────────────────────────────────────────────────

export const getConflicts = (pid: number, phase: string, resolved?: boolean) =>
  api.get<ConflictLog[]>(`/projects/${pid}/conflicts`, { params: { phase, resolved } }).then(r => r.data)

export const resolveConflict = (
  pid: number,
  conflictId: number,
  data: { resolved_by_reviewer_id: number; resolution: string; resolution_method: string; resolution_note?: string }
) => api.post(`/projects/${pid}/conflicts/${conflictId}/resolve`, data).then(r => r.data)

// ── Kappa ─────────────────────────────────────────────────────────────────────

export const getKappa = (pid: number, phase: string) =>
  api.get<KappaResult>(`/projects/${pid}/kappa`, { params: { phase } }).then(r => r.data)

// ── Export ────────────────────────────────────────────────────────────────────

export const getExportStats = (pid: number) =>
  api.get<ExportStats>(`/projects/${pid}/export/stats`).then(r => r.data)

export const exportDecisionsUrl = (pid: number, reviewerId: number, phase: string) =>
  `/api/projects/${pid}/export/decisions?reviewer_id=${reviewerId}&phase=${phase}`

export const exportBibtexUrl = (pid: number, phase: string, decision: string) =>
  `/api/projects/${pid}/export/bibtex?phase=${phase}&decision=${decision}`

// ── Paper update ──────────────────────────────────────────────────────────────

export const updatePaper = (pid: number, paperId: number, data: { full_text_url?: string; full_text_inaccessible?: boolean }) =>
  api.put(`/projects/${pid}/papers/${paperId}`, data).then(r => r.data)

// ── Snowballing ───────────────────────────────────────────────────────────────

export const getSnowballingIterations = (pid: number) =>
  api.get<SnowballingIteration[]>(`/projects/${pid}/snowballing`).then(r => r.data)

export const createSnowballingIteration = (pid: number, iteration_type: string) =>
  api.post<SnowballingIteration>(`/projects/${pid}/snowballing`, { iteration_type }).then(r => r.data)

export const updateSnowballingIteration = (pid: number, iterationId: number, iteration_type: string) =>
  api.put(`/projects/${pid}/snowballing/${iterationId}`, { iteration_type }).then(r => r.data)

export const deleteSnowballingIteration = (pid: number, iterationId: number) =>
  api.delete(`/projects/${pid}/snowballing/${iterationId}`)

export const confirmSaturation = (pid: number, iterationId: number) =>
  api.put(`/projects/${pid}/snowballing/${iterationId}/saturate`).then(r => r.data)

export const revokeSaturation = (pid: number, iterationId: number) =>
  api.put(`/projects/${pid}/snowballing/${iterationId}/unsaturate`).then(r => r.data)

export const importSnowballingBib = (pid: number, iterationId: number, file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post<{ source: string; imported_unique: number; detected_duplicates: number; imported_citekeys: string[] }>(
    `/projects/${pid}/snowballing/${iterationId}/import`,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  ).then(r => r.data)
}

// ── QA Scoring ────────────────────────────────────────────────────────────────

export const getQASummary = (pid: number) =>
  api.get<QASummary>(`/projects/${pid}/qa-summary`).then(r => r.data)

export const upsertQAScore = (
  pid: number,
  paperId: number,
  data: { reviewer_id: number; criterion_id: number; score: number; rationale?: string },
) => api.post(`/projects/${pid}/papers/${paperId}/qa-scores`, data).then(r => r.data)
