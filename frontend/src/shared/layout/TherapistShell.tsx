import { Activity, LogOut } from 'lucide-react'
import { Link, Outlet, useMatch } from 'react-router-dom'

import { useLogout } from '@/shared/hooks/useAuth'
import { GlobalSidebar } from '@/shared/layout/GlobalSidebar'
import { PatientSidebar } from '@/shared/layout/PatientSidebar'
import { Button } from '@/shared/ui/button'

export function TherapistShell() {
  const logout = useLogout()
  const rawPatientMatch = useMatch('/patients/:id/*')
  // "/patients/new" is a sibling static route, not a patient id — exclude it,
  // since useMatch pattern-matches the URL independently of sibling routes.
  const patientMatch =
    rawPatientMatch && rawPatientMatch.params.id !== 'new' ? rawPatientMatch : null

  return (
    <div className="flex h-screen flex-col">
      <header className="border-b bg-card">
        <div className="flex h-14 items-center justify-between px-4">
          <Link to="/dashboard" className="flex items-center gap-2 font-semibold">
            <Activity className="h-5 w-5 text-primary" />
            Scaffold Health
          </Link>
          <div className="flex items-center gap-3">
            <span className="text-sm capitalize text-muted-foreground">therapist</span>
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="h-4 w-4" />
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <aside className="flex shrink-0 overflow-y-auto border-r bg-card">
          <div className="w-60 shrink-0 border-r bg-card">
            <GlobalSidebar patientActive={!!patientMatch} />
          </div>
          {patientMatch && (
            <div className="w-60 shrink-0 bg-card">
              <PatientSidebar patientId={patientMatch.params.id!} />
            </div>
          )}
        </aside>
        <main className="flex-1 overflow-y-auto px-8 py-8">
          <div className="mx-auto max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
