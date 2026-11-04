import { Route, Routes } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { LABS } from '@/pages/labs'
import { CaseWorkspace } from '@/pages/CaseWorkspace'
import { Dashboard } from '@/pages/Dashboard'
import { EvidenceDetail } from '@/pages/EvidenceDetail'
import { FindingsPage } from '@/pages/Findings'
import { Investigations } from '@/pages/Investigations'
import { LabPlaceholder } from '@/pages/LabPlaceholder'
import { NotFound } from '@/pages/NotFound'
import { SettingsPage } from '@/pages/Settings'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="investigations" element={<Investigations />} />
        <Route path="investigations/:caseId" element={<CaseWorkspace />} />
        <Route path="investigations/:caseId/evidence/:evidenceId" element={<EvidenceDetail />} />
        <Route path="findings" element={<FindingsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        {LABS.map((lab) => (
          <Route key={lab.path} path={lab.path} element={<LabPlaceholder lab={lab} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
