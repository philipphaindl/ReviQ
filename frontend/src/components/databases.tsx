import type { FC } from 'react'

// Supported academic databases with SVG logo components

export const DATABASES = [
  { key: 'springerlink', label: 'Springer Link'    },
  { key: 'ieee',         label: 'IEEE Xplore'      },
  { key: 'scopus',       label: 'Scopus'           },
  { key: 'acm',          label: 'ACM Digital Library' },
  { key: 'wiley',        label: 'Wiley Online Library' },
] as const

export type DatabaseKey = (typeof DATABASES)[number]['key']

export function dbByKey(key: string) {
  return DATABASES.find(d => d.key === key)
}

// PNG file mapping: database key → public asset path
const LOGO_PNGS: Record<string, string> = {
  springerlink: '/springer.png',
  ieee:         '/ieee.png',
  scopus:       '/scopus.png',
  acm:          '/acm.png',
  wiley:        '/wiley.png',
}

// ── DatabaseBadge ─────────────────────────────────────────────────────────────

/** Shows a PNG logo for known databases, or a plain text pill for unknown ones. */
export function DatabaseBadge({ dbKey, size = 'md' }: { dbKey: string; size?: 'sm' | 'md' | 'lg' }) {
  const pngSrc = LOGO_PNGS[dbKey]
  const height = size === 'lg' ? 32 : size === 'md' ? 24 : 18

  if (pngSrc) {
    return (
      <span
        title={dbByKey(dbKey)?.label ?? dbKey}
        className="inline-flex items-center"
        style={{ lineHeight: 0 }}
      >
        <img
          src={pngSrc}
          alt={dbByKey(dbKey)?.label ?? dbKey}
          height={height}
          style={{ height, width: 'auto', display: 'block' }}
        />
      </span>
    )
  }

  // Unknown database — plain pill
  return (
    <span
      className="inline-flex items-center rounded font-bold uppercase tracking-wider"
      style={{
        fontSize: size === 'lg' ? 11 : size === 'md' ? 10 : 8,
        padding: size === 'lg' ? '3px 8px' : '2px 5px',
        background: '#F0F0F0',
        color: '#555',
        border: '1px solid #DDD',
      }}
    >
      {dbKey}
    </span>
  )
}
