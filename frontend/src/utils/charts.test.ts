import { describe, it, expect } from 'vitest'
import {
  aggregateExtractionField,
  aggregateKeywords,
  aggregateTaxonomy,
  aggregateTopVenues,
  aggregateVenueTypes,
  bandForBin,
  bandForPercentage,
  binQAScores,
  categorizeVenue,
  chartFilename,
  chartSlug,
  compactDate,
  DEFAULT_QA_THRESHOLDS,
  DEFAULT_VENUE_CATEGORIES,
  kappaBadgeBand,
  kappaInterpretation,
  percentageOf,
  pickFirstSelectField,
  summarizeQAScores,
  taxonomyLabel,
} from './charts'

describe('binQAScores', () => {
  it('creates ten bins covering 0..100 in 10-percent steps', () => {
    const bins = binQAScores([])
    expect(bins).toHaveLength(10)
    expect(bins[0]).toMatchObject({ lower: 0, upper: 10, count: 0, low: 0, medium: 0, high: 0 })
    expect(bins[9]).toMatchObject({ lower: 90, upper: 100 })
  })

  it('splits a threshold-straddling bin by per-paper band classification', () => {
    // Bin [70, 80) with default thresholds (medium 50, high 75) — 70 and 74 are
    // medium, 75 and 79 are high — so the bin should report 2 medium + 2 high.
    const bins = binQAScores([
      { key: 'a', percentage: 70 },
      { key: 'b', percentage: 74 },
      { key: 'c', percentage: 75 },
      { key: 'd', percentage: 79 },
    ])
    expect(bins[7]).toMatchObject({ count: 4, low: 0, medium: 2, high: 2 })
    // The "dominant band" annotation tracks the per-bin majority (tie → higher).
    expect(bins[7].band).toBe('high')
  })

  it('keeps the per-band split consistent with the total count', () => {
    const bins = binQAScores([
      { key: 'a', percentage: 5  },
      { key: 'b', percentage: 55 },
      { key: 'c', percentage: 80 },
    ])
    for (const bin of bins) {
      expect(bin.low + bin.medium + bin.high).toBe(bin.count)
    }
  })

  it('assigns scores to the correct bin and records the paper key', () => {
    const bins = binQAScores([
      { key: 'p1', percentage: 0 },
      { key: 'p2', percentage: 49.9 },
      { key: 'p3', percentage: 50 },
      { key: 'p4', percentage: 80 },
    ])
    expect(bins[0].paperKeys).toEqual(['p1'])
    expect(bins[4].paperKeys).toEqual(['p2'])
    expect(bins[5].paperKeys).toEqual(['p3'])
    expect(bins[8].paperKeys).toEqual(['p4'])
  })

  it('treats a score of exactly 100 as belonging to the top bin', () => {
    const bins = binQAScores([{ key: 'top', percentage: 100 }])
    expect(bins[9].count).toBe(1)
    expect(bins[9].paperKeys).toEqual(['top'])
  })

  it('clamps out-of-range scores into the boundary bins', () => {
    const bins = binQAScores([
      { key: 'neg', percentage: -5 },
      { key: 'big', percentage: 250 },
    ])
    expect(bins[0].count).toBe(1)
    expect(bins[9].count).toBe(1)
  })

  it('skips NaN scores without throwing', () => {
    const bins = binQAScores([{ key: 'bad', percentage: Number.NaN }])
    expect(bins.every(b => b.count === 0)).toBe(true)
  })

  it('respects custom thresholds when assigning bin bands', () => {
    const bins = binQAScores([], { medium: 30, high: 60 })
    expect(bins[2].band).toBe('low')      // [20,30) lower=20 < 30
    expect(bins[3].band).toBe('medium')   // [30,40) lower=30 == medium
    expect(bins[5].band).toBe('medium')   // [50,60) lower=50 < 60
    expect(bins[6].band).toBe('high')     // [60,70) lower=60 == high
  })
})

describe('bandForBin', () => {
  it('uses the bin lower edge with the default thresholds', () => {
    expect(bandForBin(0)).toBe('low')
    expect(bandForBin(40)).toBe('low')
    expect(bandForBin(50)).toBe('medium')
    expect(bandForBin(70)).toBe('medium')
    expect(bandForBin(80)).toBe('high')
  })
})

