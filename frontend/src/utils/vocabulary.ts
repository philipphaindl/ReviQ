/** What a review calls the things it is counting, phase by phase.
 *
 * PRISMA 2020 does not use one noun throughout, and the difference is not
 * pedantry. A *record* is a title and abstract returned by a search; a *report*
 * is the document that record points at; a *study* is the piece of research a
 * report describes. Screening excludes records, eligibility excludes reports,
 * and a review includes studies — which is why the three boxes of the flow
 * diagram do not add up if one word is used for all of them. Two records can
 * point at one report, and two reports can describe one study.
 *
 * ReviQ said "papers" everywhere. In the figure it already said otherwise
 * (`Records screened`, `Studies included in review`), so the interface and the
 * figure it produces disagreed about what a number counted.
 *
 * **This is display only.** The database column, the API field and the
 * replication package stay `paper`, and so do exported CSV headers: renaming
 * those would break replication packages and decision exports that existing
 * reviews depend on. The identifier and the noun a reader sees are different
 * things, and this module is the second one.
 */

export interface Noun {
  /** "record" — inside a sentence. */
  one: string
  /** "records" — inside a sentence. */
  many: string
  /** "Record" — a label, a column head, a button. */
  One: string
  /** "Records" — a label, a column head, a tab. */
  Many: string
}

const noun = (one: string, many: string): Noun => ({
  one, many,
  One: one.charAt(0).toUpperCase() + one.slice(1),
  Many: many.charAt(0).toUpperCase() + many.slice(1),
})

/** What a search returned: a title and abstract, screened as it stands. */
export const RECORD = noun('record', 'records')

/** The document a record points at, assessed in full text. */
export const REPORT = noun('report', 'reports')

/** The research a report describes — what a review finally includes. */
export const STUDY = noun('study', 'studies')

/** The phases as the interface names them, and the noun each one counts. */
export const PHASE_NOUN = {
  /** Phase 2 — import: what the searches returned. */
  import: RECORD,
  /** Phase 3 — screening: still titles and abstracts. */
  screening: RECORD,
  /** Phase 4 — full-text eligibility: the documents themselves. */
  eligibility: REPORT,
  /** Phase 6 — quality assessment: everything here is an included study. */
  quality: STUDY,
  /** Phase 7 — extraction: likewise. */
  extraction: STUDY,
  /** Phase 8 — results: likewise. */
  results: STUDY,
} as const

export type Phase = keyof typeof PHASE_NOUN

/** "1 record", "4 records" — the count and its noun, agreeing in number. */
export function counted(n: number, term: Noun): string {
  return `${n} ${n === 1 ? term.one : term.many}`
}
