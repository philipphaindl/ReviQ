import { useLocation, useNavigate } from 'react-router-dom'
import { ReactNode } from 'react'

// ── Stroke-based icons (24×24 viewBox, Lucide style) ─────────────────────────

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      {children}
    </svg>
  )
}

const icons = {
  overview: (
    <Icon>
      <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
      <polyline points="9 22 9 12 15 12 15 22"/>
    </Icon>
  ),
  setup: (
    <Icon>
      <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
      <circle cx="9" cy="7" r="4"/>
      <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>
    </Icon>
  ),
  import: (
    <Icon>
      <polyline points="16 16 12 12 8 16"/>
      <line x1="12" y1="12" x2="12" y2="21"/>
      <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3"/>
    </Icon>
  ),
  screening: (
    <Icon>
      <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
    </Icon>
  ),
  eligibility: (
    <Icon>
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <polyline points="9 15 11 17 15 13"/>
    </Icon>
  ),
  snowballing: (
    <Icon>
      <circle cx="18" cy="5" r="3"/>
      <circle cx="6" cy="12" r="3"/>
      <circle cx="18" cy="19" r="3"/>
      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
    </Icon>
  ),
  quality: (
    <Icon>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
      <polyline points="9 12 11 14 15 10"/>
    </Icon>
  ),
  extraction: (
    <Icon>
      <ellipse cx="12" cy="5" rx="9" ry="3"/>
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
    </Icon>
  ),
  results: (
    <Icon>
      <line x1="18" y1="20" x2="18" y2="10"/>
      <line x1="12" y1="20" x2="12" y2="4"/>
      <line x1="6" y1="20" x2="6" y2="14"/>
    </Icon>
  ),
}

const PHASES = [
  { path: '/',            number: null, label: 'Overview',    icon: icons.overview    },
  { path: '/setup',       number: '1',  label: 'Setup',       icon: icons.setup       },
  { path: '/import',      number: '2',  label: 'Import',      icon: icons.import      },
  { path: '/screening',   number: '3',  label: 'Screening',   icon: icons.screening   },
  { path: '/eligibility', number: '4',  label: 'Eligibility', icon: icons.eligibility },
  { path: '/snowballing', number: '5',  label: 'Snowballing', icon: icons.snowballing },
  { path: '/quality',     number: '6',  label: 'Quality',     icon: icons.quality     },
  { path: '/extraction',  number: '7',  label: 'Extraction',  icon: icons.extraction  },
  { path: '/results',     number: '8',  label: 'Results',     icon: icons.results     },
]

export default function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <aside className="w-52 shrink-0 border-r border-rule bg-[#F5F2EE] sticky top-14 h-[calc(100vh-3.5rem)] overflow-y-auto">
      <nav className="py-3 px-2">
        {PHASES.map(item => {
          const isActive = item.path === '/'
            ? location.pathname === '/'
            : location.pathname.startsWith(item.path)

          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm transition-colors text-left mb-0.5
                rounded-[3px]
                ${isActive
                  ? 'bg-white text-ink font-semibold shadow-sm'
                  : 'text-ink-muted hover:text-ink hover:bg-white/50'
                }`}
            >
              <span className={`shrink-0 ${isActive ? 'text-accent' : 'text-ink-muted/50'}`}>
                {item.icon}
              </span>
              <span className="flex-1 truncate">{item.label}</span>
              {item.number && (
                <span className={`text-2xs font-mono font-medium tabular-nums shrink-0 ${
                  isActive ? 'text-accent/50' : 'text-ink-muted/30'
                }`}>
                  {item.number}
                </span>
              )}
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