describe('bandForPercentage', () => {
  it('matches the project-level high/medium/low classification', () => {
    expect(bandForPercentage(49.9)).toBe('low')
    expect(bandForPercentage(50)).toBe('medium')
    expect(bandForPercentage(74.9)).toBe('medium')
    expect(bandForPercentage(75)).toBe('high')
  })

  it('honors custom thresholds', () => {
    const t = { medium: 40, high: 80 }
    expect(bandForPercentage(35, t)).toBe('low')
    expect(bandForPercentage(40, t)).toBe('medium')
    expect(bandForPercentage(80, t)).toBe('high')
  })
})

describe('summarizeQAScores', () => {
  it('returns zeros for an empty input set', () => {
    expect(summarizeQAScores([])).toEqual({ n: 0, mean: 0, median: 0 })
  })

  it('computes mean and median correctly for odd-length input', () => {
    const s = summarizeQAScores([
      { key: 'a', percentage: 10 },
      { key: 'b', percentage: 30 },
      { key: 'c', percentage: 80 },
    ])
    expect(s.n).toBe(3)
    expect(s.mean).toBeCloseTo(40)
    expect(s.median).toBe(30)
  })

  it('averages the two middle values for even-length input', () => {
    const s = summarizeQAScores([
      { key: 'a', percentage: 20 },
      { key: 'b', percentage: 40 },
      { key: 'c', percentage: 60 },
      { key: 'd', percentage: 100 },
    ])
    expect(s.median).toBe(50)
    expect(s.mean).toBe(55)
  })
})

describe('aggregateTaxonomy', () => {
  const papers = [
    { values: { contribution_type: 'Tool',      research_type: 'Validation' } },
    { values: { contribution_type: 'Tool',      research_type: 'Evaluation' } },
    { values: { contribution_type: 'Framework', research_type: 'Validation' } },
    { values: {} },
  ]

  it('counts papers per category and sorts by count descending', () => {
    const dist = aggregateTaxonomy(papers, 'contribution_type', ['Framework', 'Method', 'Theory', 'Tool'])
    expect(dist.categories.map(c => c.value)).toEqual(['Tool', 'Framework', 'Method', 'Theory'])
    expect(dist.categories.map(c => c.count)).toEqual([2, 1, 0, 0])
  })

  it('renders schema categories with count 0 when no paper uses them', () => {
    const dist = aggregateTaxonomy([], 'contribution_type', ['Framework', 'Tool'])
    expect(dist.categories).toHaveLength(2)
    expect(dist.categories.every(c => c.count === 0)).toBe(true)
    expect(dist.categories.every(c => c.percentage === 0)).toBe(true)
  })

  it('appends values found in papers but missing from the schema', () => {
    const dist = aggregateTaxonomy(
      [{ values: { contribution_type: 'Pattern' } }],
      'contribution_type',
      ['Tool'],
    )
    expect(dist.categories.map(c => c.value)).toContain('Pattern')
  })

  it('uses the human-readable label for snake_case keys', () => {
    expect(taxonomyLabel('contribution_type')).toBe('Contribution Type')
    expect(taxonomyLabel('research_type')).toBe('Research Type')
  })
})

describe('aggregateExtractionField', () => {
  it('counts and sorts unique values for a single field', () => {
    const result = aggregateExtractionField(
      [
        { values: { usage: 'Direct' } },
        { values: { usage: 'Indirect' } },
        { values: { usage: 'Direct' } },
        { values: { usage: '' } },
        { values: {} },
      ],
      'usage',
    )
    expect(result.map(r => r.value)).toEqual(['Direct', 'Indirect'])
    expect(result.map(r => r.count)).toEqual([2, 1])
  })

  it('returns an empty array when no paper has a value for the field', () => {
    expect(aggregateExtractionField([{ values: {} }], 'usage')).toEqual([])
  })
})

