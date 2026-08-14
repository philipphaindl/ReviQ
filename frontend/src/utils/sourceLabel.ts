/** What to call a `source` key on screen.
 *
 * The database, the API and the replication package keep the raw key — it is
 * how a paper's origin is stored and exported, and renaming it would break
 * existing replication packages. What a reader sees is another matter:
 * `grey:google` in a column headed "Database" is the interface asserting that
 * a web search engine is a bibliographic database, which is exactly the
 * conflation a multivocal review has to keep visible.
 *
 * One function rather than one per page: the Import page's per-source table
 * and the PRISMA figure's identification box name the same keys, and they had
 * begun to answer differently — the figure spelled a grey source out as
 * `grey:google` while the table wrote snowballing as "It. 1".
 */
import { dbByKey, normalizeDbKey } from '../components/databases'

const GREY = /^grey(-snowball)?:(.*)$/
const SNOWBALL = /^snowballing:(\d+)$/

export function sourceLabel(source: string): string {
  const grey = GREY.exec(source)
  if (grey) {
    const engine = grey[2]
    // `mixed` is `engine_of`'s answer for a package whose runs used more than
    // one engine; it is not the name of an engine and must not read like one.
    const name = engine === 'mixed'
      ? 'Several engines'
      : engine.charAt(0).toUpperCase() + engine.slice(1)
    return grey[1] ? `${name} (snowballed)` : name
  }

  const snowball = SNOWBALL.exec(source)
  if (snowball) return `snowballing: It. ${snowball[1]}`

  return dbByKey(normalizeDbKey(source))?.label ?? source
}
