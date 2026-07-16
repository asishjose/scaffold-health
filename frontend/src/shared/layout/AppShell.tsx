import { Activity, LogOut } from 'lucide-react'
import { Link, Outlet } from 'react-router-dom'

import { Button } from '@/shared/ui/button'
import { useAuthStore } from '@/shared/auth/authStore'
import { homeFor } from '@/shared/auth/ProtectedRoute'
import { useLogout } from '@/shared/hooks/useAuth'

export function AppShell() {
  const role = useAuthStore((s) => s.role)
  const logout = useLogout()

  return (
    <div className="min-h-screen">
      <header className="border-b bg-card">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <Link to={homeFor(role)} className="flex items-center gap-2 font-semibold">
            <Activity className="h-5 w-5 text-primary" />
            Scaffold Health
          </Link>
          <div className="flex items-center gap-3">
            <span className="text-sm capitalize text-muted-foreground">{role}</span>
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="h-4 w-4" />
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