describe('pickFirstSelectField', () => {
  const fields = [
    { id: 1, field_name: 'contribution_type', field_label: 'Contribution', field_type: 'dropdown', sort_order: 0 },
    { id: 2, field_name: 'notes',             field_label: 'Notes',        field_type: 'text',     sort_order: 1 },
    { id: 3, field_name: 'usage',             field_label: 'Usage',        field_type: 'dropdown', sort_order: 2 },
    { id: 4, field_name: 'scope',             field_label: 'Scope',        field_type: 'dropdown', sort_order: 3 },
  ]

  it('returns the first non-taxonomy dropdown field by sort order', () => {
    const picked = pickFirstSelectField(fields, ['contribution_type'])
    expect(picked?.field_name).toBe('usage')
  })

  it('returns null when no select-typed field exists', () => {
    const onlyText = [{ id: 1, field_name: 'notes', field_label: 'Notes', field_type: 'text', sort_order: 0 }]
    expect(pickFirstSelectField(onlyText, [])).toBeNull()
  })

  it('returns null when every dropdown field is a taxonomy dimension', () => {
    const taxOnly = [
      { id: 1, field_name: 'contribution_type', field_label: 'Contribution', field_type: 'dropdown', sort_order: 0 },
      { id: 2, field_name: 'research_type',     field_label: 'Research',     field_type: 'dropdown', sort_order: 1 },
    ]
    expect(pickFirstSelectField(taxOnly, ['contribution_type', 'research_type'])).toBeNull()
  })
})

describe('kappaInterpretation', () => {
  it('maps the Landis & Koch ranges to the same labels as the backend', () => {
    expect(kappaInterpretation(1.0)).toBe('Perfect agreement')
    expect(kappaInterpretation(0.85)).toBe('Almost perfect agreement')
    expect(kappaInterpretation(0.65)).toBe('Substantial agreement')
    expect(kappaInterpretation(0.50)).toBe('Moderate agreement')
    expect(kappaInterpretation(0.30)).toBe('Fair agreement')
    expect(kappaInterpretation(0.10)).toBe('Slight agreement')
    expect(kappaInterpretation(-0.1)).toBe('Poor agreement (less than chance)')
  })

  it('classifies a kappa into the three badge colors', () => {
    expect(kappaBadgeBand(0.8)).toBe('high')
    expect(kappaBadgeBand(0.5)).toBe('medium')
    expect(kappaBadgeBand(0.1)).toBe('low')
  })
})

describe('DEFAULT_QA_THRESHOLDS', () => {
  it('matches the backend defaults (medium 50%, high 75%)', () => {
    expect(DEFAULT_QA_THRESHOLDS).toEqual({ medium: 50, high: 75 })
  })
})

describe('percentageOf', () => {
  it('catches the iteration-1 0%-bug: 17/40 returns 42.5', () => {
    expect(percentageOf(17, 40)).toBe(42.5)
  })

  it('rounds to one decimal place by default', () => {
    expect(percentageOf(1, 3)).toBe(33.3)
    expect(percentageOf(2, 3)).toBe(66.7)
  })

  it('returns 0 (and does not throw) when the total is zero', () => {
    expect(percentageOf(0, 0)).toBe(0)
    expect(percentageOf(5, 0)).toBe(0)
  })

  it('returns 0 for non-finite inputs', () => {
    expect(percentageOf(Number.NaN, 10)).toBe(0)
    expect(percentageOf(5, Number.POSITIVE_INFINITY)).toBe(0)
  })

  it('honors a custom precision', () => {
    expect(percentageOf(1, 3, 2)).toBe(33.33)
    expect(percentageOf(1, 3, 0)).toBe(33)
  })
})

describe('aggregateTaxonomy percentage (was 0% bug)', () => {
  it('reports the actual share — not zero — when the chart payload is read back', () => {
    const dist = aggregateTaxonomy(
      [
        { values: { contribution_type: 'Tool' } },
        { values: { contribution_type: 'Tool' } },
        { values: { contribution_type: 'Framework' } },
        { values: {} },
      ],
      'contribution_type',
      ['Tool', 'Framework'],
    )
    const tool = dist.categories.find(c => c.value === 'Tool')!
    expect(tool.percentage).toBeCloseTo(50)  // 2 / 4 papers
  })

  it('handles total=0 without throwing or producing NaN', () => {
    const dist = aggregateTaxonomy([], 'k', ['A', 'B'])
    for (const c of dist.categories) expect(c.percentage).toBe(0)
  })
})

