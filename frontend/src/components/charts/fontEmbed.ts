/**
 * Embed web-fonts inside exported SVGs as base64-encoded WOFF2 @font-face rules.
 *
 * A standalone SVG has no access to the surrounding page's @font-face
 * declarations, so without this step the exported file renders with a default
 * system font in Inkscape, Illustrator, and any browser that doesn't have
 * the font pre-installed.
 *
 * Implementation:
 *   1. Fetch the Google Fonts CSS (which has CORS headers: Access-Control-Allow-Origin: *).
 *   2. Extract the WOFF2 URL from the "latin" @font-face block for each weight.
 *   3. Fetch each WOFF2 file (also served with CORS headers from fonts.gstatic.com).
 *   4. Base64-encode the bytes.
 *   5. Return a @font-face CSS string ready to inject into <defs><style>.
 *
 * The result is module-cached so subsequent SVG exports are instant.
 * If the network is unavailable the function returns an empty string and the
 * SVG falls back to the font-family name (existing behavior).
 */

// Module-level cache: prevents re-fetching on every export.
let cssCache: string | null = null
const woff2Cache = new Map<string, string>()  // woff2 url → base64

async function fetchBase64(url: string): Promise<string> {
  const cached = woff2Cache.get(url)
  if (cached) return cached

  const resp = await fetch(url, { cache: 'force-cache' })
  if (!resp.ok) throw new Error(`Failed to fetch font: ${url}`)
  const buffer = await resp.arrayBuffer()

  // Convert to base64 in chunks to avoid stack overflow on large arrays.
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  const b64 = btoa(binary)
  woff2Cache.set(url, b64)
  return b64
}

/**
 * Build and return a CSS string containing @font-face rules with WOFF2 data
 * embedded as base64.  Only the "latin" unicode subset is embedded (sufficient
 * for all ASCII text used in chart labels).
 *
 * Fonts fetched:
 *   - Source Sans 3: weights 400, 600, 700  (label text, axis labels)
 *   - JetBrains Mono: weight 700            (center numeral in donut)
 */
export async function buildEmbeddedFontCss(): Promise<string> {
  if (cssCache !== null) return cssCache

  const specs = [
    { family: 'Source Sans 3', weights: [400, 600, 700] },
    { family: 'JetBrains Mono', weights: [700] },
  ]

  const parts: string[] = []

  for (const { family, weights } of specs) {
    const apiUrl =
      `https://fonts.googleapis.com/css2?family=` +
      `${encodeURIComponent(family)}:wght@${weights.join(';')}&display=swap`

    try {
      const cssResp = await fetch(apiUrl)
      if (!cssResp.ok) continue
      const css = await cssResp.text()

      // Split on block-level comments so we can identify the "latin" subset.
      // Google Fonts CSS format: each block is preceded by /* comment */
      const segments = css.split(/(?=\/\*[^*]*)/)

      for (const seg of segments) {
        // Only embed the Latin subset — it covers all ASCII characters used
        // in venue names, keywords, and taxonomy labels.
        const isLatin =
          seg.startsWith('/* latin */') ||          // modern Google Fonts format
          seg.match(/unicode-range:[^;]*U\+0000/)   // fallback: detect by range

        if (!isLatin) continue

        const faceMatch = seg.match(/@font-face\s*\{([^}]+)\}/s)
        if (!faceMatch) continue
        const body = faceMatch[1]

        const urlMatch    = body.match(/url\((https:\/\/fonts\.gstatic\.com\/[^)]+\.woff2)\)/)
        const familyMatch = body.match(/font-family:\s*['"]?([^;'"]+)['"]?;/)
        const weightMatch = body.match(/font-weight:\s*([^;]+);/)
        const styleMatch  = body.match(/font-style:\s*([^;]+);/)

        if (!urlMatch) continue

        const b64 = await fetchBase64(urlMatch[1])

        parts.push(`@font-face {
  font-family: '${(familyMatch?.[1] ?? family).trim()}';
  font-weight: ${(weightMatch?.[1] ?? '400').trim()};
  font-style: ${(styleMatch?.[1] ?? 'normal').trim()};
  font-display: block;
  src: url(data:font/woff2;base64,${b64}) format('woff2');
}`)
      }
    } catch {
      // Network unavailable — skip this font, fall back to system fonts.
    }
  }

  cssCache = parts.join('\n')
  return cssCache
}
