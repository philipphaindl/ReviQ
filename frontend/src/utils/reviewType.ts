/** Systematic review or multivocal review.
 *
 * One module, for the reason `components/streams.ts` gives about streams: the
 * test spreads otherwise. Every conditional that shows or hides a
 * grey-literature feature reads `isMlr` from here, so adding a review type
 * later means editing one file rather than every page that gates on one.
 *
 * A multivocal review is declared in its protocol rather than discovered from
 * the data (Garousi, Felderer & Mäntylä 2019). Inferring it from "does this
 * project contain grey literature" would hide the retrieval features until
 * after they had been used, and would make the PRISMA figure grow a third
 * column partway through a review.
 */

export const SLR = 'slr'
export const MLR = 'mlr'

export interface ReviewTypeLike {
  review_type?: string | null
}

/** The declared type, defaulting to a systematic review.
 *
 * The fallback is not cosmetic: a project created before the column existed
 * comes back without the field, and every one of those was a systematic
 * review. Treating an absent value as multivocal would put an empty grey
 * column into an existing review's published figure.
 */
export function reviewTypeOf(project: ReviewTypeLike | null | undefined): string {
  return project?.review_type === MLR ? MLR : SLR
}

export const isMlr = (project: ReviewTypeLike | null | undefined) =>
  reviewTypeOf(project) === MLR

export const isSlr = (project: ReviewTypeLike | null | undefined) =>
  reviewTypeOf(project) === SLR

/** What to call each type in the interface, and the methodology it usually
 *  cites. Offered as a default when a project is created — a suggestion the
 *  user can overwrite, not a value the tool derives and enforces. */
export const REVIEW_TYPES = [
  {
    value: SLR,
    label: 'Systematic literature review',
    hint: 'Peer-reviewed sources from bibliographic databases.',
    defaultMethodology: 'Kitchenham & Charters (2007)',
  },
  {
    value: MLR,
    label: 'Multivocal literature review',
    hint: 'Adds grey literature from the open web, screened alongside and reported separately.',
    defaultMethodology: 'Garousi, Felderer & Mäntylä (2019)',
  },
]
