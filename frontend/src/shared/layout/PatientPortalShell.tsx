import { Activity, LogOut } from 'lucide-react'
import { Link, Outlet } from 'react-router-dom'

import { useLogout } from '@/shared/hooks/useAuth'
import { PatientPortalSidebar } from '@/shared/layout/PatientPortalSidebar'
import { Button } from '@/shared/ui/button'

export function PatientPortalShell() {
  const logout = useLogout()

  return (
    <div className="flex h-screen flex-col">
      <header className="border-b bg-card">
        <div className="flex h-14 items-center justify-between px-4">
          <Link to="/patient" className="flex items-center gap-2 font-semibold">
            <Activity className="h-5 w-5 text-primary" />
            Scaffold Health
          </Link>
          <div className="flex items-center gap-3">
            <span className="text-sm capitalize text-muted-foreground">patient</span>
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="h-4 w-4" />
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <aside className="w-60 shrink-0 overflow-y-auto border-r bg-card">
          <PatientPortalSidebar />
        </aside>
        <main className="flex-1 overflow-y-auto px-8 py-8">
          <div className="mx-auto max-w-3xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
