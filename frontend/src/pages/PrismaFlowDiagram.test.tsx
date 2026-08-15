/** Which columns the figure draws, and what each one says.
 *
 * The rule this protects: a stream that contributed nothing must not appear.
 * ReviQ has published users whose reviews have no grey literature, and an
 * empty third column in their figure would be a claim about their method that
 * they never made. The same has always been true of snowballing.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PrismaFlowDiagram } from './Results'
import {
  allStreamCounts, type PrismaPaper,
} from '../utils/prisma'
import { PHASE_NOUN } from '../utils/vocabulary'

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

const included = { final_decision: { decision: 'I' } }

type BySource = Record<string, { total: number; original: number; duplicate: number }>

function draw(
  screening: PrismaPaper[],
  bySource: BySource = {},
  fulltext: PrismaPaper[] = [],
) {
  return render(
    <PrismaFlowDiagram
      streams={allStreamCounts(screening, fulltext, bySource)}
      bySource={bySource}
      shortLabelMap={{}}
    />,
  )
}

/** The header of every column drawn, in reading order — the only text on the
 *  header band at y=16. */
const headers = () =>
  Array.from(document.querySelectorAll('#prisma-svg text[y="16"]'))
    .map(t => t.textContent)

describe('which columns the diagram draws', () => {
  it('draws one column and no headers for a database-only review', () => {
    // The single-column figure has no column headers at all: there is nothing
    // to tell apart. This is the shape every existing SLR is published with.
    draw([paper('acm')], { acm: { total: 3, original: 1, duplicate: 2 } })

    expect(screen.queryByText(/Records via snowballing/)).toBeNull()
    expect(screen.queryByText(/Records from grey literature/)).toBeNull()
    expect(screen.getByText('Records from databases')).toBeInTheDocument()
    // The final box of a one-stream review is the green one.
    expect(screen.getByText('Studies included in review')).toBeInTheDocument()
  })

  it('leaves the grey column out when the review has no grey literature', () => {
    draw([paper('acm'), paper('snowballing:1')], {
      acm: { total: 3, original: 1, duplicate: 2 },
      'snowballing:1': { total: 1, original: 1, duplicate: 0 },
    })

    expect(headers()).toEqual(['DATABASE SEARCH', 'SNOWBALLING'])
    expect(screen.queryByText(/grey literature/i)).toBeNull()
  })

  it('draws the third column once a grey record exists', () => {
    draw([paper('acm'), paper('snowballing:1'), paper('grey:google')], {
      acm: { total: 3, original: 1, duplicate: 2 },
      'snowballing:1': { total: 1, original: 1, duplicate: 0 },
      'grey:google': { total: 5, original: 1, duplicate: 4 },
    })

    expect(headers()).toEqual(['DATABASE SEARCH', 'SNOWBALLING', 'GREY LITERATURE'])
    expect(screen.getByText('Records from grey literature')).toBeInTheDocument()
    expect(screen.getByText('Included (grey literature)')).toBeInTheDocument()
  })

  it('draws grey beside databases when the review never snowballed', () => {
    // Columns follow PRISMA reading order, not the array index: an absent
    // snowball stream must not leave a gap where its column would have been.
    draw([paper('acm'), paper('grey:google')], {
      acm: { total: 1, original: 1, duplicate: 0 },
      'grey:google': { total: 1, original: 1, duplicate: 0 },
    })

    expect(headers()).toEqual(['DATABASE SEARCH', 'GREY LITERATURE'])
  })

  it('widens by one column pitch per stream', () => {
    const width = (screening: PrismaPaper[], bySource: BySource) => {
      const { unmount } = draw(screening, bySource)
      const w = Number(document.getElementById('prisma-svg')?.getAttribute('width'))
      unmount()
      return w
    }
    const two = width([paper('acm'), paper('snowballing:1')], {})
    const three = width([paper('acm'), paper('snowballing:1'), paper('grey:google')], {})

    expect(three - two).toBe(420)
  })
})

describe('what the columns say', () => {
  it('sums the included boxes into the combined one', () => {
    const fulltext = [
      paper('acm', included), paper('acm', included),
      paper('grey:google', included),
    ]
    draw(fulltext, {}, fulltext)

    // Two streams → a joined green box carrying the total, not one per column.
    expect(screen.getByText('Studies included in review')).toBeInTheDocument()
    const totals = Array.from(document.querySelectorAll('#prisma-svg text'))
      .map(t => t.textContent)
    expect(totals).toContain('n = 3')
  })

  it('breaks the grey column down by search engine, not by database key', () => {
    draw([paper('grey:google')], {
      'grey:google': { total: 5, original: 1, duplicate: 4 },
    })

    // `grey:google` is a source key, not a name a reader should have to parse.
    expect(screen.getByText(/^Google:/)).toBeInTheDocument()
  })

  it('shows a deduplication step for grey literature, which searches several engines', () => {
    draw([paper('grey:google')], {
      'grey:google': { total: 5, original: 1, duplicate: 4 },
    })

    expect(screen.getByText('Records after deduplication')).toBeInTheDocument()
    expect(screen.getByText('Duplicates removed')).toBeInTheDocument()
  })

  it('shows none for snowballing, which has no sources to overlap', () => {
    draw([paper('snowballing:1')], {})

    expect(screen.queryByText('Records after deduplication')).toBeNull()
  })

  it('renders an untouched project as an empty skeleton rather than nothing', () => {
    draw([], {})

    expect(document.getElementById('prisma-svg')).toBeInTheDocument()
    expect(screen.getByText('Records from databases')).toBeInTheDocument()
  })

  it('uses the same nouns the pages do', () => {
    // The figure has always said "Records screened" and "Studies included in
    // review" while the pages said "papers" at both. Whichever way that gets
    // fixed, it has to stay fixed in both places.
    draw([paper('acm')], { acm: { total: 1, original: 1, duplicate: 0 } })

    expect(screen.getByText(`${PHASE_NOUN.screening.Many} screened`)).toBeInTheDocument()
    expect(screen.getByText(new RegExp(`^${PHASE_NOUN.results.Many} included`)))
      .toBeInTheDocument()
  })
})
