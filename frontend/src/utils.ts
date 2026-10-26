import type { Paper, ReviewerDecision } from './api/types'

/**
 * The active reviewer's own decision on a paper. List endpoints attach every
 * reviewer's decisions; screening views must render the active reviewer's own
 * vote, never another reviewer's (independent screening).
 */
export function ownDecision(paper: Paper, reviewerId?: number | null): ReviewerDecision | undefined {
  if (reviewerId == null) return undefined
  return paper.decisions?.find(d => d.reviewer_id === reviewerId)
}

/**
 * A consensus decision exists only once at least two reviewers have voted —
 * with a single vote the backend's FinalDecision is provisional (it mirrors
 * that one reviewer's call) and must stay hidden from co-reviewers to keep
 * screening independent.
 */
export function consensusDecision(paper: Paper): string | null {
  if (!paper.final_decision) return null
  if ((paper.decisions?.length ?? 0) < 2) return null
  return paper.final_decision.decision
}

/** True while reviewers disagree and no resolution has produced a final decision. */
export function hasOpenConflict(paper: Paper): boolean {
  if (paper.final_decision) return false
  const decs = paper.decisions ?? []
  return new Set(decs.map(d => d.decision)).size > 1
}

/**
 * Format an author string (BibTeX "A and B and C" style) to a display string.
 * ≤ maxFull authors → join with ", "
 * > maxFull authors → first surname + " et al."
 */
export function formatAuthors(authors?: string, maxFull = 3): string {
  if (!authors) return ''
  const parts = splitAuthors(authors)
  if (parts.length <= maxFull) return parts.join(', ')
  // BibTeX surname-first: "Surname, Firstname" → take part before comma
  const firstSurname = parts[0].split(',')[0].trim()
  return `${firstSurname} et al.`
}

/** Surname prefixes after which a capital letter continues the same name ("McDonald", "DeMarco"). */
const NAME_PREFIXES = new Set(['Mc', 'Mac', 'De', 'Di', 'Da', 'Du', 'La', 'Le', 'Van', 'Von'])

/**
 * Split an author string into names. BibTeX separates them with " and "; the
 * SpringerLink export glues them together without any separator
 * ("Guillaume BourAnniken Wium Lie"), so a capital letter directly after a
 * lower-case one starts the next name — unless the word so far is a surname
 * prefix or shorter than three letters.
 */
export function splitAuthors(authors: string): string[] {
  if (authors.includes(' and ') || authors.includes(',')) {
    return authors.split(' and ').map(s => s.trim()).filter(Boolean)
  }
  const parts: string[] = []
  let start = 0
  for (let i = 1; i < authors.length; i++) {
    if (!/\p{Ll}/u.test(authors[i - 1]) || !/\p{Lu}/u.test(authors[i])) continue
    const word = authors.slice(Math.max(start, authors.lastIndexOf(' ', i - 1) + 1), i)
    if (word.length < 3 || NAME_PREFIXES.has(word)) continue
    parts.push(authors.slice(start, i).trim())
    start = i
  }
  parts.push(authors.slice(start).trim())
  return parts.filter(Boolean)
}

const NAMED_ENTITIES: Record<string, string> = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ',
}

/**
 * Decode HTML entities that publisher exports leave in titles and abstracts
 * ("Internet of&#xa0;Medical Things"). A non-breaking space becomes a plain
 * space so the text wraps normally. Unknown named entities stay as they are.
 */
export function decodeEntities(text: string): string {
  if (!text.includes('&')) return text
  return text.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (match, entity: string) => {
    if (entity[0] !== '#') return NAMED_ENTITIES[entity.toLowerCase()] ?? match
    const code = entity[1].toLowerCase() === 'x' ? parseInt(entity.slice(2), 16) : parseInt(entity.slice(1), 10)
    if (code === 0xa0) return ' '
    try { return String.fromCodePoint(code) } catch { return match }
  })
}
