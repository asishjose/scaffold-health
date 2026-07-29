import { Outlet } from 'react-router-dom'

import { usePortalProfile } from '@/shared/hooks/usePatients'
import { weeksPostOpLabel } from '@/shared/lib/utils'
import { phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'

export function PatientPortalHome() {
  const profile = usePortalProfile()

  if (profile.isPending) {
    return <p className="text-sm text-muted-foreground">Loading your recovery profile…</p>
  }
  if (profile.isError) {
    return <p className="text-sm text-destructive">Failed to load your profile. Try refreshing.</p>
  }

  const data = profile.data

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">Hi, {data.name.split(' ')[0]}</h1>
        <Badge className="text-sm">{phaseLabel(data.current_phase)}</Badge>
        <span className="text-sm text-muted-foreground">{weeksPostOpLabel(data.surgery_date)}</span>
      </div>
      <Outlet context={data} />
    </div>
  )
}
