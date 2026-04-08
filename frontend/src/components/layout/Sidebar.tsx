import { useLocation, useNavigate } from 'react-router-dom'

const PHASES = [
  { path: '/',            number: null,   label: 'Overview',    optional: false },
  { path: '/setup',       number: '1',    label: 'Setup',       optional: false },
  { path: '/import',      number: '2',    label: 'Import',      optional: false },
  { path: '/screening',   number: '3',    label: 'Screening',   optional: false },
  { path: '/eligibility', number: '4',    label: 'Eligibility', optional: false },
  { path: '/snowballing', number: '5',    label: 'Snowballing', optional: true  },
  { path: '/quality',     number: '6',    label: 'Quality',     optional: false },
  { path: '/extraction',  number: '7',    label: 'Extraction',  optional: false },
  { path: '/results',     number: '8',    label: 'Results',     optional: false },
]

export default function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <aside className="w-44 shrink-0 border-r border-border bg-white sticky top-12 h-[calc(100vh-3rem)] overflow-y-auto">
      <nav className="py-3">
        {PHASES.map(item => {
          const isActive = item.path === '/'
            ? location.pathname === '/'
            : location.pathname.startsWith(item.path)

          return (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-colors border-l-2 text-left
                ${isActive
                  ? 'text-navy font-semibold bg-card border-info'
                  : 'text-gray-500 hover:text-navy hover:bg-gray-50 border-transparent'
                }`}
            >
              <span className={`text-xs font-mono w-4 text-center shrink-0 tabular-nums ${isActive ? 'text-info font-bold' : 'text-gray-300'}`}>
                {item.number ?? '·'}
              </span>
              <span className="flex-1">{item.label}</span>
              {item.optional && (
                <span className="text-[9px] font-semibold text-gray-300 uppercase tracking-wide leading-none">opt</span>
              )}
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
