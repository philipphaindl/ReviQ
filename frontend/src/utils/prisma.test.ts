/** The three PRISMA streams, and the one definition each quantity now has.
 *
 * The test that matters most here is
 * `test the streams agree on what "assessed" means`: the two pre-existing
 * streams did not, and the published figure showed one PRISMA number computed
 * two ways.
 */
import { describe, expect, it } from 'vitest'

import {
  allStreamCounts, STREAMS, streamCounts, streamIsPresent,
  type PrismaPaper, type StreamSpec,
} from './prisma'

const spec = (key: string) => STREAMS.find(s => s.key === key) as StreamSpec

function paper(source: string, over: Partial<PrismaPaper> = {}): PrismaPaper {
  return {
    source,
    dedup_status: 'original',
    stream: source.startsWith('grey') ? 'grey' : 'formal',
    discovery: source.startsWith('snowballing:') || source.startsWith('grey-snowball:')
      ? 'snowball' : 'search',
    final_decision: null,
    decisions: [],
    ...over,
  }
}

const decided = (d: string, criterion?: string): Partial<PrismaPaper> => ({
  final_decision: { decision: d },
  decisions: criterion ? [{ criterion_label: criterion }] : [],
})

// ── the three streams exist and are disjoint ──────────────────────────────────

describe('stream configuration', () => {
  it('covers database, snowballing and grey', () => {
    expect(STREAMS.map(s => s.key)).toEqual(['database', 'snowball', 'grey'])
  })

  it('assigns each paper to exactly one stream', () => {
    const samples = [
      paper('acm'), paper('ieee'), paper('snowballing:1'),
      paper('grey:google'), paper('grey-snowball:google'),
    ]
    for (const p of samples) {
      const matched = STREAMS.filter(s => s.matchesPaper(p))
      expect(matched).toHaveLength(1)
    }
  })

  it('names the grey stream for what it is, not "other methods"', () => {
    // A reader has to be able to tell the grey corpus was searched
    // deliberately rather than stumbled upon.
    expect(spec('grey').label).toMatch(/grey literature/i)
  })
})

// ── the definition that had drifted ───────────────────────────────────────────

describe('"full texts assessed" has one definition across streams', () => {
  /** One paper per stream, all in the same state: passed screening, no
   *  full-text decision recorded yet. */
  const screening = [
    paper('acm', decided('I')),
    paper('snowballing:1', decided('I')),
    paper('grey:google', decided('I')),
  ]
  const fulltext = [
    paper('acm'), paper('snowballing:1'), paper('grey:google'),
  ]

  it('reports the same number for every stream in the same state', () => {
    const counts = allStreamCounts(screening, fulltext, {})
    expect(counts.map(c => c.counts.ftAssessed)).toEqual([1, 1, 1])
  })

  it('counts what entered full-text assessment, not what has been decided', () => {
    // The old snowball rule returned 0 here — the paper has no full-text
    // decision — while the old database rule returned 1. That divergence is
    // what this module removes.
    expect(streamCounts(spec('snowball'), screening, fulltext, {}).ftAssessed).toBe(1)
  })

  it('leaves the queue visible as assessed minus excluded minus included', () => {
    const s = [paper('acm', decided('I')), paper('acm', decided('I'))]
    const f = [paper('acm', decided('E', 'E1')), paper('acm')]
    const c = streamCounts(spec('database'), s, f, {})
    expect(c.ftAssessed).toBe(2)
    expect(c.ftExcluded + c.ftIncluded).toBe(1)
  })
})

// ── the eight numbers ─────────────────────────────────────────────────────────

describe('per-stream counts', () => {
  it('derives the grey stream from grey sources only', () => {
    const screening = [
      paper('grey:google', decided('I')),
      paper('grey:google', decided('E', 'E2')),
      paper('acm', decided('I')),
    ]
    const c = streamCounts(spec('grey'), screening, [], {
      'grey:google': { total: 5, original: 2, duplicate: 3 },
      acm: { total: 9, original: 1, duplicate: 8 },
    })

    expect(c.retrieved).toBe(5)
    expect(c.unique).toBe(2)
    expect(c.duplicates).toBe(3)
    expect(c.screeningExcluded).toBe(1)
    expect(c.ftAssessed).toBe(1)
    expect(c.screeningExclByCriterion).toEqual({ E2: 1 })
  })

  it('counts snowballed grey separately from searched grey', () => {
    // Grey literature has its own snowballing; both are grey, and the grey
    // column must hold both or the stream totals stop adding up.
    const screening = [
      paper('grey:google', decided('I')),
      paper('grey-snowball:google', decided('I')),
    ]
    expect(streamCounts(spec('grey'), screening, [], {}).unique).toBe(2)
    expect(streamCounts(spec('snowball'), screening, [], {}).unique).toBe(0)
  })

  it('excludes duplicates from the screened pool', () => {
    const screening = [
      paper('grey:google'),
      paper('grey:google', { dedup_status: 'duplicate' }),
    ]
    expect(streamCounts(spec('grey'), screening, [], {}).unique).toBe(1)
  })

  it('never reports a negative duplicate count', () => {
    // `bySource` counts rows in imported files, `unique` counts surviving
    // papers. Pruning papers by hand would otherwise drive this below zero.
    const screening = [paper('grey:google'), paper('grey:google')]
    const c = streamCounts(spec('grey'), screening, [], {
      'grey:google': { total: 1, original: 1, duplicate: 0 },
    })
    expect(c.duplicates).toBe(0)
  })

  it('keeps an exclusion whose criterion was never recorded', () => {
    // Dropping it would stop the reasons list adding up to the excluded count
    // printed above it.
    const screening = [paper('grey:google', decided('E'))]
    const c = streamCounts(spec('grey'), screening, [], {})
    expect(c.screeningExcluded).toBe(1)
    expect(c.screeningExclByCriterion).toEqual({ Other: 1 })
  })

  it('groups full-text exclusions by their criterion', () => {
    const fulltext = [
      paper('grey:google', decided('E', 'E1')),
      paper('grey:google', decided('E', 'E1')),
      paper('grey:google', decided('E', 'E3')),
      paper('grey:google', decided('I')),
    ]
    const c = streamCounts(spec('grey'), [], fulltext, {})
    expect(c.ftExclByCriterion).toEqual({ E1: 2, E3: 1 })
    expect(c.ftIncluded).toBe(1)
  })
})

// ── which columns the diagram draws ───────────────────────────────────────────

describe('stream presence', () => {
  it('is false for a review with no grey literature', () => {
    const c = streamCounts(spec('grey'), [paper('acm')], [], {
      acm: { total: 1, original: 1, duplicate: 0 },
    })
    expect(streamIsPresent(c)).toBe(false)
  })

  it('is true once a single grey record has been identified', () => {
    const c = streamCounts(spec('grey'), [paper('grey:google')], [], {})
    expect(streamIsPresent(c)).toBe(true)
  })

  it('is true for a stream whose records were all retrieved but deduplicated away', () => {
    // The records were still identified; PRISMA's top box counts them.
    const c = streamCounts(spec('grey'), [], [], {
      'grey:google': { total: 4, original: 0, duplicate: 4 },
    })
    expect(streamIsPresent(c)).toBe(true)
  })
})
