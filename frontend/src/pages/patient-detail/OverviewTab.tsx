import { useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import type { PatientDetail as PatientDetailType } from '@/shared/api/types'
import { useAdvancePhase } from '@/shared/hooks/usePatients'
import { formatDate, injuryLabel, weeksPostOpLabel } from '@/shared/lib/utils'
import { nextPhase, phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Label } from '@/shared/ui/label'
import { Textarea } from '@/shared/ui/textarea'

const PAIN_TREND_LABELS: Record<string, string> = {
  improving: 'Improving',
  worsening: 'Worsening',
  stable: 'Stable',
}

const PAIN_TREND_VARIANTS: Record<string, 'success' | 'destructive' | 'secondary'> = {
  improving: 'success',
  worsening: 'destructive',
  stable: 'secondary',
}

function ProfileSummaryCards({ patient }: { patient: PatientDetailType }) {
  const fields = [
    { label: 'Injury', value: injuryLabel(patient.injury) },
    { label: 'Surgery date', value: formatDate(patient.surgery_date) },
    { label: 'Recovery', value: weeksPostOpLabel(patient.surgery_date) },
    { label: 'Date of birth', value: formatDate(patient.date_of_birth) },
    { label: 'Contact email', value: patient.contact_email },
    { label: 'Record created', value: formatDate(patient.created_at) },
  ]
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
      {fields.map((field) => (
        <Card key={field.label}>
          <CardContent className="p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{field.label}</p>
            <p className="mt-1 truncate text-sm font-medium" title={field.value}>
              {field.value}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

function KnowledgeProfilePanel({ patient }: { patient: PatientDetailType }) {
  const groups = [
    { label: 'Active restrictions', values: patient.active_restrictions },
    { label: 'Active concerns', values: patient.active_concerns },
    { label: 'Milestones', values: patient.milestones },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Knowledge profile</CardTitle>
        <CardDescription>Extracted from uploaded documents.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {patient.pain_trend && (
            <Badge variant={PAIN_TREND_VARIANTS[patient.pain_trend]}>
              Pain trend: {PAIN_TREND_LABELS[patient.pain_trend]}
            </Badge>
          )}
          {patient.exercise_adherence !== null && (
            <span className="text-muted-foreground">
              Check-in adherence (7d):{' '}
              <span className="font-medium text-foreground">{patient.exercise_adherence}%</span>
            </span>
          )}
        </div>
        {groups.map((group) => (
          <div key={group.label}>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{group.label}</p>
            {group.values.length === 0 ? (
              <p className="mt-1 text-sm text-muted-foreground">None extracted yet.</p>
            ) : (
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
                {group.values.map((value) => (
                  <li key={value}>{value}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function PhaseAdvanceControl({ patient }: { patient: PatientDetailType }) {
  const advance = useAdvancePhase(patient.id)
  const [note, setNote] = useState('')
  const [confirming, setConfirming] = useState(false)
  const target = nextPhase(patient.current_phase)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!target) return
    if (!confirming) {
      setConfirming(true)
      return
    }
    advance.mutate(
      { target_phase: target, note: note.trim() || null },
      {
        onSuccess: () => {
          setNote('')
          setConfirming(false)
        },
        onError: () => setConfirming(false),
      },
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Phase progression</CardTitle>
        <CardDescription>Forward-only; one step at a time.</CardDescription>
      </CardHeader>
      <CardContent>
        {target === null ? (
          <p className="text-sm text-muted-foreground">
            {phaseLabel(patient.current_phase)} is the final phase — no further advancement.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex items-center gap-2 text-sm">
              <Badge variant="secondary">{phaseLabel(patient.current_phase)}</Badge>
              <span className="text-muted-foreground">→</span>
              <Badge>{phaseLabel(target)}</Badge>
            </div>
            <div className="space-y-2">
              <Label htmlFor="phase-note">Note (optional)</Label>
              <Textarea
                id="phase-note"
                maxLength={2000}
                placeholder="Reason or clinical observation for this advancement"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
            {advance.isError && (
              <p className="text-sm text-destructive">
                {advance.error instanceof ApiError && advance.error.status === 409
                  ? 'The phase transition was rejected — the record may have changed. Refresh and retry.'
                  : 'Phase advancement failed. Please try again.'}
              </p>
            )}
            <div className="flex items-center gap-3">
              <Button
                type="submit"
                variant={confirming ? 'destructive' : 'default'}
                disabled={advance.isPending}
              >
                {advance.isPending
                  ? 'Advancing…'
                  : confirming
                    ? `Confirm advance to ${phaseLabel(target)}`
                    : 'Advance phase'}
              </Button>
              {confirming && !advance.isPending && (
                <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
              )}
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}

export function OverviewTab() {
  const patient = useOutletContext<PatientDetailType>()

  return (
    <div className="space-y-6">
      <ProfileSummaryCards patient={patient} />
      <div className="grid gap-6 lg:grid-cols-2">
        <KnowledgeProfilePanel patient={patient} />
        <PhaseAdvanceControl patient={patient} />
      </div>
    </div>
  )
}
