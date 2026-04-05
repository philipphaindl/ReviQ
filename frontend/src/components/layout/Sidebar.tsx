import { useLocation, useNavigate } from 'react-router-dom'

const PHASES = [
  { path: '/',            number: null, label: 'Overview'    },
  { path: '/setup',       number: '0',  label: 'Setup'       },
  { path: '/import',      number: '1',  label: 'Import'      },
  { path: '/screening',   number: '2',  label: 'Screening'   },
  { path: '/eligibility', number: '3',  label: 'Eligibility' },
  { path: '/snowballing', number: '4',  label: 'Snowballing' },
  { path: '/quality',     number: '5',  label: 'Quality'     },
  { path: '/extraction',  number: '6',  label: 'Extraction'  },
  { path: '/results',     number: '7',  label: 'Results'     },
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
              <span>{item.label}</span>
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
