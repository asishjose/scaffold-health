import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/shared/api/client'
import type { Brief } from '@/shared/api/types'

export function useLatestBrief(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'brief'],
    queryFn: () => api<Brief | null>(`/patients/${patientId}/brief`),
  })
}

export function useGenerateBrief(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api<Brief>(`/patients/${patientId}/brief`, { method: 'POST' }),
    onSuccess: (brief) => {
      queryClient.setQueryData(['patients', patientId, 'brief'], brief)
    },
  })
}
