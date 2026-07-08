import { describe, it, expect } from 'vitest'
import { ownDecision, consensusDecision, hasOpenConflict, formatAuthors } from './utils'
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
