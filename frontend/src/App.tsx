import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { useAuthStore } from '@/shared/auth/authStore'
import { homeFor, ProtectedRoute } from '@/shared/auth/ProtectedRoute'
import { AppShell } from '@/shared/layout/AppShell'
import { IntakeForm } from '@/pages/IntakeForm'
import { InviteAccept } from '@/pages/InviteAccept'
import { Login } from '@/pages/Login'
import { PatientDetail } from '@/pages/PatientDetail'
import { PatientList } from '@/pages/PatientList'
import { PatientPortal } from '@/pages/PatientPortal'
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
            <Route element={<AppShell />}>
              <Route path="/dashboard" element={<PatientList />} />
              <Route path="/patients/new" element={<IntakeForm />} />
              <Route path="/patients/:id" element={<PatientDetail />} />
            </Route>
          </Route>

          <Route element={<ProtectedRoute role="patient" />}>
            <Route element={<AppShell />}>
              <Route path="/patient" element={<PatientPortal />} />
            </Route>
          </Route>

          <Route path="*" element={<RootRedirect />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
