import { Award, FileCheck, TrendingUp } from 'lucide-react'

import type { TimelineEntry, TimelineEntryType, TimelinePortalEntry } from '@/shared/api/types'
import { usePortalTimeline, useTimeline } from '@/shared/hooks/useTimeline'
import { formatDateTime } from '@/shared/lib/utils'
import { phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

const ENTRY_ICONS: Record<TimelineEntryType, typeof TrendingUp> = {
  phase_advance: TrendingUp,
  milestone: Award,
  document_extracted: FileCheck,
}

const ENTRY_LABELS: Record<TimelineEntryType, string> = {
  phase_advance: 'Phase advance',
  milestone: 'Milestone',
  document_extracted: 'Document processed',
}

function entrySummary(entry: TimelineEntry | TimelinePortalEntry): string {
  switch (entry.entry_type) {
    case 'phase_advance':
      return `${phaseLabel(entry.from_phase ?? '')} → ${phaseLabel(entry.to_phase ?? '')}`
    case 'milestone':
      return entry.value ?? ''
    case 'document_extracted':
      return `Document processed: ${entry.filename ?? ''}`
  }
}

export function PatientTimelinePanel({
  patientId,
  variant,
}: {
  patientId: string
  variant: 'therapist' | 'patient'
}) {
  const therapistQuery = useTimeline(patientId)
  const patientQuery = usePortalTimeline(patientId)
  const query = variant === 'therapist' ? therapistQuery : patientQuery
  const entries = [...(query.data ?? [])].reverse()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Timeline</CardTitle>
        <CardDescription>Phase advances, milestones, and processed documents.</CardDescription>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No timeline events yet.</p>
        ) : (
          <ul className="divide-y">
            {entries.map((entry) => {
              const Icon = ENTRY_ICONS[entry.entry_type]
              // The therapist variant's query returns TimelineEntry (with
              // provenance); the patient variant's TimelinePortalEntry never
              // carries these fields at all, so this cast is only read when
              // variant === 'therapist' below.
              const provenance = variant === 'therapist' ? (entry as TimelineEntry) : null
              return (
                <li key={entry.id} className="space-y-1 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Icon className="h-4 w-4 text-muted-foreground" />
                    <Badge variant="outline">{ENTRY_LABELS[entry.entry_type]}</Badge>
                    {provenance?.confidence != null && (
                      <span className="text-xs text-muted-foreground">
                        conf {provenance.confidence.toFixed(2)}
                      </span>
                    )}
                  </div>
                  <p className="text-sm font-medium">{entrySummary(entry)}</p>
                  {entry.entry_type === 'phase_advance' && entry.note && (
                    <p className="text-xs italic text-muted-foreground">{entry.note}</p>
                  )}
                  {provenance?.source_quote && (
                    <p className="text-xs italic text-muted-foreground">
                      “{provenance.source_quote}”
                    </p>
                  )}
                  <p className="text-xs text-muted-foreground">{formatDateTime(entry.occurred_at)}</p>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