describe('chartSlug + compactDate + chartFilename', () => {
  it('slugifies project titles into a URL-safe lowercase form', () => {
    expect(chartSlug('JVMTI Usage')).toBe('jvmti-usage')
    expect(chartSlug('   Café  ⚡  Review!  ')).toBe('cafe-review')
  })

  it('collapses empty input to "project"', () => {
    expect(chartSlug('')).toBe('project')
    expect(chartSlug('   ')).toBe('project')
  })

  it('emits YYYYMMDD in UTC', () => {
    expect(compactDate(new Date(Date.UTC(2026, 4, 16)))).toBe('20260516')
    expect(compactDate(new Date(Date.UTC(2024, 0,  3)))).toBe('20240103')
  })

  it('composes the canonical filename pattern', () => {
    expect(chartFilename('JVMTI Usage', 'research-types', new Date(Date.UTC(2026, 4, 16))))
      .toBe('reviq-jvmti-usage-research-types-20260516')
  })
})

describe('categorizeVenue', () => {
  it('@article → Journal', () => {
    expect(categorizeVenue({ entry_type: 'article', venue: 'TOPLAS' })).toBe('Journal')
  })

  it('@inproceedings with conference booktitle → Conference', () => {
    expect(categorizeVenue({ entry_type: 'inproceedings', venue: 'ICSE 2024' })).toBe('Conference')
  })

  it('@inproceedings with workshop booktitle → Workshop', () => {
    expect(categorizeVenue({ entry_type: 'inproceedings', venue: 'ICSE Workshop on Software Reuse' }))
      .toBe('Workshop')
    // case-insensitive
    expect(categorizeVenue({ entry_type: 'inproceedings', venue: 'WORKSHOP on Empirical SE' }))
      .toBe('Workshop')
  })

  it('@incollection → Book chapter', () => {
    expect(categorizeVenue({ entry_type: 'incollection', venue: 'Encyclopedia of SE' }))
      .toBe('Book chapter')
  })

  it('@techreport → Technical report', () => {
    expect(categorizeVenue({ entry_type: 'techreport', venue: 'TR-2023-1' }))
      .toBe('Technical report')
  })

  it('@phdthesis / @mastersthesis → Thesis', () => {
    expect(categorizeVenue({ entry_type: 'phdthesis' })).toBe('Thesis')
    expect(categorizeVenue({ entry_type: 'mastersthesis' })).toBe('Thesis')
  })

  it('@misc with no venue and unknown types → Other', () => {
    expect(categorizeVenue({ entry_type: 'misc' })).toBe('Other')
    expect(categorizeVenue({ entry_type: undefined })).toBe('Other')
    expect(categorizeVenue({ entry_type: 'whatever' })).toBe('Other')
  })

  // ── Fallback: entry_type absent / misc — infer from venue name ────────────

  it('null entry_type + "proceedings" in venue → Conference', () => {
    expect(categorizeVenue({ entry_type: null, venue: 'Proceedings of ICSE 2024' }))
      .toBe('Conference')
    expect(categorizeVenue({ entry_type: null, venue: 'International Symposium on SE' }))
      .toBe('Conference')
  })

  it('null entry_type + "workshop" in venue → Workshop (takes priority over conference)', () => {
    expect(categorizeVenue({ entry_type: null, venue: 'Proceedings of the 5th Workshop on SE' }))
      .toBe('Workshop')
  })

  it('null entry_type + "transactions" or "journal" in venue → Journal', () => {
    expect(categorizeVenue({ entry_type: null, venue: 'IEEE Transactions on Software Engineering' }))
      .toBe('Journal')
    expect(categorizeVenue({ entry_type: null, venue: 'Journal of Systems and Software' }))
      .toBe('Journal')
  })

  it('null entry_type + "thesis" or "dissertation" in venue → Thesis', () => {
    expect(categorizeVenue({ entry_type: null, venue: 'PhD thesis, TU Wien' }))
      .toBe('Thesis')
    expect(categorizeVenue({ entry_type: null, venue: 'doctoral dissertation' }))
      .toBe('Thesis')
  })

  it('null entry_type + "technical report" in venue → Technical report', () => {
    expect(categorizeVenue({ entry_type: null, venue: 'Technical report TR-2023-01' }))
      .toBe('Technical report')
  })

  it('null entry_type + null venue → Other (bottom of fallback chain)', () => {
    expect(categorizeVenue({ entry_type: null, venue: null })).toBe('Other')
    expect(categorizeVenue({})).toBe('Other')
  })
})

