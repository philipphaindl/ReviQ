import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { createContext, useContext, useState } from 'react'
import NavBar from './components/layout/NavBar'
import Overview from './pages/Overview'
import Settings from './pages/Settings'
import Search from './pages/Search'
import Screening from './pages/Screening'
import { EligibilityStub, SnowballingStub, QualityStub, ExtractionStub, ResultsStub } from './pages/Stubs'

// ── Project context ───────────────────────────────────────────────────────────

interface ProjectContextValue {
  projectId: number | null
  setProjectId: (id: number | null) => void
}

export const ProjectContext = createContext<ProjectContextValue>({
  projectId: null,
  setProjectId: () => {},
})

export const useProject = () => useContext(ProjectContext)

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [projectId, setProjectId] = useState<number | null>(() => {
    const stored = localStorage.getItem('reviq_project_id')
    return stored ? parseInt(stored, 10) : null
  })

  const handleSetProjectId = (id: number | null) => {
    setProjectId(id)
    if (id) localStorage.setItem('reviq_project_id', String(id))
    else localStorage.removeItem('reviq_project_id')
  }

  return (
    <ProjectContext.Provider value={{ projectId, setProjectId: handleSetProjectId }}>
      <BrowserRouter>
        <div className="min-h-screen bg-white flex flex-col">
          <NavBar />
          <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6">
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
      </BrowserRouter>
    </ProjectContext.Provider>
  )
}
