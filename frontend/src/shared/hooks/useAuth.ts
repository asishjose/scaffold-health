import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { api } from '@/shared/api/client'
import type {
  AcceptInviteResponse,
  InvitePreviewResponse,
  TherapistSignupResponse,
  TokenResponse,
} from '@/shared/api/types'
import { useAuthStore } from '@/shared/auth/authStore'

export function useLogin() {
  const setTokens = useAuthStore((s) => s.setTokens)
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api<TokenResponse>('/auth/login', { method: 'POST', body }),
    onSuccess: (data) => setTokens(data.access_token, data.refresh_token),
  })
}

export function useSignup() {
  return useMutation({
    mutationFn: (body: {
      name: string
      email: string
      password: string
      registration_code: string
    }) => api<TherapistSignupResponse>('/auth/signup', { method: 'POST', body }),
  })
}

export function useInvitePreview(token: string) {
  return useQuery({
    queryKey: ['invite', token],
    queryFn: () => api<InvitePreviewResponse>(`/auth/invite/${token}`),
    retry: false,
  })
}

export function useAcceptInvite(token: string) {
  return useMutation({
    mutationFn: (body: { password: string }) =>
      api<AcceptInviteResponse>(`/auth/invite/${token}`, { method: 'POST', body }),
  })
}

export function useLogout() {
  const clear = useAuthStore((s) => s.clear)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return () => {
    clear()
    queryClient.clear()
    navigate('/login')
  }
}
