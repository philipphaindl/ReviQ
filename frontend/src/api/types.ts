// Mirrors the backend response schemas.

export interface Project {
  id: number
  title: string
  description?: string
  lead_researcher: string
  created_at: string
  methodology: string
  /** "slr" | "mlr". Read it through utils/reviewType.ts, never by comparing
   *  the string here — a project from an older backend has no value at all. */
  review_type?: string
  qa_high_threshold: number
  qa_medium_threshold: number
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
  short_label?: string
}

export interface ExclusionCriterion {
  id: number
  project_id: number
  label: string
  description: string
  phase: string
  short_label?: string
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
  results_count?: number | null
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
  venue_category_override?: string | null
  source: string
  // Optional so that Paper literals in tests and responses from an older
  // backend stay valid. Read them through src/components/streams.ts, which
  // supplies the legacy fallback — never test the `source` string directly.
  stream?: string
  discovery?: string
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

export interface ExtractionField {
  id: number
  project_id: number
  field_name: string
  field_label: string
  field_type: string  // text, number, boolean, dropdown
  options?: string    // JSON array string for dropdown
  sort_order: number
}

export interface ExtractionRecord {
  id: number
  project_id: number
  paper_id: number
  field_name: string
  field_value?: string
  extracted_by_reviewer_id: number
}

export interface ExtractionPaperRow {
  paper_id: number
  citekey: string
  title: string
  authors?: string
  year?: number
  source: string
  values: Record<string, string | undefined>
  filled: number
  total_fields: number
}

export interface ExtractionSummary {
  fields: ExtractionField[]
  papers: ExtractionPaperRow[]
}

// ── Grey literature: importing ────────────────────────────────────────────────

/** One retrieval this project made, as a scope that can be imported.
 *
 * A batch is one entry rather than one per run: `batch` issues a whole query
 * set together and that set is the unit a methods section describes.
 */
export interface Retrieval {
  kind: 'run' | 'batch'
  /** The run id or batch id `/import/grey/from-retrieval` takes. */
  scope_id: string
  queries: string[]
  /** Taken from the runs, never chosen by the user: the runs record which
   *  engine actually answered, and a hand-typed label could contradict them. */
  engines: string[]
  started_at_utc: string
  documents: number
  runs: number
  /** A run in this scope did not complete, so the corpus is partial — and the
   *  number it contributes to "records identified" is not the number the
   *  protocol asked for. */
  incomplete: boolean
  /** This project already imported this scope. Importing it again would count
   *  every record as `already_present` and change nothing. */
  already_imported: boolean
}

/** What an import of a grey package did, record by record.
 *
 * The four disjoint outcomes — `imported_unique`, `imported_duplicates`,
 * `already_present`, `skipped_no_citekey` — partition `total_in_package`
 * exactly. They are where a PRISMA "records identified" and "duplicates
 * removed" come from, so a record falling out of all of them could not be
 * reconciled by anyone reading the finished diagram.
 */
export interface GreyImportResult {
  grey_import_id: number
  /** From the package, via `grey_service.engine_of`. `mixed` when its runs
   *  used more than one. */
  engine: string
  scope?: { kind: string; id: string } | null
  queries: number
  total_in_package: number
  imported_unique: number
  imported_duplicates: number
  already_present: number
  skipped_no_citekey: number
  /** Imported and not readable: identified by the search, lost at retrieval
   *  rather than at screening. A PRISMA "reports not retrieved". */
  imported_unretrievable: number
  unretrievable_by_reason: Record<string, number>
  /** The package's own totals, so a disagreement surfaces here rather than in
   *  a finished diagram. */
  package_reported: { documents?: number | null; usable?: number | null }
  imported_citekeys: string[]
  duplicate_citekeys: string[]
  already_present_citekeys: string[]
}

// ── Grey literature: the dataset view ─────────────────────────────────────────

/** What makes one grey source citable and checkable.
 *
 * A URL alone does not survive the page changing, and grey literature changes
 * and disappears. The retrieval timestamp, the digest of the bytes read and
 * where those bytes are archived are the citation.
 */
export interface GreySource {
  id: number
  paper_id: number
  record_key: string
  canonical_url: string
  source_url?: string | null
  host?: string | null
  retrieved_at_utc?: string | null
  sha256?: string | null
  media_type?: string | null
  content_length?: number | null
  word_count?: number | null
  archive_filename?: string | null
  archive_offset?: number | null
  archive_record_id?: string | null
  /** ok | blocked | failed | empty | not_fetched */
  retrieval_status?: string | null
  /** Why, when it is not "ok": origin_unreachable, bot_challenge, not_found, … */
  retrieval_reason?: string | null
  search_observations: number
  best_rank?: number | null
}

/** The extracted body text, and the status it was extracted under.
 *
 * The two are one object on purpose (D31): text pulled from a page served
 * under a bot challenge is kept, because in the pilot corpus three such
 * records are genuine content — but two are the challenge page's own words.
 * Nothing separates them mechanically, so `retrieval_status` has to travel
 * with the text and be rendered beside it. Never display `text` alone.
 */
export interface GreyFullText {
  id: number
  paper_id: number
  text: string
  word_count?: number | null
  extractor?: string | null
  extraction_error?: string | null
  retrieval_status?: string | null
}

/** What a model said a figure shows. Generated text, not the source's words. */
export interface GreyFigureDescription {
  id: number
  grey_figure_id: number
  description?: string | null
  /** Kept verbatim: a reader has to be able to say what produced this sentence. */
  model?: string | null
  prompt?: string | null
  described_at_utc?: string | null
  error?: string | null
}

/** One image, as the page carried it. `alt_text` and `caption` are the source's
 *  own words about it; anything generated lives in `descriptions`. */
export interface GreyFigure {
  id: number
  paper_id: number
  raw_src?: string | null
  resolved_url?: string | null
  alt_text?: string | null
  caption?: string | null
  sha256?: string | null
  content_type?: string | null
  byte_size?: number | null
  archive_filename?: string | null
  archive_offset?: number | null
  archive_record_id?: string | null
  fetch_error?: string | null
  descriptions: GreyFigureDescription[]
}

export interface GreyRecord {
  paper_id: number
  source: GreySource
  /** null when the source yielded no bytes — distinct from an empty string,
   *  which would mean a page that genuinely carried no prose. */
  full_text: GreyFullText | null
  figures: GreyFigure[]
}
