/** The dataset view for one grey source.
 *
 * A formal paper is identified by a DOI and can be looked up again. A grey
 * source cannot: the page may be edited or gone by the time anyone checks, so
 * the retrieval timestamp, the digest of the bytes that were read, and where
 * those bytes are archived *are* the citation. This panel puts those in front
 * of the reviewer alongside the text itself.
 *
 * Two rules run through the layout, both of them from real failure modes
 * rather than taste:
 *
 * 1. **Text is never shown without the status it was extracted under** (D31).
 *    `FullTextBlock` takes the whole `GreyFullText` object rather than a
 *    string, so there is no way to call it with the text alone. Under a bot
 *    challenge the extractor returns whatever the page served: in the pilot
 *    corpus that is genuine content three times and the challenge page's own
 *    "Checking your browser before accessing…" twice, with nothing to
 *    distinguish them mechanically.
 *
 * 2. **What a model wrote is never styled like what the source wrote.**
 *    `alt_text` and `caption` are the page's own words; a description is
 *    generated text. A review that quoted the second as the first would
 *    attribute a model's sentence to a cited source.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { getGreyRecord } from '../api/client'
import type { GreyFigure, GreyFullText, GreySource } from '../api/types'
import { Badge } from './ui'

/** Plain-language names for the retrieval outcomes. The raw vocabulary
 *  (`origin_unreachable`, `bot_challenge`) is the retrieval side's; a reviewer
 *  reading a dataset view should not have to learn it to know what happened. */
const REASON_LABELS: Record<string, string> = {
  origin_unreachable: 'the origin did not answer (commonly publisher access control)',
  bot_challenge: 'a firewall or bot challenge answered instead of the page',
  no_article_text: 'the markup carried no article text',
  not_found: 'gone — the link had rotted (404/410)',
  platform_post: 'a platform post or video rather than a document',
  proxy_rejected: 'the request itself was rejected by the proxy',
  unsupported_media: 'neither HTML nor PDF',
}

function statusTone(status?: string | null) {
  if (status === 'ok') return 'include' as const
  if (!status) return 'neutral' as const
  return 'uncertain' as const
}

function formatBytes(n?: number | null) {
  if (n == null) return null
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} kB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

// ── Provenance ────────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="stat-label">{label}</p>
      <div className="text-xs text-ink mt-0.5 break-words">{children}</div>
    </div>
  )
}

function Provenance({ source }: { source: GreySource }) {
  const bytes = formatBytes(source.content_length)
  return (
    <div className="bg-paper rounded-[3px] p-3.5">
      <div className="grid grid-cols-2 gap-x-5 gap-y-3">
        <Field label="Retrieved">
          {source.retrieved_at_utc ?? <span className="text-ink-muted">never</span>}
        </Field>
        <Field label="Host">{source.host ?? '—'}</Field>
        <Field label="Type">
          {[source.media_type, bytes].filter(Boolean).join(' · ') || '—'}
        </Field>
        <Field label="Found by">
          {source.search_observations === 1
            ? '1 query'
            : `${source.search_observations} queries`}
          {source.best_rank != null && (
            <span className="text-ink-muted"> · best rank {source.best_rank}</span>
          )}
        </Field>
      </div>

      <div className="mt-3 pt-3 border-t border-rule">
        <Field label="SHA-256 of the bytes read">
          {source.sha256
            ? <code className="font-mono text-2xs break-all">{source.sha256}</code>
            : <span className="text-ink-muted">no bytes were retrieved</span>}
        </Field>
      </div>

      {source.archive_filename && (
        <div className="mt-3">
          <Field label="Archived in">
            <code className="font-mono text-2xs break-all">
              {source.archive_filename}
              {source.archive_offset != null && ` @ ${source.archive_offset}`}
            </code>
          </Field>
        </div>
      )}

      <div className="mt-3">
        <Field label="Canonical URL">
          <a
            href={source.canonical_url}
            target="_blank"
            rel="noreferrer noopener"
            className="text-accent hover:underline break-all"
          >
            {source.canonical_url}
          </a>
          {/* The live page is not the evidence — it may have changed since. */}
          <p className="text-2xs text-ink-muted mt-1">
            Opens the page as it is now, which may differ from what was archived.
          </p>
        </Field>
      </div>
    </div>
  )
}

// ── Full text ─────────────────────────────────────────────────────────────────

const PREVIEW_CHARS = 1500

/** The text, and — inseparably — the status it was extracted under.
 *
 * Takes the whole record rather than a string: passing only the text is not a
 * thing a caller can express, which is the point (D31).
 */
