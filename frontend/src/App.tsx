import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { useAuthStore } from '@/shared/auth/authStore'
import { homeFor, ProtectedRoute } from '@/shared/auth/ProtectedRoute'
import { PatientPortalShell } from '@/shared/layout/PatientPortalShell'
import { TherapistShell } from '@/shared/layout/TherapistShell'
import { Caseload } from '@/pages/Caseload'
import { Copilot } from '@/pages/Copilot'
import { Dashboard } from '@/pages/Dashboard'
import { IntakeForm } from '@/pages/IntakeForm'
import { InviteAccept } from '@/pages/InviteAccept'
import { Login } from '@/pages/Login'
import { DocumentsTab } from '@/pages/patient-detail/DocumentsTab'
import { OverviewTab } from '@/pages/patient-detail/OverviewTab'
import { PainCheckinsTab } from '@/pages/patient-detail/PainCheckinsTab'
import { PatientDetailShell } from '@/pages/patient-detail/PatientDetailShell'
import { ProvenanceTab } from '@/pages/patient-detail/ProvenanceTab'
import { TimelineTab } from '@/pages/patient-detail/TimelineTab'
import { AssistantTab } from '@/pages/patient-portal/AssistantTab'
import { CheckInTab } from '@/pages/patient-portal/CheckInTab'
import { PatientPortalHome } from '@/pages/patient-portal/PatientPortalHome'
import { OverviewTab as PatientOverviewTab } from '@/pages/patient-portal/OverviewTab'
import { TimelineTab as PatientTimelineTab } from '@/pages/patient-portal/TimelineTab'
import { Signup } from '@/pages/Signup'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function RootRedirect() {
  const role = useAuthStore((s) => s.role)
  const accessToken = useAuthStore((s) => s.accessToken)
  return <Navigate to={accessToken ? homeFor(role) : '/login'} replace />
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/invite/:token" element={<InviteAccept />} />

          <Route element={<ProtectedRoute role="therapist" />}>
            <Route element={<TherapistShell />}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/caseload" element={<Caseload />} />
              <Route path="/copilot" element={<Copilot />} />
              <Route path="/patients/new" element={<IntakeForm />} />
              <Route path="/patients/:id" element={<PatientDetailShell />}>
                <Route index element={<OverviewTab />} />
                <Route path="documents" element={<DocumentsTab />} />
                <Route path="checkins" element={<PainCheckinsTab />} />
                <Route path="timeline" element={<TimelineTab />} />
                <Route path="provenance" element={<ProvenanceTab />} />
              </Route>
            </Route>
          </Route>

          <Route element={<ProtectedRoute role="patient" />}>
            <Route element={<PatientPortalShell />}>
              <Route path="/patient" element={<PatientPortalHome />}>
                <Route index element={<PatientOverviewTab />} />
                <Route path="checkin" element={<CheckInTab />} />
                <Route path="timeline" element={<PatientTimelineTab />} />
                <Route path="assistant" element={<AssistantTab />} />
              </Route>
            </Route>
          </Route>

          <Route path="*" element={<RootRedirect />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
