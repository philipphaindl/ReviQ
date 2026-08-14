/** Why a grey source could not be read, in words a reviewer can use.
 *
 * The keys mirror `LABELS` in `backend/app/retrieval/outcome.py` and must stay
 * complete against it, the way `components/streams.ts` mirrors
 * `services/streams.py`. A missing key is not a crash — the raw term is shown
 * instead — which is exactly why it goes unnoticed: the pilot corpus produces
 * `no_main_content` 14 times and `bad_request` 3 times, and the first copy of
 * this map had neither.
 *
 * It also had two keys the retrieval side never emits, `platform_post` and
 * `proxy_rejected`, and gave `no_article_text` the other one's meaning. A
 * platform post would have been reported as markup carrying no article text —
 * a statement about the wrong thing, in a dataset view a reviewer is meant to
 * take at face value.
 *
 * Phrased as a finding about the source rather than about the tool, for the
 * reason `outcome.py` gives: "excluded, behind publisher access control" is a
 * scope decision a reviewer can assess; "fetch error" is not. Lowercase
 * fragments, because every caller renders them inside a sentence.
 */
export const RETRIEVAL_REASONS: Record<string, string> = {
  bot_challenge: 'a firewall or bot challenge answered instead of the page',
  origin_unreachable: 'the origin did not answer (commonly publisher access control)',
  access_denied: 'access was refused (401/403)',
  quota_exhausted: 'the retrieval budget ran out — not a property of the source',
  transport_error: 'a local network failure during retrieval',
  not_found: 'gone — the link had rotted (404/410)',
  bad_request: 'the request itself was rejected by the proxy',
  fetch_failed: 'retrieval failed, cause not recorded',
  no_main_content: 'retrieved, but the markup carried no article text',
  no_text_layer: 'a PDF without a text layer (not OCR-ed)',
  no_article_text: 'a platform post or video rather than a document',
  unsupported_media: 'neither HTML nor PDF',
  extractor_crashed: 'the text extractor failed on these bytes',
  never_attempted: 'no retrieval was attempted',
}

/** The reason in words, or the raw term when it is one this build does not
 *  know — never nothing, since the record was still identified. */
export function reasonLabel(reason?: string | null): string | null {
  if (!reason) return null
  return RETRIEVAL_REASONS[reason] ?? reason
}
