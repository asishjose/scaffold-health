import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '@/shared/api/client'
import type { CheckIn } from '@/shared/api/types'

export function useSubmitCheckIn(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { pain_level: number; note: string | null }) =>
      api<CheckIn>(`/patients/${patientId}/checkins`, { method: 'POST', body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['portal-profile'] }),
  })
}
