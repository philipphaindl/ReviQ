/**
 * Pure data transforms feeding the synthesis charts on the Results page.
 *
 * Kept side-effect free so they can be unit-tested without a DOM and reused
 * across the web charts and the PDF report data preparation.
 */

export type QualityBand = 'low' | 'medium' | 'high'

export interface QualityThresholds {
  medium: number  // percentage at or above which a paper is "medium"
  high: number    // percentage at or above which a paper is "high"
}

export const DEFAULT_QA_THRESHOLDS: QualityThresholds = { medium: 50, high: 75 }

export interface QAScoreBin {
  /** Inclusive lower bound, in percent. */
  lower: number
  /** Exclusive upper bound, in percent (the final bin treats 100 as inclusive). */
  upper: number
  /** Total papers in this bin (= low + medium + high). */
  count: number
  /**
   * Split-fill breakdown: how many of this bin's papers fall in each project
   * threshold band. A bin straddling a threshold yields counts in two bands,
   * which the chart renders as a stacked bar.
   */
  low: number
  medium: number
  high: number
  /** Dominant band — the one with the most papers in this bin (ties go to the higher band). */
  band: QualityBand
  /** Paper identifiers contributing to this bin, in input order. */
  paperKeys: string[]
}

export interface QAScoreInput {
  key: string
  percentage: number
}

/**
 * Place each paper into one of N equal-width bins covering 0..100 %.
 * Defaults to 10 bins ([0,10), [10,20), … [90,100]). 100% is clamped into the
 * top bin so it isn't dropped. Each bin also records a per-band split
 * (low/medium/high) so a bin straddling a threshold can be rendered as a
 * stacked bar reflecting the actual classification of its papers.
 */
export function binQAScores(
  papers: QAScoreInput[],
  thresholds: QualityThresholds = DEFAULT_QA_THRESHOLDS,
  binCount: number = 10,
): QAScoreBin[] {
  const n = Math.max(1, Math.floor(binCount))
  const width = 100 / n
  const bins: QAScoreBin[] = []
  for (let i = 0; i < n; i++) {
    const lower = Math.round(i * width * 10) / 10
    const upper = Math.round((i + 1) * width * 10) / 10
    bins.push({
      lower, upper,
      count: 0, low: 0, medium: 0, high: 0,
      band: bandForBin(lower, thresholds),
      paperKeys: [],
    })
  }
  for (const p of papers) {
    if (p.percentage == null || Number.isNaN(p.percentage)) continue
    const clamped = Math.max(0, Math.min(100, p.percentage))
    let idx = Math.floor(clamped / width)
    if (idx >= n) idx = n - 1
    const bin = bins[idx]
    const band = bandForPercentage(clamped, thresholds)
    bin.count += 1
    bin[band] += 1
    bin.paperKeys.push(p.key)
  }
  // Refresh the "dominant band" annotation now that we know the actual split.
  for (const bin of bins) {
    if (bin.count === 0) continue
    const order: QualityBand[] = ['high', 'medium', 'low']
    bin.band = order.reduce((best, b) => (bin[b] > bin[best] ? b : best), order[0])
  }
  return bins
}

/**
 * Threshold band for a single percentage (used in tooltips and table coloring).
 * Matches the backend's project-level high/medium/low classification.
 */
export function bandForPercentage(pct: number, t: QualityThresholds = DEFAULT_QA_THRESHOLDS): QualityBand {
  if (pct >= t.high) return 'high'
  if (pct >= t.medium) return 'medium'
  return 'low'
}

/**
 * Conservative band assignment for a bin: uses the bin's lower edge so a bin
 * is only promoted to a higher band once it sits entirely at/above the threshold.
 */
export function bandForBin(binLowerPct: number, t: QualityThresholds = DEFAULT_QA_THRESHOLDS): QualityBand {
  return bandForPercentage(binLowerPct, t)
}

/** Summary statistics over a set of QA percentages. */
export interface QASummaryStats {
  n: number
  mean: number
  median: number
}

