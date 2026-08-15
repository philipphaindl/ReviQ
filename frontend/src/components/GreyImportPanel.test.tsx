/**
 * What the import page promises about grey literature.
 *
 * The retrieval half is proven; this is the half a user touches. Three rules
 * run through it, each from a decision rather than taste: the engine label is
 * never a field, credentials are never a field, and a retrieval that would
 * import nothing says so before the button is pressed rather than after.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import GreyImportPanel from './GreyImportPanel'
import type { GreyImportResult, Retrieval } from '../api/types'

const { getRetrievals, importGreyFromRetrieval, importGreyPackage } = vi.hoisted(() => ({
  getRetrievals: vi.fn(),
  importGreyFromRetrieval: vi.fn(),
  importGreyPackage: vi.fn(),
}))
vi.mock('../api/client', () => ({
  getRetrievals, importGreyFromRetrieval, importGreyPackage,
}))

function retrieval(over: Partial<Retrieval> = {}): Retrieval {
  return {
    kind: 'batch',
    scope_id: '4f1c9a2e-77b0-4d1e-9a3c-2b8e5d0f1a66',
    queries: ['ai maturity model', 'ai readiness assessment', 'ai capability framework'],
    engines: ['google'],
    started_at_utc: '2026-08-11T19:36:06Z',
    documents: 424,
    runs: 28,
    incomplete: false,
    already_imported: false,
    imports: 0,
    records_added: 0,
    ...over,
  }
}

function result(over: Partial<GreyImportResult> = {}): GreyImportResult {
  return {
    grey_import_id: 1,
    engine: 'google',
    scope: { kind: 'batch', id: '4f1c9a2e' },
    queries: 28,
    total_in_package: 424,
    imported_unique: 380,
    imported_duplicates: 40,
    already_present: 3,
    skipped_no_citekey: 1,
    imported_unretrievable: 22,
    unretrievable_by_reason: { bot_challenge: 14, not_found: 8 },
    package_reported: { documents: 424, usable: 402 },
    imported_citekeys: [], duplicate_citekeys: [], already_present_citekeys: [],
    ...over,
  }
}

function renderPanel(retrievals: Retrieval[] | Error = []) {
  if (retrievals instanceof Error) getRetrievals.mockRejectedValue(retrievals)
  else getRetrievals.mockResolvedValue(retrievals)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <GreyImportPanel pid={1} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getRetrievals.mockReset()
  importGreyFromRetrieval.mockReset()
  importGreyPackage.mockReset()
})

describe('choosing a retrieval', () => {
  it('imports one without anyone typing a UUID', async () => {
    const r = retrieval()
    importGreyFromRetrieval.mockResolvedValue(result())
    renderPanel([r])

    fireEvent.click(await screen.findByRole('button', { name: 'Import' }))

    await waitFor(() =>
      expect(importGreyFromRetrieval).toHaveBeenCalledWith(1, r.scope_id))
    // There is no text input to type one into, either.
    expect(document.querySelectorAll('input[type="text"]')).toHaveLength(0)
  })

  it('describes a retrieval by what it searched, not by its id', async () => {
    renderPanel([retrieval()])

    expect(await screen.findByText(/ai maturity model/)).toBeInTheDocument()
    expect(screen.getByText(/\+2 more/)).toBeInTheDocument()
    expect(screen.getByText('424')).toBeInTheDocument()
  })

  it('names the engine from the runs and offers no way to change it', async () => {
    renderPanel([retrieval({ engines: ['google', 'bing'] })])

    expect(await screen.findByText('google, bing')).toBeInTheDocument()
    // A hand-typed label could contradict the runs, so there is no dropdown.
    expect(document.querySelectorAll('select')).toHaveLength(0)
  })

  it('never offers a field for a search-engine key', async () => {
    renderPanel([retrieval()])
    await screen.findByRole('button', { name: 'Import' })

    expect(document.querySelectorAll('input[type="password"]')).toHaveLength(0)
    // The only input is the package file picker.
    const inputs = Array.from(document.querySelectorAll('input'))
    expect(inputs.map(i => i.type)).toEqual(['file'])
  })
})

describe('what a user is told before pressing the button', () => {
  it('says what an earlier import of this scope brought in', async () => {
    renderPanel([retrieval({ already_imported: true, imports: 1, records_added: 423 })])

    expect(await screen.findByText('Imported · 423 records')).toBeInTheDocument()
    // Still possible — it simply counts every record as already present — but
    // the label says which button this is.
    expect(screen.getByRole('button', { name: 'Import again' })).toBeInTheDocument()
  })

  it('says so when an import of this scope brought nothing', async () => {
    // The case that made the listing useless to read: press every row once and
    // "already imported" is on all of them, distinguishing nothing. A run whose
    // documents the batch already carried added exactly zero.
    renderPanel([retrieval({ already_imported: true, imports: 1, records_added: 0 })])

    expect(await screen.findByText('Imported · nothing new')).toBeInTheDocument()
  })

  it('refuses a scope that has no documents of its own', async () => {
    // A refetch or re-extraction run re-reads what an earlier retrieval found.
    // Saying so at the button beats saying it in the result afterwards.
    renderPanel([retrieval({ documents: 0, engines: ['none'] })])

    expect(await screen.findByText('Nothing to import')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled()
  })

  it('marks a partial corpus and says what that means for the counts', async () => {
    renderPanel([retrieval({ incomplete: true })])

    expect(await screen.findByText('Incomplete')).toBeInTheDocument()
    expect(screen.getByText(/fewer than its query set asked for/)).toBeInTheDocument()
  })

  it('says a project has made no retrievals rather than showing an empty table', async () => {
    renderPanel([])

    expect(await screen.findByText(/made no retrievals yet/)).toBeInTheDocument()
  })

  it('keeps the package path open when the retrieval database cannot be read', async () => {
    renderPanel(new Error('no such table: runs'))

    expect(await screen.findByText(/retrieval database could not be read/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Choose package file' })).toBeInTheDocument()
  })
})

describe('what an import reports', () => {
  it('shows the four disjoint counts that add up to the package', async () => {
    importGreyFromRetrieval.mockResolvedValue(result())
    renderPanel([retrieval()])
    fireEvent.click(await screen.findByRole('button', { name: 'Import' }))

    expect(await screen.findByText('In package')).toBeInTheDocument()
    for (const [label, value] of [
      ['In package', '424'], ['Imported unique', '380'], ['Duplicates', '40'],
      ['Already in project', '3'], ['Skipped (no key)', '1'],
    ] as const) {
      const cell = screen.getByText(label).parentElement!
      expect(cell.textContent).toContain(value)
    }
  })

  it('reports what was identified but never readable, by cause', async () => {
    // A review that cannot say how much of its grey literature had rotted or
    // sat behind a wall is hiding a limitation rather than not having one.
    importGreyFromRetrieval.mockResolvedValue(result())
    renderPanel([retrieval()])
    fireEvent.click(await screen.findByRole('button', { name: 'Import' }))

    expect(await screen.findByText('Imported, not retrievable')).toBeInTheDocument()
    expect(screen.getByText(/firewall or bot challenge/)).toBeInTheDocument()
    expect(screen.getByText(/the link had rotted/)).toBeInTheDocument()
  })

  it('does not pass the package\'s causes off as an account of what it imported', async () => {
    // Re-importing a run this project already holds: nothing was written, yet
    // the package still contains unreadable sources. The two numbers describe
    // different populations, and the list has to say which is which.
    importGreyFromRetrieval.mockResolvedValue(result({
      total_in_package: 8, imported_unique: 0, imported_duplicates: 0,
      already_present: 8, skipped_no_citekey: 0,
      imported_unretrievable: 0,
      unretrievable_by_reason: { origin_unreachable: 1 },
    }))
    renderPanel([retrieval()])
    fireEvent.click(await screen.findByRole('button', { name: 'Import' }))

    expect(await screen.findByText(/including\s+records this project already had/))
      .toBeInTheDocument()
  })

  it('says a scope carried nothing rather than showing a row of zeros', async () => {
    // The button is disabled for a scope the listing already knows is empty,
    // so this is the other route to it: a scope that looked importable and
    // turned out to build an empty package.
    importGreyFromRetrieval.mockResolvedValue(result({
      total_in_package: 0, imported_unique: 0, imported_duplicates: 0,
      already_present: 0, skipped_no_citekey: 0, imported_unretrievable: 0,
      unretrievable_by_reason: {}, package_reported: { documents: 0, usable: 0 },
    }))
    renderPanel([retrieval({ documents: 2 })])
    fireEvent.click(await screen.findByRole('button', { name: 'Import' }))

    expect(await screen.findByText(/carried no documents, so nothing was imported/))
      .toBeInTheDocument()
  })

  it('surfaces a package whose own total disagrees with its records', async () => {
    importGreyFromRetrieval.mockResolvedValue(
      result({ total_in_package: 400, package_reported: { documents: 424, usable: 402 } }))
    renderPanel([retrieval()])
    fireEvent.click(await screen.findByRole('button', { name: 'Import' }))

    expect(await screen.findByText(/reports 424 documents but carries 400/))
      .toBeInTheDocument()
  })

  it('repeats the server\'s own words when a package is rejected', async () => {
    // `parse_package` names the command that produces a valid package; an
    // "Import failed" of our own would throw away the actionable half.
    importGreyPackage.mockRejectedValue({
      response: { data: { detail: 'expected a reviq-grey-v1 package, got None' } },
    })
    renderPanel([])
    await screen.findByText(/made no retrievals yet/)

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, {
      target: { files: [new File(['{}'], 'records.json', { type: 'application/json' })] },
    })

    expect(await screen.findByText(/expected a reviq-grey-v1 package/)).toBeInTheDocument()
  })
})
