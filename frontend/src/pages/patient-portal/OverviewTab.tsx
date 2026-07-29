import { useOutletContext } from 'react-router-dom'

import type { PatientPortalDetail } from '@/shared/api/types'
import { formatDate, injuryLabel, weeksPostOpLabel } from '@/shared/lib/utils'
import { phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

const PAIN_TREND_COPY: Record<string, string> = {
  improving: 'Your reported pain has been trending down recently.',
  worsening: 'Your reported pain has been trending up recently.',
  stable: 'Your reported pain has been holding steady recently.',
}

export function OverviewTab() {
  const profile = useOutletContext<PatientPortalDetail>()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Your recovery</CardTitle>
        <CardDescription>
          {injuryLabel(profile.injury)} · surgery on {formatDate(profile.surgery_date)}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <Badge className="text-sm">{phaseLabel(profile.current_phase)}</Badge>
          <span className="text-sm text-muted-foreground">
            {weeksPostOpLabel(profile.surgery_date)}
          </span>
        </div>
        {profile.pain_trend && (
          <p className="text-sm text-muted-foreground">{PAIN_TREND_COPY[profile.pain_trend]}</p>
        )}
      </CardContent>
    </Card>
  )
}
