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
  const parts = authors.split(' and ').map(s => s.trim()).filter(Boolean)
  if (parts.length <= maxFull) return parts.join(', ')
  // BibTeX surname-first: "Surname, Firstname" → take part before comma
  const firstSurname = parts[0].split(',')[0].trim()
  return `${firstSurname} et al.`
}
