/** The names a reader sees for the keys the database stores.
 *
 * One function for the Import page's per-source table and the PRISMA figure's
 * identification box, which name the same keys and had begun to answer
 * differently.
 */
import { describe, expect, it } from 'vitest'

import { sourceLabel } from './sourceLabel'

describe('source labels', () => {
  it('names a database by its full name', () => {
    expect(sourceLabel('ieee')).toBe('IEEE Xplore')
    expect(sourceLabel('acm')).toBe('ACM Digital Library')
  })

  it('normalises the free-text names legacy imports wrote', () => {
    expect(sourceLabel('Springer Link')).toBe('SpringerLink')
  })

  it('names a grey source by its engine, not by its key', () => {
    // `grey:google` in a column headed "Database" asserts that a search engine
    // is a bibliographic database.
    expect(sourceLabel('grey:google')).toBe('Google')
    expect(sourceLabel('grey:bing')).toBe('Bing')
  })

  it('marks grey literature reached by snowballing as such', () => {
    // Grey literature has its own snowballing, and the two are different rows
    // in the same column of the figure.
    expect(sourceLabel('grey-snowball:google')).toBe('Google (snowballed)')
  })

  it('does not let `mixed` read like the name of an engine', () => {
    // It is `engine_of`'s answer for a package whose runs used more than one.
    expect(sourceLabel('grey:mixed')).toBe('Several engines')
  })

  it('keeps the iteration number of a snowballing round', () => {
    expect(sourceLabel('snowballing:2')).toBe('snowballing: It. 2')
  })

  it('shows an unrecognised key as itself', () => {
    // A hand-typed database name from an old project is still where those
    // papers came from; inventing a label for it would be worse.
    expect(sourceLabel('my-institutional-repository')).toBe('my-institutional-repository')
  })
})
