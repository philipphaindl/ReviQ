/** The map has to stay complete against the retrieval side's vocabulary.
 *
 * `backend/app/retrieval/outcome.py` owns the terms. A key missing here shows
 * a reviewer the raw term instead of a sentence — no crash, no test failure,
 * just a dataset view saying `no_main_content` at someone. The pilot corpus
 * produces seven distinct reasons across its 66 unreadable sources.
 */
import { describe, expect, it } from 'vitest'

import { RETRIEVAL_REASONS, reasonLabel } from './retrievalReasons'

/** The keys of `LABELS` in `backend/app/retrieval/outcome.py`, mirrored the way
 *  `streams.test.ts` mirrors `test_streams.py`: change one, change the other. */
const BACKEND_REASONS = [
  'bot_challenge', 'origin_unreachable', 'access_denied', 'quota_exhausted',
  'transport_error', 'not_found', 'bad_request', 'fetch_failed',
  'no_main_content', 'no_text_layer', 'no_article_text', 'unsupported_media',
  'extractor_crashed', 'never_attempted',
]

describe('retrieval reasons', () => {
  it('covers every reason the retrieval side emits', () => {
    expect(Object.keys(RETRIEVAL_REASONS).sort()).toEqual([...BACKEND_REASONS].sort())
  })

  it('distinguishes a platform post from markup without article text', () => {
    // These two were one entry, under the wrong key. The pilot corpus has both:
    // 7 platform posts and 14 pages whose markup carried no article text.
    expect(RETRIEVAL_REASONS.no_article_text).toMatch(/platform post/)
    expect(RETRIEVAL_REASONS.no_main_content).toMatch(/no article text/)
  })

  it('names publisher access control, which is what a reader needs to assess', () => {
    expect(RETRIEVAL_REASONS.origin_unreachable).toMatch(/publisher access control/)
  })

  it('shows an unknown term rather than nothing', () => {
    // The record was identified either way; swallowing the reason would make
    // it look as though none had been recorded.
    expect(reasonLabel('a_reason_from_a_newer_backend')).toBe('a_reason_from_a_newer_backend')
    expect(reasonLabel(null)).toBeNull()
    expect(reasonLabel(undefined)).toBeNull()
  })
})