describe('aggregateVenueTypes', () => {
  it('always renders the four default categories — zero counts allowed', () => {
    const out = aggregateVenueTypes([])
    expect(out.map(o => o.value)).toEqual([...DEFAULT_VENUE_CATEGORIES])
    expect(out.every(o => o.count === 0)).toBe(true)
    expect(out.every(o => o.percentage === 0)).toBe(true)
  })

  it('counts papers across the four buckets', () => {
    const out = aggregateVenueTypes([
      { entry_type: 'article',       venue: 'TOPLAS' },
      { entry_type: 'inproceedings', venue: 'ICSE 2024' },
      { entry_type: 'inproceedings', venue: 'ICSE 2024' },
      { entry_type: 'inproceedings', venue: 'Workshop on SE' },
      { entry_type: 'misc',          venue: 'arXiv' },
    ])
    const by = Object.fromEntries(out.map(o => [o.value, o.count]))
    expect(by).toMatchObject({ Journal: 1, Conference: 2, Workshop: 1, Other: 1 })
  })

  it('appends extra categories (Thesis, Book chapter, …) only when non-zero', () => {
    const out = aggregateVenueTypes([
      { entry_type: 'phdthesis' },
      { entry_type: 'techreport' },
    ])
    const values = out.map(o => o.value)
    expect(values.slice(0, 4)).toEqual([...DEFAULT_VENUE_CATEGORIES])
    expect(values).toContain('Thesis')
    expect(values).toContain('Technical report')
  })

  it('percentages are share-of-total and use the new percentageOf helper', () => {
    const out = aggregateVenueTypes([
      { entry_type: 'article' }, { entry_type: 'article' },
      { entry_type: 'inproceedings', venue: 'ICSE' },
    ])
    const journal = out.find(o => o.value === 'Journal')!
    const conf    = out.find(o => o.value === 'Conference')!
    expect(journal.percentage).toBeCloseTo(66.7)
    expect(conf.percentage).toBeCloseTo(33.3)
  })

  it('regression: all entry_type=null papers categorise via venue keywords, not all-Other', () => {
    // This covers the reported bug where legacy imports have entry_type=null
    // and every paper was bucketed as "Other" before the keyword fallback.
    const papers = [
      { entry_type: null, venue: 'IEEE Transactions on Software Engineering' },
      { entry_type: null, venue: 'Proceedings of ICSE 2024' },
      { entry_type: null, venue: '15th Workshop on Software Composition' },
      { entry_type: null, venue: 'Some obscure venue' },
    ]
    const out = aggregateVenueTypes(papers)
    const by  = Object.fromEntries(out.map(o => [o.value, o.count]))
    expect(by.Journal).toBe(1)
    expect(by.Conference).toBe(1)
    expect(by.Workshop).toBe(1)
    expect(by.Other).toBe(1)
    // Total should never collapse to just "Other: 4"
    expect(by.Other).not.toBe(4)
  })
})

describe('slice ordering — taxonomy aggregations', () => {
  it('is descending by count then alphabetical for ties', () => {
    const dist = aggregateTaxonomy(
      [
        { values: { k: 'B' } },
        { values: { k: 'A' } },
        { values: { k: 'A' } },
        { values: { k: 'C' } },
        { values: { k: 'C' } },
      ],
      'k',
      ['A', 'B', 'C'],
    )
    expect(dist.categories.map(c => c.value)).toEqual(['A', 'C', 'B'])
  })
})