export function summarizeQAScores(papers: QAScoreInput[]): QASummaryStats {
  const values = papers
    .map(p => p.percentage)
    .filter(v => v != null && !Number.isNaN(v))
    .sort((a, b) => a - b)
  const n = values.length
  if (n === 0) return { n: 0, mean: 0, median: 0 }
  const mean = values.reduce((s, v) => s + v, 0) / n
  const median = n % 2 === 1
    ? values[(n - 1) / 2]
    : (values[n / 2 - 1] + values[n / 2]) / 2
  return { n, mean, median }
}

// ── Taxonomy / categorical aggregation ──────────────────────────────────────

export interface CategoryCount {
  value: string
  count: number
  /** Percentage of the total (0–100); 0 when totalPapers is 0. */
  percentage: number
}

export interface TaxonomyDistribution {
  /** taxonomy_type key as stored in the project (e.g. "contribution_type"). */
  key: string
  /** Human-readable label derived from the key. */
  label: string
  categories: CategoryCount[]
}

/** Title-case a snake_case taxonomy key for display. */
export function taxonomyLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

interface PaperLike {
  values: Record<string, string | undefined>
}

/**
 * Count occurrences of each known category for a given taxonomy_type across
 * the included paper set. Categories from the schema are always rendered —
 * unseen ones come back with count 0 so the chart shows the full taxonomy.
 * Values found in papers but absent from the schema are appended at the end.
 */
