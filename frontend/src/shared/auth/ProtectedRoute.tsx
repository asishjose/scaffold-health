import { Navigate, Outlet } from 'react-router-dom'

import type { Role } from '@/shared/api/types'
import { useAuthStore } from '@/shared/auth/authStore'

export function homeFor(role: Role | null): string {
  if (role === 'therapist') return '/dashboard'
  if (role === 'patient') return '/patient'
  return '/login'
}

export function ProtectedRoute({ role }: { role: Role }) {
  const accessToken = useAuthStore((s) => s.accessToken)
  const userRole = useAuthStore((s) => s.role)

  if (!accessToken) return <Navigate to="/login" replace />
  if (userRole !== role) return <Navigate to={homeFor(userRole)} replace />
  return <Outlet />
}
