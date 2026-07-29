import type { PatientListItem } from '@/shared/api/types'
import { PHASE_SEQUENCE } from '@/shared/phases'

export function getNeedsReviewPatients(patients: PatientListItem[]): PatientListItem[] {
  return patients
    .filter((patient) => patient.needs_review.length > 0)
    .sort((a, b) => b.needs_review.length - a.needs_review.length || a.name.localeCompare(b.name))
}

export function getPendingInvites(patients: PatientListItem[]): PatientListItem[] {
  return patients
    .filter((patient) => patient.invite_accepted_at === null)
    .sort((a, b) => a.name.localeCompare(b.name))
}

export function getPhaseDistribution(patients: PatientListItem[]): { phase: string; count: number }[] {
  const counts = new Map<string, number>()
  for (const patient of patients) {
    counts.set(patient.current_phase, (counts.get(patient.current_phase) ?? 0) + 1)
  }
  return PHASE_SEQUENCE.map((phase) => ({ phase, count: counts.get(phase) ?? 0 }))
}
