/** The three nouns, and which phase uses which.
 *
 * PRISMA 2020 counts records at screening, reports at eligibility and studies
 * at the end, and the boxes of the flow diagram do not reconcile if one word
 * is used for all three: two records can point at one report, and two reports
 * can describe one study.
 */
import { describe, expect, it } from 'vitest'

import { counted, PHASE_NOUN, RECORD, REPORT, STUDY } from './vocabulary'

describe('the nouns', () => {
  it('inflects and capitalises each one', () => {
    expect([STUDY.one, STUDY.many, STUDY.One, STUDY.Many])
      .toEqual(['study', 'studies', 'Study', 'Studies'])
    expect([RECORD.one, RECORD.many]).toEqual(['record', 'records'])
    expect([REPORT.One, REPORT.Many]).toEqual(['Report', 'Reports'])
  })

  it('agrees with its count', () => {
    expect(counted(1, RECORD)).toBe('1 record')
    expect(counted(0, RECORD)).toBe('0 records')
    expect(counted(423, STUDY)).toBe('423 studies')
  })
})

describe('which phase counts what', () => {
  it('screens records and assesses reports', () => {
    // The distinction the interface used to lose: screening decides on a title
    // and an abstract, eligibility on the document it points at.
    expect(PHASE_NOUN.screening).toBe(RECORD)
    expect(PHASE_NOUN.eligibility).toBe(REPORT)
  })

  it('calls what the review keeps a study, from quality assessment onwards', () => {
    expect(PHASE_NOUN.quality).toBe(STUDY)
    expect(PHASE_NOUN.extraction).toBe(STUDY)
    expect(PHASE_NOUN.results).toBe(STUDY)
  })

  it('gives import the same noun as screening', () => {
    // Import is where records enter; nothing has been read yet.
    expect(PHASE_NOUN.import).toBe(RECORD)
  })

  it('keeps the three nouns distinct', () => {
    const many = new Set([RECORD.many, REPORT.many, STUDY.many])
    expect(many.size).toBe(3)
  })
})
