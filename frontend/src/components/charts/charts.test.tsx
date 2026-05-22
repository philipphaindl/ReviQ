/**
 * Render snapshots + behavioural assertions for the four synthesis-chart
 * components. We rely on data-testids and class/text assertions rather than
 * brittle full-tree snapshots so a Recharts release that re-orders internal
 * markup doesn't churn the diff.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  binQAScores, aggregateTaxonomy, aggregateExtractionField,
} from '../../utils/charts'
import type { KappaResult } from '../../api/types'
import {
  BAND_FILL, ExtractionFieldChart, KappaCard, QAScoreDistributionChart,
  TaxonomyBarColumn,
} from './index'
import { Donut } from './Donut'


describe('QAScoreDistributionChart', () => {
  it('renders the band legend with the three status tokens', () => {
    const bins = binQAScores([{ key: 'a', percentage: 80 }])
    render(<QAScoreDistributionChart bins={bins} thresholds={{ medium: 50, high: 75 }} />)
    const legend = screen.getByLabelText('band legend')
    expect(legend).toHaveTextContent('Low')
    expect(legend).toHaveTextContent('Medium')
    expect(legend).toHaveTextContent('High')
  })

  it('mounts the chart root with the expected testid', () => {
    const bins = binQAScores([])
    render(<QAScoreDistributionChart bins={bins} thresholds={{ medium: 50, high: 75 }} />)
    expect(screen.getByTestId('qa-distribution-chart')).toBeInTheDocument()
  })

  it('matches a stable snapshot of the legend swatch colors', () => {
    const bins = binQAScores([{ key: 'a', percentage: 80 }])
    const { container } = render(
      <QAScoreDistributionChart bins={bins} thresholds={{ medium: 50, high: 75 }} />
    )
    const swatchColors = Array.from(container.querySelectorAll('.w-2\\.5'))
      .map(el => (el as HTMLElement).style.backgroundColor)
    // Traffic-light palette: bright red / amber / green.
    expect(swatchColors).toMatchInlineSnapshot(`
      [
        "rgb(220, 38, 38)",
        "rgb(245, 158, 11)",
        "rgb(22, 163, 74)",
      ]
    `)
  })
})


describe('TaxonomyBarColumn', () => {
  const dist = aggregateTaxonomy(
    [
      { values: { contribution_type: 'Tool' } },
      { values: { contribution_type: 'Tool' } },
      { values: { contribution_type: 'Framework' } },
    ],
    'contribution_type',
    ['Framework', 'Method', 'Tool'],
  )

  it('uses a stable testid keyed on the taxonomy dimension', () => {
    render(<TaxonomyBarColumn dist={dist} />)
    expect(screen.getByTestId('taxonomy-bars-contribution_type')).toBeInTheDocument()
  })

  it('renders the human-readable dimension label as a header', () => {
    render(<TaxonomyBarColumn dist={dist} />)
    expect(screen.getByText('Contribution Type')).toBeInTheDocument()
  })

  it('renders every category from the schema, including empty ones', () => {
    render(<TaxonomyBarColumn dist={dist} />)
    // Recharts renders the YAxis ticks AND a duplicate measurement layer; we
    // only need each label to appear at least once.
    expect(screen.getAllByText('Tool').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Framework').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Method').length).toBeGreaterThan(0)
  })
})


describe('KappaCard', () => {
  const baseKappa: KappaResult = {
    kappa: 0.732, kappa_ci_lower: 0.55, kappa_ci_upper: 0.91,
    pabak: 0.81, observed_agreement: 0.9, n_papers: 42,
    n_agree_include: 20, n_agree_exclude: 15, n_disagree: 7,
    interpretation: 'Substantial agreement',
    r1_name: 'Alice', r2_name: 'Bob', phase: 'screening',
  }

  it('renders the κ point estimate and its 95% CI in tabular figures', () => {
    render(<KappaCard phaseLabel="Screening" kappa={baseKappa} />)
    expect(screen.getByText('0.732')).toBeInTheDocument()
    // The 95% CI line wraps the bracketed range inside a span; match the body
    // text without assuming a specific element split.
    // The 95% CI label sits in its own muted span next to the κ point estimate.
    expect(screen.getByText(/95% CI \[0\.550, 0\.910\]/)).toBeInTheDocument()
    expect(screen.getByText('0.810')).toBeInTheDocument()
  })

  it('badges substantial agreement with the high-band token color', () => {
    render(<KappaCard phaseLabel="Screening" kappa={baseKappa} />)
    const badge = screen.getByText('Substantial agreement')
    expect(badge).toHaveStyle(`background-color: ${BAND_FILL.high}`)
  })

  it('badges poor agreement with the low-band token color', () => {
    const poor = { ...baseKappa, kappa: -0.1, interpretation: 'Poor agreement (less than chance)' }
    render(<KappaCard phaseLabel="Full Text" kappa={poor} />)
    const badge = screen.getByText('Poor agreement (less than chance)')
    expect(badge).toHaveStyle(`background-color: ${BAND_FILL.low}`)
  })

  it('renders the reviewer-pair header', () => {
    render(<KappaCard phaseLabel="Screening" kappa={baseKappa} />)
    // The phase label and the reviewer pair line are now stacked separately.
    expect(screen.getByText('Screening')).toBeInTheDocument()
    expect(screen.getByText(/Alice\s+vs\.\s+Bob/)).toBeInTheDocument()
  })
})


describe('Donut', () => {
  const data = [
    { value: 'Tool',       count: 10, percentage: 50 },
    { value: 'Framework',  count:  6, percentage: 30 },
    { value: 'Method',     count:  4, percentage: 20 },
  ]
  const zeroData = [
    { value: 'Tool',       count: 10, percentage: 100 },
    { value: 'Framework',  count:  0, percentage:   0 },
  ]

  it('renders an svg element for the chart', () => {
    const { container } = render(<Donut data={data} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders one straight <line> connector per non-zero slice', () => {
    const { container } = render(<Donut data={data} />)
    // All connectors are straight radial <line> elements — no polylines.
    const lines     = container.querySelectorAll('line')
    const polylines = container.querySelectorAll('polyline')
    expect(lines.length).toBe(3)
    expect(polylines.length).toBe(0)
  })

  it('renders the category name and count·pct on each slice label', () => {
    render(<Donut data={data} />)
    // Each category name appears in an SVG tspan.
    expect(screen.getAllByText('Tool').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Framework').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Method').length).toBeGreaterThan(0)
  })

  it('renders only non-zero slices — zero-count categories produce no connector', () => {
    const { container } = render(<Donut data={zeroData} />)
    // Only 1 non-zero slice ("Tool") → exactly 1 <line> connector.
    expect(container.querySelectorAll('line').length).toBe(1)
    expect(container.querySelectorAll('polyline').length).toBe(0)
  })

  it('renders the empty-state ring when all counts are zero', () => {
    const { container } = render(<Donut data={[{ value: 'A', count: 0, percentage: 0 }]} />)
    // No path elements (no slices), just the neutral circle.
    expect(container.querySelector('circle')).toBeInTheDocument()
    expect(container.querySelectorAll('polyline').length).toBe(0)
  })

  it('all connectors are <line> elements — no <polyline> elements anywhere', () => {
    // The simplified spec uses only straight radial lines; elbows are removed.
    const crowded = [
      { value: 'Big', count: 90, percentage: 90 },
      { value: 'T1',  count:  2, percentage:  2 },
      { value: 'T2',  count:  2, percentage:  2 },
      { value: 'T3',  count:  2, percentage:  2 },
      { value: 'T4',  count:  2, percentage:  2 },
      { value: 'T5',  count:  2, percentage:  2 },
    ]
    const { container } = render(<Donut data={crowded} />)
    expect(container.querySelectorAll('polyline').length).toBe(0)
    expect(container.querySelectorAll('line').length).toBe(6)  // one per non-zero slice
  })

  // ── Worst-case margin verification ─────────────────────────────────────────
  it('viewBox expands to contain long labels at all four compass-point angles', () => {
    // 4 segments of 25 % each.  Their midpoints land at exactly the compass
    // points (-π/2 = top, 0 = right, π/2 = bottom, π = left) when the sweep
    // is π/2 and the start angles are chosen accordingly.
    // We can verify this by using equal-count slices and checking that:
    //   a) the SVG's viewBox is not a fixed fallback value
    //   b) the viewBox is wide/tall enough to contain the text at each extreme.
    //
    // With 4 × 25 % slices starting at -π (so their mids hit -3π/4, -π/4,
    // π/4, 3π/4 — all 45° from the compass points), the labels are still at
    // the extremes of the donut perimeter.  Use the simpler equal fixture:
    const compass = [
      { value: 'Eighteen chars ab',  count: 25, percentage: 25 },
      { value: 'Another long label', count: 25, percentage: 25 },
      { value: 'Third long-name xy', count: 25, percentage: 25 },
      { value: 'Fourth label value', count: 25, percentage: 25 },
    ]
    const { container } = render(<Donut data={compass} />)
    const svg = container.querySelector('svg')!
    expect(svg).toBeInTheDocument()

    // Parse the viewBox attribute: "x y w h"
    const vb = svg.getAttribute('viewBox')!.split(' ').map(Number)
    const vbW = vb[2], vbH = vb[3]

    // With 4 equal 25 % slices (size=240, ro=106):
    //   BASE_EXT = max(48, 106*0.35) = 48
    //   label text: "Eighteen chars ab" = 18 chars → width ≈ 18 * 6.5 = 117 px
    //   margin ≈ 48 + 4 + 117 + 8 = 177 px per side, so padH = padV ≈ 177
    //   vbW = 2 * 106 + 2 * 177 = 566, vbH ≈ same
    // We assert a minimum that is clearly larger than the bare ring (2*106=212)
    // but don't pin the exact value (it depends on angle distribution).
    expect(vbW).toBeGreaterThan(400)
    expect(vbH).toBeGreaterThan(400)
    // And there must be one connector per slice
    expect(container.querySelectorAll('line').length).toBe(4)
  })
})


describe('ExtractionFieldChart', () => {
  it('mounts the chart root with a stable testid', () => {
    const cats = aggregateExtractionField(
      [{ values: { usage: 'Direct' } }, { values: { usage: 'Indirect' } }],
      'usage',
    )
    render(<ExtractionFieldChart categories={cats} />)
    expect(screen.getByTestId('extraction-field-chart')).toBeInTheDocument()
  })

  it('renders one tick per category', () => {
    const cats = aggregateExtractionField(
      [
        { values: { usage: 'Direct' } },
        { values: { usage: 'Indirect' } },
        { values: { usage: 'Mixed' } },
      ],
      'usage',
    )
    render(<ExtractionFieldChart categories={cats} />)
    // Recharts re-renders some tick labels for layout measurement, so we just
    // assert each category label appears at least once.
    expect(screen.getAllByText('Direct').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Indirect').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Mixed').length).toBeGreaterThan(0)
  })
})
