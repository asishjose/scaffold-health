import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/shared/api/client'
import type { CopilotMessage } from '@/shared/api/types'

function copilotMessagesQueryKey(patientId: string) {
  return ['patients', patientId, 'copilot-messages']
}

export function useCopilotMessages(patientId: string) {
  return useQuery({
    queryKey: copilotMessagesQueryKey(patientId),
    queryFn: () => api<CopilotMessage[]>(`/patients/${patientId}/copilot/messages`),
  })
}

export function useSendCopilotMessage(patientId: string) {
  const queryClient = useQueryClient()
  const queryKey = copilotMessagesQueryKey(patientId)

  return useMutation({
    mutationFn: (body: { content: string }) =>
      api<CopilotMessage>(`/patients/${patientId}/copilot/messages`, { method: 'POST', body }),
    onMutate: async (body) => {
      await queryClient.cancelQueries({ queryKey })
      const previousMessages = queryClient.getQueryData<CopilotMessage[]>(queryKey)
      const optimisticMessage: CopilotMessage = {
        id: `optimistic-${crypto.randomUUID()}`,
        patient_id: patientId,
        role: 'therapist',
        content: body.content,
        posted_at: new Date().toISOString(),
      }
      queryClient.setQueryData<CopilotMessage[]>(queryKey, (old) => [
        ...(old ?? []),
        optimisticMessage,
      ])
      return { previousMessages }
    },
    onError: (_err, _body, context) => {
      if (context?.previousMessages) {
        queryClient.setQueryData(queryKey, context.previousMessages)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey })
    },
  })
}
