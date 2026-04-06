import { useNavigate } from 'react-router-dom'
import { useProject } from '../../App'
import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { getProject, getReviewers } from '../../api/client'

export default function NavBar() {
  const navigate = useNavigate()
  const { projectId, reviewerId, setReviewerId } = useProject()

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId!),
    enabled: !!projectId,
  })

  const { data: reviewers = [] } = useQuery({
    queryKey: ['reviewers', projectId],
    queryFn: () => getReviewers(projectId!),
    enabled: !!projectId,
  })

  // Auto-persist R1 into context when no reviewer is selected yet
  useEffect(() => {
    if (reviewerId === null && reviewers.length > 0) {
      const r1 = reviewers.find(r => r.role === 'R1') ?? reviewers[0]
      setReviewerId(r1.id)
    }
  }, [reviewers, reviewerId, setReviewerId])

  const activeReviewer = reviewers.find(r => r.id === reviewerId) ?? reviewers.find(r => r.role === 'R1') ?? reviewers[0]

  return (
    <nav className="bg-white border-b border-border sticky top-0 z-50 h-12 flex items-center px-6 gap-4">
      {/* Logo */}
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2 font-bold text-navy text-base tracking-tight hover:opacity-80 transition-opacity shrink-0"
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
          <span className="text-border shrink-0">|</span>
          <span className="text-xs text-navy-muted truncate max-w-[200px] shrink-0">{project.title}</span>
        </>
      )}

      <div className="flex-1" />

      {/* Reviewer role selector — always visible when project is active */}
      {projectId && (
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-gray-400 hidden sm:block">Reviewer:</span>
          {reviewers.length === 0 ? (
            <button
              className="text-xs text-gray-400 border border-dashed border-gray-300 rounded-md px-3 py-1 hover:border-info hover:text-info transition-colors"
              onClick={() => navigate('/setup')}
            >
              Add reviewers in Setup →
            </button>
          ) : (
            <>
              <select
                className="text-xs border border-border rounded-md px-2 py-1 text-navy bg-white font-medium"
                value={activeReviewer?.id ?? ''}
                onChange={e => setReviewerId(parseInt(e.target.value))}
              >
                {reviewers.map(r => (
                  <option key={r.id} value={r.id}>{r.role} – {r.name}</option>
                ))}
              </select>
              {activeReviewer && (
                <span className={`text-xs font-bold px-2 py-0.5 rounded border ${
                  activeReviewer.role === 'R1'
                    ? 'bg-blue-50 text-info border-blue-200'
                    : 'bg-gray-50 text-gray-600 border-gray-200'
                }`}>
                  {activeReviewer.role}
                </span>
              )}
            </>
          )}
        </div>
      )}
    </nav>
  )
}