function FullTextBlock({ fullText }: { fullText: GreyFullText }) {
  const [expanded, setExpanded] = useState(false)
  const text = fullText.text ?? ''
  const isLong = text.length > PREVIEW_CHARS
  const shown = expanded || !isLong ? text : text.slice(0, PREVIEW_CHARS)
  const clean = fullText.retrieval_status === 'ok'

  return (
    <div>
      {!clean && (
        <div className="mb-2.5 rounded-[3px] border border-uncertain/30 bg-uncertain/5 px-3 py-2.5">
          <p className="text-xs text-ink font-medium">
            This text came from a retrieval that did not succeed
            {fullText.retrieval_status ? ` (${fullText.retrieval_status})` : ''}.
          </p>
          <p className="text-2xs text-ink-light mt-1 leading-normal">
            The extractor returns whatever the server sent. That may be the
            document, or it may be the block page — read it before treating it
            as the source, and do not screen against it unexamined.
          </p>
        </div>
      )}

      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <Badge
          label={`Retrieval: ${fullText.retrieval_status ?? 'unknown'}`}
          variant={statusTone(fullText.retrieval_status)}
        />
        {fullText.word_count != null && (
          <span className="text-2xs text-ink-muted">
            {fullText.word_count.toLocaleString()} words
          </span>
        )}
        {fullText.extractor && (
          <span className="text-2xs text-ink-muted font-mono">{fullText.extractor}</span>
        )}
      </div>

      {fullText.extraction_error && (
        <p className="text-2xs text-exclude mb-1.5">
          Extraction reported: {fullText.extraction_error}
        </p>
      )}

      <div className="bg-paper rounded-[3px] p-3.5 max-h-96 overflow-y-auto">
        <p className="text-xs text-ink leading-relaxed whitespace-pre-wrap">
          {shown}
          {isLong && !expanded && <span className="text-ink-muted">…</span>}
        </p>
      </div>

      {isLong && (
        <button
          className="btn-ghost btn-sm mt-1.5"
          onClick={() => setExpanded(v => !v)}
        >
          {expanded
            ? 'Show less'
            : `Show all ${text.length.toLocaleString()} characters`}
        </button>
      )}
    </div>
  )
}

// ── Figures ───────────────────────────────────────────────────────────────────

function FigureCard({ figure }: { figure: GreyFigure }) {
  return (
    <div className="border border-rule rounded-[3px] p-3">
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <code className="font-mono text-2xs text-ink-muted break-all">
          {figure.resolved_url ?? figure.raw_src ?? '(no source)'}
        </code>
        {figure.fetch_error && <Badge label="Not fetched" variant="uncertain" />}
      </div>

      {/* Source content: the page's own words about its own image. */}
      {(figure.caption || figure.alt_text) && (
        <div className="mb-2">
          {figure.caption && <p className="text-xs text-ink">{figure.caption}</p>}
          {figure.alt_text && figure.alt_text !== figure.caption && (
            <p className="text-2xs text-ink-light mt-0.5">
              Alt text: {figure.alt_text}
            </p>
          )}
        </div>
      )}

      {figure.fetch_error && (
        <p className="text-2xs text-ink-muted mb-2">
          The source carried this image but the retrieval could not read it:{' '}
          {figure.fetch_error}
        </p>
      )}

      {/* Generated content, deliberately set apart from the block above. */}
      {figure.descriptions.map(d => (
        <div key={d.id} className="mt-2 border-l-2 border-accent/40 pl-2.5">
          <p className="text-2xs uppercase tracking-label text-ink-muted">
            Model description — not the source's words
          </p>
          {d.error
            ? <p className="text-2xs text-exclude mt-0.5">Failed: {d.error}</p>
            : <p className="text-xs text-ink mt-0.5">{d.description}</p>}
          <p className="text-2xs text-ink-muted mt-1 font-mono break-words">
            {d.model ?? 'unknown model'}
            {d.described_at_utc ? ` · ${d.described_at_utc}` : ''}
          </p>
          {d.prompt && (
            <details className="mt-1">
              <summary className="text-2xs text-ink-muted cursor-pointer hover:text-ink">
                Prompt
              </summary>
              <p className="text-2xs text-ink-light mt-1 whitespace-pre-wrap">
                {d.prompt}
              </p>
            </details>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Panel ─────────────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <p className="section-title mb-2">{title}</p>
      {children}
    </div>
  )
}

export default function GreyRecordPanel({
  pid,
  paperId,
}: {
  pid: number
  paperId: number
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['grey-record', pid, paperId],
    queryFn: () => getGreyRecord(pid, paperId),
    retry: false,
  })

  if (isLoading) {
    return <p className="text-xs text-ink-muted">Loading the retrieved record…</p>
  }
  // A formal paper 404s here by design; the caller should not have asked, but
  // saying so plainly beats an empty panel that looks like a failed retrieval.
  if (isError || !data) {
    return (
      <p className="text-xs text-ink-muted">
        No retrieved record for this paper.
      </p>
    )
  }

  const { source, full_text, figures } = data
  const reason = source.retrieval_reason
    ? (REASON_LABELS[source.retrieval_reason] ?? source.retrieval_reason)
    : null

  return (
    <div>
      <Section title="Retrieval provenance">
        <Provenance source={source} />
      </Section>

      <Section title="Full text">
        {full_text ? (
          <FullTextBlock fullText={full_text} />
        ) : (
          <div className="bg-paper rounded-[3px] p-3.5">
            <div className="flex items-center gap-2 mb-1">
              <Badge
                label={`Retrieval: ${source.retrieval_status ?? 'unknown'}`}
                variant={statusTone(source.retrieval_status)}
              />
            </div>
            <p className="text-xs text-ink-light leading-normal">
              Nothing was extracted from this source
              {reason ? <> — {reason}</> : null}.
            </p>
            {/* Why this is a finding rather than a blank: a review that cannot
                say how much of its grey literature had rotted or sat behind a
                wall is hiding a limitation. */}
            <p className="text-2xs text-ink-muted mt-1.5 leading-normal">
              It still counts as identified, and screening can proceed on the
              title and snippet.
            </p>
          </div>
        )}
      </Section>

      {figures.length > 0 && (
        <Section title={`Figures (${figures.length})`}>
          <div className="space-y-2">
            {figures.map(f => <FigureCard key={f.id} figure={f} />)}
          </div>
        </Section>
      )}
    </div>
  )
}
