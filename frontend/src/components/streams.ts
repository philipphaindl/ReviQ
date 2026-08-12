/**
 * How a paper entered the review. Mirror of backend/app/services/streams.py —
 * the two must agree case for case, or the PRISMA diagram in the browser and
 * the one in the exported PDF will disagree.
 *
 * Two independent axes:
 *   stream    — formal (peer-reviewed databases) vs. grey (web sources)
 *   discovery — search (a database or engine query) vs. snowball
 *
 * They are orthogonal: grey literature has its own snowballing. Never test
 * `paper.source` for a stream; it has no third case, which is how grey
 * records would end up counted as database hits.
 */
import type { Paper } from '../api/types'

export const FORMAL = 'formal'
export const GREY = 'grey'
export const SEARCH = 'search'
export const SNOWBALL = 'snowball'

const GREY_PREFIXES = ['grey:', 'grey-snowball:']
const SNOWBALL_PREFIXES = ['snowballing:', 'grey-snowball:']

type StreamLike = Pick<Paper, 'source'> & { stream?: string; discovery?: string }

/** FORMAL or GREY. Falls back to the source prefix for pre-migration rows. */
export function streamOf(p: StreamLike): string {
  if (p.stream) return p.stream
  const source = p.source ?? ''
  return GREY_PREFIXES.some(x => source.startsWith(x)) ? GREY : FORMAL
}

/** SEARCH or SNOWBALL. Falls back to the source prefix for pre-migration rows. */
export function discoveryOf(p: StreamLike): string {
  if (p.discovery) return p.discovery
  const source = p.source ?? ''
  return SNOWBALL_PREFIXES.some(x => source.startsWith(x)) ? SNOWBALL : SEARCH
}

export const isGrey = (p: StreamLike) => streamOf(p) === GREY
export const isFormal = (p: StreamLike) => streamOf(p) === FORMAL
export const isSnowballed = (p: StreamLike) => discoveryOf(p) === SNOWBALL

/**
 * The formal database-search arm of PRISMA: formal literature reached by a
 * database query. Previously written as `!source.startsWith('snowballing:')`,
 * which silently swept grey literature in with it.
 */
export const isFormalSearch = (p: StreamLike) => isFormal(p) && !isSnowballed(p)

/** The formal snowballing arm. */
export const isFormalSnowball = (p: StreamLike) => isFormal(p) && isSnowballed(p)

/** True for a `bySource` key that belongs to the formal database-search arm. */
export function isFormalSearchSource(source: string): boolean {
  return streamOf({ source } as StreamLike) === FORMAL
    && discoveryOf({ source } as StreamLike) === SEARCH
}

/** True for a `bySource` key that belongs to the formal snowballing arm. */
export function isSnowballSource(source: string): boolean {
  return (source ?? '').startsWith('snowballing:')
}

/** True for a `bySource` key produced by grey-literature retrieval. */
export function isGreySource(source: string): boolean {
  return GREY_PREFIXES.some(x => (source ?? '').startsWith(x))
}
