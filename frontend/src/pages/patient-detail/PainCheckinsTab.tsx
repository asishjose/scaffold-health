import { useOutletContext } from 'react-router-dom'

import type { PatientDetail as PatientDetailType } from '@/shared/api/types'
import { cn, formatDateTime } from '@/shared/lib/utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

function PainHistoryPanel({ patient }: { patient: PatientDetailType }) {
  const history = [...patient.pain_history].sort(
    (a, b) => new Date(b.submitted_at).getTime() - new Date(a.submitted_at).getTime(),
  )
  return (
    <Card>
      <CardHeader>
        <CardTitle>Pain history</CardTitle>
        <CardDescription>Patient-submitted check-ins, newest first.</CardDescription>
      </CardHeader>
      <CardContent>
        {history.length === 0 ? (
          <p className="text-sm text-muted-foreground">No check-ins submitted yet.</p>
        ) : (
          <ul className="divide-y">
            {history.map((checkin) => (
              <li key={checkin.id} className="flex items-start gap-4 py-3">
                <span
                  className={cn(
                    'mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
                    checkin.pain_level >= 7
                      ? 'bg-destructive/10 text-destructive'
                      : checkin.pain_level >= 4
                        ? 'bg-amber-100 text-amber-900'
                        : 'bg-emerald-100 text-emerald-900',
                  )}
                >
                  {checkin.pain_level}
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(checkin.submitted_at)}
                  </p>
                  {checkin.note && <p className="mt-1 text-sm">{checkin.note}</p>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export function PainCheckinsTab() {
  const patient = useOutletContext<PatientDetailType>()
  return <PainHistoryPanel patient={patient} />
}
