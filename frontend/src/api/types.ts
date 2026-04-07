export interface Project {
  id: number
  title: string
  description?: string
  lead_researcher: string
  created_at: string
  methodology: string
  qa_high_threshold: number
  qa_medium_threshold: number
  post_year_threshold: number
}

export interface Reviewer {
  id: number
  project_id: number
  name: string
  email?: string
  role: string // R1, R2, ...
}

export interface InclusionCriterion {
  id: number
  project_id: number
  label: string
  description: string
  phase: string
}

export interface ExclusionCriterion {
  id: number
  project_id: number
  label: string
  description: string
  phase: string
}

export interface QACriterion {
  id: number
  project_id: number
  label: string
  description: string
  max_score: number
}

export interface TaxonomyEntry {
  id: number
  project_id: number
  taxonomy_type: string
  value: string
  sort_order: number
}

export interface DatabaseSearchString {
  id: number
  project_id: number
  db_name: string
  query_string?: string
  filter_settings?: string
  search_date?: string
}

export interface Paper {
  id: number
  project_id: number
  citekey: string
  doi?: string
  title: string
  authors?: string
  year?: number
  venue?: string
  abstract?: string
  keywords?: string
  entry_type?: string
  source: string
  dedup_status: string
  language?: string
  full_text_url?: string
  full_text_inaccessible: boolean
  created_at: string
  // Enriched fields from list endpoint
  final_decision?: FinalDecision | null
  reviewer_decision_count?: number
  decisions?: ReviewerDecision[]
}

export interface ReviewerDecision {
  id: number
  project_id: number
  paper_id: number
  reviewer_id: number
  phase: string
  decision: string // I, E, U
  criterion_label?: string
  rationale?: string
  timestamp: string
  source_file?: string
}

export interface FinalDecision {
  id: number
  project_id: number
  paper_id: number
  phase: string
  decision: string
  resolution_method?: string
  resolution_note?: string
  resolved_by_reviewer_id?: number
  timestamp: string
}

export interface ConflictLog {
  id: number
  project_id: number
  paper_id: number
  phase: string
  r1_reviewer_id?: number
  r2_reviewer_id?: number
  r1_decision?: string
  r2_decision?: string
  r1_rationale?: string
  r2_rationale?: string
  resolved: boolean
  resolution?: string
  resolution_method?: string
  resolved_by_reviewer_id?: number
  resolved_at?: string
  created_at: string
  // Enriched
  paper_title?: string
  paper_citekey?: string
}

export interface KappaResult {
  kappa: number
  kappa_ci_lower: number
  kappa_ci_upper: number
  pabak: number
  observed_agreement: number
  n_papers: number
  n_agree_include: number
  n_agree_exclude: number
  n_disagree: number
  interpretation: string
  r1_name: string
  r2_name: string
  phase: string
}

export interface ImportStats {
  by_source: Record<string, { total: number; original: number; duplicate: number }>
  total_papers: number
  total_original: number
  total_duplicates: number
}

export interface ExportStats {
  total_retrieved: number
  total_unique: number
  total_duplicates: number
  screening_included: number
  screening_excluded: number
  screening_undecided: number
  fulltext_included: number
  fulltext_excluded: number
  open_conflicts: number
}

export interface SnowballingIteration {
  id: number
  project_id: number
  iteration_number: number
  iteration_type: string // forward, backward
  is_saturated: boolean
  saturation_confirmed: boolean
  created_at: string
  paper_count: number
  included_count: number
}

export interface QAScoreEntry {
  criterion_id: number
  label: string
  description: string
  max_score: number
  score: number | null
}

export interface QAPaperResult {
  paper_id: number
  paper_title: string
  paper_authors?: string
  paper_year?: number
  paper_source: string
  scores: QAScoreEntry[]
  total_score: number
  max_score: number
  percentage: number
  quality_level: 'high' | 'medium' | 'low'
  fully_scored: boolean
}

export interface QASummary {
  criteria: { id: number; label: string; description: string; max_score: number }[]
  papers: QAPaperResult[]
  max_total: number
}
