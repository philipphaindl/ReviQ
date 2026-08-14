/**
 * The dataset view's two non-negotiables.
 *
 * D31: full text is never rendered without the retrieval status it was
 * extracted under. Two of the pilot corpus's five non-`ok` texts are
 * bot-challenge boilerplate ("Checking your browser before accessing…"), and a
 * panel that showed them unqualified would put a Cloudflare interstitial in
 * front of a reviewer as though it were the document.
 *
 * And: what a model wrote is never presented as what the source wrote.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import GreyRecordPanel from './GreyRecordPanel'
import type { GreyRecord } from '../api/types'

const getGreyRecord = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({ getGreyRecord }))

function source(over: Partial<GreyRecord['source']> = {}): GreyRecord['source'] {
  return {
    id: 1, paper_id: 7,
    record_key: 'oecd-org-3f2a91c0',
    canonical_url: 'https://oecd.org/ai-maturity',
    source_url: 'https://www.oecd.org/ai-maturity/',
    host: 'oecd.org',
    retrieved_at_utc: '2026-08-11T19:36:06Z',
    sha256: 'a'.repeat(64),
    media_type: 'html', content_length: 51234, word_count: 4210,
    archive_filename: 'snapshots.warc.gz', archive_offset: 56108,
    archive_record_id: '<urn:uuid:fefa3433>',
    retrieval_status: 'ok', retrieval_reason: null,
    search_observations: 2, best_rank: 3,
    ...over,
  }
}

function renderPanel(record: GreyRecord | Error) {
  if (record instanceof Error) getGreyRecord.mockRejectedValue(record)
  else getGreyRecord.mockResolvedValue(record)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <GreyRecordPanel pid={1} paperId={7} />
    </QueryClientProvider>,
  )
}

beforeEach(() => { getGreyRecord.mockReset() })

describe('provenance', () => {
  it('shows what makes the source citable: date, digest, archive', async () => {
    renderPanel({ paper_id: 7, source: source(), full_text: null, figures: [] })

    expect(await screen.findByText('2026-08-11T19:36:06Z')).toBeInTheDocument()
    expect(screen.getByText('a'.repeat(64))).toBeInTheDocument()
    expect(screen.getByText(/snapshots\.warc\.gz @ 56108/)).toBeInTheDocument()
  })

  it('warns that the live page is not the archived evidence', async () => {
    renderPanel({ paper_id: 7, source: source(), full_text: null, figures: [] })

    expect(await screen.findByText(/may differ from what was archived/i))
      .toBeInTheDocument()
  })
})

describe('full text and its status (D31)', () => {
  const blocked: GreyRecord = {
    paper_id: 7,
    source: source({ retrieval_status: 'blocked', retrieval_reason: 'bot_challenge' }),
    full_text: {
      id: 1, paper_id: 7,
      text: 'Checking your browser before accessing pubmed.ncbi.nlm.nih.gov',
      word_count: 18, extractor: 'trafilatura-2.2.0',
      extraction_error: null, retrieval_status: 'blocked',
    },
    figures: [],
  }

  it('never shows text from a failed retrieval without saying so', async () => {
    renderPanel(blocked)

    expect(await screen.findByText(/Checking your browser/)).toBeInTheDocument()
    expect(screen.getByText(/did not succeed/i)).toBeInTheDocument()
    expect(screen.getByText(/may be the document, or it may be the block page/i))
      .toBeInTheDocument()
  })

  it('marks the status on the text itself, not only on the provenance', async () => {
    renderPanel(blocked)
    expect(await screen.findByText('Retrieval: blocked')).toBeInTheDocument()
  })

  it('does not raise the warning for a clean retrieval', async () => {
    renderPanel({
      paper_id: 7, source: source(),
      full_text: {
        id: 1, paper_id: 7, text: 'The real body of the document.',
        word_count: 4210, extractor: 'trafilatura-2.2.0',
        extraction_error: null, retrieval_status: 'ok',
      },
      figures: [],
    })

    expect(await screen.findByText('The real body of the document.')).toBeInTheDocument()
    expect(screen.queryByText(/did not succeed/i)).not.toBeInTheDocument()
    expect(screen.getByText('Retrieval: ok')).toBeInTheDocument()
  })

  it('distinguishes "nothing was retrieved" from "the page had no prose"', async () => {
    renderPanel({
      paper_id: 7,
      source: source({ retrieval_status: 'blocked', retrieval_reason: 'origin_unreachable',
                       sha256: null }),
      full_text: null, figures: [],
    })

    expect(await screen.findByText(/Nothing was extracted/i)).toBeInTheDocument()
    // The raw vocabulary is translated: a reviewer should not have to learn
    // the retrieval side's terms to know what happened.
    expect(screen.getByText(/publisher access control/i)).toBeInTheDocument()
    expect(screen.getByText(/no bytes were retrieved/i)).toBeInTheDocument()
  })

  it('still says the record counts as identified when nothing was read', async () => {
    renderPanel({
      paper_id: 7, source: source({ retrieval_status: 'failed' }),
      full_text: null, figures: [],
    })

    expect(await screen.findByText(/still counts as identified/i)).toBeInTheDocument()
  })
})

describe('figures', () => {
  const withFigure: GreyRecord = {
    paper_id: 7, source: source(), full_text: null,
    figures: [{
      id: 3, paper_id: 7,
      raw_src: '/img/fig1.png', resolved_url: 'https://oecd.org/img/fig1.png',
      alt_text: 'Maturity levels', caption: 'Figure 1: the five levels',
      sha256: 'b'.repeat(64), content_type: 'image/png', byte_size: 20481,
      archive_filename: 'figures.warc.gz', archive_offset: 4096,
      archive_record_id: '<urn:uuid:aa>', fetch_error: null,
      descriptions: [{
        id: 9, grey_figure_id: 3,
        description: 'A staircase of five levels.',
        model: 'claude-haiku-4-5', prompt: 'Describe this figure.',
        described_at_utc: '2026-08-11T20:00:00Z', error: null,
      }],
    }],
  }

  it("labels model output as not the source's words", async () => {
    renderPanel(withFigure)

    expect(await screen.findByText('A staircase of five levels.')).toBeInTheDocument()
    expect(screen.getByText(/not the source's words/i)).toBeInTheDocument()
  })

  it('keeps the source\'s own caption separate from the generated text', async () => {
    renderPanel(withFigure)

    expect(await screen.findByText('Figure 1: the five levels')).toBeInTheDocument()
    expect(screen.getByText(/Alt text: Maturity levels/)).toBeInTheDocument()
  })

  it('attributes the description to a named model', async () => {
    renderPanel(withFigure)
    expect(await screen.findByText(/claude-haiku-4-5/)).toBeInTheDocument()
  })

  it('records that an image existed even when it could not be fetched', async () => {
    renderPanel({
      paper_id: 7, source: source(), full_text: null,
      figures: [{
        ...withFigure.figures[0], fetch_error: '403', sha256: null, descriptions: [],
      }],
    })

    expect(await screen.findByText('Not fetched')).toBeInTheDocument()
    expect(screen.getByText(/could not read it: 403/i)).toBeInTheDocument()
  })
})

describe('a paper with no retrieval', () => {
  it('says so plainly rather than showing an empty provenance block', async () => {
    renderPanel(new Error('404'))

    await waitFor(() =>
      expect(screen.getByText(/No retrieved record for this paper/i))
        .toBeInTheDocument())
    expect(screen.queryByText(/SHA-256/i)).not.toBeInTheDocument()
  })
})
