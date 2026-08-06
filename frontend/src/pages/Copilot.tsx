import { Search, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { PatientListItem } from '@/shared/api/types'
import { CopilotChatPanel } from '@/shared/components/CopilotChatPanel'
import { NeedsReviewBadges } from '@/shared/components/NeedsReviewBadges'
import { usePatients } from '@/shared/hooks/usePatients'
import { cn } from '@/shared/lib/utils'
import { phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'

function sortForCopilot(patients: PatientListItem[]): PatientListItem[] {
  return [...patients].sort(
    (a, b) => b.needs_review.length - a.needs_review.length || a.name.localeCompare(b.name),
  )
}

export function Copilot() {
  const patients = usePatients()
  const [filter, setFilter] = useState('')
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null)

  const sortedPatients = useMemo(
    () => (patients.data ? sortForCopilot(patients.data) : []),
    [patients.data],
  )
  const visiblePatients = useMemo(
    () =>
      filter.trim()
        ? sortedPatients.filter((p) => p.name.toLowerCase().includes(filter.trim().toLowerCase()))
        : sortedPatients,
    [sortedPatients, filter],
  )
  const selectedPatient = sortedPatients.find((p) => p.id === selectedPatientId) ?? null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <Sparkles className="h-5 w-5 text-primary" />
          Therapist Copilot
        </h1>
        <p className="text-sm text-muted-foreground">
          Pick a patient to chat with an AI copilot grounded in their chart.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <Card className="flex max-h-[70vh] flex-col">
          <CardHeader className="space-y-3">
            <CardTitle>Select a patient</CardTitle>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Filter by name…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="pl-9"
              />
            </div>
          </CardHeader>
          <CardContent className="flex-1 space-y-1 overflow-y-auto pt-0">
            {patients.isPending && (
              <p className="text-sm text-muted-foreground">Loading caseload…</p>
            )}
            {patients.isError && (
              <p className="text-sm text-destructive">Failed to load caseload.</p>
            )}
            {patients.isSuccess && visiblePatients.length === 0 && (
              <p className="text-sm text-muted-foreground">No matching patients.</p>
            )}
            {visiblePatients.map((patient) => (
              <button
                key={patient.id}
                type="button"
                onClick={() => setSelectedPatientId(patient.id)}
                className={cn(
                  'flex w-full flex-col gap-1.5 rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent/60',
                  selectedPatientId === patient.id && 'bg-accent',
                )}
              >
                <span className="font-medium">{patient.name}</span>
                <div className="flex flex-wrap items-center gap-1">
                  <Badge variant="secondary">{phaseLabel(patient.current_phase)}</Badge>
                  <NeedsReviewBadges reasons={patient.needs_review} />
                </div>
              </button>
            ))}
          </CardContent>
        </Card>

        {selectedPatient ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-lg font-semibold">{selectedPatient.name}</h2>
              <Badge variant="secondary">{phaseLabel(selectedPatient.current_phase)}</Badge>
              <NeedsReviewBadges reasons={selectedPatient.needs_review} />
            </div>
            <CopilotChatPanel key={selectedPatient.id} patientId={selectedPatient.id} />
          </div>
        ) : (
          <Card>
            <CardContent className="flex h-full min-h-[200px] items-center justify-center p-8 text-center">
              <CardDescription>Select a patient to start a conversation.</CardDescription>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
