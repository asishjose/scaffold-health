import { useMutation } from '@tanstack/react-query'

import { api } from '@/shared/api/client'
import type { AssistantAnswer } from '@/shared/api/types'

export function useAskAssistant(patientId: string) {
  return useMutation({
    mutationFn: (body: { question: string }) =>
      api<AssistantAnswer>(`/patients/${patientId}/assistant`, { method: 'POST', body }),
  })
}