describe('aggregateKeywords', () => {
  it('splits on comma, semicolon, and pipe and lowercases', () => {
    const papers = [
      { keywords: 'Java, JVM; Bytecode | Profiling' },
      { keywords: 'java, jvmti' },
    ]
    const out = aggregateKeywords(papers)
    const values = out.map(o => o.value)
    expect(values).toContain('java')
    expect(out.find(o => o.value === 'java')?.count).toBe(2)
  })

  it('returns at most topN results sorted descending', () => {
    const papers = Array.from({ length: 10 }, (_, i) => ({
      keywords: `kw${i}, common`,
    }))
    const out = aggregateKeywords(papers, 3)
    expect(out.length).toBe(3)
    expect(out[0].value).toBe('common')
  })

  it('skips papers with no keywords field', () => {
    const papers = [
      { keywords: 'java' },
      { keywords: null },
      { keywords: undefined },
    ]
    const out = aggregateKeywords(papers)
    expect(out.find(o => o.value === 'java')?.count).toBe(1)
  })
})

describe('aggregateTopVenues', () => {
  it('normalises year suffixes so same venue in different years merges', () => {
    const papers = [
      { venue: 'ICSE 2023' },
      { venue: 'ICSE 2024' },
      { venue: 'TSE' },
      { venue: 'TSE' },
    ]
    const out = aggregateTopVenues(papers)
    const icse = out.find(o => o.value === 'ICSE')
    expect(icse).toBeDefined()
    expect(icse!.count).toBe(2)
  })

  it('strips leading ordinals ("9th International…" → "International…")', () => {
    const papers = [
      { venue: '9th International Conference on X' },
      { venue: '10th International Conference on X' },
    ]
    const out = aggregateTopVenues(papers)
    const found = out.find(o => o.value.startsWith('International'))
    expect(found).toBeDefined()
    expect(found!.count).toBe(2)
  })

  it('shows all venues individually — no "Other" bucket', () => {
    const papers = [
      { venue: 'Big Conf' }, { venue: 'Big Conf' }, { venue: 'Big Conf' },
      { venue: 'Solo A' }, { venue: 'Solo B' }, { venue: 'Solo C' },
    ]
    const out = aggregateTopVenues(papers)
    expect(out.find(o => o.value.startsWith('Other'))).toBeUndefined()
    expect(out.find(o => o.value === 'Big Conf')!.count).toBe(3)
    expect(out.find(o => o.value === 'Solo A')).toBeDefined()
  })

  it('collapses "PLDI - 33rd Annual ACM SIGPLAN Conference" with PLDI year editions', () => {
    const papers = [
      { venue: 'PLDI 2019' },
      { venue: 'PLDI 2021' },
      { venue: 'PLDI - 33rd Annual ACM SIGPLAN Conference' },
    ]
    const out = aggregateTopVenues(papers)
    const pldi = out.find(o => o.value === 'PLDI')
    expect(pldi).toBeDefined()
    expect(pldi!.count).toBe(3)
  })

  it('strips "Proceedings of the" prefix and mid-string year', () => {
    const papers = [
      { venue: 'Proceedings of the ICSE 2023' },
      { venue: 'Proceedings of the ICSE 2024' },
      { venue: 'ACM SIGPLAN 2019 Conference on Programming Language Design' },
      { venue: 'ACM SIGPLAN 2020 Conference on Programming Language Design' },
    ]
    const out = aggregateTopVenues(papers)
    expect(out.find(o => o.value === 'ICSE')!.count).toBe(2)
    expect(out.find(o => o.value.startsWith('ACM SIGPLAN'))!.count).toBe(2)
  })

  it('excludes blank-venue papers ("Unknown") from top venues', () => {
    const papers = [
      { venue: '' }, { venue: null }, { venue: '   ' },
      { venue: 'IEEE TSE' }, { venue: 'IEEE TSE' },
    ]
    const out = aggregateTopVenues(papers)
    // "Unknown" must not appear — papers without venue are not a venue
    expect(out.find(o => o.value === 'Unknown')).toBeUndefined()
    expect(out.find(o => o.value === 'IEEE TSE')!.count).toBe(2)
  })
})
