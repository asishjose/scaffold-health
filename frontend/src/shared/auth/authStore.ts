import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { Role } from '@/shared/api/types'
import { decodeJwt } from '@/shared/auth/jwt'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  role: Role | null
  userId: string | null
  setTokens: (accessToken: string, refreshToken: string) => void
  setAccessToken: (accessToken: string) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      role: null,
      userId: null,
      setTokens: (accessToken, refreshToken) => {
        const claims = decodeJwt(accessToken)
        set({
          accessToken,
          refreshToken,
          role: claims.role ?? null,
          userId: claims.sub ?? null,
        })
      },
      setAccessToken: (accessToken) => set({ accessToken }),
      clear: () => set({ accessToken: null, refreshToken: null, role: null, userId: null }),
    }),
    { name: 'scaffold-auth' },
  ),
)
