/** The gate every grey-literature feature reads.
 *
 * The default is the whole point. ReviQ is a published tool with existing
 * projects, all of them systematic reviews, and a project row from before the
 * column existed comes back with no value at all. Treating that absence as
 * multivocal would put an empty grey column into an existing review's
 * published figure.
 */
import { describe, expect, it } from 'vitest'

import { isMlr, isSlr, MLR, REVIEW_TYPES, reviewTypeOf, SLR } from './reviewType'

describe('reviewTypeOf', () => {
  it('reads a declared multivocal review', () => {
    expect(reviewTypeOf({ review_type: MLR })).toBe(MLR)
  })

  it('reads a declared systematic review', () => {
    expect(reviewTypeOf({ review_type: SLR })).toBe(SLR)
  })

  it.each([
    ['field absent', {}],
    ['field null', { review_type: null }],
    ['field undefined', { review_type: undefined }],
    ['project null', null],
    ['project undefined', undefined],
  ])('falls back to a systematic review when %s', (_label, project) => {
    expect(reviewTypeOf(project as never)).toBe(SLR)
  })

  it('does not accept a near miss as multivocal', () => {
    // A typo must degrade to the safe side rather than silently enabling the
    // grey stream on a review that never declared one.
    for (const value of ['MLR', 'multivocal', 'mlr ', '']) {
      expect(reviewTypeOf({ review_type: value })).toBe(SLR)
    }
  })
})

describe('the predicates', () => {
  it('are exact opposites', () => {
    for (const p of [{ review_type: MLR }, { review_type: SLR }, {}]) {
      expect(isMlr(p)).toBe(!isSlr(p))
    }
  })

  it('hides grey features from an untouched existing project', () => {
    expect(isMlr({})).toBe(false)
  })
})

describe('the offered types', () => {
  it('covers exactly the two the backend validates', () => {
    expect(REVIEW_TYPES.map(t => t.value).sort()).toEqual([MLR, SLR].sort())
  })

  it('suggests the methodology each type actually cites', () => {
    const byValue = Object.fromEntries(REVIEW_TYPES.map(t => [t.value, t]))
    expect(byValue[SLR].defaultMethodology).toMatch(/Kitchenham/)
    expect(byValue[MLR].defaultMethodology).toMatch(/Garousi/)
  })

  it('explains the difference rather than only naming it', () => {
    // The choice decides what the PRISMA figure shows; a user picking it needs
    // to know that without reading the handbook first.
    for (const t of REVIEW_TYPES) expect(t.hint.length).toBeGreaterThan(20)
  })
})
