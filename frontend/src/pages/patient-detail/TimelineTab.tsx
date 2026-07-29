import { useOutletContext } from 'react-router-dom'

import type { PatientDetail as PatientDetailType } from '@/shared/api/types'
import { PatientTimelinePanel } from '@/shared/components/PatientTimelinePanel'

export function TimelineTab() {
  const patient = useOutletContext<PatientDetailType>()
  return <PatientTimelinePanel patientId={patient.id} variant="therapist" />
}
