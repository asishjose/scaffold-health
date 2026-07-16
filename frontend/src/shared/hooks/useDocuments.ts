import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/shared/api/client'
import type { DocumentListItem, DocumentStatus } from '@/shared/api/types'

export function useDocuments(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'documents'],
    queryFn: () => api<DocumentListItem[]>(`/patients/${patientId}/documents`),
    // Poll while any document is still processing (PRD: poll/refetch, no websockets).
    refetchInterval: (query) =>
      query.state.data?.some((doc) => (doc.status as DocumentStatus) === 'processing')
        ? 3000
        : false,
  })
}

export function useUploadDocument(patientId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      return api<DocumentListItem>(`/patients/${patientId}/documents`, {
        method: 'POST',
        formData,
      })
    },
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['patients', patientId, 'documents'] }),
  })
}
