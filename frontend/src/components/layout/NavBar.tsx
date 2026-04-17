import { useNavigate } from 'react-router-dom'
import { useProject } from '../../App'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { getProject, getReviewers } from '../../api/client'
import type { Reviewer } from '../../api/types'

export default function NavBar() {
  const navigate = useNavigate()
  const { projectId, reviewerId, setReviewerId } = useProject()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    if (reviewerId === null && reviewers.length > 0) {
      const r1 = reviewers.find(r => r.role === 'R1') ?? reviewers[0]
      setReviewerId(r1.id)
    }
  }, [reviewers, reviewerId, setReviewerId])

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  useEffect(() => {
    document.title = project ? `ReviQ — ${project.title}` : 'ReviQ'
  }, [project])

  const activeReviewer = reviewers.find(r => r.id === reviewerId)
    ?? reviewers.find(r => r.role === 'R1')
    ?? reviewers[0]

  return (
    <nav className="bg-masthead sticky top-0 z-50 h-14 flex items-center px-5 gap-4">
      {/* Logo */}
      <button
        onClick={() => navigate('/')}
        className="flex items-center leading-none hover:opacity-80 transition-opacity shrink-0"
      >
        <img src="/logo.png" alt="ReviQ" className="h-7 w-auto object-contain brightness-0 invert" />
      </button>

      {/* Project name */}
      {project && (
        <div className="flex items-center gap-2.5 min-w-0 self-center flex-1">
          <span className="text-white/25 shrink-0 text-lg font-light leading-none">/</span>
          <span className="text-sm font-medium text-white/80 leading-none self-center truncate">
            {project.title}
          </span>
        </div>
      )}

      {!project && <div className="flex-1" />}

      {/* Profile / reviewer menu */}
      <div className="relative shrink-0" ref={menuRef}>
        <button
          onClick={() => setMenuOpen(v => !v)}
          className="flex items-center gap-2 pl-1 pr-2.5 py-1 rounded hover:bg-white/10 transition-colors"
          aria-label="Open account menu"
        >
          <Avatar reviewer={activeReviewer} />
          {activeReviewer && (
            <span className="text-xs font-medium text-white/70 hidden sm:block">
              {activeReviewer.name}
            </span>
          )}
          <ChevronIcon />
        </button>

        {menuOpen && (
          <div className="absolute right-0 top-full mt-2 w-64 bg-surface border border-rule rounded-card shadow-modal z-50 py-1 overflow-hidden">
            {projectId && (
              <div className="px-3 pt-2 pb-1">
                <p className="text-2xs uppercase tracking-label text-ink-muted font-semibold mb-1.5">
                  Reviewing as
                </p>
                {reviewers.length === 0 ? (
                  <button
                    className="text-xs text-ink-muted w-full text-left py-1 hover:text-accent"
                    onClick={() => { navigate('/setup'); setMenuOpen(false) }}
                  >
                    + Add reviewers in Setup
                  </button>
                ) : (
                  <div className="space-y-0.5">
                    {reviewers.map(r => (
                      <ReviewerOption
                        key={r.id}
                        reviewer={r}
                        selected={r.id === activeReviewer?.id}
                        onClick={() => { setReviewerId(r.id); setMenuOpen(false) }}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </nav>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Avatar({ reviewer }: { reviewer?: Reviewer }) {
  const initials = reviewer
    ? reviewer.name.split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase()
    : null
  return (
    <span className="w-7 h-7 rounded-full bg-white/15 text-white/90 text-xs font-bold flex items-center justify-center shrink-0 border border-white/10">
      {initials ?? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
      )}
    </span>
  )
}

function ReviewerOption({ reviewer, selected, onClick }: { reviewer: Reviewer; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-2 py-1.5 rounded-[3px] text-left text-sm transition-colors ${
        selected ? 'bg-accent-faint text-accent font-medium' : 'text-ink-muted hover:bg-paper hover:text-ink'
      }`}
    >
      <span className={`w-5 h-5 rounded-full text-2xs font-bold flex items-center justify-center shrink-0 ${
        selected ? 'bg-accent text-white' : 'bg-rule text-ink-muted'
      }`}>
        {reviewer.name[0]?.toUpperCase()}
      </span>
      <span className="flex-1 truncate">{reviewer.name}</span>
      <span className={`text-2xs font-bold font-mono ${selected ? 'text-accent/60' : 'text-ink-muted/40'}`}>{reviewer.role}</span>
    </button>
  )
}

function ChevronIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-white/40">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  )
}

