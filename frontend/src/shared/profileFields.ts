export const PROFILE_FIELD_LABELS: Record<string, string> = {
  injury: 'Injury',
  surgery_date: 'Surgery date',
  active_restrictions: 'Active restriction',
  active_concerns: 'Active concern',
  milestones: 'Milestone',
}

export function profileFieldLabel(fieldName: string): string {
  return PROFILE_FIELD_LABELS[fieldName] ?? fieldName
}

const NEEDS_REVIEW_VARIANTS: Record<string, 'destructive' | 'warning'> = {
  'Pending extraction': 'warning',
  'Adherence drop': 'warning',
  'No check-in': 'warning',
  'Symptom question': 'destructive',
}

export function needsReviewVariant(reason: string): 'destructive' | 'warning' {
  return NEEDS_REVIEW_VARIANTS[reason] ?? 'warning'
}
