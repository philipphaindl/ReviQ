/**
 * Mirror of backend/tests/test_streams.py. The browser PRISMA diagram and the
 * one in the exported PDF are computed independently, so these two test files
 * are what keeps them from drifting. Change one, change the other.
 */
import { describe, it, expect } from 'vitest'
import {
  FORMAL, GREY, SEARCH, SNOWBALL,
  streamOf, discoveryOf, isFormalSearch, isFormalSnowball,
  isFormalSearchSource, isSnowballSource, isGreySource,
} from './streams'

const paper = (o: Record<string, unknown>) => o as never

describe('explicit columns', () => {
  it('classifies a formal database hit', () => {
    const p = paper({ stream: 'formal', discovery: 'search', source: 'ieee' })
    expect([streamOf(p), discoveryOf(p)]).toEqual([FORMAL, SEARCH])
  })

  it('classifies a grey search hit', () => {
    const p = paper({ stream: 'grey', discovery: 'search', source: 'grey:google' })
    expect([streamOf(p), discoveryOf(p)]).toEqual([GREY, SEARCH])
  })

  it('classifies a grey snowballed source', () => {
    const p = paper({ stream: 'grey', discovery: 'snowball', source: 'grey:google' })
    expect([streamOf(p), discoveryOf(p)]).toEqual([GREY, SNOWBALL])
  })

  it('lets the columns win over the source string', () => {
    const p = paper({ stream: 'grey', discovery: 'search', source: 'snowballing:2' })
    expect([streamOf(p), discoveryOf(p)]).toEqual([GREY, SEARCH])
  })
})

describe('legacy rows written before the migration', () => {
  it('treats a bare database source as formal search', () => {
    const p = paper({ source: 'scopus' })
    expect([streamOf(p), discoveryOf(p)]).toEqual([FORMAL, SEARCH])
  })

  it('treats snowballing:N as formal snowball', () => {
    const p = paper({ source: 'snowballing:2' })
    expect([streamOf(p), discoveryOf(p)]).toEqual([FORMAL, SNOWBALL])
  })

  it('survives an empty source', () => {
    const p = paper({ source: '' })
    expect([streamOf(p), discoveryOf(p)]).toEqual([FORMAL, SEARCH])
  })
})

describe('PRISMA arm predicates', () => {
  const formalDb = paper({ stream: 'formal', discovery: 'search', source: 'ieee' })
  const formalSnow = paper({ stream: 'formal', discovery: 'snowball', source: 'snowballing:1' })
  const greyDoc = paper({ stream: 'grey', discovery: 'search', source: 'grey:google' })

  it('puts a formal database hit in the database arm only', () => {
    expect(isFormalSearch(formalDb)).toBe(true)
    expect(isFormalSnowball(formalDb)).toBe(false)
  })

  it('puts a snowballed paper in the snowballing arm only', () => {
    expect(isFormalSearch(formalSnow)).toBe(false)
    expect(isFormalSnowball(formalSnow)).toBe(true)
  })

  it('keeps grey literature out of both formal arms', () => {
    // The regression this whole module exists for: with a `source` prefix
    // test, a grey record answered "not snowballing" and was counted as a
    // database hit, inflating PRISMA's "records identified from databases".
    expect(isFormalSearch(greyDoc)).toBe(false)
    expect(isFormalSnowball(greyDoc)).toBe(false)
  })
})

describe('source-key predicates for bySource aggregation', () => {
  it('splits the three arms without overlap', () => {
    const keys = ['ieee', 'scopus', 'snowballing:1', 'grey:google', 'grey-snowball:google']
    const formal = keys.filter(isFormalSearchSource)
    const snow = keys.filter(isSnowballSource)
    const grey = keys.filter(isGreySource)

    expect(formal).toEqual(['ieee', 'scopus'])
    expect(snow).toEqual(['snowballing:1'])
    expect(grey).toEqual(['grey:google', 'grey-snowball:google'])
    expect(formal.length + snow.length + grey.length).toBe(keys.length)
  })
})
