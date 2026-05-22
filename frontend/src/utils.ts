/**
 * Format an author string (BibTeX "A and B and C" style) to a display string.
 * ≤ maxFull authors → join with ", "
 * > maxFull authors → first surname + " et al."
 */
export function formatAuthors(authors?: string, maxFull = 3): string {
  if (!authors) return ''
  const parts = authors.split(' and ').map(s => s.trim()).filter(Boolean)
  if (parts.length <= maxFull) return parts.join(', ')
  // BibTeX surname-first: "Surname, Firstname" → take part before comma
  const firstSurname = parts[0].split(',')[0].trim()
  return `${firstSurname} et al.`
}
