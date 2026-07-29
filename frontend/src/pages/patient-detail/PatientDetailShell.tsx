import { Outlet, useParams } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import { NeedsReviewBadges } from '@/shared/components/NeedsReviewBadges'
import { usePatient } from '@/shared/hooks/usePatients'
import { phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'

export function PatientDetailShell() {
  const { id = '' } = useParams()
  const patient = usePatient(id)

  if (patient.isPending) {
    return <p className="text-sm text-muted-foreground">Loading patient…</p>
  }
  if (patient.isError) {
    return (
      <p className="text-sm text-destructive">
        {patient.error instanceof ApiError && patient.error.status === 404
          ? 'Patient not found.'
          : 'Failed to load the patient record.'}
      </p>
    )
  }

  const data = patient.data

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">{data.name}</h1>
        <Badge variant="secondary">{phaseLabel(data.current_phase)}</Badge>
        {!data.invite_accepted_at && <Badge variant="warning">Invite pending</Badge>}
        <NeedsReviewBadges reasons={data.needs_review} />
      </div>
      <Outlet context={data} />
    </div>
  )
}
