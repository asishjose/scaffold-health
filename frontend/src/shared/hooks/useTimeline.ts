import { useQuery } from '@tanstack/react-query'

import { api } from '@/shared/api/client'
import type { TimelineEntry, TimelinePortalEntry } from '@/shared/api/types'

export function useTimeline(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'timeline'],
    queryFn: () => api<TimelineEntry[]>(`/patients/${patientId}/timeline`),
  })
}

export function usePortalTimeline(patientId: string) {
  return useQuery({
    queryKey: ['patients', patientId, 'timeline', 'portal'],
    queryFn: () => api<TimelinePortalEntry[]>(`/patients/${patientId}/timeline`),
  })
}
