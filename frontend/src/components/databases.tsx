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
  // Orange bar left accent + "SpringerLink" in Springer brand blue
  return (
    <svg height={height} viewBox="0 0 148 28" xmlns="http://www.w3.org/2000/svg" aria-label="SpringerLink">
      <rect x="0" y="0" width="4" height="28" rx="2" fill="#E8501A" />
      <text x="12" y="20" fontFamily="Georgia,'Times New Roman',serif" fontWeight="700" fontSize="17" fill="#1B2D6B">
        Springer
      </text>
      <text x="84" y="20" fontFamily="Georgia,'Times New Roman',serif" fontWeight="400" fontSize="17" fill="#1B2D6B">
        Link
      </text>
    </svg>
  )
}

function LogoIEEE({ height = 28 }: { height?: number }) {
  // "IEEE" bold blue + lighter "Xplore"
  return (
    <svg height={height} viewBox="0 0 118 28" xmlns="http://www.w3.org/2000/svg" aria-label="IEEE Xplore">
      <text x="0" y="21" fontFamily="Arial,Helvetica,sans-serif" fontWeight="900" fontSize="20" fill="#00629B" letterSpacing="1.5">
        IEEE
      </text>
      <text x="60" y="21" fontFamily="Arial,Helvetica,sans-serif" fontWeight="300" fontSize="20" fill="#00629B">
        Xplore
      </text>
    </svg>
  )
}

function LogoScopus({ height = 28 }: { height?: number }) {
  // "Scopus" in Elsevier orange — clean wordmark only
  return (
    <svg height={height} viewBox="0 0 90 28" xmlns="http://www.w3.org/2000/svg" aria-label="Scopus">
      <text x="0" y="21" fontFamily="Arial,Helvetica,sans-serif" fontWeight="700" fontSize="20" fill="#E9711C">
        Scopus
      </text>
    </svg>
  )
}

function LogoACM({ height = 28 }: { height?: number }) {
  // Concentric diamond mark + "ACM" bold
  return (
    <svg height={height} viewBox="0 0 100 28" xmlns="http://www.w3.org/2000/svg" aria-label="ACM Digital Library">
      {/* Diamond mark */}
      <g transform="translate(0,2)">
        <polygon points="12,0 22,12 12,24 2,12" fill="#111" />
        <polygon points="12,4 18,12 12,20 6,12" fill="white" />
        <polygon points="12,7 16,12 12,17 8,12" fill="#111" />
      </g>
      {/* ACM text */}
      <text x="28" y="15" fontFamily="Arial,Helvetica,sans-serif" fontWeight="900" fontSize="13" fill="#111" letterSpacing="0.5">ACM</text>
      <text x="28" y="26" fontFamily="Arial,Helvetica,sans-serif" fontWeight="400" fontSize="8.5" fill="#555" letterSpacing="0.4">DIGITAL LIBRARY</text>
    </svg>
  )
}

function LogoWiley({ height = 28 }: { height?: number }) {
  // "Wiley" bold black + "Online Library" small gray
  return (
    <svg height={height} viewBox="0 0 148 28" xmlns="http://www.w3.org/2000/svg" aria-label="Wiley Online Library">
      <text x="0" y="20" fontFamily="Georgia,'Times New Roman',serif" fontWeight="900" fontSize="18" fill="#111" letterSpacing="1">
        WILEY
      </text>
      <text x="68" y="20" fontFamily="Arial,Helvetica,sans-serif" fontWeight="400" fontSize="13" fill="#444">
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
