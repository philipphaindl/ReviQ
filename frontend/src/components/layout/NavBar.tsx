import { useLocation, useNavigate } from 'react-router-dom'
import { useProject } from '../../App'
import { useQuery } from '@tanstack/react-query'
import { getProject } from '../../api/client'

const NAV_ITEMS = [
  { path: '/',            icon: '🏠', label: 'Overview' },
  { path: '/setup',       icon: '⚙️', label: 'Setup' },
  { path: '/import',      icon: '📥', label: 'Import' },
  { path: '/screening',   icon: '🔍', label: 'Screening' },
  { path: '/eligibility', icon: '📄', label: 'Eligibility' },
  { path: '/snowballing', icon: '❄️', label: 'Snowballing' },
  { path: '/quality',     icon: '⭐', label: 'Quality' },
  { path: '/extraction',  icon: '📝', label: 'Extraction' },
  { path: '/results',     icon: '📊', label: 'Results' },
]

export default function NavBar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { projectId } = useProject()

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId!),
    enabled: !!projectId,
  })

  return (
    <nav className="bg-white border-b border-border sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 flex items-stretch">
        {/* Logo */}
        <div className="flex items-center gap-2 pr-6 border-r border-border mr-2 py-3">
          <span className="text-xl">📚</span>
          <span className="font-bold text-navy text-base tracking-tight">ReviQ</span>
        </div>

        {/* Project indicator */}
        {project && (
          <div className="flex items-center px-3 text-xs text-navy-muted truncate max-w-[180px]">
            <span className="truncate">{project.title}</span>
          </div>
        )}

        {/* Nav items */}
        <div className="flex items-stretch ml-auto overflow-x-auto">
          {NAV_ITEMS.map(item => {
            const isActive = item.path === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.path)
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={`nav-item ${isActive ? 'active' : ''}`}
              >
                <span className="text-sm">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            )
          })}
        </div>
      </div>
    </nav>
  )
}
