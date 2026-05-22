/**
 * Root application shell. Provides a ProjectContext (active project + active reviewer)
 * that all page components consume — both IDs are persisted to localStorage so the
 * selection survives reloads. Switching projects resets the reviewer to avoid stale refs.
 */
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { createContext, useContext, useState } from 'react'
import NavBar from './components/layout/NavBar'
import Sidebar from './components/layout/Sidebar'
import Overview from './pages/Overview'
import Settings from './pages/Settings'
import Search from './pages/Search'
import Screening from './pages/Screening'
import Eligibility from './pages/Eligibility'
import Snowballing from './pages/Snowballing'
import Quality from './pages/Quality'
import Extraction from './pages/Extraction'
import Results from './pages/Results'
// Profile page removed — keeping the app focused

// ── Project context ───────────────────────────────────────────────────────────

interface ProjectContextValue {
  projectId: number | null
  setProjectId: (id: number | null) => void
  reviewerId: number | null
  setReviewerId: (id: number | null) => void
}

export const ProjectContext = createContext<ProjectContextValue>({
  projectId: null,
  setProjectId: () => {},
  reviewerId: null,
  setReviewerId: () => {},
})

export const useProject = () => useContext(ProjectContext)

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [projectId, setProjectId] = useState<number | null>(() => {
    const stored = localStorage.getItem('reviq_project_id')
    return stored ? parseInt(stored, 10) : null
  })

  const [reviewerId, setReviewerId] = useState<number | null>(() => {
    const stored = localStorage.getItem('reviq_reviewer_id')
    return stored ? parseInt(stored, 10) : null
  })

  const handleSetProjectId = (id: number | null) => {
    setProjectId(id)
    if (id) localStorage.setItem('reviq_project_id', String(id))
    else localStorage.removeItem('reviq_project_id')
    // Reset reviewer when switching projects
    setReviewerId(null)
    localStorage.removeItem('reviq_reviewer_id')
  }

  const handleSetReviewerId = (id: number | null) => {
    setReviewerId(id)
    if (id) localStorage.setItem('reviq_reviewer_id', String(id))
    else localStorage.removeItem('reviq_reviewer_id')
  }

  return (
    <ProjectContext.Provider value={{
      projectId,
      setProjectId: handleSetProjectId,
      reviewerId,
      setReviewerId: handleSetReviewerId,
    }}>
      <BrowserRouter>
        <div className="min-h-screen bg-paper flex flex-col">
          <NavBar />
          <div className="flex flex-1">
            <Sidebar />
            <main className="flex-1 px-8 py-6 overflow-y-auto">
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/setup" element={<Settings />} />
                <Route path="/import" element={<Search />} />
                <Route path="/screening" element={<Screening />} />
                <Route path="/eligibility" element={<Eligibility />} />
                <Route path="/snowballing" element={<Snowballing />} />
                <Route path="/quality" element={<Quality />} />
                <Route path="/extraction" element={<Extraction />} />
                <Route path="/results" element={<Results />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </div>
          <footer className="sticky bottom-0 z-40 border-t border-rule bg-surface/95 backdrop-blur-sm px-8 py-1.5 flex items-center gap-2 shrink-0">
            <span className="text-2xs text-ink-muted">
              If you use ReviQ in your research, please cite:
            </span>
            <span className="text-2xs text-ink">
              Haindl, Philipp (submitted). <em>ReviQ: A Systematic Literature Review Workbench.</em> SoftwareX.
            </span>
          </footer>
        </div>
      </BrowserRouter>
    </ProjectContext.Provider>
  )
}
