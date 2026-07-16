import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/shared/api/client'
import type {
  PatientDetail,
  PatientIntakeResponse,
  PatientListItem,
  PatientPortalDetail,
  PhaseAdvanceResponse,
} from '@/shared/api/types'
import { useAuthStore } from '@/shared/auth/authStore'

export function usePatients() {
  return useQuery({
    queryKey: ['patients'],
    queryFn: () => api<PatientListItem[]>('/patients'),
  })
}

export function usePatient(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId],
    queryFn: () => api<PatientDetail>(`/patients/${patientId}`),
  })
}

/** The logged-in patient's own reduced profile (id comes from the JWT `sub`). */
export function usePortalProfile() {
  const userId = useAuthStore((s) => s.userId)
  return useQuery({
    queryKey: ['portal-profile', userId],
    queryFn: () => api<PatientPortalDetail>(`/patients/${userId}`),
    enabled: userId !== null,
  })
}

export function useCreatePatient() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      name: string
      date_of_birth: string
      contact_email: string
      surgery_date: string
    }) => api<PatientIntakeResponse>('/patients', { method: 'POST', body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['patients'] }),
  })
}

export function useAdvancePhase(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { target_phase: string; note: string | null }) =>
      api<PhaseAdvanceResponse>(`/patients/${patientId}/phase`, { method: 'POST', body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['patients'] }),
  })
}
