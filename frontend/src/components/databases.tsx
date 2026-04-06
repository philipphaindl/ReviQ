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

// Brand color palette — background / text
const DB_COLORS: Record<string, { bg: string; text: string }> = {
  springerlink: { bg: '#E8501A', text: '#fff'     },  // Springer orange
  ieee:         { bg: '#00629B', text: '#fff'     },  // IEEE blue
  scopus:       { bg: '#E87722', text: '#fff'     },  // Elsevier orange
  acm:          { bg: '#B00020', text: '#fff'     },  // ACM red
  wiley:        { bg: '#003057', text: '#fff'     },  // Wiley navy
  dblp:         { bg: '#004F9F', text: '#fff'     },  // DBLP blue
}

// ── DatabaseBadge ─────────────────────────────────────────────────────────────

/** Coloured pill badge for a database. Falls back to a neutral grey pill for unknown keys. */
export function DatabaseBadge({ dbKey, size = 'md' }: { dbKey: string; size?: 'sm' | 'md' | 'lg' }) {
  const db = dbByKey(dbKey)
  const label = db?.label ?? dbKey
  const colors = DB_COLORS[dbKey] ?? { bg: '#6B7280', text: '#fff' }

  const sizeStyles: Record<string, CSSProperties> = {
    sm: { fontSize: 9,  padding: '2px 6px',  borderRadius: 5  },
    md: { fontSize: 11, padding: '3px 8px',  borderRadius: 6  },
    lg: { fontSize: 13, padding: '4px 11px', borderRadius: 7  },
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
