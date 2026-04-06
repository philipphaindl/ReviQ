import type { CSSProperties } from 'react'

// Supported academic databases

export const DATABASES = [
  { key: 'springerlink', label: 'SpringerLink'         },
  { key: 'ieee',         label: 'IEEE Xplore'          },
  { key: 'scopus',       label: 'Elsevier Scopus'      },
  { key: 'acm',          label: 'ACM Digital Library'  },
  { key: 'wiley',        label: 'Wiley Online Library' },
  { key: 'dblp',         label: 'DBLP Library'         },
] as const

export type DatabaseKey = (typeof DATABASES)[number]['key']

export function dbByKey(key: string) {
  return DATABASES.find(d => d.key === key)
}

// Brand color palette — clearly distinct hues
const DB_COLORS: Record<string, { bg: string; text: string }> = {
  springerlink: { bg: '#E8501A', text: '#fff' },  // Springer burnt orange
  ieee:         { bg: '#00629B', text: '#fff' },  // IEEE blue
  scopus:       { bg: '#F57C00', text: '#fff' },  // Elsevier amber-orange
  acm:          { bg: '#B71C1C', text: '#fff' },  // ACM vivid crimson
  wiley:        { bg: '#003057', text: '#fff' },  // Wiley dark navy
  dblp:         { bg: '#00695C', text: '#fff' },  // DBLP teal (distinct from IEEE blue)
}

// Normalise raw source strings (from legacy free-text imports) → canonical key
const KEY_ALIASES: Record<string, string> = {
  'springer': 'springerlink',
  'springer link': 'springerlink',
  'springerlink': 'springerlink',
  'ieee xplore': 'ieee',
  'ieee explore': 'ieee',
  'ieee': 'ieee',
  'scopus': 'scopus',
  'elsevier': 'scopus',
  'elsevier scopus': 'scopus',
  'acm': 'acm',
  'acm digital library': 'acm',
  'wiley': 'wiley',
  'wiley online library': 'wiley',
  'dblp': 'dblp',
  'dblp library': 'dblp',
}

export function normalizeDbKey(raw: string): string {
  const lower = raw.toLowerCase().trim()
  if (KEY_ALIASES[lower]) return KEY_ALIASES[lower]
  const byLabel = DATABASES.find(d => d.label.toLowerCase() === lower)
  if (byLabel) return byLabel.key
  return raw
}

// ── DatabaseBadge ─────────────────────────────────────────────────────────────

/** Coloured pill badge for a database. Normalises raw source strings automatically. */
export function DatabaseBadge({ dbKey, size = 'md' }: { dbKey: string; size?: 'sm' | 'md' | 'lg' }) {
  const canonical = normalizeDbKey(dbKey)
  const db = dbByKey(canonical)
  const label = db?.label ?? dbKey
  const colors = DB_COLORS[canonical] ?? { bg: '#6B7280', text: '#fff' }

  const sizeStyles: Record<string, CSSProperties> = {
    sm: { fontSize: 9,  padding: '2px 6px',  borderRadius: 5 },
    md: { fontSize: 11, padding: '3px 8px',  borderRadius: 6 },
    lg: { fontSize: 13, padding: '4px 11px', borderRadius: 7 },
  }

  return (
    <span
      title={label}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        fontFamily: 'system-ui, sans-serif',
        fontWeight: 600,
        letterSpacing: '0.01em',
        whiteSpace: 'nowrap',
        backgroundColor: colors.bg,
        color: colors.text,
        ...sizeStyles[size],
      }}
    >
      {label}
    </span>
  )
}
