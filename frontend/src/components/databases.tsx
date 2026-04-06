// Supported academic databases with display metadata

export const DATABASES = [
  { key: 'springerlink', label: 'Springer Link',  abbr: 'SL',   color: '#ED6F00', bg: '#FFF3E8' },
  { key: 'ieee',         label: 'IEEE Xplore',    abbr: 'IEEE', color: '#006699', bg: '#E0EFF8' },
  { key: 'scopus',       label: 'Scopus',         abbr: 'SC',   color: '#E9711C', bg: '#FFF0E4' },
  { key: 'dblp',         label: 'DBLP',           abbr: 'dblp', color: '#004F9F', bg: '#E0E8F8' },
  { key: 'wiley',        label: 'Wiley Online',   abbr: 'WOL',  color: '#003057', bg: '#E0E6EE' },
] as const

export type DatabaseKey = (typeof DATABASES)[number]['key']

export function dbByKey(key: string) {
  return DATABASES.find(d => d.key === key)
}

/** Pill-style logo badge for a database key */
export function DatabaseBadge({ dbKey, size = 'md' }: { dbKey: string; size?: 'sm' | 'md' | 'lg' }) {
  const db = dbByKey(dbKey)
  if (!db) {
    // Unknown database — show generic badge
    return (
      <span
        className="inline-flex items-center rounded font-bold uppercase tracking-wider"
        style={{
          fontSize: size === 'lg' ? 13 : size === 'md' ? 11 : 9,
          padding: size === 'lg' ? '5px 10px' : size === 'md' ? '3px 7px' : '2px 5px',
          background: '#F0F0F0',
          color: '#555',
          border: '1px solid #DDD',
        }}
      >
        {dbKey}
      </span>
    )
  }
  return (
    <span
      title={db.label}
      className="inline-flex items-center rounded font-bold tracking-wide"
      style={{
        fontSize: size === 'lg' ? 13 : size === 'md' ? 11 : 9,
        padding: size === 'lg' ? '5px 12px' : size === 'md' ? '4px 8px' : '2px 5px',
        background: db.bg,
        color: db.color,
        border: `1.5px solid ${db.color}40`,
        letterSpacing: '0.04em',
      }}
    >
      {db.abbr}
    </span>
  )
}
