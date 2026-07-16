// Mirrors PHASE_SEQUENCE in backend/app/patients/events.py.
export const PHASE_SEQUENCE = [
  'pre_op',
  'phase_1_protection',
  'phase_2_early_strength',
  'phase_3_progressive_strength',
  'phase_4_advanced_strength',
  'phase_5_return_to_sport',
  'discharged',
] as const

export const PHASE_LABELS: Record<string, string> = {
  pre_op: 'Pre-Op',
  phase_1_protection: 'Phase 1 — Protection',
  phase_2_early_strength: 'Phase 2 — Early Strength',
  phase_3_progressive_strength: 'Phase 3 — Progressive Strength',
  phase_4_advanced_strength: 'Phase 4 — Advanced Strength',
  phase_5_return_to_sport: 'Phase 5 — Return to Sport',
  discharged: 'Discharged',
}

export function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase] ?? phase
}

/** The single next phase in sequence, or null if already at the end. */
export function nextPhase(current: string): string | null {
  const index = PHASE_SEQUENCE.indexOf(current as (typeof PHASE_SEQUENCE)[number])
  if (index === -1 || index + 1 >= PHASE_SEQUENCE.length) return null
  return PHASE_SEQUENCE[index + 1]
}
