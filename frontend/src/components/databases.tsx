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

// ── Per-database SVG logos ────────────────────────────────────────────────────

function LogoSpringerLink({ height = 28 }: { height?: number }) {
  return (
    <svg height={height} viewBox="0 0 160 40" xmlns="http://www.w3.org/2000/svg" aria-label="SpringerLink">
      {/* Knight silhouette (simplified) */}
      <g fill="#1B2D6B">
        <ellipse cx="14" cy="8" rx="5" ry="6" />
        <path d="M9 14 Q6 18 7 24 L11 24 Q11 20 13 18 L15 24 L19 24 L17 16 Q16 13 14 13 Z" />
        <rect x="7" y="24" width="12" height="3" rx="1" />
      </g>
      {/* Orange underline accent */}
      <rect x="6" y="28.5" width="14" height="2.5" fill="#E8501A" rx="1" />
      {/* Text */}
      <text x="30" y="26" fontFamily="Georgia, serif" fontWeight="700" fontSize="17" fill="#1B2D6B" letterSpacing="-0.2">
        SpringerLink
      </text>
    </svg>
  )
}

function LogoIEEE({ height = 28 }: { height?: number }) {
  return (
    <svg height={height} viewBox="0 0 130 36" xmlns="http://www.w3.org/2000/svg" aria-label="IEEE Xplore">
      <text x="2" y="26" fontFamily="Arial, sans-serif" fontWeight="900" fontSize="22" fill="#00629B" letterSpacing="1">
        IEEE
      </text>
      <text x="66" y="26" fontFamily="Arial, sans-serif" fontWeight="400" fontSize="20" fill="#00629B">
        Xplore
      </text>
      <text x="120" y="15" fontFamily="Arial, sans-serif" fontSize="9" fill="#00629B">®</text>
    </svg>
  )
}

function LogoScopus({ height = 28 }: { height?: number }) {
  return (
    <svg height={height} viewBox="0 0 110 36" xmlns="http://www.w3.org/2000/svg" aria-label="Scopus">
      {/* Stylised Elsevier tree (minimal) */}
      <g fill="#636466" transform="translate(2,2)">
        <rect x="12" y="18" width="2.5" height="12" />
        <ellipse cx="13" cy="12" rx="8" ry="9" />
        <ellipse cx="7" cy="16" rx="5" ry="6" />
        <ellipse cx="19" cy="16" rx="5" ry="6" />
      </g>
      {/* Scopus text */}
      <text x="34" y="26" fontFamily="Arial, sans-serif" fontWeight="700" fontSize="20" fill="#E9711C" letterSpacing="-0.3">
        Scopus
      </text>
    </svg>
  )
}

function LogoACM({ height = 28 }: { height?: number }) {
  return (
    <svg height={height} viewBox="0 0 150 36" xmlns="http://www.w3.org/2000/svg" aria-label="ACM Digital Library">
      {/* Diamond shape */}
      <g transform="translate(2,2)">
        <polygon points="16,0 30,16 16,32 2,16" fill="#111" />
        <polygon points="16,5 25,16 16,27 7,16" fill="white" />
        <polygon points="16,9 22,16 16,23 10,16" fill="#111" />
      </g>
      {/* ACM text */}
      <text x="38" y="17" fontFamily="Arial, sans-serif" fontWeight="900" fontSize="13" fill="#111" letterSpacing="0.5">ACM</text>
      <text x="38" y="31" fontFamily="Arial, sans-serif" fontWeight="700" fontSize="10" fill="#111" letterSpacing="0.3">DIGITAL LIBRARY</text>
    </svg>
  )
}

function LogoWiley({ height = 28 }: { height?: number }) {
  return (
    <svg height={height} viewBox="0 0 160 40" xmlns="http://www.w3.org/2000/svg" aria-label="Wiley Online Library">
      {/* Two green squares */}
      <rect x="2"  y="20" width="9" height="9"  fill="#2F7D32" />
      <rect x="12" y="24" width="6" height="6"  fill="#43A047" />
      {/* WILEY bold */}
      <text x="2" y="17" fontFamily="Georgia, serif" fontWeight="900" fontSize="17" fill="#111" letterSpacing="1">
        WILEY
      </text>
      {/* Online Library */}
      <text x="22" y="33" fontFamily="Arial, sans-serif" fontWeight="400" fontSize="10" fill="#333" letterSpacing="0.2">
        Online Library
      </text>
    </svg>
  )
}

const LOGO_COMPONENTS: Record<string, FC<{ height?: number }>> = {
  springerlink: LogoSpringerLink,
  ieee:         LogoIEEE,
  scopus:       LogoScopus,
  acm:          LogoACM,
  wiley:        LogoWiley,
}

// ── DatabaseBadge ─────────────────────────────────────────────────────────────

/** Shows an SVG logo for known databases, or a plain text pill for unknown ones. */
export function DatabaseBadge({ dbKey, size = 'md' }: { dbKey: string; size?: 'sm' | 'md' | 'lg' }) {
  const LogoComponent = LOGO_COMPONENTS[dbKey]
  const height = size === 'lg' ? 32 : size === 'md' ? 24 : 18

  if (LogoComponent) {
    return (
      <span
        title={dbByKey(dbKey)?.label ?? dbKey}
        className="inline-flex items-center"
        style={{ lineHeight: 0 }}
      >
        <LogoComponent height={height} />
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
