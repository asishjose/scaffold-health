import { useMutation } from '@tanstack/react-query'

import { api } from '@/shared/api/client'
import type { Brief } from '@/shared/api/types'

export function useGenerateBrief(patientId: string) {
  return useMutation({
    mutationFn: () => api<Brief>(`/patients/${patientId}/brief`, { method: 'POST' }),
  })
}
