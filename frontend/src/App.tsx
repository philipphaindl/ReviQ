import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { createContext, useContext, useState, useEffect } from 'react'
import NavBar from './components/layout/NavBar'
import Sidebar from './components/layout/Sidebar'
import Overview from './pages/Overview'
import Settings from './pages/Settings'
import Search from './pages/Search'
import Screening from './pages/Screening'
import { EligibilityStub, SnowballingStub, QualityStub, ExtractionStub, ResultsStub } from './pages/Stubs'

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

function useFavicon() {
  useEffect(() => {
    const c = document.createElement('canvas')
    c.width = c.height = 64
    const x = c.getContext('2d')!
    x.beginPath()
    const r = 11
    x.moveTo(r, 0); x.lineTo(64 - r, 0); x.arcTo(64, 0, 64, r, r)
    x.lineTo(64, 64 - r); x.arcTo(64, 64, 64 - r, 64, r)
    x.lineTo(r, 64); x.arcTo(0, 64, 0, 64 - r, r)
    x.lineTo(0, r); x.arcTo(0, 0, r, 0, r)
    x.closePath()
    x.fillStyle = '#003057'; x.fill()
    x.fillStyle = 'white'
    x.font = 'bold 46px system-ui,sans-serif'
    x.textAlign = 'center'; x.textBaseline = 'middle'
    x.fillText('R', 32, 35)
    const existing = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
    const link = existing ?? document.createElement('link')
    link.rel = 'icon'; link.type = 'image/png'
    link.href = c.toDataURL('image/png')
    if (!existing) document.head.appendChild(link)
  }, [])
}

export default function App() {
  useFavicon()
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
        <div className="min-h-screen bg-white flex flex-col">
          <NavBar />
          <div className="flex flex-1">
            <Sidebar />
            <main className="flex-1 px-8 py-6 overflow-y-auto">
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/setup" element={<Settings />} />
                <Route path="/import" element={<Search />} />
                <Route path="/screening" element={<Screening />} />
                <Route path="/eligibility" element={<EligibilityStub />} />
                <Route path="/snowballing" element={<SnowballingStub />} />
                <Route path="/quality" element={<QualityStub />} />
                <Route path="/extraction" element={<ExtractionStub />} />
                <Route path="/results" element={<ResultsStub />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </div>
        </div>
      </BrowserRouter>
    </ProjectContext.Provider>
  )
}
