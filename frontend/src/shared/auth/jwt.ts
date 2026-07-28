import type { Role } from '@/shared/api/types'

interface JwtClaims {
  sub?: string
  role?: Role
  exp?: number
}

export function decodeJwt(token: string): JwtClaims {
  try {
    const payload = token.split('.')[1]
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json) as JwtClaims
  } catch {
    return {}
  }
}
