/** Per-stream PRISMA counts, derived once for every stream.
 *
 * A multivocal review has three streams, not two: database search, snowballing,
 * and grey literature (Garousi, Felderer & Mäntylä 2019). Each needs the same
 * eight numbers, and until now each was derived inline in `Results.tsx` with
 * its own copy of the filter chain — two copies, about to become three.
 *
 * That duplication was not merely verbose. The two copies had already drifted:
 * "full texts assessed" meant *passed screening* in the database stream and
 * *has a full-text decision recorded* in the snowballing stream, in the same
 * diagram. For a finished review the two agree; for one in progress they do
 * not, and the published figure showed one number computed two ways. This
 * module exists so that adding a stream means adding a predicate, and so that
 * a PRISMA quantity has exactly one definition.
 *
 * `streams.ts` fixed the same shape of bug for the stream test itself, and its
 * docstring states the rule this follows: adding a stream must mean editing one
 * file, not twenty.
 */
import {
  isFormalSearch, isFormalSearchSource, isFormalSnowball, isGrey,
  isGreySource, isSnowballSource,
} from '../components/streams'

/** The shape `list_papers` returns: a paper plus its decisions for one phase. */
export interface PrismaPaper {
  dedup_status?: string
  // Required, matching `Paper` and the `StreamLike` the stream tests take:
  // `streams.ts` falls back to the source prefix for rows written before the
  // `stream` column existed, so it cannot be optional here.
  source: string
  stream?: string
  discovery?: string
  final_decision?: { decision?: string } | null
  decisions?: { criterion_label?: string | null }[]
}

export interface StreamCounts {
  /** Rows the search returned, before deduplication. */
  retrieved: number
  duplicates: number
  /** Records after deduplication — the pool that is screened. */
  unique: number
  screeningExcluded: number
  /**
   * Records that entered full-text assessment, i.e. passed screening.
   *
   * One definition for every stream. PRISMA 2020's box is the denominator the
   * exclusions below it are subtracted from, so it has to be "what went in",
   * not "what has been decided so far" — otherwise a review in progress shows
   * an assessed count that grows as reviewers work, and the excluded and
   * included boxes beneath it never reconcile against anything stable.
   *
   * A consequence worth knowing: while full-text review is unfinished,
   * `ftAssessed > ftExcluded + ftIncluded`. The difference is the queue, and
   * that is a true statement about the review rather than a rounding error.
   */
  ftAssessed: number
  ftExcluded: number
  ftIncluded: number
  screeningExclByCriterion: Record<string, number>
  ftExclByCriterion: Record<string, number>
}

/** How one stream recognises its own papers and its own `source` labels. */
export interface StreamSpec {
  key: 'database' | 'snowball' | 'grey'
  label: string
  matchesPaper: (p: PrismaPaper) => boolean
  matchesSource: (source: string) => boolean
}

/** The three streams of a multivocal review, in PRISMA reading order. */
export const STREAMS: StreamSpec[] = [
  {
    key: 'database',
    label: 'Identification via databases',
    matchesPaper: isFormalSearch,
    matchesSource: isFormalSearchSource,
  },
  {
    key: 'snowball',
    label: 'Identification via snowballing',
    matchesPaper: isFormalSnowball,
    matchesSource: isSnowballSource,
  },
  {
    key: 'grey',
    // Named for what it is rather than "other methods": a reader has to be able
    // to tell that the grey corpus was searched deliberately, not stumbled on.
    label: 'Identification via grey literature',
    matchesPaper: isGrey,
    matchesSource: isGreySource,
  },
]

function byCriterion(papers: PrismaPaper[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const p of papers) {
    // `Other` rather than dropping the row: an exclusion whose criterion was
    // not recorded still happened, and a reasons list that silently omits it
    // stops adding up to the excluded count above it.
    const c = p.decisions?.[0]?.criterion_label ?? 'Other'
    out[c] = (out[c] ?? 0) + 1
  }
  return out
}

export function streamCounts(
  spec: StreamSpec,
  screeningPapers: PrismaPaper[],
  fulltextPapers: PrismaPaper[],
  bySource: Record<string, { total: number; original: number; duplicate: number }>,
): StreamCounts {
  const retrieved = Object.entries(bySource)
    .filter(([source]) => spec.matchesSource(source))
    .reduce((sum, [, v]) => sum + v.total, 0)

  const mine = screeningPapers.filter(
    p => spec.matchesPaper(p) && p.dedup_status === 'original',
  )
  const screeningExcludedPapers = mine.filter(p => p.final_decision?.decision === 'E')
  // Passed screening — see `ftAssessed`. The same rule for all three streams.
  const enteredFullText = mine.filter(p => p.final_decision?.decision === 'I')

  const ftMine = fulltextPapers.filter(spec.matchesPaper)
  const ftExcludedPapers = ftMine.filter(p => p.final_decision?.decision === 'E')

  return {
    retrieved,
    // Never negative: `bySource` counts rows in imported files while `mine`
    // counts surviving papers, and a project whose papers were pruned by hand
    // would otherwise report a negative duplicate count.
    duplicates: Math.max(0, retrieved - mine.length),
    unique: mine.length,
    screeningExcluded: screeningExcludedPapers.length,
    ftAssessed: enteredFullText.length,
    ftExcluded: ftExcludedPapers.length,
    ftIncluded: ftMine.filter(p => p.final_decision?.decision === 'I').length,
    screeningExclByCriterion: byCriterion(screeningExcludedPapers),
    ftExclByCriterion: byCriterion(ftExcludedPapers),
  }
}

/** Counts for every stream, keyed by stream. */
export function allStreamCounts(
  screeningPapers: PrismaPaper[],
  fulltextPapers: PrismaPaper[],
  bySource: Record<string, { total: number; original: number; duplicate: number }>,
): { spec: StreamSpec; counts: StreamCounts }[] {
  return STREAMS.map(spec => ({
    spec,
    counts: streamCounts(spec, screeningPapers, fulltextPapers, bySource),
  }))
}

/** True when a stream contributed anything at all.
 *
 * The diagram draws a column per non-empty stream: a review with no grey
 * literature should not carry an empty grey column into its published figure,
 * and one with no snowballing already did not.
 */
export const streamIsPresent = (c: StreamCounts) =>
  c.retrieved > 0 || c.unique > 0
