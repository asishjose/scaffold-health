import { ArrowDown, Award, Flag, MapPin, TrendingUp } from 'lucide-react'

import type { TimelineEntry, TimelineEntryType, TimelinePortalEntry } from '@/shared/api/types'
import { usePortalTimeline, useTimeline } from '@/shared/hooks/useTimeline'
import { formatDate, formatDateTime } from '@/shared/lib/utils'
import { phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

const ENTRY_ICONS: Record<TimelineEntryType, typeof TrendingUp> = {
  phase_advance: TrendingUp,
  milestone: Award,
  document_extracted: TrendingUp,
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

function TimelineConnector() {
  return (
    <div className="flex justify-center py-1">
      <ArrowDown className="h-4 w-4 text-muted-foreground" />
    </div>
  )
}

function TimelineAnchorCard({
  icon: Icon,
  label,
  detail,
}: {
  icon: typeof Flag
  label: string
  detail: string
}) {
  return (
    <div className="flex items-center gap-3 rounded-md border bg-accent/30 p-3">
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{detail}</p>
      </div>
    </div>
  )
}

export function PatientTimelinePanel({
  patientId,
  variant,
  surgeryDate,
  currentPhase,
}: {
  patientId: string
  variant: 'therapist' | 'patient'
  surgeryDate: string
  currentPhase: string
}) {
  const therapistQuery = useTimeline(patientId)
  const patientQuery = usePortalTimeline(patientId)
  const query = variant === 'therapist' ? therapistQuery : patientQuery
  const entries = (query.data ?? []).filter((entry) => entry.entry_type !== 'document_extracted')

  return (
    <Card>
      <CardHeader>
        <CardTitle>Timeline</CardTitle>
        <CardDescription>From surgery to current state.</CardDescription>
      </CardHeader>
      <CardContent>
        <TimelineAnchorCard icon={Flag} label="Surgery" detail={formatDate(surgeryDate)} />
        <TimelineConnector />
        {entries.map((entry) => {
          const Icon = ENTRY_ICONS[entry.entry_type]
          // The therapist variant's query returns TimelineEntry (with
          // provenance); the patient variant's TimelinePortalEntry never
          // carries these fields at all, so this cast is only read when
          // variant === 'therapist' below.
          const provenance = variant === 'therapist' ? (entry as TimelineEntry) : null
          return (
            <div key={entry.id}>
              <div className="space-y-1 rounded-md border p-3">
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
              </div>
              <TimelineConnector />
            </div>
          )
        })}
        <TimelineAnchorCard icon={MapPin} label="Current state" detail={phaseLabel(currentPhase)} />
      </CardContent>
    </Card>
  )
}
