/**
 * The Import page shows the grey path to a multivocal review and to nobody else.
 *
 * ReviQ has published users, and every one of their projects is a systematic
 * review. A grey-literature card appearing in one of those would be the tool
 * claiming a method the review never used — which is also why the type is read
 * through `isMlr` rather than by comparing the string here: a project created
 * before the column existed comes back without the field.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Search from './Search'
import type { Project } from '../api/types'

const api = vi.hoisted(() => ({
  getProject: vi.fn(),
  getImportStats: vi.fn(),
  getDuplicates: vi.fn(),
  getRetrievals: vi.fn(),
  importBibFile: vi.fn(),
  overrideDedup: vi.fn(),
  importReviewerDecisions: vi.fn(),
  importGreyFromRetrieval: vi.fn(),
  importGreyPackage: vi.fn(),
}))
vi.mock('../api/client', () => api)
vi.mock('../App', () => ({ useProject: () => ({ projectId: 1 }) }))

function renderPage(project: Partial<Project> | null) {
  api.getProject.mockResolvedValue(project)
  api.getImportStats.mockResolvedValue({
    by_source: {}, total_papers: 0, total_original: 0, total_duplicates: 0,
  })
  api.getDuplicates.mockResolvedValue([])
  api.getRetrievals.mockResolvedValue([])
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Search />
    </QueryClientProvider>,
  )
}

const greyCard = () => screen.queryByText('Import Grey Literature')

beforeEach(() => { Object.values(api).forEach(fn => fn.mockReset()) })

describe('who sees the grey-literature path', () => {
  it('a multivocal review does', async () => {
    renderPage({ id: 1, review_type: 'mlr' } as Partial<Project>)

    expect(await screen.findByText('Import Grey Literature')).toBeInTheDocument()
  })

  it('a systematic review does not', async () => {
    renderPage({ id: 1, review_type: 'slr' } as Partial<Project>)

    await screen.findByText('Import BibTeX File')
    expect(greyCard()).toBeNull()
    expect(api.getRetrievals).not.toHaveBeenCalled()
  })

  it('a project from before the column existed does not', async () => {
    // An absent value must degrade to `slr`. Treating it as multivocal would
    // put a grey card into every existing user's review.
    renderPage({ id: 1 } as Partial<Project>)

    await screen.findByText('Import BibTeX File')
    expect(greyCard()).toBeNull()
  })

  it('a misspelled value does not', async () => {
    renderPage({ id: 1, review_type: 'MLR ' } as Partial<Project>)

    await screen.findByText('Import BibTeX File')
    expect(greyCard()).toBeNull()
  })

  it('nothing is shown while the project is still loading', async () => {
    // The card must not appear and then vanish: `isMlr(undefined)` is `slr`.
    renderPage({ id: 1, review_type: 'mlr' } as Partial<Project>)

    expect(greyCard()).toBeNull()
    await waitFor(() => expect(greyCard()).toBeInTheDocument())
  })
})

describe('the BibTeX path is untouched', () => {
  it('still asks which database a file came from', async () => {
    renderPage({ id: 1, review_type: 'mlr' } as Partial<Project>)

    await screen.findByText('Import Grey Literature')
    // A .bib file has no record of where it was downloaded from, so this one
    // stays a dropdown — unlike the engine of a grey package.
    expect(screen.getByRole('combobox')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Choose \.bib File/ })).toBeInTheDocument()
  })
})
