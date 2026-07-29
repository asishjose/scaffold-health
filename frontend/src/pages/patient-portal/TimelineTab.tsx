import { useOutletContext } from 'react-router-dom'

import type { PatientPortalDetail } from '@/shared/api/types'
import { PatientTimelinePanel } from '@/shared/components/PatientTimelinePanel'

export function TimelineTab() {
  const profile = useOutletContext<PatientPortalDetail>()
  return <PatientTimelinePanel patientId={profile.id} variant="patient" />
}
