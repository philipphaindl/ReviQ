import { useLocation, useNavigate } from 'react-router-dom'
import { useProject } from '../../App'
import { useQuery } from '@tanstack/react-query'
import { getProject } from '../../api/client'

export default function NavBar() {
  const navigate = useNavigate()
  const { projectId } = useProject()

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId!),
    enabled: !!projectId,
  })

  return (
    <nav className="bg-white border-b border-border sticky top-0 z-50 h-12 flex items-center px-6 gap-4">
      {/* Logo */}
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2 font-bold text-navy text-base tracking-tight hover:opacity-80 transition-opacity"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
        </svg>
        ReviQ
      </button>

      {/* Project name */}
      {project && (
        <>
          <span className="text-border">|</span>
          <span className="text-xs text-navy-muted truncate max-w-[240px]">{project.title}</span>
        </>
      )}
    </nav>
  )
}