export function aggregateTaxonomy(
  papers: PaperLike[],
  taxonomyKey: string,
  schemaValues: string[],
): TaxonomyDistribution {
  const counts = new Map<string, number>()
  for (const v of schemaValues) counts.set(v, 0)
  for (const p of papers) {
    const raw = p.values[taxonomyKey]
    if (!raw) continue
    counts.set(raw, (counts.get(raw) ?? 0) + 1)
  }
  const totalPapers = papers.length
  const categories: CategoryCount[] = Array.from(counts.entries())
    .map(([value, count]) => ({
      value, count,
      percentage: percentageOf(count, totalPapers),
    }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
  return { key: taxonomyKey, label: taxonomyLabel(taxonomyKey), categories }
}

/**
 * Aggregate a single extraction field's unique values across papers.
 * Empty / missing values are skipped. Sort: count desc, then alphabetical.
 */
export function aggregateExtractionField(
  papers: PaperLike[],
  fieldName: string,
): CategoryCount[] {
  const counts = new Map<string, number>()
  for (const p of papers) {
    const raw = p.values[fieldName]
    if (raw == null || raw === '') continue
    counts.set(raw, (counts.get(raw) ?? 0) + 1)
  }
  const total = Array.from(counts.values()).reduce((s, n) => s + n, 0)
  return Array.from(counts.entries())
    .map(([value, count]) => ({
      value, count,
      percentage: percentageOf(count, total),
    }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
}

interface ExtractionFieldLike {
  field_name: string
  field_label: string
  field_type: string
  sort_order: number
  id: number
}

/**
 * Pick the first dropdown-style extraction field that is *not* a taxonomy
 * dimension. Chart 4 fans out from this field, and renders nothing if
 * no such field exists.
 */
export function pickFirstSelectField(
  fields: ExtractionFieldLike[],
  taxonomyKeys: string[],
): ExtractionFieldLike | null {
  const taxSet = new Set(taxonomyKeys)
  const sorted = [...fields].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
  return sorted.find(f => f.field_type === 'dropdown' && !taxSet.has(f.field_name)) ?? null
}

/**
 * Safe `count / total * 100` with a defensible behaviour at `total === 0`.
 *
 * Centralised so every percentage rendered in the Charts tab (donut labels,
 * legend rows, CSV exports, PDF report captions) shares one definition.
 * Rounded to `digits` decimal places — default 1, matching the manuscript's
 * established convention.
 */
export function percentageOf(count: number, total: number, digits: number = 1): number {
  if (!Number.isFinite(count) || !Number.isFinite(total) || total <= 0) return 0
  const raw = (count / total) * 100
  const factor = Math.pow(10, Math.max(0, digits))
  return Math.round(raw * factor) / factor
}

/**
 * URL-safe slug used in download filenames: lowercase, [a-z0-9] only,
 * separated by single dashes, trimmed of leading/trailing dashes. Empty
 * input collapses to "project".
 */
export function chartSlug(s: string): string {
  const cleaned = (s || '')
    .toString()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')   // strip combining diacritics
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return cleaned || 'project'
}

/** Format a Date as `YYYYMMDD` (UTC, so test outputs are stable). */
export function compactDate(d: Date = new Date()): string {
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth() + 1).padStart(2, '0')
  const day = String(d.getUTCDate()).padStart(2, '0')
  return `${y}${m}${day}`
}

/** Compose the canonical chart-export filename stem (no extension). */
export function chartFilename(projectTitle: string, chartId: string, when: Date = new Date()): string {
  return `reviq-${chartSlug(projectTitle)}-${chartSlug(chartId)}-${compactDate(when)}`
}

// ── Year + publication type ─────────────────────────────────────────────────

export interface YearCount { year: number; count: number }

/**
 * Group papers by publication year and return a continuous series with zero-
 * filled gaps so a 2018-2024 timeline always has seven points, not five.
 */
export function aggregatePublicationsPerYear(
  papers: Array<{ year?: number | null }>,
): YearCount[] {
  const counts = new Map<number, number>()
  for (const p of papers) {
    if (p.year == null) continue
    counts.set(p.year, (counts.get(p.year) ?? 0) + 1)
  }
  if (counts.size === 0) return []
  const years = [...counts.keys()].sort((a, b) => a - b)
  const out: YearCount[] = []
  for (let y = years[0]; y <= years[years.length - 1]; y++) {
    out.push({ year: y, count: counts.get(y) ?? 0 })
  }
  return out
}

// ── Venue type categorization (Issue 6) ─────────────────────────────────────

/**
 * Default venue-type categories that always appear in the donut legend, even
 * with zero counts. Order matters — it's the order the legend renders in.
 */
export const DEFAULT_VENUE_CATEGORIES = [
  'Journal',
  'Conference',
  'Workshop',
  'Other',
] as const

export type VenueCategory =
  | 'Journal'
  | 'Conference'
  | 'Workshop'
  | 'Book chapter'
  | 'Technical report'
  | 'Thesis'
  | 'Other'

// ── Known venue abbreviations ─────────────────────────────────────────────────
// These cover abbreviated journal/conference names commonly found in SLR BibTeX
// files where the full name isn't spelled out. All lowercase, non-alphanumeric
// stripped before matching.

const _JOURNAL_ABBREVS = new Set([
  'tse', 'jss', 'tosem', 'emse', 'ist', 'scp', 'stvr', 'rej', 'cacm',
  'toit', 'tods', 'tois', 'toplas', 'topl', 'tocs', 'jacm', 'tdsc',
  'tpds', 'tetc', 'tc', 'spej', 'spe', 'sosym', 'infsof', 'infsoft',
  'ase', // Automated Software Engineering (journal, not the conference)
])
const _CONFERENCE_ABBREVS = new Set([
  'icse', 'fse', 'esec', 'esecfse', 'issta', 'msr', 'saner', 'icsme',
  'icsm', 'ease', 'esem', 'scam', 'ssbse', 'csmr', 'wcre', 'icpc',
  'icst', 'tap', 'cbi', 'promise', 'mobilesoft', 'icmse',
  'issre', 'valuetools', 'mascots', 'qest', 'icpe', 'wosp', 'sipew',
  'icdcs', 'dsn', 'srds', 'edcc', 'prdc', 'ladc',
  'pldi', 'oopsla', 'ecoop', 'popl', 'sosp', 'osdi', 'eurosys', 'atc',
  'nsdi', 'sigcomm', 'infocom', 'icdcs',
  'sigkdd', 'kdd', 'sigmod', 'vldb', 'icde', 'pods', 'icdm',
  'aaai', 'ijcai', 'neurips', 'nips', 'icml', 'iclr',
  'cvpr', 'iccv', 'eccv', 'acl', 'emnlp', 'naacl', 'coling',
  'chi', 'cscw', 'uist', 'dis', 'ubicomp', 'percom',
  'ccs', 'ndss', 'usenixsec',
  'www', 'sigir', 'cikm', 'wsdm', 'recsys',
  'isca', 'asplos', 'micro', 'hpca', 'dac', 'cgo',
])
const _WORKSHOP_ABBREVS = new Set([
  'iwsm', 'chase', 'techdebt', 'satose', 'wbma', 'rsse',
])

function _normAbbrev(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, '')
}

/**
 * Map a paper's BibTeX entry to a venue-type category.
 * User-set `venue_category_override` is honoured before any auto-detection.
 * Auto-detection order:
 *   1. BibTeX entry_type → typed rules
 *   2. Venue-name keyword matching (full phrases)
 *   3. Known abbreviated venue identifiers (TSE, ICSE, …)
 *   4. Fallback: Other
 */
export function categorizeVenue(paper: {
  entry_type?: string | null
  venue?: string | null
  venue_category_override?: string | null
}): VenueCategory {
  // User-set override takes absolute priority.
  if (paper.venue_category_override) return paper.venue_category_override as VenueCategory

  const entry = (paper.entry_type ?? '').toLowerCase().trim()
  const venue = (paper.venue ?? '').toLowerCase()

  // Primary: BibTeX entry type rules.
  if (entry === 'article') return 'Journal'
  if (entry === 'inproceedings' || entry === 'conference') {
    if (venue.includes('workshop')) return 'Workshop'
    return 'Conference'
  }
  if (entry === 'incollection' || entry === 'inbook') return 'Book chapter'
  if (entry === 'techreport') return 'Technical report'
  if (entry === 'phdthesis' || entry === 'mastersthesis') return 'Thesis'

  // Fallback A: venue-name keyword matching (handles full long-form names).
  if (entry === '' || entry === 'misc' || entry === 'unpublished') {
    if (venue.includes('workshop')) return 'Workshop'
    if (
      venue.includes('proceedings') || venue.includes('conference') ||
      venue.includes('symposium') || venue.includes('colloquium') ||
      venue.includes(' meeting') || venue.includes('international conference') ||
      venue.includes('lecture notes') || venue.includes(' conf.') ||
      venue.includes('int. conf') || venue.includes('intl. conf') ||
      venue.includes(' symposia')
    ) return 'Conference'
    if (
      venue.includes('journal') || venue.includes('transactions') ||
      venue.includes(' letters') || venue.includes('magazine') ||
      venue.includes('review') || venue.includes('quarterly') ||
      venue.includes('annals') || venue.includes('practice and experience') ||
      /vol\.?\s*\d+.*issue\s*\d+/i.test(venue)
    ) return 'Journal'
    if (venue.includes('thesis') || venue.includes('dissertation')) return 'Thesis'
    if (
      venue.includes('technical report') || venue.includes('techreport') ||
      venue.includes('tech. rep')
    ) return 'Technical report'
    if (
      venue.includes('book chapter') || venue.includes('chapter in') ||
      venue.includes('in: ')
    ) return 'Book chapter'

    // Fallback B: abbreviated venue names (TSE, ICSE, etc.).
    const abbrev     = _normAbbrev(paper.venue ?? '')
    const abbrevBase = abbrev.replace(/\d+$/, '')
    if (_WORKSHOP_ABBREVS.has(abbrev)    || _WORKSHOP_ABBREVS.has(abbrevBase))    return 'Workshop'
    if (_CONFERENCE_ABBREVS.has(abbrev)  || _CONFERENCE_ABBREVS.has(abbrevBase))  return 'Conference'
    if (_JOURNAL_ABBREVS.has(abbrev)     || _JOURNAL_ABBREVS.has(abbrevBase))     return 'Journal'
  }

  return 'Other'
}

/**
 * Aggregate papers by venue category and return rows in legend display order:
 * the four "default" categories always present (zero-counts allowed), then
 * any extra categories that received counts. Within the extras, sort by
 * descending count then alphabetical for stability.
 */
export function aggregateVenueTypes(papers: Array<{
  entry_type?: string | null
  venue?: string | null
  venue_category_override?: string | null
}>): CategoryCount[] {
  const counts = new Map<string, number>()
  for (const cat of DEFAULT_VENUE_CATEGORIES) counts.set(cat, 0)
  for (const p of papers) {
    const cat = categorizeVenue(p)
    counts.set(cat, (counts.get(cat) ?? 0) + 1)
  }
  const total = papers.length
  const out: CategoryCount[] = []
  for (const cat of DEFAULT_VENUE_CATEGORIES) {
    out.push({ value: cat, count: counts.get(cat) ?? 0, percentage: percentageOf(counts.get(cat) ?? 0, total) })
  }
  const extras = Array.from(counts.entries())
    .filter(([k, n]) => !DEFAULT_VENUE_CATEGORIES.includes(k as any) && n > 0)
    .map(([value, count]): CategoryCount => ({
      value, count, percentage: percentageOf(count, total),
    }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
  return [...out, ...extras]
}

const PUB_TYPE_LABELS: Record<string, string> = {
  inproceedings: 'Conference',
  conference:    'Conference',
  article:       'Journal',
  incollection:  'Book chapter',
  inbook:        'Book chapter',
  book:          'Book',
  techreport:    'Tech report',
  phdthesis:     'PhD thesis',
  mastersthesis: 'MSc thesis',
  misc:          'Other',
  unpublished:   'Unpublished',
}

export function humanPublicationType(entryType?: string | null): string {
  if (!entryType) return 'Other'
  const norm = entryType.toLowerCase().trim()
  return PUB_TYPE_LABELS[norm] ?? norm.charAt(0).toUpperCase() + norm.slice(1)
}

/**
 * Count papers by BibTeX entry_type. Returns rows sorted descending by count
 * (then alphabetical for stability), with a percentage of the total.
 */
export function aggregatePublicationTypes(
  papers: Array<{ entry_type?: string | null }>,
): CategoryCount[] {
  const counts = new Map<string, number>()
  for (const p of papers) {
    const label = humanPublicationType(p.entry_type)
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  const total = Array.from(counts.values()).reduce((s, n) => s + n, 0)
  return Array.from(counts.entries())
    .map(([value, count]) => ({
      value, count,
      percentage: percentageOf(count, total),
    }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
}

// ── Abstract keyword extraction ───────────────────────────────────────────────

/** English function words + scientific/academic filler to exclude. */
const ABSTRACT_STOPWORDS = new Set<string>([
  // Articles & determiners
  'a','an','the','this','that','these','those','some','any','all','both','each',
  'every','either','neither','no','other','another','such',
  // Prepositions
  'in','on','at','to','of','for','with','by','from','as','into','over','under',
  'about','above','below','between','through','during','after','before','among',
  'around','against','within','without','along','toward','towards','upon','per',
  'via','than','since','until','across','beyond','despite','except','off','out',
  'up','down','whether',
  // Conjunctions
  'and','or','but','nor','so','yet','although','because','when','where','if',
  'unless','though','whereas','while',
  // Pronouns
  'i','me','my','we','our','us','you','your','he','him','his','she','her','it',
  'its','they','them','their','who','whom','what','which','whose',
  // Auxiliaries
  'is','are','was','were','be','been','being','have','has','had','do','does',
  'did','will','would','could','should','may','might','shall','can','must',
  // Adverbs
  'not','no','also','just','very','quite','rather','well','even','still','yet',
  'already','often','always','never','sometimes','usually','generally',
  'typically','commonly','specifically','particularly','especially','mainly',
  'mostly','largely','highly','widely','significantly','approximately',
  'relatively','respectively','previously','recently','currently','thus',
  'hence','therefore','however','moreover','furthermore','nevertheless',
  'otherwise','accordingly','consequently','additionally','meanwhile','still',
  // Academic/scientific filler
  'paper','papers','study','studies','approach','approaches','method','methods',
  'methodology','technique','techniques','result','results','finding','findings',
  'show','shows','shown','propose','proposes','proposed','present','presents',
  'presented','demonstrate','demonstrates','demonstrated','discuss','discusses',
  'discussed','analyze','analyzes','analyzed','analyse','analyses','analysed',
  'evaluate','evaluates','evaluated','investigate','investigates','investigated',
  'examine','examines','examined','consider','considers','considered',
  'describe','describes','described','introduce','introduces','introduced',
  'provide','provides','provided','give','gives','given','make','makes','made',
  'take','takes','taken','get','gets','based','using','used','use','uses',
  'work','works','working','new','different','various','first','second','third',
  'one','two','three','four','five','number','many','several','few','large',
  'small','high','low','good','best','better','important','significant',
  'effective','efficient','novel','existing','related','general','specific',
  'similar','common','main','key','real','actual','research','data','system',
  'systems','model','models','framework','problem','problems','solution',
  'solutions','application','applications','information','evaluation',
  'experiment','experiments','implementation','performance','process',
  'processes','type','types','case','cases','example','examples','level',
  'levels','way','ways','part','parts','form','forms','order','term','terms',
  'time','times','point','points','goal','goals','task','tasks','design',
  'designs','test','tests','testing','development','developed','develop',
  'compare','comparison','increase','decrease','improve','improvement',
  'achieve','require','include','includes','included','allow','allows',
  'enable','enables','support','supports','address','addresses','focus',
  'focuses','aim','aims','target','targets','measure','measures','reduce',
  'reduces','apply','applies','applied','code','program','programs',
  'language','languages','tool','tools',
])

/**
 * Extract unigrams and bigrams from paper abstracts, filtered by stopwords.
 * Returns top `topN` terms (bigrams appear only if count ≥ 2).
 */
export function aggregateAbstractKeywords(
  papers: Array<{ abstract?: string | null }>,
  topN = 20,
): CategoryCount[] {
  const total     = papers.length
  const unigrams  = new Map<string, number>()
  const bigrams   = new Map<string, number>()

  for (const p of papers) {
    const text   = (p.abstract ?? '').toLowerCase()
    const tokens = text.split(/[^a-z]+/).filter(t => t.length >= 3 && !ABSTRACT_STOPWORDS.has(t))

    for (const t of tokens) unigrams.set(t, (unigrams.get(t) ?? 0) + 1)

    // Bigrams from consecutive non-stopword tokens
    for (let i = 0; i < tokens.length - 1; i++) {
      const bg = `${tokens[i]} ${tokens[i + 1]}`
      bigrams.set(bg, (bigrams.get(bg) ?? 0) + 1)
    }
  }

  const combined = new Map(unigrams)
  // Only include bigrams that appear at least twice — single occurrences are noise
  for (const [bg, cnt] of bigrams) if (cnt >= 2) combined.set(bg, cnt)

  return Array.from(combined.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, topN)
    .map(([value, count]) => ({ value, count, percentage: percentageOf(count, total) }))
}

/**
 * Split and count keywords across included papers.
 * Splits on comma, semicolon, or pipe; normalises to lowercase; strips whitespace.
 * Returns the top `topN` terms sorted descending by count.
 */
export function aggregateKeywords(
  papers: Array<{ keywords?: string | null }>,
  topN: number = 15,
): CategoryCount[] {
  const counts = new Map<string, number>()
  for (const p of papers) {
    if (!p.keywords) continue
    for (const raw of p.keywords.split(/[,;|]/)) {
      const kw = raw.trim().toLowerCase()
      if (kw) counts.set(kw, (counts.get(kw) ?? 0) + 1)
    }
  }
  const total = papers.length
  return Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, topN)
    .map(([value, count]) => ({ value, count, percentage: percentageOf(count, total) }))
}

/**
 * Aggregate included papers by venue name (the actual title string, not type).
 * Papers with a blank venue field are collected under "Unknown".
 * Returns the top `topN` venues sorted descending by count.
 */
/**
 * Normalise a venue string before grouping:
 *   - Strip trailing 4-digit year (e.g. "PLDI 2019" → "PLDI")
 *   - Strip leading ordinal numbers (e.g. "9th International…" → "International…")
 *   - Collapse extra whitespace
 */
function normalizeVenueName(raw: string): string {
  let v = raw
    // Strip "Proceedings - " / "Proceedings – " prefix (Scopus pattern)
    .replace(/^proceedings\s*[-–]\s*/i, '')
    // Strip "Proceedings of [the] …" prefix
    .replace(/^proceedings\s+of\s+the\s+/i, '')
    .replace(/^proceedings\s+of\s+/i, '')
    // Strip 4-digit years anywhere (1900–2099)
    .replace(/\b(?:19|20)\d{2}\b/g, '')
    // Strip numeric ordinals ("33rd", "9th", etc.)
    .replace(/\b\d+\s*(st|nd|rd|th)\b\s*/gi, '')
    // Strip word ordinals at start ("Third", "Fifth", etc.)
    .replace(/^(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+/i, '')
    // Remove " – Annual …" residue after ordinal removal
    .replace(/\s*[-–]\s*Annual\b.*/gi, '')
    // Strip volume/issue/number markers
    .replace(/\bvol(?:ume)?\.?\s*\d+\b/gi, '')
    .replace(/\bno\.?\s*\d+\b/gi, '')
    .replace(/\bissue\.?\s*\d+\b/gi, '')
    // Clean up trailing short acronyms left by year/ordinal removal
    // e.g. ", NCA"  ", ICNS'06"  ". Proceedings."
    .replace(/[,\.]\s*(?:[A-Z][A-Z0-9'–\-]{0,9}|\bProceedings\b\.?)\s*$/, '')
    // Fix space-before-comma artifacts ("Services , ICNS" → "Services, ICNS")
    .replace(/\s+,/g, ',')
    // Strip trailing punctuation artifacts
    .replace(/[,;:\-–—.]\s*$/, '')
    .replace(/\(\s*\)/g, '')
    // Collapse whitespace, trim
    .replace(/\s{2,}/g, ' ')
    .trim()
  return v || 'Unknown'
}

/**
 * Aggregate included papers by normalised venue name.
 *
 * Applies normaliseVenueName (year/ordinal/proceedings stripping) so that
 * "PLDI 2019", "PLDI 2021", and "PLDI - 33rd Annual ACM SIGPLAN Conference"
 * all collapse into one "PLDI" bar.
 *
 * Returns the top N venues by count, descending. No "Other" bucket —
 * every venue is shown at its actual aggregated count.  Names are
 * truncated to 50 characters.
 */
export function aggregateTopVenues(
  papers: Array<{ venue?: string | null }>,
  topN = 10,
): CategoryCount[] {
  const total = papers.length
  const counts = new Map<string, number>()
  for (const p of papers) {
    const raw  = (p.venue ?? '').trim()
    const name = raw ? normalizeVenueName(raw) : 'Unknown'
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }

  return Array.from(counts.entries())
    .filter(([value]) => value !== 'Unknown')   // papers without venue are not a "venue"
    .map(([value, count]) => ({ value, count, percentage: percentageOf(count, total) }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
    .slice(0, topN)
    .map(e => ({
      ...e,
      // Keep full names up to 120 chars; the two-line tick handles wrapping.
      value: e.value.length > 120 ? e.value.slice(0, 117) + '…' : e.value,
    }))
}

// ── Inter-rater agreement labels ────────────────────────────────────────────

/**
 * Landis & Koch (1977) interpretation thresholds. Kept in sync with the
 * Python `app.services.kappa_service.interpret_kappa` helper.
 */
export function kappaInterpretation(kappa: number): string {
  if (kappa >= 1.0) return 'Perfect agreement'
  if (kappa >= 0.81) return 'Almost perfect agreement'
  if (kappa >= 0.61) return 'Substantial agreement'
  if (kappa >= 0.41) return 'Moderate agreement'
  if (kappa >= 0.21) return 'Fair agreement'
  if (kappa >= 0.0)  return 'Slight agreement'
  return 'Poor agreement (less than chance)'
}

/**
 * Map an interpretation/kappa value to one of the three muted status colors
 * used for badges (matches the design system's include/uncertain/exclude tokens).
 */
export function kappaBadgeBand(kappa: number): QualityBand {
  if (kappa >= 0.61) return 'high'
  if (kappa >= 0.21) return 'medium'
  return 'low'
}
