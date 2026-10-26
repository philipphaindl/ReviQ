import { describe, it, expect } from 'vitest'
import { ownDecision, consensusDecision, hasOpenConflict, formatAuthors, splitAuthors, decodeEntities } from './utils'
import type { Paper, ReviewerDecision, FinalDecision } from './api/types'

// ── Fixtures ──────────────────────────────────────────────────────────────────

let nextId = 1
function dec(reviewerId: number, decision: string, extra: Partial<ReviewerDecision> = {}): ReviewerDecision {
  return {
    id: nextId++, project_id: 1, paper_id: 1, reviewer_id: reviewerId,
    phase: 'screening', decision, timestamp: '2026-07-01T00:00:00', ...extra,
  }
}

function final(decision: string): FinalDecision {
  return {
    id: nextId++, project_id: 1, paper_id: 1, phase: 'screening',
    decision, timestamp: '2026-07-01T00:00:00',
  }
}

function paper(overrides: Partial<Paper> = {}): Paper {
  return {
    id: 1, project_id: 1, citekey: 'p1', title: 'Paper 1', source: 'acm',
    dedup_status: 'original', full_text_inaccessible: false,
    created_at: '2026-07-01T00:00:00', decisions: [], final_decision: null,
    ...overrides,
  }
}

// ── ownDecision ───────────────────────────────────────────────────────────────

describe('ownDecision', () => {
  it('returns the active reviewer’s own decision', () => {
    const p = paper({ decisions: [dec(1, 'I'), dec(2, 'E')] })
    expect(ownDecision(p, 1)?.decision).toBe('I')
    expect(ownDecision(p, 2)?.decision).toBe('E')
  })

  it('returns undefined when the reviewer has not decided', () => {
    const p = paper({ decisions: [dec(1, 'I')] })
    expect(ownDecision(p, 2)).toBeUndefined()
  })

  it('returns undefined for null/undefined reviewer', () => {
    const p = paper({ decisions: [dec(1, 'I')] })
    expect(ownDecision(p, null)).toBeUndefined()
    expect(ownDecision(p, undefined)).toBeUndefined()
  })
})

// ── consensusDecision ─────────────────────────────────────────────────────────

describe('consensusDecision', () => {
  it('hides a provisional final (single vote) from co-reviewers', () => {
    const p = paper({ decisions: [dec(1, 'I')], final_decision: final('I') })
    expect(consensusDecision(p)).toBeNull()
  })

  it('exposes the final once two reviewers have voted', () => {
    const p = paper({ decisions: [dec(1, 'I'), dec(2, 'I')], final_decision: final('I') })
    expect(consensusDecision(p)).toBe('I')
  })

  it('exposes an adjudicated final even when votes still differ', () => {
    const p = paper({ decisions: [dec(1, 'I'), dec(2, 'E')], final_decision: final('I') })
    expect(consensusDecision(p)).toBe('I')
  })

  it('returns null without a final decision', () => {
    const p = paper({ decisions: [dec(1, 'I'), dec(2, 'E')] })
    expect(consensusDecision(p)).toBeNull()
  })
})

// ── hasOpenConflict ───────────────────────────────────────────────────────────

describe('hasOpenConflict', () => {
  it('flags disagreeing votes without a final decision', () => {
    const p = paper({ decisions: [dec(1, 'I'), dec(2, 'E')] })
    expect(hasOpenConflict(p)).toBe(true)
  })

  it('does not flag agreement', () => {
    const p = paper({ decisions: [dec(1, 'I'), dec(2, 'I')], final_decision: final('I') })
    expect(hasOpenConflict(p)).toBe(false)
  })

  it('does not flag an adjudicated disagreement (final exists)', () => {
    const p = paper({ decisions: [dec(1, 'I'), dec(2, 'E')], final_decision: final('I') })
    expect(hasOpenConflict(p)).toBe(false)
  })

  it('does not flag a single vote', () => {
    const p = paper({ decisions: [dec(1, 'I')] })
    expect(hasOpenConflict(p)).toBe(false)
  })
})

// ── formatAuthors (pre-existing helper, pinned) ───────────────────────────────

describe('formatAuthors', () => {
  it('joins up to three authors', () => {
    expect(formatAuthors('Doe, Jane and Roe, Max')).toBe('Doe, Jane, Roe, Max')
  })
  it('abbreviates four or more authors', () => {
    expect(formatAuthors('Doe, Jane and A, B and C, D and E, F')).toBe('Doe et al.')
  })
  it('handles empty input', () => {
    expect(formatAuthors(undefined)).toBe('')
  })
})

describe('splitAuthors', () => {
  it('splits BibTeX author lists on " and "', () => {
    expect(splitAuthors('Doe, Jane and Roe, Max')).toEqual(['Doe, Jane', 'Roe, Max'])
  })
  it('separates names the SpringerLink export glued together', () => {
    expect(splitAuthors('Guillaume BourAnniken Wium LieJakob Stenersen Kok'))
      .toEqual(['Guillaume Bour', 'Anniken Wium Lie', 'Jakob Stenersen Kok'])
  })
  it('keeps surname prefixes and single names intact', () => {
    expect(splitAuthors('Patrick McDaniel')).toEqual(['Patrick McDaniel'])
    expect(splitAuthors('Tom DeMarco')).toEqual(['Tom DeMarco'])
    expect(splitAuthors('Riccardo Lazzeretti')).toEqual(['Riccardo Lazzeretti'])
  })
  it('abbreviates a glued list like any other', () => {
    expect(formatAuthors('Guillaume BourAnniken Wium LieJakob Stenersen KokBendik Markussen'))
      .toBe('Guillaume Bour et al.')
  })
})

describe('decodeEntities', () => {
  it('turns non-breaking space entities into plain spaces', () => {
    expect(decodeEntities('Internet of&#xa0;Medical Things')).toBe('Internet of Medical Things')
  })
  it('decodes numeric and common named entities', () => {
    expect(decodeEntities('R&amp;D &#8211; &quot;AI&quot;')).toBe('R&D – "AI"')
  })
  it('leaves unknown entities and plain text unchanged', () => {
    expect(decodeEntities('&foo; stays')).toBe('&foo; stays')
    expect(decodeEntities('no entities')).toBe('no entities')
  })
})
