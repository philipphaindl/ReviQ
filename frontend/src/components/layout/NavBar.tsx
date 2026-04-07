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
        <svg width="30" height="30" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
          <rect width="100" height="100" rx="20" fill="#003057"/>
          <circle cx="42" cy="42" r="22" fill="none" stroke="white" strokeWidth="12"/>
          <line x1="58" y1="58" x2="80" y2="80" stroke="white" strokeWidth="12" strokeLinecap="round"/>
        </svg>
        ReviQ
      </button>

      {/* Project name */}
      {project && (
        <>
          <span className="text-border shrink-0">|</span>
          <span className="text-sm font-bold text-navy truncate max-w-[240px] shrink-0">{project.title}</span>
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
